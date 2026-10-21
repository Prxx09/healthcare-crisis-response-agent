import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw, Upload } from "lucide-react";
import { api } from "./api";
import type { PlaybookDocument, PlaybookLibrary, ResponsePlan } from "./types";

export function PlaybookLibraryPage() {
  const [library, setLibrary] = useState<PlaybookLibrary | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [previewCondition, setPreviewCondition] = useState("");
  const [previewLevel, setPreviewLevel] = useState<"monitor" | "investigate" | "escalate">("monitor");
  const [preview, setPreview] = useState<ResponsePlan | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setLoadError("");
    try { setLibrary(await api.playbooks()); }
    catch (error) { setLoadError(error instanceof Error ? error.message : "Unable to load library"); }
    finally { setInitialLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const hasProcessing = library?.documents.some((item) => item.status === "processing") ?? false;
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => window.clearInterval(timer);
  }, [hasProcessing, refresh]);
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > (library?.max_file_bytes ?? 5 * 1024 * 1024)) { setMessage("Choose a file of 5 MB or smaller."); return; }
    setBusy(true); setMessage("Extracting source text, checking actions, and indexing in Pinecone. This may take a few minutes.");
    try {
      const document = await api.uploadPlaybook(file);
      setSelected(document.id);
      setMessage(document.duplicate ? "This file is already indexed. Open it below to review." : "Saved in Supabase and indexed in Pinecone. Review the extracted actions before activation.");
    } catch (error) { setSelected(null); setMessage(error instanceof Error ? error.message : "Upload failed"); }
    finally { await refresh(); setBusy(false); }
  }
  async function previewRules() {
    if (!previewCondition) return;
    setBusy(true); setPreview(null);
    try { setPreview(await api.responsePlan(previewCondition, previewLevel)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load current rules"); }
    finally { setBusy(false); }
  }
  async function activate(document: PlaybookDocument) {
    if (reviewer.trim().length < 2) { setMessage("Enter your name to record the review."); return; }
    const confirmation = document.active
      ? "Deactivate this playbook? Its current disease rules will stop being used, and previous rules will not be restored."
      : "Activate this playbook and replace the current rules for every disease it contains? Existing issued tasks will not change.";
    if (!window.confirm(confirmation)) return;
    setBusy(true);
    try {
      await api.activatePlaybook(document.id, !document.active, reviewer.trim());
      setPreview(null);
      setMessage(document.active ? "Playbook deactivated. Previous rules will not be restored." : "Playbook activated. Its disease rules now replace previous playbooks completely.");
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to update playbook"); }
    finally { setBusy(false); }
  }
  if (initialLoading) return <section className="playbook-page"><div className="card review-empty" role="status"><span className="inline-spinner" aria-hidden="true" />Loading playbook library…</div></section>;
  if (!library) return <section className="playbook-page"><div className="card review-empty" role="alert"><strong>Playbook library unavailable</strong><p>{loadError || "The library could not be loaded."}</p><button onClick={() => { setInitialLoading(true); void refresh(); }}><RefreshCw size={16} aria-hidden="true" /> Retry</button></div></section>;
  return <section className="playbook-page" aria-busy={busy}>
    <div className="card playbook-overview"><div><span>Bundled initial guidance</span><strong>Version {library?.active_version ?? "—"}</strong><p>Used only for diseases that have never had an uploaded ruleset activated.</p></div><div><span>Supported files</span><strong>PDF · DOCX · YAML · JSON</strong><p>Up to 5 MB and 60,000 extracted characters. Scanned PDFs need OCR before upload.</p></div></div>
    <div className="card upload-panel"><Upload size={30} aria-hidden="true"/><div><h2>Upload and index a playbook</h2><p>Source file → text extraction → source-checked actions → Supabase records → Pinecone indexing.</p><p>Ordinary documents use the configured Groq or Hugging Face model. Structured playbooks are parsed directly. Any explicitly named disease is accepted.</p></div><label className="upload-button" role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.currentTarget.querySelector<HTMLInputElement>("input")?.click(); } }}>{busy ? "Processing…" : "Choose playbook"}<input aria-label="Upload playbook" type="file" accept=".pdf,.docx,.yaml,.yml,.json" disabled={busy || Boolean(library?.uploads_error) || library?.indexing_configured === false} onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }}/></label></div>
    {library.uploads_error && <p className="error-banner playbook-status-banner" role="alert">{library.uploads_error}</p>}
    {!library.indexing_configured && <p className="playbook-status-banner warning" role="alert">Configure the Pinecone key and existing index on the backend to enable uploads.</p>}
    {!library.retrieval_enabled && <p className="playbook-status-banner information">Semantic ranking is disabled. Recommendations still use the current activated playbook’s stored actions; old rules are never restored.</p>}
    {!library.ai_configured && <p className="playbook-status-banner information">AI extraction is not configured. Structured playbooks can still be uploaded.</p>}
    {loadError && <p className="error-banner" role="alert">{loadError}</p>}
    {message && <p className="card playbook-notice" role="status">{message}</p>}
    <div className="card playbook-review-toolbar"><label>Reviewed by<input placeholder="Your name" value={reviewer} onChange={(event) => setReviewer(event.target.value)}/></label><button disabled={busy} onClick={() => { void refresh(); }}><RefreshCw size={16}/> Refresh library</button></div>
    <p className="playbook-guidance">Review the original document and extracted quotations, disease labels, severity levels, owners, and timing before activating. Activating a playbook replaces all previous rules for each disease it contains. Older documents remain for audit history. Existing issued tasks retain their original source. New diseases are registered on activation; surveillance forecasts require observation data.</p>
    {(library.condition_rules?.length ?? 0) > 0 && <div className="card uploaded-playbook playbook-preview"><div className="playbook-section-heading"><div><span>Rule validation</span><h2>Preview current disease rules</h2></div><p>Confirm the active guidance for a disease and alert level.</p></div><div className="playbook-review-toolbar"><label>Disease<select value={previewCondition} onChange={(event) => {setPreviewCondition(event.target.value);setPreview(null);}}><option value="">Choose disease</option>{library.condition_rules.map((rule) => <option key={rule.condition_code} value={rule.condition_code}>{rule.condition_code.replaceAll("_", " ")}{rule.enabled ? "" : " (deactivated)"}</option>)}</select></label><label>Alert level<select value={previewLevel} onChange={(event) => {setPreviewLevel(event.target.value as typeof previewLevel);setPreview(null);}}>{["monitor","investigate","escalate"].map((level) => <option key={level}>{level}</option>)}</select></label><button disabled={busy || !previewCondition} onClick={() => {void previewRules();}}>View current rules</button></div>{preview && <div className="playbook-preview-results"><p>{preview.unavailable_reason ?? `Source: ${preview.playbook_version}`}</p>{preview.actions.map((action, index) => <div className="response-action playbook-preview-action" key={`${index}-${action.action}`}><div><strong>{action.action}</strong><p>{action.owner} · {action.timeframe}</p><small>{action.source_filename}</small></div></div>)}</div>}</div>}
    {library.documents.length === 0 && <div className="card review-empty">No uploaded playbooks yet.</div>}
    {library.documents.map((document) => <article className="card uploaded-playbook" key={document.id}>
      <div className="panel-heading"><div><h2>{document.filename}</h2><p>{document.format.toUpperCase()} · {document.size_bytes.toLocaleString()} bytes · {document.vector_count} indexed actions · {document.extraction_method ?? (document.status === "failed" ? "Parsing failed" : "Pending extraction")}</p></div><strong className={`playbook-document-status ${document.active ? "active" : document.status === "indexed" && document.reviewed_by ? "inactive" : document.status}`}>{document.active ? "Active" : document.status === "indexed" ? document.reviewed_by ? "Replaced or deactivated" : "Indexed · awaiting review" : document.status}</strong></div>
      {document.error_message && <p className="playbook-document-error" role="alert">{document.error_message} Upload the same file to retry.</p>}
      <div className="alert-actions playbook-document-actions">{document.actions.length > 0 && <button className="playbook-secondary-button" onClick={() => setSelected(selected === document.id ? null : document.id)} aria-expanded={selected === document.id} aria-controls={`playbook-actions-${document.id}`}>{selected === document.id ? "Hide actions" : `Review ${document.actions.length} actions`}</button>}<a className="report-link" href={api.playbookSourceUrl(document.id)} download><Download size={14} aria-hidden="true"/> Original file</a>{document.status === "indexed" && <button className="playbook-activation-button" disabled={busy || reviewer.trim().length < 2} onClick={() => { void activate(document); }}>{document.active ? "Deactivate" : "Review and replace disease rules"}</button>}</div>
      {document.active && <p className="playbook-document-meta"><strong>Current rules</strong>{(library.condition_rules ?? []).filter((rule) => rule.enabled && rule.document_id === document.id).map((rule) => rule.condition_code.replaceAll("_", " ")).join(", ")}</p>}
      {document.reviewed_by && <p className="playbook-document-meta"><strong>Last reviewed by</strong>{document.reviewed_by}</p>}
      {selected === document.id && document.actions.length > 0 && <div className="uploaded-actions" id={`playbook-actions-${document.id}`}>{document.actions.map((action) => <div className="response-action" key={action.action_id}><span>{action.condition_code.toUpperCase()} · {action.alert_level}</span><div><strong>{action.action}</strong><p>{action.owner} · {action.timeframe} · Source section {action.section}</p>{action.review_notes?.map((note) => <small key={note}>{note}. </small>)}<details><summary>Source quotation</summary><blockquote>{action.evidence_quote}</blockquote></details></div></div>)}</div>}
    </article>)}
  </section>;
}
