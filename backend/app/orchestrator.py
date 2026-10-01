from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from .briefing_engine import generate_briefing
from .config import Settings
from .forecast_engine import build_scenarios
from .investigation_engine import investigate_cluster
from .playbook_engine import select_response_plan
from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository


def _step(name: str, component: str, status: str, started: float, output: Any = None, message: str | None = None) -> dict[str, Any]:
    result = {
        "name": name,
        "component": component,
        "status": status,
        "duration_ms": round((perf_counter() - started) * 1000),
    }
    if output is not None:
        result["output"] = output
    if message:
        result["message"] = message
    return result


async def run_workflow(
    repository: SupabaseRepository,
    settings: Settings,
    analysis_date: date,
    region_code: str,
    condition_code: str,
) -> dict[str, Any]:
    workflow_started = datetime.now(timezone.utc)
    steps: list[dict[str, Any]] = []
    start_date = analysis_date - timedelta(days=28)

    timer = perf_counter()
    try:
        rows, context = await asyncio.gather(
            repository.get_observations(start_date.isoformat(), analysis_date.isoformat(), region_code, condition_code),
            repository.get_regional_context((analysis_date - timedelta(days=13)).isoformat(), analysis_date.isoformat(), region_code),
        )
        if not rows:
            raise ValueError("No surveillance observations were found for the selected scope")
        quality = Counter(row["data_quality"] for row in rows)
        steps.append(_step("ingestion", "Ingestion Agent", "completed", timer, {
            "records": len(rows),
            "sources": sorted({row["signal_source"] for row in rows}),
            "data_quality": dict(quality),
        }))
    except Exception:
        steps.append(_step("ingestion", "Ingestion Agent", "failed", timer, message="Unable to load or validate surveillance inputs"))
        for name, component in [
            ("signal", "Signal Agent"), ("investigation", "Investigation Agent"),
            ("forecast", "Forecast Agent"), ("response", "Response Agent"),
            ("briefing", "AI Summary Agent"), ("approval_gate", "Incident Commander Gate"),
        ]:
            steps.append({"name": name, "component": component, "status": "blocked", "duration_ms": 0, "message": "Blocked by ingestion failure"})
        return _workflow_result(workflow_started, "failed", steps, analysis_date, region_code, condition_code)

    selected_cluster = None
    timer = perf_counter()
    try:
        clusters = summarise_clusters(detect_source_signals(rows, analysis_date, 28))
        selected_cluster = next((item for item in clusters if item["region_code"] == region_code and item["condition_code"] == condition_code), None)
        steps.append(_step("signal", "Signal Agent", "completed", timer, {
            "level": selected_cluster["level"] if selected_cluster else "normal",
            "corroborated": selected_cluster["corroborated"] if selected_cluster else False,
            "supporting_sources": selected_cluster["supporting_sources"] if selected_cluster else [],
        }))
    except Exception:
        steps.append(_step("signal", "Signal Agent", "failed", timer, message="Signal calculation failed"))

    investigation_result = None
    timer = perf_counter()
    try:
        investigation_rows = [row for row in rows if row["observation_date"] >= (analysis_date - timedelta(days=13)).isoformat()]
        investigation_result = investigate_cluster(investigation_rows, context, analysis_date)
        steps.append(_step("investigation", "Investigation Agent", "completed", timer, {
            "peak_date": investigation_result["peak_date"],
            "peak_total": investigation_result["peak_total"],
            "sources_compared": len(investigation_result["source_comparison"]),
        }))
    except Exception:
        steps.append(_step("investigation", "Investigation Agent", "failed", timer, message="Cluster correlation failed"))

    forecast_result = None
    timer = perf_counter()
    try:
        forecast_result = build_scenarios(rows, analysis_date, 7)
        steps.append(_step("forecast", "Forecast Agent", "completed", timer, {
            "horizon_days": forecast_result["horizon_days"],
            "scenario_count": len(forecast_result["scenarios"]),
            "observed_weekly_change_pct": forecast_result["observed_weekly_change_pct"],
        }))
    except Exception:
        steps.append(_step("forecast", "Forecast Agent", "failed", timer, message="Scenario forecasting failed"))

    response_plan = None
    timer = perf_counter()
    if selected_cluster:
        try:
            response_plan = select_response_plan(condition_code, selected_cluster["level"])
            steps.append(_step("response", "Response Agent", "completed", timer, {
                "playbook_version": response_plan["playbook_version"],
                "action_count": len(response_plan["actions"]),
                "approval_required": response_plan["approval_required"],
            }))
        except Exception:
            steps.append(_step("response", "Response Agent", "failed", timer, message="Response playbook selection failed"))
    else:
        steps.append(_step("response", "Response Agent", "skipped", timer, message="No active signal requires a response plan"))

    timer = perf_counter()
    briefing_result = None
    if investigation_result and forecast_result:
        region_name = rows[0]["regions"]["name"]
        condition_name = rows[0]["conditions"]["name"]
        evidence = {
            "analysis_date": analysis_date.isoformat(), "region_name": region_name, "condition_name": condition_name,
            "cluster": selected_cluster, "investigation": investigation_result, "forecast": forecast_result,
            "response_plan": response_plan,
        }
        briefing_result = await generate_briefing(evidence, settings)
        steps.append(_step("briefing", "AI Summary Agent", "completed", timer, {
            "provider": briefing_result["provider"], "headline": briefing_result["headline"],
            "fallback_used": "fallback_reason" in briefing_result,
        }))
    else:
        steps.append(_step("briefing", "AI Summary Agent", "blocked", timer, message="Investigation or forecast evidence is unavailable"))

    timer = perf_counter()
    requires_gate = bool(selected_cluster and selected_cluster["corroborated"] and selected_cluster["level"] in {"investigate", "escalate"})
    gate_status = "waiting" if requires_gate else "not_required"
    steps.append(_step("approval_gate", "Incident Commander Gate", gate_status, timer, {
        "decision_required": requires_gate,
        "automatic_actions_issued": False,
    }, "Human approval is required before controlled actions are issued" if requires_gate else None))

    failed = any(step["status"] == "failed" for step in steps)
    workflow_status = "partial" if failed else "waiting_for_approval" if requires_gate else "completed"
    return _workflow_result(workflow_started, workflow_status, steps, analysis_date, region_code, condition_code)


def _workflow_result(started_at: datetime, status: str, steps: list[dict[str, Any]], analysis_date: date, region_code: str, condition_code: str) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc)
    return {
        "workflow_id": str(uuid4()),
        "status": status,
        "analysis_date": analysis_date.isoformat(),
        "region_code": region_code,
        "condition_code": condition_code,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000),
        "steps": steps,
    }
