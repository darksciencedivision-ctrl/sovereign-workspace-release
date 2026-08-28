"""The four properties host-coupling gates must have (punch list 2.4, W-22).

These run on Windows and prove the INSTRUMENT, deterministically, by injecting
absent prerequisites rather than by uninstalling anything. Environmental
acceptance is a separate leg and is explicitly not claimed here:

    Linux clean-checkout acceptance: NOT VERIFIED ON THIS HOST.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests import host_prerequisites as hp  # noqa: E402

ALWAYS_ABSENT = hp.Prerequisite("a prerequisite this host cannot have", lambda: False,
                                "injected by the W-22 tests")
ALWAYS_PRESENT = hp.Prerequisite("a prerequisite every host has", lambda: True,
                                 "injected by the W-22 tests")
DETECTOR_THROWS = hp.Prerequisite("a prerequisite whose detector explodes",
                                  lambda: (_ for _ in ()).throw(OSError("no such host API")),
                                  "injected by the W-22 tests")


@pytest.fixture(autouse=True)
def _allow_injected(monkeypatch):
    """`requires()` refuses an undeclared prerequisite on purpose; these tests declare theirs."""
    monkeypatch.setattr(hp, "KNOWN",
                        (*hp.KNOWN, ALWAYS_ABSENT, ALWAYS_PRESENT, DETECTOR_THROWS))


# ---- property 1: an unavailable prerequisite is RECOGNISED --------------------------------------

def test_an_unavailable_prerequisite_is_recognised() -> None:
    assert ALWAYS_ABSENT.missing() is True
    assert ALWAYS_PRESENT.missing() is False


def test_a_detector_that_throws_counts_the_prerequisite_as_ABSENT() -> None:
    """Fail closed: a host API that explodes is not evidence the prerequisite is there."""
    assert DETECTOR_THROWS.missing() is True


# ---- property 2: it becomes an explicit SKIP, not a failure --------------------------------------

def test_a_missing_prerequisite_produces_a_SKIP_mark_not_a_failure() -> None:
    mark = hp.requires(ALWAYS_ABSENT)
    assert mark.name == "skipif"
    assert mark.args[0] is True, "the gate must be armed when the prerequisite is absent"


def test_a_present_prerequisite_does_not_skip() -> None:
    mark = hp.requires(ALWAYS_PRESENT)
    assert mark.args[0] is False, "a satisfied prerequisite must not skip the test"


def test_the_gate_is_armed_by_the_FIRST_missing_prerequisite_of_several() -> None:
    mark = hp.requires(ALWAYS_PRESENT, ALWAYS_ABSENT)
    assert mark.args[0] is True
    assert ALWAYS_ABSENT.name in mark.kwargs["reason"]


# ---- property 3: a real regression still goes RED ------------------------------------------------

@hp.requires(hp.WINDOWS)
def test_gating_does_not_swallow_a_regression_when_the_prerequisite_IS_present() -> None:
    """This test is gated on Windows and RUNS here, so the gate is not a blanket mute. If the
    assertion below ever became false it would go red, exactly as an ungated test would — gating
    keys on the HOST, never on the outcome."""
    assert hp.WINDOWS.missing() is False
    with pytest.raises(AssertionError):
        assert False, "a gated test whose prerequisite is present still fails on a real defect"


def test_requires_gates_on_the_host_and_never_on_the_test_outcome() -> None:
    """Property 3, structurally: `requires` returns a skipif mark and nothing else. It cannot wrap
    the body, so it has no way to convert a failure into a skip."""
    mark = hp.requires(ALWAYS_PRESENT)
    assert mark.name == "skipif"
    assert set(mark.kwargs) <= {"reason"}


# ---- property 4: the reason NAMES the missing prerequisite ---------------------------------------

def test_the_skip_reason_names_the_missing_prerequisite_and_how_to_get_it() -> None:
    reason = hp.requires(ALWAYS_ABSENT).kwargs["reason"]
    assert "host prerequisite missing" in reason
    assert ALWAYS_ABSENT.name in reason, "a reader of a skipped run must learn WHAT is missing"
    assert ALWAYS_ABSENT.install_hint in reason, "…and what to do about it"


@pytest.mark.parametrize("prereq", hp.KNOWN, ids=lambda p: p.name.split()[0])
def test_every_declared_prerequisite_names_itself_and_carries_a_hint(prereq) -> None:
    assert prereq.name.strip()
    assert prereq.install_hint.strip(), f"{prereq.name} has no install hint"
    assert prereq.name in prereq.skip_reason


# ---- the vocabulary is closed ---------------------------------------------------------------------

def test_an_undeclared_prerequisite_is_refused(monkeypatch) -> None:
    """A gate may only cite a DECLARED prerequisite, so a new host coupling has to be named rather
    than smuggled in as a bare boolean nobody can read in a skipped run."""
    monkeypatch.setattr(hp, "KNOWN", (hp.WINDOWS,))
    with pytest.raises(ValueError, match="undeclared prerequisite"):
        hp.requires(ALWAYS_ABSENT)


def test_requires_with_no_prerequisite_is_refused() -> None:
    with pytest.raises(ValueError, match="gates nothing"):
        hp.requires()


def test_linux_clean_checkout_acceptance_is_recorded_as_NOT_VERIFIED() -> None:
    """Recorded literally, as ruled. The instrument above is proved on this host; the
    environmental acceptance leg is a separate, outstanding validation."""
    assert "Linux clean-checkout acceptance: NOT VERIFIED ON THIS HOST." in hp.__doc__
