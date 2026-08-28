"""Phase 16C `.selection` — the authoritative CONDUCTOR selection feed (closes U65).

Proves the emitter is a faithful, drift-free projection of the ONE selection authority
(`OPERATOR_SELECTED_CONDUCTOR`) and the succession affordance, and that `--emit-conductor-selection`
prints exactly that feed as JSON. The whole point of U65 is that the shell can source this instead of
keeping a hand-maintained literal — so the ANTI-DRIFT assertions here are the load-bearing ones.
"""
from __future__ import annotations

import json

import pytest

from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    bind_conductor_selection,
)
from node_runtime.supervisor.conductor_pane_spawn import conductor_succession_affordance
from adapters.frontier.claude_model_probe import ModelProbeLedger, ModelProbeRecord
from tools.live.emit_conductor_selection import (
    CONDUCTOR_SELECTION_FEED_SCHEMA,
    build_conductor_selection_feed,
    main,
)


def test_feed_schema_is_pinned() -> None:
    feed = build_conductor_selection_feed()
    assert feed["schema"] == CONDUCTOR_SELECTION_FEED_SCHEMA == "conductor_selection_feed@1.0"


def _empty_probe(tmp_path) -> ModelProbeLedger:
    """An UNPROBED host — the feed must then be exactly what it was before the probe existed."""
    return ModelProbeLedger(path=tmp_path / "probe.json")


def _fallback_probe(tmp_path) -> ModelProbeLedger:
    led = ModelProbeLedger(path=tmp_path / "probe.json")
    led.write(ModelProbeRecord(
        label="fable-5", candidates=("fable-5", "claude-fable-5"), accepted_slug=None,
        checkpoint=None, conclusive=True, is_fallback=True, attempts=(),
        probed_at="2026-07-25T00:00:00Z", note="every candidate rejected"))
    return led


def test_selection_record_is_the_authoritative_operator_selection_no_drift(tmp_path) -> None:
    # The exact anti-drift guarantee U65 asks for: the feed's selection is the operator's authority
    # record verbatim, not a copy that could disagree. (On an UNPROBED host the whole record is
    # byte-identical to the raw bind — the probe wiring adds nothing of its own.)
    feed = build_conductor_selection_feed(probe_ledger=_empty_probe(tmp_path))
    assert feed["selection_record"]["selection"] == OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()
    assert feed["selection_record"] == bind_conductor_selection(OPERATOR_SELECTED_CONDUCTOR).as_record()
    assert feed["selection_record"]["selection"]["model"] == "fable-5"
    assert feed["model_probe"]["source"] == "unprobed"


def test_pre_launch_binding_is_honest_nothing_executed(tmp_path) -> None:
    # Invariant 3: the badge shows the SELECTION label; the EXECUTING checkpoint stays unverified
    # until a live reply reports one. Nothing has run when the shell merely renders the badge.
    exec_rec = build_conductor_selection_feed(
        probe_ledger=_empty_probe(tmp_path))["selection_record"]["executing"]
    assert exec_rec["model"] is None
    assert exec_rec["verified"] is False
    assert exec_rec["is_fallback"] is False  # fable-5 is requested; no fallback recorded pre-launch


def test_the_badge_SURFACES_a_recorded_cli_default_fallback(tmp_path) -> None:
    """Phase 17A `.roundtrip`: `is_fallback` used to be structurally unreachable here, so on a host
    whose CLI rejects the operator's label the badge read "fable-5" while pane 1 ran the vendor
    default — the exact silence §11 15B / §16 17A forbid."""
    feed = build_conductor_selection_feed(probe_ledger=_fallback_probe(tmp_path))
    exec_rec = feed["selection_record"]["executing"]
    assert exec_rec["is_fallback"] is True
    assert exec_rec["resolved_slug"] is None
    assert "unavailable" in exec_rec["note"]
    assert feed["model_probe"]["model_available"] is False
    # the operator's SELECTION is untouched — the fallback is about what the CLI accepts
    assert feed["selection_record"]["selection"]["model"] == "fable-5"


def test_an_accepted_slug_reaches_the_badge(tmp_path) -> None:
    led = ModelProbeLedger(path=tmp_path / "probe.json")
    led.write(ModelProbeRecord(
        label="fable-5", candidates=("fable-5", "claude-fable-5"), accepted_slug="claude-fable-5",
        checkpoint="claude-fable-5", conclusive=True, is_fallback=False, attempts=(),
        probed_at="2026-07-25T00:00:00Z", note="accepted"))
    feed = build_conductor_selection_feed(probe_ledger=led)
    assert feed["selection_record"]["executing"]["resolved_slug"] == "claude-fable-5"
    assert feed["selection_record"]["executing"]["is_fallback"] is False
    assert feed["selection_record"]["selection"]["model"] == "fable-5"   # label unchanged
    # still UNVERIFIED for this binding: the probe's checkpoint is the probe call's, not this one's
    assert feed["selection_record"]["executing"]["verified"] is False


def test_succession_is_the_authoritative_affordance() -> None:
    feed = build_conductor_selection_feed()
    assert feed["succession"] == conductor_succession_affordance(OPERATOR_SELECTED_CONDUCTOR)
    assert feed["succession"]["available"] is True
    assert feed["succession"]["restore_target"] == "fable-5"
    assert feed["succession"]["actions"] == ["resume", "select", "restore"]


def test_feed_is_json_serializable() -> None:
    # The shell parses this over a subprocess pipe — it must round-trip through JSON unchanged.
    feed = build_conductor_selection_feed()
    assert json.loads(json.dumps(feed)) == feed


def test_emit_mode_prints_only_the_feed_json_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--emit-conductor-selection"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""  # ONLY the feed on stdout — the stable shell contract
    parsed = json.loads(captured.out)
    from control_plane.conductor.registry import load_runtime_conductor_descriptor
    assert parsed == build_conductor_selection_feed(
        descriptor=load_runtime_conductor_descriptor())


def test_no_arg_is_fail_closed_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 2  # non-zero ⇒ the shell source treats it as unavailable and renders unknown
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage" in captured.err.lower()
