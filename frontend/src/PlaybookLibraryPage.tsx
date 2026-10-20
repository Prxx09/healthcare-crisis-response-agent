import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw, Upload } from "lucide-react";
import { api } from "./api";
import type { PlaybookDocument, PlaybookLibrary } from "./types";

export function PlaybookLibraryPage() {
  const [library, setLibrary] = useState<PlaybookLibrary | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try { setLibrary(await api.playbooks()); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load library"); }
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
    } catch (error) { setMessage(error instanceof Error ? error.message : "Upload failed"); }
    finally { await refresh(); setBusy(false); }
  }
  async function activate(document: PlaybookDocument) {
    if (reviewer.trim().length < 2) { setMessage("Enter your name to record the review."); return; }
    setBusy(true);
    try {
      await api.activatePlaybook(document.id, !document.active, reviewer.trim());
      setMessage(document.active ? "Playbook deactivated." : "Playbook activated. Matching recommendations can now use these actions; Pinecone search may take a short time to reflect a new upload.");
      await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to update playbook"); }
    finally { setBusy(false); }
  }
  return <section className="playbook-page">
    <div className="card playbook-overview"><div><span>Bundled fallback</span><strong>Version {library?.active_version ?? "—"}</strong><p>Used when no active uploaded guidance matches.</p></div><div><span>Supported files</span><strong>PDF · DOCX · YAML · JSON</strong><p>Up to 5 MB and 60,000 extracted characters. Scanned PDFs need OCR before upload.</p></div></div>
    <div className="card upload-panel"><Upload size={30} aria-hidden="true"/><div><h2>Upload and index a playbook</h2><p>Source file → text extraction → source-checked actions → Supabase records → Pinecone indexing.</p><p>Ordinary documents use the configured Groq or Hugging Face model. Existing structured playbooks are parsed directly.</p></div><label className="upload-button" role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.currentTarget.querySelector<HTMLInputElement>("input")?.click(); } }}>{busy ? "Processing…" : "Choose playbook"}<input aria-label="Upload playbook" type="file" accept=".pdf,.docx,.yaml,.yml,.json" disabled={busy || Boolean(library?.uploads_error) || library?.indexing_configured === false} onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }}/></label></div>
    {library?.uploads_error && <p className="error-banner" role="alert">{library.uploads_error}</p>}
    {library && !library.indexing_configured && <p role="alert">Configure the Pinecone key and existing index on the backend to enable uploads.</p>}
    {library && !library.retrieval_enabled && <p>Uploaded guidance is saved and indexed, but recommendation retrieval is disabled. Set PINECONE_RAG_ENABLED=true on the backend to use active uploads.</p>}
    {library && !library.ai_configured && <p>AI extraction is not configured. Structured playbooks can still be uploaded.</p>}
    {message && <p className="card playbook-notice" role="status">{message}</p>}
    <div className="card playbook-review-toolbar"><label>Reviewed by<input placeholder="Your name" value={reviewer} onChange={(event) => setReviewer(event.target.value)}/></label><button disabled={busy} onClick={() => { void refresh(); }}><RefreshCw size={16}/> Refresh library</button></div>
    <p>Review the original document and extracted quotations, disease labels, severity levels, owners, and timing before activating. Activation makes guidance eligible for recommendations; response actions follow the existing approval workflow.</p>
    {library?.documents.length === 0 && <div className="card review-empty">No uploaded playbooks yet.</div>}
    {library?.documents.map((document) => <article className="card uploaded-playbook" key={document.id}>
      <div className="panel-heading"><div><h2>{document.filename}</h2><p>{document.format.toUpperCase()} · {document.size_bytes.toLocaleString()} bytes · {document.vector_count} indexed actions · {document.extraction_method ?? (document.status === "failed" ? "Parsing failed" : "Pending extraction")}</p></div><strong>{document.active ? "Active" : document.status === "indexed" ? "Indexed · awaiting review" : document.status}</strong></div>
      {document.error_message && <p role="alert">{document.error_message} Upload the same file to retry.</p>}
      <div className="alert-actions"><button onClick={() => setSelected(selected === document.id ? null : document.id)} aria-expanded={selected === document.id}>{selected === document.id ? "Hide actions" : `Review ${document.actions.length} actions`}</button><a className="report-link" href={api.playbookSourceUrl(document.id)}><Download size={14}/> Original file</a>{document.status === "indexed" && <button disabled={busy || reviewer.trim().length < 2} onClick={() => { void activate(document); }}>{document.active ? "Deactivate" : "Confirm review and activate"}</button>}</div>
      {document.reviewed_by && <p>Last reviewed by {document.reviewed_by}</p>}
      {selected === document.id && <div className="uploaded-actions">{document.actions.map((action) => <div className="response-action" key={action.action_id}><span>{action.condition_code.toUpperCase()} · {action.alert_level}</span><div><strong>{action.action}</strong><p>{action.owner} · {action.timeframe} · Source section {action.section}</p>{action.review_notes?.map((note) => <small key={note}>{note}. </small>)}<details><summary>Source quotation</summary><blockquote>{action.evidence_quote}</blockquote></details></div></div>)}</div>}
    </article>)}
  </section>;
}
