# CrisisWatch Workflows and Features

## Purpose

CrisisWatch is a decision-support application for synthetic, aggregate public-health surveillance. It detects unusual activity, prepares bounded demand scenarios and approved response actions, and requires human approval before operational tasks are created.

## Surveillance Workflow

The workflow is orchestrated with Microsoft Agent Framework and exposed through FastAPI.

1. **Ingestion Agent** — reads normalized surveillance observations and hospital context from Supabase, verifies that records exist, and summarizes source coverage and data quality.
2. **Signal Agent** — calculates a 28-day baseline, percentage change and z-score for each source; assigns `monitor`, `investigate` or `escalate`; and checks multi-source corroboration.
3. **Investigation Agent** — compares 14-day source activity, identifies peak activity and unusual daily values, and summarizes hospital bed occupancy, staffing coverage, and supply readiness.
4. **Forecast Agent** — creates bounded best-case, expected and upper-stress visit scenarios. The default horizon is seven days. These are planning scenarios, not epidemiological predictions.
5. **Response Agent** — selects condition- and alert-level actions from the approved versioned JSON playbook. Optional Pinecone retrieval adds supporting playbook context but cannot replace or create actions.
6. **AI Summary Agent** — prepares a grounded evidence briefing through Groq or Hugging Face when configured. Invalid or unavailable model output falls back to a deterministic briefing.
7. **Incident Commander Gate** — requires review for corroborated `investigate` and `escalate` signals. No controlled action is issued automatically.

Investigation and forecasting execute concurrently after signal analysis. The workflow returns step status and timing through `GET /api/v1/workflow`.

## Alert and Action Workflow

1. An eligible corroborated signal is submitted to the review queue.
2. An alert is created idempotently with status `pending_approval`.
3. The Incident Commander approves or dismisses the alert.
4. Approval creates tracked actions from the authoritative playbook; dismissal creates no actions.
5. Actions can move through `pending`, `in_progress`, `completed` or `cancelled`.
6. Alert decisions and action changes appear in the incident timeline and PDF situation report.

## Notification Workflow

- Scheduled or manual threshold reports are sent through configured SMTP settings.
- Newly created review alerts can notify the configured Incident Commander address.
- Approved actions can notify configured owner-role addresses.
- Delivery, failure and skipped-recipient results are stored in Supabase.

## Playbook and RAG Workflow

- `playbooks/response_playbooks.json` is the authoritative source of executable actions.
- JSON, YAML, PDF and DOCX files can be uploaded for validation only; upload does not activate a playbook.
- When enabled, Pinecone indexes approved actions and guidance and filters retrieval by playbook version, condition and alert level.
- If Pinecone is disabled or unavailable, deterministic playbook selection continues normally.

## Implemented Interface Features

- Hospital, condition and analysis-date filters
- Surveillance and scenario charts
- Evidence review and grounded AI briefing dropdown
- Recommended response playbook display
- Incident Commander alert review
- Action assignment and status tracking
- Incident timeline and PDF report download
- Email schedule, recipient and delivery-history management
- Playbook file validation
- Loading indicators and temporary bottom notifications

## Boundaries

- The data is synthetic and aggregated; no patient-level records are used.
- The application does not diagnose disease or declare outbreaks.
- Forecasts are bounded demand scenarios, not outbreak probabilities.
- Hospital operations snapshots show capacity; they do not explain why disease activity changed.
- No map/GeoJSON interface, frontend authentication, application RBAC, Microsoft Graph integration or automatic playbook activation is implemented.
- The workflow runs locally with Microsoft Agent Framework Core. It is not deployed as a hosted Microsoft Foundry agent.
