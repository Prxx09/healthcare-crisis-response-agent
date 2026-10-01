from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Any


@dataclass(frozen=True)
class SourceSignal:
    region_code: str
    region_name: str
    condition_code: str
    condition_name: str
    signal_source: str
    observation_date: str
    current_count: int
    baseline_mean: float
    percent_change: float
    z_score: float | None
    level: str


def _level(percent_change: float, z_score: float | None) -> str | None:
    if percent_change >= 100 and (z_score is None or z_score >= 2.5):
        return "escalate"
    if percent_change >= 50 and (z_score is None or z_score >= 1.5):
        return "investigate"
    if percent_change >= 25:
        return "monitor"
    return None


def detect_source_signals(rows: list[dict[str, Any]], analysis_date: date, baseline_days: int = 28) -> list[SourceSignal]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        region = row["regions"]
        condition = row["conditions"]
        grouped[(region["code"], condition["code"], row["signal_source"])].append(row)

    result: list[SourceSignal] = []
    baseline_start = analysis_date - timedelta(days=baseline_days)
    for (_, _, source), values in grouped.items():
        by_date = {date.fromisoformat(item["observation_date"]): item for item in values}
        current = by_date.get(analysis_date)
        if not current:
            continue
        baseline_counts = [
            item["observation_count"]
            for item_date, item in by_date.items()
            if baseline_start <= item_date < analysis_date
        ]
        if len(baseline_counts) < 14:
            continue
        baseline = mean(baseline_counts)
        current_count = int(current["observation_count"])
        percent_change = ((current_count - baseline) / baseline * 100) if baseline else 0.0
        deviation = stdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
        z_score = (current_count - baseline) / deviation if deviation > 0 else None
        level = _level(percent_change, z_score)
        if level:
            result.append(SourceSignal(
                region_code=current["regions"]["code"],
                region_name=current["regions"]["name"],
                condition_code=current["conditions"]["code"],
                condition_name=current["conditions"]["name"],
                signal_source=source,
                observation_date=current["observation_date"],
                current_count=current_count,
                baseline_mean=round(baseline, 2),
                percent_change=round(percent_change, 1),
                z_score=round(z_score, 2) if z_score is not None else None,
                level=level,
            ))
    return sorted(result, key=lambda item: (item.level != "escalate", -item.percent_change))


def summarise_clusters(signals: list[SourceSignal]) -> list[dict[str, Any]]:
    clusters: dict[tuple[str, str], list[SourceSignal]] = defaultdict(list)
    for signal in signals:
        clusters[(signal.region_code, signal.condition_code)].append(signal)
    summaries = []
    for _, items in clusters.items():
        sources = sorted(item.signal_source for item in items)
        highest = "escalate" if any(item.level == "escalate" for item in items) else max((item.level for item in items), key=("monitor", "investigate", "escalate").index)
        summaries.append({
            "region": items[0].region_name,
            "region_code": items[0].region_code,
            "condition": items[0].condition_name,
            "condition_code": items[0].condition_code,
            "level": highest,
            "corroborated": len(sources) >= 2,
            "supporting_sources": sources,
            "signals": [asdict(item) for item in items],
        })
    return sorted(summaries, key=lambda item: (not item["corroborated"], item["level"] != "escalate"))
