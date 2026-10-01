import type { AlertRecord, Condition, EvidenceBriefing, ForecastResponse, InvestigationResponse, Observation, PlaybookLibrary, PlaybookValidation, Region, ResponsePlan, SignalResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

async function sendJson<T>(path: string, method: "POST" | "PATCH", body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  regions: () => getJson<Region[]>("/api/v1/regions"),
  conditions: () => getJson<Condition[]>("/api/v1/conditions"),
  observations: (start: string, end: string, region: string, condition: string) => {
    const query = new URLSearchParams({ start_date: start, end_date: end, region_code: region, condition_code: condition });
    return getJson<Observation[]>(`/api/v1/observations?${query}`);
  },
  signals: (analysisDate: string) => getJson<SignalResponse>(`/api/v1/signals?analysis_date=${analysisDate}&baseline_days=28`),
  forecast: (analysisDate: string, region: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, region_code: region, condition_code: condition, horizon_days: "7" });
    return getJson<ForecastResponse>(`/api/v1/forecast?${query}`);
  },
  investigation: (analysisDate: string, region: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, region_code: region, condition_code: condition, window_days: "14" });
    return getJson<InvestigationResponse>(`/api/v1/investigation?${query}`);
  },
  responsePlan: (condition: string, level: "monitor" | "investigate" | "escalate") => {
    const query = new URLSearchParams({ condition_code: condition, alert_level: level });
    return getJson<ResponsePlan>(`/api/v1/response-plan?${query}`);
  },
  briefing: (analysisDate: string, region: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, region_code: region, condition_code: condition });
    return getJson<EvidenceBriefing>(`/api/v1/briefing?${query}`);
  },
  playbooks: () => getJson<PlaybookLibrary>("/api/v1/playbooks"),
  validatePlaybook: async (file: File) => {
    const query = new URLSearchParams({ filename: file.name });
    const response = await fetch(`${API_URL}/api/v1/playbooks/validate?${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `Playbook validation failed (${response.status})`);
    }
    return response.json() as Promise<PlaybookValidation>;
  },
  alerts: () => getJson<AlertRecord[]>("/api/v1/alerts?status=pending_approval"),
  generateAlerts: (analysisDate: string, regionCode: string, conditionCode: string) =>
    sendJson<{ analysis_date: string; eligible_clusters: number; created: number }>("/api/v1/alerts/generate", "POST", {
      analysis_date: analysisDate,
      baseline_days: 28,
      region_code: regionCode,
      condition_code: conditionCode,
    }),
  decideAlert: (id: number, status: "approved" | "dismissed", reviewerName: string, note?: string) =>
    sendJson<AlertRecord>(`/api/v1/alerts/${id}/decision`, "PATCH", { status, reviewer_name: reviewerName, note: note || null }),
};
