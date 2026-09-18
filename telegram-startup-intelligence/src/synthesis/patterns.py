"""CORE_PATTERN synthesis: collapse recurring clusters into one entry (sections 11, 12)."""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, SCRAPE, TAXONOMY  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.synthesis.common import date_range, pack, provenance  # noqa: E402
from src.utils import clamp_int, derived_id, utcnow_iso  # noqa: E402


def _groups(conn: Any, min_support: int) -> list[tuple[str, list[dict[str, Any]]]]:
    """Clusters first (true recurrence). Then, for taxonomy areas that produced no
    multi-member cluster, group the strongest singletons by tag so a well-covered
    topic is not silently dropped."""
    insights = store.query(conn, "SELECT * FROM insights")
    by_id = {r["insight_id"]: r for r in insights}
    clusters = store.query(conn, "SELECT * FROM clusters WHERE size >= ?", (min_support,))

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    used: set[str] = set()
    for c in clusters:
        members = [by_id[m] for m in c["member_ids"] if m in by_id]
        if len(members) >= min_support:
            groups.append((c["cluster_id"], members))
            used.update(m["insight_id"] for m in members)

    covered_tags = {m["category"] for _, ms in groups for m in ms}
    by_tag: dict[str, list[dict[str, Any]]] = {}
    for r in insights:
        if r["insight_id"] in used:
            continue
        by_tag.setdefault(r["category"], []).append(r)
    for tag in TAXONOMY:
        rows = by_tag.get(tag, [])
        if tag in covered_tags or len(rows) < min_support:
            continue
        rows.sort(key=lambda r: -(r["transferability_score"] + r["actionability_score"] + r["novelty_score"]))
        groups.append((derived_id("tagclu", tag), rows[:12]))
    return groups


def synth_one(group: tuple[str, list[dict[str, Any]]], provider: Any) -> dict[str, Any] | None:
    gid, rows = group
    try:
        res = provider.complete_json(
            prompts.PATTERN_SYSTEM,
            f"CLUSTER of {len(rows)} insights from the same channel, oldest first:\n\n{pack(rows, full=True)}",
        )
    except Exception as exc:
        print(f"  ! pattern synthesis failed for {gid}: {exc}", file=sys.stderr)
        return None
    name = (res.get("pattern_name") or "").strip()
    if not name:
        return None
    posts, ins = provenance(rows)
    d0, d1 = date_range(rows)
    return {
        "pattern_id": derived_id("pat", name + gid),
        "kind": "CORE_PATTERN",
        "name": name[:200],
        "payload": res,
        "source_posts": posts,
        "source_insights": ins,
        "date_start": d0,
        "date_end": d1,
        "support": len(rows),
        "confidence": clamp_int(res.get("confidence"), 1, 5, 2),
        "tags": [t for t in (res.get("tags") or []) if t in TAXONOMY][:6] or [rows[0]["category"]],
        "engine": provider.engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "created_at": utcnow_iso(),
    }


def run(channel: str = "", engine: str = "auto", min_support: int = 2, limit: int | None = None) -> int:
    conn = store.connect()
    groups = _groups(conn, min_support)
    groups.sort(key=lambda g: -len(g[1]))
    if limit:
        groups = groups[:limit]
    provider = get_provider(engine)
    print(f"synthesising {len(groups)} core patterns engine={provider.engine}", file=sys.stderr)
    run_id = store.start_run(conn, "patterns", provider.engine, {"groups": len(groups), "min_support": min_support})

    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = [r for r in pool.map(lambda g: synth_one(g, provider), groups) if r]

    conn.execute("DELETE FROM patterns WHERE kind='CORE_PATTERN'")
    store.upsert(conn, "patterns", rows, ["pattern_id"])
    store.finish_run(conn, run_id, {"patterns": len(rows)})
    conn.close()
    print(f"{len(rows)} core patterns stored", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.min_support, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
