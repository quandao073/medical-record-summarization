export type ClaimStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "LOW_CONFIDENCE"
  | "UNSUPPORTED"
  | "NO_CITATION"
  | "CONTRADICTED"
  | "NEED_REVIEW";

export interface CitedClaim {
  claim_text: string;
  status: ClaimStatus;
  citations: string[];
  confidence_score: number | null;
  is_critical: boolean;
  verification_status: string;
  is_structural?: boolean;
}

export interface SummarySection {
  section_id: string;
  title: string | null;
  content: string;
  cited_claims: CitedClaim[];
}

export interface SummaryMetrics {
  citation_coverage: number;
  critical_citation_coverage: number;
  total_critical_claims: number;
  unsupported_claim_rate: number;
  low_confidence_rate: number;
  need_review_rate: number;
  hallucination_rate: number;
  missing_section_rate: number;
  total_claims: number;
  contradiction_count: number;
  duplicate_claim_count: number;
  need_review_count: number;
  citation_precision: number;
  citation_recall: number;
  latency_seconds: number;
  token_count: number;
}

export interface FinalSummary {
  patient_id: string;
  created_at: string;
  prompt_version: string;
  model_version: string;
  sections: SummarySection[];
  metrics: SummaryMetrics;
  _from_cache?: boolean;
}

export interface SourceChunk {
  source_id: string;
  source_type: string;
  patient_id: string;
  encounter_id: string | null;
  date: string | null;
  content: string;
  metadata: Record<string, unknown>;
}

// ---- UI helpers ----

export const SECTION_LABELS: Record<string, string> = {
  overview:            "Tổng quan bệnh nhân",
  reason_for_visit:    "Lý do khám",
  medical_history:     "Tiền sử bệnh",
  current_medications: "Thuốc đang sử dụng",
  allergies:           "Dị ứng",
  abnormal_labs:       "Xét nghiệm bất thường",
  diagnoses:           "Chẩn đoán",
  treatment_timeline:  "Diễn biến điều trị",
  clinical_alerts:     "Thông tin cần chú ý",
};

export const SECTION_ICONS: Record<string, string> = {
  overview:            "👤",
  reason_for_visit:    "📋",
  medical_history:     "📜",
  current_medications: "💊",
  allergies:           "⚠️",
  abnormal_labs:       "🧪",
  diagnoses:           "🔬",
  treatment_timeline:  "📈",
  clinical_alerts:     "⚠️",
};

export const STATUS_COLORS: Record<ClaimStatus, string> = {
  SUPPORTED:           "bg-green-100 text-green-800 border border-green-300",
  PARTIALLY_SUPPORTED: "bg-yellow-100 text-yellow-800 border border-yellow-300",
  LOW_CONFIDENCE:      "bg-orange-100 text-orange-800 border border-orange-300",
  UNSUPPORTED:         "bg-red-100 text-red-700 border border-red-300",
  NO_CITATION:         "bg-gray-100 text-gray-600 border border-gray-300",
  CONTRADICTED:        "bg-red-200 text-red-900 border border-red-500",
  NEED_REVIEW:         "bg-purple-100 text-purple-800 border border-purple-300",
};

/** Human-readable display names — used in headers, panels, and tooltips */
export const STATUS_DISPLAY_NAMES: Record<ClaimStatus, string> = {
  SUPPORTED:           "Đã có nguồn xác nhận",
  PARTIALLY_SUPPORTED: "Có nguồn hỗ trợ một phần",
  LOW_CONFIDENCE:      "Nguồn chưa đủ rõ ràng",
  UNSUPPORTED:         "Chưa tìm thấy nguồn",
  NO_CITATION:         "Chưa tìm thấy nguồn trong hồ sơ",
  CONTRADICTED:        "Có mâu thuẫn trong hồ sơ",
  NEED_REVIEW:         "Cần bác sĩ kiểm tra",
};

export const STATUS_TOOLTIPS: Record<ClaimStatus, string> = {
  SUPPORTED:           "Thông tin này được xác nhận bởi nguồn trong hồ sơ",
  PARTIALLY_SUPPORTED: "Nguồn hỗ trợ một phần — nên xem lại nguồn tham chiếu",
  LOW_CONFIDENCE:      "Có nguồn liên quan nhưng chưa đủ rõ ràng",
  UNSUPPORTED:         "Chưa tìm thấy nguồn hỗ trợ trong hồ sơ",
  NO_CITATION:         "Chưa tìm thấy nguồn tham chiếu",
  CONTRADICTED:        "Có mâu thuẫn với dữ liệu trong hồ sơ",
  NEED_REVIEW:         "Cần bác sĩ kiểm tra thông tin này",
};

