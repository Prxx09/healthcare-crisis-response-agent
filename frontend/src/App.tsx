import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Database, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import type { AlertRecord, Cluster, Condition, Observation, Region, SignalResponse } from "./types";

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [view, setView] = useState<"dashboard" | "alerts">("dashboard");
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [reviewer, setReviewer] = useState("");
  const [alertMessage, setAlertMessage] = useState<string | null>(null);
  const [alertLoading, setAlertLoading] = useState(false);

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
    ])
      .then(([observationData, signalData]) => { setObservations(observationData); setSignals(signalData); })
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><ShieldCheck size={28} /><div><strong>CrisisWatch</strong><span>Public-health intelligence</span></div></div>
        <nav><button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}><Activity size={18} /> Command dashboard</button><button className={view === "alerts" ? "active" : ""} onClick={() => setView("alerts")}><AlertTriangle size={18} /> Alert review</button><button disabled><Database size={18} /> Data sources</button></nav>
        <div className="scope-note"><strong>Decision support only</strong><p>Synthetic aggregate data. Human approval is required before response actions are issued.</p></div>
      </aside>

      <main>
        <header><div><p className="eyebrow">Healthcare Crisis Prediction and Response Agent</p><h1>{view === "dashboard" ? "Surveillance command dashboard" : "Incident Commander alert review"}</h1><p className="subtitle">{view === "dashboard" ? "Review signals, supporting evidence and escalation readiness." : "Approve or dismiss corroborated alerts before any response action is issued."}</p></div><div className="system-status"><span></span> Data pipeline active</div></header>

        {view === "alerts" ? <section className="review-page">
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

          <article className="card panel evidence-panel"><div className="panel-heading"><div><h2>Evidence review</h2><p>Transparent rule output for the selected date</p></div>{selectedClusters.some((item) => item.corroborated && item.level !== "monitor") && <button className="generate-button" onClick={generateAlert} disabled={alertLoading}>Send to review</button>}</div>
            {selectedClusters.length === 0 ? <div className="empty"><CheckCircle2 size={34} /><strong>No threshold crossed</strong><p>The current values remain within the configured review thresholds.</p></div> : selectedClusters.map((cluster) => <div className="cluster" key={`${cluster.region_code}-${cluster.condition_code}`}><div className="cluster-title"><span className={`level ${cluster.level}`}>{levelLabel(cluster.level)}</span><strong>{cluster.corroborated ? "Corroborated signal" : "Single-source signal"}</strong></div>{cluster.signals.map((signal) => <div className="signal-row" key={signal.signal_source}><span>{SOURCE_LABELS[signal.signal_source] ?? signal.signal_source}</span><strong>{signal.current_count}</strong><small>{signal.percent_change > 0 ? "+" : ""}{signal.percent_change}% vs baseline</small></div>)}</div>)}
          </article>
        </section>
        </>}

        <footer>Rules calculate alert levels · AI language support will summarize prepared evidence · Incident Commander retains approval authority</footer>
      </main>
    </div>
  );
}
