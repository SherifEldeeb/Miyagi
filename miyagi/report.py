"""End-of-session coaching report, written on the device from the session's stats."""

from __future__ import annotations

from typing import Any

from .conditions import default_conditions


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def generate_report(stats: dict[str, Any]) -> str:
    """Markdown summary of ``CoachSession.stats()``: the top habits with a tip each, and what went well."""
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
