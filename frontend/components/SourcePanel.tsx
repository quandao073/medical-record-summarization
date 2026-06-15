"use client";

import { useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { SOURCE_TYPE_LABELS, STATUS_TOOLTIPS } from "@/lib/types";

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
    <div className="flex gap-2 text-sm">
      <span className="text-gray-500 min-w-[130px] shrink-0">{displayLabel}</span>
      <span className="text-gray-800 break-all">{formatMetaValue(value)}</span>
    </div>
  );
}

const STATUS_DOCTOR_LABELS: Record<string, { icon: string; text: string; cls: string; explanation: string }> = {
  SUPPORTED:           { icon: "✅", text: "Đã có nguồn xác nhận",       cls: "bg-green-50 text-green-700 border-green-200",  explanation: "Thông tin này được xác nhận bởi nguồn dữ liệu trong hồ sơ." },
  PARTIALLY_SUPPORTED: { icon: "⚠️", text: "Có nguồn hỗ trợ một phần",   cls: "bg-amber-50 text-amber-700 border-amber-200",  explanation: "Nguồn trong hồ sơ chỉ hỗ trợ một phần thông tin này. Một số chi tiết chưa được xác nhận đầy đủ." },
  LOW_CONFIDENCE:      { icon: "⚠️", text: "Nguồn chưa đủ rõ ràng",      cls: "bg-orange-50 text-orange-700 border-orange-200", explanation: "Có nguồn liên quan nhưng chưa đủ rõ ràng để xác nhận thông tin." },
  UNSUPPORTED:         { icon: "❓", text: "Chưa tìm thấy nguồn",        cls: "bg-red-50 text-red-700 border-red-200",        explanation: "Không tìm thấy nguồn hỗ trợ thông tin này trong hồ sơ." },
  NO_CITATION:         { icon: "➖", text: "Chưa tìm thấy nguồn",        cls: "bg-gray-50 text-gray-600 border-gray-200",     explanation: "Không tìm thấy nguồn dữ liệu cho thông tin này." },
  CONTRADICTED:        { icon: "❌", text: "Có mâu thuẫn trong hồ sơ",   cls: "bg-red-50 text-red-700 border-red-300",        explanation: "Nguồn dữ liệu trong hồ sơ mâu thuẫn với thông tin này." },
  NEED_REVIEW:         { icon: "🔍", text: "Cần bác sĩ kiểm tra",       cls: "bg-purple-50 text-purple-700 border-purple-200", explanation: "Thông tin này cần bác sĩ xác nhận trước khi tin cậy." },
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

const CONFIDENCE_LABELS: Record<string, string> = {};
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
}: Props) {
  const [showTechDetails, setShowTechDetails] = useState(false);

  if (!sourceId) return null;

  const statusInfo = claimContext
    ? STATUS_DOCTOR_LABELS[claimContext.status] ?? STATUS_DOCTOR_LABELS.NEED_REVIEW
    : null;

  return (
    <aside className="fixed right-0 top-0 h-full w-[400px] bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div>
          <h3 className="font-semibold text-gray-800 text-sm">Nguồn tham chiếu</h3>
          {techMode && (
            <p className="text-xs text-gray-400 mt-0.5">Citation Grounding</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-xl leading-none font-bold w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* ── Claim context ─────────────────────────────────────────────────── */}
        {claimContext && statusInfo && (
          <div className="rounded-xl border border-gray-100 bg-gray-50 p-3 space-y-2.5">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Thông tin đang kiểm tra
            </p>

            {/* Claim text */}
            <p className="text-sm text-gray-800 bg-white rounded-lg px-3 py-2 border border-gray-200 leading-relaxed italic">
              &ldquo;{stripClaimPrefix(claimContext.claim_text)}&rdquo;
            </p>

            {/* Status badge — doctor-friendly */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500">Kết luận kiểm tra:</p>
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${statusInfo.cls}`}>
                {statusInfo.icon} {statusInfo.text}
              </span>

              {/* Critical indicator */}
              {claimContext.is_critical && (
                <span className="ml-2 inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200">
                  Mức độ quan trọng: Cao
                </span>
              )}

              {/* Confidence — doctor-friendly label instead of raw number */}
              {claimContext.confidence_score !== null && claimContext.confidence_score !== undefined && (
                <div className="text-xs text-gray-500">
                  Mức độ tin cậy:{" "}
                  <span className={`font-medium ${
                    claimContext.confidence_score >= 0.8 ? "text-green-600" :
                    claimContext.confidence_score >= 0.5 ? "text-amber-600" :
                    "text-red-600"
                  }`}>
                    {confidenceLabel(claimContext.confidence_score)}
                  </span>
                  {techMode && (
                    <span className="ml-1 font-mono text-gray-400">
                      ({claimContext.confidence_score.toFixed(2)})
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Explanation */}
            <p className="text-xs text-gray-500 leading-relaxed">
              {statusInfo.explanation}
            </p>

            {/* All citations for this claim */}
            {claimContext.citations.length > 1 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 mb-1">
                  Thông tin này có {claimContext.citations.length} nguồn liên quan:
                </p>
                <div className="flex flex-wrap gap-1">
                  {claimContext.citations.map((sid) => (
                    <span
                      key={sid}
                      className={`text-xs px-2 py-0.5 rounded border ${
                        sid === sourceId
                          ? "bg-blue-100 text-blue-700 border-blue-300 font-semibold"
                          : "bg-gray-50 text-gray-500 border-gray-200"
                      }`}
                    >
                      {sid === sourceId ? "► " : ""}
                      {techMode ? sid.split("-").slice(-2).join("-") : `Nguồn ${claimContext.citations.indexOf(sid) + 1}`}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg border border-red-200">
            {error}
          </div>
        )}

        {/* ── Chunk data ────────────────────────────────────────────────────── */}
        {chunk && !loading && (
          <>
            {/* Source type + Date — doctor-friendly */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Nguồn trong hồ sơ
              </p>
              <div className="flex gap-2 flex-wrap">
                <span className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full border border-indigo-200 font-medium">
                  {SOURCE_TYPE_LABELS[chunk.source_type] ?? chunk.source_type}
                </span>
                {chunk.date && (
                  <span className="px-2 py-1 bg-gray-50 text-gray-600 text-xs rounded-full border border-gray-200">
                    {chunk.date}
                  </span>
                )}
              </div>
            </div>

            {/* Content */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Nội dung trong hồ sơ
              </p>
              <p className="text-base text-gray-800 bg-gray-50 rounded-lg p-3 border border-gray-200 leading-relaxed whitespace-pre-line">
                {chunk.content}
              </p>
            </div>

            {/* Metadata — shown as "Thông tin chi tiết" in doctor mode */}
            {Object.keys(chunk.metadata).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Thông tin chi tiết
                </p>
                <div className="space-y-1.5 bg-gray-50 rounded-lg p-3 border border-gray-200">
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
                className="text-xs text-gray-400 hover:text-indigo-600 transition flex items-center gap-1"
              >
                {showTechDetails ? "▼ Ẩn thông tin kỹ thuật" : "▶ Hiện thông tin kỹ thuật"}
              </button>
            )}

            {/* Technical IDs — always shown in techMode, togglable otherwise */}
            {(techMode || showTechDetails) && (
              <div className="space-y-1 pt-1 border-t border-gray-100">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                  Thông tin kỹ thuật
                </p>
                <MetaRow label="source_id"    value={chunk.source_id} techMode />
                <MetaRow label="patient_id"   value={chunk.patient_id} techMode />
                <MetaRow label="encounter_id" value={chunk.encounter_id} techMode />
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
