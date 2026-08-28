"""Phase 15D `.selection`: the conductor SELECTION record is deterministic, schema-pinned, and
never conflated with the EXECUTING checkpoint (directive §11 15D: "`current_conductor` =
{model: fable-5, reason: operator_selected, since: 2026-07-19} — selection preserved even when the
executing checkpoint differs, record BOTH").

Load-bearing properties proven here:
  1. The pinned operator selection IS fable-5 / operator_selected / 2026-07-19 and validates against
     the FROZEN checkpoint@1.0 `current_conductor` definition (schema is the source of truth).
  2. Selection is an INTERFACE label (invariant 3): binding it to a live backend never rewrites it,
     and an executing checkpoint that differs from the selection LABEL is surfaced as a
     label/checkpoint pair (not adjudicated as a divergent model), not masked.
  3. Fail closed: blank model, unknown reason, non-ISO `since`, unknown record keys all RAISE —
     never coerced into a permissive default.
  4. An unverified/unavailable model becomes a RECORDED fallback (never silent), and a checkpoint id
     is never fabricated (`executing_verified` is True only when a live reply reported one).
  5. Succession changes only the selection (reason=succession); restoring returns the pinned
     operator selection with a NEW `since` — the clock is injected, never read here.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    ConductorSelectionError,
    ExecutingEvidence,
    bind_conductor_selection,
    restore_operator_selection,
    selection_from_record,
    succession_selection,
)

ROOT = Path(__file__).resolve().parents[2]
_CHECKPOINT_SCHEMA = json.loads(
    (ROOT / "schemas" / "checkpoint.schema.json").read_text(encoding="utf-8"))
_CURRENT_CONDUCTOR_DEF = {
    **_CHECKPOINT_SCHEMA["definitions"]["current_conductor"],
    "definitions": _CHECKPOINT_SCHEMA["definitions"],
}

_NOW = "2026-07-19T12:00:00+00:00"


# ---- (1) the pinned operator selection -------------------------------------------------------

def test_pinned_selection_is_fable5_operator_selected_since_20260719() -> None:
    sel = OPERATOR_SELECTED_CONDUCTOR
    assert sel.model == "fable-5"
    assert sel.reason == "operator_selected"
    assert sel.since.startswith("2026-07-19")
    # the provider the selection currently runs on — recorded, not the selection itself
    assert sel.adapter == "claude_code"


def test_selection_adapter_is_pinned_to_the_adapter_constant() -> None:
    """The selection module imports NO adapter (vendor neutrality, invariants 3/4/20), so the
    recorded provider string is pinned structurally here instead — it cannot drift silently."""
    from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER

    assert OPERATOR_SELECTED_CONDUCTOR.adapter == CLAUDE_CODE_ADAPTER


def _adapter_imports(source: str) -> list[str]:
    """W-79: the structural no-adapter pin, computed on the AST instead of the source TEXT. The
    old grep passed any binding that dodged the two literal substrings - a dynamic
    `importlib.import_module("adapters.frontier.codex")` or `__import__("adapters")` imported
    exactly the module invariant 20 forbids while the pin read clean."""
    import ast

    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names
                          if a.name == "adapters" or a.name.startswith("adapters.")]
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "adapters" or node.module.startswith("adapters.")):
                offenders.append(node.module)
        elif isinstance(node, ast.Call):
            fn = node.func
            dynamic = (isinstance(fn, ast.Name) and fn.id == "__import__") or (
                isinstance(fn, ast.Attribute) and fn.attr == "import_module")
            if dynamic:
                offenders += [a.value for a in node.args
                              if isinstance(a, ast.Constant) and isinstance(a.value, str)
                              and (a.value == "adapters" or a.value.startswith("adapters."))]
    return offenders


def test_selection_module_imports_no_adapter() -> None:
    """A control-plane module must not pull a cloud adapter into every consumer's import graph
    (invariant 20 air-gap honesty / invariant 4 interchangeability). AST-checked since W-79 -
    aliased and dynamic bindings fail this pin now, not just the two literal substrings."""
    source = (ROOT / "control_plane" / "conductor" / "selection.py").read_text(encoding="utf-8")
    assert _adapter_imports(source) == []


def test_the_no_adapter_pin_catches_dynamic_and_aliased_bindings():
    """W-79 calibration of the instrument itself: every form that used to slip the text pin is
    flagged, and honest non-adapter imports stay clean."""
    flagged = _adapter_imports(
        "import importlib\n"
        "importlib.import_module('adapters.frontier.codex')\n"
        "__import__('adapters')\n"
        "import adapters.frontier.claude_code as cc\n"
        "from adapters.frontier import grok_build as gg\n"
    )
    assert sorted(flagged) == [
        "adapters", "adapters.frontier",
        "adapters.frontier.claude_code", "adapters.frontier.codex"], flagged

    assert _adapter_imports("from control_plane.policy import Identity\n") == []


def test_selection_record_validates_against_frozen_checkpoint_schema() -> None:
    record = OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()
    jsonschema.validate(record, _CURRENT_CONDUCTOR_DEF)  # frozen schema is the source of truth
    assert set(record) <= {"model", "adapter", "reason", "since", "directive_version",
                           "subscription_ref"}


# ---- (2) selection vs executing checkpoint — record BOTH -------------------------------------

def test_binding_records_selection_and_executing_separately() -> None:
    binding = bind_conductor_selection(
        executing_evidence=ExecutingEvidence("claude-fable-5-20260101"))
    record = binding.as_record()
    assert record["selection"]["model"] == "fable-5"          # selection untouched
    assert record["executing"]["model"] == "claude-fable-5-20260101"
    assert record["executing"]["verified"] is True


def test_the_same_checkpoint_as_a_bare_claim_records_nothing_as_executing() -> None:
    """U45 (`phase-15d.gate`). This test previously passed `reported_model=` and asserted a VERIFIED
    checkpoint — it encoded the defect. A bare string is a claim anyone can make; only evidence
    (exact CLI class + spend + freshness, applied by a caller that can see the backend) verifies."""
    record = bind_conductor_selection(reported_model="claude-fable-5-20260101").as_record()
    assert record["executing"]["verified"] is False
    assert record["executing"]["model"] is None
    assert record["executing"]["reported_unverified"] == "claude-fable-5-20260101"


def test_executing_checkpoint_differing_from_label_is_surfaced_not_masked() -> None:
    """The CLI may report a different checkpoint than the selection label. Invariant 3: the
    selection is preserved; the pair is SURFACED (never silently rewritten either way)."""
    binding = bind_conductor_selection(executing_evidence=ExecutingEvidence("claude-opus-4-8"))
    assert binding.selection.model == "fable-5"
    assert binding.executing_model == "claude-opus-4-8"
    assert binding.as_record()["label_mismatch"] is True


def test_matching_executing_checkpoint_is_not_flagged_mismatched() -> None:
    assert bind_conductor_selection(
        executing_evidence=ExecutingEvidence("fable-5")).as_record()["label_mismatch"] is False


def test_binding_never_mutates_the_pinned_selection() -> None:
    before = OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()
    bind_conductor_selection(requested_model="opus-4.8",
                             executing_evidence=ExecutingEvidence("claude-opus-4-8"))
    assert OPERATOR_SELECTED_CONDUCTOR.as_current_conductor() == before


# ---- (3) fail-closed construction ------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"model": "", "reason": "operator_selected", "since": _NOW},          # blank model
    {"model": "   ", "reason": "operator_selected", "since": _NOW},       # whitespace model
    {"model": "fable-5", "reason": "vendor_default", "since": _NOW},      # not in schema enum
    {"model": "fable-5", "reason": "operator_selected", "since": "yesterday"},   # non-ISO
    {"model": "fable-5", "reason": "operator_selected", "since": ""},     # empty ts
])
def test_invalid_selection_raises_never_coerced(kwargs: dict) -> None:
    with pytest.raises(ConductorSelectionError):
        ConductorSelection(**kwargs)


def test_reason_enum_is_read_from_the_frozen_schema_not_hardcoded_locally() -> None:
    """A drifting local copy of the enum would let an unauthorized reason through, so the module
    must derive it from checkpoint@1.0."""
    from control_plane.conductor.selection import CONDUCTOR_SELECTION_REASONS

    assert set(CONDUCTOR_SELECTION_REASONS) == set(
        _CHECKPOINT_SCHEMA["definitions"]["current_conductor"]["properties"]["reason"]["enum"])


def test_selection_from_record_rejects_unknown_keys_and_missing_fields() -> None:
    good = OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()
    assert selection_from_record(good) == OPERATOR_SELECTED_CONDUCTOR
    with pytest.raises(ConductorSelectionError):
        selection_from_record({**good, "authority": "self"})    # no smuggled fields
    with pytest.raises(ConductorSelectionError):
        selection_from_record({"model": "fable-5"})             # missing reason/since
    with pytest.raises(ConductorSelectionError):
        selection_from_record("fable-5")                        # not a mapping


# ---- (4) recorded fallback, never a fabricated checkpoint id ---------------------------------

def test_unavailable_model_becomes_a_recorded_fallback_never_silent() -> None:
    binding = bind_conductor_selection(model_available=False)
    rec = binding.as_record()
    assert binding.is_fallback is True
    assert rec["executing"]["resolved_slug"] is None    # backend default — no invented slug
    assert rec["executing"]["verified"] is False
    assert "fallback" in rec["executing"]["note"].lower()
    assert rec["selection"]["model"] == "fable-5"       # selection still recorded


def test_no_live_reply_means_nothing_executed_not_an_echoed_slug() -> None:
    """Nothing ran, so `executing.model` is None. Echoing the requested slug back would let a
    refused or mock run read as though that model had answered."""
    binding = bind_conductor_selection()  # nothing reported => cannot claim a checkpoint
    assert binding.executing_verified is False
    assert binding.executing_model is None
    assert binding.resolved_slug == "fable-5"           # what WOULD be requested, verbatim
    assert binding.as_record()["label_mismatch"] is False


def test_verified_note_does_not_also_claim_unverified() -> None:
    note = bind_conductor_selection(
        executing_evidence=ExecutingEvidence("claude-fable-5-20260101")).note
    assert "unverified" not in note and "reported by the live backend" in note


def test_model_label_is_stripped_so_slug_and_record_cannot_differ() -> None:
    sel = ConductorSelection(model="  fable-5 ", reason="operator_selected", since=_NOW)
    assert sel.model == "fable-5"
    assert bind_conductor_selection(sel).resolved_slug == "fable-5"


def test_resolver_is_replaceable_for_a_non_anthropic_backend() -> None:
    """Vendor neutrality (invariant 4): a successor on another backend binds through the same path
    with its own resolver — no Anthropic semantics are hardwired into the selection layer."""
    calls: list[str | None] = []

    def codex_resolver(requested: str | None) -> tuple[str | None, str]:
        calls.append(requested)
        return ("gpt-5.5-codex", "codex resolver")

    binding = bind_conductor_selection(requested_model="5.5", resolver=codex_resolver)
    assert calls == ["5.5"] and binding.resolved_slug == "gpt-5.5-codex"


@pytest.mark.parametrize("reported", [None, "", "   ", 5, {"model": "x"}])
def test_blank_or_malformed_reported_model_is_not_even_recorded_as_a_claim(reported: object) -> None:
    """Since `phase-15d.gate` NO `reported_model` verifies, so asserting `executing_verified is
    False` here would pass vacuously for every input — the validator caught that this test had
    become tautological. What still discriminates is the CLAIM channel: a blank or malformed value
    is not a checkpoint claim at all and must not be echoed into `reported_unverified`, where an
    operator would read it as something the backend said."""
    binding = bind_conductor_selection(reported_model=reported)  # type: ignore[arg-type]
    assert binding.executing_verified is False
    assert binding.reported_unverified is None
    assert binding.as_record()["executing"]["reported_unverified"] is None
    # a WELL-FORMED claim, by contrast, is recorded — so the assertion above is discriminating
    assert bind_conductor_selection(reported_model="claude-x-1").reported_unverified == "claude-x-1"


def test_selection_model_is_the_default_request() -> None:
    """15D: model_ref = fable-5 if available else recorded fallback — the conductor requests its
    own selection by default rather than silently taking the CLI default."""
    assert bind_conductor_selection().requested_model == "fable-5"
    assert bind_conductor_selection(requested_model="opus-4.8").requested_model == "opus-4.8"


# ---- (5) succession + restore ----------------------------------------------------------------

def test_succession_selection_records_reason_succession_with_injected_clock() -> None:
    succ = succession_selection("opus-4.8", adapter="claude_code", since=_NOW)
    assert (succ.model, succ.reason, succ.since) == ("opus-4.8", "succession", _NOW)
    jsonschema.validate(succ.as_current_conductor(), _CURRENT_CONDUCTOR_DEF)


def test_restore_returns_the_pinned_operator_selection_with_a_new_since() -> None:
    succ = succession_selection("opus-4.8", adapter="claude_code", since=_NOW)
    restored = restore_operator_selection(succ, since="2026-07-19T13:00:00+00:00")
    assert restored.model == OPERATOR_SELECTED_CONDUCTOR.model
    assert restored.reason == "operator_selected"
    assert restored.since == "2026-07-19T13:00:00+00:00"   # restore moment, not the original pin
    assert restored.since != OPERATOR_SELECTED_CONDUCTOR.since


def test_restore_accepts_a_checkpoint_record_and_fails_closed_on_a_bad_clock() -> None:
    record = succession_selection("opus-4.8", since=_NOW).as_current_conductor()
    assert restore_operator_selection(record, since=_NOW).reason == "operator_selected"
    with pytest.raises(ConductorSelectionError):
        restore_operator_selection(record, since="whenever")
    with pytest.raises(ConductorSelectionError):
        restore_operator_selection(record, since="2026-07-19")   # date, not date-time


def test_restore_refuses_a_state_that_was_never_succeeded() -> None:
    """Restoring a non-succession state would write an unfounded operator_selected record."""
    with pytest.raises(ConductorSelectionError):
        restore_operator_selection(OPERATOR_SELECTED_CONDUCTOR, since=_NOW)


def test_directive_version_is_carried_or_absent_never_inferred() -> None:
    """Provenance (invariant 11): a record that did not state a directive version must not come
    back carrying one."""
    parsed = selection_from_record(
        {"model": "fable-5", "reason": "operator_selected", "since": _NOW})
    assert parsed.directive_version is None
