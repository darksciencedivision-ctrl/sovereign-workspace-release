"""Phase 15D `.debate` — pure logic of the live-capable bounded debate.

Directive §11 15D: ONE bounded live debate, budgets enforced as HARD caps. These tests cover
the parts that hold no socket and spawn nothing: scoped prompt assembly (invariant 8), the
FAIL-CLOSED statement parse (a model that returns junk must never yield a fabricated citation),
per-debater leg classification, and the report's refusal to package an unbacked `live` claim.

The leg vocabulary is IMPORTED from `live_flow`, not redefined — the .flow constraint was to
reuse that honesty machinery rather than invent a second vocabulary.
"""
from __future__ import annotations

import copy
import json
from unittest.mock import patch

import pytest

from adapters.base.backend import MockBackend
from control_plane.orchestration import live_debate
from adapters.frontier.claude_code import ClaudeCliBackend, MockClaudeCliBackend
from control_plane.orchestration.live_debate import (
    DEBATE_REPORT_KEYS,
    REFUSAL_PREFIX,
    SCOPED_TRANSCRIPT_ROUNDS,
    BackendDebater,
    DebateReportError,
    build_debate_prompt,
    build_debate_report,
    debater_leg,
    parse_statement,
    verification_for,
)
from control_plane.orchestration.live_flow import ATTEMPTED_LEG, OPERATOR_DISPOSITION_PENDING

TOPIC = "Does artifact m-1 satisfy the acceptance criteria?"
ALLOWED = ("m-1", "m-2", "sha256:abc")


# --- scoped prompt (invariant 8: scoped context, never blanket transcript forwarding) ------

def _transcript(rounds: int) -> list[dict]:
    return [{"round": r,
             "positions": [{"node": f"n{i}", "position": f"round {r} position of n{i}",
                            "evidence_refs": ["m-1"], "round": r, "supported": True}
                           for i in (1, 2)]}
            for r in range(1, rounds + 1)]


def test_prompt_forwards_only_the_scoped_tail_of_the_transcript() -> None:
    """A debate over many rounds must not blanket-forward the whole transcript (invariant 8)."""
    prompt = build_debate_prompt(topic=TOPIC, round_no=4, transcript=_transcript(3),
                                 allowed_evidence=ALLOWED)
    assert SCOPED_TRANSCRIPT_ROUNDS == 1
    assert "round 3 position of n1" in prompt      # the scoped tail IS forwarded
    assert "round 1 position of n1" not in prompt  # earlier rounds are NOT
    assert "round 2 position of n1" not in prompt


def test_prompt_excerpts_long_positions_rather_than_forwarding_them_whole() -> None:
    long_transcript = [{"round": 1, "positions": [
        {"node": "n1", "position": "X" * 5_000, "evidence_refs": [], "round": 1, "supported": False}]}]
    prompt = build_debate_prompt(topic=TOPIC, round_no=2, transcript=long_transcript,
                                 allowed_evidence=ALLOWED, excerpt_chars=100)
    assert "X" * 100 in prompt
    assert "X" * 200 not in prompt          # bounded — smoke-scale tokens, real money now
    assert len(prompt) < 2_000


def test_prompt_names_only_the_evidence_the_debater_is_scoped_to_cite() -> None:
    prompt = build_debate_prompt(topic=TOPIC, round_no=1, transcript=[], allowed_evidence=("m-1",))
    assert "m-1" in prompt and "m-2" not in prompt


# --- fail-closed statement parse ----------------------------------------------------------

def test_wellformed_statement_parses() -> None:
    st = parse_statement('{"position": "it does not", "evidence_refs": ["m-2"]}',
                         allowed_evidence=ALLOWED)
    assert st.refused is False
    assert st.position == "it does not"
    assert st.evidence_refs == ("m-2",)


def test_statement_parses_from_a_fenced_or_prose_wrapped_reply() -> None:
    raw = 'Sure!\n```json\n{"position": "yes", "evidence_refs": ["m-1"]}\n```\nHope that helps.'
    st = parse_statement(raw, allowed_evidence=ALLOWED)
    assert st.refused is False and st.position == "yes" and st.evidence_refs == ("m-1",)


