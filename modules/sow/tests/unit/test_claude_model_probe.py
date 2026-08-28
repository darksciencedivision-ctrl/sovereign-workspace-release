"""Phase 17A `.roundtrip` — the live model-availability PROBE (tests first).

The operator's conductor selection is a LABEL ("fable-5"). Whether the host `claude` CLI accepts
that label as a `--model` slug is not knowable offline, and the shell was launching with it
unchecked: the live session started, painted its banner, took the keystrokes — and answered every
prompt with "There's an issue with the selected model (fable-5)". A live session that cannot answer
is the black pane with extra steps.

These tests pin the probe's rules with ZERO live calls (injected fake backends):
  * a slug is ACCEPTED only when a real one-shot call ran on it — never by assumption;
  * an error text that says the model is unavailable moves to the NEXT candidate;
  * a "successful" reply whose TEXT is the CLI's own model-unavailable message is NOT acceptance
    (the CLI reports that condition inside a 0-exit response, so exit status alone is not evidence);
  * an auth/rate condition proves NOTHING about the slug ⇒ inconclusive, and the record is not
    allowed to demote the operator's selection;
  * exhausting the candidates with model-unavailable answers is the CLI-DEFAULT FALLBACK, recorded
    and surfaced (directive §11 15B / §16 17A: "unavailable ⇒ recorded fallback, never silent").
"""
from __future__ import annotations

import json

import pytest

from adapters.frontier.claude_code import ClaudeCliBackend, ClaudeCodeAuthError
from adapters.frontier.claude_model_probe import (
    MODEL_PROBE_SCHEMA,
    ModelProbeLedger,
    ModelProbeRecord,
    candidate_slugs_for,
    classify_probe_failure,
    launch_model_resolution,
    probe_claude_model,
)


def _scripted_backend(slug, script):
    """A REAL `ClaudeCliBackend` (exact class — the probe's liveness rule is exact-type) whose
    `generate` is replaced on the INSTANCE so nothing is spawned. That substitution is the stated
    U43 limit of the vendor-side rule, used here deliberately to script the CLI's answers; the fake
    sets `calls` / `reported_model` / `reported_model_at_call` exactly as the real `generate` does."""
    backend = ClaudeCliBackend(model=slug)

    def generate(prompt, *, max_tokens=256):
        backend.calls += 1
        outcome = script(backend.model)
        if isinstance(outcome, Exception):
            raise outcome
        text, checkpoint = outcome
        backend.reported_model = checkpoint
        backend.reported_model_at_call = backend.calls if checkpoint else None
        return text

    backend.generate = generate
    return backend


def _factory(script):
    return lambda slug: _scripted_backend(slug, script)


def test_candidates_are_the_label_then_the_vendor_namespaced_form():
    assert candidate_slugs_for("fable-5") == ("fable-5", "claude-fable-5")
    # already namespaced ⇒ no duplicate, no invented third form
    assert candidate_slugs_for("claude-opus-5") == ("claude-opus-5",)
    # blank label ⇒ nothing to probe (the CLI default needs no slug)
    assert candidate_slugs_for("") == ()
    assert candidate_slugs_for(None) == ()


def test_classifier_reads_the_cli_s_own_model_unavailable_wording():
    assert classify_probe_failure(
        "There's an issue with the selected model (fable-5). It may not exist or you may not "
        "have access to it. Run /model to pick a different model.") == "model_unavailable"
    assert classify_probe_failure('{"type":"not_found_error","message":"model: fable-5"}') \
        == "model_unavailable"
    assert classify_probe_failure("claude CLI exited 1: something else entirely") == "cli_error"
    assert classify_probe_failure("") == "cli_error"


def test_first_candidate_accepted_records_the_checkpoint_and_stops():
    rec = probe_claude_model("fable-5", backend_factory=_factory(
        lambda slug: ("ok", "claude-fable-5-20260701")), now=lambda: "2026-07-25T00:00:00Z")
    assert rec.accepted_slug == "fable-5"
    assert rec.checkpoint == "claude-fable-5-20260701"
    assert rec.conclusive is True
    assert rec.is_fallback is False
    assert [a.slug for a in rec.attempts] == ["fable-5"]     # no wasted second live call
    assert rec.schema == MODEL_PROBE_SCHEMA
    assert rec.rule and "ACCEPTED" in rec.rule


def test_unavailable_first_candidate_falls_through_to_the_namespaced_slug():
    def script(slug):
        if slug == "fable-5":
            return RuntimeError("claude CLI reported error: There's an issue with the selected "
                                "model (fable-5). It may not exist or you may not have access to it.")
        return ("ok", "claude-fable-5-20260701")

    rec = probe_claude_model("fable-5", backend_factory=_factory(script))
    assert rec.accepted_slug == "claude-fable-5"
    assert rec.conclusive is True and rec.is_fallback is False
    assert [(a.slug, a.classification) for a in rec.attempts] == [
        ("fable-5", "model_unavailable"), ("claude-fable-5", "accepted")]


def test_a_zero_exit_reply_that_IS_the_unavailable_message_is_not_acceptance():
    """The CLI delivers this condition as an ordinary assistant reply (observed in the live
    interactive session), so a 0 exit and a parsed JSON result are not evidence the slug ran."""
    rec = probe_claude_model("fable-5", backend_factory=_factory(
        lambda slug: ("There's an issue with the selected model (fable-5). It may not exist or you "
                      "may not have access to it. Run /model to pick a different model.", None)))
    assert rec.accepted_slug is None
    assert rec.conclusive is True and rec.is_fallback is True
    assert {a.classification for a in rec.attempts} == {"model_unavailable"}


