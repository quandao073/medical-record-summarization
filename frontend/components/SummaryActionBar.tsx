"use client";

import { useState } from "react";

interface Props {
  summaryStatus: "draft" | "confirmed";
  confirmedAt: string | null;
  onSaveDraft: () => Promise<void>;
  onConfirm: () => Promise<void>;
  onFeedback: (text: string) => Promise<void>;
}

export default function SummaryActionBar({
  summaryStatus,
  confirmedAt,
  onSaveDraft,
  onConfirm,
  onFeedback,
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
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 bg-green-600 text-white text-sm rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      {/* Feedback panel */}
      {feedbackOpen && (
        <div className="fixed bottom-16 left-0 right-0 z-[51] bg-white border-t border-blue-200 shadow-lg p-4">
          <div className="max-w-5xl mx-auto space-y-2">
            <p className="text-sm font-medium text-gray-700">Góp ý của bác sĩ</p>
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value.slice(0, 500))}
              maxLength={500}
              rows={3}
              placeholder="Bác sĩ có góp ý gì về bản tóm tắt này?"
              className="w-full text-sm border border-blue-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">{feedbackText.length}/500</span>
              <div className="flex gap-2">
                <button
                  onClick={() => { setFeedbackOpen(false); setFeedbackText(""); }}
                  className="text-xs text-gray-500 hover:text-gray-700 px-3 py-1.5"
                >
                  Hủy
                </button>
                <button
                  onClick={handleFeedback}
                  disabled={!feedbackText.trim() || saving}
                  className="text-xs px-4 py-1.5 rounded-lg bg-blue-500 text-white font-medium hover:bg-blue-600 disabled:opacity-40 transition"
                >
                  Gửi góp ý
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sticky bar */}
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 shadow-[0_-2px_10px_rgba(0,0,0,0.05)]">
        <div className="max-w-5xl mx-auto px-4 py-2.5 flex items-center justify-between">
          <button
            onClick={() => setFeedbackOpen(o => !o)}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium transition flex items-center gap-1"
          >
            Góp ý về bản tóm tắt
            {feedbackSent && <span className="text-xs text-green-600 ml-1">(đã gửi)</span>}
          </button>

          <div className="flex items-center gap-3">
            {isConfirmed ? (
              <span className="text-sm text-green-700 font-medium flex items-center gap-1">
                Đã xác nhận
                {confirmedAt && (
                  <span className="text-xs text-gray-400 ml-1">
                    ({new Date(confirmedAt).toLocaleString("vi-VN")})
                  </span>
                )}
              </span>
            ) : (
              <>
                <button
                  onClick={handleSaveDraft}
                  disabled={saving}
                  className="px-4 py-1.5 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition font-medium"
                >
                  Lưu bản nháp
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={saving}
                  className="px-4 py-1.5 text-sm rounded-lg bg-green-600 text-white font-medium hover:bg-green-700 disabled:opacity-40 transition"
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
