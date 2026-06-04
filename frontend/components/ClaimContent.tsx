"use client";

import { useRef, useState } from "react";
import type { CitedClaim, ClaimStatus } from "@/lib/types";
import { STATUS_COLORS, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";

// ─── Status → visual maps ────────────────────────────────────────────────────

const STATUS_HIGHLIGHT: Record<ClaimStatus, string> = {
  SUPPORTED:           "bg-green-100 text-green-900",
  PARTIALLY_SUPPORTED: "bg-amber-100  text-amber-900",
  LOW_CONFIDENCE:      "bg-orange-100 text-orange-900",
  UNSUPPORTED:         "bg-red-50     text-red-900",
  NO_CITATION:         "bg-gray-100   text-gray-900",
  CONTRADICTED:        "bg-red-100    text-red-900",
  NEED_REVIEW:         "bg-purple-50  text-purple-900",
};

const STATUS_TOOLTIP_BORDER: Record<ClaimStatus, string> = {
  SUPPORTED:           "border-l-green-400",
  PARTIALLY_SUPPORTED: "border-l-amber-400",
  LOW_CONFIDENCE:      "border-l-orange-400",
  UNSUPPORTED:         "border-l-red-400",
  NO_CITATION:         "border-l-gray-300",
  CONTRADICTED:        "border-l-red-600",
  NEED_REVIEW:         "border-l-purple-400",
};

// ─── Inline citation badge ────────────────────────────────────────────────────

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
  return (
    <button
      // stopPropagation so clicking badge doesn't trigger parent handlers
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => { e.stopPropagation(); onClick(sourceId); }}
      title={`${STATUS_TOOLTIPS[status]}\n${sourceId}`}
      className={`
        inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-mono
        cursor-pointer transition-all hover:scale-105 hover:shadow-sm active:scale-95
        ${STATUS_COLORS[status]}
        ${active ? "ring-2 ring-offset-1 ring-blue-500 shadow-sm" : ""}
      `}
    >
      <span className="font-bold">{STATUS_LABELS[status]}</span>
      <span>{sourceId.split("-").slice(-2).join("-")}</span>
    </button>
  );
}

// ─── Single hoverable claim span ──────────────────────────────────────────────

const FLAG = "[CẦN XÁC NHẬN]";

function ClaimSpan({
  claim,
  activeSourceId,
  onCitationClick,
}: {
  claim: CitedClaim;
  activeSourceId: string | null;
  onCitationClick: (id: string) => void;
}) {
  const [hovered, setHovered]   = useState(false);
  const leaveTimer              = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasCitations = claim.citations.length > 0;
  const isFlagged    = claim.status !== "SUPPORTED";

  const rawText = claim.claim_text.startsWith(FLAG)
    ? claim.claim_text.slice(FLAG.length).trimStart()
    : claim.claim_text;

  // ── Shared hover handlers with a delay so the tooltip stays alive ──────────
  const handleEnter = () => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current);
    if (hasCitations) setHovered(true);
  };
  const handleLeave = () => {
    leaveTimer.current = setTimeout(() => setHovered(false), 150);
  };

  return (
    <span className="relative inline">
      {/* Outer wrapper gets hover handlers + highlight when active */}
      <span
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        className={`
          rounded px-0.5 py-0.5 transition-colors duration-100 cursor-default
          ${hasCitations ? "cursor-help" : ""}
          ${hovered ? STATUS_HIGHLIGHT[claim.status] : ""}
        `}
      >
        {/* Flag badge */}
        {isFlagged && (
          <mark className="bg-yellow-100 text-yellow-800 rounded px-0.5 mr-1 text-sm not-italic font-semibold">
            {FLAG}
          </mark>
        )}
        {rawText}
      </span>

      {/* Citation tooltip — stays alive because it shares the same handlers */}
      {hovered && hasCitations && (
        <span
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
          className={`
            absolute bottom-full left-0 mb-2 z-40
            flex items-center gap-2 flex-wrap
            bg-white rounded-xl shadow-xl
            border border-gray-100 border-l-4 ${STATUS_TOOLTIP_BORDER[claim.status]}
            px-3 py-2.5 whitespace-nowrap
            pointer-events-auto
          `}
        >
          {/* Label */}
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide shrink-0 mr-1">
            Nguồn:
          </span>

          {/* Badges — fully clickable */}
          {claim.citations.map((sid) => (
            <InlineBadge
              key={sid}
              sourceId={sid}
              status={claim.status}
              active={activeSourceId === sid}
              onClick={onCitationClick}
            />
          ))}

          {/* Tooltip arrow (down-pointing triangle) */}
          <span
            className="absolute top-full left-5 -mt-px"
            style={{
              width: 0,
              height: 0,
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "6px solid white",
              filter: "drop-shadow(0 1px 1px rgba(0,0,0,0.08))",
            }}
          />
        </span>
      )}
    </span>
  );
}

// ─── Public component ─────────────────────────────────────────────────────────

const EMPTY_MARKERS = [
  "Chưa thấy ghi nhận",
  "Chưa có nội dung",
  "[LỖI",
];

interface Props {
  content: string;
  citedClaims: CitedClaim[];
  activeSourceId: string | null;
  onCitationClick: (id: string) => void;
  isEmpty: boolean;
}

export default function ClaimContent({
  content,
  citedClaims,
  activeSourceId,
  onCitationClick,
  isEmpty,
}: Props) {
  const hasAnyClaims =
    citedClaims.length > 0 &&
    !EMPTY_MARKERS.some((m) => content.includes(m));

  if (!hasAnyClaims) {
    return (
      <p
        className={`text-base leading-relaxed whitespace-pre-line ${
          isEmpty ? "text-gray-400 italic" : "text-gray-700"
        }`}
      >
        {content || "Chưa có nội dung"}
      </p>
    );
  }

  return (
    <p className="text-base leading-relaxed text-gray-700 whitespace-pre-line">
      {citedClaims.map((claim, i) => (
        <span key={i}>
          <ClaimSpan
            claim={claim}
            activeSourceId={activeSourceId}
            onCitationClick={onCitationClick}
          />
          {i < citedClaims.length - 1 && " "}
        </span>
      ))}
    </p>
  );
}