def test_every_candidate_unavailable_is_the_recorded_cli_default_fallback():
    rec = probe_claude_model("fable-5", backend_factory=_factory(
        lambda slug: RuntimeError("claude CLI reported error: model not found")))
    assert rec.accepted_slug is None
    assert rec.conclusive is True
    assert rec.is_fallback is True            # ⇒ launch with NO --model, and SAY so
    assert len(rec.attempts) == 2
    assert "fallback" in rec.note.lower()


def test_auth_or_rate_failure_is_inconclusive_and_never_demotes_the_selection():
    calls = []

    def script(slug):
        calls.append(slug)
        raise ClaudeCodeAuthError("claude CLI auth/rate failure: usage limit reached")

    rec = probe_claude_model("fable-5", backend_factory=_factory(script))
    assert rec.conclusive is False            # we learned nothing about the slug
    assert rec.is_fallback is False
    assert rec.accepted_slug is None
    assert calls == ["fable-5"]               # aborts — a rate-limited host is not asked twice
    assert rec.attempts[0].classification == "auth_or_rate"


def test_an_inconclusive_record_leaves_the_launch_exactly_as_it_was():
    """Fail-closed direction for a CACHE: not-probed must not become "unavailable"."""
    rec = ModelProbeRecord(label="fable-5", candidates=("fable-5",), accepted_slug=None,
                           checkpoint=None, conclusive=False, is_fallback=False, attempts=(),
                           probed_at="2026-07-25T00:00:00Z", note="inconclusive")
    res = launch_model_resolution("fable-5", record=rec)
    assert res["model"] is None               # ⇒ the selection's own label is used, as before
    assert res["model_available"] is None     # ⇒ "not probed", not "unavailable"
    assert res["source"] == "inconclusive"


def test_launch_resolution_uses_the_accepted_slug_and_marks_it_available():
    rec = ModelProbeRecord(label="fable-5", candidates=("fable-5", "claude-fable-5"),
                           accepted_slug="claude-fable-5", checkpoint="claude-fable-5-20260701",
                           conclusive=True, is_fallback=False, attempts=(),
                           probed_at="2026-07-25T00:00:00Z", note="accepted")
    res = launch_model_resolution("fable-5", record=rec)
    assert res["model"] == "claude-fable-5"
    assert res["model_available"] is True
    assert res["source"] == "probe-ledger"


def test_launch_resolution_records_the_fallback_when_the_probe_was_conclusive():
    rec = ModelProbeRecord(label="fable-5", candidates=("fable-5", "claude-fable-5"),
                           accepted_slug=None, checkpoint=None, conclusive=True, is_fallback=True,
                           attempts=(), probed_at="2026-07-25T00:00:00Z", note="fallback")
    res = launch_model_resolution("fable-5", record=rec)
    assert res["model"] is None
    assert res["model_available"] is False    # ⇒ bind_conductor_selection records the fallback
    assert res["source"] == "probe-ledger"


def test_no_record_at_all_is_unprobed_not_unavailable():
    res = launch_model_resolution("fable-5", record=None)
    assert res["model"] is None and res["model_available"] is None and res["source"] == "unprobed"


def test_ledger_round_trip_and_corruption_reads_as_unprobed(tmp_path):
    path = tmp_path / "probe.json"
    led = ModelProbeLedger(path=path)
    assert led.read("fable-5") is None
    rec = probe_claude_model("fable-5", backend_factory=_factory(
        lambda slug: ("ok", "claude-fable-5-20260701")))
    led.write(rec)
    back = led.read("fable-5")
    assert back is not None
    assert back.accepted_slug == "fable-5" and back.checkpoint == "claude-fable-5-20260701"
    assert back.conclusive is True
    # a different label is not answered by this record
    assert led.read("opus-4.8") is None
    # corruption must fail CLOSED to "unprobed" (carry the label verbatim), never to "unavailable"
    path.write_text("{not json", encoding="utf-8")
    assert ModelProbeLedger(path=path).read("fable-5") is None
    # a shape drift (missing the pinned schema) is equally inert
    path.write_text(json.dumps({"entries": {"fable-5": {"accepted_slug": "x"}}}), encoding="utf-8")
    assert ModelProbeLedger(path=path).read("fable-5") is None


def test_ledger_write_keeps_other_labels(tmp_path):
    path = tmp_path / "probe.json"
    led = ModelProbeLedger(path=path)
    led.write(ModelProbeRecord(label="opus-4.8", candidates=("opus-4.8",), accepted_slug="opus-4.8",
                               checkpoint="claude-opus-4-8-x", conclusive=True, is_fallback=False,
                               attempts=(), probed_at="2026-07-25T00:00:00Z", note="n"))
    led.write(probe_claude_model("fable-5", backend_factory=_factory(
        lambda slug: ("ok", "claude-fable-5-20260701"))))
    assert led.read("opus-4.8").accepted_slug == "opus-4.8"
    assert led.read("fable-5").accepted_slug == "fable-5"


def test_a_mock_backend_can_never_produce_an_accepted_record():
    """The probe's positive claim is backed by the SAME vendor-side rule the rest of the build uses:
    a mock (not the exact CLI class) spends no subscription call and proves nothing."""
    class _Mock:
        calls = 0
        reported_model = "claude-fable-5-20260701"
        reported_model_at_call = 1

        def generate(self, prompt, *, max_tokens=256):
            return "ok"

    rec = probe_claude_model("fable-5", backend_factory=lambda slug: _Mock())
    assert rec.accepted_slug is None
    assert rec.conclusive is False            # no live evidence either way
    assert rec.attempts[0].classification == "not_a_live_backend"


def test_probe_refuses_a_blank_label():
    with pytest.raises(ValueError):
        probe_claude_model("   ", backend_factory=_factory(lambda slug: ("ok", "x")))
