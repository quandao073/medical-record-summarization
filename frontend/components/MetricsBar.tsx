import type { SummaryMetrics } from "@/lib/types";

interface Props {
  metrics: SummaryMetrics;
  fromCache: boolean;
  model: string;
}

function Pill({
  label,
  value,
  color,
  subLabel,
}: {
  label: string;
  value: string;
  color: string;
  subLabel?: string;
}) {
  return (
    <div className="flex flex-col items-center px-4 py-2 rounded-lg bg-white border border-gray-200 shadow-sm min-w-[110px]">
      <span className={`text-xl font-bold ${color}`}>{value}</span>
      <span className="text-xs text-gray-500 mt-0.5 text-center leading-tight">{label}</span>
      {subLabel && (
        <span className="text-xs text-gray-400 mt-0.5 text-center">{subLabel}</span>
      )}
    </div>
  );
}

function Divider() {
  return <div className="w-px bg-blue-100 self-stretch mx-1" />;
}

export default function MetricsBar({ metrics, fromCache, model }: Props) {
  const coverage      = Math.round(metrics.citation_coverage * 100);
  const critCoverage  = Math.round((metrics.critical_citation_coverage ?? 0) * 100);
  const unsup         = Math.round(metrics.unsupported_claim_rate * 100);
  const lowConf       = Math.round((metrics.low_confidence_rate ?? 0) * 100);
  const needRev       = Math.round((metrics.need_review_rate ?? 0) * 100);
  const halluc        = Math.round(metrics.hallucination_rate * 100);

  const coverageColor = coverage >= 70 ? "text-green-600" : coverage >= 40 ? "text-yellow-600" : "text-red-600";
  const critColor     = critCoverage >= 80 ? "text-green-600" : critCoverage >= 50 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-blue-800">Pipeline Metrics</h3>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="px-2 py-0.5 rounded bg-gray-100 font-mono">{model}</span>
          {fromCache && (
            <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-700">từ cache</span>
          )}
        </div>
      </div>

      {/* Metrics row */}
      <div className="flex flex-wrap gap-3 items-stretch">

        {/* Coverage group */}
        <Pill label="Coverage tổng"     value={`${coverage}%`}     color={coverageColor} />
        <Pill
          label="Coverage critical"
          value={`${critCoverage}%`}
          color={critColor}
          subLabel={metrics.total_critical_claims ? `${metrics.total_critical_claims} claims` : undefined}
        />

        <Divider />

        {/* Problem rates */}
        <Pill
          label="Chưa có nguồn"
          value={`${unsup}%`}
          color={unsup === 0 ? "text-green-600" : unsup <= 15 ? "text-yellow-600" : "text-red-600"}
        />
        <Pill
          label="Tin cậy thấp"
          value={`${lowConf}%`}
          color={lowConf === 0 ? "text-green-600" : lowConf <= 30 ? "text-amber-600" : "text-orange-600"}
        />
        <Pill
          label="Cần xem xét"
          value={`${needRev}%`}
          color={needRev === 0 ? "text-green-600" : "text-purple-600"}
        />
        <Pill
          label="Mâu thuẫn"
          value={`${halluc}%`}
          color={halluc === 0 ? "text-green-600" : "text-red-600"}
        />

        <Divider />

        {/* Performance */}
        <Pill label="Claims"   value={String(metrics.total_claims)}            color="text-gray-700" />
        <Pill label="Latency"  value={`${metrics.latency_seconds.toFixed(1)}s`} color="text-gray-700" />
        <Pill label="Tokens"   value={metrics.token_count.toLocaleString()}     color="text-gray-700" />
      </div>
    </div>
  );
}
