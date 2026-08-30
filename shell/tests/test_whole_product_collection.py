"""EPC-01 P1-4 / P1-5 — `pytest` at the repository root must collect, not crash.

Two defects composed into "there is no way to run this product's tests":

  * `modules/sow/conftest.py` called `item.path.resolve().relative_to(ROOT)` on EVERY
    collected item. Anything outside modules/sow raised ValueError, which pytest reports as
    INTERNALERROR and which aborts the entire run. It reached recipients: `pytest` at the
    root of the extracted archive crashed rather than reporting a result.
  * Underneath the crash, `shell/tests/__init__.py` imports `shell.tests._fswatch`
    absolutely, so the shell suite requires the repository root on sys.path — the very
    invocation the crash made impossible.

This test runs collection in a subprocess and asserts the outcome, because the failure mode
is a crash of the collector itself and cannot be observed from inside a collected test.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Below this, something has stopped being collected and the guard has gone quiet. The
#: measured figure when this test was written was 3721; the floor allows for ordinary churn
#: while still failing loudly if a tree drops out.
MINIMUM_COLLECTED = 3000


def _collect(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider", *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=600,
    )


class WholeProductCollection(unittest.TestCase):

    def test_repo_root_collection_does_not_raise_internalerror(self) -> None:
        result = _collect(REPO_ROOT)
        self.assertNotIn(
            "INTERNALERROR", result.stdout + result.stderr,
            "collection at the repository root crashed the collector. This is the defect a "
            "recipient hits when they run pytest on the extracted archive."
        )

    def test_repo_root_collection_reports_no_errors(self) -> None:
        result = _collect(REPO_ROOT)
        combined = result.stdout + result.stderr
        self.assertNotIn(
            "errors during collection", combined,
            "collection at the repository root reported import errors:\n"
            + "\n".join(ln for ln in combined.splitlines() if ln.startswith("ERROR"))
        )

    def test_the_whole_product_is_actually_collected(self) -> None:
        result = _collect(REPO_ROOT)
        match = [ln for ln in result.stdout.splitlines() if "tests collected" in ln]
        self.assertTrue(match, f"no collection summary in output:\n{result.stdout[-2000:]}")
        count = int(match[-1].split()[0])
        self.assertGreaterEqual(
            count, MINIMUM_COLLECTED,
            f"only {count} tests collected from the repository root; a tree has stopped "
            f"being collected"
        )

    def test_each_module_still_collects_on_its_own(self) -> None:
        """The root configuration must not break the per-module invocation, which is how
        each module was tested before a whole-product run existed."""
        for module in ("sow", "distillery", "debate", "tokencenter"):
            path = REPO_ROOT / "modules" / module
            if not path.is_dir():
                continue
            with self.subTest(module=module):
                result = _collect(path)
                self.assertNotIn("INTERNALERROR", result.stdout + result.stderr)
                self.assertNotIn(
                    "errors during collection", result.stdout + result.stderr,
                    f"modules/{module} stopped collecting on its own"
                )

    def test_the_shell_suite_is_reachable_from_the_repository_root(self) -> None:
        """P1-5: shell/tests/__init__.py imports `shell.tests…` absolutely, so it collects
        only from the root — the invocation P1-4's crash used to make impossible."""
        result = _collect(REPO_ROOT, "shell/tests")
        self.assertNotIn("errors during collection", result.stdout + result.stderr)
        self.assertIn("tests collected", result.stdout)


if __name__ == "__main__":
    unittest.main()
