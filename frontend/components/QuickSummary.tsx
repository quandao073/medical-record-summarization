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
    <div className="rounded-xl border-l-4 border-l-blue-400 border border-gray-200 bg-blue-50/30 p-4 space-y-2">
      <h3 className="text-sm font-semibold text-blue-800">Tóm tắt nhanh</h3>
      {displayText && (
        <p className="text-base text-gray-800 leading-relaxed">{displayText}</p>
      )}
      <div className="flex flex-wrap gap-4 text-sm text-gray-600">
        {medCount > 0 && <span>💊 {medCount} thuốc đang dùng</span>}
        {labCount > 0 && <span>🧪 {labCount} xét nghiệm bất thường</span>}
        <span className={needsReviewCount > 0 ? "text-purple-700 font-medium" : ""}>
          🔍 {needsReviewCount} thông tin cần bác sĩ kiểm tra
        </span>
      </div>
    </div>
  );
}
