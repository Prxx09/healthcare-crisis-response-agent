from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository


async def generate_eligible_alerts(
    repository: SupabaseRepository,
    analysis_date: date,
    baseline_days: int = 28,
    hospital_code: str | None = None,
    condition_code: str | None = None,
) -> dict[str, Any]:
    start_date = analysis_date - timedelta(days=baseline_days + 1)
    rows = await repository.get_observations(
        start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code
    )
    clusters = summarise_clusters(detect_source_signals(rows, analysis_date, baseline_days))
    # Every corroborated level is reviewable. Monitor is deliberately retained
    # for human review; only Investigate/Escalate may later pass agent policy.
    eligible = [cluster for cluster in clusters if cluster["corroborated"]]
    hospitals_by_code = {item["code"]: item["id"] for item in await repository.get_hospitals()}
    conditions_by_code = {item["code"]: item["id"] for item in await repository.get_conditions()}
    created: list[dict[str, Any]] = []
    for cluster in eligible:
        result = await repository.create_alert({
            "analysis_date": analysis_date.isoformat(),
            "hospital_id": hospitals_by_code[cluster["hospital_code"]],
            "condition_id": conditions_by_code[cluster["condition_code"]],
            "alert_level": cluster["level"],
            "evidence_summary": cluster,
            "rule_version": "baseline-v1",
            "status": "pending_approval",
        })
        created.extend(result)
    return {
        "analysis_date": analysis_date.isoformat(),
        "eligible_clusters": len(eligible),
        "created": len(created),
        "existing": len(eligible) - len(created),
        "created_alerts": created,
    }
