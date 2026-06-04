"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FinalSummary, SourceChunk } from "@/lib/types";
import {
  checkHealth,
  clearCache,
  getPatients,
  getSource,
  summarize,
} from "@/lib/api";
import MetricsBar from "@/components/MetricsBar";
import SectionCard from "@/components/SectionCard";
import SourcePanel from "@/components/SourcePanel";

// ─── Loading skeleton ────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm space-y-3">
      <div className="flex items-center gap-2">
        <div className="skeleton w-6 h-6 rounded-full" />
        <div className="skeleton h-4 w-40 rounded" />
      </div>
      <div className="space-y-2">
        <div className="skeleton h-3 w-full rounded" />
        <div className="skeleton h-3 w-5/6 rounded" />
        <div className="skeleton h-3 w-4/6 rounded" />
      </div>
    </div>
  );
}

// ─── Main page ───────────────────────────────────────────────────────────────
export default function HomePage() {
  // ─ Server status
  const [serverOk, setServerOk] = useState<boolean | null>(null);

  // ─ Controls
  const [patients, setPatients]   = useState<string[]>([]);
  const [patient, setPatient]     = useState("P001");
  const [model, setModel]         = useState("gpt-4o-mini");

  // ─ Pipeline state
  const [summary, setSummary]     = useState<FinalSummary | null>(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [aborted, setAborted]     = useState(false);
  const [stageIdx, setStageIdx]   = useState(0);
  const intervalRef               = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─ Last request snapshot — for retry (not tied to current selectors)
  const [lastRequest, setLastRequest] = useState<{ patient: string; model: string } | null>(null);

  // ─ Flag bad output
  const [flagOpen, setFlagOpen]         = useState(false);
  const [flagText, setFlagText]         = useState("");
  const [flagSubmitted, setFlagSubmitted] = useState(false);

  // ─ Source panel
  const [activeId, setActiveId]   = useState<string | null>(null);
  const [chunk, setChunk]         = useState<SourceChunk | null>(null);
  const [chunkLoading, setChunkLoading] = useState(false);
  const [chunkError, setChunkError]     = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const PIPELINE_STAGES = [
    "C1: Xử lý EHR...",
    "C2: Tạo chunks...",
    "C3: Lọc nguồn theo section...",
    "LLM: Tóm tắt 9 sections...",
    "C5/C6: Xác minh nguồn gốc...",
  ];

  // ─ Init: health check + patient list
  useEffect(() => {
    checkHealth().then(setServerOk);
    getPatients().then((p) => {
      setPatients(p);
      if (p.length > 0) setPatient(p[0]);
    });
  }, []);

  // ─ Load source on badge click
  const handleCitationClick = useCallback(async (sourceId: string) => {
    if (activeId === sourceId) {
      setActiveId(null);
      setChunk(null);
      return;
    }
    setActiveId(sourceId);
    setChunk(null);
    setChunkError(null);
    setChunkLoading(true);
    try {
      const c = await getSource(sourceId);
      setChunk(c);
    } catch (e) {
      setChunkError((e as Error).message);
    } finally {
      setChunkLoading(false);
    }
  }, [activeId]);

  // ─ Generate summary (delegates to handleGenerateWith — defined below)
  const handleGenerate = (forceRefresh = false) => {
    handleGenerateWith(patient, model, forceRefresh);
  };

  // ─ Cancel in-flight request
  const handleAbort = () => {
    abortRef.current?.abort();
  };

  // ─ Retry with the exact same patient+model that failed
  const handleRetry = () => {
    if (!lastRequest) return;
    // Override selectors temporarily by calling the inner logic directly
    // We re-use handleGenerate but the snapshot was already saved
    handleGenerateWith(lastRequest.patient, lastRequest.model, false);
  };

  // ─ Internal generate with explicit patient/model (for retry)
  const handleGenerateWith = async (pid: string, mdl: string, forceRefresh: boolean) => {
    abortRef.current = new AbortController();
    setLastRequest({ patient: pid, model: mdl });
    setStageIdx(0);
    setLoading(true);
    setError(null);
    setAborted(false);
    setSummary(null);
    setActiveId(null);
    setChunk(null);
    setFlagOpen(false);
    setFlagText("");
    setFlagSubmitted(false);

    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      setStageIdx((prev) => Math.min(prev + 1, PIPELINE_STAGES.length - 1));
    }, 3000);

    try {
      const result = await summarize(pid, mdl, forceRefresh, abortRef.current.signal);
      setSummary(result);
    } catch (e) {
      const err = e as Error;
      if (err.name === "AbortError") {
        setAborted(true);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  };

  // ─ Flag bad output → localStorage
  const handleFlagSubmit = () => {
    if (!summary || !flagText.trim()) return;
    const entry = {
      patient_id:    summary.patient_id,
      model_version: summary.model_version,
      created_at:    summary.created_at,
      feedback:      flagText.trim(),
      timestamp:     new Date().toISOString(),
    };
    try {
      const existing = JSON.parse(localStorage.getItem("mrs_flagged") ?? "[]") as unknown[];
      localStorage.setItem("mrs_flagged", JSON.stringify([...existing, entry]));
    } catch {
      // localStorage might be unavailable in some envs — silently ignore
    }
    setFlagSubmitted(true);
    setFlagText("");
  };

  // ─ Clear cache
  const handleClearCache = async () => {
    await clearCache(patient);
    setSummary(null);
    setError(null);
    setAborted(false);
  };

  // ─ Server offline banner
  if (serverOk === false) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md text-center bg-white p-8 rounded-2xl shadow border border-red-100">
          <p className="text-4xl mb-4">🔌</p>
          <h2 className="text-xl font-bold text-red-700 mb-2">Backend không phản hồi</h2>
          <p className="text-gray-600 text-sm">
            Khởi động FastAPI trước:
          </p>
          <pre className="mt-3 bg-gray-100 rounded p-3 text-xs text-left font-mono">
            uvicorn api.main:app --reload
          </pre>
        </div>
      </div>
    );
  }

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className={`min-h-screen ${activeId ? "mr-[380px]" : ""} transition-all`}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4 flex-wrap">
          {/* Logo */}
          <div className="flex items-center gap-2 mr-2">
            <span className="text-2xl">🏥</span>
            <div>
              <p className="font-bold text-gray-800 text-sm leading-tight">
                Medical Record Summarization
              </p>
              <p className="text-xs text-gray-400">Citation-grounded PoC</p>
            </div>
          </div>

          {/* Patient selector */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-500 font-medium">Bệnh nhân</label>
            <select
              value={patient}
              onChange={(e) => { setPatient(e.target.value); setSummary(null); }}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              {patients.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          {/* Model selector */}
          <div className="flex items-center gap-1.5">
            <label className="text-xs text-gray-500 font-medium">Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
            >
              <option value="gpt-4o-mini">gpt-4o-mini</option>
              <option value="gpt-4o">gpt-4o</option>
            </select>
          </div>

          {/* Buttons */}
          <div className="flex gap-2 ml-auto">
            <button
              onClick={handleClearCache}
              disabled={loading}
              className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition"
            >
              Xóa cache
            </button>
            <button
              onClick={() => handleGenerate(false)}
              disabled={loading}
              className="px-4 py-1.5 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-40 transition flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Đang tạo...
                </>
              ) : (
                <>▶ Tạo tóm tắt</>
              )}
            </button>

            {/* ■ Hủy — visible ONLY while loading */}
            {loading && (
              <button
                onClick={handleAbort}
                className="px-3 py-1.5 text-sm rounded-lg border border-red-300 text-red-600 hover:bg-red-50 transition font-medium"
              >
                ■ Hủy
              </button>
            )}
            {summary && (
              <button
                onClick={() => handleGenerate(true)}
                disabled={loading}
                className="px-3 py-1.5 text-sm rounded-lg border border-blue-300 text-blue-600 hover:bg-blue-50 disabled:opacity-40 transition"
              >
                Làm mới
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <main className="max-w-5xl mx-auto px-4 py-6 space-y-5">

        {/* Aborted — neutral, not an error */}
        {aborted && !loading && (
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-gray-600 text-sm flex items-center gap-2">
            <span>■</span>
            <span>Đã hủy. Nhấn <strong>Tạo tóm tắt</strong> để thử lại.</span>
          </div>
        )}

        {/* Error + Retry */}
        {error && !loading && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm flex items-start justify-between gap-4">
            <p className="text-red-700">
              <strong>Lỗi:</strong> {error}
            </p>
            {lastRequest && (
              <button
                onClick={handleRetry}
                className="shrink-0 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-medium hover:bg-red-700 transition"
              >
                Thử lại
              </button>
            )}
          </div>
        )}

        {/* Loading — stepped progress */}
        {loading && (
          <>
            <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 space-y-3">
              {/* Current stage label */}
              <div className="flex items-center gap-2 text-blue-700 text-sm font-medium">
                <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
                {PIPELINE_STAGES[stageIdx]}
              </div>

              {/* Progress bar */}
              <div className="w-full bg-blue-100 rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
                  style={{ width: `${((stageIdx + 1) / PIPELINE_STAGES.length) * 100}%` }}
                />
              </div>

              {/* Stage breadcrumbs */}
              <div className="flex gap-2 flex-wrap">
                {PIPELINE_STAGES.map((s, i) => (
                  <span
                    key={s}
                    className={`text-xs px-2 py-0.5 rounded-full transition-colors ${
                      i < stageIdx
                        ? "bg-blue-200 text-blue-700"
                        : i === stageIdx
                        ? "bg-blue-500 text-white font-semibold"
                        : "bg-gray-100 text-gray-400"
                    }`}
                  >
                    {i < stageIdx ? "✓ " : ""}{s.split(":")[0]}
                  </span>
                ))}
              </div>
            </div>

            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </>
        )}

        {/* Empty state */}
        {!loading && !summary && !error && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-5xl mb-4">📋</p>
            <p className="text-lg font-medium text-gray-500">Chọn bệnh nhân và nhấn Tạo tóm tắt</p>
            <p className="text-sm mt-1">
              Pipeline sẽ chạy C1→C2→C3→LLM→C5/C6 và trả về tóm tắt có nguồn gốc xác minh
            </p>
          </div>
        )}

        {/* Summary result */}
        {summary && !loading && (
          <>
            {/* Patient header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-xl font-bold text-gray-800">
                  Tóm tắt bệnh án — {summary.patient_id}
                </h1>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(summary.created_at).toLocaleString("vi-VN")} ·{" "}
                  prompt: {summary.prompt_version}
                </p>
              </div>
              {summary._from_cache && (
                <span className="px-2 py-1 bg-amber-50 text-amber-600 text-xs rounded-full border border-amber-200">
                  Từ cache
                </span>
              )}
            </div>

            {/* Metrics */}
            <MetricsBar
              metrics={summary.metrics}
              fromCache={summary._from_cache ?? false}
              model={summary.model_version}
            />

            {/* Flag bad output */}
            <div className="flex flex-col gap-2">
              {!flagSubmitted ? (
                <>
                  <button
                    onClick={() => setFlagOpen((o) => !o)}
                    className="self-start text-xs text-gray-400 hover:text-orange-600 transition flex items-center gap-1"
                  >
                    ⚑ Báo cáo kết quả sai
                  </button>
                  {flagOpen && (
                    <div className="rounded-xl border border-orange-200 bg-orange-50 p-4 space-y-2">
                      <p className="text-xs text-orange-700 font-medium">
                        Nội dung nào không chính xác?
                      </p>
                      <textarea
                        value={flagText}
                        onChange={(e) => setFlagText(e.target.value.slice(0, 200))}
                        maxLength={200}
                        rows={3}
                        placeholder="Mô tả vấn đề với tóm tắt này..."
                        className="w-full text-sm border border-orange-200 rounded-lg p-2 resize-none focus:outline-none focus:ring-2 focus:ring-orange-300 bg-white"
                      />
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">{flagText.length}/200</span>
                        <div className="flex gap-2">
                          <button
                            onClick={() => { setFlagOpen(false); setFlagText(""); }}
                            className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1"
                          >
                            Hủy
                          </button>
                          <button
                            onClick={handleFlagSubmit}
                            disabled={!flagText.trim()}
                            className="text-xs px-3 py-1.5 rounded-lg bg-orange-500 text-white font-medium hover:bg-orange-600 disabled:opacity-40 transition"
                          >
                            Gửi
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <span className="self-start text-xs px-2 py-1 rounded-full bg-green-100 text-green-700 border border-green-200">
                  ✓ Đã ghi nhận
                </span>
              )}
            </div>

            {/* Hint for citations */}
            <p className="text-xs text-gray-400 italic">
              Hover vào thông tin để xem nguồn gốc dữ liệu. Màu xanh = có nguồn, vàng = khớp một phần, đỏ = chưa xác minh được nguồn.
            </p>

            {/* Sections — clinical_alerts first, then rest */}
            {[
              ...summary.sections.filter((s) => s.section_id === "clinical_alerts"),
              ...summary.sections.filter((s) => s.section_id !== "clinical_alerts"),
            ].map((section) => (
              <SectionCard
                key={section.section_id}
                section={section}
                activeSourceId={activeId}
                onCitationClick={handleCitationClick}
              />
            ))}
          </>
        )}
      </main>

      {/* ── Source panel (right drawer) ─────────────────────────────────────── */}
      <SourcePanel
        sourceId={activeId}
        chunk={chunk}
        loading={chunkLoading}
        error={chunkError}
        onClose={() => { setActiveId(null); setChunk(null); }}
      />
    </div>
  );
}
