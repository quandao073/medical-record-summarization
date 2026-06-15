"use client";

import { useEffect, useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";
import { getSources } from "@/lib/api";


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
  const tooltip = `${STATUS_TOOLTIPS[status]}\n${sourceId}`;
  return (
    <button
      onClick={() => onClick(sourceId)}
      title={tooltip}
      className={`
        px-2 py-0.5 rounded-full text-xs font-mono cursor-pointer
        transition-all hover:opacity-80
        ${STATUS_COLORS[status]}
        ${active ? "ring-2 ring-offset-1 ring-blue-400" : ""}
      `}
    >
      {STATUS_LABELS[status]}
    </button>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {[40, 30, 35, 25, 18].map((w, i) => (
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

interface MedRow {
  chunk: SourceChunk;
  status: ClaimStatus;
}

export default function MedsTable({ citedClaims, activeSourceId, onCitationClick }: Props) {
  const [rows, setRows]       = useState<MedRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const idToStatus = new Map<string, ClaimStatus>();
    for (const claim of citedClaims) {
      for (const sid of claim.citations) {
        if (!idToStatus.has(sid)) idToStatus.set(sid, claim.status);
      }
    }

    if (idToStatus.size === 0) {
      setLoading(false);
      return;
    }

    getSources(Array.from(idToStatus.keys())).then((chunks) => {
      const result: MedRow[] = [];
      chunks.forEach((chunk, i) => {
        const sid = Array.from(idToStatus.keys())[i];
        if (chunk && chunk.source_type === "medications") {
          result.push({ chunk, status: idToStatus.get(sid)! });
        }
      });

      if (result.length === 0) {
        setLoading(false);
        return;
      }

      // Find the latest prescription date across all fetched med chunks
      const latestDate = result.reduce<string>((max, r) => {
        const d = r.chunk.date ?? "";
        return d > max ? d : max;
      }, "");

      // Keep only medications from the latest prescription date (latest encounter)
      const fromLatest = latestDate
        ? result.filter((r) => r.chunk.date === latestDate)
        : result;

      // Sort alphabetically within the latest encounter
      fromLatest.sort((a, b) => {
        const na = (a.chunk.metadata.drug_name as string ?? "").toLowerCase();
        const nb = (b.chunk.metadata.drug_name as string ?? "").toLowerCase();
        return na.localeCompare(nb, "vi");
      });

      setRows(fromLatest);
      setLoading(false);
    });
  }, [citedClaims]);

  if (!loading && rows.length === 0) return null;

  // Prescription date for the header (all rows have the same latest date)
  const prescriptionDate = rows[0]?.chunk.date ?? null;

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      {/* Prescription date header */}
      {prescriptionDate && !loading && (
        <div className="bg-blue-50 border-b border-blue-100 px-3 py-1.5 flex items-center gap-2">
          <span className="text-xs text-blue-600 font-medium">📅 Đơn thuốc ngày:</span>
          <span className="text-xs text-blue-800 font-semibold font-mono">{prescriptionDate}</span>
        </div>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-3 py-2 text-left font-medium">Tên thuốc</th>
            <th className="px-3 py-2 text-left font-medium">Liều dùng</th>
            <th className="px-3 py-2 text-left font-medium">Mục đích</th>
            <th className="px-3 py-2 text-left font-medium w-28">Ngày kê</th>
            <th className="px-3 py-2 text-center font-medium w-16">Nguồn</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
            : rows.map(({ chunk, status }) => {
                const m           = chunk.metadata;
                const drugName    = (m.drug_name as string) ?? chunk.source_id;
                const strength    = (m.strength as string | null)?.trim() || null;
                const dose        = (m.dose as string | null)?.trim();
                const frequency   = (m.frequency as string | null)?.trim();
                const indication  = (m.indication as string | null)?.trim() || null;
                const stopped     = m.is_current === false || frequency === "NGƯNG";
                const isActive    = activeSourceId === chunk.source_id;

                // Liều dùng: merge strength + dose + frequency
                let dosageDisplay = "";
                if (stopped) {
                  dosageDisplay = "NGƯNG";
                } else {
                  const parts = [];
                  if (strength) parts.push(strength);
                  if (dose && dose !== "0") parts.push(dose);
                  if (frequency) parts.push(frequency);
                  dosageDisplay = parts.length > 0 ? parts.join(", ") : "(Thiếu thông tin liều)";
                }

                return (
                  <tr
                    key={chunk.source_id}
                    className={`transition-colors ${
                      isActive ? "bg-blue-50" : stopped ? "bg-gray-50 opacity-60" : "hover:bg-gray-50"
                    }`}
                  >
                    {/* Tên thuốc */}
                    <td className="px-3 py-2.5">
                      <span className={`font-semibold ${stopped ? "line-through text-gray-400" : "text-gray-800"}`}>
                        {drugName}
                      </span>
                    </td>
                    {/* Liều dùng */}
                    <td className="px-3 py-2.5 text-gray-700 text-sm">
                      {stopped
                        ? <span className="text-red-500 font-medium text-xs">NGƯNG</span>
                        : dosageDisplay}
                    </td>
                    {/* Mục đích */}
                    <td className="px-3 py-2.5 text-gray-600 text-sm">
                      {indication ?? <span className="text-gray-300 text-xs">—</span>}
                    </td>
                    {/* Ngày kê */}
                    <td className="px-3 py-2.5 text-gray-400 text-xs font-mono">
                      {chunk.date ?? "—"}
                    </td>
                    {/* Nguồn */}
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
