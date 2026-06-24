import type { FinalSummary, SourceChunk, ReviewState, ClaimReviewAction, HumanEval } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {
      // ignore parse error
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export async function getPatients(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/api/v1/patients`);
  const data = await handleResponse<{ patients: string[] }>(res);
  return data.patients;
}

export async function summarize(
  patientId: string,
  model: string,
  forceRefresh: boolean,
  signal?: AbortSignal,
  provider?: string,
): Promise<FinalSummary> {
  const params = new URLSearchParams({
    model,
    force_refresh: String(forceRefresh),
  });
  if (provider) {
    params.set("provider", provider);
  }
  const res = await fetch(
    `${API_BASE}/api/v1/summarize/${patientId}?${params}`,
    { method: "POST", signal },
  );
  return handleResponse<FinalSummary>(res);
}

export async function getCachedSummary(
  patientId: string
): Promise<FinalSummary | null> {
  const res = await fetch(`${API_BASE}/api/v1/cache/${patientId}`);
  if (res.status === 404) return null;
  return handleResponse<FinalSummary>(res);
}

export async function getSource(sourceId: string): Promise<SourceChunk> {
  const res = await fetch(`${API_BASE}/api/v1/source/${sourceId}`);
  return handleResponse<SourceChunk>(res);
}

/** Batch-fetch multiple source chunks in parallel. Returns null for any that fail. */
export async function getSources(
  sourceIds: string[],
): Promise<(SourceChunk | null)[]> {
  return Promise.all(
    sourceIds.map((id) => getSource(id).catch(() => null)),
  );
}

export interface RawEncounter {
  patient_id: string;
  encounter_id: string;
  encounter: Record<string, unknown>;
  patient_info: Record<string, unknown>;
  allergies: unknown[];
}

export async function getRawEncounter(
  patientId: string,
  encounterId: string,
): Promise<RawEncounter> {
  const res = await fetch(
    `${API_BASE}/api/v1/raw-encounter/${patientId}/${encounterId}`,
  );
  return handleResponse<RawEncounter>(res);
}

export async function clearCache(patientId: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/cache/${patientId}`, { method: "DELETE" });
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function getReviewState(patientId: string): Promise<ReviewState> {
  const res = await fetch(`${API_BASE}/api/v1/review/${patientId}`);
  return handleResponse<ReviewState>(res);
}

export async function submitClaimReview(
  patientId: string,
  claimId: string,
  sectionId: string,
  claimText: string,
  action: ClaimReviewAction,
  newText?: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/review/${patientId}/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      claim_id: claimId,
      section_id: sectionId,
      claim_text: claimText,
      action,
      new_text: newText ?? null,
    }),
  });
  await handleResponse(res);
}

export async function submitSummaryStatus(
  patientId: string,
  status: "draft" | "confirmed",
  reviewer?: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/review/${patientId}/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reviewer }),
  });
  await handleResponse(res);
}

export async function submitFeedback(
  patientId: string,
  text: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/review/${patientId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  await handleResponse(res);
}

// ─── Human Eval API ───────────────────────────────────────────────────────────

export async function getHumanEval(patientId: string): Promise<HumanEval> {
  const res = await fetch(`${API_BASE}/api/v1/human-eval/${patientId}`);
  return handleResponse<HumanEval>(res);
}

export async function submitHumanEval(
  patientId: string,
  payload: {
    evaluator: string;
    summary_generated_at: string | null;
    model: string | null;
    prompt_version: string | null;
    scores: Record<string, { score: number; notes: string }>;
    overall_notes: string;
    error_categories: string[];
  },
): Promise<{ ok: boolean; weighted_score: number | null }> {
  const res = await fetch(`${API_BASE}/api/v1/human-eval/${patientId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<{ ok: boolean; weighted_score: number | null }>(res);
}

export async function listHumanEvals(): Promise<{
  evals: Array<{
    patient_id: string;
    evaluator: string | null;
    evaluated_at: string | null;
    weighted_score: number | null;
    model: string | null;
    prompt_version: string | null;
  }>;
}> {
  const res = await fetch(`${API_BASE}/api/v1/human-eval`);
  return handleResponse(res);
}
