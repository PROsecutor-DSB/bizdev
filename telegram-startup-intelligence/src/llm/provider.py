"""Swappable LLM layer.

Contract (brief section 25): the LLM is used for *meaning* only - classification,
insight/mechanism extraction, synthesis, contradiction detection, opportunity
generation. Never for scraping, IDs, storage or dedup keys.

Two implementations:

  OpenAICompatProvider  - anything that speaks the OpenAI chat-completions +
                          embeddings API (OpenAI, OpenRouter, Together, Groq,
                          vLLM, LM Studio, Ollama's /v1 shim, ...). Configure it
                          purely with LLM_BASE_URL / LLM_MODEL / LLM_API_KEY.

  HeuristicProvider     - a deterministic, offline, rule-based stand-in. It lets
                          the entire pipeline run end-to-end with no API key and
                          no network, which is what the smoke test and CI use.
                          Everything it produces is stamped engine="heuristic"
                          so it can never be mistaken for model-quality output.

Every response is disk-cached under data/processed/.llm_cache/ so re-running the
pipeline costs nothing and stays reproducible.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import LLM, PROCESSED_DIR, LLMConfig  # noqa: E402
from src.utils import sha1  # noqa: E402

CACHE_DIR = PROCESSED_DIR / ".llm_cache"


class LLMProvider(Protocol):
    name: str
    engine: str

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> dict[str, Any]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


# ------------------------------------------------------------------- JSON repair

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def parse_json_loose(text: str) -> dict[str, Any]:
    """LLMs wrap JSON in prose or fences more often than anyone would like."""
    if not text:
        return {}
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else {"items": obj}
    except json.JSONDecodeError:
        pass
    # take the outermost {...} or [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                obj = json.loads(cleaned[start : end + 1])
                return obj if isinstance(obj, dict) else {"items": obj}
            except json.JSONDecodeError:
                continue
    return {}


# ------------------------------------------------------------------------ cache

def _cache_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / f"{key}.json"


def cache_get(key: str) -> dict[str, Any] | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def cache_put(key: str, value: dict[str, Any]) -> None:
    p = _cache_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------- OpenAI-compatible API

class OpenAICompatProvider:
    name = "openai-compatible"
    engine = "llm"

    def __init__(self, cfg: LLMConfig | None = None):
        self.cfg = cfg or LLM
        if not self.cfg.available:
            raise RuntimeError(
                f"No API key found in ${self.cfg.api_key_env}. "
                "Export it, or run with --engine heuristic."
            )
        import requests  # local import keeps the heuristic path dependency-free

        self._requests = requests
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.cfg.api_key}",
                "Content-Type": "application/json",
            }
        )
        self.engine = f"llm:{self.cfg.model}"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.cfg.base_url.rstrip("/") + path
        last: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                r = self._session.post(url, json=payload, timeout=self.cfg.timeout_seconds)
            except self._requests.RequestException as exc:
                last = exc
                time.sleep(min(60, 2 ** attempt))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (408, 409, 429, 500, 502, 503, 504):
                wait = float(r.headers.get("Retry-After") or min(60, 2 ** attempt))
                print(f"  [llm {r.status_code}] retry in {wait:.0f}s", file=sys.stderr)
                time.sleep(wait)
                last = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                continue
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:500]}")
        raise RuntimeError(f"LLM request failed after retries: {last}")

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> dict[str, Any]:
        key = sha1("chat", self.cfg.model, system, user, str(max_tokens))
        if self.cfg.cache_enabled and (hit := cache_get(key)) is not None:
            return hit
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            data = self._post("/chat/completions", payload)
        except RuntimeError:
            # some OpenAI-compatible servers reject response_format; retry plainly
            payload.pop("response_format", None)
            data = self._post("/chat/completions", payload)
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        result = parse_json_loose(content)
        if self.cfg.cache_enabled:
            cache_put(key, result)
        return result

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        batch_size = 64
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            key = sha1("embed", self.cfg.embedding_model, *batch)
            if self.cfg.cache_enabled and (hit := cache_get(key)) is not None:
                out.extend(hit["vectors"])
                continue
            data = self._post("/embeddings", {"model": self.cfg.embedding_model, "input": batch})
            vectors = [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
            if self.cfg.cache_enabled:
                cache_put(key, {"vectors": vectors})
            out.extend(vectors)
        return out


# -------------------------------------------------------- deterministic fallback

class HeuristicProvider:
    """Rule-based stand-in. Honest about being dumb; never blocks the pipeline.

    complete_json() dispatches on a task marker the callers put in the system
    prompt ("TASK: classify" etc.). Each task has a small, readable rule set in
    src/llm/heuristic.py.
    """

    name = "heuristic"
    engine = "heuristic"

    def __init__(self, dim: int = 512):
        from src.llm import heuristic

        self._h = heuristic
        self.dim = dim

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> dict[str, Any]:
        return self._h.dispatch(system, user)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._h.hash_embed(t, self.dim) for t in texts]


# ----------------------------------------------------------------------- factory

_WARNED = False


def get_provider(engine: str = "auto", cfg: LLMConfig | None = None) -> LLMProvider:
    """engine: 'auto' | 'llm' | 'heuristic'."""
    global _WARNED
    cfg = cfg or LLM
    if engine == "heuristic":
        return HeuristicProvider()
    if engine == "llm":
        return OpenAICompatProvider(cfg)
    if cfg.available:
        try:
            return OpenAICompatProvider(cfg)
        except RuntimeError as exc:
            print(f"! falling back to heuristic engine: {exc}", file=sys.stderr)
    elif not _WARNED:
        _WARNED = True
        print(
            f"! ${cfg.api_key_env} is not set - running with the deterministic heuristic engine.\n"
            f"  Output will be marked engine=\"heuristic\" and is NOT model-quality.",
            file=sys.stderr,
        )
    return HeuristicProvider()
