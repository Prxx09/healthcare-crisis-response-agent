# Response playbooks

The bundled fallback is `response_playbooks.json`. The Playbook library now uploads, stores and indexes JSON, YAML, DOCX and searchable PDF files up to 5 MB. Review and activation are separate from indexing. See the upload workflow in the root README.

The active package supports optional disease-specific actions through `condition_actions[condition_code][alert_level]`. When present, these actions override the generic `levels` actions for plan generation and Pinecone indexing.

The original validation endpoint expects the package schema below, with markers in DOCX/PDF. The new upload endpoint also accepts ordinary prose without markers and uses the configured LLM to extract source-supported actions:

```text
PLAYBOOK_DATA_START
version: "1.1"
levels:
  monitor: &sample_actions
    - category: monitoring
      action: Review daily signals
      owner: Epidemiology lead
      timeframe: Daily
      requires_approval: false
  investigate: *sample_actions
  escalate: *sample_actions
condition_guidance:
  ili: [Review respiratory testing demand]
  age: [Review food and water exposure reports]
  dengue: [Compare recent rain with reports of standing water and mosquito breeding sites]
condition_actions:
  ili:
    monitor: []
    investigate: []
    escalate: []
PLAYBOOK_DATA_END
```

Every severity level must contain at least one shared action. `condition_actions` is optional, but when present it should define disease-specific action lists for `ili`, `age`, and `dengue` across `monitor`, `investigate`, and `escalate`. Each action requires `category`, `action`, `owner`, `timeframe`, and a Boolean `requires_approval` value. Use plain language that identifies the disease, the item to check, the location or facility scope, and the expected output.

## Pinecone RAG

The backend can optionally index the approved playbook in Pinecone and retrieve relevant shared actions, disease-specific actions, and condition guidance for the selected condition and alert level. For the bundled package, retrieval adds supporting context. Reviewed and activated uploads can supply recommended actions directly from canonical Supabase records, with source-document traceability. The existing alert approval policy still controls task issuance.

Configure `PINECONE_API_KEY` and the `PINECONE_*` settings in `backend/.env`, install backend requirements, then run from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m app.index_playbooks
```

Set `PINECONE_RAG_ENABLED=true` only after indexing. If Pinecone is disabled, unavailable, or temporarily fails, the application returns the deterministic plan and marks retrieval as `fallback`; it does not invent or remove response actions.


## Adding diseases and replacing guidance

Any explicitly named disease can be uploaded. Use canonical `condition_guidance` / `condition_actions` keys such as `measles` or `cholera`, and optional `condition_names` for display labels. Section-based files may use `disease` or `condition_code`. Activation registers new diseases and fully replaces previous rules for each included disease. Older documents remain for audit; they are not merged into recommendations or restored automatically on deactivation. Use the library's current-rule preview to demonstrate a disease before adding surveillance observations. The previously supplied Measles and Cholera demo JSON files are now accepted by the parser.
