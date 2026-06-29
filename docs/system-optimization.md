# System Optimization — Medical Record Summarization

> Tài liệu mô tả chiến lược tối ưu hệ thống tóm tắt hồ sơ bệnh án,
> hướng tới phục vụ hàng triệu bệnh nhân trong môi trường production.

---

## 1. Scaling

### 1.1 Đặc điểm hệ thống ảnh hưởng đến scaling

Mỗi request chỉ xử lý data của **1 patient** (~50-100 chunks). Không có global aggregation hay cross-patient query. Điều này có nghĩa:

- Scale chủ yếu là **scale concurrent requests**, không phải scale data volume per request.
- DB query luôn filter theo `patient_id` → dù 100 triệu rows, mỗi query chỉ chạm ~100 rows nhờ index.
- Bottleneck nằm ở **LLM API call** (5-15 giây/request), không phải DB hay Python processing.

### 1.2 Kiến trúc target

```
┌──────────────────────────────────────────────────────────────┐
│                      CLIENTS (Bác sĩ)                        │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
                Load Balancer (Nginx / ALB)
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       API-1        API-2        API-3         ← Stateless, auto-scale
          │            │            │
          └────────────┼────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Redis       PostgreSQL   Message Queue
       (Cache)     (Data)       (Celery + RabbitMQ)
                       │               │
                 Read Replicas    Background Workers
                                  (pre-compute pipeline)
```

### 1.3 Scaling từng tầng

#### Tầng API — Horizontal scaling

- FastAPI stateless: không giữ state trong memory, mọi state nằm ở Redis/DB.
- Container hóa (Docker) → deploy trên Kubernetes, ECS, hoặc Cloud Run.
- Auto-scale theo CPU/memory hoặc request queue depth.

| Instances | Concurrent requests (ước tính) |
|-----------|-------------------------------|
| 1         | ~50                           |
| 3         | ~150                          |
| 10        | ~500                          |
| Auto      | Theo demand                   |

#### Tầng Database — PostgreSQL

- **Index chính**: `(patient_id)` trên bảng `source_chunks` và `summaries`.
- **Compound index**: `(patient_id, source_type)` nếu cần DB-level filtering sau này.
- **Connection pooling**: PgBouncer phía trước PostgreSQL, tránh connection exhaustion.
- **Read replicas**: API đọc từ replica, chỉ write vào primary. Phù hợp vì hệ thống read-heavy (đọc summary >> ghi data mới).
- **Table partitioning**: Partition bảng `source_chunks` theo `patient_id` range khi vượt 50M rows.

Ước tính data volume:

| Quy mô bệnh nhân | Chunks          | DB xử lý     |
|--------------------|-----------------|---------------|
| 10                 | ~500 rows       | Trivial       |
| 1,000              | ~50K rows       | Trivial       |
| 100,000            | ~5M rows        | Tốt với index |
| 1,000,000          | ~50-100M rows   | Partition     |

#### Tầng Cache — Redis

- Cache **summary result** theo `patient_id` + `data_hash`.
- Giảm LLM calls từ N requests/patient xuống còn 1.
- TTL 7 ngày để tự dọn cache của bệnh nhân không còn active.
- Chi tiết cache strategy → xem mục 2.2.

#### Tầng Background Workers — Message Queue

- **Celery + RabbitMQ** (hoặc Redis làm broker nếu muốn đơn giản).
- Worker nhận event "patient data changed" → chạy pipeline → lưu summary vào cache.
- Rate limit worker để không vượt LLM API quota.
- Retry tự động nếu LLM fail (đã có circuit breaker + exponential backoff).

### 1.4 Thứ tự triển khai

| Phase   | Việc cần làm                              | Giải quyết                    |
|---------|-------------------------------------------|-------------------------------|
| Phase 1 | Redis cache cho summary result            | Giảm 90%+ LLM calls          |
| Phase 2 | Message queue + background workers        | Bác sĩ không đợi pipeline    |
| Phase 3 | Multi-instance API + load balancer        | Concurrent users cao          |
| Phase 4 | DB read replicas + PgBouncer              | DB throughput                 |
| Phase 5 | Auto-scaling + monitoring + alerting      | Vận hành ổn định              |

Mỗi phase độc lập, thêm dần. Không cần build hết từ đầu.

---

## 2. Latency Optimization

### 2.1 Phân tích nguồn gây trễ

| Bước               | Thời gian   | Chiếm tỷ lệ |
|---------------------|-------------|-------------|
| DB query chunks     | ~5ms        | 0.05%       |
| Python filter/sort  | ~0.1ms      | ~0%         |
| **LLM calls (9 sections)** | **5-15 giây** | **99.9%** |

Tối ưu DB hay Python không có ý nghĩa. Toàn bộ chiến lược tập trung vào **giảm hoặc loại bỏ thời gian chờ LLM**.

### 2.2 Chiến lược 1: Caching — Triệt tiêu latency cho repeat requests

**Cơ chế: Data version hash**

```
data_hash = hash(toàn bộ raw data của patient)

Cache key: summary:{patient_id}:{data_hash}
```

Luồng xử lý:

```
Bác sĩ request summary P001
    → Tính data_hash từ DB (~2ms, 1 query)
    → Tìm cache key "summary:P001:abc123"
        → Hit  → Trả summary ngay (~1ms)
        → Miss → Data đã thay đổi hoặc chưa có cache
                → Chạy pipeline → Lưu cache → Trả kết quả
```

