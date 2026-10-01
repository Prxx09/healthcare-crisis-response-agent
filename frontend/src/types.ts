export interface Region { id: number; code: string; name: string; population: number }
export interface Condition { id: number; code: string; name: string; syndrome_group: string }
export interface Observation {
  observation_date: string;
  signal_source: "visits" | "lab_positives" | "pharmacy_demand";
  observation_count: number;
  coverage_pct: number;
  data_quality: string;
  regions: { code: string; name: string };
  conditions: { code: string; name: string };
}
export interface SourceSignal {
  signal_source: string;
  current_count: number;
  baseline_mean: number;
  percent_change: number;
  z_score: number | null;
  level: "monitor" | "investigate" | "escalate";
}
export interface Cluster {
  region: string;
  region_code: string;
  condition: string;
  condition_code: string;
  level: "monitor" | "investigate" | "escalate";
  corroborated: boolean;
  supporting_sources: string[];
  signals: SourceSignal[];
}
export interface SignalResponse { analysis_date: string; baseline_days: number; source_signal_count: number; clusters: Cluster[] }
export interface AlertRecord {
  id: number;
  analysis_date: string;
  alert_level: "monitor" | "investigate" | "escalate";
  evidence_summary: Cluster;
  rule_version: string;
  status: "pending_approval" | "approved" | "dismissed" | "closed";
  reviewed_by: string | null;
  review_note: string | null;
  approved_at: string | null;
  created_at: string;
  regions: { code: string; name: string };
  conditions: { code: string; name: string };
}
