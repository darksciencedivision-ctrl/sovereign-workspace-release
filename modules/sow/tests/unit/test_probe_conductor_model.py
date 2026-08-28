"""Governed live model PROBE emitter (Phase 17A `.roundtrip`).

The probe is the only live call the launch path makes, so it is gated like one and bounded like one.
These tests pin that with zero live calls (the probe function itself is injected):

  * a CONCLUSIVE cached record short-circuits everything — no gate mutation, no terminal, no tokens;
  * a fresh probe runs only behind the same chain the conductor launch runs (live-operation
    authorization → R8 §6 operator terms → `claude` present) and holds ONE durable I-X3 terminal
    while it runs, handing it back in every path (D-LOOP-1);
  * a durable count already at the allowance REFUSES — a probe never becomes a third terminal;
  * an INCONCLUSIVE result is never cached (an auth/rate accident must not freeze into the launch
    path) and never demotes the operator's selection;
  * `--ledger-only` is the offline contract the ticket emitter relies on: it reports what is
    recorded and spends nothing.
"""
from __future__ import annotations

import json

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.claude_model_probe import ModelProbeLedger, ModelProbeRecord
from control_plane.profiles.live_authorization import LiveAuthorization
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from tools.live.probe_conductor_model import (
    MODEL_PROBE_EMIT_SCHEMA,
    PROBE_SUBSCRIPTION_REF,
    build_model_probe,
    main,
)

HOLDER = 5252


def _authorized(**over) -> LiveAuthorization:
    kw = dict(authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}),
              terminals_per_subscription=2, register_row="OP-6", source="(test)",
              reason="test authorization")
    kw.update(over)
    return LiveAuthorization(**kw)


def _leases(tmp_path, *, alive=(HOLDER,)):
    live = set(alive)
    return TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p in live)


def _accepted(label="fable-5", slug="claude-fable-5") -> ModelProbeRecord:
    return ModelProbeRecord(label=label, candidates=("fable-5", "claude-fable-5"),
                            accepted_slug=slug, checkpoint="claude-fable-5-20260701",
                            conclusive=True, is_fallback=False, attempts=(),
                            probed_at="2026-07-25T00:00:00Z", note="accepted")


def _inconclusive(label="fable-5") -> ModelProbeRecord:
    return ModelProbeRecord(label=label, candidates=("fable-5",), accepted_slug=None,
                            checkpoint=None, conclusive=False, is_fallback=False, attempts=(),
                            probed_at="2026-07-25T00:00:00Z", note="auth/rate — inconclusive")


def _build(tmp_path, *, probe=None, **over):
    kwargs = dict(
        label="fable-5", live_auth=_authorized(),
        probe_ledger=ModelProbeLedger(path=tmp_path / "probe.json"),
        lease_ledger=_leases(tmp_path), cli_present=True, holder_pid=HOLDER,
        probe=probe if probe is not None else (lambda label: _accepted(label)))
    kwargs.update(over)
    return build_model_probe(**kwargs)


def test_a_cached_conclusive_record_spends_nothing(tmp_path):
    probes = ModelProbeLedger(path=tmp_path / "probe.json")
    probes.write(_accepted())
    called = []
    out = _build(tmp_path, probe_ledger=probes, probe=lambda label: called.append(label) or _accepted())
    assert out["schema"] == MODEL_PROBE_EMIT_SCHEMA
    assert out["source"] == "ledger" and out["spent_live_call"] is False
    assert called == []                                    # no live call, no terminal, no tokens
    assert out["resolution"]["model"] == "claude-fable-5"
    assert out["resolution"]["model_available"] is True


def test_reprobe_forces_a_fresh_live_probe(tmp_path):
    probes = ModelProbeLedger(path=tmp_path / "probe.json")
    probes.write(_accepted(slug="fable-5"))
    out = _build(tmp_path, probe_ledger=probes, reprobe=True,
                 probe=lambda label: _accepted(slug="claude-fable-5"))
    assert out["source"] == "probed"
    assert probes.read("fable-5").accepted_slug == "claude-fable-5"   # the cache was refreshed


