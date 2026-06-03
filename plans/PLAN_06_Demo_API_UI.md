# PLAN 06 — Demo API & UI
**Component:** FastAPI Backend + Next.js Frontend  
**Tuần chính:** Tuần 5 (setup) + Tuần 6 (polish)

---

## 1. FastAPI Backend

### 1.1 API Routes

```
GET  /api/v1/health                    → System health check
GET  /api/v1/patients                  → List all patient_ids
POST /api/v1/summarize/{patient_id}    → Run pipeline → FinalSummary
GET  /api/v1/source/{source_id}        → SourceChunk lookup (citation click)
GET  /api/v1/eval/{patient_id}         → Human evaluation result
```

### 1.2 Full Implementation (`api/main.py`)

```python
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import time

from src.pipeline import Pipeline
from src.schemas import FinalSummary, SourceChunk
from src.c7_eval.metrics import compute_auto_metrics, check_all_targets

app = FastAPI(
    title="Clinical Summarization API",
    version="0.1.0",
    description="Medical record summarization with citation pipeline"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load pipeline once on startup
pipeline = Pipeline.from_config("configs/config.yaml")

@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "model": pipeline.config["llm"]["model"],
        "patients_loaded": len(pipeline.list_patients())
    }

@app.get("/api/v1/patients")
async def list_patients() -> list[str]:
    """Dropdown UI dùng endpoint này"""
    return sorted(pipeline.list_patients())

@app.post("/api/v1/summarize/{patient_id}", response_model=FinalSummary)
async def summarize_patient(patient_id: str):
    """
    Chạy full pipeline.
    Latency target: ≤ 30 giây.
    Caching: lưu result vào file để tránh re-run.
    """
    # Cache check
    cache_path = Path(f"data/cache/{patient_id}_latest.json")
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return FinalSummary(**cached)

    # Run pipeline
    try:
        t0 = time.time()
        result = pipeline.run(patient_id)
        latency = round(time.time() - t0, 2)
        result.metrics["latency_seconds"] = latency

        # Cache result
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            result.json(ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return result

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/cache/{patient_id}")
async def clear_cache(patient_id: str):
    """Force regenerate summary (bỏ cache)"""
    cache_path = Path(f"data/cache/{patient_id}_latest.json")
    if cache_path.exists():
        cache_path.unlink()
        return {"message": f"Cache cleared for {patient_id}"}
    return {"message": "No cache found"}

@app.get("/api/v1/source/{source_id}")
async def get_source(source_id: str) -> dict:
    """
    Citation viewer endpoint.
    O(1) lookup từ structured store (dict in memory).
    """
    chunk = pipeline.structured_store.get(source_id)
    if not chunk:
        raise HTTPException(
            status_code=404,
            detail=f"Source ID '{source_id}' not found"
        )
    return chunk if isinstance(chunk, dict) else chunk.dict()

@app.get("/api/v1/metrics/{patient_id}")
async def get_metrics(patient_id: str) -> dict:
    """Auto metrics cho patient (từ cached summary nếu có)"""
    cache_path = Path(f"data/cache/{patient_id}_latest.json")
    if not cache_path.exists():
        raise HTTPException(404, "Summary not found — run /summarize first")

    summary = FinalSummary(**json.loads(cache_path.read_text(encoding="utf-8")))
    metrics = compute_auto_metrics(summary)
    _, targets = check_all_targets(metrics)
    return {"metrics": metrics, "targets": targets}
```

### 1.3 Chạy Backend

```bash
# Development
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# View API docs
open http://localhost:8000/docs
```

---

## 2. Next.js Frontend

### 2.1 Component Architecture

