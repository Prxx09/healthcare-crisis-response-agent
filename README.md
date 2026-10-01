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

All five tables have Row Level Security enabled. Read-only policies expose only the four synthetic reference and surveillance tables. The `alerts` table remains unavailable to anonymous clients; its write policies will be added with the Incident Commander authentication workflow.
