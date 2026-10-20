import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import logging
import json

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
import httpx

from .config import get_settings
from .briefing_engine import generate_briefing, generate_forecast_briefing
from .action_engine import action_rows
from .alert_service import generate_eligible_alerts
from .email_alerts import EmailAlertScheduler, next_scheduled_at, normalize_emails, resolve_timezone, run_email_alert, send_incident_review_notifications, send_task_owner_notifications
from .forecast_engine import build_scenarios
from .investigation_engine import investigate_cluster
from .models import ActionUpdateRequest, AlertDecisionRequest, AlertGenerationRequest, EmailAlertConfigRequest, EmailAlertSendRequest, PredictiveAssessmentRequest, FollowupCompletionRequest
from .predictive_agent import AGENT_REVIEWER_NAME, run_predictive_agent
from .playbook_documents import MAX_FILE_BYTES, SUPPORTED_EXTENSIONS, parse_playbook_document
from .pinecone_rag import select_response_plan_with_rag
from .playbook_uploads import TABLE as PLAYBOOK_TABLE, BUCKET as PLAYBOOK_BUCKET, ingest
from .orchestrator import run_workflow
from .reporting import build_situation_report, build_timeline
from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository

settings = get_settings()
logger = logging.getLogger(__name__)
email_scheduler = EmailAlertScheduler(settings)


def _agent_may_approve(alert_level: str, assessment_result: dict) -> bool:
    """Enforce approval policy from structured server-owned fields only."""
    pre_approval = assessment_result.get("pre_approval") or {}
    eligible_levels = set(pre_approval.get("eligible_alert_levels") or [])
    return bool(
        alert_level in {"investigate", "escalate"}
        and alert_level in eligible_levels
        and pre_approval.get("approved") is True
        and pre_approval.get("reviewer_name") == AGENT_REVIEWER_NAME
    )


async def _approve_alert_from_agent(
    repository: SupabaseRepository,
    alert: dict,
    assessment_result: dict,
) -> dict:
    if not _agent_may_approve(alert["alert_level"], assessment_result):
        return {"approved": False, "actions_created": 0, "owner_notifications": {"sent": 0, "failed": 0, "skipped": 0}}
    decision_time = datetime.now(timezone.utc)
    rationale = str((assessment_result.get("pre_approval") or {}).get("rationale") or "Agent approval policy passed.")
    decided = await repository.decide_alert(alert["id"], {
        "status": "approved",
        "reviewed_by": AGENT_REVIEWER_NAME,
        "review_note": rationale[:1000],
        "approved_at": decision_time.isoformat(),
    })
    if not decided:
        return {"approved": False, "actions_created": 0, "owner_notifications": {"sent": 0, "failed": 0, "skipped": 0}}
    condition_code = alert.get("conditions", {}).get("code") or alert.get("evidence_summary", {}).get("condition_code")
    plan = await select_response_plan_with_rag(
        settings,
        condition_code,
        alert["alert_level"],
        query_context=json.dumps({"evidence": alert.get("evidence_summary"), "pressure": assessment_result.get("pressure")})[:4000],
    )
    created_actions = await repository.create_actions(action_rows(alert["id"], plan["actions"], decision_time))
    notifications = {"sent": 0, "failed": 0, "skipped": 0}
    try:
        notifications = await send_task_owner_notifications(repository, settings, alert, created_actions)
    except Exception:
        logger.exception("Task owner notification workflow failed for agent-approved alert %s", alert["id"])
        notifications["failed"] = len(created_actions)
    return {"approved": True, "actions_created": len(created_actions), "owner_notifications": notifications}


@asynccontextmanager
async def lifespan(_: FastAPI):
    email_scheduler.start()
    reassessment_task = asyncio.create_task(_reassess_when_new_data()) if settings.supabase_secret_key else None
    yield
    if reassessment_task:
        reassessment_task.cancel()
        try:
            await reassessment_task
        except asyncio.CancelledError:
            pass
    await email_scheduler.stop()


