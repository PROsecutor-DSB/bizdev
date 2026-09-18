"""HIDDEN_GEMS selection (brief section 19).

This one is deliberately deterministic: it is a *selection* problem, not a
generation problem. An insight is a hidden gem when it is rare in the corpus but
high-leverage, and when the audience did NOT reward it.

leverage   = transferability + actionability + novelty + hackathon value
rarity     = small cluster, uncommon taxonomy area, short source post
neglect    = engagement well below the channel median

We store the components, not a single blended number, so you can see why each
entry qualified.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.utils import derived_id, utcnow_iso  # noqa: E402


def run(channel: str = "", limit: int = 40) -> int:
    conn = store.connect()
    insights = store.query(conn, "SELECT * FROM insights")
    if not insights:
        raise SystemExit("no insights")
    clusters = {c["cluster_id"]: c for c in store.query(conn, "SELECT * FROM clusters")}
    cat_freq = Counter(r["category"] for r in insights)
    total = len(insights)

    engagements = [r["views"] for r in insights if r.get("views")]
    median_views = statistics.median(engagements) if engagements else None
    reacts = [r["reactions_total"] for r in insights if r.get("reactions_total")]
    median_reacts = statistics.median(reacts) if reacts else None

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in insights:
        leverage = (
            r["transferability_score"] + r["actionability_score"]
            + r["novelty_score"] + r["hackathon_value_score"]
        )
        cluster_size = clusters.get(r.get("cluster_id") or "", {}).get("size", 1)
        rarity = 0.0
        rarity += 2.0 if cluster_size == 1 else (1.0 if cluster_size == 2 else 0.0)
        rarity += 2.0 * (1.0 - cat_freq[r["category"]] / max(1, total))

        neglect = 0.0
        if median_views and r.get("views"):
            neglect += 1.5 if r["views"] < median_views else 0.0
        if median_reacts and r.get("reactions_total"):
            neglect += 1.5 if r["reactions_total"] < median_reacts else 0.0
        if not r.get("views") and not r.get("reactions_total"):
            neglect += 0.75  # no engagement data at all: mild, not decisive

        if leverage < 12 or not (r.get("mechanism") or "").strip():
            continue  # a gem must still carry a mechanism
        scored.append((leverage + rarity * 1.5 + neglect, r | {
            "_leverage": leverage, "_rarity": round(rarity, 2),
            "_neglect": round(neglect, 2), "_cluster_size": cluster_size,
        }))

    scored.sort(key=lambda x: -x[0])
    rows = []
    for rank, (_, r) in enumerate(scored[:limit], 1):
        rows.append(
            {
                "derived_id": derived_id("gem", r["insight_id"]),
                "kind": "HIDDEN_GEM",
                "title": r["thesis"][:200],
                "payload": {
                    "insight_id": r["insight_id"],
                    "rank": rank,
                    "thesis": r["thesis"],
                    "mechanism": r["mechanism"],
                    "why_it_matters": r["why_it_matters"],
                    "startup_application": r["startup_application"],
                    "hackathon_application": r["hackathon_application"],
                    "evidence_type": r["evidence_type"],
                    "leverage": r["_leverage"],
                    "rarity": r["_rarity"],
                    "neglect": r["_neglect"],
                    "cluster_size": r["_cluster_size"],
                    "views": r.get("views"),
                    "reactions_total": r.get("reactions_total"),
                    "category": r["category"],
                },
                "source_posts": r["source_posts"],
                "source_insights": [r["insight_id"]],
                "label": "OBSERVED",
                "confidence": r["evidence_strength"],
                "tags": r["tags"],
                "engine": "deterministic-selection",
                "prompt_version": "n/a",
                "created_at": utcnow_iso(),
            }
        )

    conn.execute("DELETE FROM derived WHERE kind='HIDDEN_GEM'")
    store.upsert(conn, "derived", rows, ["derived_id"])
    conn.close()
    print(f"{len(rows)} hidden gems selected from {total} insights", file=sys.stderr)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args(argv)
    run(args.channel, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
