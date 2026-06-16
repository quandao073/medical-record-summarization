"use client";

import { useState } from "react";

interface Props {
  summaryStatus: "draft" | "confirmed";
  confirmedAt: string | null;
  onSaveDraft: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onFeedback: (text: string) => Promise<void>;
  onOpenHumanEval?: () => void;
}

export default function SummaryActionBar({
  summaryStatus,
  confirmedAt,
  onSaveDraft,
  onConfirm,
  onFeedback,
  onOpenHumanEval,
}: Props) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      await onSaveDraft();
      showToast("Đã lưu bản nháp");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    if (!window.confirm("Xác nhận bản tóm tắt này? Sau khi xác nhận, bản tóm tắt sẽ được đánh dấu là đã được bác sĩ duyệt.")) return;
    setSaving(true);
    try {
      await onConfirm();
      showToast("Đã xác nhận bản tóm tắt");
    } finally {
      setSaving(false);
    }
  };

  const handleFeedback = async () => {
    if (!feedbackText.trim()) return;
    setSaving(true);
    try {
      await onFeedback(feedbackText.trim());
      setFeedbackText("");
      setFeedbackOpen(false);
      setFeedbackSent(true);
      showToast("Đã gửi góp ý");
    } finally {
      setSaving(false);
    }
  };

  const isConfirmed = summaryStatus === "confirmed";

  return (
    <>
      {/* Toast */}
      {toast && (
        <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-[60] px-3 py-1.5 bg-gray-800 text-white text-xs rounded-lg shadow">
          {toast}
        </div>
      )}

      {/* Feedback panel */}
      {feedbackOpen && (
        <div className="fixed bottom-10 left-0 right-0 z-[51] bg-white border-t border-gray-200 p-3">
          <div className="max-w-5xl mx-auto space-y-2">
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value.slice(0, 500))}
              maxLength={500}
              rows={2}
              placeholder="Bác sĩ có góp ý gì về bản tóm tắt này?"
              className="w-full text-sm border border-gray-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-1 focus:ring-gray-300 bg-white"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">{feedbackText.length}/500</span>
              <div className="flex gap-2">
                <button
                  onClick={() => { setFeedbackOpen(false); setFeedbackText(""); }}
                  className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1"
                >
                  Hủy
                </button>
                <button
                  onClick={handleFeedback}
                  disabled={!feedbackText.trim() || saving}
                  className="text-xs px-3 py-1 rounded-lg bg-gray-700 text-white font-medium hover:bg-gray-800 disabled:opacity-40 transition"
                >
                  Gửi
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sticky bar */}
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 print:hidden">
        <div className="max-w-5xl mx-auto px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {onOpenHumanEval && (
              <button
                onClick={onOpenHumanEval}
                className="text-xs text-gray-500 hover:text-gray-700 transition"
              >
                Đánh giá
              </button>
            )}
            <button
              onClick={() => setFeedbackOpen(o => !o)}
              className="text-xs text-gray-500 hover:text-gray-700 transition"
            >
              Góp ý{feedbackSent ? " (đã gửi)" : ""}
            </button>
          </div>

          <div className="flex items-center gap-2">
            {isConfirmed ? (
              <span className="text-xs text-gray-500">
                Đã xác nhận
                {confirmedAt && (
                  <span className="text-gray-400 ml-1">
                    · {new Date(confirmedAt).toLocaleString("vi-VN")}
                  </span>
                )}
              </span>
            ) : (
              <>
                <button
                  onClick={handleSaveDraft}
                  disabled={saving}
                  className="px-3 py-1 text-xs rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition"
                >
                  Lưu nháp
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={saving}
                  className="px-3 py-1 text-xs rounded-lg bg-gray-800 text-white font-medium hover:bg-gray-900 disabled:opacity-40 transition"
                >
                  Xác nhận tóm tắt
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
