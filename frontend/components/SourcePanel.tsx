"use client";

import { useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk, ClaimReview, ClaimReviewAction } from "@/lib/types";
import { SOURCE_TYPE_LABELS, STATUS_TOOLTIPS } from "@/lib/types";
import ClaimReviewButtons from "./ClaimReviewButtons";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const CLAIM_PREFIXES = [
  "[Hỗ trợ một phần] ", "[Khớp một phần] ", "[Độ tin cậy thấp] ",
  "[Cần xác minh] ", "[Chưa có nguồn] ", "[Cần xem xét] ",
  "[Mâu thuẫn] ", "[CẦN XÁC NHẬN] ", "[Cần kiểm tra] ",
];

function stripClaimPrefix(text: string): string {
  for (const p of CLAIM_PREFIXES) {
    if (text.startsWith(p)) return text.slice(p.length).trimStart();
  }
  return text;
}

function MetaRow({ label, value, techMode }: { label: string; value: unknown; techMode?: boolean }) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean" && !value && !techMode) return null;
  if (!techMode && TECH_ONLY_KEYS.has(label)) return null;

  const displayLabel = META_LABELS_VI[label] ?? (techMode ? label : null);
  if (!displayLabel) return null;

  return (
    <div className="flex gap-2 text-xs">
      <span className="text-gray-400 min-w-[110px] shrink-0">{displayLabel}</span>
      <span className="text-gray-700 break-all">{formatMetaValue(value)}</span>
    </div>
  );
}

const STATUS_DOCTOR: Record<string, { icon: string; text: string; color: string }> = {
  SUPPORTED:           { icon: "✓", text: "Có nguồn xác nhận",       color: "text-green-700" },
  PARTIALLY_SUPPORTED: { icon: "~", text: "Hỗ trợ một phần",         color: "text-amber-600" },
  LOW_CONFIDENCE:      { icon: "~", text: "Nguồn chưa đủ rõ",        color: "text-amber-600" },
  UNSUPPORTED:         { icon: "?", text: "Chưa tìm thấy nguồn",    color: "text-red-600" },
  NO_CITATION:         { icon: "–", text: "Chưa tìm thấy nguồn",    color: "text-gray-500" },
  CONTRADICTED:        { icon: "✕", text: "Mâu thuẫn trong hồ sơ",  color: "text-red-600" },
  NEED_REVIEW:         { icon: "?", text: "Cần bác sĩ kiểm tra",    color: "text-purple-600" },
};

const STATUS_EXPLANATION: Record<string, string> = {
  SUPPORTED:           "Thông tin này được xác nhận bởi nguồn dữ liệu trong hồ sơ.",
  PARTIALLY_SUPPORTED: "Nguồn trong hồ sơ chỉ hỗ trợ một phần thông tin này.",
  LOW_CONFIDENCE:      "Có nguồn liên quan nhưng chưa đủ rõ ràng để xác nhận.",
  UNSUPPORTED:         "Không tìm thấy nguồn hỗ trợ thông tin này trong hồ sơ.",
  NO_CITATION:         "Không tìm thấy nguồn dữ liệu cho thông tin này.",
  CONTRADICTED:        "Nguồn dữ liệu trong hồ sơ mâu thuẫn với thông tin này.",
  NEED_REVIEW:         "Thông tin này cần bác sĩ xác nhận trước khi tin cậy.",
};

const META_LABELS_VI: Record<string, string> = {
  test_code: "Mã xét nghiệm",
  test_name: "Tên xét nghiệm",
  value: "Giá trị",
  unit: "Đơn vị",
  reference_range: "Ngưỡng tham chiếu",
  interpretation: "Đánh giá",
  is_abnormal: "Bất thường",
  is_critical: "Nguy hiểm",
  drug_name: "Tên thuốc",
  strength: "Hàm lượng",
  dose: "Liều dùng",
  frequency: "Tần suất",
  instruction: "Hướng dẫn",
  indication: "Mục đích",
  is_current: "Đang sử dụng",
  missing_dose: "Thiếu thông tin liều",
  diagnosis_name: "Tên bệnh",
  diagnosis_type: "Loại chẩn đoán",
  icd10_code: "Mã ICD-10",
  is_active: "Đang hoạt động",
  substance: "Chất gây dị ứng",
  reaction: "Phản ứng",
  severity: "Mức độ",
  status: "Trạng thái",
  needs_patient_confirmation: "Cần xác nhận BN",
  procedure_name: "Tên thủ thuật",
  modality: "Phương pháp",
  body_part: "Vùng cơ thể",
  section: "Phần ghi chú",
  note_type: "Loại ghi chú",
  author: "Người viết",
  blood_pressure: "Huyết áp",
  abnormal_flags: "Bất thường",
  bmi: "BMI",
  age: "Tuổi",
  gender: "Giới tính",
};

const TECH_ONLY_KEYS = new Set([
  "is_current", "is_active", "note_type",
]);

function formatMetaValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "Không có";
  return String(value);
}

