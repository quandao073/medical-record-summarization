import type { SummaryMetrics } from "@/lib/types";

interface Props {
  metrics: SummaryMetrics;
  techMode?: boolean;
  readMode?: "quick" | "detail";
  onReadModeChange?: (mode: "quick" | "detail") => void;
}

function TechPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-white border border-gray-200 shadow-sm min-w-[90px]">
      <span className="text-base font-bold text-gray-700">{value}</span>
      <span className="text-xs text-gray-500 mt-0.5 text-center leading-tight">{label}</span>
    </div>
  );
}

export default function MetricsBar({ metrics, techMode, readMode, onReadModeChange }: Props) {
  const coverage     = Math.round(metrics.citation_coverage * 100);
  const critCoverage = Math.round((metrics.critical_citation_coverage ?? 0) * 100);
  const unsup        = Math.round(metrics.unsupported_claim_rate * 100);
  const lowConf      = Math.round((metrics.low_confidence_rate ?? 0) * 100);
  const needRev      = Math.round((metrics.need_review_rate ?? 0) * 100);
  const halluc       = Math.round(metrics.hallucination_rate * 100);

  const partialCount = Math.round((metrics.low_confidence_rate ?? 0) * metrics.total_claims);
  const unsupCount   = Math.round(metrics.unsupported_claim_rate * metrics.total_claims);
  const contradCount = metrics.contradiction_count ?? 0;

  const hasIssues = unsupCount > 0 || contradCount > 0;

  return (
    <div className="space-y-0">
      {/* Compact trust status */}
      <div className={`rounded-lg border px-4 py-2.5 flex items-center justify-between flex-wrap gap-2 ${
        hasIssues ? "border-amber-200 bg-amber-50/30" : "border-gray-200 bg-white"
      }`}>
        <div className="flex items-center gap-3 flex-wrap text-xs text-gray-600">
          <span className="font-medium text-gray-700">Độ tin cậy:</span>
          <span>
            <span className={coverage >= 80 ? "text-green-700 font-semibold" : "text-amber-700 font-semibold"}>{coverage}%</span>
            {" "}có nguồn
          </span>
          <span className="text-gray-300">·</span>
          <span>
            <span className={critCoverage >= 80 ? "text-green-700 font-semibold" : "text-amber-700 font-semibold"}>{critCoverage}%</span>
            {" "}thông tin quan trọng có nguồn
          </span>
          {partialCount > 0 && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-amber-600">{partialCount} hỗ trợ một phần</span>
            </>
          )}
          {unsupCount > 0 && (
            <>
              <span className="text-gray-300">·</span>
              <span className="text-amber-600">{unsupCount} chưa có nguồn</span>
            </>
          )}
          <span className="text-gray-300">·</span>
          <span className={contradCount > 0 ? "text-red-600 font-medium" : "text-gray-500"}>
            {contradCount} mâu thuẫn
          </span>
        </div>

        {/* Read mode toggle — inline right side */}
        {readMode && onReadModeChange && (
          <div className="inline-flex rounded-md border border-gray-200 overflow-hidden">
            <button
              onClick={() => onReadModeChange("quick")}
              className={`px-2.5 py-1 text-xs font-medium transition ${
                readMode === "quick"
                  ? "bg-gray-700 text-white"
                  : "bg-white text-gray-500 hover:bg-gray-50"
              }`}
            >
              Đọc nhanh
            </button>
            <button
              onClick={() => onReadModeChange("detail")}
              className={`px-2.5 py-1 text-xs font-medium transition ${
                readMode === "detail"
                  ? "bg-gray-700 text-white"
                  : "bg-white text-gray-500 hover:bg-gray-50"
              }`}
            >
              Chi tiết
            </button>
          </div>
        )}
      </div>

      {/* Technical details — only in tech mode */}
      {techMode && (
        <div className="pt-3 pb-1 space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <TechPill label="Coverage tổng" value={`${coverage}%`} />
            <TechPill label="Coverage critical" value={`${critCoverage}%`} />
            <TechPill label="Claims" value={String(metrics.total_claims)} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <TechPill label="Chưa có nguồn" value={`${unsup}%`} />
            <TechPill label="Tin cậy thấp" value={`${lowConf}%`} />
            <TechPill label="Mâu thuẫn" value={`${halluc}%`} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <TechPill label="Cần xem xét" value={`${needRev}%`} />
            <TechPill label="Latency" value={`${metrics.latency_seconds.toFixed(1)}s`} />
            <TechPill label="Tokens" value={metrics.token_count.toLocaleString()} />
          </div>
        </div>
      )}
    </div>
  );
}
