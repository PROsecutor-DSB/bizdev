"""Embed insights so near-identical restatements can be found (brief section 21)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.llm.provider import get_provider  # noqa: E402


def embed_input(row: dict[str, Any]) -> str:
    """Embed the claim AND its mechanism: two posts can share a thesis while
    explaining completely different machinery, and those are not duplicates."""
    parts = [row.get("thesis") or "", row.get("mechanism") or "", row.get("problem_pattern") or ""]
    return "\n".join(p for p in parts if p)[:4000]


def run(channel: str = "", engine: str = "auto", force: bool = False) -> int:
    conn = store.connect()
    rows = store.query(conn, "SELECT insight_id, thesis, mechanism, problem_pattern FROM insights")
    if not rows:
        raise SystemExit("no insights to embed")
    have = set()
    if not force:
        have = {r["item_id"] for r in store.query(conn, "SELECT item_id FROM embeddings WHERE kind='insight'")}
    todo = [r for r in rows if r["insight_id"] not in have]

    provider = get_provider(engine)
    print(f"embedding {len(todo)} insights ({len(have)} cached) engine={provider.engine}", file=sys.stderr)
    if todo:
        vectors = provider.embed([embed_input(r) for r in todo])
        store.upsert(
            conn,
            "embeddings",
            [
                {
                    "item_id": r["insight_id"],
                    "kind": "insight",
                    "dim": len(v),
                    "model": provider.engine,
                    "vector": json.dumps([round(x, 6) for x in v]),
                }
                for r, v in zip(todo, vectors)
            ],
            ["item_id", "kind"],
        )
    n = store.count(conn, "embeddings", "kind='insight'")
    conn.close()
    print(f"{n} insight embeddings stored", file=sys.stderr)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "heuristic"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    run(args.channel, args.engine, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
