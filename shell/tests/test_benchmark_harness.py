"""SWS-BENCH-02 harness contracts: grading and output ownership."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "tools" / "benchmark"
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(REPO_ROOT / "modules" / "sovereign"))

from run_benchmark import (  # noqa: E402
    grade,
    independent_unsupported,
    token_is_negated,
)


class GradeIndependence(unittest.TestCase):
    def _task(self, **kwargs):
        base = {
            "must_contain": ["5175"],
            "must_not_contain": ["8700"],
            "expect_abstention": False,
            "query": "What port does sovereign listen on?",
        }
        base.update(kwargs)
        return base

    def _packet(self, text="sovereign listens on 5175", source_id="ports"):
        return SimpleNamespace(
            text=text,
            sources=(SimpleNamespace(source_id=source_id, snippet=text),),
        )

    def test_negation_is_not_correct(self) -> None:
        answer = "The sovereign module does not listen on 5175."
        self.assertTrue(token_is_negated(answer, "5175"))
        assessment = MagicMock(unattributed_claims=[], unknown_citations=[], accepted=False)
        with patch("run_benchmark.assess_quick_response", return_value=assessment):
            g = grade(self._task(), answer, {"abstention_markers": ["unknown"]}, self._packet())
        self.assertFalse(g["correct"])
        self.assertIn("5175", g["negated_required"])

    def test_wrong_claim_with_real_citation_is_unsupported(self) -> None:
        answer = "Sovereign listens on 8700 [ports]."
        self.assertGreaterEqual(
            independent_unsupported(self._task(), answer, self._packet()), 1)

    def test_required_words_asserting_the_opposite_are_not_correct(self) -> None:
        answer = "5175 is not the port; the module never uses 5175."
        self.assertTrue(token_is_negated(answer, "5175"))

    def test_unattributed_is_not_the_unsupported_metric(self) -> None:
        assessment = MagicMock(unattributed_claims=["clause"], unknown_citations=[], accepted=True)
        answer = "The sovereign module listens on port 5175 [ports]."
        with patch("run_benchmark.assess_quick_response", return_value=assessment):
            g = grade(self._task(), answer, {"abstention_markers": ["unknown"]}, self._packet())
        self.assertEqual(g["unattributed_claims"], 1)
        self.assertEqual(g["unsupported_claims"], independent_unsupported(
            self._task(), answer, self._packet()))
        self.assertNotEqual(g["unsupported_claims"], g["unattributed_claims"])


class MeasurementSkipSeam(unittest.TestCase):
    def test_production_defaults_do_not_skip_stages(self) -> None:
        from sovereign_product.semantic_deep import SemanticDeepExecutor
        root = REPO_ROOT / "modules" / "sovereign"
        with tempfile.TemporaryDirectory() as tmp:
            ex = SemanticDeepExecutor(
                root, object(), artifact_root=tmp, trusted_roots=(tmp,),
                base_options={"num_ctx": 65536, "num_predict": 1024, "temperature": 0.1, "seed": 1})
            self.assertFalse(ex.skip_critique)
            self.assertFalse(ex.skip_verification)
            ex.set_measurement_skip("critic")
            self.assertTrue(ex.skip_critique)
            self.assertFalse(ex.skip_verification)
            ex.set_measurement_skip("verifier")
            self.assertTrue(ex.skip_verification)

    def test_product_service_does_not_enable_the_seam(self) -> None:
        text = (REPO_ROOT / "modules" / "sovereign" / "sovereign_product" / "server.py").read_text(
            encoding="utf-8")
        self.assertNotIn("set_measurement_skip", text)
        self.assertNotIn("skip_critique=True", text)
        self.assertNotIn("skip_verification=True", text)

    def test_harness_disable_stage_calls_the_seam(self) -> None:
        from run_benchmark import _disable_stage

        class E:
            def set_measurement_skip(self, stage: str) -> None:
                self.stage = stage

        e = E()
        _disable_stage(e, "critic")
        self.assertEqual(e.stage, "critic")


class AnalyzeRejectsContamination(unittest.TestCase):
    def test_mixed_candidate_sha_is_refused(self) -> None:
        sys.path.insert(0, str(BENCH))
        from analyze import load
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.jsonl"
            path.write_text(
                json.dumps({"record_kind": "environment", "candidate_sha": "aaa",
                            "partial": True}) + "\n"
                + json.dumps({"record_kind": "run", "candidate_sha": "aaa",
                              "task_id": "gf-01", "condition": "A_single",
                              "run_index": 0, "grade": {"correct": True}}) + "\n"
                + json.dumps({"record_kind": "run", "candidate_sha": "bbb",
                              "task_id": "gf-02", "condition": "A_single",
                              "run_index": 0, "grade": {"correct": True}}) + "\n",
                encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)


class OutputOwnership(unittest.TestCase):
    def test_refuses_to_overwrite_without_resume(self) -> None:
        script = BENCH / "run_benchmark.py"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "runs.jsonl"
            out.write_text("{}\n", encoding="utf-8")
            env = os.environ.copy()
            proc = subprocess.run(
                [sys.executable, str(script), "--out", str(out), "--runs", "1",
                 "--conditions", "A_single", "--tasks", "gf-01"],
                capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=30)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("refusing to overwrite", (proc.stdout + proc.stderr).lower())


if __name__ == "__main__":
    unittest.main()
