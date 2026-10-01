"""Generate synthetic, aggregate disease-surveillance data for the healthcare agent.

The output deliberately contains no personal, clinical, or identifiable patient data.
It models multiple independent sources so downstream rules can corroborate a signal.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START_DATE = date(2025, 10, 1)
DAYS = 365
OUT = Path(__file__).parent / "output"

REGIONS = [
    ("north_district", "North District", 420_000),
    ("central_district", "Central District", 610_000),
    ("east_district", "East District", 385_000),
    ("lakeside_district", "Lakeside District", 470_000),
]

CONDITIONS = [
    ("ili", "Influenza-like Illness", "Respiratory syndrome"),
    ("age", "Acute Gastroenteritis", "Gastrointestinal syndrome"),
    ("dengue", "Dengue", "Vector-borne febrile illness"),
]


def clamp(value: float, low: float = 0.0) -> int:
    return max(int(low), round(value))


def event_multiplier(day_index: int, region_code: str, condition_code: str) -> float:
    """Inject three explainable demonstration clusters into otherwise routine variation."""
    # ILI: sustained respiratory cluster in Central District during days 62–75.
    if condition_code == "ili" and region_code == "central_district" and 62 <= day_index <= 75:
        return 1.0 + 0.10 * (day_index - 61)
    # AGE: shorter local food/water-like cluster in Lakeside District during days 35–42.
    if condition_code == "age" and region_code == "lakeside_district" and 35 <= day_index <= 42:
        return 1.0 + 0.18 * min(day_index - 34, 5)
    # Dengue: growing, weather-associated cluster in East District during days 68–89.
    if condition_code == "dengue" and region_code == "east_district" and 68 <= day_index <= 89:
        return 1.0 + 0.06 * (day_index - 67)
    return 1.0


def write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    region_rows = [
        {"code": code, "name": name, "population": population, "active": "true"}
        for code, name, population in REGIONS
    ]
    condition_rows = [
        {"code": code, "name": name, "syndrome_group": syndrome, "active": "true"}
        for code, name, syndrome in CONDITIONS
    ]
    context_rows: list[dict[str, object]] = []
    observation_rows: list[dict[str, object]] = []

    for day_index in range(DAYS):
        current_date = START_DATE + timedelta(days=day_index)
        weekly_wave = math.sin(2 * math.pi * day_index / 7)
        seasonal_wave = math.sin(2 * math.pi * day_index / 90)
        for region_index, (region_code, _, _) in enumerate(REGIONS):
            rain = clamp(30 + 18 * seasonal_wave + 8 * region_index + rng.gauss(0, 5))
            mobility = clamp(100 + 6 * weekly_wave + rng.gauss(0, 3))
            temperature = round(26 + 2.2 * seasonal_wave + 0.4 * region_index + rng.gauss(0, 0.4), 1)
            context_rows.append({
                "observation_date": current_date.isoformat(),
                "region_code": region_code,
                "rainfall_index": rain,
                "mobility_index": mobility,
                "temperature_c": temperature,
                "context_note": "Synthetic regional context",
            })

            for condition_code, _, _ in CONDITIONS:
                multiplier = event_multiplier(day_index, region_code, condition_code)
                base = {"ili": 34, "age": 22, "dengue": 8}[condition_code]
                season_adjustment = {
                    "ili": 1.0 + 0.10 * weekly_wave,
                    "age": 1.0 + 0.05 * weekly_wave,
                    "dengue": 0.85 + 0.010 * rain,
                }[condition_code]
                visit_count = clamp((base + 2 * region_index + rng.gauss(0, 3)) * season_adjustment * multiplier)
                sources = [
                    ("visits", visit_count, "Syndromic visits or suspected-case counts"),
                    ("lab_positives", clamp(visit_count * {"ili": 0.22, "age": 0.14, "dengue": 0.32}[condition_code] + rng.gauss(0, 1.5)), "Synthetic laboratory positives"),
                ]
                if condition_code in {"ili", "age"}:
                    sources.append(("pharmacy_demand", clamp(visit_count * {"ili": 1.45, "age": 1.20}[condition_code] + rng.gauss(0, 4)), "Synthetic pharmacy demand index"))
                for source, count, description in sources:
                    observation_rows.append({
                        "observation_date": current_date.isoformat(),
                        "region_code": region_code,
                        "condition_code": condition_code,
                        "signal_source": source,
                        "observation_count": count,
                        "coverage_pct": 95 if source != "pharmacy_demand" else 90,
                        "data_quality": "validated",
                        "source_note": description,
                        "synthetic_run_id": "seed-42-jul-sep-2026",
                    })

    write_csv(OUT / "regions.csv", ["code", "name", "population", "active"], region_rows)
    write_csv(OUT / "conditions.csv", ["code", "name", "syndrome_group", "active"], condition_rows)
    write_csv(OUT / "regional_context.csv", ["observation_date", "region_code", "rainfall_index", "mobility_index", "temperature_c", "context_note"], context_rows)
    write_csv(OUT / "surveillance_observations.csv", ["observation_date", "region_code", "condition_code", "signal_source", "observation_count", "coverage_pct", "data_quality", "source_note", "synthetic_run_id"], observation_rows)
    print(f"Created {len(observation_rows)} surveillance observations and {len(context_rows)} context records in {OUT}")


if __name__ == "__main__":
    main()
