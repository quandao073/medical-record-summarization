import type { FinalSummary, SourceChunk } from "./types";

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
): Promise<FinalSummary> {
  const params = new URLSearchParams({
    model,
    force_refresh: String(forceRefresh),
  });
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
