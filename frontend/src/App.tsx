import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Database, FileCheck2, RefreshCw, ShieldCheck, Sparkles, Upload, Workflow as WorkflowIcon, XCircle } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import type { AlertRecord, Cluster, Condition, EvidenceBriefing, ForecastResponse, InvestigationResponse, Observation, PlaybookLibrary, PlaybookValidation, Region, ResponsePlan, SignalResponse, WorkflowRun } from "./types";

const SOURCE_LABELS: Record<string, string> = { visits: "Visits", lab_positives: "Lab positives", pharmacy_demand: "Pharmacy demand" };

function isoDaysBefore(value: string, days: number) {
  const result = new Date(`${value}T00:00:00Z`);
  result.setUTCDate(result.getUTCDate() - days);
  return result.toISOString().slice(0, 10);
}

function levelLabel(level: Cluster["level"]) {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

export default function App() {
  const [regions, setRegions] = useState<Region[]>([]);
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [region, setRegion] = useState("central_district");
  const [condition, setCondition] = useState("ili");
  const [analysisDate, setAnalysisDate] = useState("2025-12-15");
  const [observations, setObservations] = useState<Observation[]>([]);
  const [signals, setSignals] = useState<SignalResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null);
  const [responsePlan, setResponsePlan] = useState<ResponsePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState<"dashboard" | "alerts" | "playbooks">("dashboard");
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [alertLoading, setAlertLoading] = useState(false);
  const [playbookLibrary, setPlaybookLibrary] = useState<PlaybookLibrary | null>(null);
  const [playbookValidation, setPlaybookValidation] = useState<PlaybookValidation | null>(null);
  const [playbookMessage, setPlaybookMessage] = useState<string | null>(null);
  const [playbookLoading, setPlaybookLoading] = useState(false);
  const [briefing, setBriefing] = useState<EvidenceBriefing | null>(null);
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [workflow, setWorkflow] = useState<WorkflowRun | null>(null);

  useEffect(() => {
    Promise.all([api.regions(), api.conditions()])
      .then(([regionData, conditionData]) => { setRegions(regionData); setConditions(conditionData); })
      .catch(() => setError("The dashboard could not load its reference data."));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.observations(isoDaysBefore(analysisDate, 28), analysisDate, region, condition),
      api.signals(analysisDate),
      api.forecast(analysisDate, region, condition),
      api.investigation(analysisDate, region, condition),
      api.workflow(analysisDate, region, condition),
    ])
      .then(([observationData, signalData, forecastData, investigationData, workflowData]) => { setObservations(observationData); setSignals(signalData); setForecast(forecastData); setInvestigation(investigationData); setWorkflow(workflowData); })
      .catch(() => setError("The surveillance API is unavailable. Confirm that the FastAPI service is running."))
      .finally(() => setLoading(false));
  }, [analysisDate, condition, region, refreshKey]);

  useEffect(() => {
    if (view !== "alerts") return;
    setAlertLoading(true);
    setAlertMessage(null);
    api.alerts()
      .then(setAlerts)
      .catch((reason: Error) => setAlertMessage(reason.message))
      .finally(() => setAlertLoading(false));
  }, [view, refreshKey]);

  useEffect(() => {
    if (view !== "playbooks") return;
    api.playbooks().then(setPlaybookLibrary).catch(() => setPlaybookMessage("The playbook service is unavailable."));
  }, [view]);

  async function validatePlaybook(file: File | undefined) {
    if (!file) return;
    setPlaybookLoading(true);
    setPlaybookMessage(null);
    setPlaybookValidation(null);
    try {
      const result = await api.validatePlaybook(file);
      setPlaybookValidation(result);
      setPlaybookMessage("Playbook structure is valid. Validation does not replace the active playbook.");
    } catch (reason) {
      setPlaybookMessage(reason instanceof Error ? reason.message : "Unable to validate the playbook.");
    } finally { setPlaybookLoading(false); }
  }

  async function generateBriefing() {
    setBriefingLoading(true);
    try { setBriefing(await api.briefing(analysisDate, region, condition)); }
    catch { setError("The evidence briefing could not be generated."); }
    finally { setBriefingLoading(false); }
  }

  async function generateAlert() {
    setAlertLoading(true);
    setAlertMessage(null);
    try {
      const result = await api.generateAlerts(analysisDate, region, condition);
      setAlertMessage(result.created > 0 ? `${result.created} alert sent for human review.` : "No new eligible alert was created. It may already exist or require corroboration.");
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setAlertMessage(reason instanceof Error ? reason.message : "Unable to generate alert.");
    } finally { setAlertLoading(false); }
  }

  async function decideAlert(id: number, status: "approved" | "dismissed") {
    if (reviewer.trim().length < 2) { setAlertMessage("Enter the Incident Commander name before recording a decision."); return; }
    setAlertLoading(true);
    setAlertMessage(null);
    try {
      await api.decideAlert(id, status, reviewer.trim());
      setAlerts((items) => items.filter((item) => item.id !== id));
      setAlertMessage(`Alert ${status}. The decision was recorded in the audit trail.`);
    } catch (reason) {
      setAlertMessage(reason instanceof Error ? reason.message : "Unable to record the decision.");
    } finally { setAlertLoading(false); }
  }

  const chartData = useMemo(() => {
    const rows = new Map<string, Record<string, string | number>>();
    observations.forEach((item) => {
      const row = rows.get(item.observation_date) ?? { date: item.observation_date.slice(5) };
      row[item.signal_source] = item.observation_count;
      rows.set(item.observation_date, row);
    });
    return [...rows.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, row]) => row);
  }, [observations]);

  const selectedClusters = signals?.clusters.filter((item) => item.region_code === region && item.condition_code === condition) ?? [];
  const latestVisits = [...observations].reverse().find((item) => item.signal_source === "visits")?.observation_count ?? 0;
  const activeLevel = selectedClusters.length > 0 ? selectedClusters[0].level : "normal";
  const forecastChartData = useMemo(() => {
    if (!forecast) return [];
    const rows = new Map<string, Record<string, string | number>>();
    forecast.scenarios.forEach((scenario) => scenario.points.forEach((point) => {
      const row = rows.get(point.date) ?? { date: point.date.slice(5) };
      row[scenario.scenario] = point.projected_visits;
      rows.set(point.date, row);
    }));
    return [...rows.values()];
  }, [forecast]);

  useEffect(() => {
    if (activeLevel === "normal") { setResponsePlan(null); return; }
    api.responsePlan(condition, activeLevel)
      .then(setResponsePlan)
      .catch(() => setResponsePlan(null));
  }, [activeLevel, condition]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><ShieldCheck size={28} /><div><strong>CrisisWatch</strong><span>Public-health intelligence</span></div></div>
        <nav><button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}><Activity size={18} /> Command dashboard</button><button className={view === "alerts" ? "active" : ""} onClick={() => setView("alerts")}><AlertTriangle size={18} /> Alert review</button><button className={view === "playbooks" ? "active" : ""} onClick={() => setView("playbooks")}><Database size={18} /> Playbook library</button></nav>
        <div className="scope-note"><strong>Decision support only</strong><p>Synthetic aggregate data. Human approval is required before response actions are issued.</p></div>
      </aside>

      <main>
        <header><div><p className="eyebrow">Healthcare Crisis Prediction and Response Agent</p><h1>{view === "dashboard" ? "Surveillance command dashboard" : view === "alerts" ? "Incident Commander alert review" : "Response playbook library"}</h1><p className="subtitle">{view === "dashboard" ? "Review signals, supporting evidence and escalation readiness." : view === "alerts" ? "Approve or dismiss corroborated alerts before any response action is issued." : "Validate operational guidance before it is considered for controlled activation."}</p></div><div className="system-status"><span></span> Data pipeline active</div></header>

        {view === "playbooks" ? <section className="playbook-page">
          <div className="card playbook-overview"><div><span>Active playbook</span><strong>Version {playbookLibrary?.active_version ?? "—"}</strong><p>Current bounded response actions used by the recommendation engine.</p></div><div><span>Supported files</span><strong>{playbookLibrary?.supported_formats.map((item) => item.toUpperCase()).join(" · ") ?? "PDF · DOCX · YAML · JSON"}</strong><p>Maximum file size {playbookLibrary ? `${Math.round(playbookLibrary.max_file_bytes / 1024 / 1024)} MB` : "5 MB"}.</p></div></div>
          <div className="card upload-panel"><Upload size={30} /><div><h2>Validate a playbook</h2><p>The file is parsed and checked against the required response schema. It is not activated or stored.</p></div><label className="upload-button">{playbookLoading ? "Validating…" : "Choose file"}<input type="file" accept=".pdf,.docx,.yaml,.yml,.json" disabled={playbookLoading} onChange={(event) => validatePlaybook(event.target.files?.[0])} /></label></div>
          {playbookMessage && <div className="notice-banner">{playbookMessage}</div>}
          {playbookValidation && <div className="card validation-result"><div className="validation-title"><FileCheck2 size={26} /><div><strong>{playbookValidation.source.filename}</strong><span>{playbookValidation.source.format.toUpperCase()} · {playbookValidation.source.size_bytes.toLocaleString()} bytes · Version {playbookValidation.summary.version}</span></div></div><div className="validation-metrics"><div><span>Conditions</span><strong>{playbookValidation.summary.conditions.length}</strong><small>{playbookValidation.summary.conditions.join(", ").toUpperCase()}</small></div>{Object.entries(playbookValidation.summary.action_counts).map(([level, count]) => <div key={level}><span>{level}</span><strong>{count}</strong><small>validated actions</small></div>)}</div><p className="hash">SHA-256: {playbookValidation.source.sha256}</p></div>}
        </section> : view === "alerts" ? <section className="review-page">
          <div className="card review-toolbar"><label>Incident Commander<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" /></label><button onClick={() => setRefreshKey((value) => value + 1)} disabled={alertLoading}><RefreshCw size={16} /> Refresh queue</button></div>
          {alertMessage && <div className="notice-banner">{alertMessage}</div>}
          <div className="review-heading"><div><h2>Pending approval</h2><p>Only corroborated investigate or escalate signals enter this queue.</p></div><span>{alerts.length} pending</span></div>
          {alertLoading && alerts.length === 0 ? <div className="card review-empty">Loading review queue…</div> : alerts.length === 0 ? <div className="card review-empty"><CheckCircle2 size={36} /><strong>Review queue is clear</strong><p>Generate an alert from an eligible signal on the command dashboard.</p></div> : <div className="alert-list">{alerts.map((item) => <article className="card alert-card" key={item.id}><div className="alert-summary"><span className={`level ${item.alert_level}`}>{levelLabel(item.alert_level)}</span><div><h3>{item.conditions.name} · {item.regions.name}</h3><p>Analysis date {item.analysis_date} · {item.evidence_summary.supporting_sources.length} supporting sources</p></div></div><div className="alert-evidence">{item.evidence_summary.signals.map((signal) => <span key={signal.signal_source}><strong>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</strong>{signal.current_count} ({signal.percent_change > 0 ? "+" : ""}{signal.percent_change}%)</span>)}</div><div className="alert-actions"><button className="dismiss" onClick={() => decideAlert(item.id, "dismissed")} disabled={alertLoading}><XCircle size={16} /> Dismiss</button><button className="approve-button" onClick={() => decideAlert(item.id, "approved")} disabled={alertLoading}><CheckCircle2 size={16} /> Approve</button></div></article>)}</div>}
        </section> : <>

        <section className="filters card">
          <label>Region<select value={region} onChange={(event) => setRegion(event.target.value)}>{regions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label>Condition<select value={condition} onChange={(event) => setCondition(event.target.value)}>{conditions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label>Analysis date<input type="date" min="2025-10-29" max="2026-09-30" value={analysisDate} onChange={(event) => setAnalysisDate(event.target.value)} /></label>
          <button onClick={() => setRefreshKey((value) => value + 1)}><RefreshCw size={16} /> Refresh</button>
        </section>

        {error && <div className="error-banner"><AlertTriangle size={18} />{error}</div>}

        {workflow && <section className="card workflow-strip"><div className="workflow-title"><WorkflowIcon size={19} /><div><strong>Workflow trace</strong><span>{workflow.status.replaceAll("_", " ")} · {workflow.duration_ms} ms</span></div></div><div className="workflow-steps">{workflow.steps.map((step, index) => <div className={`workflow-step ${step.status}`} key={step.name}><span>{index + 1}</span><div><strong>{step.component}</strong><small>{step.status.replaceAll("_", " ")} · {step.duration_ms} ms</small></div></div>)}</div></section>}

        <section className="metrics">
          <article className="card metric"><span>Current status</span><strong className={`status-text ${activeLevel}`}>{selectedClusters.length === 0 ? "No active signal" : levelLabel(selectedClusters[0].level)}</strong><small>Selected region and condition</small></article>
          <article className="card metric"><span>Latest visits</span><strong>{latestVisits.toLocaleString()}</strong><small>Daily aggregate count</small></article>
          <article className="card metric"><span>Supporting signals</span><strong>{selectedClusters[0]?.supporting_sources.length ?? 0}</strong><small>Corroborating data sources</small></article>
          <article className="card metric"><span>Approval state</span><strong className="approval"><CheckCircle2 size={23} /> Human gate</strong><small>No response is issued automatically</small></article>
        </section>

        <section className="content-grid">
          <article className="card panel trend-panel"><div className="panel-heading"><div><h2>28-day surveillance trend</h2><p>Daily aggregate signals for the selected scope</p></div>{loading && <span className="loading">Loading…</span>}</div>
            <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData}><CartesianGrid strokeDasharray="3 3" stroke="#e7edf3" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="visits" name="Visits" stroke="#1261a0" strokeWidth={2.5} dot={false} /><Line type="monotone" dataKey="lab_positives" name="Lab positives" stroke="#dc6b35" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="pharmacy_demand" name="Pharmacy demand" stroke="#2c9c83" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
          </article>

          <article className="card panel evidence-panel"><div className="panel-heading"><div><h2>Evidence review</h2><p>Transparent rule output for the selected date</p></div><div className="evidence-actions"><button className="briefing-button" onClick={generateBriefing} disabled={briefingLoading}><Sparkles size={13} /> {briefingLoading ? "Preparing…" : "Prepare briefing"}</button>{selectedClusters.some((item) => item.corroborated && item.level !== "monitor") && <button className="generate-button" onClick={generateAlert} disabled={alertLoading}>Send to review</button>}</div></div>
            {selectedClusters.length === 0 ? <div className="empty"><CheckCircle2 size={34} /><strong>No threshold crossed</strong><p>The current values remain within the configured review thresholds.</p></div> : selectedClusters.map((cluster) => <div className="cluster" key={`${cluster.region_code}-${cluster.condition_code}`}><div className="cluster-title"><span className={`level ${cluster.level}`}>{levelLabel(cluster.level)}</span><strong>{cluster.corroborated ? "Corroborated signal" : "Single-source signal"}</strong></div>{cluster.signals.map((signal) => <div className="signal-row" key={signal.signal_source}><span>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</span><strong>{signal.current_count}</strong><small>{signal.percent_change > 0 ? "+" : ""}{signal.percent_change}% vs baseline</small></div>)}</div>)}
          </article>
        </section>
        <section className="card panel forecast-panel"><div className="panel-heading"><div><h2>Seven-day planning scenarios</h2><p>Bounded projections based on recent visit activity—not an epidemiological prediction</p></div>{forecast && <span className="forecast-change">Weekly change {forecast.observed_weekly_change_pct > 0 ? "+" : ""}{forecast.observed_weekly_change_pct}%</span>}</div>
          <div className="forecast-layout"><div className="forecast-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={forecastChartData}><CartesianGrid strokeDasharray="3 3" stroke="#e7edf3" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="best_case" name="Best case" stroke="#2c9c83" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="expected" name="Expected" stroke="#1261a0" strokeWidth={2.5} dot={false} /><Line type="monotone" dataKey="worst_case" name="Worst case" stroke="#cf573f" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div><div className="assumptions"><strong>Model assumptions</strong>{forecast?.assumptions.map((item) => <p key={item}>{item}</p>)}</div></div>
        </section>
        <section className="card investigation-panel"><div className="panel-heading"><div><h2>Cluster investigation</h2><p>Fourteen-day evidence correlation for the selected scope</p></div>{investigation && <span className="forecast-change">Peak {investigation.peak_date.slice(5)}</span>}</div>
          <div className="investigation-grid"><div><strong>Source comparison</strong><div className="source-cards">{investigation?.source_comparison.map((item) => <div key={item.signal_source}><span>{SOURCE_LABELS[item.signal_source] ?? item.signal_source}</span><strong>{item.latest_count}</strong><small>{item.window_change_pct > 0 ? "+" : ""}{item.window_change_pct}% across window</small></div>)}</div></div><div><strong>Regional context</strong><dl className="context-list"><div><dt>Rainfall index</dt><dd>{investigation?.regional_context.average_rainfall_index ?? "—"}</dd></div><div><dt>Mobility index</dt><dd>{investigation?.regional_context.average_mobility_index ?? "—"}</dd></div><div><dt>Temperature</dt><dd>{investigation?.regional_context.average_temperature_c ?? "—"}°C</dd></div></dl></div><div><strong>Investigation findings</strong><ul className="finding-list">{investigation?.findings.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
        </section>
        {responsePlan && <section className="card response-panel"><div className="panel-heading"><div><h2>Recommended response playbook</h2><p>Version {responsePlan.playbook_version} · Actions remain behind the human approval gate</p></div><span className={`level ${responsePlan.alert_level}`}>{levelLabel(responsePlan.alert_level)}</span></div><div className="response-grid"><div className="action-list">{responsePlan.actions.map((item) => <div className="response-action" key={`${item.category}-${item.action}`}><span>{item.category}</span><div><strong>{item.action}</strong><p>{item.owner} · {item.timeframe}</p></div>{item.requires_approval && <small>Approval required</small>}</div>)}</div><aside><strong>Condition guidance</strong>{responsePlan.condition_guidance.map((item) => <p key={item}>{item}</p>)}<div className="boundary-note">{responsePlan.boundary}</div></aside></div></section>}
        {briefing && <section className="card briefing-panel"><div className="briefing-header"><Sparkles size={23} /><div><span>Evidence briefing · {briefing.provider}{briefing.model ? ` · ${briefing.model}` : ""}</span><h2>{briefing.headline}</h2></div></div><p className="briefing-situation">{briefing.situation}</p><div className="briefing-columns"><div><strong>Supporting evidence</strong><ul>{briefing.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Uncertainties</strong><ul>{briefing.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="review-callout"><strong>Recommended review</strong><p>{briefing.recommended_review}</p></div>{briefing.fallback_reason && <p className="fallback-note">Fallback used: {briefing.fallback_reason}</p>}<small>{briefing.disclaimer}</small></section>}
        </>}

        <footer>Rules calculate alert levels · AI language support will summarize prepared evidence · Incident Commander retains approval authority</footer>
      </main>
    </div>
  );
}
