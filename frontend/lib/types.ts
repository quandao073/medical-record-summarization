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
}

export interface SummarySection {
  section_id: string;
  title: string | null;
  content: string;
  cited_claims: CitedClaim[];
}

export interface SummaryMetrics {
  citation_coverage: number;
  unsupported_claim_rate: number;
  hallucination_rate: number;
  missing_section_rate: number;
  total_claims: number;
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
  clinical_alerts:     "Cảnh báo lâm sàng",
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
  clinical_alerts:     "🚨",
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

export const STATUS_TOOLTIPS: Record<ClaimStatus, string> = {
  SUPPORTED:           "Khớp chính xác với dữ liệu nguồn",
  PARTIALLY_SUPPORTED: "Khớp từ khóa — cần xem lại nguồn",
  LOW_CONFIDENCE:      "Tin cậy thấp — không đủ bằng chứng rõ ràng",
  UNSUPPORTED:         "Không tìm thấy bằng chứng hỗ trợ",
  NO_CITATION:         "Không tìm thấy nguồn — cần xác minh",
  CONTRADICTED:        "Mâu thuẫn với dữ liệu nguồn",
  NEED_REVIEW:         "Cần xem xét thêm",
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
