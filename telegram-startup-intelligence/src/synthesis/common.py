"""Shared helpers for the synthesis passes."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils import token_count_estimate  # noqa: E402

MAX_CLUSTER_TOKENS = 6000


def insight_brief(row: dict[str, Any], *, full: bool = False) -> str:
    """Compact, citable rendering of one insight for a synthesis prompt."""
    lines = [
        f"[{row['insight_id']}] {row.get('date') or '?'} {row.get('source_url')}",
        f"THESIS: {row.get('thesis')}",
    ]
    if row.get("mechanism"):
        lines.append(f"MECHANISM: {row['mechanism']}")
    if full:
        for field in ("why_it_matters", "problem_pattern", "solution_pattern",
                      "startup_application", "hackathon_application", "example", "anti_pattern"):
            if row.get(field):
                lines.append(f"{field.upper()}: {row[field]}")
    lines.append(f"EVIDENCE: {row.get('evidence_type')} (strength {row.get('evidence_strength')})")
    if row.get("quote"):
        lines.append(f'QUOTE: "{row["quote"]}"')
    return "\n".join(lines)


def pack(rows: Iterable[dict[str, Any]], max_tokens: int = MAX_CLUSTER_TOKENS, full: bool = False) -> str:
    """Fit as many insights as the budget allows, oldest first so the model can
    see how the idea developed."""
    rows = sorted(rows, key=lambda r: (r.get("date") or "", r["insight_id"]))
    out: list[str] = []
    used = 0
    for r in rows:
        block = insight_brief(r, full=full)
        t = token_count_estimate(block)
        if used + t > max_tokens and out:
            out.append(f"\n[... {len(rows)-len(out)} further supporting insights omitted for length ...]")
            break
        out.append(block)
        used += t
    return "\n\n".join(out)


def provenance(rows: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Returns (source_post_uids, source_insight_ids) - never lost, ever."""
    rows = list(rows)
    posts: list[str] = []
    for r in rows:
        for p in r.get("source_posts") or [r.get("source_post_id")]:
            if p and p not in posts:
                posts.append(p)
    return sorted(posts), sorted(r["insight_id"] for r in rows)


def date_range(rows: Iterable[dict[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted(r["date"] for r in rows if r.get("date"))
    return (dates[0], dates[-1]) if dates else (None, None)
