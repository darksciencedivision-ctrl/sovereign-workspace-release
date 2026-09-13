#!/usr/bin/env python
"""P2 benchmark validity: R09/F-091, R10, R11, F-090.

R09/F-091: execution failures were "records without a grade" -- but the runner grades every
           execution, so that was always 0. Failures/timeouts/grading-failures are now counted
           from structured record fields.
R10: a timeout was any reason containing the substring "timeout", so a normal rejection whose
     prose discussed timeout settings was mis-counted. It is now the structured status only.
R11: completeness trusted per-row `partial` flags; it is now derived from the planned Cartesian
     design and forces PRELIMINARY on any shortfall.
F-090: the citation-support check looked for [<sid>], but the packet cites [source:<sid>], so
       citation-support errors were structurally uncounted.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze  # noqa: E402
import run_benchmark  # noqa: E402


def _packet(text, sources):
    return types.SimpleNamespace(
        text=text,
        sources=[types.SimpleNamespace(source_id=sid, snippet=snip) for sid, snip in sources])


class F090_CitationSupport(unittest.TestCase):
    def setUp(self):
        self.task = {"must_contain": ["widgets"], "must_not_contain": [], "expect_abstention": False}
        self.packet = _packet("source A: widgets in stock. source B: gadgets only.",
                              [("srcA", "widgets in stock"), ("srcB", "gadgets only")])

    def test_citing_the_wrong_source_is_a_support_error(self) -> None:
        # "widgets" is cited to srcB, whose snippet does not contain it.
        count = run_benchmark.independent_unsupported(
            self.task, "We have widgets [source:srcB].", self.packet)
        self.assertGreaterEqual(count, 1, "a wrong-source citation must be counted (F-090)")

    def test_citing_the_correct_source_is_not_an_error(self) -> None:
        count = run_benchmark.independent_unsupported(
            self.task, "We have widgets [source:srcA].", self.packet)
        self.assertEqual(count, 0)


class R09_R10_StructuredFailureCounts(unittest.TestCase):
    def _run(self, **kw):
        base = {"condition": "A_single", "task_id": "t1", "run_index": 0, "category": "cat",
                "elapsed_s": 1.0, "grade": {"correct": True, "abstained": False,
                                            "unsupported_claims": 0, "citation_errors": 0}}
        base.update(kw)
        return base

    def test_counts_are_structured_not_grade_absence(self) -> None:
        runs = [
            self._run(),                                              # clean
            self._run(error="RuntimeError: boom", grade=None),       # execution error
            self._run(error="timeout", timed_out=True, grade=None),  # timeout
            self._run(grade=None, error=None),                       # grading failure (ran, no grade)
            # A normal rejection whose reason MENTIONS timeout -- must NOT be a timeout (R10).
            self._run(status="rejected", reason="the timeout setting is 30s",
                      error=None, timed_out=False),
        ]
        s = analyze.summarise(runs, "A_single")
        self.assertEqual(s["execution_errors"], 2)   # RuntimeError + the real timeout
        self.assertEqual(s["timeouts"], 1)            # only the structured timeout
        self.assertEqual(s["grading_failures"], 1)    # error-free run with no grade


class R11_Completeness(unittest.TestCase):
    def _write(self, tmp, env, runs):
        path = Path(tmp) / "runs.jsonl"
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"record_kind": "environment", **env}) + "\n")
            for r in runs:
                f.write(json.dumps({"record_kind": "run", **r}) + "\n")
        return path

    def _run(self, cond, task, idx):
        return {"condition": cond, "task_id": task, "run_index": idx, "category": "cat",
                "candidate_sha": "abc", "grade": {"correct": True, "abstained": False,
                                                   "unsupported_claims": 0, "citation_errors": 0}}

    def test_a_missing_cell_forces_preliminary(self) -> None:
        env = {"candidate_sha": "abc", "conditions": ["A_single"], "runs_per_cell": 1,
               "task_count": 2, "partial": False}
        # Only 1 of the 2 planned tasks present.
        runs = [self._run("A_single", "t1", 0)]
        tmp = tempfile.mkdtemp(prefix="r11-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = self._write(tmp, env, runs)
        out = io.StringIO()
        with redirect_stdout(out):
            analyze.main(["--results", str(path)])
        text = out.getvalue()
        self.assertIn("PRELIMINARY", text)
        self.assertIn("incomplete:", text)

    def test_a_complete_set_is_not_flagged(self) -> None:
        env = {"candidate_sha": "abc", "conditions": ["A_single"], "runs_per_cell": 1,
               "task_count": 2, "partial": False}
        runs = [self._run("A_single", "t1", 0), self._run("A_single", "t2", 0)]
        tmp = tempfile.mkdtemp(prefix="r11b-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = self._write(tmp, env, runs)
        out = io.StringIO()
        with redirect_stdout(out):
            analyze.main(["--results", str(path)])
        self.assertNotIn("PRELIMINARY", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
