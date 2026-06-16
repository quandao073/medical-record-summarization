"use client";

import type { FinalSummary } from "@/lib/types";

interface Props {
  summary: FinalSummary;
}

export default function QuickSummary({ summary }: Props) {
  const overviewSection = summary.sections.find(s => s.section_id === "overview");
  const overviewText = overviewSection?.content ?? "";
  const firstSentences = overviewText.split(/[.!?]\s/).slice(0, 3).join(". ").trim();
  const displayText = firstSentences ? (firstSentences.endsWith(".") ? firstSentences : firstSentences + ".") : null;

  const medsSection = summary.sections.find(s => s.section_id === "current_medications");
  const medCount = medsSection?.cited_claims.filter(c => !c.is_structural).length ?? 0;

  const labsSection = summary.sections.find(s => s.section_id === "abnormal_labs");
  const labCount = labsSection?.cited_claims.filter(c => !c.is_structural).length ?? 0;

  const needsReviewCount = summary.metrics.need_review_count ?? 0;

  if (!displayText && medCount === 0 && labCount === 0) return null;

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
      <h3 className="text-sm font-semibold text-gray-800">Tóm tắt nhanh</h3>
      {displayText && (
        <p className="text-base text-gray-800 leading-relaxed">{displayText}</p>
      )}
      <div className="flex flex-wrap gap-3 text-xs text-gray-500">
        {medCount > 0 && <span>{medCount} thuốc đang dùng</span>}
        {labCount > 0 && (
          <>
            {medCount > 0 && <span className="text-gray-300">·</span>}
            <span>{labCount} xét nghiệm bất thường</span>
          </>
        )}
        <span className="text-gray-300">·</span>
        <span className={needsReviewCount > 0 ? "text-purple-700 font-medium" : ""}>
          {needsReviewCount} thông tin cần bác sĩ kiểm tra
        </span>
      </div>
    </div>
  );
}
