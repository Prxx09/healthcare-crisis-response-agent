from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import Settings
from .playbook_engine import load_playbooks

logger = logging.getLogger(__name__)
PINECONE_DIMENSION = 1024


def build_playbook_documents(playbooks: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Turn the approved, versioned playbook into stable retrieval documents."""
    source = playbooks or load_playbooks()
    version = str(source["version"])
    documents: list[dict[str, Any]] = []
    for level, actions in source["levels"].items():
        for index, action in enumerate(actions):
            documents.append({
                "id": f"{version}|{level}|action|{index}",
                "text": (
                    f"Approved response playbook version {version}. Alert level: {level}. "
                    f"Category: {action['category']}. Action: {action['action']}. "
                    f"Owner: {action['owner']}. Timeframe: {action['timeframe']}. "
                    f"Approval required: {'yes' if action['requires_approval'] else 'no'}."
                ),
                "metadata": {
                    "playbook_version": version,
                    "alert_level": level,
                    "content_type": "action",
                    "category": str(action["category"]),
                    "requires_approval": bool(action["requires_approval"]),
                },
            })
    for condition_code, guidance in source["condition_guidance"].items():
        for index, item in enumerate(guidance):
            documents.append({
                "id": f"{version}|{condition_code}|guidance|{index}",
                "text": (
                    f"Approved response playbook version {version}. Condition: {condition_code}. "
                    f"Condition guidance: {item}"
                ),
                "metadata": {
                    "playbook_version": version,
                    "condition_code": condition_code,
                    "content_type": "condition_guidance",
                },
            })
    return documents


def _pinecone_client(settings: Settings):
    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is not configured")
    try:
        from pinecone import Pinecone
    except ImportError as error:
        raise RuntimeError("The Pinecone SDK is not installed; install backend requirements") from error
    return Pinecone(api_key=settings.pinecone_api_key)


def _index(settings: Settings, client: Any):
    if settings.pinecone_index_host:
        return client.Index(host=settings.pinecone_index_host)
    return client.Index(settings.pinecone_index_name)


def _embedding_values(result: Any) -> list[float]:
    data = getattr(result, "data", None)
    if data is None and isinstance(result, dict):
        data = result.get("data")
    if not data:
        raise RuntimeError("Pinecone returned no embedding")
    first = data[0]
    values = first.get("values") if isinstance(first, dict) else getattr(first, "values", None)
    if not values:
        raise RuntimeError("Pinecone returned an empty embedding")
    return list(values)


def _match_value(match: Any, key: str, default: Any = None) -> Any:
    if isinstance(match, dict):
        return match.get(key, default)
    return getattr(match, key, default)


def _retrieve_sync(settings: Settings, condition_code: str, alert_level: str, query_context: str | None) -> list[dict[str, Any]]:
    client = _pinecone_client(settings)
    query = (
        f"Approved response guidance for condition {condition_code} at alert level {alert_level}. "
        f"{query_context or ''}"
    ).strip()
    embeddings = client.inference.embed(
        model=settings.pinecone_embedding_model,
        inputs=[query],
        parameters={"input_type": "query", "truncate": "END"},
    )
    index = _index(settings, client)
    result = index.query(
        vector=_embedding_values(embeddings),
        top_k=max(1, min(settings.pinecone_top_k, 20)),
        include_metadata=True,
        namespace=settings.pinecone_namespace,
        filter={"playbook_version": str(load_playbooks()["version"])},
    )
    matches = getattr(result, "matches", None)
    if matches is None and isinstance(result, dict):
        matches = result.get("matches", [])
    retrieved: list[dict[str, Any]] = []
    for match in matches or []:
        metadata = _match_value(match, "metadata", {}) or {}
        retrieved.append({
            "id": _match_value(match, "id"),
            "score": round(float(_match_value(match, "score", 0.0)), 4),
            "text": str(metadata.get("text", "")),
            "metadata": metadata,
        })
    return retrieved


async def retrieve_playbook_context(
    settings: Settings,
    condition_code: str,
    alert_level: str,
    query_context: str | None = None,
) -> dict[str, Any]:
    if not settings.pinecone_rag_enabled:
        return {"enabled": False, "status": "disabled", "matches": []}
    try:
        matches = await asyncio.to_thread(_retrieve_sync, settings, condition_code, alert_level, query_context)
        return {"enabled": True, "status": "ready", "matches": matches}
    except Exception as error:
        logger.warning("Playbook RAG retrieval unavailable: %s", error)
        return {"enabled": True, "status": "fallback", "matches": [], "error": "Retrieval unavailable"}


async def select_response_plan_with_rag(
    settings: Settings,
    condition_code: str,
    alert_level: str,
    query_context: str | None = None,
) -> dict[str, Any]:
    # The static plan remains authoritative. Retrieval only supplies traceable context.
    from .playbook_engine import select_response_plan

    plan = select_response_plan(condition_code, alert_level)
    retrieval = await retrieve_playbook_context(settings, condition_code, alert_level, query_context)
    plan["retrieval"] = {
        "enabled": retrieval["enabled"],
        "status": retrieval["status"],
        "match_count": len(retrieval["matches"]),
        "matches": retrieval["matches"],
    }
    plan["retrieved_guidance"] = [match["text"] for match in retrieval["matches"] if match.get("text")]
    return plan
