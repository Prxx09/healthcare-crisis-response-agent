from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean
from typing import Any


def build_scenarios(rows: list[dict[str, Any]], analysis_date: date, horizon_days: int = 7) -> dict[str, Any]:
    """Build bounded, explainable scenarios from recent visit counts."""
    visits_by_date: dict[date, int] = defaultdict(int)
    for row in rows:
        if row["signal_source"] == "visits":
            visits_by_date[date.fromisoformat(row["observation_date"])] += int(row["observation_count"])

    latest = visits_by_date.get(analysis_date)
    if latest is None:
        raise ValueError("No visit observation exists for the selected analysis date")

    recent = [visits_by_date.get(analysis_date - timedelta(days=offset), 0) for offset in range(1, 8)]
    previous = [visits_by_date.get(analysis_date - timedelta(days=offset), 0) for offset in range(8, 15)]
    recent_mean = mean(recent)
    previous_mean = mean(previous)
    observed_growth = (recent_mean - previous_mean) / previous_mean if previous_mean else 0.0
    expected_rate = max(-0.08, min(0.12, observed_growth / 7))
    rates = {
        "best_case": max(-0.15, expected_rate - 0.05),
        "expected": expected_rate,
        "worst_case": min(0.25, expected_rate + 0.08),
    }

    scenarios = []
    for name, daily_rate in rates.items():
        points = []
        for day_number in range(horizon_days + 1):
            projected = round(latest * ((1 + daily_rate) ** day_number))
            points.append({
                "date": (analysis_date + timedelta(days=day_number)).isoformat(),
                "projected_visits": max(0, projected),
            })
        scenarios.append({
            "scenario": name,
            "daily_change_pct": round(daily_rate * 100, 1),
            "points": points,
        })

    return {
        "analysis_date": analysis_date.isoformat(),
        "horizon_days": horizon_days,
        "latest_visits": latest,
        "observed_weekly_change_pct": round(observed_growth * 100, 1),
        "scenarios": scenarios,
        "assumptions": [
            "Visit counts are used as the primary demand indicator.",
            "Recent seven-day activity is compared with the preceding seven days.",
            "Daily growth is bounded to avoid implausible short-term projections.",
            "Scenarios support planning and are not epidemiological predictions.",
        ],
    }
