import { useEffect, useState } from "react";
import { CalendarClock, CheckCircle2, Mail, Plus, RefreshCw, Save, Send, Users, X } from "lucide-react";
import { api } from "./api";
import { NotificationBanner } from "./NotificationBanner";
import type { EmailAlertConfig, EmailAlertDashboard } from "./types";

type Props = { analysisDate: string };

export function EmailAlertsPage({ analysisDate }: Props) {
  const [dashboard, setDashboard] = useState<EmailAlertDashboard | null>(null);
  const [config, setConfig] = useState<EmailAlertConfig | null>(null);
  const [recipientInput, setRecipientInput] = useState("");
  const [ccInput, setCcInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api.emailAlertDashboard()
      .then((result) => { setDashboard(result); setConfig(result.config); })
      .catch((reason: Error) => setMessage(reason.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  function addEmail(field: "recipients" | "cc", value: string) {
    const email = value.trim().toLowerCase();
    if (!config || !email) return;
    if (!/^\S+@\S+\.\S+$/.test(email)) { setMessage("Enter a valid email address."); return; }
    if (!config[field].includes(email)) setConfig({ ...config, [field]: [...config[field], email] });
    field === "recipients" ? setRecipientInput("") : setCcInput("");
    setMessage(null);
  }

  function removeEmail(field: "recipients" | "cc", email: string) {
    if (config) setConfig({ ...config, [field]: config[field].filter((item) => item !== email) });
  }

  async function save() {
    if (!config) return;
    setLoading(true); setMessage(null);
    try {
      const updated = await api.saveEmailAlertConfig({
        enabled: config.enabled,
        schedule_time: config.schedule_time.slice(0, 5),
        timezone: config.timezone,
        recipients: config.recipients,
        cc: config.cc,
        minimum_level: config.minimum_level,
        incident_master_email: config.incident_master_email,
        owner_emails: config.owner_emails,
      });
      setConfig(updated);
      setMessage("Email alert configuration saved.");
      await loadDashboard();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to save email settings."); }
    finally { setLoading(false); }
  }

  async function loadDashboard() {
    const result = await api.emailAlertDashboard();
    setDashboard(result);
    setConfig(result.config);
  }

  async function sendNow() {
    setLoading(true); setMessage(null);
    try {
      const result = await api.sendEmailAlerts(analysisDate);
      setMessage(result.status === "success" ? `Mail server accepted the consolidated report with ${result.alerts_sent} threshold alert(s). Inbox delivery is not yet confirmed.` : "Unable to send the consolidated report.");
      await loadDashboard();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "Unable to send email alerts."); }
    finally { setLoading(false); }
  }

  if (!config || !dashboard) return <div className="card review-empty">{message ?? "Loading email alert settings…"}</div>;
  const nextRun = dashboard.next_scheduled_at ? new Date(dashboard.next_scheduled_at).toLocaleString() : "Scheduling paused";
  const ownerAddresses = Object.values(config.owner_emails).map((value) => value.trim().toLowerCase()).filter(Boolean);
  const sharedOwnerAddress = ownerAddresses.length > 1 && new Set(ownerAddresses).size === 1;

  return <section className="email-page">
    <div className="card scheduler-summary">
      <div className="scheduler-heading"><div><CalendarClock size={24} /><div><h2>Email alert scheduler</h2><p>Consolidated reporting across all hospitals and conditions</p></div></div><span className={`scheduler-state ${dashboard.scheduler_status}`}><CheckCircle2 size={15} /> {dashboard.scheduler_status}</span></div>
      <div className="scheduler-facts"><div><small>Next scheduled run</small><strong>{nextRun}</strong></div><div><small>Recipients</small><strong>{config.recipients.length} To · {config.cc.length} CC</strong></div><div><small>SMTP submission</small><strong>{dashboard.smtp_configured ? "Configured" : "Configuration required"}</strong></div></div>
    </div>

    <NotificationBanner message={message} onDismiss={() => setMessage(null)} />
    <div className="email-layout">
      <div className="card email-config-panel">
        <div className="email-section-heading"><div><Mail size={20} /><h2>Email configuration</h2></div><label className="switch-row"><input type="checkbox" checked={config.enabled} onChange={(event) => setConfig({ ...config, enabled: event.target.checked })} /> Scheduler enabled</label></div>
        <div className="schedule-controls"><label>Scheduled time<input type="time" value={config.schedule_time.slice(0, 5)} onChange={(event) => setConfig({ ...config, schedule_time: event.target.value })} /></label><label>Timezone<select value={config.timezone} onChange={(event) => setConfig({ ...config, timezone: event.target.value })}><option value="Asia/Kolkata">Asia/Kolkata</option><option value="UTC">UTC</option><option value="America/New_York">America/New_York</option><option value="Europe/London">Europe/London</option></select></label><label>Minimum level<select value={config.minimum_level} onChange={(event) => setConfig({ ...config, minimum_level: event.target.value as EmailAlertConfig["minimum_level"] })}><option value="investigate">Investigate</option><option value="escalate">Escalate only</option></select></label></div>

        <EmailList title="Recipients (To)" values={config.recipients} input={recipientInput} setInput={setRecipientInput} onAdd={() => addEmail("recipients", recipientInput)} onRemove={(email) => removeEmail("recipients", email)} />
        <EmailList title="CC" values={config.cc} input={ccInput} setInput={setCcInput} onAdd={() => addEmail("cc", ccInput)} onRemove={(email) => removeEmail("cc", email)} />
        <div className="incident-master-editor"><div><h3>Incident master review notification</h3><p>This address receives a card whenever a corroborated alert is sent for review.</p></div><label>Incident master email<input type="email" value={config.incident_master_email ?? ""} onChange={(event) => setConfig({ ...config, incident_master_email: event.target.value })} /></label></div>
        <div className="owner-email-editor"><div><h3>Task owner notifications</h3><p>Each newly approved response task is emailed to its responsible role.</p>{sharedOwnerAddress && <p className="shared-owner-warning">All roles currently use one mailbox. Separate department heads will not receive these messages unless their own addresses are configured.</p>}</div>{["Epidemiology lead", "Operations lead", "Incident communications", "Incident Commander"].map((role) => <label key={role}>{role}<input type="email" value={config.owner_emails[role] ?? ""} onChange={(event) => setConfig({ ...config, owner_emails: { ...config.owner_emails, [role]: event.target.value } })} /></label>)}</div>
        <div className="email-config-actions"><button className="save-email-button" onClick={save} disabled={loading}><Save size={16} /> Save configuration</button><button className="send-now-button" onClick={sendNow} disabled={loading || !dashboard.smtp_configured}><Send size={16} /> Send consolidated report for {analysisDate}</button></div>
      </div>

      <aside className="email-side">
        <div className="card activity-snapshot"><h3>Activity snapshot</h3><div><span><small>Consolidated reports accepted by SMTP</small><strong>{dashboard.total_sends}</strong></span><span><small>Configured time</small><strong>{config.schedule_time.slice(0, 5)}</strong></span></div></div>
        <div className="card send-history"><div className="history-heading"><h3><RefreshCw size={17} /> Send history</h3><button onClick={load} disabled={loading}>Refresh</button></div>{dashboard.history.length === 0 ? <p className="history-empty">No email attempts recorded.</p> : <div className="history-list">{dashboard.history.map((item) => <div className="history-item" key={item.id}><div><strong>{new Date(item.sent_at).toLocaleString()}</strong><span className={`delivery-status ${item.status}`}>{item.status === "success" ? "SMTP accepted" : item.status}</span></div><p>{item.subject ?? item.error_message ?? "No eligible alerts"}</p><small>{item.trigger_mode} · {item.recipients.length + item.cc.length} recipient(s) · {item.alert_ids.length} alert(s)</small></div>)}</div>}</div>
      </aside>
    </div>
  </section>;
}

function EmailList({ title, values, input, setInput, onAdd, onRemove }: { title: string; values: string[]; input: string; setInput: (value: string) => void; onAdd: () => void; onRemove: (email: string) => void }) {
  return <div className="email-list-editor"><h3><Users size={16} /> {title}</h3><div className="email-chips">{values.length === 0 ? <span className="chip-empty">No addresses added</span> : values.map((email) => <span className="email-chip" key={email}>{email}<button onClick={() => onRemove(email)} aria-label={`Remove ${email}`}><X size={13} /></button></span>)}</div><div className="add-email-row"><input type="email" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); onAdd(); } }} placeholder={`Add ${title.toLowerCase()} email`} /><button onClick={onAdd}><Plus size={16} /> Add</button></div></div>;
}
