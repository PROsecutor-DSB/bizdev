"""ANTI_PATTERNS synthesis (brief section 13).

Source material: every insight that carries an `anti_pattern` field, plus
insights whose thesis is itself about a mistake. Grouped by taxonomy category so
one entry covers a recurring mistake rather than twenty near-copies.

The seed list in the brief (building before demand, too-wide ICP, feature
factory, vanity metrics, premature scaling, ...) is used only as a *coverage
check* at report time - the entries themselves are extracted from the channel.
"""
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

MISTAKE_WORDS = ("ошибк", "mistake", "не работает", "fails", "trap", "ловушк", "anti", "провал", "wrong")


def _candidates(conn: Any) -> list[dict[str, Any]]:
    rows = store.query(conn, "SELECT * FROM insights")
    out = []
    for r in rows:
        blob = " ".join(
            str(r.get(f) or "") for f in ("anti_pattern", "thesis", "problem_pattern", "why_it_matters")
        ).lower()
        if (r.get("anti_pattern") or "").strip() or any(w in blob for w in MISTAKE_WORDS):
            out.append(r)
    return out


def synth_one(group: tuple[str, list[dict[str, Any]]], provider: Any) -> dict[str, Any] | None:
    key, rows = group
    try:
        res = provider.complete_json(
            prompts.ANTIPATTERN_SYSTEM,
            f"{len(rows)} insights describing mistakes in the area {key}, oldest first:\n\n{pack(rows, full=True)}",
        )
    except Exception as exc:
        print(f"  ! anti-pattern synthesis failed for {key}: {exc}", file=sys.stderr)
        return None
    name = (res.get("anti_pattern_name") or "").strip()
    if not name:
        return None
    posts, ins = provenance(rows)
    d0, d1 = date_range(rows)
    return {
        "pattern_id": derived_id("anti", name + key),
        "kind": "ANTI_PATTERN",
        "name": name[:200],
        "payload": res,
        "source_posts": posts,
        "source_insights": ins,
        "date_start": d0,
        "date_end": d1,
        "support": len(rows),
        "confidence": clamp_int(res.get("confidence"), 1, 5, 2),
        "tags": [t for t in (res.get("tags") or []) if t in TAXONOMY][:6] or [key],
        "engine": provider.engine,
        "prompt_version": prompts.PROMPT_VERSION,
        "created_at": utcnow_iso(),
    }


def run(channel: str = "", engine: str = "auto", min_support: int = 1, limit: int | None = None) -> int:
    conn = store.connect()
    cands = _candidates(conn)
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in cands:
        groups.setdefault(r["category"], []).append(r)
    todo = [(k, v) for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])) if len(v) >= min_support]
    if limit:
        todo = todo[:limit]

    provider = get_provider(engine)
    print(f"synthesising anti-patterns from {len(cands)} candidate insights in {len(todo)} areas", file=sys.stderr)
    run_id = store.start_run(conn, "antipatterns", provider.engine, {"areas": len(todo)})
    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        rows = [r for r in pool.map(lambda g: synth_one(g, provider), todo) if r]

    conn.execute("DELETE FROM patterns WHERE kind='ANTI_PATTERN'")
    store.upsert(conn, "patterns", rows, ["pattern_id"])
    store.finish_run(conn, run_id, {"anti_patterns": len(rows)})
    conn.close()
    print(f"{len(rows)} anti-patterns stored", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--min-support", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.min_support, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