function confidenceLabel(score: number): string {
  if (score >= 0.8) return "Cao";
  if (score >= 0.5) return "Trung bình";
  return "Thấp";
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  sourceId: string | null;
  chunk: SourceChunk | null;
  claimContext: CitedClaim | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  techMode?: boolean;
  claimReview?: ClaimReview | null;
  onClaimReview?: (action: ClaimReviewAction, newText?: string) => Promise<void>;
  onSourceSwitch?: (sourceId: string) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function SourcePanel({
  sourceId,
  chunk,
  claimContext,
  loading,
  error,
  onClose,
  techMode,
  claimReview,
  onClaimReview,
  onSourceSwitch,
}: Props) {
  const [showTechDetails, setShowTechDetails] = useState(false);

  if (!sourceId) return null;

  const statusInfo = claimContext
    ? STATUS_DOCTOR[claimContext.status] ?? STATUS_DOCTOR.NEED_REVIEW
    : null;

  return (
    <aside className="fixed right-0 top-0 h-full w-[380px] bg-white shadow border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="font-semibold text-gray-800 text-sm">Nguồn tham chiếu</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-lg leading-none w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 pb-20 space-y-0">

        {/* ── Claim context ─────────────────────────────────────────────────── */}
        {claimContext && statusInfo && (
          <div className="pb-3 mb-3 border-b border-gray-100 space-y-2.5">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              Thông tin đang kiểm tra
            </p>
            <p className="text-sm text-gray-800 leading-relaxed">
              &ldquo;{stripClaimPrefix(claimContext.claim_text)}&rdquo;
            </p>

            {/* Status — compact single line */}
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <span className={`font-semibold ${statusInfo.color}`}>
                {statusInfo.text}
              </span>
              {claimContext.is_critical && (
                <>
                  <span className="text-gray-300">·</span>
                  <span className="text-red-600 font-medium">Quan trọng</span>
                </>
              )}
              {claimContext.confidence_score != null && (
                <>
                  <span className="text-gray-300">·</span>
                  <span className={`font-medium ${
                    claimContext.confidence_score >= 0.8 ? "text-green-600" :
                    claimContext.confidence_score >= 0.5 ? "text-amber-600" :
                    "text-red-600"
                  }`}>
                    Tin cậy: {confidenceLabel(claimContext.confidence_score)}
                  </span>
                  {techMode && (
                    <span className="font-mono text-gray-400">
                      ({claimContext.confidence_score.toFixed(2)})
                    </span>
                  )}
                </>
              )}
            </div>

            <p className="text-xs text-gray-400 leading-relaxed">
              {STATUS_EXPLANATION[claimContext.status] ?? ""}
            </p>

            {/* Multiple citations */}
            {claimContext.citations.length > 1 && (
              <div className="flex flex-wrap gap-1">
                {claimContext.citations.map((sid) => (
                  <button
                    key={sid}
                    onClick={() => sid !== sourceId && onSourceSwitch?.(sid)}
                    className={`text-xs px-2 py-0.5 rounded border transition ${
                      sid === sourceId
                        ? "bg-gray-100 text-gray-700 border-gray-300 font-medium"
                        : "text-gray-500 border-gray-200 hover:bg-gray-50 cursor-pointer"
                    }`}
                  >
                    {techMode ? sid.split("-").slice(-2).join("-") : `Nguồn ${claimContext.citations.indexOf(sid) + 1}`}
                  </button>
                ))}
              </div>
            )}

            {/* Review buttons */}
            {onClaimReview && (
              <ClaimReviewButtons
                currentReview={claimReview ?? null}
                onReview={onClaimReview}
              />
            )}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-red-600 text-sm p-3 rounded-lg border border-red-200">
            {error}
          </div>
        )}

        {/* ── Chunk data ────────────────────────────────────────────────────── */}
        {chunk && !loading && (
          <div className="space-y-3">
            {/* Source type + Date */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-gray-500 font-medium">
                {SOURCE_TYPE_LABELS[chunk.source_type] ?? chunk.source_type}
              </span>
              {chunk.date && (
                <>
                  <span className="text-gray-300">·</span>
                  <span className="text-gray-400">{chunk.date}</span>
                </>
              )}
            </div>

            {/* Content */}
            <div className="pb-3 border-b border-gray-100">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">
                Nội dung trong hồ sơ
              </p>
              <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-line">
                {chunk.content}
              </p>
            </div>

            {/* Metadata */}
            {Object.keys(chunk.metadata).length > 0 && (
              <div className="pb-3 border-b border-gray-100">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Thông tin chi tiết
                </p>
                <div className="space-y-1">
                  {Object.entries(chunk.metadata).map(([k, v]) => (
                    <MetaRow key={k} label={k} value={v as unknown} techMode={techMode} />
                  ))}
                </div>
              </div>
            )}

            {/* Technical details toggle */}
            {!techMode && (
              <button
                onClick={() => setShowTechDetails((v) => !v)}
                className="text-xs text-gray-400 hover:text-gray-600 transition flex items-center gap-1"
              >
                {showTechDetails ? "▼ Ẩn thông tin kỹ thuật" : "▶ Thông tin kỹ thuật"}
              </button>
            )}

            {/* Technical IDs */}
            {(techMode || showTechDetails) && (
              <div className="space-y-1 pt-1 border-t border-gray-100">
                <MetaRow label="source_id"    value={chunk.source_id} techMode />
                <MetaRow label="patient_id"   value={chunk.patient_id} techMode />
                <MetaRow label="encounter_id" value={chunk.encounter_id} techMode />
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
