"use client";

import type { CitedClaim, ClaimStatus, SummarySection } from "@/lib/types";
import { SECTION_LABELS } from "@/lib/types";

const REVIEW_STATUSES: Set<string> = new Set([
  "NEED_REVIEW",
  "UNSUPPORTED",
  "NO_CITATION",
  "CONTRADICTED",
]);

const CLAIM_PREFIXES = [
  "[Hỗ trợ một phần] ", "[Khớp một phần] ", "[Độ tin cậy thấp] ",
  "[Cần xác minh] ", "[Chưa có nguồn] ", "[Cần xem xét] ",
  "[Mâu thuẫn] ", "[CẦN XÁC NHẬN] ", "[Cần kiểm tra] ",
];

function stripPrefix(text: string): string {
  for (const p of CLAIM_PREFIXES) {
    if (text.startsWith(p)) return text.slice(p.length).trimStart();
  }
  return text;
}

const STATUS_ICON: Record<string, string> = {
  NEED_REVIEW:  "🔍",
  UNSUPPORTED:  "❓",
  NO_CITATION:  "➖",
  CONTRADICTED: "❌",
};

const STATUS_LABEL: Record<string, string> = {
  NEED_REVIEW:  "Cần bác sĩ kiểm tra",
  UNSUPPORTED:  "Chưa tìm thấy nguồn",
  NO_CITATION:  "Chưa tìm thấy nguồn trong hồ sơ",
  CONTRADICTED: "Có mâu thuẫn trong hồ sơ",
};

interface ReviewItem {
  claim: CitedClaim;
  sectionId: string;
}

interface Props {
  sections: SummarySection[];
  onCitationClick: (sourceId: string) => void;
}

export default function NeedsReviewSection({ sections, onCitationClick }: Props) {
  const items: ReviewItem[] = [];

  for (const section of sections) {
    for (const claim of section.cited_claims) {
      if (claim.is_structural) continue;
      if (REVIEW_STATUSES.has(claim.status)) {
        items.push({ claim, sectionId: section.section_id });
      }
      if (claim.status === "PARTIALLY_SUPPORTED" && claim.is_critical) {
        items.push({ claim, sectionId: section.section_id });
      }
    }
  }

  return (
    <div className={`rounded-xl border border-gray-200 bg-white p-4 space-y-3 ${items.length > 0 ? "border-l-4 border-l-purple-400" : ""}`}>
      <div className="flex items-center gap-2">
        <h2 className="font-semibold text-sm text-gray-800">Cần bác sĩ kiểm tra</h2>
        {items.length > 0 && (
          <span className="ml-auto text-xs text-purple-600 font-medium">
            {items.length} thông tin
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="text-xs text-gray-500">
          Không có thông tin cần bác sĩ kiểm tra.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item, i) => {
            const icon = STATUS_ICON[item.claim.status] ?? "⚠️";
            const label = STATUS_LABEL[item.claim.status] ?? item.claim.status;
            const sectionName = SECTION_LABELS[item.sectionId] ?? item.sectionId;
            const firstCitation = item.claim.citations[0];

            return (
              <div
                key={i}
                className="rounded-lg border border-gray-100 p-3 space-y-1.5"
              >
                <div className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5 text-sm">{icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800">
                      {stripPrefix(item.claim.claim_text)}
                    </p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-xs text-purple-600 font-medium">{label}</span>
                      <span className="text-xs text-gray-300">·</span>
                      <span className="text-xs text-gray-400">{sectionName}</span>
                      {firstCitation && (
                        <button
                          onClick={() => onCitationClick(firstCitation)}
                          className="text-xs text-blue-600 hover:text-blue-800 hover:underline transition"
                        >
                          Xem nguồn
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
