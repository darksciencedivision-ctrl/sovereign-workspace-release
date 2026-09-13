"""F-117 (RESEARCH half) — a progress event with no derivable percent must not be dropped.

RESEARCH progress events carry a stage/detail but no percent. _safe_progress defaulted the percent
to 0, which the store rejected as a regression below the job's initial 1% (InvalidTransition,
swallowed), so RESEARCH sat at "running 1%" for its whole (multi-hour) duration. _safe_progress now
OMITS percent when none is present or derivable, so update_job_progress keeps the prior percent and
the stage/detail advance. (The DEEP half -- resolving the recovery pointer through the shared
contract instead of the install root -- is exercised by the pointer-resolution tests.)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.server import _safe_progress  # noqa: E402


class SafeProgressPercent(unittest.TestCase):
    def test_a_research_style_event_omits_percent_rather_than_zeroing_it(self) -> None:
        out = _safe_progress({"stage": "iterating", "detail": "hypothesis 3"},
                             fallback_stage="running")
        self.assertNotIn("percent", out, "a percent-less event must not be forced to 0 (F-117)")
        self.assertEqual(out["stage"], "iterating")

    def test_a_derivable_percent_is_computed(self) -> None:
        self.assertEqual(
            _safe_progress({"current": 3, "total": 4}, fallback_stage="running")["percent"], 75.0)

    def test_an_explicit_percent_is_preserved_and_clamped(self) -> None:
        self.assertEqual(_safe_progress({"percent": 42}, fallback_stage="running")["percent"], 42.0)
        self.assertEqual(_safe_progress({"percent": 250}, fallback_stage="running")["percent"], 100)

    def test_a_boolean_percent_is_not_treated_as_a_number(self) -> None:
        # bool is an int subclass; it must fall through to omission, not become 1%/0%.
        out = _safe_progress({"percent": True}, fallback_stage="running")
        self.assertNotIn("percent", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