async def _reassess_when_new_data() -> None:
    """Recheck watched scopes only when newer surveillance data is available."""
    while True:
        await asyncio.sleep(300)
        try:
            repository = SupabaseRepository()
            due = await repository.get_due_assessments(datetime.now(timezone.utc).isoformat())
            seen: set[tuple[str, str]] = set()
            for item in due:
                scope = (item["hospital_code"], item["condition_code"])
                if scope in seen:
                    continue
                seen.add(scope)
                latest = await repository.get_latest_observation_date(*scope)
                if not latest or latest <= item["analysis_date"]:
                    continue
                if await repository.get_latest_assessment(*scope, latest):
                    continue
                await create_predictive_assessment(PredictiveAssessmentRequest(
                    analysis_date=date.fromisoformat(latest), hospital_code=scope[0], condition_code=scope[1]
                ))
        except Exception:
            logger.exception("Scheduled predictive reassessment failed; next poll will retry")


app = FastAPI(title="Healthcare Crisis Prediction and Response Agent API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "healthcare-crisis-agent-api"}


@app.get("/api/v1/hospitals")
async def hospitals() -> list[dict]:
    return await SupabaseRepository().get_hospitals()


@app.get("/api/v1/predictive-assessments/latest")
async def latest_predictive_assessment(analysis_date: date, hospital_code: str, condition_code: str) -> dict:
    repository = SupabaseRepository()
    try:
        assessment = await repository.get_latest_assessment(hospital_code, condition_code, analysis_date.isoformat())
        requests = await repository.get_followup_requests(hospital_code, condition_code, analysis_date.isoformat())
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail="Unable to read predictive assessment") from error
    return {"assessment": assessment, "requests": requests}


@app.post("/api/v1/predictive-assessments")
async def create_predictive_assessment(request: PredictiveAssessmentRequest) -> dict:
    repository = SupabaseRepository()
    if not repository.secret_key:
        raise HTTPException(status_code=503, detail="SUPABASE_SECRET_KEY is required for agent actions")
    try:
        result = await run_predictive_agent(
            repository, settings, request.analysis_date, request.hospital_code, request.condition_code
        )
        prior = await repository.get_followup_requests(request.hospital_code, request.condition_code, request.analysis_date.isoformat())
        result["prior_requests"] = [{"request_key": item["request_key"], "status": item["status"], "completion_note": item["completion_note"]} for item in prior]
        already_requested = {item["request_key"] for item in prior}
        result["followups"] = [item for item in result["followups"] if item["request_key"] not in already_requested]
        assessment = await repository.create_assessment(result)
        now = datetime.now(timezone.utc)
        for followup in result["followups"]:
            await repository.create_followup_request({
                "assessment_id": assessment["id"], "analysis_date": request.analysis_date.isoformat(),
                "hospital_code": request.hospital_code, "condition_code": request.condition_code,
                "request_key": followup["request_key"], "owner_role": followup["owner_role"],
                "request_text": followup["request_text"],
                "due_at": (now + timedelta(hours=followup["due_hours"])).isoformat(),
            })
        requests = await repository.get_followup_requests(request.hospital_code, request.condition_code, request.analysis_date.isoformat())
        agent_approval = {"approved": False, "actions_created": 0, "owner_notifications": {"sent": 0, "failed": 0, "skipped": 0}}
        pending_alert = await repository.get_pending_alert_for_scope(
            request.analysis_date.isoformat(), request.hospital_code, request.condition_code
        )
        if pending_alert:
            agent_approval = await _approve_alert_from_agent(repository, pending_alert, result)
        return {"assessment": assessment, "requests": requests, "agent_approval": agent_approval}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (httpx.HTTPError, RuntimeError) as error:
        logger.exception("Predictive assessment failed")
        raise HTTPException(status_code=502, detail="Unable to complete predictive assessment") from error


