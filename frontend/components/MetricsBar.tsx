import type { SummaryMetrics } from "@/lib/types";

interface Props {
  metrics: SummaryMetrics;
  fromCache: boolean;
  model: string;
  techMode?: boolean;
}

function TrustItem({
  icon,
  label,
  value,
  color,
}: {
  icon: string;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={`text-base ${color}`}>{icon}</span>
      <span className="text-gray-700">
        <span className={`font-semibold ${color}`}>{value}</span> {label}
      </span>
    </div>
  );
}

function TechPill({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col items-center px-3 py-1.5 rounded-lg bg-white border border-gray-200 shadow-sm min-w-[90px]">
      <span className="text-base font-bold text-gray-700">{value}</span>
      <span className="text-xs text-gray-500 mt-0.5 text-center leading-tight">{label}</span>
    </div>
  );
}

export default function MetricsBar({ metrics, fromCache, model, techMode }: Props) {
  const coverage      = Math.round(metrics.citation_coverage * 100);
  const critCoverage  = Math.round((metrics.critical_citation_coverage ?? 0) * 100);
  const unsup         = Math.round(metrics.unsupported_claim_rate * 100);
  const lowConf       = Math.round((metrics.low_confidence_rate ?? 0) * 100);
  const needRev       = Math.round((metrics.need_review_rate ?? 0) * 100);
  const halluc        = Math.round(metrics.hallucination_rate * 100);

  const partialCount  = Math.round((metrics.low_confidence_rate ?? 0) * metrics.total_claims);
  const unsupCount    = Math.round(metrics.unsupported_claim_rate * metrics.total_claims);
  const contradCount  = metrics.contradiction_count ?? 0;

  return (
    <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-emerald-800">
          Độ tin cậy bản tóm tắt
        </h3>
        {techMode && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="px-2 py-0.5 rounded bg-gray-100 font-mono">{model}</span>
            {fromCache && (
              <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-700">từ cache</span>
            )}
          </div>
        )}
      </div>

      {/* Doctor-friendly trust indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <TrustItem
          icon={coverage >= 80 ? "✅" : coverage >= 50 ? "⚠️" : "❌"}
          label="thông tin có nguồn xác nhận"
          value={`${coverage}%`}
          color={coverage >= 80 ? "text-green-600" : coverage >= 50 ? "text-amber-600" : "text-red-600"}
        />
        <TrustItem
          icon={critCoverage >= 80 ? "✅" : critCoverage >= 50 ? "⚠️" : "❌"}
          label="thông tin quan trọng có nguồn xác nhận"
          value={`${critCoverage}%`}
          color={critCoverage >= 80 ? "text-green-600" : critCoverage >= 50 ? "text-amber-600" : "text-red-600"}
        />
        {partialCount > 0 && (
          <TrustItem
            icon="⚠️"
            label="thông tin có nguồn hỗ trợ một phần"
            value={String(partialCount)}
            color="text-amber-600"
          />
        )}
        <TrustItem
          icon={unsupCount === 0 ? "✅" : "⚠️"}
          label="thông tin chưa tìm thấy nguồn"
          value={String(unsupCount)}
          color={unsupCount === 0 ? "text-green-600" : "text-amber-600"}
        />
        <TrustItem
          icon={contradCount === 0 ? "✅" : "❌"}
          label="thông tin có mâu thuẫn"
          value={String(contradCount)}
          color={contradCount === 0 ? "text-green-600" : "text-red-600"}
        />
      </div>

      {/* Technical details — only in tech mode */}
      {techMode && (
        <div className="flex flex-wrap gap-2 pt-2 border-t border-emerald-100">
          <TechPill label="Coverage tổng" value={`${coverage}%`} />
          <TechPill label="Coverage critical" value={`${critCoverage}%`} />
          <TechPill label="Chưa có nguồn" value={`${unsup}%`} />
          <TechPill label="Tin cậy thấp" value={`${lowConf}%`} />
          <TechPill label="Cần xem xét" value={`${needRev}%`} />
          <TechPill label="Mâu thuẫn" value={`${halluc}%`} />
          <TechPill label="Claims" value={String(metrics.total_claims)} />
          <TechPill label="Latency" value={`${metrics.latency_seconds.toFixed(1)}s`} />
          <TechPill label="Tokens" value={metrics.token_count.toLocaleString()} />
        </div>
      )}
    </div>
  );
}
