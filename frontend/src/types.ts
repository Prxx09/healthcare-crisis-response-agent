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
export interface ForecastPoint { date: string; projected_visits: number }
export interface ForecastScenario {
  scenario: "best_case" | "expected" | "worst_case";
  daily_change_pct: number;
  points: ForecastPoint[];
}
export interface ForecastResponse {
  analysis_date: string;
  horizon_days: number;
  latest_visits: number;
  observed_weekly_change_pct: number;
  scenarios: ForecastScenario[];
  assumptions: string[];
}
export interface InvestigationResponse {
  analysis_date: string;
  window_start: string;
  peak_date: string;
  peak_total: number;
  source_comparison: Array<{ signal_source: string; window_start_count: number; latest_count: number; window_change_pct: number }>;
  data_quality: Record<string, number>;
  regional_context: { average_rainfall_index: number | null; average_mobility_index: number | null; average_temperature_c: number | null };
  findings: string[];
}
export interface ResponseAction {
  category: string;
  action: string;
  owner: string;
  timeframe: string;
  requires_approval: boolean;
}
export interface ResponsePlan {
  playbook_version: string;
  condition_code: string;
  alert_level: "monitor" | "investigate" | "escalate";
  actions: ResponseAction[];
  condition_guidance: string[];
  approval_required: boolean;
  boundary: string;
}
export interface PlaybookLibrary {
  active_version: string;
  supported_formats: string[];
  max_file_bytes: number;
  validation_only: boolean;
}
export interface PlaybookValidation {
  valid: boolean;
  source: { filename: string; format: string; size_bytes: number; sha256: string };
  summary: { version: string; conditions: string[]; action_counts: Record<string, number> };
}
export interface EvidenceBriefing {
  provider: "deterministic" | "groq" | "huggingface";
  model: string | null;
  generated_at: string;
  headline: string;
  situation: string;
  evidence: string[];
  uncertainties: string[];
  recommended_review: string;
  disclaimer: string;
  fallback_reason?: string;
}
export interface WorkflowStep {
  name: string;
  component: string;
  status: "completed" | "failed" | "blocked" | "skipped" | "waiting" | "not_required";
  duration_ms: number;
  output?: Record<string, unknown>;
  message?: string;
}
export interface WorkflowRun {
  workflow_id: string;
  status: "completed" | "partial" | "failed" | "waiting_for_approval";
  analysis_date: string;
  region_code: string;
  condition_code: string;
  duration_ms: number;
  steps: WorkflowStep[];
}
export interface IncidentAction {
  id: number;
  alert_id: number;
  action_key: string;
  category: string;
  action_text: string;
  owner_role: string;
  assignee_name: string | null;
  timeframe: string;
  due_at: string | null;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  completion_note: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  alerts: { alert_level: "monitor" | "investigate" | "escalate"; analysis_date: string; regions: { code: string; name: string }; conditions: { code: string; name: string } };
}
export interface TimelineEvent {
  timestamp: string;
  event: string;
  title: string;
  detail: string;
}
export interface IncidentTimeline { alert_id: number; events: TimelineEvent[] }
