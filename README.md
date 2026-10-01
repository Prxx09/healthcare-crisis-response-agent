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

## Import order after the Supabase project is created

1. Run `supabase/schema.sql` in Supabase SQL Editor.
2. Import `regions.csv` and `conditions.csv`.
3. Import `regional_context.csv`.
4. Import `surveillance_observations.csv`.

The application backend will use a server-only Supabase key for ingestion and analytics. No service key belongs in the dashboard/frontend.

## Supabase project

- Project: `healthcare-crisis-response-agent`
- Region: `ap-south-1`
- Project reference: `jinbmggobfeccvqrnnze`

All five tables have Row Level Security enabled. The current database is intentionally backend-only: it has no browser-access policies yet. When dashboard authentication is added, policies will be defined around authenticated roles and the Incident Commander approval workflow.