```
ui/
├── app/
│   ├── layout.tsx              # Root layout + global styles
│   ├── page.tsx                # Home: Patient selector
│   └── summary/
│       └── [id]/
│           └── page.tsx        # Summary viewer
├── components/
│   ├── PatientSelector.tsx     # Dropdown + Run button
│   ├── SummaryCard.tsx         # Container cho 1 section
│   ├── SummarySection.tsx      # Section header + content
│   ├── CitationBadge.tsx       # Clickable [source_id] badge
│   ├── CitationPanel.tsx       # Sidebar/modal hiện source gốc
│   ├── MetricsBar.tsx          # Citation coverage, hallucination %, latency
│   ├── AllergyHighlight.tsx    # Section dị ứng với nền đỏ
│   └── LoadingSpinner.tsx
├── lib/
│   └── api.ts                  # API client functions
└── types/
    └── index.ts                # TypeScript types
```

### 2.2 TypeScript Types (`ui/types/index.ts`)

```typescript
export interface CitedClaim {
  claim_text: string;
  status: "SUPPORTED" | "PARTIAL" | "UNSUPPORTED" | "CONTRADICTED" | "NO_CITATION";
  citations: string[];
  is_critical: boolean;
}

export interface SummarySection {
  section_id: string;
  noi_dung: string;
  cited_claims: CitedClaim[];
}

export interface FinalSummary {
  patient_id: string;
  ngay_tao: string;
  prompt_version: string;
  model_version: string;
  sections: SummarySection[];
  metrics: {
    citation_coverage?: number;
    hallucination_rate?: number;
    latency_seconds?: number;
    total_claims?: number;
  };
}

export interface SourceChunk {
  source_id: string;
  source_type: string;
  patient_id: string;
  visit_id: string;
  ngay: string | null;
  noi_dung: string;
  metadata: Record<string, any>;
}
```

