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

    async def get_hospitals(self) -> list[dict[str, Any]]:
        return await self.get("hospitals", {"select": "id,code,name,bed_capacity", "active": "eq.true", "order": "name"})

    async def get_conditions(self) -> list[dict[str, Any]]:
        return await self.get("conditions", {"select": "id,code,name,syndrome_group", "active": "eq.true", "order": "name"})

    async def get_observations(self, start_date: str, end_date: str, hospital_code: str | None = None, condition_code: str | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "observation_date,signal_source,observation_count,coverage_pct,data_quality,hospitals!inner(code,name),conditions!inner(code,name)",
            "observation_date": f"gte.{start_date}",
            "order": "observation_date.asc",
        }
        if end_date:
            params["and"] = f"(observation_date.lte.{end_date})"
        if hospital_code:
            params["hospitals.code"] = f"eq.{hospital_code}"
        if condition_code:
            params["conditions.code"] = f"eq.{condition_code}"
        return await self.get("surveillance_observations", params)

    async def get_hospital_context(self, start_date: str, end_date: str, hospital_code: str) -> list[dict[str, Any]]:
        return await self.get("hospital_context", {
            "select": "observation_date,staffed_beds,occupied_beds,staffing_coverage_pct,supply_readiness_pct,context_note,hospitals!inner(code,name)",
            "observation_date": f"gte.{start_date}",
            "and": f"(observation_date.lte.{end_date})",
            "hospitals.code": f"eq.{hospital_code}",
            "order": "observation_date.asc",
        })

    async def get_alerts(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "id,analysis_date,alert_level,evidence_summary,rule_version,status,reviewed_by,review_note,approved_at,created_at,hospitals!inner(code,name),conditions!inner(code,name)",
            "order": "created_at.desc",
        }
        if status:
            params["status"] = f"eq.{status}"
        return await self.privileged_get("alerts", params)

    async def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        rows = await self.privileged_get("alerts", {
            "select": "id,analysis_date,alert_level,evidence_summary,rule_version,status,reviewed_by,review_note,approved_at,created_at,hospitals!inner(code,name),conditions!inner(code,name)",
            "id": f"eq.{alert_id}",
            "limit": "1",
        })
        return rows[0] if rows else None

    async def get_alerts_for_date(self, analysis_date: str) -> list[dict[str, Any]]:
        return await self.privileged_get("alerts", {
            "select": "id,analysis_date,alert_level,evidence_summary,rule_version,status,reviewed_by,review_note,approved_at,created_at,hospitals!inner(code,name),conditions!inner(code,name)",
            "analysis_date": f"eq.{analysis_date}",
            "alert_level": "in.(investigate,escalate)",
            "order": "alert_level.desc,created_at.desc",
        })

    async def create_alert(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return await self.post("alerts", payload)
        except httpx.HTTPStatusError as error:
            # Alert generation is intentionally idempotent. PostgREST does not
            # apply resolution=ignore-duplicates reliably to the partial unique
            # index used for analysis scope, so treat that conflict as existing.
            if error.response.status_code == 409:
                return []
            raise

    async def decide_alert(self, alert_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.patch("alerts", {"id": f"eq.{alert_id}", "status": "eq.pending_approval"}, payload)

    async def get_actions(self, status: str | None = None, alert_id: int | None = None) -> list[dict[str, Any]]:
        params = {
            "select": "id,alert_id,action_key,category,action_text,owner_role,assignee_name,timeframe,due_at,status,completion_note,completed_at,created_at,updated_at,alerts!inner(alert_level,analysis_date,hospitals!inner(code,name),conditions!inner(code,name))",
            "order": "created_at.desc",
        }
        if status:
            params["status"] = f"eq.{status}"
        if alert_id is not None:
            params["alert_id"] = f"eq.{alert_id}"
        return await self.privileged_get("incident_actions", params)

    async def create_actions(self, payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return await self.post("incident_actions", payload)

    async def update_action(self, action_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.patch("incident_actions", {"id": f"eq.{action_id}"}, payload)

    async def get_latest_observation_date(self) -> str | None:
        rows = await self.get("surveillance_observations", {
            "select": "observation_date",
            "order": "observation_date.desc",
            "limit": "1",
        })
        return rows[0]["observation_date"] if rows else None

    async def get_email_alert_config(self) -> dict[str, Any]:
        rows = await self.privileged_get("email_alert_config", {"select": "*", "id": "eq.1", "limit": "1"})
        if not rows:
            raise RuntimeError("Email alert configuration is missing. Apply the email scheduler migration.")
        return rows[0]

    async def update_email_alert_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        rows = await self.patch("email_alert_config", {"id": "eq.1"}, payload)
        if not rows:
            raise RuntimeError("Email alert configuration could not be updated")
        return rows[0]

    async def get_email_alert_deliveries(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.privileged_get("email_alert_deliveries", {
            "select": "*", "order": "sent_at.desc", "limit": str(limit),
        })

    async def get_scheduled_email_delivery(self, schedule_date: str) -> dict[str, Any] | None:
        rows = await self.privileged_get("email_alert_deliveries", {
            "select": "*", "trigger_mode": "eq.scheduled", "schedule_date": f"eq.{schedule_date}", "limit": "1",
        })
        return rows[0] if rows else None

    async def create_email_alert_delivery(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.post("email_alert_deliveries", payload)
        return rows[0] if rows else None

    async def create_task_owner_notification(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.post("task_owner_notifications", payload)
        return rows[0] if rows else None

    async def create_incident_review_notification(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = await self.post("incident_review_notifications", payload)
        return rows[0] if rows else None
