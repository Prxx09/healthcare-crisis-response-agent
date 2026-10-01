# Healthcare Crisis Prediction and Response Agent — Data Foundation

This folder contains the first implementation assets for the project:

- `data/generate_synthetic_surveillance.py` generates one year of synthetic, aggregated surveillance data.
- `data/output/` is created by the generator and contains CSV files ready for import.
- `supabase/schema.sql` creates the Supabase tables, constraints, indexes, and baseline RLS configuration.

The dataset contains no patient-level records or real clinical data. It is designed for the three selected conditions: influenza-like illness (ILI), acute gastroenteritis (AGE), and dengue.

## Generate the dataset

```bash
python data/generate_synthetic_surveillance.py
```

The generator is deterministic (`seed=42`), so the same input produces the same dataset.

## Run the application locally

Backend:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

Dashboard:

```bash
cd frontend
npm install
npm run dev
```

The dashboard expects the API at `http://localhost:8000` by default. Copy `frontend/.env.example` to `frontend/.env.local` to override it.

The command dashboard includes a transparent seven-day scenario forecast for the selected region and condition. It compares the most recent seven days with the preceding seven days, then displays bounded best-case, expected, and worst-case visit trajectories. These scenarios are planning aids, not epidemiological predictions.

The investigation panel correlates surveillance sources across a fourteen-day review window, identifies peak activity, summarizes data quality, and adds regional rainfall, mobility, and temperature context. Regional indicators are presented as context only and are not treated as causal evidence.

Versioned response playbooks are stored in `playbooks/response_playbooks.json`. The API selects bounded investigation, readiness, coordination, and communication actions by alert level and condition. Controlled actions remain subject to Incident Commander approval.

The playbook validation endpoint accepts PDF, DOCX, YAML and JSON files up to 5 MB. It extracts and validates a normalized playbook, reports file metadata and action counts, and never replaces the active playbook automatically. See `playbooks/README.md` for the document markers and required schema.

## Import order after the Supabase project is created

1. Run `supabase/schema.sql` in Supabase SQL Editor.
2. Import `regions.csv` and `conditions.csv`.
3. Import `regional_context.csv`.
4. Import `surveillance_observations.csv`.

The initial backend uses the Supabase publishable key for read-only access to synthetic aggregate surveillance tables. Alert decisions and future write operations remain protected and will require authenticated, role-specific policies.

## Supabase project

- Project: `healthcare-crisis-response-agent`
- Region: `ap-south-1`
- Project reference: `jinbmggobfeccvqrnnze`

All five tables have Row Level Security enabled. Read-only policies expose only the four synthetic reference and surveillance tables. The `alerts` table remains unavailable to anonymous clients; the FastAPI service reads and writes it with a server-only Supabase secret.

To enable alert generation and Incident Commander decisions locally, add `SUPABASE_SECRET_KEY` to `backend/.env`. Obtain it from Supabase Project Settings → API Keys and never place it in frontend environment files or commit it to source control.
