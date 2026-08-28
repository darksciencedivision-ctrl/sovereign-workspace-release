"""The Phase 19 pytest wrapper's TERMINATION path (punch list 6.12).

The wrapper exists to hold the committed wall-clock ceiling. It could not: on a
timeout it sent SIGTERM to the process group and then called `process.wait()`
with **no timeout**, so a child that ignores termination hung the wrapper
forever and the ceiling never fired. On Windows `_terminate_tree` already used
`taskkill /T /F`, which cannot be ignored; the unbounded wait was a defect on
both platforms and the soft-only signal was a defect on POSIX.

These tests never spawn a real unkillable child. The policy is isolated and
falsified deterministically: the stub's `wait()` raises on the UNBOUNDED call,
so the defect shows up as an explicit failure instead of hanging the suite that
is testing it.
"""
from __future__ import annotations

import subprocess

import pytest

from tools import run_phase19_pytest as mod


class _IgnoresTermination:
    """A child that survives the soft signal and dies only on the hard kill."""

    def __init__(self, *, dies_on_hard_kill: bool = True) -> None:
        self.hard_killed = False
        self.dies_on_hard_kill = dies_on_hard_kill
        self.pid = 4242
        self.bounded_waits: list[float] = []

    def poll(self):
        return -9 if (self.hard_killed and self.dies_on_hard_kill) else None

    def wait(self, timeout=None):
        if timeout is None:
            raise AssertionError(
                "the runner waited on a terminated child with NO timeout: a child that ignores "
                "termination hangs here forever and the committed ceiling never fires")
        self.bounded_waits.append(timeout)
        if self.hard_killed and self.dies_on_hard_kill:
            return -9
        raise subprocess.TimeoutExpired("pytest", timeout)


def _install(monkeypatch, child):
    """Bind the stub in place of a real spawn, and record the escalation steps."""
    steps: list[bool] = []

    def _fake_terminate(process, hard=False):
        steps.append(bool(hard))
        if hard:
            process.hard_killed = True

    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(mod, "_terminate_tree", _fake_terminate)
    return steps


def test_a_child_that_ignores_termination_is_hard_killed_within_a_declared_ceiling(
        monkeypatch, capsys) -> None:
    """6.12 NEGATIVE. Pre-repair this fails on the unbounded `wait()` assertion above."""
    child = _IgnoresTermination()
    steps = _install(monkeypatch, child)

    rc = mod.main(["full"])

    assert steps == [False, True], (
        f"expected terminate then hard-kill escalation, got {steps}")
    assert rc == 124, "a suite that blew its ceiling still reports the ceiling code"
    assert all(t is not None and t > 0 for t in child.bounded_waits), (
        "every wait after the ceiling must be BOUNDED")
    assert "ceiling" in capsys.readouterr().err


def test_a_child_that_survives_the_hard_kill_is_an_explicit_failure(
        monkeypatch, capsys) -> None:
    """6.12 NEGATIVE, the other end: unreaped must be REPORTED, never waited on forever."""
    child = _IgnoresTermination(dies_on_hard_kill=False)
    steps = _install(monkeypatch, child)

    rc = mod.main(["full"])

    assert steps == [False, True]
    assert rc != 0 and rc != 124, (
        "a tree that outlived the hard kill is a different outcome from a plain ceiling breach")
    err = capsys.readouterr().err
    assert "ceiling" in err
    assert "unreaped" in err.lower() or "did not" in err.lower()


def test_a_suite_that_finishes_inside_the_ceiling_is_untouched(monkeypatch) -> None:
    """POSITIVE. The escalation must not run for a normal completion."""
    class _Finishes:
        pid = 4242

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    steps = _install(monkeypatch, _Finishes())
    assert mod.main(["full"]) == 0
    assert steps == [], "no termination step may run when the suite finished on its own"


def test_the_escalation_bounds_are_declared_and_positive() -> None:
    """The ceiling is only a ceiling if every wait beneath it is finite."""
    assert isinstance(mod.TERMINATE_GRACE_SECONDS, (int, float))
    assert isinstance(mod.HARD_KILL_GRACE_SECONDS, (int, float))
    assert mod.TERMINATE_GRACE_SECONDS > 0
    assert mod.HARD_KILL_GRACE_SECONDS > 0


def test_the_posix_soft_signal_escalates_to_SIGKILL(monkeypatch) -> None:
    """POSIX-only half of the defect: the soft path sent SIGTERM and nothing else. Asserted
    through the signal the code selects, so it is checked on this Windows host too."""
    if mod.os.name == "nt":
        pytest.skip("POSIX process-group signalling; the Windows path uses taskkill /T /F")
    sent: list[int] = []
    monkeypatch.setattr(mod.os, "killpg", lambda pid, sig: sent.append(sig))
    proc = _IgnoresTermination()
    mod._terminate_tree(proc)                 # noqa: SLF001 - the unit under test
    mod._terminate_tree(proc, hard=True)      # noqa: SLF001
    assert sent == [mod.signal.SIGTERM, mod.signal.SIGKILL]