**Khi nào cache miss (invalidation)?**

Có 2 trigger duy nhất:

1. **Data bệnh nhân thay đổi** (encounter mới, thuốc thay đổi, xét nghiệm mới, chẩn đoán cập nhật, dị ứng mới). Hash thay đổi → cache key mới → miss tự nhiên. Chỉ ảnh hưởng 1 patient.

2. **Pipeline/prompt thay đổi** (cập nhật prompt template, nâng cấp LLM model, sửa logic chunker/retriever). Hiếm nhưng ảnh hưởng toàn bộ → flush all cache.

**TTL**: 7 ngày — không dùng để đảm bảo correctness (data hash đã lo), chỉ để giải phóng memory Redis cho bệnh nhân không còn active.

**Hiệu quả**: 1 patient chỉ gọi LLM **1 lần** cho tới khi data thay đổi. 1 triệu patients ≠ 1 triệu LLM calls.

### 2.3 Chiến lược 2: Pre-compute — Triệt tiêu latency cho first request

```
Event: encounter mới cho P001
    → Message Queue
    → Background worker chạy pipeline
    → Summary lưu vào cache
    → Bác sĩ mở hồ sơ sau đó: summary đã sẵn sàng (~1ms)
```

Bác sĩ **không bao giờ đợi LLM**. Summary luôn có sẵn trước khi được xem.

Kết hợp với caching:

| Tình huống                  | Latency         |
|------------------------------|-----------------|
| Summary đã có trong cache    | ~1ms            |
| Data mới, worker đã chạy xong | ~1ms           |
| Data mới, worker chưa xong   | 5-15s (fallback chạy on-demand) |

### 2.4 Chiến lược 3: Streaming response — Giảm perceived latency

```
Không streaming:
  Bác sĩ đợi ████████████████████ 12s → thấy toàn bộ summary

Streaming:
  Section "Thông tin BN"    hiện sau 1.5s  ██
  Section "Thuốc đang dùng" hiện sau 2.5s  ████
  Section "XN bất thường"   hiện sau 3.5s  ██████
  ...
```

Tổng thời gian không đổi, nhưng bác sĩ thấy dữ liệu xuất hiện dần thay vì nhìn màn hình trắng 12 giây. **Perceived latency giảm từ 12s xuống ~1.5s** (thời gian section đầu tiên hiện).

Cách triển khai:
- API trả Server-Sent Events (SSE) hoặc chunked HTTP response.
- Mỗi section hoàn thành → push ngay cho client.
- Frontend render progressive: section nào có thì hiển thị, section chưa có thì skeleton loading.

### 2.5 Chiến lược 4: Tiered model — Giảm actual latency

Không phải section nào cũng cần model mạnh nhất:

| Section                           | Độ phức tạp        | Model phù hợp     | Latency |
|------------------------------------|--------------------|--------------------|---------|
| `allergies`, `current_medications` | Liệt kê data      | Haiku (nhanh, rẻ)  | ~0.5s   |
| `abnormal_labs`, `diagnoses`       | Filter + format    | Sonnet (cân bằng)  | ~1-2s   |
| `overview`, `treatment_timeline`   | Tổng hợp, suy luận | Opus (mạnh nhất)  | ~3-5s   |

Hiệu quả: tổng latency giảm vì các section đơn giản hoàn thành nhanh hơn, kết hợp với streaming → bác sĩ thấy kết quả sớm hơn.

### 2.6 Chiến lược 5: Parallel section generation (đã có)

Hệ thống đã dùng `ThreadPoolExecutor` để gọi LLM song song cho 9 sections. Latency = section chậm nhất (~3-5s) thay vì tổng 9 sections (~30-45s).

Tối ưu thêm:
- Với local LLM (LMStudio/Ollama): giới hạn 3 workers tránh overload GPU.
- Với cloud API: tăng workers = số sections, tận dụng concurrency.

### 2.7 Tổng hợp — Ưu tiên triển khai

| Chiến lược       | Latency đạt được        | Effort triển khai                     |
|-------------------|--------------------------|---------------------------------------|
| **Pre-compute**   | 15s → ~1ms               | Cao (cần message queue + worker)      |
| **Streaming**     | Perceived 15s → ~1.5s    | Trung bình (sửa API + frontend)      |
| **Tiered model**  | 15s → ~5s                | Thấp (config model per section)      |
| **Caching**       | Repeat: 15s → ~1ms       | Thấp (thêm Redis)                    |
| **Parallel**      | Đã có                    | Đã triển khai                         |

Ưu tiên: **Caching → Pre-compute → Streaming → Tiered model**.

---

## 3. Fault Tolerance

Triết lý: **graceful degradation** — hệ thống y tế không được sập hoàn toàn vì một thành phần lỗi. Bác sĩ luôn nhận được thứ gì đó hữu ích thay vì màn hình trắng.

### 3.1 Cơ chế đã có trong hệ thống

