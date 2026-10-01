from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .config import get_settings
from .signal_engine import detect_source_signals, summarise_clusters
from .supabase_client import SupabaseRepository

settings = get_settings()
app = FastAPI(title="Healthcare Crisis Prediction and Response Agent API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


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
