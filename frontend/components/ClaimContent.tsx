"use client";

import { useRef, useState } from "react";
import type { CitedClaim, ClaimStatus } from "@/lib/types";
import { STATUS_COLORS, STATUS_DISPLAY_NAMES, STATUS_LABELS, STATUS_TOOLTIPS } from "@/lib/types";

// ─── Status → visual maps ────────────────────────────────────────────────────

const STATUS_HIGHLIGHT: Record<ClaimStatus, string> = {
  SUPPORTED:           "bg-green-50   text-green-900",
  PARTIALLY_SUPPORTED: "bg-amber-50   text-amber-900",
  LOW_CONFIDENCE:      "bg-orange-50  text-orange-900",
  UNSUPPORTED:         "bg-red-50     text-red-800",
  NO_CITATION:         "bg-gray-50    text-gray-800",
  CONTRADICTED:        "bg-red-50     text-red-900",
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

// ─── STATUS → inline badge (null = SUPPORTED, no badge needed) ───────────────

/**
 * Inline badge shown BEFORE the claim text for problematic statuses only.
 * PARTIALLY_SUPPORTED and LOW_CONFIDENCE are intentionally omitted here —
 * they get a colored underline (via STATUS_UNDERLINE) but NO inline text badge,
 * to keep the summary readable. Their counts appear in the section header instead.
 */
const CLAIM_BADGE: Partial<Record<ClaimStatus, { text: string; cls: string }>> = {
  // PARTIALLY_SUPPORTED → no badge (only colored underline + hover tooltip)
  // LOW_CONFIDENCE      → no badge (only colored underline + hover tooltip)
  UNSUPPORTED:         { text: "Chưa tìm thấy nguồn",     cls: "bg-red-100 text-red-700 border border-red-300" },
  NO_CITATION:         { text: "Chưa tìm thấy nguồn",     cls: "bg-gray-100 text-gray-600 border border-gray-300" },
  CONTRADICTED:        { text: "Có mâu thuẫn trong hồ sơ", cls: "bg-red-200 text-red-800 border border-red-400" },
  NEED_REVIEW:         { text: "Cần bác sĩ kiểm tra",     cls: "bg-purple-100 text-purple-700 border border-purple-300" },
};

// ─── Single hoverable claim span ──────────────────────────────────────────────

// Known prefixes injected by C6 verifier — strip before display
const KNOWN_PREFIXES = [
  "[CẦN XÁC NHẬN] ",
  "[Hỗ trợ một phần] ",
  "[Khớp một phần] ",      // legacy — strip if still present
  "[Độ tin cậy thấp] ",
  "[Cần xác minh] ",
  "[Chưa có nguồn] ",
  "[Cần xem xét] ",
  "[Mâu thuẫn] ",
  "[Cần kiểm tra] ",
];

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
  const isActive = activeSourceId !== null && claim.citations.includes(activeSourceId);
  const badge = CLAIM_BADGE[claim.status] ?? null;  // null for SUPPORTED

  // Strip any verifier prefix from claim_text before display
  const rawText = (() => {
    let t = claim.claim_text;
    for (const p of KNOWN_PREFIXES) {
      if (t.startsWith(p)) { t = t.slice(p.length).trimStart(); break; }
    }
    return t;
  })();

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
          rounded px-0.5 py-0.5 transition-colors duration-200 cursor-default
          ${hasCitations ? "cursor-help" : ""}
          ${isActive ? "bg-blue-100/80 border-l-2 border-l-blue-600" : ""}
          ${hovered && !isActive ? STATUS_HIGHLIGHT[claim.status] : ""}
        `}
      >
        {/* Status-specific badge — only shown for non-SUPPORTED claims */}
        {badge && (
          <mark className={`rounded px-1.5 py-0.5 mr-1 text-xs not-italic font-medium ${badge.cls}`}>
            {badge.text}
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
          {/* Status label in tooltip — shows "Hỗ trợ một phần" even when no inline badge */}
          <span className={`text-xs font-semibold shrink-0 mr-1 ${
            claim.status === "SUPPORTED" ? "text-green-600" :
            claim.status === "PARTIALLY_SUPPORTED" ? "text-amber-600" :
            claim.status === "LOW_CONFIDENCE" ? "text-orange-600" :
            "text-gray-500"
          }`}>
            {STATUS_DISPLAY_NAMES[claim.status]}:
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
  sectionId?: string;
}

export default function ClaimContent({
  content,
  citedClaims,
  activeSourceId,
  onCitationClick,
  isEmpty,
  sectionId,
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

  // Custom renderer for treatment_timeline — grouped by date
  if (sectionId === "treatment_timeline") {
    const datePattern = /^(\d{1,2}\/\d{1,2}\/\d{4}|\d{4}-\d{2}-\d{2})/;
    const groups: Array<{ date: string; claims: Array<{ claim: CitedClaim; idx: number }> }> = [];
    let currentGroup: typeof groups[number] | null = null;

    citedClaims.forEach((claim, i) => {
      const dateMatch = claim.claim_text.match(datePattern);
      if (dateMatch || (claim.is_structural && claim.claim_text.trim().endsWith(":"))) {
        const dateStr = dateMatch ? dateMatch[1] : claim.claim_text.replace(":", "").trim();
        currentGroup = { date: dateStr, claims: [] };
        groups.push(currentGroup);
        if (!dateMatch) return;
      }
      if (currentGroup) {
        currentGroup.claims.push({ claim, idx: i });
      } else {
        if (!currentGroup) {
          currentGroup = { date: "", claims: [] };
          groups.push(currentGroup);
        }
        currentGroup.claims.push({ claim, idx: i });
      }
    });

    return (
      <div className="space-y-4">
        {groups.map((group, gi) => (
          <div key={gi} className="relative pl-6 border-l-2 border-blue-200">
            {group.date && (
              <div className="flex items-center gap-2 mb-1.5 -ml-[25px]">
                <span className="w-3 h-3 rounded-full bg-blue-500 border-2 border-white shadow-sm shrink-0" />
                <span className="text-sm font-semibold text-blue-700">{group.date}</span>
              </div>
            )}
            <div className="space-y-1 text-base leading-relaxed text-gray-700">
              {group.claims.map(({ claim, idx }) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-gray-400 shrink-0 select-none pt-0.5">•</span>
                  <ClaimSpan
                    claim={claim}
                    activeSourceId={activeSourceId}
                    onCitationClick={onCitationClick}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Custom renderer for medical_history (Tiền sử bệnh)
  if (sectionId === "medical_history") {
    return (
      <div className="space-y-1.5 text-base leading-relaxed text-gray-700">
        {citedClaims.map((claim, i) => {
          const isHeader = claim.is_structural && claim.claim_text.trim().endsWith(":");
          if (isHeader) {
            return (
              <div key={i} className="font-semibold text-gray-800 pt-2 first:pt-0">
                <ClaimSpan
                  claim={claim}
                  activeSourceId={activeSourceId}
                  onCitationClick={onCitationClick}
                />
              </div>
            );
          }
          return (
            <div key={i} className="flex items-start gap-2 pl-4">
              <span className="text-gray-400 shrink-0 select-none pt-0.5">•</span>
              <ClaimSpan
                claim={claim}
                activeSourceId={activeSourceId}
                onCitationClick={onCitationClick}
              />
            </div>
          );
        })}
      </div>
    );
  }

  // Custom renderer for clinical_alerts (Điểm cần lưu ý / Cảnh báo)
  if (sectionId === "clinical_alerts") {
    return (
      <div className="space-y-1.5 text-base leading-relaxed">
        {citedClaims.map((claim, i) => {
          const isHeader = claim.is_structural && claim.claim_text.trim().endsWith(":");
          const isPlaceholder = claim.is_structural && !isHeader;

          if (isHeader) {
            return (
              <div key={i} className="font-semibold text-gray-800 pt-2.5 first:pt-0">
                <ClaimSpan
                  claim={claim}
                  activeSourceId={activeSourceId}
                  onCitationClick={onCitationClick}
                />
              </div>
            );
          } else if (isPlaceholder) {
            return (
              <div key={i} className="pl-4 text-gray-400 italic">
                <ClaimSpan
                  claim={claim}
                  activeSourceId={activeSourceId}
                  onCitationClick={onCitationClick}
                />
              </div>
            );
          } else {
            return (
              <div key={i} className="pl-4 flex items-start gap-2">
                <span className="text-red-400 shrink-0 select-none pt-0.5">•</span>
                <ClaimSpan
                  claim={claim}
                  activeSourceId={activeSourceId}
                  onCitationClick={onCitationClick}
                />
              </div>
            );
          }
        })}
      </div>
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