| Cơ chế | Vị trí | Bảo vệ chống lại |
|--------|--------|-------------------|
| **Circuit Breaker** | `src/llm/circuit_breaker.py` | LLM API lỗi liên tục — mở circuit sau 5 lần fail, ngừng gọi 60s, tự thử lại |
| **Retry + exponential backoff** | `src/llm/retry.py` | Lỗi tạm thời (timeout, connection) — retry 3 lần, delay 1s→2s→4s |
| **Rule-based fallback** | `src/c4_llm_draft/fallback.py` | LLM hoàn toàn không khả dụng — sinh summary từ raw chunks |
| **Two-tier cache** | `src/cache/redis_cache.py` | Redis chết — tự fallback xuống file cache (L2) |
| **DB pool_pre_ping** | `src/db/engine.py` | Connection chết trong pool — ping trước khi dùng, tự reconnect |
| **DB init retry** | `api/main.py` | DB chưa sẵn sàng lúc startup — retry 5 lần với backoff |
| **Timeout middleware** | `api/middleware/timeout.py` | Request treo — cắt sau 120s |
| **Centralized error handlers** | `api/errors.py` | Mọi exception → JSON response sạch, không leak stack trace |

### 3.2 Các tầng degradation (theo thứ tự ưu tiên)

```
1. Summary có trong cache (Redis)        → trả ngay
2. Redis chết → đọc file cache (L2)      → vẫn trả được
3. Cache miss → gọi LLM (retry + CB)     → tạo mới
4. LLM lỗi tạm thời → retry 3 lần        → thường phục hồi
5. LLM chết hẳn → circuit mở             → rule-based fallback
6. Mọi thứ fail → error handler          → 503 + thông báo rõ ràng
```

Mỗi tầng là một lớp lưới an toàn. Phải fail toàn bộ 6 tầng thì bác sĩ mới gặp lỗi cứng.

### 3.3 Health check & self-healing

`api/routers/health.py` cung cấp:

- **`/health`** (liveness): process còn sống không → cho Kubernetes biết có cần restart pod.
- **`/health/ready`** (readiness): kiểm tra LLM circuit, disk space, DB, Redis, data dir → chỉ nhận traffic khi thực sự sẵn sàng.
- **`/health/circuit-breakers`**: admin xem trạng thái circuit.
- **`/health/circuit-breakers/reset`**: admin reset thủ công sau khi khắc phục sự cố.

Kết hợp với Kubernetes liveness/readiness probe → pod tự restart khi treo, tự rút khỏi load balancer khi chưa sẵn sàng.

### 3.4 Cần bổ sung

- **Idempotency key** cho pipeline write: tránh tạo summary trùng khi worker retry.
- **Dead-letter queue**: job pipeline fail hết retry → đẩy vào DLQ để điều tra, không mất silently.
- **Circuit breaker cho DB và Redis**: hiện chỉ LLM có circuit breaker; nên bọc cả DB/Redis để fail nhanh khi chúng quá tải.
- **Graceful shutdown**: drain request đang xử lý trước khi tắt pod (hiện `lifespan` đã có `close_db`, nên mở rộng).

---

## 4. High Availability

Mục tiêu: không có **single point of failure**, hệ thống chịu được mất một node/zone mà vẫn phục vụ.

### 4.1 Nguyên tắc kiến trúc

| Thành phần | Chiến lược HA |
|------------|----------------|
| **API** | Stateless + nhiều replica + load balancer. Mất 1 instance → LB định tuyến sang instance khác. |
| **PostgreSQL** | Primary + standby replica (streaming replication). Tự failover bằng Patroni/cloud-managed (RDS Multi-AZ). |
| **Redis** | Redis Sentinel hoặc Cluster — tự bầu master mới khi master chết. Cache là non-critical (file L2 backup). |
| **Message Queue** | RabbitMQ cluster / mirrored queues — job không mất khi 1 node chết. |
| **Background Workers** | Nhiều worker, stateless — mất 1 worker, job được pick up bởi worker khác. |

### 4.2 Multi-AZ / Multi-Region

```
        Region (Primary)                    Region (DR — optional)
   ┌─────────────────────────┐         ┌─────────────────────────┐
   │  AZ-1        AZ-2        │         │  Standby replica         │
   │  API-1       API-2       │         │  (async replication)     │
   │  Worker-1    Worker-2    │ ──────► │                          │
   │  PG-Primary  PG-Standby  │         │  Cold/warm standby       │
   │  Redis-M     Redis-S     │         │                          │
   └─────────────────────────┘         └─────────────────────────┘
```

- **Multi-AZ** (bắt buộc cho HA): phân bố instances qua ≥2 availability zones. Mất 1 AZ vẫn chạy.
- **Multi-Region** (cho disaster recovery): replica ở region khác, dùng khi cả region primary sập. Tốn kém hơn, cân nhắc theo SLA.

### 4.3 Mục tiêu SLA và đo lường

| Chỉ số | Ý nghĩa | Mục tiêu gợi ý |
|--------|---------|------------------|
| **Uptime** | % thời gian phục vụ được | 99.9% (≈8.7h downtime/năm) |
| **RTO** (Recovery Time Objective) | Bao lâu để phục hồi sau sự cố | < 5 phút (auto-failover) |
| **RPO** (Recovery Point Objective) | Mất tối đa bao nhiêu data | < 1 phút (synchronous replication cho PG primary) |

### 4.4 Lưu ý đặc thù

- **Cache là HA "miễn phí"**: vì đã có two-tier (Redis + file) và data hash, mất Redis chỉ làm chậm (cache miss → gọi LLM lại), không mất correctness.
- **Stateless là chìa khóa**: API/Worker không giữ state → scale và failover trivial. Mọi state nằm ở PG (durable) + Redis (ephemeral).
- **DB là SPOF nguy hiểm nhất**: cần đầu tư replica + auto-failover trước tiên, vì đây là thành phần khó scale/recover nhất.

