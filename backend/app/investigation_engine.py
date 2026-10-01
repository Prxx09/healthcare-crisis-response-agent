from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import mean
from typing import Any


def investigate_cluster(observations: list[dict[str, Any]], context: list[dict[str, Any]], analysis_date: date) -> dict[str, Any]:
    if not observations:
        raise ValueError("No surveillance observations exist for the selected scope")

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    daily_totals: dict[str, int] = defaultdict(int)
    quality = Counter()
    for row in observations:
        by_source[row["signal_source"]].append(row)
        daily_totals[row["observation_date"]] += int(row["observation_count"])
        quality[row["data_quality"]] += 1

    peak_date, peak_total = max(daily_totals.items(), key=lambda item: item[1])
    sources = []
    for source, rows in sorted(by_source.items()):
        ordered = sorted(rows, key=lambda item: item["observation_date"])
        first, latest = ordered[0], ordered[-1]
        first_count = int(first["observation_count"])
        latest_count = int(latest["observation_count"])
        change = ((latest_count - first_count) / first_count * 100) if first_count else 0.0
        sources.append({
            "signal_source": source,
            "window_start_count": first_count,
            "latest_count": latest_count,
            "window_change_pct": round(change, 1),
        })

    def average(field: str) -> float | None:
        values = [float(row[field]) for row in context if row.get(field) is not None]
        return round(mean(values), 1) if values else None

    context_summary = {
        "average_rainfall_index": average("rainfall_index"),
        "average_mobility_index": average("mobility_index"),
        "average_temperature_c": average("temperature_c"),
    }
    findings = [
        f"{len(by_source)} surveillance sources are available for correlation.",
        f"The highest combined activity occurred on {peak_date} with {peak_total} recorded observations.",
        f"{quality.get('validated', 0)} of {sum(quality.values())} records in the review window are validated.",
    ]
    if context_summary["average_rainfall_index"] is not None:
        findings.append("Regional environmental and mobility indicators are included as supporting context, not causal evidence.")

    return {
        "analysis_date": analysis_date.isoformat(),
        "window_start": min(daily_totals),
        "peak_date": peak_date,
        "peak_total": peak_total,
        "source_comparison": sources,
        "data_quality": dict(quality),
        "regional_context": context_summary,
        "findings": findings,
    }
