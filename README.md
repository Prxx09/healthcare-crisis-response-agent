# Healthcare Crisis Prediction and Response Agent

A public-health decision-support application that monitors synthetic surveillance feeds, detects unusual disease activity, investigates corroborating evidence, forecasts short-term planning scenarios, and prepares bounded response actions for human approval.

The project uses synthetic, aggregated data only. It is not a diagnostic system and does not declare real outbreaks.

## Project scope

The current implementation covers three conditions selected for shared data structure and manageable surveillance complexity:

| Condition | Primary signals | Context |
|---|---|---|
| Influenza-like illness (ILI) | Visits, laboratory positives, pharmacy demand | Hospital capacity and staffing |
| Acute gastroenteritis (AGE) | Visits, laboratory positives, pharmacy demand | Hospital capacity and supplies |
| Dengue | Suspected visits, laboratory positives | Hospital capacity and staffing |

The system monitors four simulated hospitals from 1 October 2025 through 16 October 2026 in Supabase. Counts represent observations at each hospital; they do not imply a geographic outbreak.

## Workflow

```mermaid
flowchart TD
    A["Synthetic surveillance feeds"] --> B["Ingestion Agent"]
    B --> C["Signal Agent"]
    C --> D["Investigation Agent"]
    C --> E["Forecast Agent"]
    C --> F["Response Agent"]
    D --> G["AI Summary Agent"]
    E --> G
    F --> G
    G --> H{"Incident Commander Gate"}
    H -->|Approve| I["Tracked response actions"]
    H -->|Dismiss| J["Decision recorded"]
    I --> K["Timeline and PDF report"]
```

The existing workflow returns a trace with component status and timing. A separate predictive agent can investigate a selected hospital and disease, save its evidence trail, and create internal verification requests. Controlled response actions remain subject to Incident Commander approval.

## Main capabilities

- Multi-source surveillance for visits, laboratory positives, pharmacy demand, and hospital context.
- Transparent baseline anomaly detection by hospital, condition, source, and date.
- Hospital-level signal investigation with source comparison, peak activity, data quality, bed occupancy, staffing coverage, and supply readiness.
- Seven-day best-case, expected, and worst-case planning scenarios.
- Robust forecast anchor based on the latest three-day median, with a minimum reported-day requirement.
- Predictive agent with bounded evidence checks, optional Groq/Hugging Face tool choice, a deterministic fallback, and explicit contradictory-evidence review.
- Persisted assessments and internal lab, surveillance, or operations verification requests; completing a request runs a fresh assessment.
- A five-minute scheduler checks due scopes and reassesses them when a newer surveillance date is available.
- Prominent forecast outlook with day-seven metrics and an optional structured LLM interpretation.
- Versioned response playbooks with owners, timeframes, approval requirements, and condition guidance.
- Optional Pinecone RAG retrieval over approved playbook guidance; deterministic playbook actions remain authoritative.
- PDF, DOCX, YAML, and JSON playbook validation.
- Deterministic evidence briefings with optional Groq or Hugging Face generation.
- Incident Commander approval and dismissal workflow.
- Assigned action tracking with due dates and completion state.
- Chronological incident timeline and downloadable PDF situation report.
- Scheduled and manual threshold email alerts with configurable recipients, severity, timezone, and delivery history.
- Configurable Incident Commander review emails sent when a corroborated signal enters the review queue.
- Role-based task assignment emails sent after Incident Commander approval, with configurable Epidemiology, Operations, and Incident Communications addresses.

## Technology stack

| Layer | Technology |
|---|---|
| Dashboard | React, TypeScript, Vite, Recharts, Lucide |
| API and orchestration | FastAPI, Microsoft Agent Framework, Pydantic, HTTPX |
| Database | Supabase Postgres |
| AI summaries | Deterministic fallback, optional Groq or Hugging Face |
| Playbooks | JSON, YAML, PDF, DOCX; optional Pinecone RAG |
| Reports | ReportLab PDF generation |
| Local workflow | Python virtual environment, npm, Make, Bash scripts, PowerShell scripts |

Docker is not required. The project runs directly with a Python virtual environment and the Vite development server.

## Repository structure

```text
backend/app/       FastAPI routes and workflow components
frontend/src/      React command dashboard
data/              Deterministic synthetic-data generator
playbooks/         Active response playbook and format guidance
supabase/          Schema, policies, seed data, and migrations
scripts/           Local setup and development commands
DATASET_GUIDE.md   Dataset coverage and design notes
WORKFLOWS_AND_FEATURES.md        Implemented workflows, features and boundaries
AGENT_PROGRESS_AND_FEATURES.md  Agent implementation and configuration status
```

## Microsoft Agent Framework orchestration

The end-to-end surveillance pipeline runs as a Microsoft Agent Framework functional workflow. Ingestion, signal detection, investigation, forecasting, response-plan retrieval, briefing generation, and the Incident Commander gate are named framework steps. Investigation and forecasting retain their parallel execution, and the existing `/api/v1/workflow` response contract is unchanged.

