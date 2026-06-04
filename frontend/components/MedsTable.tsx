"use client";

import { useEffect, useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";
import { getSources } from "@/lib/api";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDosage(m: Record<string, unknown>): string {
  const dose      = (m.dose as string | null)?.trim();
  const frequency = (m.frequency as string | null)?.trim();
  const strength  = (m.strength as string | null)?.trim();

  if (!dose && !frequency) return "(Thiếu thông tin liều)";

  const parts: string[] = [];
  if (dose && dose !== "0") parts.push(dose);
  if (frequency && frequency !== "NGƯNG") parts.push(frequency);

  const label = parts.join(", ");

  // Flag stopped medications
  if (frequency === "NGƯNG" || (m.is_current === false)) {
    return `${strength ?? ""} — NGƯNG`.trim();
  }

  return strength ? `${strength} — ${label}` : label;
}

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
      {[55, 65, 24].map((w, i) => (
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

      // Deduplicate by drug_name — keep most recent (first seen after sort desc by date)
      const seen = new Set<string>();
      const deduped: MedRow[] = [];
      result
        .sort((a, b) => (b.chunk.date ?? "").localeCompare(a.chunk.date ?? ""))
        .forEach((row) => {
          const name = (row.chunk.metadata.drug_name as string ?? row.chunk.source_id).toLowerCase();
          if (!seen.has(name)) {
            seen.add(name);
            deduped.push(row);
          }
        });

      // Final sort: alphabetical by drug name for readability
      deduped.sort((a, b) => {
        const na = (a.chunk.metadata.drug_name as string ?? "").toLowerCase();
        const nb = (b.chunk.metadata.drug_name as string ?? "").toLowerCase();
        return na.localeCompare(nb, "vi");
      });

      setRows(deduped);
      setLoading(false);
    });
  }, [citedClaims]);

  if (!loading && rows.length === 0) return null;

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th className="px-3 py-2 text-left font-medium">Tên thuốc</th>
            <th className="px-3 py-2 text-left font-medium">Liều lượng</th>
            <th className="px-3 py-2 text-center font-medium w-16">Nguồn</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
            : rows.map(({ chunk, status }) => {
                const m        = chunk.metadata;
                const drugName = (m.drug_name as string) ?? chunk.source_id;
                const dosage   = formatDosage(m);
                const stopped  = m.is_current === false || (m.frequency as string) === "NGƯNG";
                const isActive = activeSourceId === chunk.source_id;

                return (
                  <tr
                    key={chunk.source_id}
                    className={`transition-colors ${
                      isActive ? "bg-blue-50" : stopped ? "bg-gray-50 opacity-60" : "hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-3 py-2.5">
                      <span className={`font-medium ${stopped ? "line-through text-gray-400" : "text-gray-800"}`}>
                        {drugName}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-gray-600">{dosage}</td>
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
