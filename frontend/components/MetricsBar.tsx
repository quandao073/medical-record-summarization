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
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center px-4 py-2 rounded-lg bg-white border border-gray-200 shadow-sm min-w-[100px]">
      <span className={`text-xl font-bold ${color}`}>{value}</span>
      <span className="text-xs text-gray-500 mt-0.5 text-center">{label}</span>
    </div>
  );
}

export default function MetricsBar({ metrics, fromCache, model }: Props) {
  const coverage = Math.round(metrics.citation_coverage * 100);
  const halluc   = Math.round(metrics.hallucination_rate * 100);
  const unsup    = Math.round(metrics.unsupported_claim_rate * 100);

  const coverageColor =
    coverage >= 70 ? "text-green-600" : coverage >= 40 ? "text-yellow-600" : "text-red-600";

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-blue-800">Pipeline Metrics</h3>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="px-2 py-0.5 rounded bg-gray-100 font-mono">{model}</span>
          {fromCache && (
            <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-700">
              từ cache
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Pill
          label="Citation Coverage"
          value={`${coverage}%`}
          color={coverageColor}
        />
        <Pill
          label="Hallucination Rate"
          value={`${halluc}%`}
          color={halluc === 0 ? "text-green-600" : "text-red-600"}
        />
        <Pill
          label="Unsupported"
          value={`${unsup}%`}
          color={unsup <= 20 ? "text-green-600" : "text-orange-600"}
        />
        <Pill
          label="Total Claims"
          value={String(metrics.total_claims)}
          color="text-gray-700"
        />
        <Pill
          label="Latency"
          value={`${metrics.latency_seconds.toFixed(1)}s`}
          color="text-gray-700"
        />
        <Pill
          label="Tokens"
          value={metrics.token_count.toLocaleString()}
          color="text-gray-700"
        />
      </div>
    </div>
  );
}
