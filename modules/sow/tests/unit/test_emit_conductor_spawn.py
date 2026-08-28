"""Phase 16C `.spawn` — the governed CONDUCTOR spawn feed the shell sources on launch.

Proves the emitter drives the REAL governed spawn path (`spawn_conductor_pane`) through its full
live-gate chain and projects it into the stable `conductor_spawn_feed@1.0` shell contract, WITHOUT a
live model call and WITHOUT leaking the I-X3 terminal:

  * governed happy path (no launcher) ⇒ `awaiting_live_conductor`, interactive argv (no `-p`),
    credential-scrubbed env, and D-LOOP-1 teardown proven (`torn_down` + `governor_released`, the
    governor count back to 0 on the SAME injected governor);
  * the mock-first "ready" branch (a launcher injected) ⇒ `node_state: ready`, and the launched
    session is CLOSED by teardown;
  * fail-closed refusals (denied auth, unconfirmed terms, absent CLI) ⇒ a refusal feed with a reason,
    never a fabricated spawn, and no terminal leaked;
  * `--emit-conductor-spawn` prints ONLY the feed JSON and exits 0; any other invocation is a
    fail-closed usage error (exit 2).
"""
from __future__ import annotations

import json

import pytest

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER, is_credential_env_key
from control_plane.profiles.live_authorization import LiveAuthorization
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
from tools.live.emit_conductor_spawn import (
    CONDUCTOR_SPAWN_FEED_SCHEMA,
    CONDUCTOR_SUBSCRIPTION_REF,
    build_conductor_spawn_feed,
    main,
)


def _authorized() -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}),
        terminals_per_subscription=2, register_row="OP-6", source="(test)",
        reason="test authorization")


def _denied() -> LiveAuthorization:
    return LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


class _MockSession:
    """A stand-in interactive session handle (mock-first): records the argv/env it launched with and
    whether it was closed. Spawns NOTHING — no `claude`, no subprocess."""

    def __init__(self, *, argv, env, node_id):
        self.argv = list(argv)
        self.env = dict(env)
        self.node_id = node_id
        self.closed = False

    def close(self):
        self.closed = True


def _launcher():
    calls = {}

    def launch(*, argv, env, node_id):
        s = _MockSession(argv=argv, env=env, node_id=node_id)
        calls["session"] = s
        return s

    launch.calls = calls
    return launch


# ---- schema + governed happy path (deferred; no launcher) -----------------------------------

def test_feed_schema_is_pinned() -> None:
    feed = build_conductor_spawn_feed(live_auth=_authorized(), cli_present=True)
    assert feed["schema"] == CONDUCTOR_SPAWN_FEED_SCHEMA == "conductor_spawn_feed@1.0"


def test_governed_deferred_spawn_is_awaiting_and_torn_down() -> None:
    """No launcher ⇒ the real interactive drive is deferred (operator-run §6): node_state honest
    'awaiting_live_conductor', governed, and the I-X3 terminal is RELEASED by teardown (D-LOOP-1)."""
    gov = SubscriptionGovernor()
    feed = build_conductor_spawn_feed(live_auth=_authorized(), governor=gov, cli_present=True)
    assert feed["spawned"] is True and feed["refused"] is False
    assert feed["node_state"] == "awaiting_live_conductor"
    assert feed["launched"] is False
    assert feed["chrome"]["governed"] is True and feed["chrome"]["interactive"] is True
    assert feed["chrome"]["role"] == "conductor" and feed["chrome"]["label"] == "CONDUCTOR"
    assert feed["chrome"]["pinned"] is True and feed["chrome"]["pane_ordinal"] == 1
    # D-LOOP-1: teardown ran and the governor returned to 0 on the SAME injected governor.
    assert feed["torn_down"] is True and feed["governor_released"] is True
    assert gov.active_count(CONDUCTOR_SUBSCRIPTION_REF) == 0
    assert feed["live_authorized"] is True and feed["cli_present"] is True


def test_launch_spec_is_interactive_never_headless() -> None:
    """The conductor pane is an INTERACTIVE agentic chat (OP-8 §13.1) — never the one-shot `-p`
    worker command; the badge shows the SELECTION label, executing unverified (invariant 3)."""
    feed = build_conductor_spawn_feed(live_auth=_authorized(), cli_present=True)
    launch = feed["launch"]
    assert launch["interactive"] is True and launch["one_shot"] is False
    assert launch["env_credential_scrubbed"] is True
    assert launch["argv"] == ["claude", "--model", "fable-5"]
    for banned in ("-p", "--output-format", "json"):
        assert banned not in launch["argv"]
    rec = feed["selection_record"]
    assert rec["selection"]["model"] == "fable-5"
    assert rec["executing"]["model"] is None and rec["executing"]["verified"] is False