def test_a_fresh_probe_holds_one_terminal_and_hands_it_back(tmp_path):
    leases = _leases(tmp_path)
    held = []

    def probe(label):
        held.append(leases.in_use(PROBE_SUBSCRIPTION_REF))   # observed DURING the probe
        return _accepted(label)

    out = _build(tmp_path, lease_ledger=leases, probe=probe)
    assert out["source"] == "probed" and out["ok"] is True
    assert held == [1]                                       # I-X3 counted while the call ran
    assert leases.in_use(PROBE_SUBSCRIPTION_REF) == 0        # D-LOOP-1: nothing outlives the tool


def test_the_terminal_is_handed_back_even_when_the_probe_raises(tmp_path):
    leases = _leases(tmp_path)

    def boom(label):
        raise RuntimeError("probe exploded")

    with pytest.raises(RuntimeError):
        _build(tmp_path, lease_ledger=leases, probe=boom)
    assert leases.in_use(PROBE_SUBSCRIPTION_REF) == 0


def test_a_full_durable_count_refuses_rather_than_taking_a_third_terminal(tmp_path):
    leases = _leases(tmp_path)
    for i in range(2):
        leases.acquire(subscription_ref=PROBE_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                       node_id=f"other-{i}", allowance=2, holder_pid=HOLDER, session_id=f"s{i}")
    out = _build(tmp_path, lease_ledger=leases, probe=lambda label: _accepted(label))
    assert out["refused"] is True and out["ok"] is False
    assert "SubscriptionLimitExceeded" in out["reason"]
    assert out["resolution"]["model_available"] is None       # unprobed ⇒ launch is unchanged
    assert leases.in_use(PROBE_SUBSCRIPTION_REF) == 2         # nothing leaked


def test_an_unauthorized_live_config_refuses_before_any_call(tmp_path):
    called = []
    out = _build(tmp_path, live_auth=_authorized(authorized=False, providers=frozenset()),
                 probe=lambda label: called.append(label) or _accepted(label))
    assert out["refused"] is True and called == []
    assert out["source"] == "refused"


def test_unconfirmed_operator_terms_refuse(tmp_path):
    out = _build(tmp_path, operator_terms_confirmed=False)
    assert out["refused"] is True and "LiveTermsNotConfirmed" in out["reason"]


def test_an_absent_cli_refuses(tmp_path):
    out = _build(tmp_path, cli_present=False)
    assert out["refused"] is True and "ClaudeCliUnavailable" in out["reason"]


def test_an_inconclusive_probe_is_never_cached(tmp_path):
    probes = ModelProbeLedger(path=tmp_path / "probe.json")
    out = _build(tmp_path, probe_ledger=probes, probe=lambda label: _inconclusive(label))
    assert out["source"] == "probed"
    assert out["resolution"]["model_available"] is None       # not "unavailable"
    assert probes.read("fable-5") is None                     # nothing frozen into the launch path


def test_ledger_only_is_offline_and_reports_the_absence_honestly(tmp_path):
    called = []
    out = _build(tmp_path, ledger_only=True,
                 probe=lambda label: called.append(label) or _accepted(label))
    assert called == [] and out["source"] == "ledger"
    assert out["record"] is None
    assert out["resolution"]["source"] == "unprobed"


def test_cli_main_emits_one_json_line(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("SOW_MODEL_PROBE_LEDGER", str(tmp_path / "probe.json"))
    ModelProbeLedger(path=tmp_path / "probe.json").write(_accepted())
    assert main(["--emit-model-probe", "--label", "fable-5", "--ledger-only"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["schema"] == MODEL_PROBE_EMIT_SCHEMA
    assert payload["resolution"]["model"] == "claude-fable-5"


def test_cli_usage_error_exits_two_with_no_json(capsys):
    assert main([]) == 2
    assert capsys.readouterr().out == ""
