"""
PoC Pipeline — Tuan 3+.
Full C1→C2→C3→LLM→C5→C6 pipeline with atomic claim verification.
Provider: OpenAI (gpt-4o-mini for dev/test, gpt-4o for demo).
Section IDs: English. Summary content: Vietnamese.

Usage:
    python -m poc.poc_pipeline --patient P001
    python -m poc.poc_pipeline --patient P001 --model gpt-4o-mini
    python -m poc.poc_pipeline --all-patients
    python -m poc.poc_pipeline --patient P001 --vector   # enable hybrid retrieval
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from openai import OpenAI
from dotenv import load_dotenv

from src.c1_emr.pipeline import load_and_process, C1ProcessingError
from src.c2_chunking.chunker import chunk_ehr
from src.c2_chunking.store_builder import build_structured_store, save_structured_store
from src.c3_retrieval.retriever import retrieve_for_section
from src.c3_retrieval.vector_store import VectorStore
from src.c6_verifier.verifier import verify_section, check_internal_consistency
from src.schemas import SourceChunk, CitedClaim, FinalSummary, SummarySection, SummaryMetrics

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR      = ROOT / "data" / "processed"
ASSEMBLED_DIR = DATA_DIR / "assembled"
STORE_DIR     = DATA_DIR / "stores"
OUTPUT_DIR    = DATA_DIR / "outputs"
VECTOR_DIR    = DATA_DIR / "vector_store"

# ---------------------------------------------------------------------------
# Section definitions — English IDs, Vietnamese display labels
# ---------------------------------------------------------------------------

SECTIONS = [
    "overview",
    "reason_for_visit",
    "medical_history",
    "current_medications",
    "allergies",
    "abnormal_labs",
    "diagnoses",
    "treatment_timeline",
    "clinical_alerts",
]

SECTION_LABELS = {
    "overview":            "Tổng quan bệnh nhân",
    "reason_for_visit":    "Lý do khám / Triệu chứng chính",
    "medical_history":     "Tiền sử bệnh",
    "current_medications": "Thuốc đang sử dụng",
    "allergies":           "Dị ứng",
    "abnormal_labs":       "Kết quả xét nghiệm bất thường",
    "diagnoses":           "Chẩn đoán",
    "treatment_timeline":  "Diễn biến điều trị",
    "clinical_alerts":     "Điểm cần lưu ý / Cảnh báo",
}

# Per-section chunk budget — sections with more encounters or more structured data get more chunks
TOP_K_PER_SECTION: dict[str, int] = {
    "overview":            8,
    "reason_for_visit":    5,
    "medical_history":     15,
    "current_medications": 15,
    "allergies":           5,
    "abnormal_labs":       20,
    "diagnoses":           10,
    "treatment_timeline":  50,   # needs all encounters for timeline
    "clinical_alerts":     20,
}

# ---------------------------------------------------------------------------
# Prompts — instructions in Vietnamese so LLM outputs Vietnamese
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Bạn là hệ thống tóm tắt hồ sơ bệnh án lâm sàng hỗ trợ bác sĩ Việt Nam.

NGUYÊN TẮC BẮT BUỘC — VI PHẠM LÀ LỖI NGHIÊM TRỌNG:
1. CHỈ dùng thông tin có trong [CONTEXT]. Tuyệt đối không suy luận, bịa đặt, hoặc suy đoán.
2. Nếu không có thông tin cho section này: PHẢI viết "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
3. KHÔNG kê đơn, KHÔNG chẩn đoán thêm, KHÔNG gợi ý điều trị, KHÔNG đề xuất xét nghiệm.
4. KHÔNG tự thêm hoặc sửa đổi: mã ICD-10, tên thuốc, liều dùng, giá trị số, đơn vị xét nghiệm.
5. KHÔNG tự tạo source_id — chỉ dùng đúng source_id xuất hiện trong [CONTEXT].
6. KHÔNG merge thông tin từ các encounters khác nhau trừ khi hướng dẫn section yêu cầu.
7. Nếu phát hiện mâu thuẫn giữa diagnosis_text và ICD-10, KHÔNG tự sửa — ghi "Cần kiểm tra ICD".
8. Giữ nguyên đơn vị gốc như mg, mmol/L, %, µmol/L, U/L, mg/g — KHÔNG đổi đơn vị.
9. Output ngắn gọn, đúng chuẩn lâm sàng, không có disclaimer AI.
10. KHÔNG dùng emoji, icon, ký tự trang trí hoặc markdown phức tạp trong content.
11. KHÔNG dùng bảng markdown trong content.
12. KHÔNG chèn source_id trực tiếp vào content. Source_id chỉ được đặt trong mảng source_ids.
13. Content chỉ dùng plain text, heading ngắn và bullet dấu "-" nếu cần.
14. Không dùng các ký hiệu gây rối UI như: ⚠️, ✅, ❓, 📅, ↑, ↓.
15. Nếu cần diễn đạt xu hướng, dùng chữ: "tăng", "giảm", "cải thiện", "xấu đi", "ổn định".
16. NHẤT QUÁN giữa các section: loại bệnh (ví dụ đái tháo đường type 1 hay type 2), giá trị số, mã ICD phải GIỐNG NHAU ở mọi section. Lấy đúng loại bệnh từ chẩn đoán gốc trong [CONTEXT], KHÔNG suy diễn, KHÔNG để mâu thuẫn type giữa các section.
17. Nếu dữ liệu thiếu, ghi "chưa rõ" hoặc "chưa xác định". TUYỆT ĐỐI KHÔNG in "None", "null", "unknown", "nan" trong content.

ĐỊNH DẠNG OUTPUT BẮT BUỘC:
Trả về một JSON object hợp lệ với key là section_id được yêu cầu.

Mỗi section là một object:
{
  "content": "...",
  "source_ids": ["id1", "id2"]
}

Quy tắc về source_ids:
- source_ids PHẢI là các source_id thực tế xuất hiện trong [CONTEXT].
- Không được tự tạo source_id.
- Không được đưa source_id vào content.
- Không lặp lại source_id nếu không cần thiết.
- Nếu content có nhiều ý, source_ids là danh sách các nguồn hỗ trợ cho toàn section.
- Nếu không có source phù hợp, source_ids là mảng rỗng [].
"""