---

## 5. Security

Đây là phần **quan trọng nhất với dữ liệu y tế** (PHI — Protected Health Information). Quy định liên quan: HIPAA (US), GDPR (EU), Nghị định 13/2023 về bảo vệ dữ liệu cá nhân (VN).

### 5.1 Cơ chế đã có

| Cơ chế | Vị trí | Tác dụng |
|--------|--------|-----------|
| **Rate limiting** | `api/middleware/rate_limiter.py` | 30 req/phút/IP trên endpoint summarize — chống abuse/DoS cơ bản |
| **CORS allowlist** | `api/main.py` | Chỉ cho phép origin `localhost:3000` — chặn cross-origin trái phép |
| **Generic error messages** | `api/errors.py` | Không leak stack trace / chi tiết nội bộ ra client |
| **Request ID tracing** | `api/main.py` | Mỗi request có `X-Request-ID` — truy vết khi điều tra |
| **Timeout** | `api/middleware/timeout.py` | Chặn slow-loris / request treo tài nguyên |

### 5.2 Khoảng trống cần bổ sung (ưu tiên cao)

> ⚠️ Hệ thống hiện **chưa có authentication/authorization**. Với dữ liệu y tế, đây là yêu cầu bắt buộc trước khi production.

| Hạng mục | Vấn đề hiện tại | Cần làm |
|----------|------------------|----------|
| **Authentication** | Endpoint mở, ai cũng gọi được | JWT / OAuth2 — xác thực bác sĩ trước mọi request |
| **Authorization** | Không kiểm soát ai xem hồ sơ nào | RBAC + kiểm tra: bác sĩ chỉ xem được bệnh nhân mình phụ trách |
| **Audit logging** | Không ghi lại ai truy cập hồ sơ nào | Log bất biến: user X xem summary patient Y lúc Z — bắt buộc với HIPAA |
| **Encryption at rest** | PHI lưu plaintext trong DB | Mã hóa cột nhạy cảm / TDE (Transparent Data Encryption) |
| **Encryption in transit** | (tùy deploy) | Bắt buộc TLS 1.2+ cho mọi kết nối |
| **PII/PHI masking trong logs** | Log có thể chứa tên/dữ liệu BN | Scrub PHI trước khi ghi log |
| **Rate limiter phân tán** | In-memory, không share giữa các instance | Chuyển sang Redis-backed để hiệu lực toàn cluster |
| **Secrets management** | API key qua env var | Vault / AWS Secrets Manager, rotate định kỳ |

### 5.3 Rủi ro đặc thù khi dùng LLM

- **PHI rò rỉ qua LLM provider**: gửi hồ sơ bệnh nhân lên API bên thứ ba (OpenAI/Anthropic) → cần BAA (Business Associate Agreement), hoặc cân nhắc **self-host model** cho dữ liệu nhạy cảm nhất.
- **Prompt injection**: dữ liệu EHR chứa text tự do (clinical_notes) có thể chứa nội dung độc hại điều khiển LLM. Cần sanitize input và tách rõ system prompt vs data.
- **Data residency**: một số quy định yêu cầu dữ liệu y tế không rời khỏi biên giới quốc gia → ảnh hưởng việc chọn LLM provider và region.

### 5.4 Defense in depth

```
TLS (in transit)
  └─ WAF / Rate limit (chống abuse)
       └─ Authentication (JWT — bạn là ai?)
            └─ Authorization (RBAC — bạn được xem gì?)
                 └─ Audit log (ghi lại mọi truy cập)
                      └─ Encryption at rest (PHI mã hóa trong DB)
                           └─ PII masking (log sạch)
```

Mỗi lớp độc lập — kẻ tấn công phải vượt qua tất cả mới chạm được PHI.

---

## 6. Cost Optimization

Chi phí lớn nhất của hệ thống là **LLM API calls**, không phải compute/storage. Mọi tối ưu chi phí xoay quanh việc **giảm số token gửi/nhận và số lần gọi LLM**.

### 6.1 Phân tích cơ cấu chi phí

| Hạng mục | Tỷ trọng (ước tính) | Ghi chú |
|----------|----------------------|---------|
| **LLM API calls** | ~85-95% | Chi phối toàn bộ. 9 sections × token mỗi patient |
| Database | ~3-5% | Rẻ, scale tuyến tính |
| Redis cache | ~1-2% | Rẻ, nhưng tiết kiệm LLM rất nhiều |
| Compute (API/Worker) | ~3-5% | Stateless, auto-scale theo tải |

### 6.2 Đòn bẩy lớn nhất: Caching + Pre-compute

| Tình huống | LLM calls/triệu BN | Chi phí tương đối |
|-------------|---------------------|--------------------|
| Không cache | ~1 triệu calls mỗi lần xem | Không khả thi |
| Có cache (data hash) | ~1 call/BN cho tới khi data đổi | Giảm ~90%+ |

Cache key đã bao gồm `model` + `prompt_version` (`src/cache/redis_cache.py`) → đổi model/prompt tự động tạo key mới, không phục vụ data cũ sai. Đây là nền tảng tiết kiệm chi phí lớn nhất, **đã có sẵn**.

### 6.3 Tiered model — đúng việc, đúng model

Không dùng model đắt nhất cho mọi section:

