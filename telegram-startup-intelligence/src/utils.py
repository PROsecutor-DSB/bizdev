"""Deterministic helpers: IDs, text normalisation, JSONL I/O.

Everything in here is pure Python and reproducible. No LLM, no network.
Rule from the brief (section 25): parsing, storage and dedup IDs must be
deterministic; the LLM only reasons about meaning.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<![\w/#])#([A-Za-zА-Яа-яЁё0-9_]{2,40})")
MENTION_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_]{4,32})")
WS_RE = re.compile(r"[ \t ]+")
MULTINEWLINE_RE = re.compile(r"\n{3,}")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha1(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()


def post_uid(channel: str, post_id: int | str) -> str:
    """Stable primary key for a post across re-scrapes."""
    return f"{channel}/{post_id}"


def insight_id(source_post_id: str, thesis: str) -> str:
    """Deterministic insight id: same post + same thesis => same id, always.

    This makes re-runs idempotent and lets us upsert instead of duplicating.
    """
    return "ins_" + sha1(source_post_id, normalize_for_hash(thesis))[:20]


def cluster_id(member_ids: Iterable[str]) -> str:
    return "clu_" + sha1("|".join(sorted(member_ids)))[:16]


def derived_id(prefix: str, key: str) -> str:
    return f"{prefix}_" + sha1(normalize_for_hash(key))[:16]


def normalize_for_hash(text: str) -> str:
    """Aggressive normalisation used only for hashing/near-duplicate keys."""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = URL_RE.sub(" ", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clean_whitespace(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = WS_RE.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = MULTINEWLINE_RE.sub("\n\n", t)
    return t.strip()


def extract_urls(text: str) -> list[str]:
    seen: list[str] = []
    for m in URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?)")
        if u not in seen:
            seen.append(u)
    return seen


def extract_hashtags(text: str) -> list[str]:
    seen: list[str] = []
    for m in HASHTAG_RE.finditer(text or ""):
        tag = "#" + m.group(1)
        if tag not in seen:
            seen.append(tag)
    return seen


def strip_links(text: str) -> str:
    """text_without_links: URLs removed, surrounding text kept readable."""
    t = URL_RE.sub(" ", text or "")
    t = WS_RE.sub(" ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return MULTINEWLINE_RE.sub("\n\n", t).strip()


def token_count_estimate(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~3.3 chars/token for ru+en mix)."""
    return max(1, int(len(text or "") / 3.3))


# --------------------------------------------------------------------------- IO

def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def clamp(value: Any, lo: float, hi: float, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def clamp_int(value: Any, lo: int, hi: int, default: int = 0) -> int:
    return int(round(clamp(value, lo, hi, default)))
