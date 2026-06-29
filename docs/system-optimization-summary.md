# System Optimization — Tóm tắt nhanh (Interview Cheat Sheet)

> Bản rút gọn của [system-optimization.md](system-optimization.md) — mỗi phần chỉ liệt kê cách tối ưu.

## 1. Scaling
- Horizontal scale API (stateless + load balancer + auto-scale)
- PostgreSQL: index `(patient_id)`, read replicas, PgBouncer, partition khi >50M rows
- Redis cache summary result
- Message queue + background workers

## 2. Latency
- Caching (data hash) — repeat request ~1ms
- Pre-compute pipeline khi data đổi
- Streaming response (SSE) — giảm perceived latency
- Tiered model (Haiku/Sonnet/Opus theo độ phức tạp)
- Parallel section generation (đã có)

## 3. Fault Tolerance
- Circuit breaker, retry + backoff, rule-based fallback (đã có)
- Two-tier cache (Redis → file)
- DB pool_pre_ping + init retry
- Idempotency key, dead-letter queue, circuit breaker cho DB/Redis

## 4. High Availability
- Stateless + multi-replica mọi tầng
- PostgreSQL primary + standby auto-failover
- Redis Sentinel/Cluster
- Multi-AZ (bắt buộc), Multi-Region (DR)
- Mục tiêu: 99.9% uptime, RTO < 5 phút, RPO < 1 phút

## 5. Security
- Authentication (JWT/OAuth2), Authorization (RBAC)
- Audit logging mọi truy cập PHI
- Encryption at rest + in transit (TLS)
- PII masking trong logs
- Rate limiter phân tán (Redis-backed)
- Secrets management (Vault), BAA với LLM provider, sanitize chống prompt injection

## 6. Cost
- Caching (data hash) — giảm ~90% LLM calls
- Prompt caching (cache system prompt prefix)
- Tiered model
- Giảm token (giới hạn chunks, max_tokens, batch sections)
- Self-host model cho non-critical
- Token accounting + budget alert + cache hit ratio

## 7. Observability
- Metrics (Prometheus), structured logs + Request ID, distributed tracing (OpenTelemetry)
- Theo dõi golden signals + business metrics (citation/critical coverage, hallucination rate, fallback rate)
- Dashboard (Grafana), log aggregation (ELK/Loki)
- Alerting theo triệu chứng, không theo nguyên nhân

## 8. Quality & Evaluation
- C5 evidence matching + C6 verifier (KEEP/FLAG/REMOVE)
- Decision matrix theo mức critical (asymmetric risk)
- Cross-section consistency check (drug dose, lab value, disease type)
- Offline benchmark + multi-run (đo variance) + human evaluation
- Human-in-the-loop (citation click-to-verify)

## 9. Design Trade-offs
- Rule-based trước, vector sau
- Python in-memory filter (không premature DB optimization)
- Sync → async khi scale (YAGNI)
- Conservative verifier (tham số precision/recall điều chỉnh được)
- Multi-provider LLM (build vs buy linh hoạt)

## 10. Capacity Planning
- Back-of-envelope: Storage ~110GB, QPS ~0.2 (nhẹ), bottleneck = LLM cost
- Ước lượng để xác định ràng buộc thật → đầu tư đúng chỗ

## 11. Reliability (SLO/SLA)
- Định nghĩa SLI/SLO/SLA + error budget
- Failure scenario playbook (X chết → cơ chế bảo vệ)
- Bulkhead isolation, fail fast, no silent failure

## 12. Data Consistency
- Data hash đảm bảo chunks/summary khớp raw data
- Single source of truth = raw EHR; chunks/summary là cache tái tạo được
- Idempotency key cho worker retry
- Transaction boundary khi re-chunk
