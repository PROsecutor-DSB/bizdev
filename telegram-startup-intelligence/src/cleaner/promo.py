"""Promo-shell removal, exposed as a standalone module for auditing.

The rule is from brief section 3: a post that sells a course AND states a real
principle keeps the principle and loses the sales copy. Nothing is deleted from
the corpus - `clean_text` is an additional field next to the untouched original.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm.heuristic import strip_promo_shell  # noqa: F401,E402

__all__ = ["strip_promo_shell"]