@app.patch("/api/v1/agent-followups/{request_id}")
async def complete_agent_followup(request_id: int, request: FollowupCompletionRequest) -> dict:
    repository = SupabaseRepository()
    try:
        existing = await repository.get_followup_request(request_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Request not found")
        updated = await repository.complete_followup_request(request_id, request.note)
        if not updated:
            raise HTTPException(status_code=409, detail="Request was already completed")
        return updated
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail="Unable to update evidence request") from error


@app.get("/api/v1/conditions")
async def conditions() -> list[dict]:
    return await SupabaseRepository().get_conditions()


@app.get("/api/v1/data-availability")
async def data_availability() -> dict[str, str]:
    try:
        latest_date = await SupabaseRepository().get_latest_observation_date()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read surveillance data availability") from error
    if not latest_date:
        raise HTTPException(status_code=404, detail="No surveillance observations are available")
    return {"latest_date": latest_date}


@app.get("/api/v1/observations")
async def observations(
    start_date: date = Query(...),
    end_date: date = Query(...),
    hospital_code: str | None = None,
    condition_code: str | None = None,
) -> list[dict]:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    try:
        return await SupabaseRepository().get_observations(start_date.isoformat(), end_date.isoformat(), hospital_code, condition_code)
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
    hospital_code: str = Query(...),
    condition_code: str = Query(...),
    horizon_days: int = Query(default=7, ge=3, le=14),
) -> dict:
    start_date = analysis_date - timedelta(days=15)
    try:
        rows = await SupabaseRepository().get_observations(
            start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code
        )
        return build_scenarios(rows, analysis_date, horizon_days)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to build forecast scenarios") from error