| Section | Độ phức tạp | Model | Chi phí tương đối |
|---------|--------------|-------|--------------------|
| `allergies`, `current_medications` | Liệt kê | Haiku | 1x |
| `abnormal_labs`, `diagnoses` | Filter + format | Sonnet | ~5x |
| `overview`, `treatment_timeline` | Tổng hợp, suy luận | Opus | ~15x |

Phần lớn section chỉ cần liệt kê/format → dùng model rẻ. Chỉ section cần suy luận mới dùng Opus. Có thể giảm chi phí LLM 50-70% so với dùng Opus cho tất cả.

### 6.4 Giảm token

- **Prompt caching** (Anthropic/OpenAI hỗ trợ): system prompt + guidelines giống nhau giữa các request → cache phần prefix, chỉ trả tiền phần data thay đổi. Tiết kiệm đáng kể vì system prompt thường dài.
- **Giới hạn chunks vào context**: `format_chunks_as_context(max_chunks=60)` đã giới hạn — retrieval tốt giúp đưa ít chunk hơn nhưng đúng hơn, giảm input token.
- **Giới hạn `max_tokens` output**: đặt trần hợp lý cho từng section, tránh sinh thừa.
- **Batch sections**: gộp vài section đơn giản vào 1 prompt thay vì 9 calls riêng → giảm overhead system prompt lặp lại.

### 6.5 Self-hosting (khi quy mô lớn)

| | LLM API (cloud) | Self-host (Llama/Qwen) |
|--|------------------|-------------------------|
| Chi phí | Trả theo token | Trả theo GPU (cố định) |
| Hòa vốn | Khi volume thấp | Khi volume cao + ổn định |
| Phù hợp | Khởi đầu, volume biến động | Sections không critical, volume lớn, dữ liệu nhạy cảm |

Hệ thống đã hỗ trợ nhiều provider (`LOCAL_PROVIDERS = {"lmstudio", "ollama"}`) → có thể route section không critical sang model self-host, giữ cloud cho section cần chất lượng cao.

### 6.6 Quan sát & kiểm soát chi phí

- **Token accounting**: pipeline đã trả `total_tokens` mỗi request → log lại để theo dõi chi phí theo patient/section/model.
- **Budget alert**: cảnh báo khi chi phí LLM/ngày vượt ngưỡng.
- **Cache hit ratio**: theo dõi `SummaryCache.stats` (hits/misses) — hit ratio thấp = đang đốt tiền LLM không cần thiết.

### 6.7 Tổng hợp đòn bẩy chi phí

| Đòn bẩy | Mức tiết kiệm | Trạng thái |
|---------|----------------|-------------|
| Caching (data hash) | ~90%+ LLM calls | ✅ Đã có |
| Prompt caching | ~30-50% input token | Cần bật |
| Tiered model | ~50-70% LLM cost | Cần config |
| Pre-compute (tránh duplicate) | Gộp với caching | Cần queue |
| Self-host non-critical | Theo volume | Hạ tầng đã hỗ trợ |

---

## 7. Observability & Monitoring

Câu hỏi cốt lõi: **"Làm sao biết hệ thống đang chạy đúng?"** Không quan sát được nghĩa là không vận hành được. Với hệ thống y tế, một summary sai mà không ai biết = nguy hiểm cho bệnh nhân.

### 7.1 Ba trụ cột (three pillars)

| Trụ cột | Câu hỏi trả lời | Trong hệ thống |
|---------|------------------|------------------|
| **Metrics** | Hệ thống khỏe không? Xu hướng thế nào? | Prometheus (`/metrics`), `SummaryCache.stats`, token count |
| **Logs** | Chuyện gì đã xảy ra với request này? | Structured logging (`src/logging_config.py`) + Request ID |
| **Tracing** | Request đi qua những đâu, chậm ở khâu nào? | `X-Request-ID` xuyên suốt, `timed_query` cho DB |

### 7.2 Phân loại metrics cần theo dõi

**System metrics (hạ tầng):**
- Latency: p50/p95/p99 mỗi endpoint — p99 quan trọng hơn trung bình (trải nghiệm tệ nhất).
- Throughput: requests/giây.
- Error rate: % 5xx, % 4xx.
- Saturation: CPU/memory/connection pool usage.

**Business/domain metrics (đặc thù — quan trọng nhất):**
- **Citation coverage** (`citation_coverage`): % claim có nguồn hợp lệ.
- **Critical citation coverage**: chỉ số an toàn — claim quan trọng (thuốc, dị ứng, chẩn đoán) có được chứng thực không.
- **Hallucination rate** (`hallucination_rate`): % claim bị đánh dấu mâu thuẫn.
- **Cache hit ratio**: hiệu quả chi phí.
- **LLM token/cost per request**: kiểm soát ngân sách.
- **Fallback rate**: bao nhiêu % request phải dùng rule-based fallback (LLM đang yếu).

> Điểm mấu chốt cho phỏng vấn: với AI system, **business metrics quan trọng hơn system metrics**. Hệ thống "khỏe" (p99 thấp, error rate 0%) nhưng hallucination rate cao thì vẫn là thất bại.

### 7.3 The Four Golden Signals (Google SRE)

Latency · Traffic · Errors · Saturation — bộ tối thiểu để biết hệ thống có vấn đề. Bổ sung cho hệ thống này: **một golden signal domain-specific là `critical_citation_coverage`** — tụt dưới ngưỡng phải báo động ngay.

