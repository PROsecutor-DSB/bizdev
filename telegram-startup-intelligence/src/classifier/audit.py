"""STEP 4: manual audit of the classifier on a random stratified sample.

Workflow:
  1. python -m src.classifier.audit sample --n 50
     -> writes output/CLASSIFIER_AUDIT.md (for reading) and
        data/processed/<channel>.audit.jsonl (for filling in)
  2. Open the .jsonl, set "human_category" and "human_signal_score" on each row.
  3. python -m src.classifier.audit score
     -> prints agreement, a confusion matrix, and score correlation.

The sample is seeded, so the same command always draws the same 50 posts and
your labels stay valid across re-runs.
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import OUTPUT_DIR, PROCESSED_DIR, SCRAPE  # noqa: E402
from src.utils import load_jsonl, write_jsonl  # noqa: E402

SEED = 20260918


def audit_path(channel: str) -> Path:
    return PROCESSED_DIR / f"{channel}.audit.jsonl"


def sample(channel: str, n: int = 50) -> Path:
    threads = {t["thread_id"]: t for t in load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")}
    classified = load_jsonl(PROCESSED_DIR / f"{channel}.classified.jsonl")
    if not classified:
        raise SystemExit("nothing classified yet")

    # Stratify by predicted category so rare labels actually get reviewed.
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in classified:
        by_cat[c["category"]].append(c)

    rng = random.Random(SEED)
    picked: list[dict[str, Any]] = []
    cats = sorted(by_cat)
    per_cat = max(1, n // max(1, len(cats)))
    for cat in cats:
        rows = sorted(by_cat[cat], key=lambda r: r["thread_id"])
        picked.extend(rng.sample(rows, min(per_cat, len(rows))))
    remaining = [c for c in sorted(classified, key=lambda r: r["thread_id"]) if c not in picked]
    rng.shuffle(remaining)
    picked.extend(remaining[: max(0, n - len(picked))])
    picked = picked[:n]

    # keep previously entered human labels
    previous = {r["thread_id"]: r for r in load_jsonl(audit_path(channel))}
    rows: list[dict[str, Any]] = []
    for c in picked:
        t = threads.get(c["thread_id"], {})
        prev = previous.get(c["thread_id"], {})
        rows.append(
            {
                "thread_id": c["thread_id"],
                "url": (t.get("urls") or [""])[0],
                "date": t.get("date_start"),
                "predicted_category": c["category"],
                "predicted_signal_score": c["content_signal_score"],
                "rule_signal_score": c.get("rule_signal_score"),
                "human_category": prev.get("human_category", ""),
                "human_signal_score": prev.get("human_signal_score", ""),
                "note": prev.get("note", ""),
                "text_excerpt": (t.get("text") or "")[:1200],
            }
        )
    out = audit_path(channel)
    write_jsonl(out, rows)

    L = [
        f"# Classifier audit sample - @{channel}\n",
        f"{len(rows)} threads, stratified by predicted category, seed {SEED}.\n",
        "Fill in `human_category` / `human_signal_score` in "
        f"`data/processed/{channel}.audit.jsonl`, then run "
        "`python -m src.classifier.audit score`.\n",
    ]
    for i, r in enumerate(rows, 1):
        L.append(f"## {i}. `{r['thread_id']}` - predicted **{r['predicted_category']}** "
                 f"(signal {r['predicted_signal_score']}, rule {r['rule_signal_score']})\n")
        L.append(f"{r['date']} - {r['url']}\n")
        L.append("```")
        L.append(r["text_excerpt"])
        L.append("```\n")
    (OUTPUT_DIR / "CLASSIFIER_AUDIT.md").write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {len(rows)} audit rows -> {out}", file=sys.stderr)
    print(f"human-readable sample -> {OUTPUT_DIR / 'CLASSIFIER_AUDIT.md'}", file=sys.stderr)
    return out


def score(channel: str) -> dict[str, Any]:
    rows = [r for r in load_jsonl(audit_path(channel)) if (r.get("human_category") or "").strip()]
    if not rows:
        raise SystemExit(
            "no human labels found. Fill in human_category in "
            f"data/processed/{channel}.audit.jsonl first."
        )
    agree = sum(1 for r in rows if r["human_category"] == r["predicted_category"])
    confusion: Counter[tuple[str, str]] = Counter(
        (r["human_category"], r["predicted_category"]) for r in rows
    )
    # "Substance preserved" is the metric that actually matters: did we route a
    # post with real content into a category the extractor will read?
    extractable = {"CONTENT", "CONTENT_PLUS_PROMO", "CASE", "PERSONAL", "NEWS", "REPOST", "OTHER"}
    human_content = [r for r in rows if r["human_category"] in {"CONTENT", "CONTENT_PLUS_PROMO", "CASE"}]
    kept = sum(1 for r in human_content if r["predicted_category"] in extractable)

    scored = [r for r in rows if str(r.get("human_signal_score") or "").strip() != ""]
    mae = (
        round(sum(abs(int(r["human_signal_score"]) - int(r["predicted_signal_score"])) for r in scored) / len(scored), 1)
        if scored
        else None
    )

    result = {
        "reviewed": len(rows),
        "category_accuracy": round(100.0 * agree / len(rows), 1),
        "content_recall": round(100.0 * kept / max(1, len(human_content)), 1),
        "content_reviewed": len(human_content),
        "signal_score_mae": mae,
        "signal_scored": len(scored),
        "confusion": {f"{h} -> {p}": n for (h, p), n in confusion.most_common()},
    }
    print(f"reviewed:            {result['reviewed']}")
    print(f"category accuracy:   {result['category_accuracy']}%")
    print(f"content recall:      {result['content_recall']}%  "
          f"(of {result['content_reviewed']} human-labelled substantive threads, how many stayed extractable)")
    if mae is not None:
        print(f"signal score MAE:    {mae} points over {result['signal_scored']} threads")
    print("\nconfusion (human -> predicted):")
    for k, v in result["confusion"].items():
        mark = "  " if k.split(" -> ")[0] == k.split(" -> ")[1] else "! "
        print(f"{mark}{k:<45} {v}")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["sample", "score"])
    ap.add_argument("--channel", default=SCRAPE.channel)
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args(argv)
    if args.action == "sample":
        sample(args.channel, args.n)
    else:
        score(args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
