"""
PoC Pipeline — Tuan 2.
Minimal end-to-end: EHR -> C1 -> C2 -> LLM (all chunks as context) -> structured summary.
Provider: OpenAI only.
Section IDs: English. Summary content: Vietnamese.

Usage:
    python -m poc.poc_pipeline --patient P001
    python -m poc.poc_pipeline --patient P001 --model gpt-4o-mini
    python -m poc.poc_pipeline --all-patients
"""

from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

from src.c1_emr.pipeline import load_and_process, C1ProcessingError
from src.c2_chunking.chunker import chunk_ehr
from src.c2_chunking.store_builder import build_structured_store, save_structured_store
from src.schemas import SourceChunk, FinalSummary, SummarySection, CitedClaim, SummaryMetrics

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR      = ROOT / "data" / "processed"
ASSEMBLED_DIR = DATA_DIR / "assembled"
STORE_DIR     = DATA_DIR / "stores"
OUTPUT_DIR    = DATA_DIR / "outputs"

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
    "clinical_alerts":     "Điểm cần lưu ý / Cảnh báo",
}

# Sections that always require citations (critical clinical data)
CRITICAL_SECTIONS = {"current_medications", "allergies", "abnormal_labs", "diagnoses"}

# ---------------------------------------------------------------------------
# Prompts — instructions in Vietnamese so LLM outputs Vietnamese
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Bạn là hệ thống tóm tắt hồ sơ bệnh án lâm sàng hỗ trợ bác sĩ Việt Nam.

NGUYÊN TẮC BẮT BUỘC:
1. Chỉ dùng thông tin có trong [CONTEXT]. Tuyệt đối không suy luận thêm.
2. Nếu không có thông tin cho section này: viết "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
3. Không kê đơn, không chẩn đoán thêm, không gợi ý điều trị.
4. Giữ nguyên mã ICD-10, tên thuốc, giá trị số từ context.
5. Giữ nguyên source_id từ [CONTEXT] khi tham chiếu.
6. Output ngắn gọn, đúng chuẩn lâm sàng, không có disclaimer AI.