SECTION_GUIDELINES = {
    "overview": (
        "Viết Tổng quan 2-3 câu ngắn. "
        "KHÔNG đề cập chi tiết thuốc hay số liệu xét nghiệm vì đã có section riêng. "
        "Bao gồm theo thứ tự: "
        "(1) tuổi, giới tính; "
        "(2) bệnh nền chính và năm phát hiện nếu context có; "
        "(3) thể trạng như BMI hoặc cân nặng nếu context có; "
        "(4) biến chứng mạn tính đang theo dõi nếu context đề cập; "
        "Chỉ dùng thông tin có trong context. Không suy đoán năm phát hiện."
    ),

    "reason_for_visit": (
        "Nêu lý do khám và triệu chứng chính của lần khám gần nhất trong [CONTEXT]. "
        "Không tổng hợp từ nhiều lần khám. Chỉ lấy lần khám mới nhất. "
        "Viết ngắn gọn trong 1-3 câu hoặc bullet ngắn nếu có nhiều triệu chứng."
    ),

    "medical_history": (
        "Trình bày dạng bullet, mỗi bullet là một ý lâm sàng riêng biệt để dễ truy vết nguồn. "
        "Chia thành các nhóm rõ ràng nếu có thông tin trong context:\n"
        "Tiền sử bản thân:\n"
        "- Từng bệnh nền và năm phát hiện nếu có.\n"
        "- Phẫu thuật hoặc thủ thuật nếu có.\n\n"
        "Tiền sử gia đình:\n"
        "- Bệnh tim mạch, đái tháo đường, ung thư hoặc bệnh liên quan nếu có.\n\n"
        "Thói quen nguy cơ:\n"
        "- Hút thuốc, rượu bia, vận động, ăn uống nếu có.\n\n"
        "Ghi chú lâm sàng khác:\n"
        "- Các thông tin liên quan khác từ context nếu có.\n\n"
        "Bỏ qua nhóm nào nếu context không có thông tin. "
        "KHÔNG lặp lại phần dị ứng vì đã có section riêng. "
        "KHÔNG bịa thêm thông tin không có trong context."
    ),

    "current_medications": (
        "Liệt kê thuốc từ đơn thuốc mới nhất trong [CONTEXT], dựa trên prescription_date hoặc encounter gần nhất. "
        "Không merge thuốc từ nhiều lần khám. Chỉ dùng đơn thuốc ngày gần nhất. "
        "Mỗi thuốc viết thành MỘT câu hoàn chỉnh trên một dòng, gồm tên, hàm lượng, liều, "
        "tần suất và thời điểm dùng. KHÔNG tách thời điểm dùng (ví dụ 'Uống buổi sáng') "
        "thành câu riêng — phải gộp vào cùng câu với tên thuốc.\n"
        "Format mỗi dòng:\n"
        "- Tên thuốc hàm lượng — liều, tần suất, hướng dẫn dùng nếu có.\n"
        "Nếu thiếu liều, ghi '(thiếu thông tin liều)'. "
        "Giữ nguyên tên thuốc, hàm lượng, liều dùng, tần suất và đơn vị từ context. "
        "Không diễn giải lại thuốc theo ý riêng."
    ),

    "allergies": (
        "Liệt kê tất cả dị ứng đã biết từ context, mỗi dị ứng viết thành MỘT câu văn tự nhiên. "
        "TUYỆT ĐỐI KHÔNG dùng định dạng liệt kê trường kiểu 'Dị ứng: X; phản ứng: Y; mức độ: Z; trạng thái: W' — "
        "đây là lỗi thường gặp cần tránh.\n"
        "QUY TẮC QUAN TRỌNG NHẤT: chỉ nhắc tới trường nào THỰC SỰ có dữ liệu trong context. "
        "Nếu một trường (phản ứng/mức độ/trạng thái) không có dữ liệu hoặc là 'unknown', "
        "thì KHÔNG được viết tên trường đó ra kèm 'chưa rõ' — hãy bỏ hẳn trường đó khỏi câu, "
        "như thể nó không tồn tại. KHÔNG bao giờ in 'None'/'unknown'/'null'.\n"
        "Ví dụ — đầy đủ dữ liệu: 'Dị ứng Penicillin, biểu hiện nổi mề đay toàn thân, mức độ trung bình, "
        "trạng thái đang theo dõi.'\n"
        "Ví dụ — chỉ có tác nhân và trạng thái (không rõ phản ứng/mức độ): "
        "'Dị ứng Sulfonamide, trạng thái đang theo dõi. Cần xác nhận lại thông tin này với bệnh nhân.'\n"
        "Ví dụ — chỉ có tác nhân, không rõ gì khác: 'Dị ứng thuốc (chưa xác định loại). "
        "Cần xác nhận lại thông tin này với bệnh nhân.'\n"
        "Nếu không có dữ liệu dị ứng nào, ghi đúng: 'Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp.' "
        "Chỉ thêm câu 'Cần xác nhận lại thông tin này với bệnh nhân.' khi dị ứng còn thiếu thông tin "
        "hoặc cần xác nhận; nếu context đã có đầy đủ tác nhân, phản ứng, mức độ và trạng thái thì không thêm câu này."
    ),

    "abnormal_labs": (
        "Liệt kê xét nghiệm bất thường từ lần khám gần nhất như trạng thái hiện tại. "
        "Không dùng ký hiệu mũi tên hoặc ký hiệu tăng/giảm. Dùng chữ 'cao', 'thấp', 'tăng', 'giảm', 'cải thiện'. "
        "Format mỗi dòng:\n"
        "- Tên xét nghiệm: giá trị đơn vị, nhận xét cao/thấp nếu có, tham chiếu: khoảng tham chiếu, ngày: YYYY-MM-DD.\n"
        "Nếu có giá trị cùng xét nghiệm từ lần khám trước, thêm xu hướng trong cùng dòng:\n"
        "- HbA1c: 7.1%, cao, tham chiếu: <5.6%, ngày: 2024-10-10. Xu hướng: 9.2% xuống 7.1%, cải thiện.\n"
        "Nếu chỉ số đã về bình thường ở lần khám gần nhất, không liệt kê như xét nghiệm bất thường. "
        "Không tự đổi đơn vị hoặc tự thêm khoảng tham chiếu nếu context không có."
    ),

    "diagnoses": (
        "Liệt kê chẩn đoán từ lần khám gần nhất, dạng bullet có cấu trúc. "
        "Format mỗi dòng:\n"
        "- [Loại] Tên bệnh (ICD-10)\n"
        "Loại có thể là: Chính, Bệnh kèm, Biến chứng. "
        "Ví dụ:\n"
        "- Chính: Đái tháo đường type 2 (E11)\n"
        "- Bệnh kèm: Tăng huyết áp nguyên phát (I10)\n"
        "- Biến chứng: Microalbuminuria trong ĐTĐ (N18.3)\n"
        "QUAN TRỌNG: Giữ nguyên mã ICD-10 từ context. KHÔNG tự thêm hoặc sửa ICD-10. "
        "Nếu diagnosis_text và ICD-10 có vẻ không khớp, ghi nguyên bản và thêm 'Cần kiểm tra ICD'. "
        "Mỗi chẩn đoán phải được hỗ trợ bởi source_id tương ứng trong source_ids."
    ),

    "treatment_timeline": (
        "Tóm tắt diễn biến điều trị theo từng lần khám, thứ tự thời gian từ cũ đến mới. "
        "Không dùng ký hiệu mũi tên hoặc ký hiệu tăng/giảm. Dùng chữ 'tăng', 'giảm', 'cải thiện', 'xấu đi', 'ổn định'.\n\n"
        "Format mỗi dòng:\n"
        "- YYYY-MM-DD: [chỉ số chính nếu có] — [thay đổi thuốc nếu có] — [nhận xét xu hướng ngắn].\n\n"
        "Ví dụ:\n"
        "- 2024-01-10: HbA1c 9.2%, huyết áp 148/92 mmHg, LDL 3.4 mmol/L — tăng Metformin, thêm Empagliflozin, thêm Perindopril — kiểm soát chưa đạt.\n"
        "- 2024-10-10: HbA1c 7.1%, huyết áp 128/78 mmHg, LDL 2.6 mmol/L — duy trì phác đồ — cải thiện rõ.\n\n"
        "BẮT BUỘC: Viết một dòng cho MỖI encounter trong context, đặc biệt encounter MỚI NHẤT phải có mặt. "
        "Không bỏ sót encounter nào. "
        "Không đưa khuyến nghị. Chỉ dùng dữ liệu trong context."
    ),

    "clinical_alerts": (
        "Dựa trên dữ liệu lần khám gần nhất để viết phần Cảnh báo lâm sàng. "
        "Không dùng ký hiệu mũi tên hoặc ký hiệu tăng/giảm. Dùng chữ 'tăng', 'giảm', 'cải thiện', 'xấu đi', 'ổn định'.\n\n"

        "Format content bắt buộc:\n"
        "Cảnh báo hiện tại:\n"
        "- ...\n"
        "- ...\n\n"
        "Đã cải thiện:\n"
        "- ...\n"
        "- ...\n\n"
        "Cần xác minh:\n"
        "- ...\n"
        "- ...\n\n"

        "Quy tắc nội dung:\n"
        "1. Cảnh báo hiện tại chỉ gồm các vấn đề còn hiện diện ở lần khám gần nhất, ví dụ: chỉ số mới nhất còn bất thường, dị ứng đang active, biến chứng còn cần theo dõi, hoặc nguy cơ chưa giải quyết.\n"
        "2. Đã cải thiện dùng cho các chỉ số từng bất thường nhưng đã giảm hoặc đạt mục tiêu ở lần khám gần nhất. Viết theo dạng: tên chỉ số + giá trị cũ sang giá trị mới + nhận xét ngắn.\n"
        "3. Cần xác minh chỉ dùng cho thông tin thiếu rõ ràng, thiếu liều thuốc, thiếu đơn vị xét nghiệm, dị ứng chưa xác nhận, hoặc dữ liệu có mâu thuẫn.\n"
        "4. KHÔNG lặp lại giá trị cũ như cảnh báo hiện tại nếu lần khám gần nhất đã cải thiện.\n"
        "5. KHÔNG dùng các từ quá mạnh như 'nguy hiểm', 'cấp cứu', 'nặng' nếu context không ghi rõ.\n"
        "6. Nếu một nhóm không có thông tin, ghi '- Không ghi nhận.'\n"
        "7. Mỗi bullet nên ngắn, tối đa 1 câu.\n"
        "8. Tối đa 4 bullets cho mỗi nhóm để tránh rối UI.\n"
        "9. Các giá trị xét nghiệm, huyết áp, thuốc, dị ứng phải giữ nguyên theo context.\n"
    ),
}