@pytest.mark.parametrize("raw", [
    "", "   ", "not json at all", "{", "[]", '{"evidence_refs": ["m-1"]}',
    '{"position": ""}', '{"position": "   "}', '{"position": 7}', '{"position": null}',
    "null", '"a bare string"', None, 42,
])
def test_unparseable_reply_refuses_and_NEVER_fabricates_a_citation(raw) -> None:
    """The load-bearing rule: junk in must not become a supported assertion.

    A refusal carries NO evidence_refs, so the EvidenceManager classifies it UNSUPPORTED — a
    model vote is not evidence (Plan §19.3 prohibited drift).
    """
    st = parse_statement(raw, allowed_evidence=ALLOWED)
    assert st.refused is True
    assert st.evidence_refs == ()
    assert st.position.startswith(REFUSAL_PREFIX)
    assert st.notes


def test_refusal_position_can_never_be_mistaken_for_an_argument() -> None:
    """Pinned against the LITERAL marker, not against `REFUSAL_PREFIX` itself: asserting
    `startswith(REFUSAL_PREFIX)` holds for any value of the constant (including ""), so it
    cannot detect the marker being emptied. This pins the actual text.
    """
    st = parse_statement("garbage", allowed_evidence=ALLOWED)
    assert REFUSAL_PREFIX == "[no position: "
    assert st.position.startswith("[no position: ") and st.position.endswith("]")
    assert "garbage" not in st.position
    assert len(st.position) > len("[no position: ")


def test_citations_outside_the_scoped_set_are_DROPPED_and_NOTED_not_silently_kept() -> None:
    """Invariant 8: a ref the debater was never scoped to is not admissible from this path.

    Dropping it silently would leave an operator reading a debate record that cites evidence the
    node had no scoped access to, with nothing saying so.
    """
    st = parse_statement('{"position": "p", "evidence_refs": ["m-1", "m-999"]}',
                         allowed_evidence=ALLOWED)
    assert st.refused is False
    assert st.evidence_refs == ("m-1",)
    assert any("m-999" in n for n in st.notes)


def test_a_statement_whose_every_citation_is_out_of_scope_keeps_the_position_but_loses_support() -> None:
    st = parse_statement('{"position": "p", "evidence_refs": ["m-999"]}', allowed_evidence=ALLOWED)
    assert st.refused is False and st.position == "p"
    assert st.evidence_refs == ()          # -> UNSUPPORTED downstream, never quietly supported
    assert st.notes


@pytest.mark.parametrize("refs", ['"m-1"', "7", "null", '{"a": 1}', '[7, "m-1"]', '[""]', "[null]"])
def test_malformed_evidence_refs_degrade_to_unsupported_never_to_an_invented_ref(refs) -> None:
    st = parse_statement('{"position": "p", "evidence_refs": %s}' % refs, allowed_evidence=ALLOWED)
    assert st.position == "p" and st.refused is False
    assert all(isinstance(r, str) and r.strip() for r in st.evidence_refs)
    assert set(st.evidence_refs) <= set(ALLOWED)


# --- BackendDebater ------------------------------------------------------------------------

class _ScriptedBackend:
    """A non-vendor backend returning canned replies (never live-eligible)."""

    def __init__(self, replies: list[str], name: str = "scripted") -> None:
        self.name = name
        self.calls = 0
        self._replies = replies

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        return self._replies[min(self.calls - 1, len(self._replies) - 1)]


def test_debater_calls_its_backend_once_per_round_and_returns_the_round_manager_shape() -> None:
    b = _ScriptedBackend(['{"position": "p1", "evidence_refs": ["m-1"]}'])
    d = BackendDebater("worker-A", b, allowed_evidence=ALLOWED)
    out = d.argue(TOPIC, 1, [])
    assert b.calls == 1
    assert out == {"position": "p1", "evidence_refs": ["m-1"]}


def test_debater_records_a_backend_EXCEPTION_as_a_refusal_and_keeps_the_debate_bounded() -> None:
    class _Boom:
        name, calls = "boom", 0

        def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
            raise RuntimeError("backend exploded")

    d = BackendDebater("worker-A", _Boom(), allowed_evidence=ALLOWED)
    out = d.argue(TOPIC, 1, [])
    assert out["position"].startswith(REFUSAL_PREFIX)
    assert out["evidence_refs"] == []
    assert any("RuntimeError" in n["note"] for n in d.notes)


