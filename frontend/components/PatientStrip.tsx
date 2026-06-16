"use client";

import type { FinalSummary } from "@/lib/types";

interface Props {
  summary: FinalSummary;
}

function parseOverviewDemographics(text: string): { age: string | null; gender: string | null } {
  const match = text.match(/(Nam|Nữ)[,\s]+(\d+)\s*tuổi/);
  if (match) return { gender: match[1], age: match[2] };
  return { gender: null, age: null };
}

export default function PatientStrip({ summary }: Props) {
  const overviewText = summary.sections.find(s => s.section_id === "overview")?.content ?? "";
  const { age, gender } = parseOverviewDemographics(overviewText);

  const allergySection = summary.sections.find(s => s.section_id === "allergies");
  const hasAllergies =
    allergySection &&
    !allergySection.content.includes("Chưa thấy ghi nhận") &&
    allergySection.cited_claims.filter(c => !c.is_structural).length > 0;
  const allergyCount = hasAllergies
    ? allergySection!.cited_claims.filter(c => !c.is_structural).length
    : 0;

  if (!age && !gender && allergyCount === 0) return null;

  const demographicStr = [gender, age ? `${age} tuổi` : null].filter(Boolean).join(", ");

  return (
    <div className="flex items-center gap-3 text-xs text-gray-500 flex-wrap -mt-2 pb-1">
      {demographicStr && <span>{demographicStr}</span>}
      {allergyCount > 0 && (
        <>
          {demographicStr && <span className="text-gray-300">·</span>}
          <span className="text-amber-600 font-medium">{allergyCount} dị ứng cần lưu ý</span>
        </>
      )}
    </div>
  );
}
