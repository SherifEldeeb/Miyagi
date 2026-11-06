"""End-of-session coaching report: LLM-written when available, rules otherwise."""

from __future__ import annotations

import json
import logging
from typing import Any

from .conditions import default_conditions
from .llm import LLMError, get_provider

log = logging.getLogger(__name__)

SYSTEM = (
    "You are a warm, direct presentation and video-call coach. You receive aggregate "
    "statistics of non-verbal habits detected by a webcam during one meeting. "
    "Write a short report in Markdown: a one-paragraph overview, then the top 3 habits to "
    "work on (most frequent or longest first) each with one concrete, practical exercise, "
    "then one thing that went well. Be encouraging, specific, and under 300 words. "
    "Detections are heuristic and can be wrong, so do not over-interpret small counts."
)


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def rule_based_report(stats: dict[str, Any]) -> str:
    habits = stats.get("habits", {})
    tips = {c.id: c.tip for c in default_conditions().values()}
    lines = [f"## Session summary ({_fmt_duration(stats.get('duration_seconds', 0))})", ""]
    if not habits:
        lines.append("No habits detected - great composure! 🎉")
        return "\n".join(lines)
    total = sum(h["count"] for h in habits.values())
    lines.append(f"We flagged **{total}** moments across **{len(habits)}** habits.")
    lines += ["", "### Focus on"]
    for cid, h in list(habits.items())[:3]:
        lines.append(
            f"- {h['emoji']} **{h['label']}**: {h['count']}x "
            f"(~{h['per_10_min']} per 10 min, {h['total_seconds']} s total). {tips.get(cid, '')}"
        )
    quiet = [
        c.label for cid, c in default_conditions().items() if cid in stats.get("enabled", []) and cid not in habits
    ]
    if quiet:
        lines += ["", "### Went well", f"No {', '.join(quiet[:4]).lower()} detected."]
    return "\n".join(lines)


async def generate_report(stats: dict[str, Any], provider_name: str | None = None) -> dict[str, Any]:
    fallback = rule_based_report(stats)
    try:
        provider = get_provider(provider_name)
    except LLMError as e:
        return {"source": "rules", "markdown": fallback, "note": str(e)}
    if provider is None:
        return {"source": "rules", "markdown": fallback}
    if not stats.get("habits") and stats.get("duration_seconds", 0) < 30:
        return {"source": "rules", "markdown": fallback, "note": "Session too short for an AI report."}
    prompt = "Session statistics (JSON):\n" + json.dumps(stats, ensure_ascii=False, indent=1)
    try:
        text = await provider.complete(SYSTEM, prompt)
        if not text:
            raise LLMError("empty response")
        return {"source": f"{provider.name}:{provider.model}", "markdown": text}
    except LLMError as e:
        log.warning("LLM report failed: %s", e)
        return {"source": "rules", "markdown": fallback, "note": str(e)}