def test_debater_notes_are_observable_per_round_never_silent() -> None:
    b = _ScriptedBackend(['{"position": "p", "evidence_refs": ["m-999"]}'])
    d = BackendDebater("worker-A", b, allowed_evidence=ALLOWED)
    d.argue(TOPIC, 1, [])
    assert d.notes and d.notes[0]["node"] == "worker-A" and d.notes[0]["round"] == 1


# --- leg classification (reuses the .flow vocabulary) --------------------------------------

def test_uncalled_backend_is_skipped_not_mock() -> None:
    assert debater_leg(MockBackend()) == "skipped"
    assert debater_leg(MockClaudeCliBackend()) == "skipped"


def test_called_mock_backend_is_mock() -> None:
    b = MockClaudeCliBackend()
    b.generate("hi")
    assert debater_leg(b) == "mock"


def test_a_mock_CANNOT_spoof_a_live_leg_by_setting_reported_model() -> None:
    """Classification is on the backend TYPE, never on an attribute a mock may set freely.

    An earlier version of this docstring cited `live_flow._leg_for_backend` as "the same
    non-spoofable rule". That is false in both halves and is withdrawn: `live_flow` still uses
    subclass-permissive `isinstance`, so it is the SPOOFABLE one, and its output feeds the
    acceptance packet the gate engine can promote to ACCEPTED. Recorded as U45, owed to
    `phase-15d.gate` — not fixed here, and no longer cited as this module's precedent.
    """
    b = MockClaudeCliBackend()
    b.generate("hi")
    b.reported_model = "claude-opus-4-8-20260101"   # a lie
    assert debater_leg(b) == "mock"
    assert verification_for(b) is None


def test_a_checkpoint_reported_by_a_call_in_THIS_debate_is_live() -> None:
    """The classifier CONTRACT for `live`: exact CLI class + a checkpoint the CLI reported for a
    call made after the bind-time snapshot.

    This is a test of the classifier, NOT evidence that anything ran live: only the real
    `generate` sets `reported_model_at_call`, and reaching it requires actually spawning `claude`.
    No end-to-end test in this build produces a `live` leg — see
    `test_no_leg_in_this_MOCK_FIRST_suite_can_reach_live` in the integration suite.
    """
    b = ClaudeCliBackend()
    b.calls = 6
    b.reported_model = "claude-opus-4-8-20260101"
    b.reported_model_at_call = 6                    # reported by call #6
    assert debater_leg(b, calls_before=5) == "live"
    assert verification_for(b, calls_before=5) == {"model": "claude-opus-4-8-20260101",
                                                   "verified": True}


def test_a_checkpoint_that_predates_this_debate_is_NOT_live() -> None:
    """A reused backend carries an earlier debate's checkpoint; `reported_model` is never cleared."""
    b = ClaudeCliBackend()
    b.calls = 9                                     # spent here...
    b.reported_model = "claude-opus-4-8-20260101"
    b.reported_model_at_call = 4                    # ...but the checkpoint is from call #4
    assert verification_for(b, calls_before=5) is None
    assert debater_leg(b, calls_before=5) == ATTEMPTED_LEG


def test_a_checkpoint_with_no_freshness_stamp_is_NOT_live() -> None:
    """`reported_model` alone cannot date itself, so alone it cannot back a live claim."""
    b = ClaudeCliBackend()
    b.calls = 6
    b.reported_model = "claude-opus-4-8-20260101"   # set by hand, never by a real call
    assert b.reported_model_at_call is None
    assert verification_for(b, calls_before=5) is None
    assert debater_leg(b, calls_before=5) == ATTEMPTED_LEG


def test_without_a_bind_time_snapshot_live_is_unreachable() -> None:
    """Absence of evidence is not evidence: no snapshot ⇒ no provable freshness ⇒ no live claim."""
    b = ClaudeCliBackend()
    b.calls = 6
    b.reported_model = "claude-opus-4-8-20260101"
    b.reported_model_at_call = 6
    assert verification_for(b, calls_before=None) is None
    assert debater_leg(b, calls_before=None) == ATTEMPTED_LEG


