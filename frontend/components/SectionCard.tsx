"use client";

import type { SummarySection } from "@/lib/types";
import { SECTION_ICONS, SECTION_LABELS } from "@/lib/types";
import CitationBadge from "./CitationBadge";
import ClaimContent from "./ClaimContent";
import LabsTable from "./LabsTable";
import MedsTable from "./MedsTable";

interface Props {
  section: SummarySection;
  activeSourceId: string | null;
  onCitationClick: (sourceId: string) => void;
}


export default function SectionCard({
  section,
  activeSourceId,
  onCitationClick,
}: Props) {
  const label = SECTION_LABELS[section.section_id] ?? section.section_id;
  const icon  = SECTION_ICONS[section.section_id] ?? "📄";
  const isAlert = section.section_id === "clinical_alerts";

  // Collect all unique citations from all claims
  const allCitations: Array<{ sourceId: string; status: string }> = [];
  const seen = new Set<string>();
  for (const claim of section.cited_claims) {
    for (const sid of claim.citations) {
      if (!seen.has(sid)) {
        seen.add(sid);
        allCitations.push({ sourceId: sid, status: claim.status });
      }
    }
  }

  const isEmpty =
    !section.content ||
    section.content.includes("Chưa thấy ghi nhận") ||
    section.content.includes("Chưa thấy ghi nhận được xác minh");

  return (
    <div
      className={`rounded-xl border p-5 shadow-sm ${
        isAlert
          ? "border-red-200 bg-red-50"
          : "border-gray-200 bg-white hover:border-blue-200"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">{icon}</span>
        <h2
          className={`font-semibold text-base ${
            isAlert ? "text-red-700" : "text-gray-800"
          }`}
        >
          {label}
        </h2>
        {allCitations.length > 0 && (
          <span className="ml-auto text-xs text-gray-400">
            {allCitations.length} nguồn
          </span>
        )}
      </div>

      {/* Specialised table renderers */}
      {section.section_id === "abnormal_labs" && section.cited_claims.length > 0 ? (
        <LabsTable
          citedClaims={section.cited_claims}
          activeSourceId={activeSourceId}
          onCitationClick={onCitationClick}
        />
      ) : section.section_id === "current_medications" && section.cited_claims.length > 0 ? (
        <MedsTable
          citedClaims={section.cited_claims}
          activeSourceId={activeSourceId}
          onCitationClick={onCitationClick}
        />
      ) : (
        <>
          {/* Default: claim-aware content with hover citations */}
          <ClaimContent
            content={section.content}
            citedClaims={section.cited_claims}
            activeSourceId={activeSourceId}
            onCitationClick={onCitationClick}
            isEmpty={isEmpty}
          />

          {/* Citation badges row — fallback for sections with no structured claims */}
          {allCitations.length > 0 && section.cited_claims.length === 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-100">
              {allCitations.map(({ sourceId, status }) => (
                <CitationBadge
                  key={sourceId}
                  sourceId={sourceId}
                  status={status as import("@/lib/types").ClaimStatus}
                  active={activeSourceId === sourceId}
                  onClick={onCitationClick}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
