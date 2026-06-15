"use client";

import { useState } from "react";
import type { ClaimReview, ClaimReviewAction } from "@/lib/types";

interface Props {
  currentReview: ClaimReview | null;
  onReview: (action: ClaimReviewAction, newText?: string) => Promise<void>;
}

const ACTION_BADGES: Record<ClaimReviewAction, { icon: string; text: string; cls: string }> = {
  approved:     { icon: "✓", text: "Đã xác nhận",   cls: "bg-green-50 text-green-700 border-green-200" },
  edited:       { icon: "✏", text: "Đã sửa",        cls: "bg-amber-50 text-amber-700 border-amber-200" },
  needs_review: { icon: "🔍", text: "Cần kiểm tra", cls: "bg-purple-50 text-purple-700 border-purple-200" },
};

export default function ClaimReviewButtons({ currentReview, onReview }: Props) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [reReviewing, setReReviewing] = useState(false);

  const handleAction = async (action: ClaimReviewAction, newText?: string) => {
    setSaving(true);
    try {
      await onReview(action, newText);
      setEditing(false);
      setEditText("");
      setReReviewing(false);
    } finally {
      setSaving(false);
    }
  };

  if (currentReview && !reReviewing) {
    const badge = ACTION_BADGES[currentReview.action];
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${badge.cls}`}>
            {badge.icon} {badge.text}
          </span>
          <button
            onClick={() => setReReviewing(true)}
            disabled={saving}
            className="text-xs text-gray-400 hover:text-gray-600 underline"
          >
            Chỉnh đánh giá
          </button>
        </div>
        {currentReview.action === "edited" && currentReview.new_text && (
          <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1 border border-amber-200">
            Sửa thành: &ldquo;{currentReview.new_text}&rdquo;
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-500">Đánh giá của bác sĩ:</p>
      <div className="flex gap-2">
        <button
          onClick={() => handleAction("approved")}
          disabled={saving}
          className="px-3 py-1.5 text-xs rounded-lg border border-green-300 text-green-700 bg-green-50 hover:bg-green-100 disabled:opacity-40 transition font-medium"
        >
          ✓ Đúng
        </button>
        <button
          onClick={() => { setEditing(true); setEditText(""); }}
          disabled={saving}
          className="px-3 py-1.5 text-xs rounded-lg border border-amber-300 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-40 transition font-medium"
        >
          ✏ Sửa
        </button>
        <button
          onClick={() => handleAction("needs_review")}
          disabled={saving}
          className="px-3 py-1.5 text-xs rounded-lg border border-purple-300 text-purple-700 bg-purple-50 hover:bg-purple-100 disabled:opacity-40 transition font-medium"
        >
          🔍 Cần kiểm tra
        </button>
      </div>
      {editing && (
        <div className="space-y-1.5">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={3}
            placeholder="Nhập nội dung đã sửa..."
            className="w-full text-sm border border-amber-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-2 focus:ring-amber-300 bg-white"
          />
          <div className="flex gap-2">
            <button
              onClick={() => { setEditing(false); setEditText(""); }}
              className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1"
            >
              Hủy
            </button>
            <button
              onClick={() => handleAction("edited", editText)}
              disabled={!editText.trim() || saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-amber-500 text-white font-medium hover:bg-amber-600 disabled:opacity-40 transition"
            >
              Lưu sửa
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