def test_a_SUBCLASS_of_the_real_cli_can_never_be_live() -> None:
    """REGRESSION: `isinstance` let a subclass inherit CLI identity without running the CLI.

    A subclass may override `generate` to return canned text and stamp both freshness fields
    itself. Classification is on EXACT type, so inherited identity buys nothing.
    """
    class _FakeCli(ClaudeCliBackend):
        def generate(self, prompt, *, max_tokens=256):
            self.calls += 1
            self.reported_model = "claude-opus-4-8-20260101"
            self.reported_model_at_call = self.calls
            return "{}"

    b = _FakeCli()
    b.generate("hi")
    assert verification_for(b, calls_before=0) is None
    assert debater_leg(b, calls_before=0) == "mock"


def test_contradictory_evidence_a_checkpoint_with_no_counted_call_is_NOT_live() -> None:
    """A checkpoint dated to a call the counter says never happened is contradictory.

    `reported_model_at_call` claims call #6 reported it while `calls` says only 5 were ever made.
    Nothing ran, yet something reported — the fail-closed reading of a contradiction is the WEAKER
    claim, so this must not be `live`.
    """
    b = ClaudeCliBackend()
    b.calls = 5                                     # no call spent since the snapshot...
    b.reported_model = "claude-opus-4-8-20260101"
    b.reported_model_at_call = 6                    # ...but a checkpoint claims one was
    assert debater_leg(b, calls_before=5) == "skipped"


def test_contradictory_evidence_publishes_NO_checkpoint_either() -> None:
    """The demotion must reach `debater_models`, not just `legs`.

    `debater_leg` demoted the contradictory case to `skipped` while `verification_for` still
    returned `{"verified": True}` — so the artifact carried the weaker claim in `legs` and the
    stronger one in `debater_models`, which is the field that actually carries the live evidence.
    Fixing only the leg fixes the label and leaves the claim.
    """
    b = ClaudeCliBackend()
    b.calls = 5                                     # no call spent since the snapshot
    b.reported_model = "claude-opus-4-8-20260101"
    b.reported_model_at_call = 6
    assert debater_leg(b, calls_before=5) == "skipped"
    assert verification_for(b, calls_before=5) is None


def test_report_REFUSES_a_checkpoint_attached_to_a_NON_live_leg() -> None:
    """The reverse direction of the correspondence.

    `live ⇒ verified checkpoint` was checked; `checkpoint ⇒ live leg` was not, so a report could
    publish `{"verified": true}` for a debater it simultaneously said had not run live.
    """
    for leg in ("mock", "attempted", "skipped"):
        with pytest.raises(DebateReportError, match="fails closed"):
            build_debate_report(
                record=_RECORD, legs={"worker-A": leg},
                verification={"worker-A": {"model": "claude-opus-4-8", "verified": True}},
                ts="2026-07-19T00:00:00+00:00")


def test_report_resolves_verification_ONCE_so_a_stateful_mapping_cannot_diverge() -> None:
    """Guard and emit must read the same snapshot.

    Two independent `verification.get(node)` calls let a stateful mapping show the guard a valid
    checkpoint and the emit something else — the guard passing on evidence the artifact never
    carried. Contrived as a mapping, real as a class of bug (it is how the `get`/`__contains__`
    variant leaked).
    """
    class _Stateful(dict):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.reads = 0

        def get(self, key, default=None):
            self.reads += 1
            if self.reads == 1:                       # what the guard sees
                return {"model": "claude-opus-4-8", "verified": True}
            return None                               # what a second lookup would see

    verification = _Stateful()
    rep = build_debate_report(record=_RECORD, legs={"worker-A": "live"},
                              verification=verification, ts="2026-07-19T00:00:00+00:00")
    assert verification.reads == 1                    # exactly one lookup per node
    assert rep["debater_models"] == {"worker-A": {"model": "claude-opus-4-8", "verified": True}}


def test_a_non_integer_freshness_stamp_fails_closed() -> None:
    """A bool is an int in Python, so `True` (== 1) must be excluded by TYPE, not by magnitude.

    `calls_before=0` is the case that actually exercises the bool guard: at any higher snapshot
    `True == 1` is already rejected by `1 <= calls_before`, so the guard would look pinned while
    contributing nothing. An earlier version of this test used `calls_before=5` and its docstring
    claimed to cover `True > 0` — a case it never constructed. A reviewer's mutant removing the
    bool exclusion survived that version.
    """
    for bogus in (True, "1", 1.0, None):
        b = ClaudeCliBackend()
        b.calls = 1
        b.reported_model = "claude-opus-4-8-20260101"
        b.reported_model_at_call = bogus
        assert verification_for(b, calls_before=0) is None, bogus


