from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PLAYBOOK_PATH = Path(__file__).resolve().parents[2] / "playbooks" / "response_playbooks.json"


@lru_cache(maxsize=1)
def load_playbooks() -> dict[str, Any]:
    return json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))


def select_response_plan(condition_code: str, level: str) -> dict[str, Any]:
    playbooks = load_playbooks()
    if level not in playbooks["levels"]:
        raise ValueError("Unsupported alert level")
    if condition_code not in playbooks["condition_guidance"]:
        raise ValueError("Unsupported condition")
    actions = playbooks["levels"][level]
    return {
        "playbook_version": playbooks["version"],
        "condition_code": condition_code,
        "alert_level": level,
        "actions": actions,
        "condition_guidance": playbooks["condition_guidance"][condition_code],
        "approval_required": any(action["requires_approval"] for action in actions),
        "boundary": "This plan prepares response tasks. The Incident Commander must approve controlled actions before they are issued.",
    }
