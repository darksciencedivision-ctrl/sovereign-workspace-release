"""The skip-count gate, falsified by injection (2.5, W-23).

`py -3.12` is present on this host, so the real suites skip nothing and the gate
would be green on first contact — an uncalibrated instrument. Red-before-green is
therefore satisfied DETERMINISTICALLY: a synthetic 28-skip summary is injected and
the gate must go RED, then the permitted value is injected and it must go GREEN.

Recorded explicitly, because the difference matters:

    The missing-`py -3.12` HOST BEHAVIOUR was NOT executed. What is proved here is
    the POLICY over a skip count, not that 28 legs actually skip on a host without
    Python 3.12. That remains an outstanding validation leg.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.js_skip_policy import (  # noqa: E402
    SkipSummaryMissing,
    evaluate_skip_policy,
    parse_node_test_summary,
)

#: The shape `node --test` actually prints, captured from a real run on this host.
def _summary(*, tests: int, passed: int, failed: int, skipped: int) -> str:
    return (
        "ℹ tests {t}\nℹ suites 0\nℹ pass {p}\nℹ fail {f}\n"
        "ℹ cancelled 0\nℹ skipped {s}\nℹ todo 0\nℹ duration_ms 210.9202\n"
    ).format(t=tests, p=passed, f=failed, s=skipped)


# ---- (1) inject an unacceptable skip count -> RED -------------------------------------------------

def test_the_gate_goes_RED_on_the_28_skipped_cross_language_legs() -> None:
    """The exact condition the audit measured: 28 JS<->Python legs skip when `py -3.12` is absent
    and the run still reads green."""
    output = _summary(tests=1035, passed=1007, failed=0, skipped=28)
    verdict = evaluate_skip_policy(output, suite="apps/desktop")
    assert verdict.ok is False
    assert verdict.skipped == 28
    assert "28" in verdict.reason
    assert "reads green" in verdict.reason, "the reason must say WHY a green run is the problem"


def test_the_gate_ignores_the_process_exit_code_entirely() -> None:
    """`node --test` exits 0 with skips. A gate that consulted the exit code would agree with the
    defect, so the policy is a pure function of the reported counts."""
    output = _summary(tests=100, passed=99, failed=0, skipped=1)
    assert evaluate_skip_policy(output, suite="any").ok is False


def test_one_skip_over_budget_is_already_RED() -> None:
    assert evaluate_skip_policy(_summary(tests=10, passed=9, failed=0, skipped=1),
                                suite="any", allowed_skips=0).ok is False
    assert evaluate_skip_policy(_summary(tests=10, passed=8, failed=0, skipped=2),
                                suite="any", allowed_skips=1).ok is False


# ---- (2) inject the permitted value -> GREEN ------------------------------------------------------

def test_the_gate_goes_GREEN_on_zero_skips() -> None:
    verdict = evaluate_skip_policy(_summary(tests=1035, passed=1035, failed=0, skipped=0),
                                   suite="apps/desktop")
    assert verdict.ok is True
    assert verdict.skipped == 0


def test_a_stated_budget_is_honoured_exactly() -> None:
    """A budget must be a deliberate number, and equal to it is inside it."""
    assert evaluate_skip_policy(_summary(tests=10, passed=8, failed=0, skipped=2),
                                suite="any", allowed_skips=2).ok is True


# ---- an absent summary is a refusal, not zero ------------------------------------------------------

@pytest.mark.parametrize("output", ["", "some noise\nno summary here\n",
                                    "ℹ tests 5\nℹ pass 5\n"])
def test_a_missing_or_partial_summary_is_REFUSED_not_read_as_zero(output: str) -> None:
    """The failure mode this replaces is a quiet suite. A run that reported nothing must not be
    mistaken for a run that skipped nothing."""
    with pytest.raises(SkipSummaryMissing):
        parse_node_test_summary(output)


def test_both_summary_glyphs_parse() -> None:
    """node prints `ℹ` on a TTY and `#` under some reporters; the count is what matters."""
    hashed = "# tests 4\n# suites 0\n# pass 4\n# fail 0\n# skipped 0\n# todo 0\n"
    assert parse_node_test_summary(hashed)["pass"] == 4


# ---- (3) the real Windows configuration, recorded ---------------------------------------------------

@pytest.mark.parametrize("suite,args", [
    ("terminal", ["--test", "terminal/test/*.test.js"]),
])
def test_the_real_suite_on_this_host_is_recorded(suite: str, args: list[str]) -> None:
    """(3) Run the real configuration here and record what it reports. This host HAS `py -3.12`,
    so the expected observation is zero skips — and that is an observation, not the proof that the
    gate works. The proof is the injection above.

    Only the terminal suite is run here: it takes ~0.3 s. The desktop suite is ~100 s and belongs
    to the W-24 composition, not to a unit test.
    """
    proc = subprocess.run([_node(), *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, check=False)
    verdict = evaluate_skip_policy(proc.stdout, suite=suite)
    assert verdict.ok is True, verdict.reason
    assert verdict.skipped == 0, (
        f"OBSERVED on this host: {verdict.skipped} skipped in {suite}. Recorded, not asserted as "
        f"a cross-host claim.")


def _node() -> str:
    import shutil
    node = shutil.which("node")
    if node is None:                     # pragma: no cover - the prerequisite gate covers this
        pytest.skip("host prerequisite missing: node on PATH")
    return node


# ---- (4) what was NOT executed ---------------------------------------------------------------------

def test_the_missing_python_host_behaviour_is_recorded_as_NOT_EXECUTED() -> None:
    """(4) Stated in the module docstring so it cannot be lost in a summary, and asserted so it
    cannot be quietly deleted."""
    import tests.unit.test_js_skip_policy as self_mod

    assert "was NOT executed" in self_mod.__doc__
    assert "outstanding validation leg" in self_mod.__doc__