def test_the_live_branch_takes_the_EARLIER_reading_of_a_moving_counter() -> None:
    """`debater_leg`'s `spent and` is load-bearing, not redundant.

    `debater_leg` and `verification_for` read the call counter SEPARATELY. A counter that advances
    between the two reads — a concurrent call landing mid-classification — makes them disagree, and
    the `and` takes the earlier, lower reading. Without it, this backend classifies `live` on the
    strength of a call that had not yet happened when the leg was judged. Fail closed.

    (I originally claimed removing `spent and` was an EQUIVALENT mutant. A reviewer refuted it with
    exactly this input; the claim is withdrawn and pinned here instead.)
    """
    class _RacingCounter(ClaudeCliBackend):
        pass                                          # subclass only to host the property

    reads = []

    def _calls(self):
        reads.append(1)
        return 5 + len(reads) - 1                     # 5 on the first read, 6 on the next

    with patch.object(ClaudeCliBackend, "calls", property(_calls, lambda self, v: None),
                      create=True):
        b = ClaudeCliBackend()
        b.reported_model = "claude-opus-4-8-20260101"
        b.reported_model_at_call = 6
        assert debater_leg(b, calls_before=5) == "skipped"     # earlier reading wins


@pytest.mark.parametrize("reported", [None, "", "   "])
def test_real_cli_backend_that_spent_a_call_without_a_checkpoint_is_ATTEMPTED_not_skipped(reported) -> None:
    """Under-reporting spend is the dishonest direction (§6) — `skipped` would claim nothing ran."""
    b = ClaudeCliBackend()
    b.calls = 1
    b.reported_model = reported
    assert debater_leg(b) == ATTEMPTED_LEG
    assert verification_for(b) is None


def test_real_cli_backend_never_called_is_skipped() -> None:
    b = ClaudeCliBackend()
    assert b.calls == 0 and debater_leg(b) == "skipped"


def test_a_backend_error_message_is_BOUNDED_before_it_reaches_the_record() -> None:
    """CLI stderr flows into a refusal `position`, which lands in the immutable debate record.

    Nothing bounds it at the source — `ClaudeCliBackend` happens to truncate its own messages, and
    relying on that is an inherited accident, not a guarantee.
    """
    class _Verbose:
        name = "verbose"
        calls = 0

        def generate(self, prompt, *, max_tokens=256):
            raise RuntimeError("x" * 10_000)

    d = BackendDebater("worker-A", _Verbose(), allowed_evidence=ALLOWED)
    out = d.argue(TOPIC, 1, [])
    assert len(out["position"]) < 1_000
    assert "[truncated]" in out["position"]           # cut, and visibly so
    assert out["evidence_refs"] == []                 # a refusal cites nothing


def test_an_oversized_POSITION_is_bounded_and_the_truncation_is_RECORDED() -> None:
    """The position is the largest model-controlled field and lands in the frozen record."""
    raw = json.dumps({"position": "y" * 10_000, "evidence_refs": []})
    st = parse_statement(raw, allowed_evidence=ALLOWED)
    assert not st.refused                             # a long position is still a position
    assert len(st.position) < 3_000
    assert "[truncated]" in st.position
    assert any("truncated" in n for n in st.notes)    # observable, never silent


def test_a_position_within_the_bound_is_carried_VERBATIM() -> None:
    """The bound must not rewrite ordinary positions — dissent is preserved verbatim (inv 15)."""
    raw = json.dumps({"position": "it satisfies the criteria", "evidence_refs": []})
    st = parse_statement(raw, allowed_evidence=ALLOWED)
    assert st.position == "it satisfies the criteria"
    assert not any("truncated" in n for n in st.notes)


