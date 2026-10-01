from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .config import get_settings
from .models import AlertDecisionRequest, AlertGenerationRequest
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


@app.get("/api/v1/alerts")
async def alerts(status: str | None = Query(default="pending_approval")) -> list[dict]:
    try:
        return await SupabaseRepository().get_alerts(status)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to read alerts") from error


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
    try:
        result = await SupabaseRepository().decide_alert(alert_id, {
            "status": request.status,
            "reviewed_by": request.reviewer_name.strip(),
            "review_note": request.note.strip() if request.note else None,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Unable to record alert decision") from error
    if not result:
        raise HTTPException(status_code=409, detail="Alert is no longer pending review")
    return result[0]
