"""The terminal JS suite is INVOKED, and invoked COMPLETELY (punch list 2.9, W-27).

`terminal/test/` holds a real suite that no npm script, no runner and no CI step
invoked — `git grep terminal/test` across package.json, tools/ and .github/
returns nothing. It ran only when somebody typed the command by hand, which means
it was evidence nobody collected.

MEASURED, and the measurement governs: **15 files, 222 tests**. The directive says
14 files; that number is stale and is not preserved here.

WHY THE FILE LIST IS EXPLICIT. A glob is what let this suite drift out of view in
the first place: `node --test "terminal/test/*.test.js"` silently covers whatever
happens to match, so a file added tomorrow is either picked up invisibly or
missed invisibly, and neither is a contract. The set is pinned, and adding a test
file is therefore a deliberate act that updates this list.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TERMINAL_TESTS = REPO / "terminal" / "test"

#: The complete measured set. Pinned, not globbed — see the module docstring.
EXPECTED_FILES = (
    "approval-drawer.test.js",
    "conductor-dispatch.test.js",
    "conductor-pane.test.js",
    "inspector-derive.test.js",
    "inspector-model.test.js",
    "layout-reconstruct.test.js",
    "pane-model.test.js",
    "reconstruct.test.js",
    "recovery-machine.test.js",
    "ring-buffer.test.js",
    "session-manager.test.js",
    "session-registry.test.js",
    "statusbar-model.test.js",
    "tiling.test.js",
    "voice-indicator.test.js",
)

#: The measured total. A drop here means tests stopped running, which is exactly the failure this
#: unit exists to make visible — `node --test` reports a skip as `ok`, so a shrinking suite is
#: silent otherwise.
#:
#: SWEEP PROVENANCE (A REPAIR MUST SWEEP WHAT IT MOVED - third instance, after U501 and C4/U530):
#: pinned 216 at W-27 (2026-08-16); the suite grew to 222 through the W-63/W-64 era (U507/U508
#: each recorded 222 passed / 0 failed) and this pin was never swept with those repairs, which
#: U528 mis-read as a subprocess quirk and U537 registered as a stale instrument. Re-taken to
#: 222 by N4b (2026-08-23). Any future change to terminal/test/ updates this pin IN THE SAME
#: COMMIT as the tests that move it.
EXPECTED_TEST_COUNT = 222

_SUMMARY = re.compile(r"^[\sℹ#]*\s*(tests|pass|fail|skipped)\s+(\d+)\s*$", re.MULTILINE)


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("host prerequisite missing: node on PATH — install Node.js")
    return node


def test_the_pinned_file_list_is_exactly_what_is_on_disk() -> None:
    """Both directions: a new test file that nobody added here is caught, and a pinned file that
    was deleted or renamed is caught."""
    on_disk = tuple(sorted(p.name for p in TERMINAL_TESTS.glob("*.test.js")))
    assert on_disk == tuple(sorted(EXPECTED_FILES)), (
        f"terminal/test/ has drifted from the pinned set.\n"
        f"  on disk : {on_disk}\n  pinned  : {tuple(sorted(EXPECTED_FILES))}")
    assert len(EXPECTED_FILES) == 15, "the measured count is 15 files, not the directive's 14"


def test_the_complete_terminal_suite_runs_and_every_test_passes() -> None:
    """W-27's actual acceptance: the COMPLETE set is invoked, from a place a runner reaches, and
    the measured total is preserved. Every file is passed EXPLICITLY rather than by glob."""
    argv = [_node(), "--test", *[f"terminal/test/{name}" for name in EXPECTED_FILES]]
    proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600, check=False)
    counts = {name: int(value) for name, value in _SUMMARY.findall(proc.stdout)}
    assert counts, f"no `node --test` summary:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"

    assert counts["fail"] == 0, f"{counts['fail']} terminal test(s) failed"
    assert counts["skipped"] == 0, (
        f"{counts['skipped']} terminal test(s) SKIPPED — `node --test` reports a skip as `ok`, so "
        f"this would otherwise read green")
    assert counts["tests"] == EXPECTED_TEST_COUNT, (
        f"terminal suite reports {counts['tests']} tests, pinned at {EXPECTED_TEST_COUNT}. A DROP "
        f"means tests stopped running; a RISE means new coverage that should update this pin.")
    assert proc.returncode == 0
