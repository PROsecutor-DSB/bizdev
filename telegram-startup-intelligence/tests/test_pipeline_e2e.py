"""End-to-end pipeline test on the synthetic corpus. No network, no API key.

Asserts the invariants that make the output trustworthy:
  * threads merge a real series and do not merge unrelated posts;
  * nothing is silently deleted - promo posts survive in the database;
  * every insight carries a resolvable Telegram permalink;
  * every derived (inferred) row is labelled DERIVED_HYPOTHESIS;
  * the heuristic engine never fabricates opportunities, ideas or answers;
  * re-running is idempotent, and re-rendering is byte-identical.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import DB_PATH, PROCESSED_DIR  # noqa: E402
from src.db import store  # noqa: E402
from src.utils import load_jsonl  # noqa: E402

CHANNEL = "demo_channel"
STAGES = ("normalize,threads,classify,stats,extract,ajtbd,embed,cluster,relations,"
          "patterns,antipatterns,evolution,opportunities,techjob,ideas,gems,reports")
OUT = ROOT / "output" / "_demo_synthetic"


def run_pipeline() -> None:
    subprocess.run([sys.executable, "tests/make_demo_corpus.py"], cwd=ROOT, check=True, capture_output=True)
    r = subprocess.run(
        [sys.executable, "run_pipeline.py", "--channel", CHANNEL, "--engine", "heuristic",
         "--skip-scrape", "--stage", STAGES, "--out-dir", str(OUT)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, f"pipeline failed:\n{r.stderr[-3000:]}"


def test_e2e() -> None:
    DB_PATH.unlink(missing_ok=True)
    run_pipeline()
    conn = store.connect()

    posts = store.query(conn, "SELECT * FROM posts")
    assert len(posts) == 43, f"expected 43 posts, got {len(posts)}"

    # --- threads: the 4-post series merged, nothing else did
    threads = load_jsonl(PROCESSED_DIR / f"{CHANNEL}.threads.jsonl")
    multi = [t for t in threads if t["size"] > 1]
    assert len(multi) == 1, f"expected exactly one merged thread, got {len(multi)}"
    assert multi[0]["size"] == 4, f"the wedge series should merge all 4 posts, got {multi[0]['size']}"
    assert "part_marker" in multi[0]["merge_reasons"] or "tight_followup" in multi[0]["merge_reasons"]

    # --- nothing is deleted: promo and hiring posts are still in the database
    cats = {r["category"]: r["n"] for r in store.query(
        conn, "SELECT category, COUNT(*) AS n FROM classifications GROUP BY category")}
    assert cats.get("PROMO", 0) >= 4, "promo posts must be kept, not dropped"
    assert cats.get("HIRING", 0) >= 2, "hiring posts must be kept, not dropped"
    assert cats.get("CONTENT_PLUS_PROMO", 0) >= 3, "mixed posts must get their own category"

    # --- the promo shell is stripped but the substance survives
    mixed = store.query(conn, "SELECT * FROM classifications WHERE category='CONTENT_PLUS_PROMO'")
    for m in mixed:
        assert m["clean_text"].strip(), "a CONTENT_PLUS_PROMO post must retain substance"
        low = m["clean_text"].lower()
        assert "скидка" not in low and "записаться" not in low, \
            f"promo shell survived cleaning in {m['thread_id']}: {m['clean_text'][:200]}"

    # --- provenance: every insight resolves to a real collected post
    known = {p["post_uid"] for p in posts}
    insights = store.query(conn, "SELECT * FROM insights")
    assert insights, "no insights extracted"
    for i in insights:
        assert i["source_url"].startswith("https://t.me/"), i["source_url"]
        assert i["source_post_id"] in known, f"insight cites unknown post {i['source_post_id']}"
        for p in i["source_posts"]:
            assert p in known, f"insight cites unknown post {p}"
        assert i["evidence_type"], "evidence_type must always be set"
        assert "\n" not in i["thesis"], "a thesis must be a single line"

    # --- clustering assigned every insight
    assert all(i["cluster_id"] for i in insights), "every insight must land in a cluster"
    reps = [i for i in insights if i["is_cluster_representative"]]
    assert len(reps) == store.count(conn, "clusters")

    # --- inference is always labelled
    for d in store.query(conn, "SELECT * FROM derived WHERE kind IN ('OPPORTUNITY','IDEA','TECH_JOB')"):
        assert d["label"] == "DERIVED_HYPOTHESIS", f"{d['kind']} must be labelled as inference"

    # --- the heuristic engine refuses to invent
    assert store.count(conn, "derived", "kind='OPPORTUNITY'") == 0, \
        "the heuristic engine must not fabricate opportunities"
    assert store.count(conn, "derived", "kind='IDEA'") == 0, \
        "the heuristic engine must not fabricate ideas"

    # --- every report exists and carries the honesty banner
    for name in ("START_HERE.md", "CORE_INSIGHTS.md", "AJTBD_KNOWLEDGE_BASE.md",
                 "STARTUP_PATTERNS.md", "ANTI_PATTERNS.md", "HACKATHON_COMPASS.md",
                 "HIDDEN_GEMS.md", "EVOLUTION_OF_THOUGHT.md", "OPPORTUNITY_MAP.md",
                 "IDEA_GENERATOR.md", "DATASET_STATS.md"):
        f = OUT / name
        assert f.exists(), f"{name} was not rendered"
        assert f.stat().st_size > 400, f"{name} is suspiciously small"
    assert "heuristic engine" in (OUT / "START_HERE.md").read_text(encoding="utf-8")

    n_before = store.count(conn, "insights")
    conn.close()

    def report_hashes() -> dict[str, str]:
        return {
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(OUT.glob("*.md"))
        }

    before = report_hashes()

    # --- idempotency: a second full run changes nothing
    run_pipeline()
    conn = store.connect()
    assert store.count(conn, "insights") == n_before, "re-running must not duplicate insights"
    conn.close()

    # --- reproducibility: identical data must render byte-identical files, so a
    #     re-render never shows up as a diff (no timestamps in the output)
    after = report_hashes()
    changed = [name for name, h in before.items() if after.get(name) != h]
    assert not changed, f"re-rendering unchanged data produced different bytes in: {changed}"
    print(f"e2e: {len(posts)} posts, {len(insights)} insights, "
          f"{store.connect().execute('SELECT COUNT(*) FROM patterns').fetchone()[0]} patterns: OK")


if __name__ == "__main__":
    test_e2e()
