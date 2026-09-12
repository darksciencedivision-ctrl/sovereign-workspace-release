"""R38 — a crash after final synthesis resumes to completion, with no duplicate synthesis.

Final synthesis and finalization used to be one loop turn: after the synthesis output was
checkpointed (next_phase=None), the same turn marked the run completed and wrote the final
artifacts. A crash in that window left `final_synthesis` persisted but the run not completed, and
resume raised "non-completed state has no next phase" -- the run could never finish.

Finalization is now its own durable, idempotent, model-free phase. On resume, a state whose
synthesis was persisted (whether next_phase is the new FINALIZE or a legacy None) finalizes rather
than failing, and it never calls the model again.

These drive the executor's control flow directly with the model-producing helpers stubbed, so the
fix is exercised without a full multi-phase model pipeline; the model client raises if generation
is ever attempted, which is exactly the "no duplicate synthesis call" assertion.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from sovereign_product.paths import (  # noqa: E402
    ROOT_MARKER,
    ROOT_MARKER_CONTENT,
    resolve_product_paths,
)
from sovereign_product.research import (  # noqa: E402
    ResearchExecutor,
    ResearchPhase,
    ResearchStatus,
)


class _Client:
    def generate(self, **kwargs):
        raise AssertionError("finalization must not call the model (would be a duplicate synthesis)")


class DurableFinalization(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="r38-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        root = self.tmp / "install"
        root.mkdir()
        (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
        (root / "SYSTEM_MANIFEST.json").write_text("{}", encoding="utf-8")
        state = self.tmp / "external-state"
        paths = resolve_product_paths(
            root, state_dir=state, approved_roots=(state,), create=True)
        self.executor = ResearchExecutor(paths, _Client())
        # Stub the side-effecting finalization helpers so we exercise control flow, not a full
        # valid checkpoint chain. Record what finalization does.
        self.writes: list[bool] = []
        self.checkpoints: list[str] = []
        self.executor._write_final_artifacts = (  # type: ignore[assignment]
            lambda st, *, completed: self.writes.append(completed))
        self.executor._checkpoint = (  # type: ignore[assignment]
            lambda st, reason: self.checkpoints.append(reason))
        self.executor._result = (  # type: ignore[assignment]
            lambda st: {"status": st["status"], "next_phase": st.get("next_phase")})

    def _synthesized_state(self, *, next_phase) -> dict:
        return {
            "research_id": "r1",
            "status": ResearchStatus.RUNNING.value,
            "next_phase": next_phase,
            "final_synthesis": {"summary": "the answer", "remaining_unknowns": []},
            "resources": {"active_seconds": 1.0, "model_calls": 5, "phase_failures": 0},
            "completed_at": None,
        }

    def test_resume_from_legacy_next_phase_none_finalizes(self) -> None:
        # The exact crash window: synthesis persisted, next_phase left None, status still running.
        state = self._synthesized_state(next_phase=None)
        result = self.executor._drive(state)
        self.assertEqual(state["status"], ResearchStatus.COMPLETED.value)
        self.assertEqual(result["status"], ResearchStatus.COMPLETED.value)
        self.assertEqual(self.writes, [True], "final artifacts were not published on finalize")
        self.assertIn("research-completed", self.checkpoints)
        self.assertIsNone(state["next_phase"])

    def test_resume_from_finalize_phase_finalizes(self) -> None:
        state = self._synthesized_state(next_phase=ResearchPhase.FINALIZE.value)
        result = self.executor._drive(state)
        self.assertEqual(result["status"], ResearchStatus.COMPLETED.value)
        self.assertEqual(self.writes, [True])

    def test_an_already_completed_state_is_returned_without_re_publishing(self) -> None:
        state = self._synthesized_state(next_phase=None)
        state["status"] = ResearchStatus.COMPLETED.value
        result = self.executor._drive(state)
        self.assertEqual(result["status"], ResearchStatus.COMPLETED.value)
        self.assertEqual(self.writes, [], "a completed run must not re-publish artifacts on resume")

    def test_finalize_is_idempotent(self) -> None:
        state = self._synthesized_state(next_phase=ResearchPhase.FINALIZE.value)
        self.executor._finalize(state)
        first_completed_at = state["completed_at"] if state.get("completed_at") else "set"
        state["completed_at"] = first_completed_at
        self.executor._finalize(state)      # running it again must be a harmless no-op-equivalent
        self.assertEqual(state["status"], ResearchStatus.COMPLETED.value)
        self.assertEqual(state["completed_at"], first_completed_at,
                         "a second finalize moved completed_at; it is not idempotent")

    def test_a_running_state_with_no_synthesis_and_no_phase_is_not_faked_complete(self) -> None:
        # Nothing was synthesized, so there is nothing to finalize: the run must NOT be reported as
        # completed. _drive routes the unrecoverable state to a failed result rather than pretending
        # it finished.
        state = self._synthesized_state(next_phase=None)
        state["final_synthesis"] = None
        result = self.executor._drive(state)
        self.assertEqual(result["status"], ResearchStatus.FAILED.value)
        self.assertNotIn(True, self.writes, "a failed run must not publish a completed report")


if __name__ == "__main__":
    unittest.main(verbosity=2)