@app.get("/api/v1/forecast/briefing")
async def forecast_briefing(
    analysis_date: date = Query(...),
    hospital_code: str = Query(...),
    condition_code: str = Query(...),
    horizon_days: int = Query(default=7, ge=3, le=14),
) -> dict:
    start_date = analysis_date - timedelta(days=15)
    repository = SupabaseRepository()
    try:
        rows = await repository.get_observations(
            start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code
        )
        forecast_result = build_scenarios(rows, analysis_date, horizon_days)
        hospital_name = rows[0]["hospitals"]["name"] if rows else hospital_code
        condition_name = rows[0]["conditions"]["name"] if rows else condition_code
        return await generate_forecast_briefing(
            {
                "analysis_date": analysis_date.isoformat(),
                "hospital_name": hospital_name,
                "condition_name": condition_name,
                "forecast": forecast_result,
            },
            settings,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare forecast briefing") from error


@app.get("/api/v1/investigation")
async def investigation(
    analysis_date: date = Query(...),
    hospital_code: str = Query(...),
    condition_code: str = Query(...),
    window_days: int = Query(default=14, ge=7, le=30),
) -> dict:
    start_date = analysis_date - timedelta(days=window_days - 1)
    repository = SupabaseRepository()
    try:
        rows, context = await asyncio.gather(
            repository.get_observations(start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code),
            repository.get_hospital_context(start_date.isoformat(), analysis_date.isoformat(), hospital_code),
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
    query_context: str | None = Query(default=None, max_length=4000),
) -> dict:
    try:
        return await select_response_plan_with_rag(settings, condition_code, alert_level, query_context)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/v1/briefing")
async def briefing(
    analysis_date: date = Query(...),
    hospital_code: str = Query(...),
    condition_code: str = Query(...),
) -> dict:
    start_date = analysis_date - timedelta(days=28)
    repository = SupabaseRepository()
    try:
        rows, context = await asyncio.gather(
            repository.get_observations(start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code),
            repository.get_hospital_context((analysis_date - timedelta(days=13)).isoformat(), analysis_date.isoformat(), hospital_code),
        )
        clusters = summarise_clusters(detect_source_signals(rows, analysis_date, 28))
        cluster = next((item for item in clusters if item["hospital_code"] == hospital_code and item["condition_code"] == condition_code), None)
        investigation_rows = [row for row in rows if row["observation_date"] >= (analysis_date - timedelta(days=13)).isoformat()]
        investigation_result = investigate_cluster(investigation_rows, context, analysis_date)
        forecast_result = build_scenarios(rows, analysis_date, 7)
        hospital_name = rows[0]["hospitals"]["name"] if rows else hospital_code
        condition_name = rows[0]["conditions"]["name"] if rows else condition_code
        response_plan_result = await select_response_plan_with_rag(
            settings,
            condition_code,
            cluster["level"],
            query_context=json.dumps({"cluster": cluster, "readiness": investigation_result.get("hospital_context")})[:4000],
        ) if cluster else None
        evidence = {
            "analysis_date": analysis_date.isoformat(),
            "hospital_name": hospital_name,
            "condition_name": condition_name,
            "cluster": cluster,
            "investigation": investigation_result,
            "forecast": forecast_result,
            "response_plan": response_plan_result,
        }
        return await generate_briefing(evidence, settings)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare briefing evidence") from error


@app.get("/api/v1/briefing/aggregate")
async def aggregate_briefing(
    analysis_date: date = Query(...),
    hospital_code: str | None = None,
    condition_code: str | None = None,
) -> dict:
    start_date = analysis_date - timedelta(days=28)
    repository = SupabaseRepository()
    try:
        rows = await repository.get_observations(
            start_date.isoformat(), analysis_date.isoformat(), hospital_code, condition_code
        )
        clusters = summarise_clusters(detect_source_signals(rows, analysis_date, 28))
        hospital_name = rows[0]["hospitals"]["name"] if hospital_code and rows else "All hospitals"
        condition_name = rows[0]["conditions"]["name"] if condition_code and rows else "All diseases"
        return await generate_briefing({
            "aggregate": True,
            "analysis_date": analysis_date.isoformat(),
            "scope": f"{condition_name} · {hospital_name}",
            "hospital_name": hospital_name,
            "condition_name": condition_name,
            "clusters": clusters,
        }, settings)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare aggregate briefing evidence") from error


@app.get("/api/v1/workflow")
async def workflow(
    analysis_date: date = Query(...),
    hospital_code: str = Query(...),
    condition_code: str = Query(...),
) -> dict:
    return await run_workflow(SupabaseRepository(), settings, analysis_date, hospital_code, condition_code)


class PlaybookActivation(BaseModel):
    active: bool
    reviewer_name: str = Field(min_length=2, max_length=100)


@app.get("/api/v1/playbooks")
async def playbooks() -> dict:
    from .playbook_engine import load_playbooks
    documents, error = [], None
    try:
        documents = await SupabaseRepository().privileged_get(PLAYBOOK_TABLE, {
            "select": "id,filename,format,size_bytes,status,active,vector_count,extraction_method,error_message,created_at,reviewed_by,actions",
            "order": "created_at.desc", "limit": "100",
        })
    except (RuntimeError, httpx.HTTPError):
        error = "Upload library unavailable. Configure SUPABASE_SECRET_KEY and apply the playbook schema."
    return {"active_version": str(load_playbooks()["version"]),
        "supported_formats": sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS),
        "max_file_bytes": MAX_FILE_BYTES, "validation_only": False, "documents": documents,
        "uploads_error": error, "indexing_configured": bool(settings.pinecone_api_key),
        "ai_configured": settings.ai_provider != "deterministic", "retrieval_enabled": settings.pinecone_rag_enabled}


async def read_playbook_body(request: Request) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="Playbook files must be 5 MB or smaller")
    return bytes(data)