def test_unreadable_call_counter_on_the_REAL_cli_fails_closed_to_attempted() -> None:
    """An unreadable counter is NOT zero — reporting it as `skipped` under-reports spend.

    Patched on the real class inside a context manager rather than subclassed: a subclass now
    classifies `mock`, so it could not reach the real-CLI branch this test exists to pin. The
    patch is scoped, so no other test in the session sees a mutated `ClaudeCliBackend`.
    """
    def _unreadable(self):
        raise RuntimeError("counter unreadable")

    # `create=True`: `calls` is an INSTANCE attribute, so there is no class attribute to replace.
    # A class-level data descriptor shadows the instance assignment `__init__` makes.
    with patch.object(ClaudeCliBackend, "calls",
                      property(_unreadable, lambda self, v: None), create=True):
        b = ClaudeCliBackend()
        assert live_debate._calls_or_none(b) is None      # unreadable, NOT zero
        assert debater_leg(b, calls_before=0) == ATTEMPTED_LEG

    assert ClaudeCliBackend().calls == 0                  # the real class is intact afterwards


def test_unreadable_call_counter_on_a_non_cli_backend_is_mock_not_skipped() -> None:
    class _Unreadable:
        name = "x"

        @property
        def calls(self):
            raise RuntimeError("counter unreadable")

    assert debater_leg(_Unreadable(), calls_before=3) == "mock"


# --- report honesty ------------------------------------------------------------------------

_RECORD = {"debate_id": "d-1", "schema": "debate@1.0",
           "request": {"caller_node": "worker-A", "topic": TOPIC, "max_rounds": 3,
                       "participants": [], "budget": {"tokens": 300}},
           "result": {"rounds_used": 2, "positions": [], "outcome": "CONVERGED", "dissent": None,
                      "evidence_map": {}, "cost_actual": {"tokens": 200}}}


def test_report_carries_the_debate_record_and_pins_operator_disposition_pending() -> None:
    rep = build_debate_report(record=_RECORD, legs={"worker-A": "mock", "worker-B": "mock"},
                              verification={}, ts="2026-07-19T00:00:00+00:00")
    assert rep["operator_disposition"] == OPERATOR_DISPOSITION_PENDING
    assert rep["outcome"] == "CONVERGED" and rep["rounds_used"] == 2
    assert rep["legs"] == {"worker-A": "mock", "worker-B": "mock"}
    assert rep["ts"] == "2026-07-19T00:00:00+00:00"


def test_report_REFUSES_a_live_leg_with_no_verified_checkpoint() -> None:
    with pytest.raises(DebateReportError, match="VERIFIED"):
        build_debate_report(record=_RECORD, legs={"worker-A": "live"}, verification={},
                            ts="2026-07-19T00:00:00+00:00")


@pytest.mark.parametrize("model", [123, 0, True, ["x"], {"m": "x"}, None, "", "   "])
def test_report_REFUSES_a_live_leg_whose_checkpoint_is_not_a_non_blank_STRING(model) -> None:
    """A checkpoint that is not text is not a checkpoint.

    The guard once used `str(record.get("model") or "").strip()`, and `str(123).strip()` is
    truthy — so a non-string checkpoint reached an operator-facing artifact as a verified model id.
    """
    with pytest.raises(DebateReportError, match="VERIFIED"):
        build_debate_report(record=_RECORD, legs={"worker-A": "live"},
                            verification={"worker-A": {"model": model, "verified": True}},
                            ts="2026-07-19T00:00:00+00:00")


def test_report_cannot_emit_a_live_leg_with_an_EMPTY_checkpoint_map() -> None:
    """The guard and the emit must resolve the same value from the same lookup.

    The guard used `verification.get(node)` while the emit used `node in verification` /
    `verification[node]`. A mapping whose `get` and `__contains__` disagree therefore passed the
    guard and emitted a `live` leg carrying NO checkpoint record — a live claim with its evidence
    silently dropped. Contrived as a mapping, real as a class of bug.
    """
    class _Inconsistent(dict):
        def __contains__(self, key):        # claims to hold nothing...
            return False

    verification = _Inconsistent({"worker-A": {"model": "claude-opus-4-8", "verified": True}})
    rep = build_debate_report(record=_RECORD, legs={"worker-A": "live"},
                              verification=verification, ts="2026-07-19T00:00:00+00:00")
    # ...yet the emitted report still carries the checkpoint the guard passed on
    assert rep["debater_models"] == {"worker-A": {"model": "claude-opus-4-8", "verified": True}}


def test_report_REFUSES_a_live_leg_whose_verification_is_marked_unverified() -> None:
    with pytest.raises(DebateReportError, match="VERIFIED"):
        build_debate_report(record=_RECORD, legs={"worker-A": "live"},
                            verification={"worker-A": {"model": "x", "verified": False}},
                            ts="2026-07-19T00:00:00+00:00")