def format_chunks_as_context(chunks: list[SourceChunk], max_chunks: int = 60) -> str:
    lines = []
    for chunk in chunks[:max_chunks]:
        date_str = f" [{chunk.date}]" if chunk.date else ""
        lines.append(f"[{chunk.source_id}]{date_str} ({chunk.source_type}): {chunk.content}")
    return "\n".join(lines)


def format_chunks_by_encounter(chunks: list[SourceChunk], max_chunks: int = 60) -> str:
    """
    Group chunks by encounter_id and format as a timeline for treatment_timeline section.
    Encounters are sorted chronologically (oldest first).
    """
    from collections import defaultdict

    by_enc: dict[str, list[SourceChunk]] = defaultdict(list)
    for c in chunks[:max_chunks]:
        key = c.encounter_id or "UNKNOWN"
        by_enc[key].append(c)

    # Sort encounters by their earliest date
    sorted_enc_ids = sorted(
        by_enc.keys(),
        key=lambda eid: min(c.date or "9999-99-99" for c in by_enc[eid]),
    )

    lines = []
    for enc_id in sorted_enc_ids:
        enc_chunks = by_enc[enc_id]
        dates = [c.date for c in enc_chunks if c.date]
        enc_date = min(dates) if dates else "?"
        lines.append(f"\n=== Encounter {enc_id} [{enc_date}] ===")
        for c in enc_chunks:
            lines.append(f"[{c.source_id}] ({c.source_type}): {c.content}")

    return "\n".join(lines)


