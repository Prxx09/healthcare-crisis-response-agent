from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


class SupabaseRepository:
    """Small read-only client for the Supabase REST API."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {settings.supabase_publishable_key}",
        }

    async def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/{table}", headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    async def get_regions(self) -> list[dict[str, Any]]:
        return await self.get("regions", {"select": "id,code,name,population", "active": "eq.true", "order": "name"})

    async def get_conditions(self) -> list[dict[str, Any]]:
        return await self.get("conditions", {"select": "id,code,name,syndrome_group", "active": "eq.true", "order": "name"})

    async def get_observations(self, start_date: str, end_date: str, region_code: str | None = None, condition_code: str | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "observation_date,signal_source,observation_count,coverage_pct,data_quality,regions!inner(code,name),conditions!inner(code,name)",
            "observation_date": f"gte.{start_date}",
            "order": "observation_date.asc",
        }
        if end_date:
            params["observation_date"] = f"gte.{start_date}"
            params["and"] = f"(observation_date.lte.{end_date})"
        if region_code:
            params["regions.code"] = f"eq.{region_code}"
        if condition_code:
            params["conditions.code"] = f"eq.{condition_code}"
        return await self.get("surveillance_observations", params)
