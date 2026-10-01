from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import Settings


def deterministic_briefing(evidence: dict[str, Any], fallback_reason: str | None = None) -> dict[str, Any]:
    cluster = evidence.get("cluster")
    investigation = evidence["investigation"]
    forecast = evidence["forecast"]
    if cluster:
        headline = f"{cluster['level'].title()} signal for {cluster['condition']} in {cluster['region']}"
        situation = f"{len(cluster['supporting_sources'])} sources crossed review thresholds on {evidence['analysis_date']}."
        evidence_points = [
            f"Supporting sources: {', '.join(cluster['supporting_sources'])}.",
            f"Peak combined activity was {investigation['peak_total']} on {investigation['peak_date']}.",
            f"Recent weekly visit activity changed by {forecast['observed_weekly_change_pct']}%.",
        ]
        recommended_review = "Review the prepared evidence and response playbook before deciding whether to approve an alert."
    else:
        headline = f"No active threshold signal for {evidence['condition_name']} in {evidence['region_name']}"
        situation = f"Available sources remained below configured review thresholds on {evidence['analysis_date']}."
        evidence_points = [
            f"Peak combined activity was {investigation['peak_total']} on {investigation['peak_date']}.",
            f"Recent weekly visit activity changed by {forecast['observed_weekly_change_pct']}%.",
        ]
        recommended_review = "Continue routine surveillance and verify feed completeness."
    result = {
        "provider": "deterministic",
        "model": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "situation": situation,
        "evidence": evidence_points,
        "uncertainties": [
            "The dataset is synthetic and aggregated.",
            "Scenario trajectories are bounded planning estimates, not epidemiological predictions.",
            "Regional indicators provide context and do not establish causation.",
        ],
        "recommended_review": recommended_review,
        "disclaimer": "Decision support only. An Incident Commander retains authority for alert and response actions.",
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result


def _provider_config(settings: Settings) -> tuple[str, str, str]:
    if settings.ai_provider == "groq" and settings.groq_api_key and settings.groq_model:
        return "https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model
    if settings.ai_provider == "huggingface" and settings.huggingface_token and settings.huggingface_model:
        return "https://router.huggingface.co/v1", settings.huggingface_token, settings.huggingface_model
    raise RuntimeError("The selected AI provider is not fully configured")


async def generate_briefing(evidence: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if settings.ai_provider == "deterministic":
        return deterministic_briefing(evidence)
    try:
        base_url, api_key, model = _provider_config(settings)
        system_prompt = (
            "You summarize prepared synthetic public-health surveillance evidence. "
            "Do not diagnose, infer causation, change alert levels, or invent facts. "
            "Return only JSON with keys headline, situation, evidence, uncertainties, recommended_review. "
            "evidence and uncertainties must be arrays of short strings."
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "max_tokens": 650,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(evidence, separators=(",", ":"))},
                    ],
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        summary = json.loads(content)
        required = {"headline", "situation", "evidence", "uncertainties", "recommended_review"}
        if not required.issubset(summary) or not isinstance(summary["evidence"], list) or not isinstance(summary["uncertainties"], list):
            raise ValueError("AI summary did not match the required structure")
        return {
            "provider": settings.ai_provider,
            "model": model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **{key: summary[key] for key in required},
            "disclaimer": "Decision support only. An Incident Commander retains authority for alert and response actions.",
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError):
        return deterministic_briefing(evidence, "Configured AI provider was unavailable or returned an invalid summary")