def build_section_prompt(section_id: str, context: str) -> str:
    label = SECTION_LABELS.get(section_id, section_id)
    guideline = SECTION_GUIDELINES.get(section_id, "Tóm tắt ngắn gọn thông tin liên quan.")

    return f"""[CONTEXT]
{context}

[YÊU CẦU]
Section: {label}
Hướng dẫn: {guideline}

Trả về JSON:
{{
  "{section_id}": {{
    "content": "...",
    "source_ids": ["source_id_1", "source_id_2"]
  }}
}}
Chỉ trả JSON, không thêm giải thích.
"""


def call_llm(
    prompt: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1200,
    retries: int = 3,
) -> tuple[str, int]:
    """Call OpenAI API with retry. Returns (text, total_tokens).
    Uses response_format=json_object to reduce parse failures."""
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            text = resp.choices[0].message.content.strip()
            tokens = resp.usage.prompt_tokens + resp.usage.completion_tokens
            return text, tokens
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"    [RETRY {attempt+1}/{retries}] {e}")
            time.sleep(2 ** attempt)

    return "", 0


def _extract_json_object(text: str) -> str:
    """
    Robustly extract the first JSON object from LLM output.
    Handles code fences, leading text, and trailing text.
    """
    text = text.strip()

    # Prefer content inside a fenced code block if present.
    if "```" in text:
        lines = text.splitlines()
        fenced_lines: list[str] = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                fenced_lines.append(line)
        if fenced_lines:
            text = "\n".join(fenced_lines).strip()

    # Fall back to extracting the outermost JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", text, 0)
    return text[start : end + 1]