ĐỊNH DẠNG OUTPUT BẮT BUỘC (JSON):
Trả về một JSON object với key là section_id được yêu cầu.
Mỗi section là một object: {"content": "...", "source_ids": ["id1", "id2"]}
source_ids là danh sách các source_id từ [CONTEXT] hỗ trợ cho content đó.
"""

SECTION_GUIDELINES = {
    "overview": (
        "Viết Tổng quan (tối đa 2 câu): tuổi, giới, bệnh nền chính, BMI nếu có. "
        "Ví dụ: 'Bệnh nhân nam 55 tuổi, tiền sử tăng huyết áp 5 năm, đái tháo đường type 2. BMI 29.1.'"
    ),
    "reason_for_visit": (
        "Nêu lý do khám và triệu chứng chính từ dữ liệu. "
        "Nếu có nhiều lần khám, ưu tiên lần khám gần nhất."
    ),
    "medical_history": (
        "Liệt kê tiền sử bệnh bản thân (bệnh nền, phẫu thuật), tiền sử gia đình quan trọng. "
        "Không lặp lại phần dị ứng."
    ),
    "current_medications": (
        "Liệt kê thuốc theo format: Tên thuốc Hàm lượng — Liều, Tần suất. "
        "Nếu thiếu liều: ghi '(thiếu thông tin liều)'. "
        "Ưu tiên thuốc từ lần khám gần nhất / is_current=true."
    ),
    "allergies": (
        "Liệt kê tất cả dị ứng đã biết. "
        "Nếu không có dữ liệu dị ứng: 'Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp.' "
        "Dị ứng cần xác nhận: đánh dấu [CẦN XÁC NHẬN]."
    ),
    "abnormal_labs": (
        "Liệt kê chỉ XN bất thường (abnormal=true hoặc critical=true). "
        "Format: Tên XN: giá trị đơn_vị ↑/↓ (tham chiếu: range) [ngày]. "
        "Ghi ngày xét nghiệm nếu có nhiều lần khám."
    ),
    "diagnoses": (
        "Liệt kê chẩn đoán từ lần khám gần nhất. "
        "Format: Bệnh chính: tên (mã ICD-10). Bệnh kèm: tên (mã ICD-10). "
        "Giữ nguyên mã ICD-10 từ context."
    ),
    "clinical_alerts": (
        "Liệt kê 3-5 điểm quan trọng nhất cần lưu ý: "
        "chỉ số chưa đạt mục tiêu, nguy cơ, biến chứng, dị ứng, thông tin cần xác nhận. "
        "Chỉ kết luận từ dữ liệu có trong context."
    ),
}


def format_chunks_as_context(chunks: list[SourceChunk], max_chunks: int = 60) -> str:
    lines = []
    for chunk in chunks[:max_chunks]:
        date_str = f" [{chunk.date}]" if chunk.date else ""
        lines.append(f"[{chunk.source_id}]{date_str} ({chunk.source_type}): {chunk.content}")
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
    max_tokens: int = 1000,
    retries: int = 3,
) -> tuple[str, int]:
    """Call OpenAI API with retry. Returns (text, total_tokens)."""
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.1,
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


def parse_section_response(text: str, section_id: str) -> dict:
    """Parse LLM JSON response for one section."""
    try:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        data = json.loads(text)
        if section_id in data:
            return data[section_id]
        if "content" in data:
            return data
        return {"content": str(data), "source_ids": []}
    except json.JSONDecodeError:
        return {"content": text, "source_ids": []}


def run_poc(
    patient_id: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
    max_context_chunks: int = 60,
    verbose: bool = True,
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

    context = format_chunks_as_context(chunks, max_context_chunks)

    # LLM: Generate each section
    sections: list[SummarySection] = []
    total_tokens = 0

    for section_id in SECTIONS:
        if verbose:
            print(f"[LLM] {section_id}...", end=" ", flush=True)

        prompt = build_section_prompt(section_id, context)
        try:
            raw_text, tokens = call_llm(prompt, client, model)
            total_tokens += tokens
        except Exception as e:
            print(f"ERROR: {e}")
            sections.append(SummarySection(
                section_id=section_id,
                content="[LỖI: Không thể tạo section này]",
            ))
            continue

        parsed = parse_section_response(raw_text, section_id)
        content   = parsed.get("content", "Chưa thấy ghi nhận trong dữ liệu được cung cấp.")
        source_ids = parsed.get("source_ids", [])

        valid_ids = [sid for sid in source_ids if sid in store]
        claim = CitedClaim(
            claim_text=content,
            status="SUPPORTED" if valid_ids else "NO_CITATION",
            citations=valid_ids,
            is_critical=section_id in CRITICAL_SECTIONS,
        )
        sections.append(SummarySection(
            section_id=section_id,
            content=content,
            cited_claims=[claim],
        ))

        if verbose:
            print(f"OK ({tokens} tok, {len(valid_ids)} citations)")

    # Metrics
    all_claims = [c for s in sections for c in s.cited_claims]
    total_claims = len(all_claims)
    supported = sum(1 for c in all_claims if c.status == "SUPPORTED")
    no_citation = sum(1 for c in all_claims if c.status == "NO_CITATION")
    complete_sections = sum(
        1 for s in sections
        if s.content
        and "Chưa thấy ghi nhận" not in s.content
        and "[LỖI" not in s.content
    )
    latency = round(time.time() - t_start, 2)

    metrics = SummaryMetrics(
        citation_coverage=round(supported / total_claims, 3) if total_claims else 0.0,
        unsupported_claim_rate=round(no_citation / total_claims, 3) if total_claims else 0.0,
        missing_section_rate=round((len(SECTIONS) - complete_sections) / len(SECTIONS), 3),
        total_claims=total_claims,
        latency_seconds=latency,
        token_count=total_tokens,
    )

    final = FinalSummary(
        patient_id=patient_id,
        prompt_version="poc_v1",
        model_version=model,
        sections=sections,
        metrics=metrics,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{patient_id}_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final.model_dump(), f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n{'='*60}")
        print(f"DONE | {patient_id}")
        print(f"  Latency:   {latency}s")
        print(f"  Tokens:    {total_tokens:,}")
        print(f"  Coverage:  {metrics.citation_coverage:.0%}")
        print(f"  Sections:  {complete_sections}/{len(SECTIONS)}")
        print(f"  Output:    {out_path}")
        print(f"{'='*60}")

    return final


def main():
    parser = argparse.ArgumentParser(description="PoC Pipeline — Medical Record Summarization")
    parser.add_argument("--patient", default="P001")
    parser.add_argument("--all-patients", action="store_true")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--max-chunks", type=int, default=60)
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        return

    client = OpenAI(api_key=api_key)

    if args.all_patients:
        patient_ids = sorted(p.stem for p in ASSEMBLED_DIR.glob("*.json"))
        print(f"Running PoC | {len(patient_ids)} patients | model: {args.model}")
        for pid in patient_ids:
            try:
                run_poc(pid, client, args.model, args.max_chunks)
            except Exception as e:
                print(f"[ERROR] {pid}: {e}")
    else:
        run_poc(args.patient, client, args.model, args.max_chunks)


if __name__ == "__main__":
    main()
