import type { PredictiveAssessment } from "./types";

const TOOL_LABELS: Record<string, string> = {
  check_history: "Visit trends", check_labs: "Laboratory results",
  check_reporting: "Reporting quality", check_readiness: "Hospital readiness",
  check_pharmacy: "Pharmacy demand",
};
const FIELD_LABELS: Record<string, string> = {
  recent_median: "Recent 7-day median", previous_median: "Previous 7-day median",
  change_pct: "Change from previous week", days_reported: "Days reported this week",
  reported_days: "Days reported this week", latest_positives: "Latest positive results",
  staffed_beds: "Staffed beds", occupied_beds: "Occupied beds",
  staffing_coverage_pct: "Staffing coverage", supply_readiness_pct: "Supply readiness",
  low_quality_rows: "Records needing review", minimum_coverage_pct: "Lowest reporting coverage",
};
function label(key: string) {
  return FIELD_LABELS[key] ?? key.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}
function valueText(key: string, value: unknown): string {
  if (value == null) return "Not available";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return `${value.toLocaleString()}${key.endsWith("_pct") ? "%" : ""}`;
  if (Array.isArray(value)) return value.map((item) => valueText("", item)).join(", ") || "None";
  if (typeof value === "object") return Object.entries(value).map(([name, item]) => `${label(name)}: ${valueText(name, item)}`).join("; ");
  return String(value);
}

export function AgentEvidenceChecks({ checks }: { checks: PredictiveAssessment["result"]["checks"] }) {
  return <section className="agent-evidence-section">
    <div className="agent-section-heading"><h3>Evidence checks</h3><span>{checks.length} checks selected by the agent</span></div>
    <div className="agent-evidence-grid">{checks.map((check, index) => <article className="agent-evidence-card" key={`${check.tool}-${index}`}>
      <div className="agent-evidence-title"><h4>{TOOL_LABELS[check.tool] ?? label(check.tool.replace(/^check_/, ""))}</h4><span>{check.selected_by === "model" ? "AI selected" : "Policy selected"}</span></div>
      <p className="agent-check-reason">{check.reason}</p>
      {check.result.available === false && <p className="agent-data-warning">Evidence unavailable for this check.</p>}
      <dl className="agent-evidence-values">{Object.entries(check.result).filter(([key]) => key !== "available").map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{valueText(key, value)}</dd></div>)}</dl>
      <details className="agent-source-details"><summary>View source data</summary><pre>{JSON.stringify(check.result, null, 2)}</pre></details>
    </article>)}</div>
  </section>;
}
