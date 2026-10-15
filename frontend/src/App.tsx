import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Clock3, Database, Download, FileCheck2, ListChecks, Mail, RefreshCw, ShieldCheck, Sparkles, Upload, Workflow as WorkflowIcon, XCircle } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import { EmailAlertsPage } from "./EmailAlertsPage";
import { NotificationBanner } from "./NotificationBanner";
import type { AlertRecord, Cluster, Condition, EvidenceBriefing, ForecastBriefing, ForecastResponse, IncidentAction, IncidentTimeline, InvestigationResponse, Observation, PlaybookLibrary, PlaybookValidation, Hospital, ResponsePlan, SignalResponse, WorkflowRun } from "./types";

const SOURCE_LABELS: Record<string, string> = { visits: "Visits", lab_positives: "Lab positives", pharmacy_demand: "Pharmacy demand" };
type View = "dashboard" | "alerts" | "actions" | "playbooks" | "emails";
const PAGE_PATHS: Record<View, string> = {
  dashboard: "/command-dashboard",
  alerts: "/alert-review",
  actions: "/action-tracker",
  emails: "/email-alerts",
  playbooks: "/playbook-library",
};

function viewFromPath(pathname: string): View {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return (Object.entries(PAGE_PATHS).find(([, path]) => path === normalized)?.[0] as View | undefined) ?? "dashboard";
}

function isoDaysBefore(value: string, days: number) {
  const result = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(result.getTime())) return value;
  result.setUTCDate(result.getUTCDate() - days);
  return result.toISOString().slice(0, 10);
}

function isValidIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(parsed);
}

function formatChartDate(value: string) {
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" }).format(parsed);
}

function levelLabel(level: Cluster["level"]) {
  return level.charAt(0).toUpperCase() + level.slice(1);
}

