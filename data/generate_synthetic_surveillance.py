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
DAYS = 378
OUT = Path(__file__).parent / "output"

HOSPITALS = [
    ("north_hospital", "North Hospital", 120),
    ("central_hospital", "Central Hospital", 180),
    ("east_hospital", "East Hospital", 110),
    ("lakeside_hospital", "Lakeside Hospital", 140),
]

CONDITIONS = [
    ("ili", "Influenza-like Illness", "Respiratory syndrome"),
    ("age", "Acute Gastroenteritis", "Gastrointestinal syndrome"),
    ("dengue", "Dengue", "Vector-borne febrile illness"),
]


def clamp(value: float, low: float = 0.0) -> int:
    return max(int(low), round(value))


def event_multiplier(day_index: int, hospital_code: str, condition_code: str) -> float:
    """Inject three explainable demonstration clusters into otherwise routine variation."""
    # ILI: sustained respiratory cluster in Central Hospital during days 62–75.
    if condition_code == "ili" and hospital_code == "central_hospital" and 62 <= day_index <= 75:
        return 1.0 + 0.10 * (day_index - 61)
    # AGE: shorter increase in gastrointestinal presentations at Lakeside Hospital.
    if condition_code == "age" and hospital_code == "lakeside_hospital" and 35 <= day_index <= 42:
        return 1.0 + 0.18 * min(day_index - 34, 5)
    # Dengue: growing increase in suspected dengue presentations at East Hospital.
    if condition_code == "dengue" and hospital_code == "east_hospital" and 68 <= day_index <= 89:
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

    hospital_rows = [
        {"code": code, "name": name, "bed_capacity": bed_capacity, "active": "true"}
        for code, name, bed_capacity in HOSPITALS
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
        for hospital_index, (hospital_code, _, bed_capacity) in enumerate(HOSPITALS):
            staffed_beds = min(bed_capacity, max(1, round(bed_capacity * (0.85 + 0.04 * weekly_wave))))
            occupied_beds = min(staffed_beds, max(0, round(staffed_beds * (0.65 + 0.08 * seasonal_wave + rng.gauss(0, 0.025)))))
            staffing_coverage_pct = min(100, max(0, round(90 + 4 * weekly_wave + rng.gauss(0, 2), 1)))
            supply_readiness_pct = min(100, max(0, round(88 + 3 * seasonal_wave + rng.gauss(0, 2), 1)))
            context_rows.append({
                "observation_date": current_date.isoformat(),
                "hospital_code": hospital_code,
                "staffed_beds": staffed_beds,
                "occupied_beds": occupied_beds,
                "staffing_coverage_pct": staffing_coverage_pct,
                "supply_readiness_pct": supply_readiness_pct,
                "context_note": "Synthetic hospital operations snapshot",
            })

            for condition_code, _, _ in CONDITIONS:
                multiplier = event_multiplier(day_index, hospital_code, condition_code)
                base = {"ili": 34, "age": 22, "dengue": 8}[condition_code]
                season_adjustment = {
                    "ili": 1.0 + 0.10 * weekly_wave,
                    "age": 1.0 + 0.05 * weekly_wave,
                    "dengue": 1.0 + 0.10 * seasonal_wave,
                }[condition_code]
                visit_count = clamp((base + 2 * hospital_index + rng.gauss(0, 3)) * season_adjustment * multiplier)
                sources = [
                    ("visits", visit_count, "Syndromic visits or suspected-case counts"),
                    ("lab_positives", clamp(visit_count * {"ili": 0.22, "age": 0.14, "dengue": 0.32}[condition_code] + rng.gauss(0, 1.5)), "Synthetic laboratory positives"),
                ]
                if condition_code in {"ili", "age"}:
                    sources.append(("pharmacy_demand", clamp(visit_count * {"ili": 1.45, "age": 1.20}[condition_code] + rng.gauss(0, 4)), "Synthetic pharmacy demand index"))
                for source, count, description in sources:
                    observation_rows.append({
                        "observation_date": current_date.isoformat(),
                        "hospital_code": hospital_code,
                        "condition_code": condition_code,
                        "signal_source": source,
                        "observation_count": count,
                        "coverage_pct": 95 if source != "pharmacy_demand" else 90,
                        "data_quality": "validated",
                        "source_note": description,
                        "synthetic_run_id": "seed-42-oct-2025-oct-2026",
                    })

    write_csv(OUT / "hospitals.csv", ["code", "name", "bed_capacity", "active"], hospital_rows)
    write_csv(OUT / "conditions.csv", ["code", "name", "syndrome_group", "active"], condition_rows)
    write_csv(OUT / "hospital_context.csv", ["observation_date", "hospital_code", "staffed_beds", "occupied_beds", "staffing_coverage_pct", "supply_readiness_pct", "context_note"], context_rows)
    write_csv(OUT / "surveillance_observations.csv", ["observation_date", "hospital_code", "condition_code", "signal_source", "observation_count", "coverage_pct", "data_quality", "source_note", "synthetic_run_id"], observation_rows)
    print(f"Created {len(observation_rows)} surveillance observations and {len(context_rows)} context records in {OUT}")


if __name__ == "__main__":
    main()