### 7.4 Alerting — báo động dựa trên triệu chứng, không phải nguyên nhân

```
❌ Alert "CPU > 80%"            → có thể vô hại, gây alert fatigue
✅ Alert "p99 latency > 30s"    → bác sĩ đang chờ quá lâu (triệu chứng thật)
✅ Alert "critical coverage < 90%" → chất lượng y khoa giảm (nguy hiểm thật)
✅ Alert "fallback rate > 20%"  → LLM đang có vấn đề hệ thống
```

Nguyên tắc: alert vào thứ **người dùng cảm nhận được**, không phải mọi dao động kỹ thuật. Mỗi alert phải actionable — nếu không làm gì được thì đừng alert.

### 7.5 Cần bổ sung

- **Dashboard** (Grafana): trực quan hóa golden signals + domain metrics theo thời gian.
- **Distributed tracing** (OpenTelemetry): theo dõi 1 request qua API → DB → LLM → cache, tìm bottleneck chính xác.
- **Log aggregation** (ELK/Loki): gom log từ nhiều instance về một nơi, query theo Request ID.
- **SLO dashboard**: theo dõi error budget (xem mục 11).

---

## 8. Quality & Evaluation (đặc thù AI/LLM)

Đây là phần **khác biệt nhất so với hệ thống phần mềm thông thường**. Với LLM, output không deterministic và có thể "bịa" (hallucinate) → không thể chỉ test pass/fail, phải **đo lường chất lượng thống kê**.

### 8.1 Vấn đề cốt lõi: LLM có thể bịa thông tin y khoa

Một câu summary nghe rất hợp lý nhưng sai sự thật = nguy hiểm chết người. Giải pháp của hệ thống: **không tin LLM, bắt LLM chứng minh**.

```
LLM tạo claim → C5 trích xuất claim + tìm bằng chứng (evidence matching)
             → C6 verifier: claim này có nguồn không?
                  ├─ Có nguồn rõ ràng    → KEEP
                  ├─ Nguồn yếu/một phần   → FLAG (cảnh báo bác sĩ)
                  └─ Không nguồn/mâu thuẫn → REMOVE (nếu critical)
```

### 8.2 Decision matrix — an toàn theo mức độ quan trọng

C6 (`src/c6_verifier/verifier.py`) quyết định dựa trên **(trạng thái claim × có critical không)**:

| Trạng thái | Critical (thuốc, dị ứng, chẩn đoán) | Non-critical |
|------------|--------------------------------------|---------------|
| SUPPORTED | KEEP | KEEP |
| PARTIALLY_SUPPORTED | FLAG | FLAG |
| UNSUPPORTED | **REMOVE** | FLAG |
| CONTRADICTED | **REMOVE** | REMOVE |
| NO_CITATION | **REMOVE** | FLAG |

Tư duy thiết kế: **claim quan trọng bị xử lý nghiêm khắc hơn**. Thông tin thuốc không có nguồn → xóa thẳng. Thông tin phụ không có nguồn → chỉ gắn cờ. Đây là **asymmetric risk** — sai một thông tin critical tốn kém hơn nhiều so với bỏ sót một thông tin phụ.

### 8.3 Cross-section consistency — phát hiện LLM tự mâu thuẫn

C6 còn kiểm tra LLM có nói ngược nhau giữa các section không:

- **Disease classifier**: section A nói "ĐTĐ type 1", section B nói "type 2" → đánh dấu mâu thuẫn.
- **Drug dose**: cùng một thuốc nhưng liều khác nhau giữa các section.
- **Lab value**: cùng xét nghiệm nhưng giá trị khác nhau (trừ `treatment_timeline` vì đó là theo dõi xu hướng).

Logic: lấy giá trị xuất hiện nhiều nhất làm "chuẩn", cái nào lệch thì flag. Đây là **majority voting** để tự sửa lỗi nội bộ.

### 8.4 Các chỉ số đánh giá

| Metric | Đo cái gì | Kết quả hiện tại |
|--------|-----------|-------------------|
| **Citation Precision** | Claim có nguồn / tổng claim | 85.5% |
| **Critical Precision** | Claim critical có nguồn / tổng critical | 87.6% |
| **Hallucination Rate** | % claim mâu thuẫn | (đo qua `contradiction_count`) |
| **Missing Section Rate** | % section trống sau verify | (đo qua `missing_section_rate`) |

### 8.5 Phương pháp đánh giá

- **Multi-run benchmark** (`scripts/run_multirun_benchmark.py`): chạy nhiều lần để đo **độ ổn định** — LLM không deterministic nên 1 lần chạy tốt không có nghĩa hệ thống tốt. Cần đo variance.
- **Recite-and-eval** (`scripts/recite_and_eval.py`): kiểm tra summary có trích dẫn đúng nguồn không.
- **Human evaluation** (`api/routers/human_eval.py`): bác sĩ chấm điểm — vì một số khía cạnh chất lượng (đọc tự nhiên, đúng trọng tâm lâm sàng) không đo tự động được.

### 8.6 Tư duy đánh giá cho phỏng vấn

1. **Offline eval trước khi deploy**: benchmark trên tập test cố định, so sánh các model/prompt.
2. **Online monitoring sau deploy**: theo dõi metrics thực tế (mục 7.2), phát hiện degradation.
3. **Human-in-the-loop**: hệ thống **hỗ trợ** chứ không thay thế bác sĩ. Mọi FLAG/citation đều click được để bác sĩ verify. Đây là quyết định thiết kế quan trọng nhất về mặt an toàn.