def _normalise_content(value: object) -> str:
    """
    LLM sometimes returns content as a list (e.g. when asked for bullet format).
    Always convert to a single string so SummarySection.content stays valid.
    """
    if isinstance(value, list):
        parts = []
        for item in value:
            s = str(item).strip()
            # Preserve bullet markers if already present, otherwise add plain "- "
            if s and not s.startswith(("- ", "* ")):
                s = "- " + s
            if s:
                parts.append(s)
        return "\n".join(parts)
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def parse_section_response(text: str, section_id: str) -> dict:
    """Parse LLM JSON response for one section. Robust to code fences and wrapper text."""
    try:
        raw = _extract_json_object(text)
        data = json.loads(raw)
        # Unwrap if wrapped under section_id key
        if section_id in data and isinstance(data[section_id], dict):
            result = data[section_id]
        elif "content" in data:
            result = data
        else:
            result = {"content": str(data), "source_ids": []}
    except (json.JSONDecodeError, ValueError):
        result = {"content": text.strip(), "source_ids": []}

    # Guarantee content is always a string (LLM may return list for bullet sections)
    result["content"] = _normalise_content(result.get("content", ""))
    if not result["content"]:
        result["content"] = "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
    return result


def run_poc(
    patient_id: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
    max_context_chunks: int = 60,
    verbose: bool = True,
    use_vector_store: bool = False,
) -> FinalSummary:
    t_start = time.time()
    if verbose:
        print(f"\n{'='*60}")
        print(f"PoC Pipeline | Patient: {patient_id} | Model: {model}")
        print(f"{'='*60}")

    # C1: Load + Validate + De-identify + Normalize
    ehr_path = ASSEMBLED_DIR / f"{patient_id}.json"
    if not ehr_path.exists():
        raise FileNotFoundError(f"EHR not found: {ehr_path}")

    if verbose:
        print("[C1] Processing EHR...")
    try:
        safe_ehr = load_and_process(ehr_path)
    except C1ProcessingError as e:
        print(f"[C1] VALIDATION FAILED: {e}")
        raise

    # C2: Chunk + Build Store
    if verbose:
        print("[C2] Chunking...")
    chunks = chunk_ehr(safe_ehr)
    store = build_structured_store(chunks)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    save_structured_store(store, STORE_DIR / f"{patient_id}_store.json")

    if verbose:
        type_counts = {}
        for c in chunks:
            type_counts[c.source_type] = type_counts.get(c.source_type, 0) + 1
        print(f"[C2] {len(chunks)} chunks: {type_counts}")

    # C3-prep: Build or load vector store for hybrid retrieval
    vs: VectorStore | None = None
    if use_vector_store:
        vs_path = VECTOR_DIR / patient_id
        if vs_path.exists() and (vs_path / "index.faiss").exists():
            if verbose:
                print(f"[C3] Loading vector store from {vs_path}...")
            vs = VectorStore()
            vs.load(vs_path)
        else:
            if verbose:
                print(f"[C3] Building vector store ({len(chunks)} chunks)...", end=" ", flush=True)
            vs = VectorStore()
            vs.build(chunks)
            vs.save(vs_path)
            if verbose:
                print("OK")

    # ──────────────────────────────────────────────────────────────────────────
    # C3 + C4 (LLM): Generate draft sections, store per-section chunks
    # ──────────────────────────────────────────────────────────────────────────
    draft_sections: list[SummarySection] = []
    section_chunks_map: dict[str, list[SourceChunk]] = {}
    total_tokens = 0

    for section_id in SECTIONS:
        if verbose:
            print(f"[C3→LLM] {section_id}...", end=" ", flush=True)

        # C3: retrieve relevant chunks with per-section budget (hybrid if vector store available)
        top_k = TOP_K_PER_SECTION.get(section_id, 15)
        section_chunks = retrieve_for_section(chunks, section_id, max_chunks=top_k, vector_store=vs)
        section_chunks_map[section_id] = section_chunks

        # Format context (timeline uses encounter-grouped format)
        if section_id == "treatment_timeline":
            context = format_chunks_by_encounter(section_chunks, top_k)
        else:
            context = format_chunks_as_context(section_chunks, top_k)

        prompt = build_section_prompt(section_id, context)
        try:
            raw_text, tokens = call_llm(prompt, client, model)
            total_tokens += tokens
        except Exception as e:
            print(f"ERROR: {e}")
            draft_sections.append(SummarySection(
                section_id=section_id,
                content="[LỖI: Không thể tạo section này]",
            ))
            continue

        parsed  = parse_section_response(raw_text, section_id)
        content = parsed.get("content", "Chưa thấy ghi nhận trong dữ liệu được cung cấp.")
        draft_sections.append(SummarySection(
            section_id=section_id,
            content=content,
            cited_claims=[],   # claims filled in by C5/C6 below
        ))

        if verbose:
            print(f"OK ({tokens} tok, {len(section_chunks)} chunks)")

    # ──────────────────────────────────────────────────────────────────────────
    # C5 (Claim Extraction + Evidence Matching) + C6 (Hallucination Verifier)
    # Run per section with its specific chunks for highest precision
    # ──────────────────────────────────────────────────────────────────────────
    if verbose:
        print("[C5/C6] Verifying claims per section...")

    verified_sections: list[SummarySection] = []
    removed_claims: list[CitedClaim] = []
    for draft in draft_sections:
        sc = section_chunks_map.get(draft.section_id, chunks)
        # C5 (extract + match) + C6 (KEEP/FLAG/REMOVE) run inside verify_section.
        v_section, _ = verify_section(draft, sc, conservative=True, removed_out=removed_claims)
        verified_sections.append(v_section)

    # Cross-section consistency pass (e.g. diabetes type disagreement across sections)
    verified_sections, _ = check_internal_consistency(verified_sections, conservative=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Metrics — computed from verified atomic claims (not blob-per-section)
    # ──────────────────────────────────────────────────────────────────────────
    all_claims     = [c for s in verified_sections for c in s.cited_claims if not c.is_structural]
    total_claims   = len(all_claims)
    critical_claims = [c for c in all_claims if c.is_critical]
    total_critical  = len(critical_claims)

    supported       = sum(1 for c in all_claims if c.status == "SUPPORTED")
    crit_supported  = sum(1 for c in critical_claims if c.status == "SUPPORTED")
    unsupported_n   = sum(1 for c in all_claims if c.status in ("UNSUPPORTED", "NO_CITATION"))
    low_conf        = sum(1 for c in all_claims if c.status in ("PARTIALLY_SUPPORTED", "LOW_CONFIDENCE"))
    need_rev        = sum(1 for c in all_claims if c.status == "NEED_REVIEW")
    contradicted    = sum(1 for c in all_claims if c.status == "CONTRADICTED")
    empty_sections  = sum(1 for s in verified_sections
                         if s.content and "Chưa thấy ghi nhận" in s.content)
    complete_sections = len(SECTIONS) - empty_sections

    latency = round(time.time() - t_start, 2)

    metrics = SummaryMetrics(
        citation_coverage          = round(supported / total_claims, 3)        if total_claims   else 0.0,
        critical_citation_coverage = round(crit_supported / total_critical, 3) if total_critical else 0.0,
        total_critical_claims      = total_critical,
        unsupported_claim_rate     = round(unsupported_n / total_claims, 3)    if total_claims   else 0.0,
        low_confidence_rate        = round(low_conf / total_claims, 3)         if total_claims   else 0.0,
        need_review_rate           = round(need_rev / total_claims, 3)         if total_claims   else 0.0,
        hallucination_rate         = round(contradicted / total_claims, 3)     if total_claims   else 0.0,
        missing_section_rate       = round(empty_sections / len(SECTIONS), 3)  if SECTIONS       else 0.0,
        total_claims               = total_claims,
        contradiction_count        = contradicted,
        need_review_count          = need_rev,
        duplicate_claim_count      = 0,
        latency_seconds            = latency,
        token_count                = total_tokens,
    )

    sections = verified_sections

    final = FinalSummary(
        patient_id=patient_id,
        prompt_version="poc_v4",
        model_version=model,
        sections=sections,
        metrics=metrics,
        removed_claims=removed_claims,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{patient_id}_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final.model_dump(), f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n{'='*60}")
        print(f"DONE | {patient_id}")
        print(f"  Latency:          {latency}s")
        print(f"  Tokens:           {total_tokens:,}")
        print(f"  Total claims:     {total_claims}")
        print(f"  Critical claims:  {total_critical}")
        print(f"  Coverage:         {metrics.citation_coverage:.0%} overall  "
              f"| {metrics.critical_citation_coverage:.0%} critical")
        print(f"  Low confidence:   {metrics.low_confidence_rate:.0%}")
        print(f"  Need review:      {metrics.need_review_rate:.0%}")
        print(f"  Sections:         {complete_sections}/{len(SECTIONS)}")
        print(f"  Output:           {out_path}")
        print(f"{'='*60}")

    return final


def main():
    parser = argparse.ArgumentParser(description="PoC Pipeline — Medical Record Summarization")
    parser.add_argument("--patient", default="P001")
    parser.add_argument("--all-patients", action="store_true")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--max-chunks", type=int, default=60)
    parser.add_argument("--vector", action="store_true", help="Enable vector store hybrid retrieval (default: rule-based only)")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        return

    client = OpenAI(api_key=api_key)

    use_vs = args.vector

    if args.all_patients:
        patient_ids = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
        print(f"Running PoC | {len(patient_ids)} patients | model: {args.model} | vector: {use_vs}")
        for pid in patient_ids:
            try:
                run_poc(pid, client, args.model, args.max_chunks, use_vector_store=use_vs)
            except Exception as e:
                print(f"[ERROR] {pid}: {e}")
    else:
        run_poc(args.patient, client, args.model, args.max_chunks, use_vector_store=use_vs)


if __name__ == "__main__":
    main()