The framework is used for orchestration and observability; it does not replace the deterministic domain engines. Alert levels still come from transparent rules, approved actions still come from the versioned playbook, Pinecone remains supporting retrieval only, and controlled actions still require the existing human approval endpoint. No Azure resource is required for local execution. Deploying the workflow as a hosted Microsoft Foundry agent additionally requires Azure Developer CLI and a configured Foundry project.

The predictive investigation uses a bounded tool-choice loop outside the fixed surveillance workflow. When `AI_PROVIDER` is configured for Groq or Hugging Face, the model chooses one remaining read-only check at a time. Invalid or unavailable model responses fall back to a transparent policy. The agent records its choices and may create internal evidence requests in Supabase; it cannot issue clinical instructions, procurement, public warnings, or resource transfers.

The project pins `agent-framework-core==1.21.0`. Microsoft currently marks the functional workflow API as experimental, so framework upgrades should be tested before changing this version.

For concise implementation documentation, see [Workflows and Features](WORKFLOWS_AND_FEATURES.md) and [Agent Progress and Implemented Features](AGENT_PROGRESS_AND_FEATURES.md).

## Quick start

Requirements:

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- Make and Bash on Linux/macOS, or PowerShell on Windows

Install all dependencies on Linux/macOS:

```bash
make setup
```

Install all dependencies on Windows PowerShell:

```powershell
.\scripts\setup.ps1
```

Configure `backend/.env` using `backend/.env.example`. The final credential checklist is below.

Start the API and dashboard together on Linux/macOS:

```bash
make dev
```

Start the API and dashboard together on Windows PowerShell:

```powershell
.\scripts\dev.ps1
```

Open:

- Command dashboard: `http://127.0.0.1:5173/command-dashboard`
- Alert review: `http://127.0.0.1:5173/alert-review`
- Action tracker: `http://127.0.0.1:5173/action-tracker`
- Email alerts: `http://127.0.0.1:5173/email-alerts`
- Playbook library: `http://127.0.0.1:5173/playbook-library`
- API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

Individual services can be started with `make api` and `make web` on Linux/macOS. On Windows, you can also run the backend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend
```

Then run the frontend in a second PowerShell window:

```powershell
npm run dev --prefix frontend
```

### Enable Pinecone playbook RAG

After installing backend requirements and configuring the `PINECONE_*` variables in `backend/.env`, index the approved playbook from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m app.index_playbooks
```

Then set `PINECONE_RAG_ENABLED=true` and restart the API. The `/api/v1/response-plan`, workflow, briefing, and approval paths will retrieve relevant playbook context. Retrieved text is evidence only; executable actions still come from the versioned `playbooks/response_playbooks.json` and remain behind human approval.

## Useful commands

```bash
make setup   # Install pinned Python and frontend dependencies
make dev     # Run API and dashboard without Docker
make check   # Compile the backend and build the frontend
make data    # Regenerate deterministic synthetic CSV files
```

Windows PowerShell equivalents:

```powershell
.\scripts\setup.ps1
.\scripts\dev.ps1
.\scripts\check.ps1
.\.venv\Scripts\python.exe data\generate_synthetic_surveillance.py
```

## Demonstration scenarios

Use these dates in the dashboard to demonstrate known synthetic patterns:

| Date | Scope | Expected behavior |
|---|---|---|
| 10 November 2025 | Lakeside Hospital / AGE | Corroborated investigation signal |
| 15 December 2025 | Central Hospital / ILI | Corroborated investigation signal |
| 15 December 2025 | East Hospital / Dengue | Corroborated investigation signal |
| 30 September 2026 | Central Hospital / ILI | No active threshold signal |