def test_subscription_view_reflects_the_acquired_terminal() -> None:
    """The chrome subscription is captured at spawn time (in_use 1 of allowance 2, OP-6), before the
    D-LOOP-1 teardown drops it back to 0."""
    feed = build_conductor_spawn_feed(live_auth=_authorized(), cli_present=True)
    assert feed["chrome"]["subscription"] == {
        "ref": CONDUCTOR_SUBSCRIPTION_REF, "in_use": 1, "allowance": 2}


# ---- mock-first "ready" branch (launcher injected; still zero live calls) ---------------------

def test_mock_launcher_reaches_ready_and_teardown_closes_the_session() -> None:
    gov = SubscriptionGovernor()
    launcher = _launcher()
    feed = build_conductor_spawn_feed(
        live_auth=_authorized(), governor=gov, cli_present=True, launcher=launcher)
    assert feed["spawned"] is True and feed["node_state"] == "ready" and feed["launched"] is True
    # the launched session received the credential-scrubbed env (§2.2) and was CLOSED by teardown
    session = launcher.calls["session"]
    assert session.closed is True
    assert not any(is_credential_env_key(k) for k in session.env)
    assert feed["torn_down"] is True and gov.active_count(CONDUCTOR_SUBSCRIPTION_REF) == 0


# ---- fail-closed refusals: never a fabricated spawn, never a leaked terminal ------------------

def test_denied_live_auth_is_a_refusal_feed_no_terminal_leaked() -> None:
    gov = SubscriptionGovernor()
    feed = build_conductor_spawn_feed(live_auth=_denied(), governor=gov, cli_present=True)
    assert feed["spawned"] is False and feed["refused"] is True
    assert feed["node_state"] == "spawn_refused"
    assert feed["chrome"] is None and feed["launch"] is None and feed["selection_record"] is None
    assert feed["reason"] and ("ProfileViolation" in feed["reason"] or "LiveAuthorization" in feed["reason"])
    assert feed["live_authorized"] is False
    assert gov.active_count(CONDUCTOR_SUBSCRIPTION_REF) == 0


def test_unconfirmed_operator_terms_is_a_refusal_feed() -> None:
    feed = build_conductor_spawn_feed(
        live_auth=_authorized(), cli_present=True, operator_terms_confirmed=False)
    assert feed["spawned"] is False and feed["refused"] is True
    assert "LiveTermsNotConfirmed" in feed["reason"]


def test_absent_cli_is_a_refusal_feed() -> None:
    """No launcher ⇒ real path ⇒ the `claude` CLI must be present; absent ⇒ fail closed, no spawn."""
    gov = SubscriptionGovernor()
    feed = build_conductor_spawn_feed(live_auth=_authorized(), governor=gov, cli_present=False)
    assert feed["spawned"] is False and feed["refused"] is True
    assert "ClaudeCliUnavailable" in feed["reason"]
    assert feed["cli_present"] is False
    assert gov.active_count(CONDUCTOR_SUBSCRIPTION_REF) == 0


def test_recorded_fallback_when_selection_model_unavailable() -> None:
    """directive §11 15B: an unavailable model ⇒ recorded CLI-default fallback, never silent."""
    feed = build_conductor_spawn_feed(
        live_auth=_authorized(), cli_present=True, model_available=False)
    assert feed["chrome"]["is_fallback"] is True
    assert feed["chrome"]["model_label"] == "fable-5"   # the SELECTION label still shown
    assert feed["launch"]["argv"] == ["claude"]          # no --model ⇒ CLI default


# ---- emit-mode contract ----------------------------------------------------------------------

def test_emit_mode_prints_only_the_feed_json_and_exits_zero(
        capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--emit-conductor-spawn"])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""  # ONLY the feed on stdout — the stable shell contract
    parsed = json.loads(captured.out)
    assert parsed["schema"] == CONDUCTOR_SPAWN_FEED_SCHEMA
    # on THIS host the real config authorizes + `claude` is present ⇒ a governed deferred spawn,
    # torn down; if the host lacked either, it would be a refusal feed — both are valid, never a
    # fabricated spawn. Assert the shape is internally consistent either way.
    assert isinstance(parsed["spawned"], bool)
    if parsed["spawned"]:
        assert parsed["node_state"] == "awaiting_live_conductor"
        assert parsed["torn_down"] is True and parsed["governor_released"] is True
        assert "-p" not in parsed["launch"]["argv"]
    else:
        assert parsed["refused"] is True and parsed["reason"]


def test_feed_round_trips_through_json() -> None:
    feed = build_conductor_spawn_feed(live_auth=_authorized(), cli_present=True)
    assert json.loads(json.dumps(feed, default=str))["node_state"] == "awaiting_live_conductor"


def test_no_arg_is_fail_closed_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 2  # non-zero ⇒ the shell source treats it as unavailable and renders no governed birth
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage" in captured.err.lower()