@app.post("/api/v1/playbooks/validate")
async def validate_playbook(request: Request, filename: str = Query(..., min_length=1, max_length=180)) -> dict:
    data = await read_playbook_body(request)
    try:
        return parse_playbook_document(filename, data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/v1/playbooks/upload")
async def upload_playbook(request: Request, filename: str = Query(..., min_length=1, max_length=180)) -> dict:
    data = await read_playbook_body(request)
    try:
        document = await ingest(SupabaseRepository(), settings, filename, data)
        # The source text is retained server-side; the UI reviews action quotations.
        return {key: value for key, value in document.items() if key != "extracted_text"}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to save the playbook. Check Supabase configuration.") from error


@app.patch("/api/v1/playbooks/{document_id}/activation")
async def activate_playbook(document_id: str, request: PlaybookActivation) -> dict:
    reviewer = request.reviewer_name.strip()
    if len(reviewer) < 2:
        raise HTTPException(status_code=400, detail="Enter the reviewer's name")
    repository = SupabaseRepository()
    try:
        rows = await repository.privileged_get(PLAYBOOK_TABLE, {"select": "id,status", "id": f"eq.{document_id}"})
        if not rows:
            raise HTTPException(status_code=404, detail="Playbook not found")
        if request.active and rows[0]["status"] != "indexed":
            raise HTTPException(status_code=409, detail="Only successfully indexed playbooks can be activated")
        if request.active:
            active = await repository.privileged_get(PLAYBOOK_TABLE, {"select": "id", "active": "eq.true"})
            if len(active) >= 20 and document_id not in {item["id"] for item in active}:
                raise HTTPException(status_code=409, detail="Deactivate a playbook first; at most 20 can be active")
        result = await repository.patch(PLAYBOOK_TABLE, {"id": f"eq.{document_id}"}, {
            "active": request.active, "reviewed_by": reviewer,
            "reviewed_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return {key: value for key, value in result[0].items() if key != "extracted_text"}
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to update the playbook") from error


@app.get("/api/v1/playbooks/{document_id}/source")
async def download_playbook_source(document_id: str) -> Response:
    repository = SupabaseRepository()
    try:
        rows = await repository.privileged_get(PLAYBOOK_TABLE, {"select": "storage_path,format", "id": f"eq.{document_id}"})
        if not rows:
            raise HTTPException(status_code=404, detail="Playbook not found")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{PLAYBOOK_BUCKET}/{rows[0]['storage_path']}", headers=repository._write_headers())
        response.raise_for_status()
        return Response(content=response.content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="playbook-{document_id[:12]}.{rows[0]["format"]}"'})
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to download the source document") from error


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
    try:
        generation = await generate_eligible_alerts(
            repository, request.analysis_date, request.baseline_days, request.hospital_code, request.condition_code
        )
        created_alerts = generation.pop("created_alerts", [])
        notification_result = {"sent": 0, "failed": 0, "skipped": 0}
        owner_notification_result = {"sent": 0, "failed": 0, "skipped": 0}
        pending_alerts = []
        auto_approved = 0
        actions_created = 0
        for created in created_alerts:
            alert = await repository.get_alert(created["id"])
            if not alert:
                continue
            assessment = await repository.get_latest_assessment(
                alert["hospitals"]["code"], alert["conditions"]["code"], request.analysis_date.isoformat()
            )
            if assessment:
                approval = await _approve_alert_from_agent(repository, alert, assessment["result"])
            elif alert["alert_level"] in {"investigate", "escalate"}:
                # Assess newly generated eligible alerts immediately so dynamic
                # approval does not depend on a separate dashboard action.
                agent_state = await create_predictive_assessment(PredictiveAssessmentRequest(
                    analysis_date=request.analysis_date,
                    hospital_code=alert["hospitals"]["code"],
                    condition_code=alert["conditions"]["code"],
                ))
                approval = agent_state["agent_approval"]
            else:
                # Monitor alerts always remain in the human review queue.
                approval = {"approved": False, "actions_created": 0, "owner_notifications": {"sent": 0, "failed": 0, "skipped": 0}}
            if approval["approved"]:
                auto_approved += 1
                actions_created += approval["actions_created"]
                for key in owner_notification_result:
                    owner_notification_result[key] += approval["owner_notifications"][key]
            else:
                pending_alerts.append(alert)
        if pending_alerts:
            try:
                notification_result = await send_incident_review_notifications(
                    repository, settings, pending_alerts
                )
            except Exception:
                logger.exception("Incident review notification workflow failed")
                notification_result["failed"] = len(pending_alerts)
        return {
            **generation,
            "pending_human_review": len(pending_alerts),
            "auto_approved": auto_approved,
            "actions_created": actions_created,
            "incident_master_notifications": notification_result,
            "owner_notifications": owner_notification_result,
        }
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to generate alerts") from error


@app.patch("/api/v1/alerts/{alert_id}/decision")
async def decide_alert(alert_id: int, request: AlertDecisionRequest) -> dict:
    repository = SupabaseRepository()
    notification_result = {"sent": 0, "failed": 0, "skipped": 0}
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
            plan = await select_response_plan_with_rag(
                settings,
                alert["conditions"]["code"],
                alert["alert_level"],
                query_context=json.dumps(alert.get("evidence_summary", {}))[:4000],
            )
            created_actions = await repository.create_actions(action_rows(alert_id, plan["actions"], decision_time))
            try:
                notification_result = await send_task_owner_notifications(repository, settings, alert, created_actions)
            except Exception:
                logger.exception("Task owner notification workflow failed for alert %s", alert_id)
                notification_result["failed"] = len(created_actions)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to record alert decision") from error
    if not result:
        raise HTTPException(status_code=409, detail="Alert is no longer pending review")
    return {"alert": result[0], "actions_created": len(created_actions), "owner_notifications": notification_result}


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


@app.get("/api/v1/email-alerts/dashboard")
async def email_alert_dashboard() -> dict:
    repository = SupabaseRepository()
    try:
        config, history = await asyncio.gather(
            repository.get_email_alert_config(), repository.get_email_alert_deliveries(50)
        )
        next_run = next_scheduled_at(config)
        return {
            "config": config,
            "scheduler_status": "running" if config["enabled"] else "paused",
            "smtp_configured": settings.smtp_configured,
            "next_scheduled_at": next_run.isoformat() if next_run else None,
            "total_sends": len([item for item in history if item["status"] == "success"]),
            "history": history,
        }
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to load email alert settings") from error


@app.put("/api/v1/email-alerts/config")
async def update_email_alert_config(request: EmailAlertConfigRequest) -> dict:
    try:
        resolve_timezone(request.timezone)
        recipients = normalize_emails(request.recipients)
        cc = normalize_emails(request.cc)
        allowed_owner_roles = {"Epidemiology lead", "Operations lead", "Incident communications", "Incident Commander"}
        if set(request.owner_emails) != allowed_owner_roles:
            raise ValueError("Configure email addresses for Epidemiology lead, Operations lead, and Incident communications")
        owner_emails = {role: normalize_emails([email])[0] for role, email in request.owner_emails.items()}
        incident_master_email = normalize_emails([request.incident_master_email])[0]
        if request.enabled and not recipients:
            raise ValueError("At least one recipient is required when the scheduler is enabled")
        if request.enabled and not settings.smtp_configured:
            raise ValueError("Configure SMTP environment variables before enabling the scheduler")
        config = await SupabaseRepository().update_email_alert_config({
            "enabled": request.enabled,
            "schedule_time": request.schedule_time.isoformat(timespec="minutes"),
            "timezone": request.timezone,
            "recipients": recipients,
            "cc": cc,
            "minimum_level": request.minimum_level,
            "incident_master_email": incident_master_email,
            "owner_emails": owner_emails,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return config
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to save email alert settings") from error


@app.post("/api/v1/email-alerts/send")
async def send_email_alert(request: EmailAlertSendRequest) -> dict:
    try:
        return await run_email_alert(SupabaseRepository(), settings, "manual", request.analysis_date)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to prepare email alerts") from error
