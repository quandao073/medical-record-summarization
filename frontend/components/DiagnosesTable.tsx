"use client";

import { useEffect, useState } from "react";
import type { CitedClaim, ClaimStatus, SourceChunk } from "@/lib/types";
import { STATUS_TOOLTIPS } from "@/lib/types";
import { getSources } from "@/lib/api";

// ─── Diagnosis type labels ────────────────────────────────────────────────────

const DX_TYPE: Record<string, { text: string; cls: string }> = {
  primary:      { text: "Chính",       cls: "bg-red-50 text-red-600 border border-red-100" },
  comorbidity:  { text: "Bệnh kèm",    cls: "bg-gray-100 text-gray-600 border border-gray-200" },
  complication: { text: "Biến chứng",  cls: "bg-amber-50 text-amber-600 border border-amber-100" },
};

const DX_TYPE_ORDER: Record<string, number> = {
  primary: 0, comorbidity: 1, complication: 2,
};

// ─── Inline citation badge ────────────────────────────────────────────────────

function InlineBadge({
  sourceId, status, active, onClick,
}: {
  sourceId: string; status: ClaimStatus; active: boolean; onClick: (id: string) => void;
}) {
  const isOk = status === "SUPPORTED";
  return (
    <button
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => { e.stopPropagation(); onClick(sourceId); }}
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

function SkeletonRow() {
  return (
    <tr>
      {[18, 55, 15, 22, 18].map((w, i) => (
        <td key={i} className="px-3 py-2.5">
          <div className="skeleton h-3 rounded" style={{ width: `${w}%` }} />
        </td>
      ))}
    </tr>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface DxRow {
  chunk: SourceChunk;
  status: ClaimStatus;
}

interface Props {
  citedClaims: CitedClaim[];
  activeSourceId: string | null;
  onCitationClick: (sourceId: string) => void;
}

export default function DiagnosesTable({ citedClaims, activeSourceId, onCitationClick }: Props) {
  const [rows, setRows]       = useState<DxRow[]>([]);
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
      const result: DxRow[] = [];
      chunks.forEach((chunk, i) => {
        const sid = Array.from(idToStatus.keys())[i];
        if (chunk && chunk.source_type === "diagnoses") {
          result.push({ chunk, status: idToStatus.get(sid)! });
        }
      });

      // Sort: primary → comorbidity → complication → others; then by diagnosis_name
      result.sort((a, b) => {
        const ta = DX_TYPE_ORDER[a.chunk.metadata.diagnosis_type as string ?? ""] ?? 9;
        const tb = DX_TYPE_ORDER[b.chunk.metadata.diagnosis_type as string ?? ""] ?? 9;
        if (ta !== tb) return ta - tb;
        const na = (a.chunk.metadata.diagnosis_name as string ?? "").toLowerCase();
        const nb = (b.chunk.metadata.diagnosis_name as string ?? "").toLowerCase();
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
            <th className="px-3 py-2 text-left font-medium w-28">Loại</th>
            <th className="px-3 py-2 text-left font-medium">Chẩn đoán</th>
            <th className="px-3 py-2 text-left font-medium w-24">ICD-10</th>
            <th className="px-3 py-2 text-left font-medium w-28">Ngày ghi nhận</th>
            <th className="px-3 py-2 text-center font-medium w-16">Nguồn</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => <SkeletonRow key={i} />)
            : rows.map(({ chunk, status }) => {
                const m         = chunk.metadata;
                const dxType    = (m.diagnosis_type as string) ?? "";
                const dxName    = (m.diagnosis_name as string) ?? chunk.source_id;
                const icd       = (m.icd10_code as string) ?? "—";
                const isActive  = activeSourceId === chunk.source_id;
                const typeLabel = DX_TYPE[dxType] ?? { text: dxType || "Khác", cls: "bg-gray-100 text-gray-600 border border-gray-300" };

                return (
                  <tr
                    key={chunk.source_id}
                    className={`transition-colors ${isActive ? "bg-blue-50" : "hover:bg-gray-50"}`}
                  >
                    {/* Loại */}
                    <td className="px-3 py-2.5">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${typeLabel.cls}`}>
                        {typeLabel.text}
                      </span>
                    </td>
                    {/* Tên bệnh */}
                    <td className="px-3 py-2.5 text-gray-800 font-medium">{dxName}</td>
                    {/* ICD-10 */}
                    <td className="px-3 py-2.5">
                      <span className="font-mono text-xs text-gray-500">
                        {icd}
                      </span>
                    </td>
                    {/* Ngày ghi nhận */}
                    <td className="px-3 py-2.5 text-gray-500 text-xs">
                      {chunk.date ?? <span className="text-gray-300">—</span>}
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
