"use client";

import type { SummarySection } from "@/lib/types";
import { SECTION_ICONS, SECTION_LABELS } from "@/lib/types";
import CitationBadge from "./CitationBadge";
import ClaimContent from "./ClaimContent";
import DiagnosesTable from "./DiagnosesTable";
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

  // Claim status breakdown for the header chip
  const claims = section.cited_claims.filter(c => !c.is_structural);
  const nSupported      = claims.filter(c => c.status === "SUPPORTED").length;
  const nNeedsAttention = claims.filter(c =>
    ["NEED_REVIEW", "NO_CITATION", "UNSUPPORTED", "CONTRADICTED"].includes(c.status)
  ).length;
  const nLowConf = claims.filter(c =>
    ["PARTIALLY_SUPPORTED", "LOW_CONFIDENCE"].includes(c.status)
  ).length;

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
        {claims.length > 0 && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-gray-400 flex-wrap justify-end">
            <span className="text-gray-400">{allCitations.length} nguồn</span>
            {nSupported > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200 font-medium whitespace-nowrap">
                {nSupported} đã có nguồn
              </span>
            )}
            {nLowConf > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 font-medium whitespace-nowrap">
                {nLowConf} hỗ trợ một phần
              </span>
            )}
            {nNeedsAttention > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200 font-medium whitespace-nowrap">
                {nNeedsAttention} cần xem lại
              </span>
            )}
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
      ) : section.section_id === "diagnoses" && section.cited_claims.length > 0 ? (
        <DiagnosesTable
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
            sectionId={section.section_id}
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