## API overview

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/hospitals` | Available hospitals |
| `GET /api/v1/conditions` | Monitored conditions |
| `GET /api/v1/observations` | Filtered aggregate surveillance observations |
| `GET /api/v1/signals` | Rule-based signal and cluster output |
| `GET /api/v1/investigation` | Correlated cluster evidence |
| `GET /api/v1/forecast` | Seven-day planning scenarios |
| `GET /api/v1/predictive-assessments/latest` | Latest saved investigation for a hospital, disease, and date |
| `POST /api/v1/predictive-assessments` | Run and save an evidence-seeking assessment and create internal requests |
| `PATCH /api/v1/agent-followups/{id}` | Record a verification result and complete its request |
| `GET /api/v1/forecast/briefing` | Structured AI interpretation of prepared forecast scenarios |
| `GET /api/v1/response-plan` | Bounded playbook actions |
| `GET /api/v1/briefing` | Stakeholder evidence briefing |
| `GET /api/v1/workflow` | Complete workflow trace |
| `GET /api/v1/alerts` | Protected approval queue |
| `POST /api/v1/alerts/generate` | Create eligible alerts idempotently |
| `PATCH /api/v1/alerts/{id}/decision` | Approve or dismiss an alert |
| `GET /api/v1/actions` | Protected incident actions |
| `PATCH /api/v1/actions/{id}` | Assign or update an action |
| `GET /api/v1/incidents/{id}/timeline` | Incident audit timeline |
| `GET /api/v1/incidents/{id}/report.pdf` | Downloadable situation report |
| `POST /api/v1/playbooks/validate` | Validate an uploaded playbook |
| `GET /api/v1/email-alerts/dashboard` | Scheduler configuration, readiness, next run, and delivery history |
| `PUT /api/v1/email-alerts/config` | Save recipients and scheduled delivery settings |
| `POST /api/v1/email-alerts/send` | Manually evaluate thresholds and send an alert digest |

Interactive request and response schemas are available through FastAPI at `/docs`.

## Data and security boundaries

- No patient-level data, names, clinical records, or real health events are stored.
- Public browser access is read-only and limited to synthetic reference and surveillance tables.
- Alerts and incident actions have RLS enabled and no anonymous or authenticated policies.
- The Supabase secret key is used only by FastAPI and must never be placed in frontend files.
- AI providers receive prepared aggregate evidence only and cannot change alert levels or decisions.
- Groq and Hugging Face failures return a deterministic evidence summary.
- PDF and DOCX playbooks require an embedded structured section and are validated before use.
- Human approval is required before controlled response tasks are created.

## Supabase project

- Project name: `healthcare-crisis-response-agent`
- Hospital: `ap-south-1`
- Project reference: `jinbmggobfeccvqrnnze`

The database contains four simulated hospitals, three monitored conditions, 12,192 surveillance observations, and 1,524 hospital operations snapshots after applying `supabase/demo_20261014_16.sql`. Schema changes are tracked in `supabase/migrations/`. The separate demo SQL can be rerun safely on the same synthetic run ID.

For the predictive agent demo, choose **16 October 2026** and run the agent for **Central Hospital / ILI** (corroborated rise and readiness pressure), **Lakeside Hospital / AGE** (visits rise while laboratory positives remain flat), or **North Hospital / ILI** (partial visit reporting). The API backend needs `SUPABASE_SECRET_KEY` to save assessments and create internal verification requests.

## Final environment configuration

Backend variables:

| Variable | Required | Purpose |
|---|---|---|
| `SUPABASE_URL` | Yes | Supabase project API URL |
| `SUPABASE_PUBLISHABLE_KEY` | Yes | Read-only synthetic surveillance access |
| `SUPABASE_SECRET_KEY` | For protected workflows and the predictive agent | Server-only assessment, evidence-request, alert, action, timeline, and report access |
| `ALLOWED_ORIGINS` | Yes | Dashboard origins allowed by CORS |
| `BACKEND_PORT` | No | Local API port used by launch scripts; default `8000`, with `8001` and `8002` supported as alternatives |
| `AI_PROVIDER` | No | `deterministic`, `groq`, or `huggingface` |
| `GROQ_API_KEY` and `GROQ_MODEL` | When using Groq | Groq structured summary generation |
| `HUGGINGFACE_TOKEN` and `HUGGINGFACE_MODEL` | When using Hugging Face | Hugging Face structured summary generation |
| `SMTP_HOST`, `SMTP_PORT` | For email alerts | SMTP server and port, commonly port 587 with TLS |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | When SMTP requires authentication | Server-only mail credentials or app password |
| `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | For email alerts | Sender address and display name |
| `SMTP_USE_TLS` | No | Enable STARTTLS; defaults to `true` |
| `PUBLIC_APP_URL` | No | Dashboard link included in notification emails |
| `EMAIL_SCHEDULER_POLL_SECONDS` | No | Scheduler check interval; defaults to 30 seconds |
| `PINECONE_RAG_ENABLED` | No | Enable playbook retrieval-augmented context; defaults to `false` |
| `PINECONE_API_KEY` | When using Pinecone | Server-only Pinecone API key |
| `PINECONE_INDEX_NAME` | When using Pinecone | Pinecone index containing approved playbook embeddings |
| `PINECONE_INDEX_HOST` | No | Optional index host; use when preferred over index-name lookup |
| `PINECONE_NAMESPACE` | No | Namespace for approved playbook vectors |
| `PINECONE_EMBEDDING_MODEL` | No | Pinecone hosted embedding model; defaults to `llama-text-embed-v2` |
| `PINECONE_TOP_K` | No | Maximum retrieved playbook matches; defaults to 5 |

Frontend variables:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://127.0.0.1:8000` | FastAPI base URL; ports 8001 and 8002 are supported alternatives |

Never use `VITE_` variables for Supabase secret or AI-provider credentials; Vite exposes them to the browser.

## Important limitation

This repository demonstrates surveillance, investigation, coordination, and human-gated response using synthetic data. Its outputs must not be used for diagnosis, clinical decisions, public warnings, or declarations of real disease outbreaks.
