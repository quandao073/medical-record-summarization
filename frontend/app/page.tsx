"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CitedClaim, ClaimReviewAction, FinalSummary, ReviewState, SourceChunk } from "@/lib/types";
import {
  checkHealth,
  clearCache,
  getPatients,
  getReviewState,
  getSource,
  submitClaimReview,
  summarize,
} from "@/lib/api";
import MetricsBar from "@/components/MetricsBar";
import NeedsReviewSection from "@/components/NeedsReviewSection";
import SectionCard from "@/components/SectionCard";
import SourcePanel from "@/components/SourcePanel";
import QuickSummary from "@/components/QuickSummary";
import SummaryActionBar from "@/components/SummaryActionBar";
import { submitSummaryStatus, submitFeedback } from "@/lib/api";

// ─── Freshness helper ────────────────────────────────────────────────────────
function summaryFreshness(createdAt: string): { label: string; stale: boolean } {
  const diffMs = Date.now() - new Date(createdAt).getTime();
  const mins = Math.floor(diffMs / 60_000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);

  let label: string;
  if (mins < 5) label = "Vừa tạo";
  else if (mins < 60) label = `Tạo ${mins} phút trước`;
  else if (hours < 24) label = `Tạo ${hours} giờ trước`;
  else label = `Tạo ${days} ngày trước`;

  const stale = hours >= 4;
  if (stale) {
    label += " — nên kiểm tra/làm mới nếu hồ sơ đã thay đổi";
  }
  return { label, stale };
}

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

  // ─ Technical mode toggle
  const [techMode, setTechMode] = useState(false);

  // ─ Review state
  const [reviewState, setReviewState] = useState<ReviewState | null>(null);

  // ─ Read mode
  const [readMode, setReadMode] = useState<"quick" | "detail">("detail");

  // ─ Source panel
  const [activeId, setActiveId]       = useState<string | null>(null);
  const [chunk, setChunk]             = useState<SourceChunk | null>(null);
  const [claimContext, setClaimContext] = useState<CitedClaim | null>(null);
  const [chunkLoading, setChunkLoading] = useState(false);
  const [chunkError, setChunkError]     = useState<string | null>(null);

  // ─ sourceId → CitedClaim map (rebuilt whenever summary changes)
  const sourceToClaimMap = useMemo(() => {
    const map = new Map<string, CitedClaim>();
    if (!summary) return map;
    for (const section of summary.sections) {
      for (const claim of section.cited_claims) {
        for (const sid of claim.citations) {
          if (!map.has(sid)) map.set(sid, claim);
        }
      }
    }
    return map;
  }, [summary]);

  const abortRef = useRef<AbortController | null>(null);

  const PIPELINE_STAGES = techMode
    ? [
        "C1: Xử lý EHR...",
        "C2: Tạo chunks...",
        "C3: Lọc nguồn theo section...",
        "LLM: Tóm tắt 9 sections...",
        "C5/C6: Xác minh nguồn gốc...",
      ]
    : [
        "Đang đọc hồ sơ bệnh nhân...",
        "Đang phân tích dữ liệu...",
        "Đang lọc thông tin theo chuyên mục...",
        "Đang tạo bản tóm tắt...",
        "Đang xác minh nguồn tham chiếu...",
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
      setClaimContext(null);
      return;
    }
    setActiveId(sourceId);
    setChunk(null);
    setClaimContext(sourceToClaimMap.get(sourceId) ?? null);
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
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      setStageIdx((prev) => Math.min(prev + 1, PIPELINE_STAGES.length - 1));
    }, 3000);

    try {
      const result = await summarize(pid, mdl, forceRefresh, abortRef.current.signal);
      setSummary(result);
      getReviewState(pid).then(setReviewState).catch(() => {});
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

  // ─ Clear cache
  const handleClearCache = async () => {
    await clearCache(patient);
    setSummary(null);
    setError(null);
    setAborted(false);
  };

  // ─ Claim ID generation
  function makeClaimId(patientId: string, sectionId: string, claimIndex: number, claimText: string): string {
    const hash = Array.from(claimText).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
    const hashStr = Math.abs(hash).toString(16).slice(0, 5);
    return `${patientId}-${sectionId}-${String(claimIndex).padStart(3, "0")}-${hashStr}`;
  }

  // ─ Claim review handler
  const handleClaimReview = useCallback(async (action: ClaimReviewAction, newText?: string) => {
    if (!summary || !claimContext || !activeId) return;
    const section = summary.sections.find(s =>
      s.cited_claims.some(c => c.citations.includes(activeId!))
    );
    if (!section) return;
    const claimIndex = section.cited_claims.findIndex(c =>
      c.claim_text === claimContext.claim_text && c.citations.includes(activeId!)
    );
    if (claimIndex < 0) return;
    const claimId = makeClaimId(summary.patient_id, section.section_id, claimIndex, claimContext.claim_text);
    await submitClaimReview(summary.patient_id, claimId, section.section_id, claimContext.claim_text, action, newText);
    const updated = await getReviewState(summary.patient_id);
    setReviewState(updated);
  }, [summary, claimContext, activeId]);

  // ─ Current claim's review lookup
  const currentClaimReview = useMemo(() => {
    if (!reviewState || !summary || !claimContext || !activeId) return null;
    const section = summary.sections.find(s =>
      s.cited_claims.some(c => c.citations.includes(activeId!))
    );
    if (!section) return null;
    const claimIndex = section.cited_claims.findIndex(c =>
      c.claim_text === claimContext.claim_text && c.citations.includes(activeId!)
    );
    if (claimIndex < 0) return null;
    const claimId = makeClaimId(summary.patient_id, section.section_id, claimIndex, claimContext.claim_text);
    return reviewState.claim_reviews[claimId] ?? null;
  }, [reviewState, summary, claimContext, activeId]);

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
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200">
        {/* Row 1: Title + actions */}
        <div className="max-w-5xl mx-auto px-4 py-2.5 flex items-center gap-3 flex-wrap">
          <p className="font-bold text-gray-800 text-sm leading-tight">
            Tóm tắt bệnh án thông minh
          </p>

          {/* Patient selector */}
          <select
            value={patient}
            onChange={(e) => { setPatient(e.target.value); setSummary(null); }}
            className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          >
            {patients.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          {/* Tech controls — only in tech mode */}
          {techMode && (
            <>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
              >
                <option value="gpt-4o-mini">gpt-4o-mini</option>
                <option value="gpt-4o">gpt-4o</option>
              </select>
              <button
                onClick={handleClearCache}
                disabled={loading}
                className="px-2.5 py-1 text-xs rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-50 disabled:opacity-40 transition"
              >
                Xóa cache
              </button>
            </>
          )}

          {/* Actions — right side */}
          <div className="flex gap-2 ml-auto items-center">
            <button
              onClick={() => setTechMode((v) => !v)}
              className={`px-2 py-1 text-xs rounded border transition ${
                techMode
                  ? "border-indigo-300 bg-indigo-50 text-indigo-600"
                  : "border-gray-200 text-gray-400 hover:bg-gray-50"
              }`}
              title={techMode ? "Ẩn thông tin kỹ thuật" : "Hiện thông tin kỹ thuật"}
            >
              {techMode ? "Kỹ thuật" : "KT"}
            </button>

            <button
              onClick={() => handleGenerate(false)}
              disabled={loading}
              className="px-3 py-1 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-40 transition flex items-center gap-1.5"
            >
              {loading ? (
                <>
                  <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Đang tạo...
                </>
              ) : (
                "Tạo tóm tắt"
              )}
            </button>
            {loading && (
              <button
                onClick={handleAbort}
                className="px-2.5 py-1 text-xs rounded-lg border border-red-300 text-red-600 hover:bg-red-50 transition font-medium"
              >
                Hủy
              </button>
            )}
            {summary && !loading && (
              <button
                onClick={() => handleGenerate(true)}
                disabled={loading}
                className="px-2.5 py-1 text-xs rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition"
              >
                Làm mới
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Patient info + status (only when summary exists) */}
        {summary && !loading && (
          <div className="max-w-5xl mx-auto px-4 pb-2 flex items-center gap-3 text-xs text-gray-500 flex-wrap">
            <span className="font-medium text-gray-700">Bệnh nhân {summary.patient_id}</span>
            <span className="text-gray-300">·</span>
            <span>{new Date(summary.created_at).toLocaleString("vi-VN")}</span>
            {techMode && <><span className="text-gray-300">·</span><span>prompt: {summary.prompt_version}</span></>}
            <span className="text-gray-300">·</span>
            {(() => {
              const { label, stale } = summaryFreshness(summary.created_at);
              return (
                <span className={stale ? "text-amber-600" : "text-gray-500"}>
                  {label}
                </span>
              );
            })()}
            <span className={`ml-auto px-2.5 py-0.5 rounded-full border text-xs font-medium ${
              reviewState?.summary_status === "confirmed"
                ? "bg-green-50 text-green-700 border-green-200"
                : "text-gray-500 border-gray-200"
            }`}>
              {reviewState?.summary_status === "confirmed"
                ? "Đã xác nhận"
                : "Bản nháp"
              }
            </span>
            {techMode && summary._from_cache && (
              <span className="px-2 py-0.5 bg-gray-100 text-gray-400 text-xs rounded-full border border-gray-200">
                cache
              </span>
            )}
          </div>
        )}
      </header>

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <main className="max-w-5xl mx-auto px-4 py-6 pb-20 space-y-5">

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
              Hệ thống sẽ đọc hồ sơ, tạo bản tóm tắt và xác minh nguồn tham chiếu cho từng thông tin
            </p>
          </div>
        )}

        {/* Summary result */}
        {summary && !loading && (
          <>
            {/* Metrics — compact trust status bar with read mode toggle */}
            <MetricsBar
              metrics={summary.metrics}
              fromCache={summary._from_cache ?? false}
              model={summary.model_version}
              techMode={techMode}
              readMode={readMode}
              onReadModeChange={setReadMode}
            />

            {/* Quick summary */}
            <QuickSummary summary={summary} />

            {/* Hint for citations */}
            <p className="text-xs text-gray-400 italic">
              Di chuột vào thông tin để xem nguồn tham chiếu. Màu xanh = có nguồn xác nhận, vàng = nguồn hỗ trợ một phần, đỏ = chưa tìm thấy nguồn.
            </p>

            {/* Needs Review — always shown prominently */}
            <NeedsReviewSection
              sections={summary.sections}
              onCitationClick={handleCitationClick}
            />

            {/* Sections — clinical order per plan:
                1. clinical_alerts (cảnh báo)
                2. overview (tổng quan)
                3. current_medications (thuốc)
                4. abnormal_labs (xét nghiệm)
                5. diagnoses (chẩn đoán)
                6. treatment_timeline (diễn biến)
                7. medical_history (tiền sử)
                8. reason_for_visit (lý do khám)
                9. allergies (dị ứng)
            */}
            {(() => {
              const ORDER = [
                "clinical_alerts",
                "overview",
                "current_medications",
                "abnormal_labs",
                "diagnoses",
                "treatment_timeline",
                "medical_history",
                "reason_for_visit",
                "allergies",
              ];
              const byId = new Map(summary.sections.map((s) => [s.section_id, s]));
              const ordered = ORDER.map((id) => byId.get(id)).filter(Boolean);
              const rest = summary.sections.filter((s) => !ORDER.includes(s.section_id));
              return [...ordered, ...rest].map((section) => (
                <SectionCard
                  key={section!.section_id}
                  section={section!}
                  activeSourceId={activeId}
                  onCitationClick={handleCitationClick}
                  collapsed={readMode === "quick"}
                />
              ));
            })()}
          </>
        )}
      </main>

      {/* ── Source panel (right drawer) ─────────────────────────────────────── */}
      <SourcePanel
        sourceId={activeId}
        chunk={chunk}
        claimContext={claimContext}
        loading={chunkLoading}
        error={chunkError}
        onClose={() => { setActiveId(null); setChunk(null); setClaimContext(null); }}
        techMode={techMode}
        claimReview={currentClaimReview}
        onClaimReview={handleClaimReview}
        onSourceSwitch={handleCitationClick}
      />

      {/* ── Sticky action bar ─────────────────────────────────────────────── */}
      {summary && !loading && (
        <SummaryActionBar
          summaryStatus={reviewState?.summary_status ?? "draft"}
          confirmedAt={reviewState?.confirmed_at ?? null}
          onSaveDraft={async () => {
            await submitSummaryStatus(summary.patient_id, "draft");
            const updated = await getReviewState(summary.patient_id);
            setReviewState(updated);
          }}
          onConfirm={async () => {
            await submitSummaryStatus(summary.patient_id, "confirmed", "Demo Doctor");
            const updated = await getReviewState(summary.patient_id);
            setReviewState(updated);
          }}
          onFeedback={async (text) => {
            await submitFeedback(summary.patient_id, text);
            const updated = await getReviewState(summary.patient_id);
            setReviewState(updated);
          }}
        />
      )}
    </div>
  );
}
