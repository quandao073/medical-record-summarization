"use client";

import type { ClaimStatus } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";

interface Props {
  sourceId: string;
  status: ClaimStatus;
  active: boolean;
  onClick: (sourceId: string) => void;
}

export default function CitationBadge({
  sourceId,
  status,
  active,
  onClick,
}: Props) {
  const short = sourceId.split("-").slice(-2).join("-");

  const tooltip = `${STATUS_TOOLTIPS[status]}\n${sourceId}`;

  return (
    <button
      onClick={() => onClick(sourceId)}
      title={tooltip}
      className={`
        inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono
        cursor-pointer transition-all hover:opacity-80 hover:scale-105
        ${STATUS_COLORS[status]}
        ${active ? "ring-2 ring-offset-1 ring-blue-400" : ""}
      `}
    >
      <span>{STATUS_LABELS[status]}</span>
      <span>{short}</span>
    </button>
  );
}
