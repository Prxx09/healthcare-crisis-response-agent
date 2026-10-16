# Dataset Guide

## Purpose

This dataset supports the Healthcare Crisis Prediction and Response Agent. It is used to demonstrate how the system detects unusual disease-related activity, reviews supporting evidence, and prepares response recommendations for human approval.

## Data boundary

All records are synthetic and aggregated. The dataset contains no patient names, identifiers, medical records, or live clinical data. It supports demonstration and development only; it must not be used to diagnose disease or declare a real outbreak.

## Coverage

- **Time period:** 1 October 2025 to 13 October 2026 (378 days)
- **Hospitals:** 4 simulated hospitals
- **Conditions:** Influenza-like illness (ILI), acute gastroenteritis (AGE), and dengue
- **Records:** 12,096 surveillance observations and 1,512 hospital operations snapshots

The Supabase demonstration extends this base dataset through **16 October 2026** using `supabase/demo_20261014_16.sql`. It adds 96 observations and 12 operations snapshots, for **12,192** and **1,524** records respectively. The local CSV generator still creates the original 378-day base.

## Files and tables

| File / table | Purpose |
|---|---|
| `hospitals.csv` / `hospitals` | Simulated hospital name and bed capacity. |
| `conditions.csv` / `conditions` | The three monitored conditions and their syndrome groups. |
| `surveillance_observations.csv` / `surveillance_observations` | Daily aggregate counts by condition, hospital, and signal source. |
| `hospital_context.csv` / `hospital_context` | Daily staffed and occupied beds, staffing coverage, and supply readiness. |
| `alerts` | Stores future rule-based alerts and Incident Commander decisions. |

## Signal sources

- **Visits:** Syndrome-related visits or suspected-case counts.
- **Laboratory positives:** Aggregate positive test counts.
- **Pharmacy demand:** Aggregate demand indicator for ILI and AGE only.
- **Hospital context:** Synthetic operations snapshots that describe capacity during a signal. These figures do not establish its cause.

## Designed scenarios

The data includes three transparent patterns so the detection workflow can be demonstrated:

1. A sustained ILI increase in Central Hospital.
2. A short AGE increase in Lakeside Hospital.
3. A gradual increase in suspected dengue visits at East Hospital.

These patterns are illustrative signals, not simulated real-world outbreaks.

The three-day continuation provides focused agent examples: Central Hospital / ILI has increasing visits, lab positives, and pharmacy demand alongside readiness pressure; Lakeside Hospital / AGE has rising visits with flat recent laboratory positives; North Hospital / ILI has three days of partial visit reporting. Choose 16 October 2026 in the dashboard to inspect these cases.

## Reproducibility

Run `python data/generate_synthetic_surveillance.py` to regenerate the local CSV files. The generator uses a fixed seed (`42`) so results are reproducible.
