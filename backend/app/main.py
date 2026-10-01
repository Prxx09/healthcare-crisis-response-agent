import asyncio
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx

from .config import get_settings
from .briefing_engine import generate_briefing
from .action_engine import action_rows
from .forecast_engine import build_scenarios
from .investigation_engine import investigate_cluster
from .models import ActionUpdateRequest, AlertDecisionRequest, AlertGenerationRequest
from .playbook_documents import MAX_FILE_BYTES, SUPPORTED_EXTENSIONS, parse_playbook_document
from .playbook_engine import select_response_plan
from .orchestrator import run_workflow
from .reporting import build_situation_report, build_timeline
from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository

settings = get_settings()
app = FastAPI(title="Healthcare Crisis Prediction and Response Agent API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "healthcare-crisis-agent-api"}


@app.get("/api/v1/regions")
async def regions() -> list[dict]:
    return await SupabaseRepository().get_regions()


@app.get("/api/v1/conditions")
async def conditions() -> list[dict]:
    return await SupabaseRepository().get_conditions()


@app.get("/api/v1/observations")
async def observations(
    start_date: date = Query(...),
    end_date: date = Query(...),
    region_code: str | None = None,
    condition_code: str | None = None,
) -> list[dict]:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    try:
        return await SupabaseRepository().get_observations(start_date.isoformat(), end_date.isoformat(), region_code, condition_code)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read surveillance data") from error


@app.get("/api/v1/signals")
async def signals(analysis_date: date = Query(default=date(2026, 9, 30)), baseline_days: int = Query(default=28, ge=14, le=60)) -> dict:
    start_date = analysis_date - timedelta(days=baseline_days + 1)
    try:
        rows = await SupabaseRepository().get_observations(start_date.isoformat(), analysis_date.isoformat())
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read surveillance data") from error
    source_signals = detect_source_signals(rows, analysis_date, baseline_days)
    return {
        "analysis_date": analysis_date,
        "baseline_days": baseline_days,
        "source_signal_count": len(source_signals),
        "clusters": summarise_clusters(source_signals),
    }


@app.get("/api/v1/forecast")
async def forecast(
    analysis_date: date = Query(...),
    region_code: str = Query(...),
    condition_code: str = Query(...),
    horizon_days: int = Query(default=7, ge=3, le=14),
) -> dict:
    start_date = analysis_date - timedelta(days=15)
    try:
        rows = await SupabaseRepository().get_observations(
            start_date.isoformat(), analysis_date.isoformat(), region_code, condition_code
        )
        return build_scenarios(rows, analysis_date, horizon_days)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to build forecast scenarios") from error


@app.get("/api/v1/investigation")
async def investigation(
    analysis_date: date = Query(...),
    region_code: str = Query(...),
    condition_code: str = Query(...),
    window_days: int = Query(default=14, ge=7, le=30),
) -> dict:
    start_date = analysis_date - timedelta(days=window_days - 1)
    repository = SupabaseRepository()
    try:
        rows, context = await asyncio.gather(
            repository.get_observations(start_date.isoformat(), analysis_date.isoformat(), region_code, condition_code),
            repository.get_regional_context(start_date.isoformat(), analysis_date.isoformat(), region_code),
        )
        return investigate_cluster(rows, context, analysis_date)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to investigate the selected cluster") from error


@app.get("/api/v1/response-plan")
async def response_plan(
    condition_code: str = Query(...),
    alert_level: str = Query(...),
) -> dict:
    try:
        return select_response_plan(condition_code, alert_level)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/briefing")
async def briefing(
    analysis_date: date = Query(...),
    region_code: str = Query(...),
    condition_code: str = Query(...),
) -> dict:
    start_date = analysis_date - timedelta(days=28)
    repository = SupabaseRepository()
    try:
        rows, context = await asyncio.gather(
            repository.get_observations(start_date.isoformat(), analysis_date.isoformat(), region_code, condition_code),
            repository.get_regional_context((analysis_date - timedelta(days=13)).isoformat(), analysis_date.isoformat(), region_code),
        )
        clusters = summarise_clusters(detect_source_signals(rows, analysis_date, 28))
        cluster = next((item for item in clusters if item["region_code"] == region_code and item["condition_code"] == condition_code), None)
        investigation_rows = [row for row in rows if row["observation_date"] >= (analysis_date - timedelta(days=13)).isoformat()]
        investigation_result = investigate_cluster(investigation_rows, context, analysis_date)
        forecast_result = build_scenarios(rows, analysis_date, 7)
        region_name = rows[0]["regions"]["name"] if rows else region_code
        condition_name = rows[0]["conditions"]["name"] if rows else condition_code
        evidence = {
            "analysis_date": analysis_date.isoformat(),
            "region_name": region_name,
            "condition_name": condition_name,
            "cluster": cluster,
            "investigation": investigation_result,
            "forecast": forecast_result,
            "response_plan": select_response_plan(condition_code, cluster["level"]) if cluster else None,
        }
        return await generate_briefing(evidence, settings)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare briefing evidence") from error


@app.get("/api/v1/workflow")
async def workflow(
    analysis_date: date = Query(...),
    region_code: str = Query(...),
    condition_code: str = Query(...),
) -> dict:
    return await run_workflow(SupabaseRepository(), settings, analysis_date, region_code, condition_code)


@app.get("/api/v1/playbooks")
async def playbooks() -> dict:
    active = select_response_plan("ili", "monitor")
    return {
        "active_version": active["playbook_version"],
        "supported_formats": sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS),
        "max_file_bytes": MAX_FILE_BYTES,
        "validation_only": True,
    }