---

## 9. Key Design Trade-offs

Phỏng vấn system design xoay quanh câu hỏi **"tại sao chọn X mà không phải Y?"** Dưới đây là các quyết định lớn của hệ thống và lý do.

### 9.1 Rule-based retrieval vs Vector/Semantic search

| | Rule-based (đã chọn) | Vector search |
|--|----------------------|----------------|
| Phù hợp khi | Data có cấu trúc, biết chính xác cần loại nào | Free-text query, "tìm thứ tương tự" |
| Ưu | Deterministic, dễ debug, giải thích được cho bác sĩ | Linh hoạt với câu hỏi mở |
| Nhược | Cứng nhắc với query không lường trước | Khó debug, có thể trả về nhiễu |

**Quyết định**: dữ liệu EHR đã structured, mỗi section biết chính xác cần `source_type` nào → rule-based đủ và **giải thích được** (quan trọng với y tế). Vector chỉ là enhancement optional khi có quá nhiều chunk cùng loại cần re-rank.

> Bài học: **đừng dùng giải pháp phức tạp (RAG/vector DB) cho bài toán mà giải pháp đơn giản (SQL filter) giải quyết được.**

### 9.2 DB-level filtering vs Python in-memory filtering

**Quyết định**: load chunks của 1 patient (~50-100) lên memory, filter bằng Python.

Lý do: bottleneck là LLM (giây), không phải filter vài chục object (mili giây). Giữ logic phức tạp (dedup, temporal) ở Python dễ đọc/test hơn SQL. Premature optimization ở tầng DB không đáng — tối ưu chỗ không phải bottleneck là lãng phí.

### 9.3 Synchronous vs Asynchronous pipeline

| | Sync (on-demand) | Async (pre-compute) |
|--|-------------------|----------------------|
| Trải nghiệm | Bác sĩ chờ 5-15s | Summary có sẵn ngay |
| Độ phức tạp | Đơn giản | Cần queue + worker |
| Phù hợp giai đoạn | POC/demo | Production quy mô lớn |

