"""Run every test in order. `python tests/run_all.py`"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_classifier_quality  # noqa: E402
import test_pipeline_e2e  # noqa: E402
import test_scraper_parse  # noqa: E402
import test_units  # noqa: E402

TESTS = [
    ("units", test_units.run_all),
    ("scraper parse + pagination", test_scraper_parse.run_all),
    ("pipeline e2e", test_pipeline_e2e.test_e2e),
    ("classifier quality", test_classifier_quality.test_classifier_quality),
]


def main() -> int:
    failed = []
    for name, fn in TESTS:
        print(f"\n=== {name} ===")
        try:
            fn()
        except Exception:
            traceback.print_exc()
            failed.append(name)
    print("\n" + "=" * 50)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"all {len(TESTS)} test groups passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