@app.post("/api/v1/playbooks/validate")
async def validate_playbook(request: Request, filename: str = Query(..., min_length=1, max_length=180)) -> dict:
    data = await request.body()
    try:
        return parse_playbook_document(filename, data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/alerts")
async def alerts(status: str | None = Query(default="pending_approval")) -> list[dict]:
    try:
        return await SupabaseRepository().get_alerts(status)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read alerts") from error


@app.get("/api/v1/actions")
async def actions(status: str | None = None) -> list[dict]:
    try:
        return await SupabaseRepository().get_actions(status)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read incident actions") from error


@app.get("/api/v1/incidents/{alert_id}/timeline")
async def incident_timeline(alert_id: int) -> dict:
    repository = SupabaseRepository()
    try:
        alert, action_rows_result = await asyncio.gather(repository.get_alert(alert_id), repository.get_actions(alert_id=alert_id))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to build incident timeline") from error
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert_id": alert_id, "events": build_timeline(alert, action_rows_result)}


@app.get("/api/v1/incidents/{alert_id}/report.pdf")
async def situation_report(alert_id: int) -> StreamingResponse:
    repository = SupabaseRepository()
    try:
        alert, action_rows_result = await asyncio.gather(repository.get_alert(alert_id), repository.get_actions(alert_id=alert_id))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare situation report") from error
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    pdf = build_situation_report(alert, action_rows_result)
    filename = f"situation-report-alert-{alert_id}.pdf"
    return StreamingResponse(BytesIO(pdf), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/v1/alerts/generate")
async def generate_alerts(request: AlertGenerationRequest) -> dict:
    repository = SupabaseRepository()
    start_date = request.analysis_date - timedelta(days=request.baseline_days + 1)
    try:
        rows = await repository.get_observations(
            start_date.isoformat(), request.analysis_date.isoformat(), request.region_code, request.condition_code
        )
        clusters = summarise_clusters(detect_source_signals(rows, request.analysis_date, request.baseline_days))
        regions_by_code = {item["code"]: item["id"] for item in await repository.get_regions()}
        conditions_by_code = {item["code"]: item["id"] for item in await repository.get_conditions()}
        created = []
        for cluster in clusters:
            if not cluster["corroborated"] or cluster["level"] == "monitor":
                continue
            result = await repository.create_alert({
                "analysis_date": request.analysis_date.isoformat(),
                "region_id": regions_by_code[cluster["region_code"]],
                "condition_id": conditions_by_code[cluster["condition_code"]],
                "alert_level": cluster["level"],
                "evidence_summary": cluster,
                "rule_version": "baseline-v1",
                "status": "pending_approval",
            })
            created.extend(result)
        return {"analysis_date": request.analysis_date, "eligible_clusters": len([c for c in clusters if c["corroborated"] and c["level"] != "monitor"]), "created": len(created)}
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to generate alerts") from error


@app.patch("/api/v1/alerts/{alert_id}/decision")
async def decide_alert(alert_id: int, request: AlertDecisionRequest) -> dict:
    repository = SupabaseRepository()
    try:
        alert = await repository.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        decision_time = datetime.now(timezone.utc)
        result = await repository.decide_alert(alert_id, {
            "status": request.status,
            "reviewed_by": request.reviewer_name.strip(),
            "review_note": request.note.strip() if request.note else None,
            "approved_at": decision_time.isoformat(),
        })
        created_actions = []
        if result and request.status == "approved":
            plan = select_response_plan(alert["conditions"]["code"], alert["alert_level"])
            created_actions = await repository.create_actions(action_rows(alert_id, plan["actions"], decision_time))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to record alert decision") from error
    if not result:
        raise HTTPException(status_code=409, detail="Alert is no longer pending review")
    return {"alert": result[0], "actions_created": len(created_actions)}


@app.patch("/api/v1/actions/{action_id}")
async def update_action(action_id: int, request: ActionUpdateRequest) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": request.status,
        "assignee_name": request.assignee_name.strip() if request.assignee_name else None,
        "completion_note": request.note.strip() if request.note else None,
        "completed_at": now if request.status == "completed" else None,
        "updated_at": now,
    }
    try:
        result = await SupabaseRepository().update_action(action_id, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to update incident action") from error
    if not result:
        raise HTTPException(status_code=404, detail="Incident action not found")
    return result[0]
