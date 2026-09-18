"""Measure the deterministic classifier against known labels.

This is the automated half of STEP 4. The manual half, on the real channel,
is `python -m src.classifier.audit sample`.

The number that matters is not raw accuracy but CONTENT RECALL: of the posts
that genuinely carry transferable knowledge, how many stayed in a category the
extractor will read. A PROMO misread as CONTENT costs a few tokens. A CONTENT
misread as PROMO loses knowledge permanently.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import EXTRACTABLE_CATEGORIES, PROCESSED_DIR  # noqa: E402
from src.utils import load_jsonl  # noqa: E402

CHANNEL = "demo_channel"
SUBSTANTIVE = {"CONTENT", "CONTENT_PLUS_PROMO", "CASE"}


def test_classifier_quality(min_recall: float = 90.0, min_accuracy: float = 60.0) -> dict:
    labels = {r["post_uid"]: r["category"] for r in load_jsonl(Path(__file__).parent / "fixtures" / "demo_channel.labels.jsonl")}
    threads = {t["thread_id"]: t for t in load_jsonl(PROCESSED_DIR / f"{CHANNEL}.threads.jsonl")}
    classified = load_jsonl(PROCESSED_DIR / f"{CHANNEL}.classified.jsonl")
    assert classified, "run the classifier on demo_channel first"

    pairs: list[tuple[str, str]] = []
    for c in classified:
        t = threads[c["thread_id"]]
        truths = {labels[u] for u in t["post_uids"] if u in labels}
        if not truths:
            continue
        # a merged thread inherits the strongest label present in it
        truth = next((x for x in ("CONTENT", "CONTENT_PLUS_PROMO", "CASE") if x in truths), sorted(truths)[0])
        pairs.append((truth, c["category"]))

    accuracy = 100.0 * sum(1 for a, b in pairs if a == b) / len(pairs)
    subs = [(a, b) for a, b in pairs if a in SUBSTANTIVE]
    recall = 100.0 * sum(1 for _, b in subs if b in EXTRACTABLE_CATEGORIES) / max(1, len(subs))
    promo = [(a, b) for a, b in pairs if a in ("PROMO", "HIRING", "ANNOUNCEMENT")]
    noise_precision = 100.0 * sum(1 for _, b in promo if b in ("PROMO", "HIRING", "ANNOUNCEMENT")) / max(1, len(promo))

    print(f"threads compared:        {len(pairs)}")
    print(f"exact category accuracy: {accuracy:.1f}%")
    print(f"content recall:          {recall:.1f}%  ({len(subs)} substantive threads)")
    print(f"noise caught:            {noise_precision:.1f}%  ({len(promo)} promo/hiring/announcement threads)")
    print("\nconfusion (truth -> predicted):")
    for (a, b), n in Counter(pairs).most_common():
        print(f"  {'  ' if a == b else '! '}{a:<20} -> {b:<20} {n}")

    assert recall >= min_recall, f"content recall {recall:.1f}% below {min_recall}% - knowledge is being discarded"
    assert accuracy >= min_accuracy, f"accuracy {accuracy:.1f}% below {min_accuracy}%"
    return {"accuracy": accuracy, "content_recall": recall, "noise_precision": noise_precision}


if __name__ == "__main__":
    test_classifier_quality()
    print("\nclassifier quality: OK")