### 2.3 API Client (`ui/lib/api.ts`)

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function listPatients(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/v1/patients`);
  if (!res.ok) throw new Error("Failed to load patients");
  return res.json();
}

export async function generateSummary(patientId: string): Promise<FinalSummary> {
  const res = await fetch(`${API_BASE}/api/v1/summarize/${patientId}`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Summarization failed");
  }
  return res.json();
}

export async function getSource(sourceId: string): Promise<SourceChunk> {
  const res = await fetch(`${API_BASE}/api/v1/source/${encodeURIComponent(sourceId)}`);
  if (!res.ok) throw new Error("Source not found");
  return res.json();
}

export async function clearCache(patientId: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/cache/${patientId}`, { method: "DELETE" });
}
```

### 2.4 Home Page (`ui/app/page.tsx`)

```tsx
"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { listPatients, generateSummary, clearCache } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [patients, setPatients] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forceRefresh, setForceRefresh] = useState(false);

  useEffect(() => {
    listPatients().then(setPatients).catch(console.error);
  }, []);

  const handleGenerate = async () => {
    if (!selected) return;
    setLoading(true);
    setError(null);

    try {
      if (forceRefresh) {
        await clearCache(selected);
      }
      await generateSummary(selected);  // Triggers cache
      router.push(`/summary/${selected}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-gray-50">
      <div className="max-w-md w-full bg-white rounded-xl shadow-md p-8">
        <h1 className="text-2xl font-bold text-gray-800 mb-2">
          Tóm tắt Bệnh án Lâm sàng
        </h1>
        <p className="text-sm text-gray-500 mb-6">AI-generated • Citation-based</p>

        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 mb-3 text-gray-700"
        >
          <option value="">— Chọn bệnh nhân —</option>
          {patients.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <label className="flex items-center gap-2 mb-4 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={forceRefresh}
            onChange={(e) => setForceRefresh(e.target.checked)}
          />
          Bỏ cache, tạo mới
        </label>

        <button
          onClick={handleGenerate}
          disabled={!selected || loading}
          className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium
                     disabled:opacity-50 hover:bg-blue-700 transition"
        >
          {loading ? "Đang tạo tóm tắt..." : "Tạo tóm tắt"}
        </button>

        {error && (
          <p className="mt-3 text-red-600 text-sm">{error}</p>
        )}

        <p className="mt-4 text-xs text-gray-400 text-center">
          ⚠️ AI-generated draft — cần bác sĩ kiểm tra trước khi dùng
        </p>
      </div>
    </main>
  );
}
```

### 2.5 Summary Page (`ui/app/summary/[id]/page.tsx`)

```tsx
"use client";
import { useEffect, useState } from "react";
import { generateSummary, getSource } from "@/lib/api";
import { FinalSummary, SourceChunk } from "@/types";

const SECTION_LABELS: Record<string, string> = {
  tong_quan: "Tổng quan",
  ly_do_kham: "Lý do khám",
  tien_su: "Tiền sử bệnh",
  thuoc_hien_tai: "Thuốc đang dùng",
  di_ung: "Dị ứng",
  xn_bat_thuong: "Xét nghiệm bất thường",
  chan_doan: "Chẩn đoán",
  luu_y: "⚠️ Điểm cần lưu ý",
};

export default function SummaryPage({ params }: { params: { id: string } }) {
  const [summary, setSummary] = useState<FinalSummary | null>(null);
  const [activeSource, setActiveSource] = useState<SourceChunk | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    generateSummary(params.id)
      .then(setSummary)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [params.id]);

  const handleCitationClick = async (sid: string) => {
    setSourceId(sid);
    const chunk = await getSource(sid);
    setActiveSource(chunk);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Đang tạo tóm tắt lâm sàng...</p>
          <p className="text-gray-400 text-sm mt-1">Có thể mất đến 30 giây</p>
        </div>
      </div>
    );
  }

  if (!summary) return <div className="p-8 text-red-600">Không tải được tóm tắt.</div>;

  return (
    <div className="flex gap-4 p-6 min-h-screen bg-gray-50">
      {/* Main summary */}
      <div className="flex-1 max-w-2xl">
        {/* Header */}
        <div className="bg-white rounded-xl shadow-sm p-6 mb-4">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-xl font-bold text-gray-800">
                Tóm tắt bệnh án — {summary.patient_id}
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                {summary.ngay_tao.slice(0, 10)} · {summary.model_version} · {summary.prompt_version}
              </p>
            </div>
            <span className="bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded-full">
              AI Draft
            </span>
          </div>

          {/* Metrics bar */}
          {summary.metrics && (
            <div className="mt-4 flex gap-4 text-sm">
              <MetricBadge
                label="Citation"
                value={`${((summary.metrics.citation_coverage || 0) * 100).toFixed(0)}%`}
                ok={(summary.metrics.citation_coverage || 0) >= 0.9}
              />
              <MetricBadge
                label="Hallucination"
                value={`${((summary.metrics.hallucination_rate || 0) * 100).toFixed(0)}%`}
                ok={(summary.metrics.hallucination_rate || 0) <= 0.05}
                inverse
              />
              <MetricBadge
                label="Latency"
                value={`${summary.metrics.latency_seconds}s`}
                ok={(summary.metrics.latency_seconds || 99) <= 30}
              />
            </div>
          )}
        </div>

        {/* Sections */}
        {summary.sections.map((section) => (
          <div
            key={section.section_id}
            className={`bg-white rounded-xl shadow-sm p-6 mb-4 ${
              section.section_id === "di_ung" ? "border-l-4 border-red-400" : ""
            } ${
              section.section_id === "luu_y" ? "border-l-4 border-yellow-400" : ""
            }`}
          >
            <h2 className="font-semibold text-gray-700 mb-3">
              {SECTION_LABELS[section.section_id] || section.section_id}
            </h2>
            <p className="text-gray-700 leading-relaxed whitespace-pre-line mb-3">
              {section.noi_dung}
            </p>

            {/* Citation badges */}
            <div className="flex flex-wrap gap-1.5">
              {[...new Set(
                section.cited_claims.flatMap((c) => c.citations)
              )].map((sid) => (
                <button
                  key={sid}
                  onClick={() => handleCitationClick(sid)}
                  className={`text-xs px-2 py-0.5 rounded font-mono ${
                    activeSource?.source_id === sid
                      ? "bg-blue-600 text-white"
                      : "bg-blue-100 text-blue-700 hover:bg-blue-200"
                  }`}
                >
                  [{sid.split("_").slice(-2).join("_")}]
                </button>
              ))}
            </div>
          </div>
        ))}

        <p className="text-xs text-gray-400 text-center mt-4">
          ⚠️ Đây là bản tóm tắt do AI tạo ra. Cần bác sĩ kiểm tra trước khi dùng cho quyết định lâm sàng.
        </p>
      </div>

      {/* Citation panel (sidebar) */}
      {activeSource && (
        <div className="w-80 sticky top-6 h-fit bg-white rounded-xl shadow-sm p-5 border border-blue-100">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold text-gray-700 text-sm">Nguồn dữ liệu gốc</h3>
            <button
              onClick={() => setActiveSource(null)}
              className="text-gray-400 hover:text-gray-600 text-lg leading-none"
            >
              ×
            </button>
          </div>

          <div className="space-y-2 text-sm">
            <div>
              <span className="text-gray-400">ID:</span>
              <code className="ml-2 text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                {activeSource.source_id}
              </code>
            </div>
            <div>
              <span className="text-gray-400">Loại:</span>
              <span className="ml-2 text-gray-700 capitalize">
                {activeSource.source_type}
              </span>
            </div>
            {activeSource.ngay && (
              <div>
                <span className="text-gray-400">Ngày:</span>
                <span className="ml-2 text-gray-700">{activeSource.ngay}</span>
              </div>
            )}
            <div className="mt-3 pt-3 border-t">
              <p className="text-gray-400 text-xs mb-1">Nội dung gốc:</p>
              <p className="text-gray-700 leading-relaxed">{activeSource.noi_dung}</p>
            </div>
            {Object.keys(activeSource.metadata || {}).length > 0 && (
              <div className="mt-2 pt-2 border-t">
                <p className="text-gray-400 text-xs mb-1">Metadata:</p>
                <pre className="text-xs bg-gray-50 p-2 rounded overflow-auto max-h-32">
                  {JSON.stringify(activeSource.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricBadge({
  label, value, ok, inverse = false
}: {
  label: string; value: string; ok: boolean; inverse?: boolean;
}) {
  const color = inverse
    ? (ok ? "green" : "red")
    : (ok ? "green" : "red");

  return (
    <div className={`text-${color}-700 bg-${color}-50 px-2 py-1 rounded`}>
      <span className="text-xs text-gray-500">{label}: </span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
```

---

## 3. Demo Script (Tuần 6)

```
Kịch bản demo 10 phút:

1. (1 min) Overview
   - Giải thích bài toán: bác sĩ khám 40-60 BN/ngày, cần review nhanh
   - Mô tả pipeline: EHR → preprocess → RAG → cite → verify
   - Không dùng cho quyết định lâm sàng cuối cùng

2. (3 min) BN001 — Golden case
   - Chọn BN001, bấm "Tạo tóm tắt"
   - Chờ loading ~20-25s
   - Chỉ ra: metrics bar (citation coverage, latency)
   - Click 2-3 citations → hiện source panel
   - Chỉ ra: dị ứng section highlight đỏ

3. (2 min) BN005 — Edge case (ICD mâu thuẫn)
   - Chỉ ra: verifier đã loại claim contradicted
   - Chỉ ra: claim có ⚠️ flag

4. (2 min) BN002 — Multi-visit
   - Chỉ ra: summary tổng hợp xuyên suốt nhiều visits
   - Chỉ ra: xu hướng HbA1c qua thời gian trong luu_y section

5. (2 min) Metrics + MLflow
   - Mở MLflow UI: http://localhost:5000
   - So sánh prompt_v1 vs prompt_v2
   - Q&A
```

---

## 4. Setup

```bash
# Backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd ui
npm run dev
# → http://localhost:3000

# MLflow
mlflow ui --host 0.0.0.0 --port 5000
# → http://localhost:5000

# Env vars (ui/.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000
```