**Quyết định**: hiện tại sync (đủ cho demo), thiết kế sẵn sàng chuyển async khi scale. Không build queue ngay từ đầu — **YAGNI** (You Aren't Gonna Need It) cho tới khi có bằng chứng cần.

### 9.4 Conservative verifier (REMOVE → FLAG)

C6 có chế độ `conservative=True`: thay vì xóa claim đáng ngờ, chỉ gắn cờ.

**Trade-off**: precision vs recall. Xóa nhiều → an toàn hơn nhưng có thể bỏ sót thông tin đúng (giảm recall). Gắn cờ → giữ thông tin nhưng đẩy trách nhiệm verify cho bác sĩ.

**Quyết định**: trong demo dùng conservative để không "nuốt" thông tin hợp lệ; production có thể siết chặt hơn cho claim critical. Đây là **tham số chính sách**, điều chỉnh được theo ngữ cảnh.

### 9.5 Build vs Buy (LLM)

**Quyết định**: dùng cloud LLM API (buy) làm mặc định, hỗ trợ self-host (build) cho non-critical/dữ liệu nhạy cảm.

Lý do: cloud API cho chất lượng cao ngay, không cần đầu tư hạ tầng GPU. Self-host chỉ đáng khi volume lớn ổn định hoặc yêu cầu data residency. Kiến trúc đa provider giữ **tính linh hoạt** để chuyển đổi khi điều kiện thay đổi.

### 9.6 Nguyên tắc xuyên suốt

> **Deterministic trước, probabilistic sau. Đơn giản trước, phức tạp khi có bằng chứng cần. Giải thích được quan trọng hơn tinh vi — vì đây là y tế.**

---

## 10. Capacity Planning (Back-of-envelope)

Kỹ năng phỏng vấn kinh điển: **ước lượng quy mô bằng phép tính nhẩm** để biết hệ thống cần gì.

### 10.1 Giả định đầu vào

```
Số bệnh nhân:           1,000,000
Chunks/bệnh nhân:       ~100
Summary/bệnh nhân:      1 (cache lại)
Tỷ lệ active/tháng:     10% → 100,000 BN có hoạt động/tháng
Bác sĩ xem summary:     ~5 lần/BN active/tháng
```

### 10.2 Ước lượng Storage

```
Chunks:   1M BN × 100 chunks × ~1KB/chunk  = ~100 GB
Summaries: 1M × ~10KB                        = ~10 GB
Tổng DB:                                     ~110 GB  → PostgreSQL xử lý thoải mái
```

### 10.3 Ước lượng QPS (Queries Per Second)

```
Lượt xem/tháng = 100,000 BN active × 5 lần = 500,000 views/tháng
QPS trung bình = 500,000 / (30 × 86,400)   ≈ 0.2 QPS
QPS đỉnh (giờ hành chính, ×10)             ≈ 2 QPS
```

→ Tải rất nhẹ về mặt request. **Vài instance API là quá đủ.**

### 10.4 Ước lượng LLM calls (chi phí thật)

```
Không cache: 500,000 views × 9 sections = 4.5M LLM calls/tháng  → cực đắt
Có cache:    Chỉ gọi khi data thay đổi
             ~100,000 BN active × 9 sections = 900K calls/tháng → giảm 80%
             (và chỉ 1 lần cho tới khi data đổi tiếp)
```

> Kết luận quan trọng: **bottleneck không phải QPS (0.2) mà là LLM cost.** Đây là lý do caching/pre-compute là ưu tiên số 1, không phải scale API. Ước lượng giúp **nhìn ra đâu mới thực sự là ràng buộc**.

### 10.5 Bài học tư duy

Back-of-envelope không cần chính xác — cần đúng **bậc độ lớn** (order of magnitude) để trả lời: "Có cần phân tán không? Bottleneck ở đâu? Đầu tư vào đâu trước?" Ở đây câu trả lời là: DB nhỏ, QPS nhỏ, **tiền nằm ở LLM** → tối ưu đúng chỗ đó.

---

## 11. Reliability: SLO, SLA & Failure Scenarios

### 11.1 SLI / SLO / SLA

| Khái niệm | Định nghĩa | Ví dụ |
|-----------|------------|--------|
| **SLI** (Indicator) | Số đo thực tế | p99 latency, error rate, critical coverage |
| **SLO** (Objective) | Mục tiêu nội bộ | 99.9% request < 30s; critical coverage > 95% |
| **SLA** (Agreement) | Cam kết với khách hàng (có phạt) | 99.5% uptime/tháng |

**Error budget**: nếu SLO uptime là 99.9% → được phép "lỗi" 0.1% (~43 phút/tháng). Dùng budget này để cân bằng giữa **ship tính năng mới** (rủi ro) và **giữ ổn định**. Hết budget → đóng băng feature, tập trung sửa độ tin cậy.

### 11.2 Failure scenarios — "Chuyện gì xảy ra nếu X chết?"

Interviewer rất hay hỏi dạng này. Hệ thống đã thiết kế cho từng kịch bản:

| Thành phần chết | Hệ quả | Cơ chế bảo vệ |
|------------------|--------|----------------|
| **LLM API tạm lỗi** | 1 request fail | Retry 3× với backoff → thường phục hồi |
| **LLM API chết hẳn** | Không tạo được draft | Circuit breaker mở → rule-based fallback |
| **Redis chết** | Mất L1 cache | Tự fallback xuống file cache (L2) |
| **DB tạm mất kết nối** | Query fail | `pool_pre_ping` reconnect; init retry lúc startup |
| **1 API instance chết** | Request đang xử lý mất | Load balancer định tuyến sang instance khác; stateless nên không mất state |
| **1 Worker chết** | Job đang chạy dở | Job quay lại queue, worker khác pick up |
| **Disk gần đầy** | Nguy cơ ghi lỗi | Readiness probe phát hiện, rút khỏi LB |
| **Cả AZ chết** | Mất nửa cụm | Multi-AZ: AZ còn lại tiếp tục phục vụ |

### 11.3 Nguyên tắc thiết kế resilience

- **Fail fast, recover gracefully**: phát hiện lỗi nhanh (circuit breaker, health check) thay vì treo.
- **Bulkhead**: cô lập lỗi — LLM chết không kéo sập DB; section này fail không kéo section khác (mỗi section gọi LLM độc lập).
- **No silent failure**: mọi fallback đều được log + đếm (fallback rate metric) để biết hệ thống đang "âm thầm xuống cấp".

---

## 12. Data Consistency & Integrity

### 12.1 Vấn đề: Chunks là derived data

Chunks được sinh ra từ raw EHR. Khi raw data đổi mà chunks không cập nhật → bác sĩ thấy summary cũ/sai. Đây là bài toán **consistency giữa source và derived data**.

### 12.2 Chiến lược đảm bảo nhất quán

```
Raw data thay đổi (encounter mới, sửa thuốc)
    → data_hash thay đổi
    → cache key mới → cache miss
    → pipeline chạy lại: re-chunk → re-retrieve → re-summarize
    → summary mới khớp với data mới
```

**Data hash là cơ chế consistency cốt lõi** — không cần invalidation thủ công, hash tự phản ánh trạng thái data. Nếu data y hệt → hash y hệt → dùng lại kết quả; data đổi 1 ký tự → hash khác → tính lại.

### 12.3 Source of truth rõ ràng

- **Raw EHR (DB)** = single source of truth.
- **Chunks** = derived, có thể tái tạo bất cứ lúc nào từ raw → không cần backup riêng, không sợ "lệch".
- **Summary** = derived từ chunks + model + prompt → cache key gồm cả `model` + `prompt_version` để không phục vụ kết quả sinh bởi prompt/model cũ.

> Nguyên tắc: **chỉ có một nguồn sự thật; mọi thứ khác là cache có thể tái tạo.** Điều này khiến hệ thống dễ suy luận — khi nghi ngờ, xóa cache và tính lại.

### 12.4 Idempotency

Khi worker retry (do timeout/lỗi tạm), không được tạo summary trùng. Giải pháp: dùng `(patient_id, data_hash, model, prompt_version)` làm khóa idempotent — chạy lại với cùng input → ghi đè cùng một cache key, không tạo bản ghi mới.

### 12.5 Transaction boundary

Khi re-chunk: xóa chunks cũ + ghi chunks mới của patient nên nằm trong **cùng một transaction**, tránh trạng thái nửa vời (mất chunks cũ nhưng chưa có chunks mới). Đảm bảo bác sĩ không bao giờ thấy patient ở trạng thái "đang cập nhật dở".