def test_report_ACCEPTS_a_live_leg_backed_by_a_verified_checkpoint() -> None:
    rep = build_debate_report(
        record=_RECORD, legs={"worker-A": "live", "worker-B": "mock"},
        verification={"worker-A": {"model": "claude-opus-4-8-20260101", "verified": True}},
        ts="2026-07-19T00:00:00+00:00")
    assert rep["legs"]["worker-A"] == "live"
    assert rep["debater_models"]["worker-A"]["model"] == "claude-opus-4-8-20260101"


@pytest.mark.parametrize("bad", ["LIVE", "real", "", None, "partial"])
def test_report_refuses_a_leg_outside_the_shared_vocabulary(bad) -> None:
    with pytest.raises(DebateReportError):
        build_debate_report(record=_RECORD, legs={"worker-A": bad}, verification={},
                            ts="2026-07-19T00:00:00+00:00")


def test_report_refuses_an_empty_leg_set() -> None:
    """A report with no legs declares nothing about what ran."""
    with pytest.raises(DebateReportError):
        build_debate_report(record=_RECORD, legs={}, verification={},
                            ts="2026-07-19T00:00:00+00:00")


def test_report_refuses_a_missing_injected_timestamp() -> None:
    with pytest.raises(DebateReportError):
        build_debate_report(record=_RECORD, legs={"worker-A": "mock"}, verification={}, ts="  ")


def test_report_deep_copies_the_record_so_later_mutation_cannot_rewrite_it() -> None:
    """Mutates a NESTED value, not a scalar: rebinding `result["outcome"]` on a shallow `dict()`
    copy would not reach the report either, so a scalar tamper cannot tell a deep copy from a
    shallow one. A nested list element can."""
    record = copy.deepcopy(_RECORD)
    record["result"]["positions"] = [{"node": "worker-A", "position": "original",
                                      "evidence_refs": ["m-1"]}]
    rep = build_debate_report(record=record, legs={"worker-A": "mock"}, verification={},
                              ts="2026-07-19T00:00:00+00:00")

    record["result"]["positions"][0]["position"] = "TAMPERED"
    record["result"]["positions"][0]["evidence_refs"].append("m-injected")

    assert rep["positions"][0]["position"] == "original"
    assert rep["positions"][0]["evidence_refs"] == ["m-1"]


def test_report_key_set_is_pinned_so_a_field_cannot_appear_or_vanish_unnoticed() -> None:
    rep = build_debate_report(record=_RECORD, legs={"worker-A": "mock"}, verification={},
                              ts="2026-07-19T00:00:00+00:00")
    assert tuple(rep) == DEBATE_REPORT_KEYS


def test_the_key_set_GUARD_actually_fires_when_the_declaration_and_the_body_disagree(
        monkeypatch) -> None:
    """Asserting `tuple(rep) == DEBATE_REPORT_KEYS` alone cannot detect the guard being deleted —
    the literal naturally matches the constant. Forcing a disagreement is what pins the guard.
    """
    monkeypatch.setattr(live_debate, "DEBATE_REPORT_KEYS",
                        DEBATE_REPORT_KEYS + ("a_field_nobody_declared",))
    with pytest.raises(DebateReportError, match="do not match the declared"):
        build_debate_report(record=_RECORD, legs={"worker-A": "mock"}, verification={},
                            ts="2026-07-19T00:00:00+00:00")


# --- spend derivation ----------------------------------------------------------------------

@pytest.mark.parametrize("legs,expected", [
    ({"a": "skipped", "b": "skipped"}, False),
    ({"a": "mock", "b": "skipped"}, True),
    ({"a": ATTEMPTED_LEG}, True),
    ({"a": "live"}, True),
    ({}, False),
])
def test_spend_is_DERIVED_from_the_legs_never_from_which_branch_was_taken(legs, expected) -> None:
    """`attempt_live_debate` reports `ran` from counted-call evidence on EVERY failure path.

    The refusal path cannot currently follow a spent call (every refusal in `DebateService`
    precedes the first `generate`), so this pins the rule at the function rather than through a
    scenario — the alternative is an assertion of `ran is False` that would silently become wrong
    the moment a future refusal moves after a call.
    """
    assert live_debate._any_spend(legs) is expected
