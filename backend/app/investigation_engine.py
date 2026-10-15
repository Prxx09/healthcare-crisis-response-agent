from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from statistics import mean, median
from typing import Any


def _percentage_change(initial: float, recent: float) -> float | None:
    if initial == 0:
        return 0.0 if recent == 0 else None
    return round((recent - initial) / initial * 100, 1)


def _outlier_dates(ordered: list[dict[str, Any]]) -> list[str]:
    counts = [int(row["observation_count"]) for row in ordered]
    center = float(median(counts))
    mad = float(median(abs(value - center) for value in counts))
    if mad > 0:
        return [
            row["observation_date"]
            for row, value in zip(ordered, counts)
            if abs(0.6745 * (value - center) / mad) > 3.5
        ]

    # When most values are identical, retain a practical minimum difference so
    # one small integer change is not incorrectly labelled as an outlier.
    fallback_threshold = max(5.0, center * 0.5)
    return [
        row["observation_date"]
        for row, value in zip(ordered, counts)
        if abs(value - center) > fallback_threshold
    ]


def _source_summary(source: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda item: item["observation_date"])
    period_days = min(3, max(1, len(ordered) // 2))
    initial_counts = [int(row["observation_count"]) for row in ordered[:period_days]]
    recent_counts = [int(row["observation_count"]) for row in ordered[-period_days:]]
    initial_median = float(median(initial_counts))
    recent_median = float(median(recent_counts))
    latest_count = int(ordered[-1]["observation_count"])
    peak = max(ordered, key=lambda item: int(item["observation_count"]))
    outliers = _outlier_dates(ordered)
    return {
        "signal_source": source,
        "window_start_count": int(ordered[0]["observation_count"]),
        "latest_count": latest_count,
        "initial_median": round(initial_median, 1),
        "recent_median": round(recent_median, 1),
        "comparison_period_days": period_days,
        "window_change_pct": _percentage_change(initial_median, recent_median),
        "peak_count": int(peak["observation_count"]),
        "peak_date": peak["observation_date"],
        "outlier_count": len(outliers),
        "outlier_dates": outliers,
    }


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
    sources = [_source_summary(source, rows) for source, rows in sorted(by_source.items())]

    def average(field: str) -> float | None:
        values = [float(row[field]) for row in context if row.get(field) is not None]
        return round(mean(values), 1) if values else None

    context_summary = {
        "average_bed_occupancy_pct": round(mean([
            100 * float(row["occupied_beds"]) / float(row["staffed_beds"])
            for row in context if row.get("staffed_beds") and row.get("occupied_beds") is not None
        ]), 1) if any(row.get("staffed_beds") and row.get("occupied_beds") is not None for row in context) else None,
        "average_staffing_coverage_pct": average("staffing_coverage_pct"),
        "average_supply_readiness_pct": average("supply_readiness_pct"),
    }
    findings = [
        f"{len(by_source)} surveillance sources are available for correlation.",
        f"The highest combined activity occurred on {peak_date} with {peak_total} recorded observations.",
        f"{quality.get('validated', 0)} of {sum(quality.values())} records in the review window are validated.",
    ]
    for source in sources:
        if source["outlier_count"]:
            findings.append(
                f"{source['signal_source'].replace('_', ' ').title()} contains "
                f"{source['outlier_count']} unusual daily value(s); the source peak was "
                f"{source['peak_count']} on {source['peak_date']}."
            )
    if context_summary["average_bed_occupancy_pct"] is not None:
        findings.append("Hospital capacity, staffing, and supply figures describe operational readiness; they do not establish the cause of an increase in visits.")

    return {
        "analysis_date": analysis_date.isoformat(),
        "window_start": min(daily_totals),
        "peak_date": peak_date,
        "peak_total": peak_total,
        "source_comparison": sources,
        "data_quality": dict(quality),
        "hospital_context": context_summary,
        "findings": findings,
    }
