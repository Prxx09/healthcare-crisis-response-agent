export interface Hospital { id: number; code: string; name: string; bed_capacity: number }
export interface Condition { id: number; code: string; name: string; syndrome_group: string }
export interface Observation {
  observation_date: string;
  signal_source: "visits" | "lab_positives" | "pharmacy_demand";
  observation_count: number;
  coverage_pct: number;
  data_quality: string;
  hospitals: { code: string; name: string };
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
  hospital: string;
  hospital_code: string;
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
  hospitals: { code: string; name: string };
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
  planning_anchor_visits: number;
  observed_weekly_change_pct: number;
  scenarios: ForecastScenario[];
  assumptions: string[];
}
export interface ForecastBriefing {
  provider: "deterministic" | "groq" | "huggingface";
  model: string | null;
  generated_at: string;
  headline: string;
  outlook: string;
  key_points: string[];
  uncertainty: string;
  planning_note: string;
  disclaimer: string;
  fallback_reason?: string;
}
export interface InvestigationResponse {
  analysis_date: string;
  window_start: string;
  peak_date: string;
  peak_total: number;
  source_comparison: Array<{
    signal_source: string;
    window_start_count: number;
    latest_count: number;
    initial_median: number;
    recent_median: number;
    comparison_period_days: number;
    window_change_pct: number | null;
    peak_count: number;
    peak_date: string;
    outlier_count: number;
    outlier_dates: string[];
  }>;
  data_quality: Record<string, number>;
  hospital_context: { average_bed_occupancy_pct: number | null; average_staffing_coverage_pct: number | null; average_supply_readiness_pct: number | null };
  findings: string[];
}
export interface ResponseAction {
  category: string;
  action: string;
  owner: string;
  timeframe: string;
  requires_approval: boolean;
  source_filename?: string;
}
export interface ResponsePlan {
  playbook_version: string;
  condition_code: string;
  alert_level: "monitor" | "investigate" | "escalate";
  actions: ResponseAction[];
  condition_guidance: string[];
  approval_required: boolean;
  boundary: string;
  available?: boolean;
  unavailable_reason?: string;
}
export interface PlaybookLibrary {
  active_version: string;
  supported_formats: string[];
  max_file_bytes: number;
  validation_only: boolean;
  documents: PlaybookDocument[];
  condition_rules: PlaybookConditionRule[];
  uploads_error: string | null;
  indexing_configured: boolean;
  ai_configured: boolean;
  retrieval_enabled: boolean;
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
  hospital_code: string;
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
  alerts: { alert_level: "monitor" | "investigate" | "escalate"; analysis_date: string; hospitals: { code: string; name: string }; conditions: { code: string; name: string } };
}
export interface TimelineEvent {
  timestamp: string;
  event: string;
  title: string;
  detail: string;
}
export interface IncidentTimeline { alert_id: number; events: TimelineEvent[] }
export interface EmailAlertConfig {
  id: number;
  enabled: boolean;
  schedule_time: string;
  timezone: string;
  recipients: string[];
  cc: string[];
  minimum_level: "investigate" | "escalate";
  incident_master_email: string;
  owner_emails: Record<string, string>;
  updated_at: string;
}
export interface EmailAlertDelivery {
  id: number;
  trigger_mode: "scheduled" | "manual";
  status: "success" | "failed" | "skipped";
  analysis_date: string | null;
  schedule_date: string | null;
  recipients: string[];
  cc: string[];
  alert_ids: number[];
  subject: string | null;
  error_message: string | null;
  sent_at: string;
}
export interface EmailAlertDashboard {
  config: EmailAlertConfig;
  scheduler_status: "running" | "paused";
  smtp_configured: boolean;
  next_scheduled_at: string | null;
  total_sends: number;
  history: EmailAlertDelivery[];
}

export interface PredictiveAssessment {
  id: number;
  created_at: string;
  next_review_at: string;
  result: {
    assessment: { status: "routine" | "watch" | "prepare" | "uncertain"; confidence: string; hypotheses: string[]; contradictory_evidence: boolean; data_quality_concern: boolean; boundary: string };
    pressure: { level: string; expected_day_7_visits: number; upper_scenario_day_7_visits: number; expected_growth_pct: number; occupancy_pct: number | null; first_constraint: string | null; interpretation: string };
    checks: Array<{ tool: string; reason: string; selected_by: "model" | "policy"; result: Record<string, unknown> }>;
    prior_requests: Array<{ request_key: string; status: string; completion_note: string | null }>;
    pre_approval: { approved: boolean; reviewer_name: string; eligible_alert_levels: Array<"investigate" | "escalate">; rationale: string };
    approval_boundary: string;
  };
}
export interface AgentFollowup {
  id: number;
  request_key: string;
  owner_role: string;
  request_text: string;
  due_at: string;
  status: "open" | "completed";
  completion_note: string | null;
}
export interface PredictiveAgentState {
  assessment: PredictiveAssessment | null;
  requests: AgentFollowup[];
  agent_approval?: { approved: boolean; actions_created: number; owner_notifications: { sent: number; failed: number; skipped: number } };
}

export interface UploadedPlaybookAction {
  action_id: string;
  condition_code: string;
  alert_level: string;
  action: string;
  owner: string;
  timeframe: string;
  evidence_quote: string;
  section: number;
  review_notes?: string[];
}
export interface PlaybookDocument {
  id: string;
  filename: string;
  format: string;
  size_bytes: number;
  status: "processing" | "indexed" | "failed";
  active: boolean;
  vector_count: number;
  extraction_method: string | null;
  error_message: string | null;
  reviewed_by: string | null;
  actions: UploadedPlaybookAction[];
  duplicate?: boolean;
}

export interface PlaybookConditionRule {
  condition_code: string;
  document_id: string;
  enabled: boolean;
  reviewed_by: string;
}
