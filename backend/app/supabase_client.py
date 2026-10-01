from __future__ import annotations

from typing import Any

import httpx

from .config import get_settings


class SupabaseRepository:
    """Small REST client that keeps privileged alert operations server-side."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self.read_headers = {
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {settings.supabase_publishable_key}",
        }
        self.secret_key = settings.supabase_secret_key

    def _write_headers(self) -> dict[str, str]:
        if not self.secret_key:
            raise RuntimeError("SUPABASE_SECRET_KEY is not configured on the API server")
        return {
            "apikey": self.secret_key,
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/{table}", headers=self.read_headers, params=params)
        response.raise_for_status()
        return response.json()

    async def privileged_get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/{table}", headers=self._write_headers(), params=params)
        response.raise_for_status()
        return response.json()

    async def post(self, table: str, payload: Any) -> list[dict[str, Any]]:
        headers = {**self._write_headers(), "Prefer": "return=representation,resolution=ignore-duplicates"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{self.base_url}/{table}", headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def patch(self, table: str, filters: dict[str, str], payload: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {**self._write_headers(), "Prefer": "return=representation"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.patch(f"{self.base_url}/{table}", headers=headers, params=filters, json=payload)
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

    async def get_regional_context(self, start_date: str, end_date: str, region_code: str) -> list[dict[str, Any]]:
        return await self.get("regional_context", {
            "select": "observation_date,rainfall_index,mobility_index,temperature_c,context_note,regions!inner(code,name)",
            "observation_date": f"gte.{start_date}",
            "and": f"(observation_date.lte.{end_date})",
            "regions.code": f"eq.{region_code}",
            "order": "observation_date.asc",
        })

    async def get_alerts(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "id,analysis_date,alert_level,evidence_summary,rule_version,status,reviewed_by,review_note,approved_at,created_at,regions!inner(code,name),conditions!inner(code,name)",
            "order": "created_at.desc",
        }
        if status:
            params["status"] = f"eq.{status}"
        return await self.privileged_get("alerts", params)

    async def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        rows = await self.privileged_get("alerts", {
            "select": "id,analysis_date,alert_level,evidence_summary,rule_version,status,regions!inner(code,name),conditions!inner(code,name)",
            "id": f"eq.{alert_id}",
            "limit": "1",
        })
        return rows[0] if rows else None

    async def create_alert(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.post("alerts", payload)

    async def decide_alert(self, alert_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.patch("alerts", {"id": f"eq.{alert_id}", "status": "eq.pending_approval"}, payload)

    async def get_actions(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "id,alert_id,action_key,category,action_text,owner_role,assignee_name,timeframe,due_at,status,completion_note,completed_at,created_at,updated_at,alerts!inner(alert_level,analysis_date,regions!inner(code,name),conditions!inner(code,name))",
            "order": "created_at.desc",
        }
        if status:
            params["status"] = f"eq.{status}"
        return await self.privileged_get("incident_actions", params)

    async def create_actions(self, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self.post("incident_actions", payload)

    async def update_action(self, action_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.patch("incident_actions", {"id": f"eq.{action_id}"}, payload)
