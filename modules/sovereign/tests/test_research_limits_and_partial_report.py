"""F-116 (research executor half) — product-appropriate limits, no disposition quota, partial
reports surfaced.

The RESEARCH defaults were an eight-hour proof configuration: a minimum of eight iterations, an
eight-hour ceiling, and a disposition quota (a run could not be considered successful until it had
both rejected AND revised a hypothesis). An ordinary operator question was forced through
manufactured iterations, and a one-pass answer was held incomplete. And a run that exhausted its
budget returned empty rather than its partial report.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER,
    ROOT_MARKER_CONTENT,
    resolve_product_paths,
)
from sovereign_product.research import ResearchExecutor, ResearchLimits  # noqa: E402
from sovereign_product.server import ProductService, _terminal_status  # noqa: E402


class ProductAppropriateDefaults(unittest.TestCase):
    def test_defaults_are_product_scale_and_have_no_quota(self) -> None:
        limits = ResearchLimits()
        self.assertEqual(limits.minimum_iterations, 1)
        self.assertLessEqual(limits.maximum_duration_seconds, 60 * 60)
        self.assertFalse(limits.require_rejected_hypothesis)
        self.assertFalse(limits.require_revised_hypothesis)


class TargetsMetWithoutTheQuota(unittest.TestCase):
    def _state(self, limits: ResearchLimits, *, iterations, decisions) -> dict:
        return {
            "limits": asdict(limits),
            "completed_iterations": iterations,
            "resources": {"active_seconds": 0.0},
            "iterations": [{"decision": {"decision": d}} for d in decisions],
        }

    def test_a_single_pass_with_no_dispositions_meets_the_default_targets(self) -> None:
        state = self._state(ResearchLimits(), iterations=1, decisions=["retain"])
        self.assertTrue(ResearchExecutor._targets_met(object(), state))

    def test_the_quota_is_still_enforceable_when_explicitly_requested(self) -> None:
        strict = ResearchLimits(require_rejected_hypothesis=True, require_revised_hypothesis=True)
        state = self._state(strict, iterations=1, decisions=["retain"])
        self.assertFalse(ResearchExecutor._targets_met(object(), state))


class _FakeService:
    def __init__(self, paths) -> None:
        self.paths = paths

    _research_answer = ProductService._research_answer


class PartialReportsAreSurfaced(unittest.TestCase):
    def test_terminal_status_maps_budget_exhausted_with_a_report_to_completed(self) -> None:
        self.assertEqual(_terminal_status("budget_exhausted", has_answer=True), "completed")
        self.assertEqual(_terminal_status("budget_exhausted", has_answer=False), "rejected")

    def test_research_answer_returns_a_partial_report(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="f116-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        root = tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        state = tmp / "external-state"
        paths = resolve_product_paths(
            root, state_dir=state, approved_roots=(state,), create=True)
        report = paths.evidence_dir / "research" / "r1" / "final_report.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# partial findings\nas far as the budget allowed", encoding="utf-8")
        pointer = paths.make_pointer(report)

        svc = _FakeService(paths)
        answer = svc._research_answer(
            {"status": "budget_exhausted"}, {"final_report": pointer})
        self.assertIn("partial findings", answer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