export const STATUS_LABELS: Record<ClaimStatus, string> = {
  SUPPORTED:           "✓",
  PARTIALLY_SUPPORTED: "~",
  LOW_CONFIDENCE:      "?",
  UNSUPPORTED:         "✗",
  NO_CITATION:         "–",
  CONTRADICTED:        "✗✗",
  NEED_REVIEW:         "⚑",
};

export const SOURCE_TYPE_LABELS: Record<string, string> = {
  labs:           "Xét nghiệm",
  medications:    "Thuốc",
  diagnoses:      "Chẩn đoán",
  allergies:      "Dị ứng",
  vitals:         "Sinh hiệu",
  clinical_notes: "Ghi chú lâm sàng",
  imaging:        "Chẩn đoán hình ảnh",
  procedures:     "Thủ thuật",
  patient_info:   "Thông tin bệnh nhân",
};

// ─── Review types ────────────────────────────────────────────────────────────

export type ClaimReviewAction = "approved" | "edited" | "needs_review";

export interface ClaimReview {
  claim_id: string;
  section_id: string;
  claim_text: string;
  action: ClaimReviewAction;
  new_text: string | null;
  reviewed_at: string;
}

export interface ReviewFeedback {
  text: string;
  submitted_at: string;
}

export interface ReviewState {
  patient_id: string;
  summary_status: "draft" | "confirmed";
  confirmed_at: string | null;
  reviewer: string | null;
  claim_reviews: Record<string, ClaimReview>;
  feedback: ReviewFeedback[];
}

// ─── Human Eval types ─────────────────────────────────────────────────────────

export interface RubricScore {
  score: number | null;
  notes: string;
}

export interface HumanEvalScores {
  clinical_correctness: RubricScore;
  completeness: RubricScore;
  citation_faithfulness: RubricScore;
  safety: RubricScore;
  temporal_correctness: RubricScore;
  readability: RubricScore;
}

export interface HumanEval {
  patient_id: string;
  summary_generated_at: string | null;
  model: string | null;
  prompt_version: string | null;
  evaluator: string | null;
  evaluated_at: string | null;
  scores: HumanEvalScores;
  overall_notes: string;
  error_categories: string[];
  weighted_score: number | null;
}

export const CRITERIA_CONFIG: Record<
  keyof HumanEvalScores,
  { label: string; weight: number; description: string }
> = {
  clinical_correctness: {
    label: "Độ chính xác lâm sàng",
    weight: 0.25,
    description: "Thông tin thuốc, liều, chẩn đoán, xét nghiệm có chính xác không?",
  },
  completeness: {
    label: "Tính đầy đủ",
    weight: 0.20,
    description: "Có bỏ sót thông tin lâm sàng quan trọng không?",
  },
  citation_faithfulness: {
    label: "Trích dẫn trung thực",
    weight: 0.20,
    description: "Citation có thực sự hỗ trợ claim tương ứng không?",
  },
  safety: {
    label: "An toàn",
    weight: 0.20,
    description: "Có thông tin sai lệch nguy hiểm: sai thuốc, sai liều, bỏ sót dị ứng?",
  },
  temporal_correctness: {
    label: "Đúng thứ tự thời gian",
    weight: 0.10,
    description: "Timeline điều trị và xu hướng xét nghiệm có đúng không?",
  },
  readability: {
    label: "Dễ đọc",
    weight: 0.05,
    description: "Bác sĩ đọc nhanh và hiểu được không?",
  },
};

export const ERROR_CATEGORY_LABELS: Record<string, string> = {
  omission: "Bỏ sót thông tin quan trọng",
  commission: "Thêm thông tin không có trong hồ sơ",
  wrong_source: "Citation trỏ sai nguồn",
  partial_citation: "Citation hỗ trợ một phần claim",
  no_source: "Không có citation cho claim quan trọng",
  temporal_error: "Sai thứ tự thời gian",
  safety_error: "Thông tin sai lệch nguy hiểm",
  readability_issue: "Ngôn ngữ khó đọc hoặc không tự nhiên",
};

export const SCORE_LABELS: Record<number, string> = {
  1: "Rất kém",
  2: "Kém",
  3: "Trung bình",
  4: "Tốt",
  5: "Xuất sắc",
};
