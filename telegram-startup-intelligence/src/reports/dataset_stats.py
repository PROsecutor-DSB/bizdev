"""STEP 2: dataset statistics. Run this before trusting anything downstream."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import OUTPUT_DIR, PROCESSED_DIR, SCRAPE  # noqa: E402
from src.utils import allow_broken_pipe, load_jsonl, write_json  # noqa: E402


def compute(channel: str) -> dict[str, Any]:
    posts = load_jsonl(PROCESSED_DIR / f"{channel}.posts.jsonl")
    threads = load_jsonl(PROCESSED_DIR / f"{channel}.threads.jsonl")
    classified = {c["thread_id"]: c for c in load_jsonl(PROCESSED_DIR / f"{channel}.classified.jsonl")}
    if not posts:
        raise SystemExit(f"no normalised posts for {channel}")

    dated = [p for p in posts if p.get("date")]
    lens = sorted(p["char_len"] for p in posts)
    per_year = Counter(p["year"] for p in dated)
    per_month = Counter(p["month"] for p in dated)
    ids = sorted(p["post_id"] for p in posts)
    gaps = [b - a for a, b in zip(ids, ids[1:]) if b - a > 1]

    def pct(n: int) -> float:
        return round(100.0 * n / max(1, len(posts)), 1)

    stats: dict[str, Any] = {
        "channel": channel,
        "posts_total": len(posts),
        "post_id_min": ids[0],
        "post_id_max": ids[-1],
        "post_ids_missing_in_range": (ids[-1] - ids[0] + 1) - len(ids),
        "largest_id_gaps": sorted(gaps, reverse=True)[:5],
        "date_earliest": min((p["date"] for p in dated), default=None),
        "date_latest": max((p["date"] for p in dated), default=None),
        "posts_without_date": len(posts) - len(dated),
        "posts_per_year": dict(sorted(per_year.items())),
        "months_covered": len(per_month),
        "empty_text_posts": sum(1 for p in posts if p["is_empty"]),
        "exact_duplicate_posts": sum(1 for p in posts if p.get("duplicate_of")),
        "text_length": {
            "min": lens[0],
            "p25": lens[len(lens) // 4],
            "median": lens[len(lens) // 2],
            "p75": lens[3 * len(lens) // 4],
            "p90": lens[min(len(lens) - 1, 9 * len(lens) // 10)],
            "max": lens[-1],
            "mean": round(sum(lens) / len(lens), 1),
        },
        "media": {
            "with_image": pct(sum(1 for p in posts if p["has_image"])),
            "with_video": pct(sum(1 for p in posts if p["has_video"])),
            "with_document": pct(sum(1 for p in posts if p["has_document"])),
            "with_poll": pct(sum(1 for p in posts if p["has_poll"])),
            "text_only": pct(sum(1 for p in posts if not (p["has_image"] or p["has_video"] or p["has_document"]))),
        },
        "forwards": sum(1 for p in posts if p["is_forward"]),
        "replies": sum(1 for p in posts if p.get("reply_to")),
        "languages": dict(Counter(p["lang"] for p in posts)),
        "posts_with_links": sum(1 for p in posts if p["outgoing_links"]),
        "top_link_domains": [
            {"domain": d, "n": n}
            for d, n in Counter(
                u.split("/")[2] for p in posts for u in p["outgoing_links"] if "//" in u
            ).most_common(15)
        ],
        "top_hashtags": [{"tag": t, "n": n} for t, n in Counter(h for p in posts for h in p["hashtags"]).most_common(25)],
        "views_available": sum(1 for p in posts if p.get("views")),
        "reactions_available": sum(1 for p in posts if p.get("reactions_total")),
        "threads_total": len(threads),
        "threads_multi_post": sum(1 for t in threads if t["size"] > 1),
        "total_tokens_estimate": sum(p["token_estimate"] for p in posts),
        "sources": dict(Counter(p.get("source") or "unknown" for p in posts)),
    }

    if classified:
        cats = Counter(c["category"] for c in classified.values())
        scores = sorted(c["content_signal_score"] for c in classified.values())
        stats["classified_threads"] = len(classified)
        stats["categories"] = dict(cats.most_common())
        stats["signal_score"] = {
            "median": scores[len(scores) // 2],
            "p75": scores[3 * len(scores) // 4],
            "p90": scores[min(len(scores) - 1, 9 * len(scores) // 10)],
            ">=50": sum(1 for s in scores if s >= 50),
            ">=70": sum(1 for s in scores if s >= 70),
        }
    else:
        stats["classified_threads"] = 0
        stats["categories"] = {}
    return stats


def render_markdown(s: dict[str, Any]) -> str:
    L: list[str] = []
    a = L.append
    a(f"# Dataset statistics - @{s['channel']}\n")
    a("Raw collection facts only. No interpretation, no AI. Regenerate with:")
    a("`python -m src.reports.dataset_stats`\n")
    a("## Coverage\n")
    a(f"- **Posts collected:** {s['posts_total']}")
    a(f"- **Post id range:** {s['post_id_min']} - {s['post_id_max']} "
      f"({s['post_ids_missing_in_range']} ids missing in range: deletions, service messages, or gaps in the public preview)")
    a(f"- **Date range:** {s['date_earliest']} - {s['date_latest']} ({s['months_covered']} months)")
    a(f"- **Logical threads:** {s['threads_total']} ({s['threads_multi_post']} span several posts)")
    a(f"- **Estimated tokens in corpus:** ~{s['total_tokens_estimate']:,}")
    a(f"- **Collected via:** {s['sources']}\n")
    a("### Posts per year\n")
    a("| Year | Posts |")
    a("|---|---|")
    for y, n in s["posts_per_year"].items():
        a(f"| {y} | {n} |")
    a("")
    a("## Content shape\n")
    t = s["text_length"]
    a(f"- **Length (chars):** min {t['min']} / p25 {t['p25']} / median {t['median']} / p75 {t['p75']} / p90 {t['p90']} / max {t['max']} (mean {t['mean']})")
    a(f"- **Empty-text posts (media only):** {s['empty_text_posts']}")
    a(f"- **Exact duplicate texts:** {s['exact_duplicate_posts']} (kept, flagged via `duplicate_of`)")
    a(f"- **Languages:** {s['languages']}")
    a(f"- **Forwards:** {s['forwards']} | **Replies:** {s['replies']}")
    m = s["media"]
    a(f"- **Media:** image {m['with_image']}% | video {m['with_video']}% | document {m['with_document']}% | poll {m['with_poll']}% | text-only {m['text_only']}%")
    a(f"- **Posts containing links:** {s['posts_with_links']}")
    a(f"- **Views available:** {s['views_available']} posts | **Reactions available:** {s['reactions_available']} posts\n")
    if s["top_link_domains"]:
        a("### Most-linked domains\n")
        a("| Domain | Links |")
        a("|---|---|")
        for d in s["top_link_domains"]:
            a(f"| {d['domain']} | {d['n']} |")
        a("")
    if s["top_hashtags"]:
        a("### Top hashtags\n")
        a("| Tag | Posts |")
        a("|---|---|")
        for h in s["top_hashtags"]:
            a(f"| {h['tag']} | {h['n']} |")
        a("")
    if s.get("categories"):
        a("## Approximate content categories\n")
        a(f"Classified threads: {s['classified_threads']}\n")
        a("| Category | Threads | Share |")
        a("|---|---|---|")
        total = sum(s["categories"].values())
        for c, n in s["categories"].items():
            a(f"| {c} | {n} | {100*n/max(1,total):.1f}% |")
        a("")
        ss = s["signal_score"]
        a(f"**Content signal score:** median {ss['median']}, p75 {ss['p75']}, p90 {ss['p90']}; "
          f"{ss['>=50']} threads >= 50, {ss['>=70']} threads >= 70.\n")
    else:
        a("## Approximate content categories\n")
        a("_Not classified yet. Run `python -m src.classifier.classify`._\n")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    allow_broken_pipe()
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=SCRAPE.channel)
    args = ap.parse_args(argv)
    s = compute(args.channel)
    write_json(PROCESSED_DIR / f"{args.channel}.stats.json", s)
    md = render_markdown(s)
    (OUTPUT_DIR / "DATASET_STATS.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
