"""Central configuration. Everything is overridable through environment variables.

Design note (see README "Architectural decisions"): no secrets ever live in code or
in committed files. API keys are read from the environment only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
INSIGHTS_DIR = DATA_DIR / "insights"
OUTPUT_DIR = ROOT / "output"
DB_DIR = ROOT / "database"
DB_PATH = DB_DIR / "intelligence.sqlite"

for _p in (RAW_DIR, PROCESSED_DIR, INSIGHTS_DIR, OUTPUT_DIR, DB_DIR):
    _p.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class ScrapeConfig:
    channel: str = field(default_factory=lambda: _env("TG_CHANNEL", "zamesin"))
    base_url: str = "https://t.me"
    # Politeness, not evasion: we slow ourselves down and honour Retry-After.
    delay_seconds: float = field(default_factory=lambda: _env_float("TG_DELAY_SECONDS", 1.0))
    timeout_seconds: int = field(default_factory=lambda: _env_int("TG_TIMEOUT_SECONDS", 30))
    max_retries: int = field(default_factory=lambda: _env_int("TG_MAX_RETRIES", 4))
    user_agent: str = field(
        default_factory=lambda: _env(
            "TG_USER_AGENT",
            "telegram-startup-intelligence/0.1 (public channel archiver; contact: local user)",
        )
    )

    @property
    def preview_url(self) -> str:
        return f"{self.base_url}/s/{self.channel}"

    def post_url(self, post_id: int) -> str:
        return f"{self.base_url}/{self.channel}/{post_id}"


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI-compatible interface. Point base_url at OpenAI, Together, Groq,
    OpenRouter, vLLM, Ollama (/v1) - anything that speaks the chat-completions API."""

    base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "https://api.openai.com/v1"))
    api_key_env: str = field(default_factory=lambda: _env("LLM_API_KEY_ENV", "LLM_API_KEY"))
    model: str = field(default_factory=lambda: _env("LLM_MODEL", "gpt-4o-mini"))
    embedding_model: str = field(default_factory=lambda: _env("LLM_EMBEDDING_MODEL", "text-embedding-3-small"))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.1))
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 4096))
    timeout_seconds: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT_SECONDS", 180))
    max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 4))
    concurrency: int = field(default_factory=lambda: _env_int("LLM_CONCURRENCY", 4))
    cache_enabled: bool = field(default_factory=lambda: _env("LLM_CACHE", "1") != "0")

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "").strip()

    @property
    def available(self) -> bool:
        return bool(self.api_key)


SCRAPE = ScrapeConfig()
LLM = LLMConfig()

# Post classification labels (section 3 of the brief).
POST_CATEGORIES = [
    "CONTENT",
    "PROMO",
    "CONTENT_PLUS_PROMO",
    "PERSONAL",
    "NEWS",
    "CASE",
    "ANNOUNCEMENT",
    "HIRING",
    "REPOST",
    "OTHER",
]

# Categories that may still carry transferable knowledge and therefore go to the
# extractor. PROMO/HIRING/ANNOUNCEMENT are kept in the DB but skipped by default.
EXTRACTABLE_CATEGORIES = {"CONTENT", "CONTENT_PLUS_PROMO", "CASE", "PERSONAL", "NEWS", "REPOST", "OTHER"}

# Knowledge taxonomy (section 7).
TAXONOMY = [
    "CUSTOMER", "JOB", "SEGMENT", "PROBLEM", "NEED", "BEHAVIOR", "VALUE",
    "VALUE_PROPOSITION", "COMPETITION", "PRODUCT", "MVP", "EXPERIMENT", "RISK",
    "RAT", "GROWTH", "RETENTION", "CONVERSION", "DISTRIBUTION", "MARKETING",
    "PRICING", "UNIT_ECONOMICS", "STRATEGY", "FOCUS", "DISRUPTION",
    "BUSINESS_MODEL", "PRODUCT_MARKET_FIT", "ORGANIZATION", "TEAM", "AI",
    "AI_AGENTS", "VIBE_CODING", "AUTOMATION", "STARTUP", "HACKATHON",
]

# Epistemic status of a claim (section 9).
EVIDENCE_TYPES = [
    "OBSERVATION", "HYPOTHESIS", "FRAMEWORK", "PERSONAL_OPINION",
    "CASE_EVIDENCE", "EMPIRICAL_EVIDENCE", "MARKETING_CLAIM", "AUTHOR_CLAIM",
]

# Relationship between two semantically close insights (section 21).
RELATION_TYPES = ["DUPLICATE", "REFINEMENT", "CONTRADICTION", "EXAMPLE", "EVOLUTION"]

# AJTBD concepts we try to reconstruct from the author's own material (section 8).
AJTBD_CONCEPTS = [
    "job", "job_graph", "context", "trigger", "need", "emotion",
    "success_criteria", "job_types", "job_properties", "segmentation", "value",
    "problems", "competing_solutions", "switching", "behavior_change",
    "awareness", "activation", "conversion", "retention", "viral_jobs",
    "tax_jobs", "creating_new_jobs", "destroying_jobs", "multi_job_products",
    "next_job", "disruptive_value",
]
