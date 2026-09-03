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


def _selected(result: subprocess.CompletedProcess) -> int:
    """The count pytest reports for a `--collect-only -q` run, whether or not it deselected.

    With a `-m` selector the summary reads "N/M tests collected (K deselected)"; without one it
    reads "M tests collected". Both start with the number that was SELECTED.
    """
    match = [ln for ln in result.stdout.splitlines() if "tests collected" in ln]
    if not match:
        return 0
    return int(match[-1].split("/")[0].split()[0])


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

    def test_runtime_worktrees_are_not_collected(self) -> None:
        """A coding pane's own git worktree must never be collected (EPC-04).

        `test_repo_root_collection_reports_no_errors` above catches this only on a host that has
        actually launched a coding pane — on a fresh clone `worktrees/` does not exist and the
        guard passes while the configuration is still wrong. So the exclusion is pinned directly.

        The defect it pins was measured: each `worktrees/worker-<pane>` holds a full copy of
        `modules/sow`, `conftest.py` included, so collecting them registers the same conftest
        plugin twice and pytest INTERRUPTS the run — `ValueError: Plugin already registered`,
        exit 2, no result for the whole product. 2 errors with it collected, 0 without.
        """
        import configparser

        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
        excluded = parser["pytest"]["norecursedirs"].split()
        self.assertIn(
            "worktrees", excluded,
            "`worktrees/` is runtime output (it is already in .git/info/exclude) and collecting "
            "it aborts the whole-product run; it must stay in norecursedirs"
        )

    def test_the_phase19_markers_actually_attach_in_a_whole_product_run(self) -> None:
        """A marker declared but never applied is worse than an absent one.

        `modules/sow/conftest.py` stamps `host_coupled` and `phase19_focused` by looking each
        item up in two `getini` path lists. Only modules/sow/pytest.ini carried those lists, so a
        run from the repository root marked NOTHING: `-m host_coupled` reported "no tests
        collected (4094 deselected)" while the same selector from modules/sow returned its eight
        files. `-m "not host_coupled"` therefore looked like it excluded the load-sensitive tests
        and excluded none of them.

        That is not hypothetical here: `test_opencode_candidate_live` drives a real coder model,
        passes alone in 141s, and times out (returncode 124) against the full suite. It was
        already declared host-coupled and still ran unmarked in the whole-product run.
        """
        for marker in ("host_coupled", "phase19_focused"):
            with self.subTest(marker=marker):
                result = _collect(REPO_ROOT, "-m", marker)
                self.assertGreater(
                    _selected(result), 0,
                    f"`-m {marker}` selects nothing from the repository root — the marker is "
                    f"declared in pytest.ini but its phase19_*_paths list is not, so conftest "
                    f"stamps no item and the selector silently matches nothing"
                )

    def test_the_marking_is_identical_from_either_invocation(self) -> None:
        """The subsets are declared once and must mark the same items however pytest is invoked.

        This is what makes the single-source read in modules/sow/conftest.py checkable: the
        per-module invocation was always correct, so the root invocation is compared against it
        rather than against a number written down here.
        """
        module_root = REPO_ROOT / "modules" / "sow"
        for marker in ("host_coupled", "phase19_focused"):
            with self.subTest(marker=marker):
                from_root = _collect(REPO_ROOT, "-m", marker, "modules/sow/tests")
                from_module = _collect(module_root, "-m", marker, "tests")
                self.assertEqual(
                    _selected(from_root), _selected(from_module),
                    f"`-m {marker}` selects a different set from the repository root than from "
                    f"modules/sow — conftest is not seeing the declared subset in one of them"
                )
                self.assertGreater(_selected(from_module), 0,
                                   f"the {marker} subset is empty; this test proves nothing")

    def test_the_shell_suite_is_reachable_from_the_repository_root(self) -> None:
        """P1-5: shell/tests/__init__.py imports `shell.tests…` absolutely, so it collects
        only from the root — the invocation P1-4's crash used to make impossible."""
        result = _collect(REPO_ROOT, "shell/tests")
        self.assertNotIn("errors during collection", result.stdout + result.stderr)
        self.assertIn("tests collected", result.stdout)


if __name__ == "__main__":
    unittest.main()
