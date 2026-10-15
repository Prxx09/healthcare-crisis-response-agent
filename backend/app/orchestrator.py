from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from agent_framework import step, workflow

from .briefing_engine import generate_briefing
from .config import Settings
from .forecast_engine import build_scenarios
from .investigation_engine import investigate_cluster
from .pinecone_rag import select_response_plan_with_rag
from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository


@dataclass(frozen=True)
class CrisisWorkflowRequest:
    """Request-scoped dependencies and selection passed through Agent Framework."""

    repository: SupabaseRepository
    settings: Settings
    analysis_date: date
    hospital_code: str
    condition_code: str


def _trace(
    name: str,
    component: str,
    status: str,
    started: float,
    output: Any = None,
    message: str | None = None,
) -> dict[str, Any]:
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


def _scope_replay_key(payload: dict[str, Any]) -> str:
    """Give concurrent framework steps a stable identity for replay/checkpointing."""

    return (
        f"{payload['analysis_date'].isoformat()}|"
        f"{payload['hospital_code']}|{payload['condition_code']}"
    )


@step(name="crisiswatch_ingestion_agent")
async def ingestion_agent(request: CrisisWorkflowRequest) -> dict[str, Any]:
    timer = perf_counter()
    start_date = request.analysis_date - timedelta(days=28)
    try:
        rows, context = await asyncio.gather(
            request.repository.get_observations(
                start_date.isoformat(), request.analysis_date.isoformat(), request.hospital_code, request.condition_code
            ),
            request.repository.get_hospital_context(
                (request.analysis_date - timedelta(days=13)).isoformat(),
                request.analysis_date.isoformat(),
                request.hospital_code,
            ),
        )
        if not rows:
            raise ValueError("No surveillance observations were found for the selected scope")
        quality = Counter(row["data_quality"] for row in rows)
        return {
            "ok": True,
            "rows": rows,
            "context": context,
            "trace": _trace(
                "ingestion",
                "Ingestion Agent",
                "completed",
                timer,
                {
                    "records": len(rows),
                    "sources": sorted({row["signal_source"] for row in rows}),
                    "data_quality": dict(quality),
                },
            ),
        }
    except Exception:
        return {
            "ok": False,
            "rows": [],
            "context": [],
            "trace": _trace(
                "ingestion",
                "Ingestion Agent",
                "failed",
                timer,
                message="Unable to load or validate surveillance inputs",
            ),
        }