export default function App() {
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [hospital, setHospital] = useState("all");
  const [condition, setCondition] = useState("all");
  const [analysisDate, setAnalysisDate] = useState("");
  const [latestAnalysisDate, setLatestAnalysisDate] = useState("");
  const [observations, setObservations] = useState<Observation[]>([]);
  const [signals, setSignals] = useState<SignalResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [forecastBriefing, setForecastBriefing] = useState<ForecastBriefing | null>(null);
  const [forecastBriefingLoading, setForecastBriefingLoading] = useState(false);
  const [forecastBriefingError, setForecastBriefingError] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null);
  const [responsePlan, setResponsePlan] = useState<ResponsePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState<View>(() => viewFromPath(window.location.pathname));
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
  const [briefingOpen, setBriefingOpen] = useState(false);
  const [briefingError, setBriefingError] = useState<string | null>(null);
  const [briefingScope, setBriefingScope] = useState("");
  const [caseBriefing, setCaseBriefing] = useState<EvidenceBriefing | null>(null);
  const [caseBriefingKey, setCaseBriefingKey] = useState<string | null>(null);
  const [caseBriefingLoading, setCaseBriefingLoading] = useState(false);
  const [caseBriefingOpen, setCaseBriefingOpen] = useState(false);
  const [caseBriefingError, setCaseBriefingError] = useState<string | null>(null);
  const [expandedClusterKey, setExpandedClusterKey] = useState<string | null>(null);
  const briefingRequestRef = useRef(0);
  const [workflow, setWorkflow] = useState<WorkflowRun | null>(null);
  const [actions, setActions] = useState<IncidentAction[]>([]);
  const [actionAssignee, setActionAssignee] = useState("");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [timeline, setTimeline] = useState<IncidentTimeline | null>(null);

  useEffect(() => {
    const canonicalPath = PAGE_PATHS[viewFromPath(window.location.pathname)];
    if (window.location.pathname !== canonicalPath) window.history.replaceState({}, "", canonicalPath);
    const handlePopState = () => setView(viewFromPath(window.location.pathname));
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigate(nextView: View) {
    const path = PAGE_PATHS[nextView];
    if (window.location.pathname !== path) window.history.pushState({}, "", path);
    setView(nextView);
  }

  useEffect(() => {
    Promise.all([api.hospitals(), api.conditions(), api.dataAvailability()])
      .then(([hospitalData, conditionData, availability]) => {
        setHospitals(hospitalData);
        setConditions(conditionData);
        setLatestAnalysisDate(availability.latest_date);
        setAnalysisDate(availability.latest_date);
      })
      .catch(() => {
        setLoading(false);
        setError("The dashboard could not load its reference data or latest analysis date.");
      });
  }, []);

  useEffect(() => {
    if (!analysisDate) return;
    const hasSpecificScope = hospital !== "all" && condition !== "all";
    setLoading(true);
    setError(null);
    briefingRequestRef.current += 1;
    setBriefing(null);
    setBriefingOpen(false);
    setBriefingError(null);
    setBriefingScope("");
    setCaseBriefing(null);
    setCaseBriefingKey(null);
    setCaseBriefingLoading(false);
    setCaseBriefingOpen(false);
    setCaseBriefingError(null);
    setExpandedClusterKey(null);
    setForecastBriefing(null);
    setForecastBriefingError(null);
    Promise.all([
      api.observations(
        isoDaysBefore(analysisDate, 28),
        analysisDate,
        hospital === "all" ? undefined : hospital,
        condition === "all" ? undefined : condition,
      ),
      api.signals(analysisDate),
      hasSpecificScope ? api.forecast(analysisDate, hospital, condition) : Promise.resolve(null),
      hasSpecificScope ? api.investigation(analysisDate, hospital, condition) : Promise.resolve(null),
      hasSpecificScope ? api.workflow(analysisDate, hospital, condition) : Promise.resolve(null),
    ])
      .then(([observationData, signalData, forecastData, investigationData, workflowData]) => { setObservations(observationData); setSignals(signalData); setForecast(forecastData); setInvestigation(investigationData); setWorkflow(workflowData); })
      .catch(() => setError("The surveillance API is unavailable. Confirm that the FastAPI service is running."))
      .finally(() => setLoading(false));
  }, [analysisDate, condition, hospital, refreshKey]);

  useEffect(() => {
    if (view !== "alerts") return;
    setAlertLoading(true);
    api.alerts()
      .then(setAlerts)
      .catch((reason: Error) => setAlertMessage(reason.message))
      .finally(() => setAlertLoading(false));
  }, [view, refreshKey]);

  useEffect(() => {
    if (view !== "playbooks") return;
    api.playbooks().then(setPlaybookLibrary).catch(() => setPlaybookMessage("The playbook service is unavailable."));
  }, [view]);

  useEffect(() => {
    if (view !== "actions") return;
    setActionLoading(true);
    setActionMessage(null);
    api.actions().then(setActions).catch((reason: Error) => setActionMessage(reason.message)).finally(() => setActionLoading(false));
  }, [view, refreshKey]);

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

  async function generateCaseBriefing(targetHospital: string, targetCondition: string) {
    const requestId = ++briefingRequestRef.current;
    const targetKey = `${targetHospital}-${targetCondition}`;
    setCaseBriefingKey(targetKey);
    setCaseBriefing(null);
    setCaseBriefingLoading(true);
    setCaseBriefingOpen(true);
    setCaseBriefingError(null);
    try {
      const result = await api.briefing(analysisDate, targetHospital, targetCondition);
      if (requestId !== briefingRequestRef.current) return;
      setCaseBriefing(result);
    } catch {
      if (requestId === briefingRequestRef.current) setCaseBriefingError("The case briefing could not be generated.");
    }
    finally { setCaseBriefingLoading(false); }
  }

  async function generateFilteredBriefing() {
    const requestId = ++briefingRequestRef.current;
    setBriefingLoading(true);
    setBriefingError(null);
    setBriefingScope(scopeLabel);
    try {
      const result = await api.aggregateBriefing(
        analysisDate,
        hospital === "all" ? undefined : hospital,
        condition === "all" ? undefined : condition,
      );
      if (requestId !== briefingRequestRef.current) return;
      setBriefing(result);
      setBriefingOpen(true);
    } catch {
      if (requestId === briefingRequestRef.current) setBriefingError("The filtered evidence briefing could not be generated.");
    } finally { setBriefingLoading(false); }
  }

  async function generateForecastBriefing() {
    setForecastBriefingLoading(true);
    setForecastBriefingError(null);
    try { setForecastBriefing(await api.forecastBriefing(analysisDate, hospital, condition)); }
    catch { setForecastBriefingError("The forecast briefing could not be generated."); }
    finally { setForecastBriefingLoading(false); }
  }

  async function updateAction(id: number, status: IncidentAction["status"]) {
    if ((status === "completed" || status === "cancelled") && !window.confirm(`Confirm marking this action ${status === "completed" ? "complete" : "cancelled"}?`)) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const updated = await api.updateAction(id, status, actionAssignee.trim());
      setActions((items) => items.map((item) => item.id === id ? { ...item, ...updated } : item));
      setActionMessage(`Action marked ${status.replaceAll("_", " ")}.`);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to update the action.");
    } finally { setActionLoading(false); }
  }

  async function loadTimeline(alertId: number) {
    setActionLoading(true);
    setActionMessage(null);
    try { setTimeline(await api.incidentTimeline(alertId)); }
    catch (reason) { setActionMessage(reason instanceof Error ? reason.message : "Unable to load the incident timeline."); }
    finally { setActionLoading(false); }
  }

  async function downloadSituationReport(alertId: number) {
    setActionMessage(null);
    try {
      const response = await fetch(api.situationReportUrl(alertId));
      if (!response.ok) throw new Error(`PDF request failed (${response.status})`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `situation-report-alert-${alertId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to download the PDF report.");
    }
  }

  async function generateAlert(targetHospital = hospital, targetCondition = condition) {
    setAlertLoading(true);
    setAlertMessage(null);
    try {
      const result = await api.generateAlerts(analysisDate, targetHospital, targetCondition);
      if (result.created > 0) {
        const notification = result.incident_master_notifications;
        const emailSummary = notification.sent
          ? ` Incident master email sent.`
          : notification.failed
            ? ` Incident master email failed; the alert remains in the review queue.`
            : ` Incident master email skipped because no address is configured.`;
        setAlertMessage(`${result.created} alert sent for human review.${emailSummary}`);
        navigate("alerts");
      } else {
        setAlertMessage(result.existing > 0 ? "This threshold alert has already been submitted for review." : "No eligible corroborated alert was found.");
      }
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setAlertMessage(reason instanceof Error ? reason.message : "Unable to generate alert.");
    } finally { setAlertLoading(false); }
  }

  async function decideAlert(id: number, status: "approved" | "dismissed") {
    if (reviewer.trim().length < 2) { setAlertMessage("Enter the Incident Commander name before recording a decision."); return; }
    if (!window.confirm(`Confirm ${status === "approved" ? "approving" : "dismissing"} this alert?`)) return;
    setAlertLoading(true);
    setAlertMessage(null);
    try {
      const result = await api.decideAlert(id, status, reviewer.trim());
      setAlerts((items) => items.filter((item) => item.id !== id));
      const notificationSummary = status === "approved" && result.actions_created > 0
        ? ` ${result.owner_notifications.sent} owner email(s) sent${result.owner_notifications.failed ? `; ${result.owner_notifications.failed} failed` : ""}${result.owner_notifications.skipped ? `; ${result.owner_notifications.skipped} skipped` : ""}.`
        : "";
      setAlertMessage(`Alert ${status}. The decision was recorded in the audit trail.${notificationSummary}`);
    } catch (reason) {
      setAlertMessage(reason instanceof Error ? reason.message : "Unable to record the decision.");
    } finally { setAlertLoading(false); }
  }

  const chartData = useMemo(() => {
    const rows = new Map<string, Record<string, string | number>>();
    observations.forEach((item) => {
      const row = rows.get(item.observation_date) ?? { date: formatChartDate(item.observation_date) };
      row[item.signal_source] = Number(row[item.signal_source] ?? 0) + item.observation_count;
      rows.set(item.observation_date, row);
    });
    return [...rows.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, row]) => row);
  }, [observations]);

  const hasSpecificScope = hospital !== "all" && condition !== "all";
  const selectedClusters = signals?.clusters.filter((item) =>
    (hospital === "all" || item.hospital_code === hospital) &&
    (condition === "all" || item.condition_code === condition)
  ) ?? [];
  const displayedClusters = expandedClusterKey
    ? [...selectedClusters].sort((left, right) => {
        const leftKey = `${left.hospital_code}-${left.condition_code}`;
        const rightKey = `${right.hospital_code}-${right.condition_code}`;
        return leftKey === expandedClusterKey ? -1 : rightKey === expandedClusterKey ? 1 : 0;
      })
    : selectedClusters;
  const latestObservationDate = observations.at(-1)?.observation_date;
  const latestVisits = observations
    .filter((item) => item.observation_date === latestObservationDate && item.signal_source === "visits")
    .reduce((total, item) => total + item.observation_count, 0);
  const activeLevel = selectedClusters.some((item) => item.level === "escalate")
    ? "escalate"
    : selectedClusters.some((item) => item.level === "investigate")
      ? "investigate"
      : selectedClusters.some((item) => item.level === "monitor") ? "monitor" : "normal";
  const scopeLabel = `${condition === "all" ? "All diseases" : conditions.find((item) => item.code === condition)?.name ?? condition} · ${hospital === "all" ? "All hospitals" : hospitals.find((item) => item.code === hospital)?.name ?? hospital}`;
  const forecastChartData = useMemo(() => {
    if (!forecast) return [];
    const rows = new Map<string, Record<string, string | number>>();
    forecast.scenarios.forEach((scenario) => scenario.points.forEach((point) => {
      const row = rows.get(point.date) ?? { date: formatChartDate(point.date) };
      row[scenario.scenario] = point.projected_visits;
      rows.set(point.date, row);
    }));
    return [...rows.values()];
  }, [forecast]);
  const forecastSummary = useMemo(() => {
    if (!forecast) return null;
    const scenarios = Object.fromEntries(forecast.scenarios.map((item) => [item.scenario, item]));
    const expected = scenarios.expected;
    const best = scenarios.best_case;
    const worst = scenarios.worst_case;
    if (!expected || !best || !worst) return null;
    const expectedEnd = expected.points.at(-1)?.projected_visits ?? forecast.latest_visits;
    const bestEnd = best.points.at(-1)?.projected_visits ?? forecast.latest_visits;
    const worstEnd = worst.points.at(-1)?.projected_visits ?? forecast.latest_visits;
    const expectedChange = forecast.latest_visits ? ((expectedEnd - forecast.latest_visits) / forecast.latest_visits) * 100 : 0;
    return { scenarios, expectedEnd, bestEnd, worstEnd, expectedChange };
  }, [forecast]);

  useEffect(() => {
    if (!hasSpecificScope || activeLevel === "normal") { setResponsePlan(null); return; }
    api.responsePlan(condition, activeLevel)
      .then(setResponsePlan)
      .catch(() => setResponsePlan(null));
  }, [activeLevel, condition, hasSpecificScope]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><ShieldCheck size={28} /><div><strong>CrisisWatch</strong><span>Public-health intelligence</span></div></div>
        <nav><button className={view === "dashboard" ? "active" : ""} onClick={() => navigate("dashboard")}><Activity size={18} /> Command dashboard</button><button className={view === "alerts" ? "active" : ""} onClick={() => navigate("alerts")}><AlertTriangle size={18} /> Alert review</button><button className={view === "actions" ? "active" : ""} onClick={() => navigate("actions")}><ListChecks size={18} /> Action tracker</button><button className={view === "emails" ? "active" : ""} onClick={() => navigate("emails")}><Mail size={18} /> Email alerts</button><button className={view === "playbooks" ? "active" : ""} onClick={() => navigate("playbooks")}><Database size={18} /> Playbook library</button></nav>
      </aside>

      <main>
        <header><div><p className="eyebrow">Healthcare Crisis Prediction and Response Agent</p><h1>{view === "dashboard" ? "Surveillance command dashboard" : view === "alerts" ? "Incident Commander alert review" : view === "actions" ? "Incident action tracker" : view === "emails" ? "Threshold email alerts" : "Response playbook library"}</h1><p className="subtitle">{view === "dashboard" ? "Review signals, supporting evidence and escalation readiness." : view === "alerts" ? "Approve or dismiss corroborated alerts before any response action is issued." : view === "actions" ? "Assign and track approved response tasks through completion." : view === "emails" ? "Configure scheduled delivery, recipients and manual threshold notifications." : "Validate operational guidance before it is considered for controlled activation."}</p></div><div className="system-status" role="status"><span aria-hidden="true"></span> Data pipeline active</div></header>

        {view === "emails" && <EmailAlertsPage analysisDate={analysisDate} />}

        {view === "actions" ? <section className="action-page"><div className="card action-toolbar"><label>Assign updates as<input value={actionAssignee} onChange={(event) => setActionAssignee(event.target.value)} placeholder="Team member or role" /></label><button onClick={() => setRefreshKey((value) => value + 1)} disabled={actionLoading}><RefreshCw size={16} /> Refresh actions</button></div><NotificationBanner message={actionMessage} onDismiss={() => setActionMessage(null)} />{timeline && <div className="card timeline-panel"><div className="panel-heading"><div><h2>Incident timeline · Alert #{timeline.alert_id}</h2><p>Chronological alert decision and action history</p></div><button className="report-link" onClick={() => downloadSituationReport(timeline.alert_id)}><Download size={14} /> Download PDF</button></div><div className="timeline-list">{timeline.events.map((event) => <div key={`${event.timestamp}-${event.event}`}><span><Clock3 size={12} /></span><div><strong>{event.title}</strong><p>{event.detail}</p><small>{new Date(event.timestamp).toLocaleString()}</small></div></div>)}</div></div>}<div className="review-heading"><div><h2>Approved response actions</h2><p>Tasks are created only after Incident Commander approval.</p></div><span>{actions.filter((item) => item.status !== "completed" && item.status !== "cancelled").length} open</span></div>{actionLoading && actions.length === 0 ? <div className="card review-empty">Loading action tracker…</div> : actions.length === 0 ? <div className="card review-empty"><ListChecks size={36} /><strong>No response actions</strong><p>Approved alerts will create tasks from the selected playbook.</p></div> : <div className="action-tracker-list">{actions.map((item) => <article className="card tracked-action" key={item.id}><div className="tracked-heading"><span className={`task-status ${item.status}`}>{item.status.replaceAll("_", " ")}</span><div><strong>{item.action_text}</strong><p>{item.alerts.conditions.name} · {item.alerts.hospitals.name} · Alert #{item.alert_id}</p></div></div><div className="task-meta"><span><small>Owner</small>{item.owner_role}</span><span><small>Assignee</small>{item.assignee_name || "Unassigned"}</span><span><small>Timeframe</small>{item.timeframe}</span><span><small>Due</small>{item.due_at ? new Date(item.due_at).toLocaleString() : "Ongoing"}</span></div><div className="alert-actions"><button className="timeline-button" onClick={() => loadTimeline(item.alert_id)} disabled={actionLoading}><Clock3 size={14} /> Timeline</button><button className="report-link compact" onClick={() => downloadSituationReport(item.alert_id)}><Download size={14} /> PDF report</button>{item.status === "pending" && <button className="generate-button" onClick={() => updateAction(item.id, "in_progress")} disabled={actionLoading}>Start action</button>}{item.status === "in_progress" && <button className="approve-button" onClick={() => updateAction(item.id, "completed")} disabled={actionLoading}><CheckCircle2 size={16} /> Complete</button>}{item.status !== "completed" && item.status !== "cancelled" && <button className="dismiss" onClick={() => updateAction(item.id, "cancelled")} disabled={actionLoading}>Cancel</button>}</div></article>)}</div>}</section> : view === "playbooks" ? <section className="playbook-page">
          <div className="card playbook-overview"><div><span>Active playbook</span><strong>Version {playbookLibrary?.active_version ?? "—"}</strong><p>Current bounded response actions used by the recommendation engine.</p></div><div><span>Supported files</span><strong>{playbookLibrary?.supported_formats.map((item) => item.toUpperCase()).join(" · ") ?? "PDF · DOCX · YAML · JSON"}</strong><p>Maximum file size {playbookLibrary ? `${Math.round(playbookLibrary.max_file_bytes / 1024 / 1024)} MB` : "5 MB"}.</p></div></div>
          <div className="card upload-panel"><Upload size={30} aria-hidden="true" /><div><h2>Validate a playbook</h2><p>The file is parsed and checked against the required response schema. It is not activated or stored.</p></div><label className="upload-button" tabIndex={0} role="button" onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.currentTarget.querySelector<HTMLInputElement>("input")?.click(); } }}>{playbookLoading ? "Validating…" : "Choose file"}<input type="file" accept=".pdf,.docx,.yaml,.yml,.json" disabled={playbookLoading} onChange={(event) => validatePlaybook(event.target.files?.[0])} /></label></div>
          <NotificationBanner message={playbookMessage} onDismiss={() => setPlaybookMessage(null)} />
          {playbookValidation && <div className="card validation-result"><div className="validation-title"><FileCheck2 size={26} /><div><strong>{playbookValidation.source.filename}</strong><span>{playbookValidation.source.format.toUpperCase()} · {playbookValidation.source.size_bytes.toLocaleString()} bytes · Version {playbookValidation.summary.version}</span></div></div><div className="validation-metrics"><div><span>Conditions</span><strong>{playbookValidation.summary.conditions.length}</strong><small>{playbookValidation.summary.conditions.join(", ").toUpperCase()}</small></div>{Object.entries(playbookValidation.summary.action_counts).map(([level, count]) => <div key={level}><span>{level}</span><strong>{count}</strong><small>validated actions</small></div>)}</div><p className="hash">SHA-256: {playbookValidation.source.sha256}</p></div>}
        </section> : view === "alerts" ? <section className="review-page">
          <div className="card review-toolbar"><label>Incident Commander<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Enter reviewer name" /></label><button onClick={() => setRefreshKey((value) => value + 1)} disabled={alertLoading}><RefreshCw size={16} /> Refresh queue</button></div>
          <NotificationBanner message={alertMessage} onDismiss={() => setAlertMessage(null)} />
          <div className="review-heading"><div><h2>Pending approval</h2><p>Only corroborated investigate or escalate signals enter this queue.</p></div><span>{alerts.length} pending</span></div>
          {alertLoading && alerts.length === 0 ? <div className="card review-empty">Loading review queue…</div> : alerts.length === 0 ? <div className="card review-empty"><CheckCircle2 size={36} /><strong>Review queue is clear</strong><p>Generate an alert from an eligible signal on the command dashboard.</p></div> : <div className="alert-list">{alerts.map((item) => <article className="card alert-card" key={item.id}><div className="alert-summary"><span className={`level ${item.alert_level}`}>{levelLabel(item.alert_level)}</span><div><h3>{item.conditions.name} · {item.hospitals.name}</h3><p>Analysis date {item.analysis_date} · {item.evidence_summary.supporting_sources.length} supporting sources</p></div></div><div className="alert-evidence">{item.evidence_summary.signals.map((signal) => <span key={signal.signal_source}><strong>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</strong>{signal.current_count} ({signal.percent_change > 0 ? "+" : ""}{signal.percent_change}%)</span>)}</div><div className="alert-actions"><button className="dismiss" onClick={() => decideAlert(item.id, "dismissed")} disabled={alertLoading}><XCircle size={16} /> Dismiss</button><button className="approve-button" onClick={() => decideAlert(item.id, "approved")} disabled={alertLoading}><CheckCircle2 size={16} /> Approve</button></div></article>)}</div>}
        </section> : view === "dashboard" ? <>

        <section className="filters card">
          <label>Hospital<select value={hospital} onChange={(event) => setHospital(event.target.value)}><option value="all">All hospitals</option>{hospitals.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label>Condition<select value={condition} onChange={(event) => setCondition(event.target.value)}><option value="all">All diseases</option>{conditions.map((item) => <option key={item.code} value={item.code}>{item.name}</option>)}</select></label>
          <label>Analysis date<input type="date" min="2025-10-29" max={latestAnalysisDate || undefined} value={analysisDate} onChange={(event) => { if (isValidIsoDate(event.target.value)) setAnalysisDate(event.target.value); }} /></label>
          <button onClick={() => setRefreshKey((value) => value + 1)} disabled={loading}><RefreshCw size={16} /> {loading ? "Refreshing..." : "Refresh"}</button>
        </section>

        <NotificationBanner message={error} onDismiss={() => setError(null)} variant="error" durationMs={8000} />
        <NotificationBanner message={alertMessage} onDismiss={() => setAlertMessage(null)} className="dashboard-notice" />

        {workflow && <section className="card workflow-strip"><div className="workflow-title"><WorkflowIcon size={19} /><div><strong>Workflow trace</strong><span>{workflow.status.replaceAll("_", " ")} · {workflow.duration_ms} ms</span></div></div><div className="workflow-steps">{workflow.steps.map((step, index) => <div className={`workflow-step ${step.status}`} key={step.name}><span>{index + 1}</span><div><strong>{step.component}</strong><small>{step.status.replaceAll("_", " ")} · {step.duration_ms} ms</small></div></div>)}</div></section>}

        <section className="metrics">
          <article className="card metric"><span>Current status</span><strong className={`status-text ${activeLevel}`}>{selectedClusters.length === 0 ? "No active signal" : levelLabel(activeLevel as Cluster["level"])}</strong><small>{hasSpecificScope ? "Selected hospital and disease" : "Highest level in the selected scope"}</small></article>
          <article className="card metric"><span>Latest visits</span><strong>{latestVisits.toLocaleString()}</strong><small>Daily aggregate count</small></article>
          <article className="card metric"><span>{hasSpecificScope ? "Supporting signals" : "Active clusters"}</span><strong>{hasSpecificScope ? selectedClusters[0]?.supporting_sources.length ?? 0 : selectedClusters.length}</strong><small>{hasSpecificScope ? "Corroborating data sources" : "Threshold crossings across the scope"}</small></article>
          <article className="card metric"><span>Approval state</span><strong className="approval"><CheckCircle2 size={23} /> Human gate</strong><small>No response is issued automatically</small></article>
        </section>

        {hasSpecificScope && <section className="card forecast-overview">
          <div className="forecast-heading"><div><span className="forecast-eyebrow">Seven-day forecast outlook</span><h2>Planning scenarios for the selected scope</h2><p>{conditions.find((item) => item.code === condition)?.name ?? condition} · {hospitals.find((item) => item.code === hospital)?.name ?? hospital} · From {formatDate(analysisDate)}</p></div><button className="forecast-ai-button" onClick={generateForecastBriefing} disabled={!forecast || forecastBriefingLoading}><Sparkles size={16} /> {forecastBriefingLoading ? "Preparing outlook…" : "Explain with AI"}</button></div>
          {forecast && forecastSummary ? <>
            <div className="forecast-kpis">
              <article><span>Latest visits</span><strong>{forecast.latest_visits.toLocaleString()}</strong><small>Observed on analysis date</small></article>
              <article><span>Expected day 7</span><strong>{forecastSummary.expectedEnd.toLocaleString()}</strong><small className={forecastSummary.expectedChange > 0 ? "up" : forecastSummary.expectedChange < 0 ? "down" : ""}>{forecastSummary.expectedChange >= 0 ? "+" : ""}{forecastSummary.expectedChange.toFixed(1)}% from latest</small></article>
              <article><span>Day-7 planning range</span><strong>{forecastSummary.bestEnd.toLocaleString()}–{forecastSummary.worstEnd.toLocaleString()}</strong><small>Best to upper-stress scenario</small></article>
              <article><span>Recent weekly change</span><strong>{forecast.observed_weekly_change_pct >= 0 ? "+" : ""}{forecast.observed_weekly_change_pct}%</strong><small>Recent 7 days vs previous 7</small></article>
            </div>
          <div className="forecast-body">
              <div className="forecast-chart-card"><div className="forecast-chart-label"><strong>Projected visits by scenario</strong><span>Day 0 through day {forecast.horizon_days}</span></div><div className="forecast-chart" role="img" aria-label={`Seven-day visit forecast for ${conditions.find((item) => item.code === condition)?.name ?? condition} in ${hospitals.find((item) => item.code === hospital)?.name ?? hospital}. Expected day-seven visits: ${forecastSummary.expectedEnd.toLocaleString()}.`}><ResponsiveContainer width="100%" height="100%"><LineChart data={forecastChartData}><CartesianGrid strokeDasharray="3 3" stroke="#e7edf3" /><XAxis dataKey="date" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="best_case" name="Best case" stroke="#2c9c83" strokeWidth={2.5} dot={false} /><Line type="monotone" dataKey="expected" name="Expected" stroke="#1261a0" strokeWidth={3} dot={false} /><Line type="monotone" dataKey="worst_case" name="Upper stress" stroke="#cf573f" strokeWidth={2.5} dot={false} /></LineChart></ResponsiveContainer></div></div>
              <div className="scenario-cards">{(["best_case", "expected", "worst_case"] as const).map((name) => { const scenario = forecastSummary.scenarios[name]; const finalValue = scenario.points.at(-1)?.projected_visits ?? forecast.latest_visits; return <article className={`scenario-card ${name}`} key={name}><div><span>{name === "best_case" ? "Best case" : name === "expected" ? "Expected" : "Upper stress"}</span><strong>{scenario.daily_change_pct >= 0 ? "+" : ""}{scenario.daily_change_pct}% daily</strong></div><p>{finalValue.toLocaleString()} visits on day 7</p></article>; })}<div className="forecast-boundary"><strong>Planning boundary</strong><p>These are bounded demand scenarios—not outbreak probability or an epidemiological prediction.</p></div></div>
            </div>
            <NotificationBanner message={forecastBriefingError} onDismiss={() => setForecastBriefingError(null)} variant="error" durationMs={8000} />
            {forecastBriefing && <div className="forecast-briefing"><div className="forecast-briefing-title"><Sparkles size={19} /><div><span>AI interpretation · {forecastBriefing.provider}{forecastBriefing.model ? ` · ${forecastBriefing.model}` : ""}</span><strong>{forecastBriefing.headline}</strong></div></div><p>{forecastBriefing.outlook}</p><ul>{forecastBriefing.key_points.map((item) => <li key={item}>{item}</li>)}</ul><div className="forecast-planning-note"><strong>Planning note</strong><p>{forecastBriefing.planning_note}</p></div><small>{forecastBriefing.uncertainty} {forecastBriefing.disclaimer}</small>{forecastBriefing.fallback_reason && <span className="fallback-note">Fallback used: {forecastBriefing.fallback_reason}</span>}</div>}
            <details className="forecast-assumptions"><summary>Method and assumptions</summary>{forecast.assumptions.map((item) => <p key={item}>{item}</p>)}</details>
          </> : <div className="forecast-loading">{loading ? "Preparing forecast scenarios…" : "Forecast data is unavailable for this selection."}</div>}
        </section>}

        <section className="content-grid">
          <article className="card panel trend-panel"><div className="panel-heading"><div><h2>28-day surveillance trend</h2><p>Daily aggregate signals · {scopeLabel}</p></div>{loading && <span className="loading">Loading…</span>}</div>
            <div className="chart-wrap" role="img" aria-label={`Twenty-eight-day surveillance trend for ${scopeLabel}. Three series show visits, lab positives, and pharmacy demand.`}><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData}><CartesianGrid strokeDasharray="3 3" stroke="#e7edf3" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Legend /><Line type="monotone" dataKey="visits" name="Visits" stroke="#1261a0" strokeWidth={2.5} dot={false} /><Line type="monotone" dataKey="lab_positives" name="Lab positives" stroke="#dc6b35" strokeWidth={2} dot={false} /><Line type="monotone" dataKey="pharmacy_demand" name="Pharmacy demand" stroke="#2c9c83" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
          </article>

          <article className="card panel evidence-panel"><div className="panel-heading"><div><h2>Evidence review</h2><p>Transparent rule output · {scopeLabel}</p></div>{selectedClusters.length > 0 && <div className="evidence-actions"><button className="briefing-button" onClick={generateFilteredBriefing} disabled={briefingLoading}><Sparkles size={13} /> {briefingLoading ? "Preparing…" : "Brief filtered scope"}</button>{hasSpecificScope && selectedClusters.some((item) => item.corroborated && item.level !== "monitor") && <button className="generate-button" onClick={() => generateAlert()} disabled={alertLoading}>Send to review</button>}</div>}</div>
             {selectedClusters.length === 0 ? <div className="empty"><CheckCircle2 size={34} /><strong>No threshold crossed</strong><p>The current values remain within the configured review thresholds.</p></div> : <div className="evidence-cluster-grid">{displayedClusters.map((cluster) => {
               const clusterKey = `${cluster.hospital_code}-${cluster.condition_code}`;
               const isExpanded = expandedClusterKey === clusterKey;
               return <article className={`cluster ${isExpanded ? "expanded" : ""}`} key={clusterKey} role="button" tabIndex={0} aria-expanded={isExpanded} onClick={() => setExpandedClusterKey(isExpanded ? null : clusterKey)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setExpandedClusterKey(isExpanded ? null : clusterKey); } }}>
                 <div className="cluster-title"><div className="cluster-identity"><strong>{cluster.condition}</strong><div className="cluster-meta"><span>{cluster.hospital}</span><small>{cluster.corroborated ? "Corroborated signal" : "Single-source signal"}</small></div></div><span className={`level ${cluster.level}`}>{levelLabel(cluster.level)}</span></div>
                 <div className="cluster-signal-summary">{cluster.signals.map((signal) => <div className="signal-row" key={signal.signal_source}><span>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</span><strong>{signal.current_count}</strong><small>{signal.percent_change > 0 ? "+" : ""}{signal.percent_change}% vs baseline</small></div>)}</div>
                 {!isExpanded && <span className="evidence-expand-label">View complete details</span>}
                 {isExpanded && <div className="evidence-expanded" onClick={(event) => event.stopPropagation()}>
                   <div className="evidence-detail-heading"><strong>Source calculations</strong><span>Analysis date {formatDate(analysisDate)}</span></div>
                   <div className="evidence-detail-list">{cluster.signals.map((signal) => <div className="evidence-detail-row" key={signal.signal_source}>
                     <strong>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</strong>
                     <span><small>Current</small>{signal.current_count.toLocaleString()}</span>
                     <span><small>28-day baseline</small>{signal.baseline_mean.toLocaleString()}</span>
                     <span><small>Change</small>{signal.percent_change > 0 ? "+" : ""}{signal.percent_change}%</span>
                     <span><small>Z-score</small>{signal.z_score ?? "—"}</span>
                     <span><small>Source level</small>{levelLabel(signal.level)}</span>
                   </div>)}</div>
                 </div>}
                 {isExpanded && <div className="evidence-card-footer"><span className="evidence-expand-label">Hide details</span><div className="evidence-card-actions" onClick={(event) => event.stopPropagation()}><button className="briefing-button" onClick={() => generateCaseBriefing(cluster.hospital_code, cluster.condition_code)} disabled={caseBriefingLoading}><Sparkles size={14} /> {caseBriefingLoading && caseBriefingKey === clusterKey ? "Preparing…" : "Brief this case"}</button>{cluster.corroborated && cluster.level !== "monitor" && <button className="generate-button" onClick={() => generateAlert(cluster.hospital_code, cluster.condition_code)} disabled={alertLoading}>Send case to review</button>}</div></div>}
                 {isExpanded && caseBriefingKey === clusterKey && (caseBriefing || caseBriefingLoading || caseBriefingError) && <details className="case-briefing-dropdown" open={caseBriefingOpen} onClick={(event) => event.stopPropagation()} onToggle={(event) => setCaseBriefingOpen(event.currentTarget.open)}>
                   <summary><span><Sparkles size={16} /> Case briefing</span><small>{caseBriefingLoading ? "Preparing this case briefing…" : caseBriefing ? `${cluster.condition} · ${cluster.hospital}` : "Unable to generate briefing"}</small></summary>
                   {caseBriefingLoading && <div className="briefing-inline-loading">Reviewing the evidence for this case…</div>}
                   {caseBriefingError && <div className="briefing-inline-error">{caseBriefingError}</div>}
                   {caseBriefing && <div className="briefing-inline-content"><div className="briefing-header"><Sparkles size={20} /><div><span>AI interpretation · {caseBriefing.provider}{caseBriefing.model ? ` · ${caseBriefing.model}` : ""}</span><h2>{caseBriefing.headline}</h2></div></div><p className="briefing-situation">{caseBriefing.situation}</p><div className="briefing-columns"><div><strong>Supporting evidence</strong><ul>{caseBriefing.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Uncertainties</strong><ul>{caseBriefing.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="review-callout"><strong>Recommended review</strong><p>{caseBriefing.recommended_review}</p></div>{caseBriefing.fallback_reason && <p className="fallback-note">Fallback used: {caseBriefing.fallback_reason}</p>}<small>{caseBriefing.disclaimer}</small></div>}
                 </details>}
               </article>;
             })}</div>}
             {(briefing || briefingLoading || briefingError) && <details className="briefing-dropdown" open={briefingOpen} onToggle={(event) => setBriefingOpen(event.currentTarget.open)}>
               <summary><span><Sparkles size={16} /> AI briefing</span><small>{briefingLoading ? `Preparing briefing for ${briefingScope || "the selected scope"}...` : briefing ? `Generated for ${briefingScope || "the selected scope"}` : "Unable to generate briefing"}</small></summary>
               {briefingLoading && <div className="briefing-inline-loading">Preparing the evidence briefing...</div>}
               {briefingError && <div className="briefing-inline-error">{briefingError}</div>}
               {briefing && <div className="briefing-inline-content"><div className="briefing-header"><Sparkles size={20} /><div><span>AI interpretation · {briefing.provider}{briefing.model ? ` · ${briefing.model}` : ""}</span><h2>{briefing.headline}</h2></div></div><p className="briefing-situation">{briefing.situation}</p><div className="briefing-columns"><div><strong>Supporting evidence</strong><ul>{briefing.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Uncertainties</strong><ul>{briefing.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="review-callout"><strong>Recommended review</strong><p>{briefing.recommended_review}</p></div>{briefing.fallback_reason && <p className="fallback-note">Fallback used: {briefing.fallback_reason}</p>}<small>{briefing.disclaimer}</small></div>}
             </details>}
          </article>
         </section>
         {(briefing || briefingLoading || briefingError) && <details className="briefing-dropdown briefing-dropdown-wide" open={briefingOpen} onToggle={(event) => setBriefingOpen(event.currentTarget.open)}>
           <summary><span><Sparkles size={16} /> AI briefing</span><small>{briefingLoading ? `Preparing briefing for ${briefingScope || "the selected scope"}...` : briefing ? `Generated for ${briefingScope || "the selected scope"}` : "Unable to generate briefing"}</small></summary>
           {briefingLoading && <div className="briefing-inline-loading">Preparing the evidence briefing...</div>}
           {briefingError && <div className="briefing-inline-error">{briefingError}</div>}
           {briefing && <div className="briefing-inline-content"><div className="briefing-header"><Sparkles size={20} /><div><span>AI interpretation · {briefing.provider}{briefing.model ? ` · ${briefing.model}` : ""}</span><h2>{briefing.headline}</h2></div></div><p className="briefing-situation">{briefing.situation}</p><div className="briefing-columns"><div><strong>Supporting evidence</strong><ul>{briefing.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Uncertainties</strong><ul>{briefing.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="review-callout"><strong>Recommended review</strong><p>{briefing.recommended_review}</p></div>{briefing.fallback_reason && <p className="fallback-note">Fallback used: {briefing.fallback_reason}</p>}<small>{briefing.disclaimer}</small></div>}
         </details>}
         {hasSpecificScope && <section className="card investigation-panel"><div className="panel-heading"><div><h2>Cluster investigation</h2><p>Fourteen-day evidence correlation for the selected scope</p></div>{investigation && <span className="forecast-change">Peak {formatDate(investigation.peak_date)}</span>}</div>
          <div className="investigation-grid"><div><strong>Source comparison</strong><div className="source-cards">{investigation?.source_comparison.map((item) => <div key={item.signal_source}><span>{SOURCE_LABELS[item.signal_source] ?? item.signal_source}</span><strong>{item.recent_median}</strong><small>{item.comparison_period_days}-day recent median</small><small>{item.window_change_pct === null ? "New activity from zero baseline" : `${item.window_change_pct > 0 ? "+" : ""}${item.window_change_pct}% vs early median`}</small><small>Latest {item.latest_count} · Peak {item.peak_count}</small>{item.outlier_count > 0 && <small className="outlier-note">{item.outlier_count} unusual day{item.outlier_count === 1 ? "" : "s"} detected</small>}</div>)}</div></div><div><strong>Hospital operations</strong><dl className="context-list"><div><dt>Average bed occupancy</dt><dd>{investigation?.hospital_context.average_bed_occupancy_pct ?? "—"}%</dd></div><div><dt>Staffing coverage</dt><dd>{investigation?.hospital_context.average_staffing_coverage_pct ?? "—"}%</dd></div><div><dt>Supply readiness</dt><dd>{investigation?.hospital_context.average_supply_readiness_pct ?? "—"}%</dd></div></dl></div><div><strong>Investigation findings</strong><ul className="finding-list">{investigation?.findings.map((item) => <li key={item}>{item}</li>)}</ul></div></div>
        </section>}
        {responsePlan && <section className="card response-panel"><div className="panel-heading"><div><h2>Recommended response playbook</h2><p>Version {responsePlan.playbook_version} · Actions remain behind the human approval gate</p></div><span className={`level ${responsePlan.alert_level}`}>{levelLabel(responsePlan.alert_level)}</span></div><div className="response-grid"><div className="action-list">{responsePlan.actions.map((item) => <div className="response-action" key={`${item.category}-${item.action}`}><span>{item.category}</span><div><strong>{item.action}</strong><p>{item.owner} · {item.timeframe}</p></div>{item.requires_approval && <small>Approval required</small>}</div>)}</div><aside><strong>Condition guidance</strong>{responsePlan.condition_guidance.map((item) => <p key={item}>{item}</p>)}<div className="boundary-note">{responsePlan.boundary}</div></aside></div></section>}
        {briefing && <section className="card briefing-panel"><div className="briefing-header"><Sparkles size={23} /><div><span>AI interpretation · {briefing.provider}{briefing.model ? ` · ${briefing.model}` : ""}</span><h2>{briefing.headline}</h2></div></div><p className="briefing-situation">{briefing.situation}</p><div className="briefing-columns"><div><strong>Supporting evidence</strong><ul>{briefing.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div><div><strong>Uncertainties</strong><ul>{briefing.uncertainties.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="review-callout"><strong>Recommended review</strong><p>{briefing.recommended_review}</p></div>{briefing.fallback_reason && <p className="fallback-note">Fallback used: {briefing.fallback_reason}</p>}<small>{briefing.disclaimer}</small></section>}
        </> : null}

        <footer>Rules calculate alert levels · AI language support will summarize prepared evidence · Incident Commander retains approval authority</footer>
      </main>
    </div>
  );
}
