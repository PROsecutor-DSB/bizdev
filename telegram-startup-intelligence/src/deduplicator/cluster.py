"""Cluster semantically close insights into CORE_PATTERN candidates (section 11).

Pure Python, deterministic: a similarity graph thresholded at --threshold, then
connected components. No sklearn dependency, and identical input always produces
identical clusters, which matters because cluster ids end up in report links.

Nothing is deleted. Every member keeps its own row; the cluster only records
which insight is the representative.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import SCRAPE  # noqa: E402
from src.db import store  # noqa: E402
from src.utils import cluster_id as make_cluster_id  # noqa: E402

DEFAULT_THRESHOLD = 0.78


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def connected_components(ids: list[str], edges: list[tuple[str, str, float]]) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # deterministic merge direction

    groups: dict[str, list[str]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return [sorted(v) for v in sorted(groups.values(), key=lambda g: (-len(g), sorted(g)[0]))]


def run(channel: str = "", threshold: float = DEFAULT_THRESHOLD, max_pairs: int = 400_000) -> dict[str, Any]:
    conn = store.connect()
    embs = store.query(conn, "SELECT item_id, vector FROM embeddings WHERE kind='insight'")
    if not embs:
        raise SystemExit("no embeddings - run src.deduplicator.embed first")
    insights = {r["insight_id"]: r for r in store.query(conn, "SELECT * FROM insights")}

    vectors = {e["item_id"]: json.loads(e["vector"]) for e in embs if e["item_id"] in insights}
    ids = sorted(vectors)
    n = len(ids)
    if n * (n - 1) // 2 > max_pairs:
        print(
            f"! {n} insights -> {n*(n-1)//2} pairs exceeds --max-pairs={max_pairs}. "
            "Raise it, or shard by tag.",
            file=sys.stderr,
        )

    edges: list[tuple[str, str, float]] = []
    for i in range(n):
        vi = vectors[ids[i]]
        for j in range(i + 1, n):
            s = cosine(vi, vectors[ids[j]])
            if s >= threshold:
                edges.append((ids[i], ids[j], s))
    print(f"{n} insights, {len(edges)} similar pairs at threshold {threshold}", file=sys.stderr)

    groups = connected_components(ids, edges)
    clusters: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for g in groups:
        cid = make_cluster_id(g)
        members = [insights[m] for m in g]
        # representative = the member with the most usable mechanism, then the
        # strongest evidence, then the earliest date (origin of the idea).
        rep = sorted(
            members,
            key=lambda m: (
                -len(m.get("mechanism") or ""),
                -(m.get("evidence_strength") or 0),
                m.get("date") or "9999",
            ),
        )[0]
        dates = sorted(m["date"] for m in members if m.get("date"))
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(g),
                "label": (rep.get("thesis") or "")[:200],
                "member_ids": g,
                "date_start": dates[0] if dates else None,
                "date_end": dates[-1] if dates else None,
                "representative_id": rep["insight_id"],
            }
        )
        for m in members:
            updates.append(
                {
                    "insight_id": m["insight_id"],
                    "cluster_id": cid,
                    "is_cluster_representative": int(m["insight_id"] == rep["insight_id"]),
                }
            )

    conn.execute("DELETE FROM clusters")
    store.upsert(conn, "clusters", clusters, ["cluster_id"])
    store.update(conn, "insights", updates, ["insight_id"])

    # store the raw similarity for the pairs we will ask the LLM about
    store.upsert(
        conn,
        "relations",
        [
            {"a_id": a, "b_id": b, "relation": "UNVERIFIED", "similarity": round(s, 4), "engine": "cosine"}
            for a, b, s in edges
            if not store.query(conn, "SELECT 1 FROM relations WHERE a_id=? AND b_id=? AND relation!='UNVERIFIED'", (a, b))
        ],
        ["a_id", "b_id"],
    )
    multi = [c for c in clusters if c["size"] > 1]
    stats = {
        "insights": n,
        "clusters": len(clusters),
        "multi_member_clusters": len(multi),
        "largest_cluster": max((c["size"] for c in clusters), default=0),
        "insights_in_multi_clusters": sum(c["size"] for c in multi),
        "similar_pairs": len(edges),
    }
    conn.close()
    print(json.dumps(stats, indent=2), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--max-pairs", type=int, default=400_000)
    args = ap.parse_args(argv)
    run(args.channel, args.threshold, args.max_pairs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
