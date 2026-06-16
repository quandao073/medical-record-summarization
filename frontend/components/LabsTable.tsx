"use client";

import { useEffect, useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { STATUS_TOOLTIPS } from "@/lib/types";
import { getSources } from "@/lib/api";

// ─── Value position indicator ────────────────────────────────────────────────

type Interp = "high" | "low" | "normal" | "critical" | string | null;

const INTERP_STYLE: Record<string, { text: string; arrow: string; justify: string }> = {
  high:     { text: "text-red-600 font-semibold",   arrow: "↑", justify: "justify-end"    },
  critical: { text: "text-red-800 font-bold",        arrow: "⚠", justify: "justify-end"    },
  low:      { text: "text-blue-600 font-semibold",  arrow: "↓", justify: "justify-start"  },
  normal:   { text: "text-green-700",               arrow: "→", justify: "justify-center" },
};

/** Shows only the numeric value + direction arrow, no unit. */
function LabValue({
  value,
  interpretation,
}: {
  value: number | null;
  interpretation: Interp;
}) {
  const key = interpretation && interpretation in INTERP_STYLE ? interpretation : "normal";
  const { text, arrow, justify } = INTERP_STYLE[key];
  const display = value !== null && value !== undefined ? String(value) : "—";

  return (
    <div className={`flex items-center gap-1 ${justify}`}>
      <span className={`${text} font-mono text-sm`}>
        {arrow} {display}
      </span>
    </div>
  );
}

// ─── Inline citation badge (minimal, no separate component needed) ────────────

function InlineBadge({
  sourceId,
  status,
  active,
  onClick,
}: {
  sourceId: string;
  status: ClaimStatus;
  active: boolean;
  onClick: (id: string) => void;
}) {
  const isOk = status === "SUPPORTED";
  return (
    <button
      onClick={() => onClick(sourceId)}
      title={`${STATUS_TOOLTIPS[status]}\nClick để xem nguồn trong hồ sơ`}
      className={`text-xs underline transition-colors ${
        active
          ? "text-blue-600"
          : isOk
          ? "text-gray-400 hover:text-gray-600"
          : "text-amber-600 hover:text-amber-800"
      }`}
    >
      {isOk ? "Xem" : "⚠ Xem"}
    </button>
  );
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr>
      {[50, 20, 18, 40, 25, 28, 30, 18].map((w, i) => (
        <td key={i} className="px-3 py-2.5">
          <div className="skeleton h-3 rounded" style={{ width: `${w}%` }} />
        </td>
      ))}
    </tr>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  citedClaims: CitedClaim[];
  activeSourceId: string | null;
  onCitationClick: (sourceId: string) => void;
}

interface LabRow {
  chunk: SourceChunk;
  status: ClaimStatus;
  prevValue?: number | null;   // previous encounter value for trend display
  prevDate?: string | null;
}

export default function LabsTable({ citedClaims, activeSourceId, onCitationClick }: Props) {
  const [rows, setRows]       = useState<LabRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Collect unique source_ids preserving first-seen status
    const idToStatus = new Map<string, ClaimStatus>();
    for (const claim of citedClaims) {
      for (const sid of claim.citations) {
        if (!idToStatus.has(sid)) {
          idToStatus.set(sid, claim.status);
        }
      }
    }

    if (idToStatus.size === 0) {
      setLoading(false);
      return;
    }

    getSources(Array.from(idToStatus.keys())).then((chunks) => {
      const labChunks: Array<{ chunk: SourceChunk; status: ClaimStatus }> = [];
      chunks.forEach((chunk, i) => {
        const sid = Array.from(idToStatus.keys())[i];
        if (chunk && chunk.source_type === "labs") {
          labChunks.push({ chunk, status: idToStatus.get(sid)! });
        }
      });

      // Sort descending by date so [0] = latest
      labChunks.sort((a, b) => (b.chunk.date ?? "").localeCompare(a.chunk.date ?? ""));

      // Group by test_name — keep latest as main row, previous as trend source
      const byTest = new Map<string, typeof labChunks>();
      for (const row of labChunks) {
        const name = (row.chunk.metadata.test_name as string ?? row.chunk.source_id).toLowerCase();
        if (!byTest.has(name)) byTest.set(name, []);
        byTest.get(name)!.push(row);
      }

      // One result row per test: latest value + optional previous for trend
      const result: LabRow[] = [];
      Array.from(byTest.values()).forEach((group) => {
        const latest = group[0];
        const prev   = group[1] ?? null;
        result.push({
          chunk:     latest.chunk,
          status:    latest.status,
          prevValue: prev ? (prev.chunk.metadata.value as number | null) : undefined,
          prevDate:  prev ? prev.chunk.date : undefined,
        });
      });

      // Final sort: by test_name alphabetically
      result.sort((a, b) => {
        const na = (a.chunk.metadata.test_name as string ?? "").toLowerCase();
        const nb = (b.chunk.metadata.test_name as string ?? "").toLowerCase();
        return na.localeCompare(nb, "vi");
      });

      setRows(result);
      setLoading(false);
    });
  }, [citedClaims]);

  if (!loading && rows.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-3 py-2 text-left font-medium">Xét nghiệm</th>
            <th className="px-3 py-2 text-center font-medium w-28">Kết quả</th>
            <th className="px-3 py-2 text-left font-medium w-24">Đơn vị</th>
            <th className="px-3 py-2 text-left font-medium">Ngưỡng tham chiếu</th>
            <th className="px-3 py-2 text-left font-medium w-28">Ngày</th>
            <th className="px-3 py-2 text-left font-medium w-32">Xu hướng</th>
            <th className="px-3 py-2 text-left font-medium w-36">Nhận xét</th>
            <th className="px-3 py-2 text-center font-medium w-16">Nguồn</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
            : rows.map(({ chunk, status, prevValue, prevDate }) => {
                const m        = chunk.metadata;
                const val      = m.value as number | null;
                const unit     = (m.unit as string | null) || null;
                const interp   = m.interpretation as Interp;
                const testName = (m.test_name as string) ?? chunk.source_id;
                const isActive = activeSourceId === chunk.source_id;

                // reference_range: prefer metadata, fallback parse content
                let refRange = (m.reference_range as string) || null;
                if (!refRange) {
                  const match = chunk.content.match(/\(tham chiếu:\s*([^)]+)\)/);
                  refRange = match ? match[1].trim() : null;
                }

                // Clinical interpretation note
                let clinicalNote = "";
                const interpLower = (interp ?? "").toString().toLowerCase();
                if (interpLower === "critical") {
                  clinicalNote = "Nguy hiểm";
                } else if (interpLower === "high") {
                  if (prevValue !== undefined && prevValue !== null && val !== null && val < prevValue) {
                    clinicalNote = "Cao, đã cải thiện";
                  } else {
                    clinicalNote = "Cao, cần theo dõi";
                  }
                } else if (interpLower === "low") {
                  clinicalNote = "Thấp, cần theo dõi";
                } else if (interpLower === "normal") {
                  clinicalNote = "Bình thường";
                }

                // Trend: compare current vs previous value
                let trendNode: React.ReactNode = <span className="text-gray-300 text-xs">—</span>;
                if (prevValue !== undefined && prevValue !== null && val !== null) {
                  const diff = val - prevValue;
                  const improved = diff < 0;
                  const arrow = diff < 0 ? "↓" : diff > 0 ? "↑" : "→";
                  const color = diff === 0
                    ? "text-gray-500"
                    : improved ? "text-green-600" : "text-orange-600";
                  trendNode = (
                    <span className={`text-xs font-mono ${color}`} title={prevDate ?? undefined}>
                      {prevValue} {arrow} {val}
                    </span>
                  );
                }

                return (
                  <tr
                    key={chunk.source_id}
                    className={`transition-colors ${isActive ? "bg-blue-50" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-3 py-2.5 text-gray-800 font-medium">{testName}</td>
                    <td className="px-3 py-2.5">
                      <LabValue value={val} interpretation={interp} />
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 font-mono text-xs">
                      {unit ?? <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 font-mono text-xs">
                      {refRange ?? <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 text-xs">{chunk.date ?? "—"}</td>
                    <td className="px-3 py-2.5">{trendNode}</td>
                    <td className="px-3 py-2.5">
                      {clinicalNote ? (
                        <span className={`text-xs font-medium ${
                          interpLower === "critical" ? "text-red-700" :
                          interpLower === "high" ? "text-orange-600" :
                          interpLower === "low" ? "text-blue-600" :
                          "text-green-600"
                        }`}>
                          {clinicalNote}
                        </span>
                      ) : (
                        <span className="text-gray-300 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <InlineBadge
                        sourceId={chunk.source_id}
                        status={status}
                        active={isActive}
                        onClick={onCitationClick}
                      />
                    </td>
                  </tr>
                );
              })}
        </tbody>
      </table>
    </div>
  );
}
