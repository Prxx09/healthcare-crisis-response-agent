# Dataset Guide

## Purpose

This dataset supports the Healthcare Crisis Prediction and Response Agent. It is used to demonstrate how the system detects unusual disease-related activity, reviews supporting evidence, and prepares response recommendations for human approval.

## Data boundary

All records are synthetic and aggregated. The dataset contains no patient names, identifiers, medical records, or live clinical data. It supports demonstration and development only; it must not be used to diagnose disease or declare a real outbreak.

## Coverage

- **Time period:** 1 October 2025 to 30 September 2026 (365 days)
- **Regions:** 4 simulated districts
- **Conditions:** Influenza-like illness (ILI), acute gastroenteritis (AGE), and dengue
- **Records:** 11,680 surveillance observations and 1,460 regional-context records

## Files and tables

| File / table | Purpose |
|---|---|
| `regions.csv` / `regions` | Simulated region name and population. |
| `conditions.csv` / `conditions` | The three monitored conditions and their syndrome groups. |
| `surveillance_observations.csv` / `surveillance_observations` | Daily aggregate counts by condition, region, and signal source. |
| `regional_context.csv` / `regional_context` | Daily contextual indicators such as rainfall, mobility, and temperature. |
| `alerts` | Stores future rule-based alerts and Incident Commander decisions. |

## Signal sources

- **Visits:** Syndrome-related visits or suspected-case counts.
- **Laboratory positives:** Aggregate positive test counts.
- **Pharmacy demand:** Aggregate demand indicator for ILI and AGE only.
- **Regional context:** Synthetic rainfall, mobility, and temperature indicators that help add context to patterns.

## Designed scenarios

The data includes three transparent patterns so the detection workflow can be demonstrated:

1. A sustained ILI increase in Central District.
2. A short AGE increase in Lakeside District.
3. A gradual dengue increase in East District, aligned with higher rainfall context.

These patterns are illustrative signals, not simulated real-world outbreaks.

## Reproducibility

Run `python data/generate_synthetic_surveillance.py` to regenerate the local CSV files. The generator uses a fixed seed (`42`) so results are reproducible.
