"""LLM verification of candidate duplicate pairs (brief section 21).

Cosine similarity says two insights are close. It cannot say WHY. This pass asks
the model to label each close pair as DUPLICATE / REFINEMENT / CONTRADICTION /
EXAMPLE / EVOLUTION.

Nothing is deleted on a DUPLICATE verdict. The pair is recorded, the cluster
keeps one representative for the reports, and every member stays queryable.
CONTRADICTION pairs are the raw material for EVOLUTION_OF_THOUGHT.md.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, RELATION_TYPES, SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.llm import prompts  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402
from src.utils import clamp  # noqa: E402


def verify_pair(pair: dict[str, Any], insights: dict[str, Any], provider: Any) -> dict[str, Any]:
    a, b = insights[pair["a_id"]], insights[pair["b_id"]]
    try:
        res = provider.complete_json(prompts.RELATION_SYSTEM, prompts.relation_user(a, b))
    except Exception as exc:
        print(f"  ! relation failed {pair['a_id']}/{pair['b_id']}: {exc}", file=sys.stderr)
        res = {}
    rel = (res.get("relation") or "").upper()
    if rel not in RELATION_TYPES:
        rel = "DUPLICATE" if pair["similarity"] >= 0.92 else "REFINEMENT"
    return {
        "a_id": pair["a_id"],
        "b_id": pair["b_id"],
        "relation": rel,
        "confidence": round(clamp(res.get("confidence"), 0.0, 1.0, 0.4), 3),
        "reasoning": (res.get("reasoning") or "")[:400],
        "similarity": pair["similarity"],
        "engine": provider.engine,
    }


def run(channel: str = "", engine: str = "auto", limit: int | None = None, min_similarity: float = 0.78) -> dict[str, int]:
    conn = store.connect()
    pairs = store.query(
        conn,
        "SELECT * FROM relations WHERE relation='UNVERIFIED' AND similarity >= ? ORDER BY similarity DESC",
        (min_similarity,),
    )
    if limit:
        pairs = pairs[:limit]
    if not pairs:
        print("no unverified pairs", file=sys.stderr)
        conn.close()
        return {}

    insights = {r["insight_id"]: r for r in store.query(conn, "SELECT * FROM insights")}
    pairs = [p for p in pairs if p["a_id"] in insights and p["b_id"] in insights]

    provider = get_provider(engine)
    print(f"verifying {len(pairs)} candidate pairs engine={provider.engine}", file=sys.stderr)
    run_id = store.start_run(conn, "relations", provider.engine, {"pairs": len(pairs)})

    workers = LLM.concurrency if provider.engine != "heuristic" else 1
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda p: verify_pair(p, insights, provider), pairs))

    store.upsert(conn, "relations", results, ["a_id", "b_id"])
    counts: dict[str, int] = {}
    for r in store.query(conn, "SELECT relation, COUNT(*) AS n FROM relations GROUP BY relation"):
        counts[r["relation"]] = r["n"]
    store.finish_run(conn, run_id, counts)
    conn.close()
    print("relation counts:", counts, file=sys.stderr)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-similarity", type=float, default=0.78)
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.limit, args.min_similarity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
