import type { Condition, Observation, Region, SignalResponse } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
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
};
