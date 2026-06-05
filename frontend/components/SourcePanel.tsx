"use client";

import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { SOURCE_TYPE_LABELS, STATUS_COLORS, STATUS_DISPLAY_NAMES, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";

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

function MetaRow({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "" || value === false) return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-gray-500 min-w-[130px] shrink-0">{label}</span>
      <span className="text-gray-800 font-mono break-all">{String(value)}</span>
    </div>
  );
}

const VERIFICATION_LABELS: Record<string, { text: string; cls: string }> = {
  PENDING:    { text: "⏳ Chờ bác sĩ duyệt",  cls: "bg-amber-50 text-amber-700 border-amber-200" },
  CONFIRMED:  { text: "✅ Bác sĩ đã xác nhận", cls: "bg-green-50 text-green-700 border-green-200" },
  UNVERIFIED: { text: "❓ Chưa xác nhận",      cls: "bg-gray-50 text-gray-600 border-gray-200"   },
  INCORRECT:  { text: "❌ Không chính xác",    cls: "bg-red-50 text-red-700 border-red-200"      },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  sourceId: string | null;
  chunk: SourceChunk | null;
  claimContext: CitedClaim | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function SourcePanel({
  sourceId,
  chunk,
  claimContext,
  loading,
  error,
  onClose,
}: Props) {
  if (!sourceId) return null;

  const verif = claimContext
    ? VERIFICATION_LABELS[claimContext.verification_status] ?? VERIFICATION_LABELS.PENDING
    : null;

  return (
    <aside className="fixed right-0 top-0 h-full w-[400px] bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div>
          <h3 className="font-semibold text-gray-800 text-sm">Nguồn gốc dữ liệu</h3>
          <p className="text-xs text-gray-400 mt-0.5">Citation Grounding</p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-xl leading-none font-bold w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Source ID */}
        <div className="font-mono text-xs bg-blue-50 text-blue-700 px-3 py-2 rounded-lg break-all border border-blue-100">
          {sourceId}
        </div>

        {/* ── Claim context ─────────────────────────────────────────────────── */}
        {claimContext && (
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 p-3 space-y-2.5">
            <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">
              Claim đã tham chiếu source này
            </p>

            {/* Claim text — strip any known prefix before display */}
            <p className="text-sm text-gray-800 bg-white rounded-lg px-3 py-2 border border-indigo-100 leading-relaxed italic">
              &ldquo;{stripClaimPrefix(claimContext.claim_text)}&rdquo;
            </p>

            {/* Combined status + verification (issue 5) */}
            <div className="flex flex-wrap gap-2 items-center">
              {/* Primary combined badge — maps status + verification into one clear label */}
              {claimContext.status === "SUPPORTED" ? (
                <span
                  title={STATUS_TOOLTIPS[claimContext.status as ClaimStatus]}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800 border border-green-300"
                >
                  ✓ Đã có nguồn
                  {verif && (
                    <span className="text-green-600 font-normal">· {verif.text.replace(/^[^ ]+ /, "")}</span>
                  )}
                </span>
              ) : (
                <span
                  title={STATUS_TOOLTIPS[claimContext.status as ClaimStatus]}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${
                    STATUS_COLORS[claimContext.status as ClaimStatus]
                  }`}
                >
                  {STATUS_LABELS[claimContext.status as ClaimStatus]}
                  {STATUS_DISPLAY_NAMES[claimContext.status as ClaimStatus]}
                </span>
              )}

              {/* Critical indicator */}
              {claimContext.is_critical && (
                <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200">
                  🔴 Critical
                </span>
              )}

              {/* Confidence score */}
              {claimContext.confidence_score !== null && claimContext.confidence_score !== undefined && (
                <span className="px-2 py-1 rounded-full text-xs font-mono bg-gray-100 text-gray-600 border border-gray-200">
                  conf: {claimContext.confidence_score.toFixed(2)}
                </span>
              )}
            </div>

            {/* Verification status — only shown if NOT SUPPORTED (SUPPORTED already combined above) */}
            {verif && claimContext.status !== "SUPPORTED" && (
              <span className={`inline-flex text-xs px-2 py-1 rounded-lg border ${verif.cls}`}>
                {verif.text}
              </span>
            )}

            {/* Status explanation line */}
            <p className="text-xs text-gray-500 leading-relaxed">
              {claimContext.status === "SUPPORTED" && "Claim này được hỗ trợ đầy đủ bởi nguồn dữ liệu bên dưới."}
              {claimContext.status === "PARTIALLY_SUPPORTED" && "Nguồn này chỉ hỗ trợ một phần claim. Một số chi tiết chưa được xác nhận đầy đủ."}
              {claimContext.status === "LOW_CONFIDENCE" && "Nguồn có liên quan nhưng chưa đủ rõ ràng để xác nhận claim."}
              {claimContext.status === "NEED_REVIEW" && "Claim cần bác sĩ hoặc bệnh nhân xác nhận trước khi tin cậy."}
              {claimContext.status === "NO_CITATION" && "Không tìm thấy nguồn dữ liệu hỗ trợ claim này."}
              {claimContext.status === "UNSUPPORTED" && "Claim không có nguồn hỗ trợ trong dữ liệu được cung cấp."}
              {claimContext.status === "CONTRADICTED" && "Nguồn dữ liệu mâu thuẫn với nội dung claim này."}
            </p>

            {/* All citations for this claim (issue 4) */}
            {claimContext.citations.length > 1 && (
              <div>
                <p className="text-xs font-semibold text-indigo-600 mb-1">
                  Claim này có {claimContext.citations.length} nguồn:
                </p>
                <div className="flex flex-wrap gap-1">
                  {claimContext.citations.map((sid) => (
                    <span
                      key={sid}
                      className={`font-mono text-xs px-2 py-0.5 rounded border ${
                        sid === sourceId
                          ? "bg-blue-100 text-blue-700 border-blue-300 font-semibold"
                          : "bg-gray-50 text-gray-500 border-gray-200"
                      }`}
                    >
                      {sid === sourceId ? "► " : ""}{sid.split("-").slice(-2).join("-")}
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
            {/* Type + Date */}
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

            {/* Raw content */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Nội dung gốc
              </p>
              <p className="text-base text-gray-800 bg-gray-50 rounded-lg p-3 border border-gray-200 leading-relaxed whitespace-pre-line">
                {chunk.content}
              </p>
            </div>

            {/* Metadata */}
            {Object.keys(chunk.metadata).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Metadata
                </p>
                <div className="space-y-1.5 bg-gray-50 rounded-lg p-3 border border-gray-200">
                  {Object.entries(chunk.metadata).map(([k, v]) => (
                    <MetaRow key={k} label={k} value={v as unknown} />
                  ))}
                </div>
              </div>
            )}

            {/* IDs */}
            <div className="space-y-1 pt-1 border-t border-gray-100">
              <MetaRow label="source_id"    value={chunk.source_id} />
              <MetaRow label="patient_id"   value={chunk.patient_id} />
              <MetaRow label="encounter_id" value={chunk.encounter_id} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
