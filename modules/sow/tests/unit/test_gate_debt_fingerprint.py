"""A registered debt cannot absorb a different failure (W-24 hardening).

Registration is not permission to downgrade arbitrary failure. The gate runner
maps a FAILING step to KNOWN_OPEN_DEBT only when that failure matches the
registered fingerprint exactly — same exit code, same output signatures. A step
that fails differently is a NEW defect wearing an old badge, and must be FAIL.

Without this the calibrated runner becomes a sophisticated machine for laundering
red into green: register one failure, inherit cover for every future one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _gate():
    spec = importlib.util.spec_from_file_location(
        "phase19_gate", REPO / "tools" / "run_phase19_gate.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules[cls.__module__]
    sys.modules["phase19_gate"] = module
    spec.loader.exec_module(module)
    return module


GATE = _gate()
DEBT = GATE.DECLARED_DEBTS["mutation:_op18d_close_mutations"]

#: The registered condition, as `_op18d_close_mutations.py` actually reports it.
REGISTERED_OUTPUT = (
    "R3  the incarnation is asked of memory, not of the log   GREEN (guard does not hold) restored\n"
    "28/29 RED, all restores byte-identical\n"
)


def test_the_exact_registered_condition_is_a_known_open_debt() -> None:
    matched, why = DEBT.matches(1, REGISTERED_OUTPUT)
    assert matched, why
    assert DEBT.register_row == "U446"


@pytest.mark.parametrize("label,exit_code,output", [
    ("a SECOND row also failing", 1, REGISTERED_OUTPUT.replace("28/29", "27/29")),
    ("a restore that diverged", 1,
     REGISTERED_OUTPUT.replace("all restores byte-identical", "1 restore MISMATCH")),
    ("a DIFFERENT row going green", 1, REGISTERED_OUTPUT.replace("R3", "R9")),
    ("a different exit code", 3, REGISTERED_OUTPUT),
    ("no recognisable output at all", 1, "boom\n"),
])
def test_a_failure_that_is_not_the_registered_one_is_refused(
        label: str, exit_code: int, output: str) -> None:
    """Each of these would have been silently accepted as U446 before the fingerprint existed."""
    matched, why = DEBT.matches(exit_code, output)
    assert not matched, f"{label} was accepted as the registered debt"
    assert why, "a refusal must say what did not match"


def test_every_registered_debt_carries_a_row_a_reason_and_signatures() -> None:
    """A debt with no fingerprint is the loose form this hardening removed."""
    assert GATE.DECLARED_DEBTS, "no debts declared — this test would be vacuous"
    for name, debt in GATE.DECLARED_DEBTS.items():
        assert debt.register_row.startswith("U"), f"{name} cites no register row"
        assert debt.why.strip(), f"{name} has no reason"
        assert debt.signatures, f"{name} has no output signature to match on"
        assert isinstance(debt.exit_code, int), f"{name} pins no exit code"


def test_unresolved_receipts_are_registered_by_NAME_not_by_unit() -> None:
    """The other laundering path: a newly failing 18E receipt must not inherit KNOWN_OPEN_DEBT
    merely by belonging to 18E."""
    registered = GATE.REGISTERED_UNRESOLVED_RECEIPTS
    assert registered, "no receipts registered — the policy would be vacuous"
    assert all(name.endswith(".json") for name in registered), (
        "registration must be by exact receipt FILENAME, never by unit prefix")
    assert "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json" in registered
    # a plausible new sibling of the same unit is NOT covered
    assert "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_tomorrow.json" not in registered
    assert all(len(sha) == 64 for sha in registered.values()), (
        "every registered receipt must pin a SHA-256; a filename is identity, not a fingerprint")


# ---- the four receipt calibrations -----------------------------------------------------------
# Filename alone stopped a NEW FILE inheriting debt status. It did not stop a registered receipt
# keeping its name, having its CONTENTS replaced, and still being recognised as the old debt.

KNOWN = "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json"
RECEIPTS_DIR = REPO / "docs" / "evidence" / "receipts"


def _stage(tmp_path: Path, *, name: str, mutate: bool = False) -> Path:
    data = (RECEIPTS_DIR / KNOWN).read_bytes()
    if mutate:
        # one byte, and deliberately one that changes nothing a reader would notice
        data = data.replace(b"false", b"falsE", 1)
    (tmp_path / name).write_bytes(data)
    return tmp_path


def test_calibration_1_the_exact_known_receipt_is_a_known_open_debt(tmp_path: Path) -> None:
    staged = _stage(tmp_path, name=KNOWN)
    matched, why = GATE.registered_debt_state(staged, KNOWN)
    assert matched, why


def test_calibration_2_same_filename_one_byte_mutation_is_refused(tmp_path: Path) -> None:
    """The gap this correction closes. Same name, different condition — not the known debt."""
    staged = _stage(tmp_path, name=KNOWN, mutate=True)
    matched, why = GATE.registered_debt_state(staged, KNOWN)
    assert not matched, "a mutated receipt kept its registered debt status"
    assert "content changed" in why
    assert "re-adjudicate" in why, "the refusal must say what to do about it"


def test_calibration_3_same_bytes_different_filename_is_refused(tmp_path: Path) -> None:
    """A renamed copy of a known debt is not that debt."""
    renamed = "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_copy.json"
    staged = _stage(tmp_path, name=renamed)
    matched, why = GATE.registered_debt_state(staged, renamed)
    assert not matched, "a renamed copy inherited the registered debt"
    assert "not a registered receipt filename" in why


def test_calibration_4_a_new_failing_receipt_in_the_same_unit_is_refused(tmp_path: Path) -> None:
    """Belonging to 18E is not membership of the 18E debt."""
    sibling = "PHASE18E_LIVE_ACCEPTANCE_SELFCHECK_20260901T0000Z.json"
    staged = _stage(tmp_path, name=sibling, mutate=True)
    matched, why = GATE.registered_debt_state(staged, sibling)
    assert not matched, "a new sibling inherited the unit's registered debt"
    assert "not a registered receipt filename" in why


def test_a_repaired_receipt_stops_being_callable_old_debt(tmp_path: Path) -> None:
    """The property that makes this worth the annoyance: repair changes the hash, so the runner
    refuses to keep calling it debt and forces re-adjudication."""
    staged = _stage(tmp_path, name=KNOWN, mutate=True)   # stands in for "someone fixed it"
    matched, _why = GATE.registered_debt_state(staged, KNOWN)
    assert not matched


def test_the_five_states_are_distinct_and_none_is_an_alias_for_pass() -> None:
    states = {GATE.PASS, GATE.FAIL, GATE.SKIP, GATE.NOT_VERIFIED, GATE.KNOWN_OPEN_DEBT}
    assert len(states) == 5, "the five states must not collapse into fewer"
    assert GATE.KNOWN_OPEN_DEBT != GATE.PASS
    assert GATE.NOT_VERIFIED != GATE.PASS
