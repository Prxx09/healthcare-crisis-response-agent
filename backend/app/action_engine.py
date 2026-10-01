from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _due_at(timeframe: str, approved_at: datetime) -> str | None:
    match = re.search(r"within\s+(\d+)\s+hour", timeframe, re.IGNORECASE)
    if match:
        return (approved_at + timedelta(hours=int(match.group(1)))).isoformat()
    if "business day" in timeframe.lower():
        return (approved_at + timedelta(days=1)).isoformat()
    return None


def action_rows(alert_id: int, actions: list[dict[str, Any]], approved_at: datetime) -> list[dict[str, Any]]:
    return [
        {
            "alert_id": alert_id,
            "action_key": f"{index + 1}-{action['category']}",
            "category": action["category"],
            "action_text": action["action"],
            "owner_role": action["owner"],
            "timeframe": action["timeframe"],
            "due_at": _due_at(action["timeframe"], approved_at),
            "status": "pending",
        }
        for index, action in enumerate(actions)
    ]
