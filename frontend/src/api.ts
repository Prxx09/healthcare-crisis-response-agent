import type { AlertRecord, Condition, EmailAlertConfig, EmailAlertDashboard, EvidenceBriefing, ForecastBriefing, ForecastResponse, IncidentAction, IncidentTimeline, InvestigationResponse, Observation, PlaybookLibrary, PlaybookValidation, Hospital, ResponsePlan, SignalResponse, WorkflowRun } from "./types";

const API_URL = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

async function sendJson<T>(path: string, method: "POST" | "PUT" | "PATCH", body: unknown): Promise<T> {
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
  hospitals: () => getJson<Hospital[]>("/api/v1/hospitals"),
  conditions: () => getJson<Condition[]>("/api/v1/conditions"),
  dataAvailability: () => getJson<{ latest_date: string }>("/api/v1/data-availability"),
  observations: (start: string, end: string, hospital?: string, condition?: string) => {
    const query = new URLSearchParams({ start_date: start, end_date: end });
    if (hospital) query.set("hospital_code", hospital);
    if (condition) query.set("condition_code", condition);
    return getJson<Observation[]>(`/api/v1/observations?${query}`);
  },
  signals: (analysisDate: string) => getJson<SignalResponse>(`/api/v1/signals?analysis_date=${analysisDate}&baseline_days=28`),
  forecast: (analysisDate: string, hospital: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, hospital_code: hospital, condition_code: condition, horizon_days: "7" });
    return getJson<ForecastResponse>(`/api/v1/forecast?${query}`);
  },
  forecastBriefing: (analysisDate: string, hospital: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, hospital_code: hospital, condition_code: condition, horizon_days: "7" });
    return getJson<ForecastBriefing>(`/api/v1/forecast/briefing?${query}`);
  },
  investigation: (analysisDate: string, hospital: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, hospital_code: hospital, condition_code: condition, window_days: "14" });
    return getJson<InvestigationResponse>(`/api/v1/investigation?${query}`);
  },
  responsePlan: (condition: string, level: "monitor" | "investigate" | "escalate") => {
    const query = new URLSearchParams({ condition_code: condition, alert_level: level });
    return getJson<ResponsePlan>(`/api/v1/response-plan?${query}`);
  },
  briefing: (analysisDate: string, hospital: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, hospital_code: hospital, condition_code: condition });
    return getJson<EvidenceBriefing>(`/api/v1/briefing?${query}`);
  },
  aggregateBriefing: (analysisDate: string, hospital?: string, condition?: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate });
    if (hospital) query.set("hospital_code", hospital);
    if (condition) query.set("condition_code", condition);
    return getJson<EvidenceBriefing>(`/api/v1/briefing/aggregate?${query}`);
  },
  workflow: (analysisDate: string, hospital: string, condition: string) => {
    const query = new URLSearchParams({ analysis_date: analysisDate, hospital_code: hospital, condition_code: condition });
    return getJson<WorkflowRun>(`/api/v1/workflow?${query}`);
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
  actions: () => getJson<IncidentAction[]>("/api/v1/actions"),
  incidentTimeline: (alertId: number) => getJson<IncidentTimeline>(`/api/v1/incidents/${alertId}/timeline`),
  situationReportUrl: (alertId: number) => `${API_URL}/api/v1/incidents/${alertId}/report.pdf`,
  generateAlerts: (analysisDate: string, hospitalCode: string, conditionCode: string) =>
    sendJson<{ analysis_date: string; eligible_clusters: number; created: number; existing: number; incident_master_notifications: { sent: number; failed: number; skipped: number } }>("/api/v1/alerts/generate", "POST", {
      analysis_date: analysisDate,
      baseline_days: 28,
      hospital_code: hospitalCode,
      condition_code: conditionCode,
    }),
  decideAlert: (id: number, status: "approved" | "dismissed", reviewerName: string, note?: string) =>
    sendJson<{ alert: AlertRecord; actions_created: number; owner_notifications: { sent: number; failed: number; skipped: number } }>(`/api/v1/alerts/${id}/decision`, "PATCH", { status, reviewer_name: reviewerName, note: note || null }),
  updateAction: (id: number, status: IncidentAction["status"], assigneeName?: string, note?: string) =>
    sendJson<IncidentAction>(`/api/v1/actions/${id}`, "PATCH", { status, assignee_name: assigneeName || null, note: note || null }),
  emailAlertDashboard: () => getJson<EmailAlertDashboard>("/api/v1/email-alerts/dashboard"),
  saveEmailAlertConfig: (config: Pick<EmailAlertConfig, "enabled" | "schedule_time" | "timezone" | "recipients" | "cc" | "minimum_level" | "incident_master_email" | "owner_emails">) =>
    sendJson<EmailAlertConfig>("/api/v1/email-alerts/config", "PUT", config),
  sendEmailAlerts: (analysisDate: string) =>
    sendJson<{ status: string; alerts_sent: number }>("/api/v1/email-alerts/send", "POST", { analysis_date: analysisDate }),
};
