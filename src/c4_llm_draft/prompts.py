"""Prompt definitions for clinical section summarization."""

from __future__ import annotations

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

TOP_K_PER_SECTION: dict[str, int] = {
    "overview":            8,
    "reason_for_visit":    5,
    "medical_history":     15,
    "current_medications": 15,
    "allergies":           5,
    "abnormal_labs":       20,
    "diagnoses":           10,
    "treatment_timeline":  50,
    "clinical_alerts":     20,
}

# ---------------------------------------------------------------------------
# System prompt — Vietnamese so LLM outputs Vietnamese
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
        "BẮT BUỘC: Liệt kê ĐẦY ĐỦ TẤT CẢ dị ứng riêng biệt có trong context, không bỏ sót dị ứng nào — "
        "kể cả khi chỉ có tên tác nhân mà thiếu thông tin phản ứng/mức độ/trạng thái. "
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
        "10. BẮT BUỘC: mỗi bullet chỉ chứa MỘT thông tin/chỉ số duy nhất (atomic claim) — "
        "không gộp nhiều chỉ số hoặc nhiều nhận xét khác nhau vào một bullet. "
        "Nếu có nhiều chỉ số liên quan, tách thành nhiều bullet riêng, mỗi bullet ứng với một nguồn dữ liệu duy nhất.\n"
    ),
}


SECTION_EXAMPLES: dict[str, str] = {
    "overview": '''{
  "overview": {
    "content": "Bệnh nhân Nguyễn Văn An, 55 tuổi, nam giới, có bệnh nền chính là đái tháo đường type 2. Bệnh nhân có BMI 28.0, thuộc nhóm thừa cân. Hiện tại đang theo dõi biến chứng microalbuminuria.",
    "source_ids": ["P001-PATIENT-INFO", "P001-E004-DX-E11"]
  }
}''',
    "medical_history": '''{
  "medical_history": {
    "content": "Tiền sử bản thân:\\n- Đái tháo đường type 2, phát hiện năm 2021.\\n- Tăng huyết áp, phát hiện năm 2019.\\n\\nTiền sử gia đình:\\n- Cha mắc đái tháo đường type 2, mất năm 2018 do nhồi máu cơ tim.\\n\\nThói quen nguy cơ:\\n- Hút thuốc lá 15 gói-năm, đã bỏ 2 năm nay.",
    "source_ids": ["P001-E001-NOTE-NOTE002", "P001-E001-NOTE-NOTE004"]
  }
}''',
    "abnormal_labs": '''{
  "abnormal_labs": {
    "content": "- HbA1c: 7.1%, cao, tham chiếu: <5.6%, ngày: 2024-10-10. Xu hướng: 9.2% xuống 7.1%, cải thiện.\\n- Glucose huyết tương lúc đói: 6.2 mmol/L, cao, tham chiếu: 3.9 - 6.1, ngày: 2024-10-10.\\n- Microalbumin/Creatinine ratio: 32 mg/g, cao, tham chiếu: <30, ngày: 2024-10-10. Xu hướng: 42 xuống 32, giảm.\\n- LDL-Cholesterol: 2.8 mmol/L, cao, tham chiếu: <2.6, ngày: 2024-07-10.\\n- Cholesterol toàn phần: 5.8 mmol/L, cao, tham chiếu: <5.2, ngày: 2024-01-10.\\n- Triglyceride: 2.8 mmol/L, cao, tham chiếu: <1.7, ngày: 2024-01-10.\\n- HDL-Cholesterol: 0.9 mmol/L, thấp, tham chiếu: >1.0, ngày: 2024-01-10.",
    "source_ids": ["P001-E004-LAB-HBA1C", "P001-E004-LAB-GLUCOSE", "P001-E004-LAB-ACR", "P001-E003-LAB-LDL", "P001-E001-LAB-CHOL"]
  }
}''',
    "diagnoses": '''{
  "diagnoses": {
    "content": "- Chính: Đái tháo đường type 2 (E11)\\n- Bệnh kèm: Tăng huyết áp nguyên phát (I10)\\n- Bệnh kèm: Rối loạn chuyển hóa lipid hỗn hợp (E78.5)\\n- Biến chứng: Microalbuminuria trong ĐTĐ (N18.3)\\n- Biến chứng: Bệnh thần kinh ngoại biên trong ĐTĐ (G63.2)",
    "source_ids": ["P001-E004-DX-E11", "P001-E004-DX-I10", "P001-E004-DX-E78.5", "P001-E004-DX-N18.3", "P001-E001-DX-G63.2"]
  }
}''',
    "clinical_alerts": '''{
  "clinical_alerts": {
    "content": "Cảnh báo hiện tại:\\n- Microalbuminuria với tỷ lệ 32 mg/g cần tiếp tục theo dõi.\\n- Glucose huyết tương lúc đói 6.2 mmol/L còn cao.\\n\\nĐã cải thiện:\\n- Microalbuminuria giảm từ 42 mg/g sang 32 mg/g.\\n- HbA1c giảm từ 7.5% sang 7.1%.\\n\\nCần xác minh:\\n- Không ghi nhận.",
    "source_ids": ["P001-E004-LAB-ACR", "P001-E004-LAB-HBA1C"]
  }
}''',
}


def build_section_prompt(section_id: str, context: str, *, local_model: bool = False) -> str:
    label = SECTION_LABELS.get(section_id, section_id)
    guideline = SECTION_GUIDELINES.get(section_id, "Tóm tắt ngắn gọn thông tin liên quan.")

    example_block = ""
    if local_model and section_id in SECTION_EXAMPLES:
        example_block = f"\n\n[VÍ DỤ OUTPUT]\n{SECTION_EXAMPLES[section_id]}"

    local_reminders = ""
    if local_model:
        local_reminders = (
            "\n\nLƯU Ý QUAN TRỌNG:"
            "\n- content phải là văn bản tiếng Việt tự nhiên, KHÔNG chèn source_id vào content."
            "\n- KHÔNG để raw field name (vd: overweight_bmi) — phải dịch sang tiếng Việt."
            "\n- KHÔNG bọc output trong thêm JSON wrapper."
            "\n- Liệt kê ĐẦY ĐỦ các mục, không bỏ sót."
        )

    return f"""[CONTEXT]
{context}

[YÊU CẦU]
Section: {label}
Hướng dẫn: {guideline}{local_reminders}{example_block}

Trả về JSON:
{{
  "{section_id}": {{
    "content": "...",
    "source_ids": ["source_id_1", "source_id_2"]
  }}
}}
Chỉ trả JSON, không thêm giải thích.
"""