# -----------------------------------------------------------------------------------------
# CARD 00 / U480: a ceiling breach and a suite failure are DIFFERENT outcomes.
#
# The wrapper holds the committed wall-clock ceiling. What it may not do anymore is let a
# breach and a failure collapse onto one exit code: a breach with ZERO test failures
# observed before the kill is host load, not a product verdict, and keeps exit 124. A
# breach with at least one observed failure/error takes the distinct exit 123 so the
# downstream gate can keep grading it FAIL. The unreaped tree stays 125.
# -----------------------------------------------------------------------------------------

import io
from types import SimpleNamespace

from tools import run_phase19_gate as gate_mod


class _BreachesWithCapturedOutput:
    """A child that outlives the ceiling; its partial output survives the kill."""

    pid = 4242

    def __init__(self, stream: bytes) -> None:
        self.stdout = io.BytesIO(stream)

    def poll(self):
        return None

    def wait(self, timeout=None):
        if getattr(self, "hard_killed", False):
            return -9
        raise subprocess.TimeoutExpired("pytest", timeout)


def _progress(*lines: bytes) -> bytes:
    return bytes((10,)).join(lines) + bytes((10,))


_CLEAN_PROGRESS = (
    _progress(
        b"============================= test session starts ==============================",
        b"platform win32 -- Python 3.12.10, pytest-8.3.5, pluggy-1.5.0",
        b"rootdir: example",
        b"collected 12 items",
        b"",
    )
    + b"." * 12
)
_DIRTY_PROGRESS = _CLEAN_PROGRESS[:-12] + b"..F.E......."


def _wrapper_step():
    import sys
    return gate_mod.Step(
        "python-suite",
        [sys.executable, "tools/run_phase19_pytest.py", "full"],
        1500.0,
    )


def test_a_breach_with_observed_test_failures_takes_the_distinct_failure_code(
        monkeypatch, capsys) -> None:
    """CARD 00 NEGATIVE. Pre-repair every breach shares exit 124, so a loaded host that
    was ALSO failing tests is indistinguishable from a loaded host failing nothing."""
    child = _BreachesWithCapturedOutput(_DIRTY_PROGRESS)
    _install(monkeypatch, child)

    rc = mod.main(["full"])

    assert rc == 123, (
        f"a ceiling breach WITH observed test failures must take the distinct exit 123; got {rc}"
    )
    assert "failure" in capsys.readouterr().err.lower()


def test_a_breach_with_zero_observed_failures_keeps_the_ceiling_code_and_says_why(
        monkeypatch, capsys) -> None:
    """CARD 00. The clean breach keeps 124 AND states that nothing had failed."""
    child = _BreachesWithCapturedOutput(_CLEAN_PROGRESS)
    _install(monkeypatch, child)

    rc = mod.main(["full"])

    assert rc == 124
    err = capsys.readouterr().err.lower()
    assert "ceiling" in err
    assert "no test failure" in err, (
        "the clean-breach report must say that zero test failures were observed")


def test_a_clean_ceiling_breach_is_not_graded_as_a_product_failure(monkeypatch) -> None:
    """CARD 00 NEGATIVE, at the gate. Pre-repair run_step() grades ANY nonzero wrapper
    exit as FAIL, so host load reports as a product failure."""
    monkeypatch.setattr(
        gate_mod.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=124, stdout="ceiling", stderr=""))

    result = gate_mod.run_step(_wrapper_step())

    assert result.state == gate_mod.NOT_VERIFIED, (
        f"a budget breach with zero test failures graded as {result.state}, which is a "
        "product verdict")


def test_a_ceiling_breach_with_failures_is_still_graded_FAIL(monkeypatch) -> None:
    """CARD 00 control, the other direction: failures observed means FAIL stands."""
    monkeypatch.setattr(
        gate_mod.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=123, stdout="tail", stderr=""))

    result = gate_mod.run_step(_wrapper_step())

    assert result.state == gate_mod.FAIL
    assert "observed" in result.detail.lower(), (
        "the FAIL detail must say failures were OBSERVED before the ceiling fired")


def test_the_clean_breach_mapping_does_not_leak_to_other_steps(monkeypatch) -> None:
    """CARD 00 guard: exit 124 arriving from any OTHER step is still just a failure."""
    step = gate_mod.Step("some-other-step", ["whatever"], 300.0)
    monkeypatch.setattr(
        gate_mod.subprocess, "run",
        lambda *a, **k: SimpleNamespace(returncode=124, stdout="tail", stderr=""))

    result = gate_mod.run_step(step)

    assert result.state == gate_mod.FAIL
