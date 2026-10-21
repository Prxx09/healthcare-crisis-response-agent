from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import yaml
from docx import Document
from pypdf import PdfReader

from .disease_codes import normalize_disease_code


SUPPORTED_EXTENSIONS = {".json", ".yaml", ".yml", ".docx", ".pdf"}
MAX_FILE_BYTES = 5 * 1024 * 1024
START_MARKER = "PLAYBOOK_DATA_START"
END_MARKER = "PLAYBOOK_DATA_END"


def _document_text(data: bytes, extension: str) -> str:
    if extension == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if extension == ".docx":
        document = Document(io.BytesIO(data))
        lines = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            lines.extend("\t".join(cell.text for cell in row.cells) for row in table.rows)
        return "\n".join(lines)
    return data.decode("utf-8")


def _structured_section(text: str) -> str:
    if START_MARKER in text and END_MARKER in text:
        return text.split(START_MARKER, 1)[1].split(END_MARKER, 1)[0].strip()
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    raise ValueError(f"PDF and DOCX playbooks must contain a structured section between {START_MARKER} and {END_MARKER}")


def _section_playbook(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize explicit section-based instructions without requiring an LLM."""
    version = payload.get("document_version")
    if isinstance(version, bool) or not isinstance(version, (str, int, float)) or not str(version).strip():
        raise ValueError("Section-based playbooks require document_version")
    condition = normalize_disease_code(payload.get("condition_code") or payload.get("disease"))
    condition_name = payload.get("disease") or condition.replace("_", " ").title()
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Playbook sections must be a non-empty list")
    levels: dict[str, list[dict[str, Any]]] = {"monitor": [], "investigate": [], "escalate": []}
    for number, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            raise ValueError(f"Section {number} must be an object")
        heading = section.get("heading", "")
        match = re.match(r"^(monitor|investigate|escalate)(?=\s|[—–:|-]|$)", heading.strip(), re.I) if isinstance(heading, str) else None
        level = section.get("alert_level") or (match.group(1).lower() if match else None)
        if not isinstance(level, str) or level not in levels:
            raise ValueError(f"Section {number} must declare monitor, investigate or escalate in its heading or alert_level")
        instructions = section.get("instructions")
        if not isinstance(instructions, list) or not instructions:
            raise ValueError(f"Section {number} instructions must be a non-empty list")
        for instruction in instructions:
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError(f"Section {number} instructions must be non-empty strings")
            # Preserve complete instructions verbatim. Only copy roles/timing explicitly present.
            owner_match = re.search(r"\b([A-Z][A-Za-z ]{0,60}?(?:lead|Commander))\s+must\b", instruction)
            timeframe_match = re.search(r"\bwithin\s+\d+\s+(?:hours?|days?|minutes?)\b", instruction, re.I)
            owner = owner_match.group(1) if owner_match else None
            timeframe = timeframe_match.group(0) if timeframe_match else None
            levels[level].append({"action": instruction.strip(), "category": "monitoring" if level == "monitor" else "investigation" if level == "investigate" else "coordination",
                "owner": owner or "Incident Commander", "timeframe": timeframe or "After review", "requires_approval": True,
                "source_section": number, "review_notes": [message for value, message in (
                    (owner, "Owner not specified; confirm assignment"), (timeframe, "Timeframe not specified; confirm timing")) if not value]})
    if any(not actions for actions in levels.values()):
        raise ValueError("Section-based playbooks require instructions for monitor, investigate and escalate")
    guidance = payload.get("purpose") or payload.get("title") or "Review the original playbook before activating its actions."
    return {"version": str(version), "condition_names": {condition: condition_name}, "levels": levels, "condition_actions": {condition: levels},
            "condition_guidance": {condition: [guidance] if isinstance(guidance, str) else []}}


def _validate_playbook(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Playbook content must be an object")
    if "sections" in payload:
        payload = _section_playbook(payload)
    if not isinstance(payload.get("version"), (str, int, float)):
        raise ValueError("Playbook version is required")
    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise ValueError("Playbook levels must be an object")
    required_levels = {"monitor", "investigate", "escalate"}
    if set(levels) != required_levels:
        raise ValueError("Playbook levels must contain exactly monitor, investigate and escalate")
    required_action_fields = {"category", "action", "owner", "timeframe", "requires_approval"}
    for level, actions in levels.items():
        if not isinstance(actions, list) or not actions:
            raise ValueError(f"The {level} level must contain at least one action")
        for action in actions:
            if not isinstance(action, dict) or not required_action_fields.issubset(action):
                raise ValueError(f"Each {level} action must contain {', '.join(sorted(required_action_fields))}")
            if not isinstance(action["requires_approval"], bool):
                raise ValueError("requires_approval must be true or false")
    condition_actions = payload.get("condition_actions")
    if condition_actions is not None:
        if not isinstance(condition_actions, dict):
            raise ValueError("condition_actions must map condition codes to alert-level action lists")
        for condition_code, condition_levels in condition_actions.items():
            if not isinstance(condition_levels, dict) or set(condition_levels) != required_levels:
                raise ValueError(f"condition_actions for {condition_code} must contain exactly monitor, investigate and escalate")
            for level, actions in condition_levels.items():
                if not isinstance(actions, list) or not actions:
                    raise ValueError(f"The {condition_code} {level} level must contain at least one action")
                for action in actions:
                    if not isinstance(action, dict) or not required_action_fields.issubset(action):
                        raise ValueError(f"Each {condition_code} {level} action must contain {', '.join(sorted(required_action_fields))}")
                    if not isinstance(action["requires_approval"], bool):
                        raise ValueError("requires_approval must be true or false")
    guidance = payload.get("condition_guidance")
    if not isinstance(guidance, dict) or not all(isinstance(items, list) for items in guidance.values()):
        raise ValueError("condition_guidance must map condition codes to lists")
    if not guidance:
        raise ValueError("The playbook must identify at least one disease")
    normalized = {}
    original_keys = {}
    for original, items in guidance.items():
        code = normalize_disease_code(original)
        if code in normalized:
            raise ValueError(f"Duplicate disease after normalization: {code}")
        normalized[code] = items
        original_keys[original] = code
    names = payload.get("condition_names", {})
    if not isinstance(names, dict):
        raise ValueError("condition_names must map codes to disease names")
    normalized_names = {original_keys[k]: names.get(k, k.replace("_", " ").title()) for k in guidance}
    if any(not isinstance(name, str) or not name.strip() or len(name) > 160 for name in normalized_names.values()):
        raise ValueError("Disease names must be non-empty text of at most 160 characters")
    normalized_actions = {}
    for original, actions in payload.get("condition_actions", {}).items():
        code = normalize_disease_code(original)
        if code not in normalized or code in normalized_actions:
            raise ValueError("condition_actions must match the diseases declared in condition_guidance")
        normalized_actions[code] = actions
    return {**payload, "condition_guidance": normalized, "condition_names": normalized_names,
            **({"condition_actions": normalized_actions} if "condition_actions" in payload else {})}


def parse_playbook_document(filename: str, data: bytes) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Supported playbook formats are PDF, DOCX, YAML and JSON")
    if not data:
        raise ValueError("The uploaded playbook is empty")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Playbook files must be 5 MB or smaller")
    text = _document_text(data, extension)
    structured = text if extension in {".json", ".yaml", ".yml"} else _structured_section(text)
    try:
        payload = json.loads(structured) if structured.lstrip().startswith("{") else yaml.safe_load(structured)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise ValueError("The structured playbook content is not valid JSON or YAML") from error
    playbook = _validate_playbook(payload)
    return {
        "valid": True,
        "source": {
            "filename": Path(filename).name,
            "format": extension.lstrip("."),
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        "summary": {
            "version": str(playbook["version"]),
            "conditions": sorted(playbook["condition_guidance"]),
            "action_counts": {level: len(actions) for level, actions in playbook["levels"].items()},
            "condition_action_counts": {
                condition: {level: len(actions) for level, actions in levels.items()}
                for condition, levels in playbook.get("condition_actions", {}).items()
            },
        },
        "playbook": playbook,
    }
