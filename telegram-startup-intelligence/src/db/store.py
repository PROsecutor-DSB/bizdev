"""SQLite knowledge base. The markdown reports are derived views over this file.

Design notes:
  * every derived row carries provenance (source_post_uid / source_posts JSON),
    so nothing can be read without being traceable back to a Telegram permalink;
  * every LLM-produced row carries `engine` and `prompt_version`, so you can tell
    heuristic output from model output months later;
  * FTS5 gives the query CLI a real lexical search without extra dependencies.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import DB_PATH  # noqa: E402

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS posts (
  post_uid TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  post_id INTEGER NOT NULL,
  date TEXT, month TEXT, year INTEGER,
  permanent_url TEXT NOT NULL,
  raw_text TEXT, text_without_links TEXT,
  outgoing_links TEXT, hashtags TEXT,
  views INTEGER, reactions TEXT, reactions_total INTEGER,
  has_image INTEGER, has_video INTEGER, has_document INTEGER,
  has_poll INTEGER, has_sticker INTEGER,
  is_forward INTEGER, forwarded_from TEXT, forwarded_from_url TEXT,
  reply_to INTEGER, grouped_id INTEGER, link_preview TEXT,
  char_len INTEGER, word_count INTEGER, token_estimate INTEGER,
  lang TEXT, is_empty INTEGER, content_hash TEXT, duplicate_of INTEGER,
  source TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_date ON posts(date);
CREATE INDEX IF NOT EXISTS idx_posts_hash ON posts(content_hash);

CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY,
  channel TEXT, post_ids TEXT, post_uids TEXT, urls TEXT,
  size INTEGER, date_start TEXT, date_end TEXT,
  merge_reasons TEXT, text TEXT, char_len INTEGER, token_estimate INTEGER,
  views_max INTEGER, reactions_total INTEGER, hashtags TEXT,
  has_media INTEGER, is_forward INTEGER
);

CREATE TABLE IF NOT EXISTS classifications (
  thread_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  content_signal_score INTEGER NOT NULL,
  rule_signal_score INTEGER,
  promo_present INTEGER,
  clean_text TEXT,
  removed_promo TEXT,
  tags TEXT,
  reasoning TEXT,
  engine TEXT, prompt_version TEXT, classified_at TEXT,
  FOREIGN KEY(thread_id) REFERENCES threads(thread_id)
);
CREATE INDEX IF NOT EXISTS idx_cls_cat ON classifications(category);
CREATE INDEX IF NOT EXISTS idx_cls_score ON classifications(content_signal_score);

CREATE TABLE IF NOT EXISTS insights (
  insight_id TEXT PRIMARY KEY,
  source_post_id TEXT NOT NULL,
  source_posts TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_urls TEXT,
  date TEXT,
  category TEXT, sub_category TEXT, tags TEXT,
  thesis TEXT NOT NULL, mechanism TEXT, mechanism_missing_reason TEXT,
  why_it_matters TEXT, problem_pattern TEXT, solution_pattern TEXT,
  startup_application TEXT, hackathon_application TEXT,
  example TEXT, anti_pattern TEXT, quote TEXT,
  evidence_type TEXT, evidence_strength INTEGER,
  novelty_score INTEGER, actionability_score INTEGER,
  transferability_score INTEGER, hackathon_value_score INTEGER,
  keywords TEXT,
  content_signal_score INTEGER, views INTEGER, reactions_total INTEGER,
  cluster_id TEXT, is_cluster_representative INTEGER DEFAULT 1,
  engine TEXT, prompt_version TEXT, extracted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ins_cat ON insights(category);
CREATE INDEX IF NOT EXISTS idx_ins_date ON insights(date);
CREATE INDEX IF NOT EXISTS idx_ins_cluster ON insights(cluster_id);

CREATE TABLE IF NOT EXISTS insight_tags (
  insight_id TEXT NOT NULL, tag TEXT NOT NULL,
  PRIMARY KEY (insight_id, tag),
  FOREIGN KEY(insight_id) REFERENCES insights(insight_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_itags_tag ON insight_tags(tag);

CREATE TABLE IF NOT EXISTS ajtbd_concepts (
  concept_uid TEXT PRIMARY KEY,
  concept TEXT NOT NULL, label TEXT,
  definition TEXT, mechanism TEXT, business_consequence TEXT,
  how_to_detect TEXT, how_to_use TEXT, example TEXT,
  divergence_from_classic_jtbd TEXT, quote TEXT, confidence INTEGER,
  source_post_id TEXT, source_url TEXT, date TEXT,
  engine TEXT, prompt_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_ajtbd_concept ON ajtbd_concepts(concept);

CREATE TABLE IF NOT EXISTS embeddings (
  item_id TEXT NOT NULL, kind TEXT NOT NULL,
  dim INTEGER NOT NULL, model TEXT, vector TEXT NOT NULL,
  PRIMARY KEY (item_id, kind)
);

CREATE TABLE IF NOT EXISTS clusters (
  cluster_id TEXT PRIMARY KEY,
  size INTEGER, label TEXT, member_ids TEXT,
  date_start TEXT, date_end TEXT, representative_id TEXT
);

CREATE TABLE IF NOT EXISTS relations (
  a_id TEXT NOT NULL, b_id TEXT NOT NULL,
  relation TEXT NOT NULL, confidence REAL, reasoning TEXT,
  similarity REAL, engine TEXT,
  PRIMARY KEY (a_id, b_id)
);
CREATE INDEX IF NOT EXISTS idx_rel_type ON relations(relation);

CREATE TABLE IF NOT EXISTS patterns (
  pattern_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
  name TEXT NOT NULL, payload TEXT NOT NULL,
  source_posts TEXT NOT NULL, source_insights TEXT NOT NULL,
  date_start TEXT, date_end TEXT, support INTEGER,
  confidence INTEGER, tags TEXT,
  engine TEXT, prompt_version TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pat_kind ON patterns(kind);

CREATE TABLE IF NOT EXISTS derived (
  derived_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
  title TEXT, payload TEXT NOT NULL,
  source_posts TEXT NOT NULL, source_insights TEXT,
  label TEXT NOT NULL DEFAULT 'DERIVED_HYPOTHESIS',
  confidence INTEGER, tags TEXT,
  engine TEXT, prompt_version TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_der_kind ON derived(kind);

CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  stage TEXT, started_at TEXT, finished_at TEXT,
  engine TEXT, params TEXT, stats TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
  insight_id UNINDEXED, thesis, mechanism, why_it_matters,
  startup_application, hackathon_application, keywords, tags,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
  post_uid UNINDEXED, text,
  tokenize='unicode61 remove_diacritics 2'
);
"""