@step(name="crisiswatch_signal_agent")
async def signal_agent(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    try:
        clusters = summarise_clusters(detect_source_signals(payload["rows"], payload["analysis_date"], 28))
        selected_cluster = next(
            (
                item
                for item in clusters
                if item["hospital_code"] == payload["hospital_code"]
                and item["condition_code"] == payload["condition_code"]
            ),
            None,
        )
        return {
            "cluster": selected_cluster,
            "trace": _trace(
                "signal",
                "Signal Agent",
                "completed",
                timer,
                {
                    "level": selected_cluster["level"] if selected_cluster else "normal",
                    "corroborated": selected_cluster["corroborated"] if selected_cluster else False,
                    "supporting_sources": selected_cluster["supporting_sources"] if selected_cluster else [],
                },
            ),
        }
    except Exception:
        return {
            "cluster": None,
            "trace": _trace(
                "signal", "Signal Agent", "failed", timer, message="Signal calculation failed"
            ),
        }


@step(name="crisiswatch_investigation_agent", replay_key=_scope_replay_key)
async def investigation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    try:
        window_start = (payload["analysis_date"] - timedelta(days=13)).isoformat()
        investigation_rows = [row for row in payload["rows"] if row["observation_date"] >= window_start]
        result = investigate_cluster(investigation_rows, payload["context"], payload["analysis_date"])
        return {
            "result": result,
            "trace": _trace(
                "investigation",
                "Investigation Agent",
                "completed",
                timer,
                {
                    "peak_date": result["peak_date"],
                    "peak_total": result["peak_total"],
                    "sources_compared": len(result["source_comparison"]),
                },
            ),
        }
    except Exception:
        return {
            "result": None,
            "trace": _trace(
                "investigation", "Investigation Agent", "failed", timer, message="Cluster correlation failed"
            ),
        }


@step(name="crisiswatch_forecast_agent", replay_key=_scope_replay_key)
async def forecast_agent(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    try:
        result = build_scenarios(payload["rows"], payload["analysis_date"], 7)
        return {
            "result": result,
            "trace": _trace(
                "forecast",
                "Forecast Agent",
                "completed",
                timer,
                {
                    "horizon_days": result["horizon_days"],
                    "scenario_count": len(result["scenarios"]),
                    "observed_weekly_change_pct": result["observed_weekly_change_pct"],
                },
            ),
        }
    except Exception:
        return {
            "result": None,
            "trace": _trace(
                "forecast", "Forecast Agent", "failed", timer, message="Scenario forecasting failed"
            ),
        }


@step(name="crisiswatch_response_agent")
async def response_agent(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    cluster = payload["cluster"]
    if not cluster:
        return {
            "result": None,
            "trace": _trace(
                "response",
                "Response Agent",
                "skipped",
                timer,
                message="No active signal requires a response plan",
            ),
        }
    try:
        result = await select_response_plan_with_rag(
            payload["settings"],
            payload["condition_code"],
            cluster["level"],
            query_context=f"Hospital {payload['hospital_code']}; analysis date {payload['analysis_date'].isoformat()}",
        )
        return {
            "result": result,
            "trace": _trace(
                "response",
                "Response Agent",
                "completed",
                timer,
                {
                    "playbook_version": result["playbook_version"],
                    "action_count": len(result["actions"]),
                    "approval_required": result["approval_required"],
                },
            ),
        }
    except Exception:
        return {
            "result": None,
            "trace": _trace(
                "response", "Response Agent", "failed", timer, message="Response playbook selection failed"
            ),
        }


@step(name="crisiswatch_summary_agent")
async def summary_agent(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    investigation = payload["investigation"]
    forecast = payload["forecast"]
    if not investigation or not forecast:
        return {
            "result": None,
            "trace": _trace(
                "briefing",
                "AI Summary Agent",
                "blocked",
                timer,
                message="Investigation or forecast evidence is unavailable",
            ),
        }

    evidence = {
        "analysis_date": payload["analysis_date"].isoformat(),
        "hospital_name": payload["rows"][0]["hospitals"]["name"],
        "condition_name": payload["rows"][0]["conditions"]["name"],
        "cluster": payload["cluster"],
        "investigation": investigation,
        "forecast": forecast,
        "response_plan": payload["response_plan"],
    }
    result = await generate_briefing(evidence, payload["settings"])
    return {
        "result": result,
        "trace": _trace(
            "briefing",
            "AI Summary Agent",
            "completed",
            timer,
            {
                "provider": result["provider"],
                "headline": result["headline"],
                "fallback_used": "fallback_reason" in result,
            },
        ),
    }


@step(name="crisiswatch_incident_commander_gate")
async def incident_commander_gate(payload: dict[str, Any]) -> dict[str, Any]:
    timer = perf_counter()
    cluster = payload["cluster"]
    requires_gate = bool(
        cluster and cluster["corroborated"] and cluster["level"] in {"investigate", "escalate"}
    )
    return {
        "required": requires_gate,
        "trace": _trace(
            "approval_gate",
            "Incident Commander Gate",
            "waiting" if requires_gate else "not_required",
            timer,
            {"decision_required": requires_gate, "automatic_actions_issued": False},
            "Human approval is required before controlled actions are issued" if requires_gate else None,
        ),
    }


@workflow(
    name="crisiswatch_surveillance_workflow",
    description="Grounded public-health surveillance workflow with a human approval boundary.",
)
async def crisiswatch_surveillance_workflow(request: CrisisWorkflowRequest) -> dict[str, Any]:
    """Execute the existing CrisisWatch pipeline through Microsoft Agent Framework."""

    workflow_started = datetime.now(timezone.utc)
    ingestion = await ingestion_agent(request)
    steps = [ingestion["trace"]]
    if not ingestion["ok"]:
        for name, component in [
            ("signal", "Signal Agent"),
            ("investigation", "Investigation Agent"),
            ("forecast", "Forecast Agent"),
            ("response", "Response Agent"),
            ("briefing", "AI Summary Agent"),
            ("approval_gate", "Incident Commander Gate"),
        ]:
            steps.append(
                {
                    "name": name,
                    "component": component,
                    "status": "blocked",
                    "duration_ms": 0,
                    "message": "Blocked by ingestion failure",
                }
            )
        return _workflow_result(
            workflow_started,
            "failed",
            steps,
            request.analysis_date,
            request.hospital_code,
            request.condition_code,
        )

    shared = {
        "rows": ingestion["rows"],
        "context": ingestion["context"],
        "analysis_date": request.analysis_date,
        "hospital_code": request.hospital_code,
        "condition_code": request.condition_code,
        "settings": request.settings,
    }
    signal = await signal_agent(shared)
    investigation, forecast = await asyncio.gather(investigation_agent(shared), forecast_agent(shared))
    response = await response_agent({**shared, "cluster": signal["cluster"]})
    briefing = await summary_agent(
        {
            **shared,
            "cluster": signal["cluster"],
            "investigation": investigation["result"],
            "forecast": forecast["result"],
            "response_plan": response["result"],
        }
    )
    gate = await incident_commander_gate({"cluster": signal["cluster"]})

    steps.extend(
        [
            signal["trace"],
            investigation["trace"],
            forecast["trace"],
            response["trace"],
            briefing["trace"],
            gate["trace"],
        ]
    )
    failed = any(item["status"] == "failed" for item in steps)
    workflow_status = "partial" if failed else "waiting_for_approval" if gate["required"] else "completed"
    return _workflow_result(
        workflow_started,
        workflow_status,
        steps,
        request.analysis_date,
        request.hospital_code,
        request.condition_code,
    )


async def run_workflow(
    repository: SupabaseRepository,
    settings: Settings,
    analysis_date: date,
    hospital_code: str,
    condition_code: str,
) -> dict[str, Any]:
    """Compatibility adapter retaining the API's original call signature."""

    runtime = crisiswatch_surveillance_workflow.build()
    result = await runtime.run(
        CrisisWorkflowRequest(
            repository=repository,
            settings=settings,
            analysis_date=analysis_date,
            hospital_code=hospital_code,
            condition_code=condition_code,
        )
    )
    outputs = result.get_outputs()
    if len(outputs) != 1 or not isinstance(outputs[0], dict):
        raise RuntimeError("Microsoft Agent Framework returned an invalid workflow result")
    return outputs[0]


def _workflow_result(
    started_at: datetime,
    status: str,
    steps: list[dict[str, Any]],
    analysis_date: date,
    hospital_code: str,
    condition_code: str,
) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc)
    return {
        "workflow_id": str(uuid4()),
        "status": status,
        "analysis_date": analysis_date.isoformat(),
        "hospital_code": hospital_code,
        "condition_code": condition_code,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": round((completed_at - started_at).total_seconds() * 1000),
        "steps": steps,
    }
