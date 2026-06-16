"use client";

import { useState, useEffect } from "react";
import type { HumanEval } from "@/lib/types";
import {
  CRITERIA_CONFIG,
  ERROR_CATEGORY_LABELS,
  SCORE_LABELS,
} from "@/lib/types";
import { getHumanEval, submitHumanEval } from "@/lib/api";

interface SummaryMeta {
  generatedAt: string;
  model: string;
  promptVersion: string;
}

interface Props {
  patientId: string;
  isOpen: boolean;
  onClose: () => void;
  summaryMeta: SummaryMeta | null;
}

type CriterionKey = keyof typeof CRITERIA_CONFIG;
type ScoreMap = Record<CriterionKey, { score: number | null; notes: string }>;

function defaultScores(): ScoreMap {
  return Object.fromEntries(
    Object.keys(CRITERIA_CONFIG).map((k) => [k, { score: null, notes: "" }]),
  ) as ScoreMap;
}

function ScoreSelector({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex gap-1 shrink-0">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          title={SCORE_LABELS[n]}
          className={`w-7 h-7 text-xs rounded border transition ${
            value === n
              ? "bg-gray-800 text-white border-gray-800"
              : "border-gray-200 text-gray-500 hover:border-gray-400 hover:text-gray-700"
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

export default function HumanEvalPanel({
  patientId,
  isOpen,
  onClose,
  summaryMeta,
}: Props) {
  const [existingEval, setExistingEval] = useState<HumanEval | null>(null);
  const [evaluator, setEvaluator] = useState("Đào Anh Quân");
  const [scores, setScores] = useState<ScoreMap>(defaultScores());
  const [overallNotes, setOverallNotes] = useState("");
  const [errorCategories, setErrorCategories] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [weightedPreview, setWeightedPreview] = useState<number | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    getHumanEval(patientId)
      .then((data) => {
        setExistingEval(data);
        if (data.evaluated_at) {
          setEvaluator(data.evaluator ?? "Đào Anh Quân");
          setScores(
            Object.fromEntries(
              Object.keys(CRITERIA_CONFIG).map((k) => {
                const s = (data.scores as unknown as Record<string, { score: number | null; notes: string }>)[k];
                return [k, { score: s?.score ?? null, notes: s?.notes ?? "" }];
              }),
            ) as ScoreMap,
          );
          setOverallNotes(data.overall_notes);
          setErrorCategories(data.error_categories);
        } else {
          setEvaluator("Đào Anh Quân");
          setScores(defaultScores());
          setOverallNotes("");
          setErrorCategories([]);
        }
      })
      .catch(() => {
        setExistingEval(null);
        setEvaluator("Đào Anh Quân");
        setScores(defaultScores());
        setOverallNotes("");
        setErrorCategories([]);
      });
  }, [isOpen, patientId]);

  useEffect(() => {
    let total = 0;
    for (const [key, cfg] of Object.entries(CRITERIA_CONFIG)) {
      const s = scores[key as CriterionKey]?.score;
      if (s == null) {
        setWeightedPreview(null);
        return;
      }
      total += s * cfg.weight;
    }
    setWeightedPreview(Math.round(total * 1000) / 1000);
  }, [scores]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleSubmit = async () => {
    if (!evaluator.trim()) {
      showToast("Vui lòng nhập tên người đánh giá.");
      return;
    }
    const allScored = Object.keys(CRITERIA_CONFIG).every(
      (c) => scores[c as CriterionKey]?.score != null,
    );
    if (!allScored) {
      showToast("Vui lòng chấm điểm tất cả 6 tiêu chí trước khi gửi.");
      return;
    }
    setSaving(true);
    try {
      await submitHumanEval(patientId, {
        evaluator: evaluator.trim(),
        summary_generated_at: summaryMeta?.generatedAt ?? null,
        model: summaryMeta?.model ?? null,
        prompt_version: summaryMeta?.promptVersion ?? null,
        scores: scores as Record<string, { score: number; notes: string }>,
        overall_notes: overallNotes,
        error_categories: errorCategories,
      });
      showToast("Đã lưu kết quả đánh giá!");
      const fresh = await getHumanEval(patientId);
      setExistingEval(fresh);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  const isCompleted = existingEval?.evaluated_at != null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/25 z-[55] backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-x-4 top-4 bottom-4 max-w-xl mx-auto z-[56] bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 shrink-0">
          <div>
            <h2 className="font-semibold text-gray-800 text-sm">
              Đánh giá bản tóm tắt — {patientId}
            </h2>
            {summaryMeta && (
              <p className="text-xs text-gray-400 mt-0.5 font-mono">
                {summaryMeta.model} · {summaryMeta.promptVersion} ·{" "}
                {new Date(summaryMeta.generatedAt).toLocaleString("vi-VN")}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-700 w-7 h-7 flex items-center justify-center rounded hover:bg-gray-100 text-lg leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Toast */}
          {toast && (
            <div className="bg-gray-800 text-white text-xs rounded-lg px-3 py-2">
              {toast}
            </div>
          )}

          {/* Evaluator */}
          <div>
            <label className="text-xs text-gray-500 font-medium">
              Người đánh giá
            </label>
            <input
              value={evaluator}
              onChange={(e) => setEvaluator(e.target.value)}
              className="mt-1 w-full text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-gray-300"
            />
          </div>

          {/* Criteria */}
          <div className="space-y-4">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              Tiêu chí đánh giá
            </p>
            {(
              Object.entries(CRITERIA_CONFIG) as [
                CriterionKey,
                (typeof CRITERIA_CONFIG)[CriterionKey],
              ][]
            ).map(([key, cfg]) => (
              <div key={key} className="space-y-1.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-1.5 flex-wrap">
                      <span className="text-sm text-gray-700 font-medium">
                        {cfg.label}
                      </span>
                      <span className="text-xs text-gray-400">
                        ({Math.round(cfg.weight * 100)}%)
                      </span>
                      {scores[key]?.score != null && (
                        <span className="text-xs text-gray-500 font-mono">
                          → {SCORE_LABELS[scores[key].score!]}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5 leading-relaxed">
                      {cfg.description}
                    </p>
                  </div>
                  <ScoreSelector
                    value={scores[key]?.score ?? null}
                    onChange={(v) =>
                      setScores((prev) => ({
                        ...prev,
                        [key]: { ...prev[key], score: v },
                      }))
                    }
                  />
                </div>
                <input
                  value={scores[key]?.notes ?? ""}
                  onChange={(e) =>
                    setScores((prev) => ({
                      ...prev,
                      [key]: { ...prev[key], notes: e.target.value },
                    }))
                  }
                  placeholder="Ghi chú cụ thể (tuỳ chọn)"
                  className="w-full text-xs border border-gray-100 rounded-lg px-2.5 py-1.5 text-gray-600 focus:outline-none focus:ring-1 focus:ring-gray-300 bg-gray-50"
                />
              </div>
            ))}
          </div>

          {/* Error categories */}
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">
              Loại lỗi ghi nhận (nếu có)
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(ERROR_CATEGORY_LABELS).map(([key, label]) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={errorCategories.includes(key)}
                    onChange={(e) =>
                      setErrorCategories((prev) =>
                        e.target.checked
                          ? [...prev, key]
                          : prev.filter((c) => c !== key),
                      )
                    }
                    className="rounded border-gray-300"
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>

          {/* Overall notes */}
          <div>
            <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              Nhận xét tổng thể
            </label>
            <textarea
              value={overallNotes}
              onChange={(e) => setOverallNotes(e.target.value)}
              rows={3}
              placeholder="Nhận xét chung về chất lượng bản tóm tắt..."
              className="mt-1.5 w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-gray-300 resize-none"
            />
          </div>

          {/* Weighted score preview */}
          {weightedPreview !== null && (
            <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <span className="text-xs text-gray-500">Điểm tổng hợp (ước tính)</span>
              <span
                className={`text-lg font-bold ${
                  weightedPreview >= 4
                    ? "text-green-700"
                    : weightedPreview >= 3
                      ? "text-amber-600"
                      : "text-red-600"
                }`}
              >
                {weightedPreview.toFixed(3)}
              </span>
              <span className="text-xs text-gray-400">/ 5.0</span>
              {weightedPreview >= 4.0 && (
                <span className="text-xs text-green-600 font-medium">✓ Đạt mục tiêu</span>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-between shrink-0">
          <span className="text-xs text-gray-400">
            {isCompleted && existingEval
              ? `Đã đánh giá · ${new Date(existingEval.evaluated_at!).toLocaleString("vi-VN")}`
              : "Chưa có đánh giá"}
          </span>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="px-4 py-1.5 text-xs rounded-lg bg-gray-800 text-white font-medium hover:bg-gray-900 disabled:opacity-40 transition"
          >
            {saving
              ? "Đang lưu..."
              : isCompleted
                ? "Cập nhật đánh giá"
                : "Lưu đánh giá"}
          </button>
        </div>
      </div>
    </>
  );
}