JSON_FIELDS = {
    "link_preview", "outgoing_links", "hashtags", "reactions", "post_ids", "post_uids", "urls",
    "merge_reasons", "tags", "keywords", "source_posts", "source_urls",
    "member_ids", "source_insights", "removed_promo", "params", "stats", "payload",
}


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _encode(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return int(value)
    return value


def decode_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    for k, v in list(d.items()):
        if k in JSON_FIELDS and isinstance(v, str) and v:
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return d


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def upsert(conn: sqlite3.Connection, table: str, rows: Iterable[dict[str, Any]], pk: Sequence[str]) -> int:
    """Insert-or-update, ignoring keys the table does not have.

    Extra keys are dropped rather than raised on: upstream stages legitimately
    carry working fields (chunk bookkeeping, scratch scores) that are not part of
    the persisted schema, and a scraper that learns a new field should not break
    a database written by an older version."""
    rows = list(rows)
    if not rows:
        return 0
    known = table_columns(conn, table)
    cols = sorted({c for r in rows for c in r} & known)
    if not cols:
        return 0
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in pk)
    sql = (
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT({','.join(pk)}) DO UPDATE SET {updates}"
        if updates
        else f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    )
    conn.executemany(sql, [[_encode(r.get(c)) for c in cols] for r in rows])
    conn.commit()
    return len(rows)


def update(conn: sqlite3.Connection, table: str, rows: Iterable[dict[str, Any]], pk: Sequence[str]) -> int:
    """Partial UPDATE of existing rows. Unlike upsert() this never inserts, so it
    is safe for patching a few columns without supplying NOT NULL fields."""
    rows = list(rows)
    if not rows:
        return 0
    known = table_columns(conn, table)
    cols = sorted(({c for r in rows for c in r} & known) - set(pk))
    if not cols:
        return 0
    sql = (
        f"UPDATE {table} SET {','.join(f'{c}=?' for c in cols)} "
        f"WHERE {' AND '.join(f'{k}=?' for k in pk)}"
    )
    conn.executemany(sql, [[_encode(r.get(c)) for c in cols] + [r[k] for k in pk] for r in rows])
    conn.commit()
    return len(rows)


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM insights_fts")
    conn.execute(
        """INSERT INTO insights_fts (insight_id, thesis, mechanism, why_it_matters,
                                     startup_application, hackathon_application, keywords, tags)
           SELECT insight_id, COALESCE(thesis,''), COALESCE(mechanism,''),
                  COALESCE(why_it_matters,''), COALESCE(startup_application,''),
                  COALESCE(hackathon_application,''), COALESCE(keywords,''), COALESCE(tags,'')
           FROM insights"""
    )
    conn.execute("DELETE FROM posts_fts")
    conn.execute(
        """INSERT INTO posts_fts (post_uid, text)
           SELECT post_uid, COALESCE(text_without_links,'') FROM posts"""
    )
    conn.commit()


def start_run(conn: sqlite3.Connection, stage: str, engine: str, params: dict[str, Any]) -> int:
    from src.utils import utcnow_iso

    cur = conn.execute(
        "INSERT INTO runs (stage, started_at, engine, params) VALUES (?,?,?,?)",
        (stage, utcnow_iso(), engine, json.dumps(params, ensure_ascii=False)),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, stats: dict[str, Any]) -> None:
    from src.utils import utcnow_iso

    conn.execute(
        "UPDATE runs SET finished_at=?, stats=? WHERE run_id=?",
        (utcnow_iso(), json.dumps(stats, ensure_ascii=False), run_id),
    )
    conn.commit()


def query(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [decode_row(r) for r in conn.execute(sql, params).fetchall()]


def count(conn: sqlite3.Connection, table: str, where: str = "", params: Sequence[Any] = ()) -> int:
    sql = f"SELECT COUNT(*) AS n FROM {table}" + (f" WHERE {where}" if where else "")
    return int(conn.execute(sql, params).fetchone()["n"])
