"""Governed conductor-first pane spawn (Phase 15E `.conductor-pane`, directive §13 / OP-8).

`pane_node_spawn` refuses the conductor role and points here. These unit tests prove, WITHOUT a
live call, that the dedicated conductor path:

  * opens the conductor pane through the SAME fail-closed frontier live gates the worker path uses
    (LIVE_OPERATION_AUTHORIZED, provider-live, R8 §6 operator terms, CLI presence, I-X3), and TEARS
    DOWN releasing the governed count (D-LOOP-1);
  * builds an INTERACTIVE `claude` launch (no `-p`, no `--output-format json`) — the operator drives
    it — with a credential-scrubbed env (§2.2);
  * produces the CONDUCTOR chrome: pinned pane 1, `attended` mode, model badge = the SELECTION label
    (fable-5), executing checkpoint UNVERIFIED until a live reply (invariant 3);
  * surfaces the Resume→Select succession affordance reachable from chrome;
  * refuses fail-closed on a naked identity, a missing subscription (uncounted terminal), an
    unauthorized live_auth, unconfirmed operator terms, and an absent CLI.
"""
from __future__ import annotations

import pytest

from adapters.frontier.claude_code import (
    CLAUDE_CODE_ADAPTER,
    build_interactive_command,
    is_credential_env_key,
    scrub_credential_env,
)
from control_plane.conductor.selection import OPERATOR_SELECTED_CONDUCTOR
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import (
    DeploymentProfile,
    ProfileLoader,
    ProfileViolation,
)
from node_runtime.supervisor.conductor_pane_spawn import (
    CONDUCTOR_LABEL,
    ConductorPaneRefused,
    conductor_succession_affordance,
    spawn_conductor_pane,
)
from node_runtime.supervisor.frontier_spawn import (
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


def _authorized() -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset({CLAUDE_CODE_ADAPTER}),
        terminals_per_subscription=2, register_row="OP-6", source="(test)",
        reason="test authorization")


def _denied() -> LiveAuthorization:
    return LiveAuthorization.denied("no live-operation config (enforcement-by-absence)")


def _loader() -> ProfileLoader:
    return ProfileLoader(DeploymentProfile("cloud"))


class _MockSession:
    """A stand-in interactive session handle (mock-first): records the argv/env it was launched
    with and whether it was closed. Spawns NOTHING — no `claude`, no subprocess."""

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


def _spawn(governor=None, *, launcher=None, live=None, terms=True, model=None,
           model_available=None, node_id="conductor-fable5", profile="pp-conductor",
           subscription_ref="claude-sub"):
    gov = governor or SubscriptionGovernor()
    return spawn_conductor_pane(
        mcp_client=object(), governor=gov, subscription_ref=subscription_ref, node_id=node_id,
        permission_profile_id=profile, live_auth=live or _authorized(), profile_loader=_loader(),
        operator_terms_confirmed=terms, model=model, model_available=model_available,
        launcher=launcher)


# ---- interactive command + shared env scrub (§2.2) ------------------------------------------

def test_interactive_command_has_no_headless_flags() -> None:
    """The conductor pane is an INTERACTIVE agentic chat (OP-8 §13.1) — never the one-shot worker
    command. No `-p`, no `--output-format`, no JSON."""
    cmd = build_interactive_command("claude", model="fable-5")
    assert cmd == ["claude", "--model", "fable-5"]
    assert "-p" not in cmd and "--output-format" not in cmd and "json" not in cmd


def test_interactive_command_default_model_is_cli_default() -> None:
    assert build_interactive_command("claude", model=None) == ["claude"]
    assert build_interactive_command("claude", model="   ") == ["claude"]  # blank ⇒ CLI default


def test_interactive_command_refuses_credential_and_bypass_flags() -> None:
    """The forbidden-flag guard applies to the interactive path too (§2.2, fail closed)."""
    with pytest.raises(ValueError):
        build_interactive_command("claude", model="--dangerously-skip-permissions")


def test_scrub_credential_env_removes_every_credential_and_endpoint_var() -> None:
    base = {
        "PATH": "/usr/bin", "HOME": "/home/op", "HTTPS_PROXY": "http://p:8080",
        "ANTHROPIC_API_KEY": "sk-x", "CLAUDE_CODE_OAUTH_TOKEN": "oauth-y",
        "ANTHROPIC_BASE_URL": "http://evil", "AWS_SECRET_ACCESS_KEY": "z",
        "OPENAI_API_KEY": "sk-o", "SOME_TOKEN": "t", "GOOGLE_APPLICATION_CREDENTIALS": "/c.json",
    }
    scrubbed = scrub_credential_env(base)
    assert scrubbed == {"PATH": "/usr/bin", "HOME": "/home/op", "HTTPS_PROXY": "http://p:8080"}
    for k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL",
              "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "SOME_TOKEN",
              "GOOGLE_APPLICATION_CREDENTIALS"):
        assert is_credential_env_key(k) and k not in scrubbed


# ---- governed happy path: pinned CONDUCTOR chrome + I-X3 + teardown --------------------------

def test_conductor_pane_spawns_governed_pinned_conductor_first() -> None:
    gov = SubscriptionGovernor()
    launcher = _launcher()
    session = _spawn(gov, launcher=launcher)

    ch = session.chrome
    # conductor-first: pinned pane 1, CONDUCTOR label, attended mode (the operator talks to it)
    assert ch.label == CONDUCTOR_LABEL == "CONDUCTOR"
    assert ch.pane_ordinal == 1 and ch.pinned is True
    assert ch.role == "conductor" and ch.mode == "attended"
    assert ch.governed is True and ch.interactive is True
    assert ch.locality == "frontier" and ch.adapter == CLAUDE_CODE_ADAPTER
    # I-X3 n/2 visible in chrome (OP-6 allowance=2)
    assert ch.subscription == {"ref": "claude-sub", "in_use": 1, "allowance": 2}
    assert gov.active_count("claude-sub") == 1
    # D-LOOP-1: teardown closes the session AND releases the governed count
    session.teardown()
    assert launcher.calls["session"].closed is True
    assert gov.active_count("claude-sub") == 0


def test_badge_shows_selection_label_executing_unverified() -> None:
    """The badge shows the operator SELECTION label (fable-5); the EXECUTING checkpoint stays
    unverified until a live reply reports one (invariant 3 — never a fabricated checkpoint id)."""
    session = _spawn(launcher=_launcher())
    ch = session.chrome
    assert ch.model_label == "fable-5" == OPERATOR_SELECTED_CONDUCTOR.model
    assert ch.model_slug == "fable-5"          # requested --model slug, carried verbatim
    assert ch.model_verified is False          # no live reply ⇒ unverified
    assert ch.is_fallback is False
    rec = session.selection_record
    assert rec["selection"]["model"] == "fable-5"
    assert rec["executing"]["model"] is None   # executed nothing ⇒ None, not the requested slug
    assert rec["executing"]["verified"] is False


def test_recorded_fallback_when_selection_model_unavailable() -> None:
    """directive §11 15B: an unavailable model ⇒ recorded CLI-default fallback, never silent.
    `model_available=False` records that branch — the badge is a fallback, the argv drops --model."""
    session = _spawn(launcher=_launcher(), model_available=False)
    ch = session.chrome
    assert ch.model_label == "fable-5"          # the SELECTION label is still shown
    assert ch.model_slug is None                # resolved to the CLI default
    assert ch.is_fallback is True
    assert session.launch["argv"] == ["claude"]  # no --model ⇒ CLI default (recorded fallback)


def test_launch_spec_is_interactive_and_credential_scrubbed() -> None:
    session = _spawn(launcher=_launcher())
    launch = session.launch
    assert launch["interactive"] is True and launch["one_shot"] is False
    assert launch["argv"] == ["claude", "--model", "fable-5"]
    assert launch["env_credential_scrubbed"] is True
    assert launch["launched"] is True
    # the mock session received the scrubbed env — no credential key survived (§2.2)
    env = _launcher_env(session)
    assert not any(is_credential_env_key(k) for k in env)


def _launcher_env(session):
    return session.handle.env


def test_succession_affordance_reachable_from_chrome() -> None:
    """The Resume→Select control is reachable from the conductor chrome (OP-8 §13.7 / §12.4)."""
    session = _spawn(launcher=_launcher())
    succ = session.chrome.succession
    assert succ["available"] is True and succ["control"] == "resume_select"
    assert set(succ["actions"]) == {"resume", "select", "restore"}
    assert succ["current_selection"]["model"] == "fable-5"
    assert succ["restore_target"] == "fable-5"
    # standalone helper returns the same reachable affordance
    assert conductor_succession_affordance()["available"] is True


def test_deferred_launch_without_launcher_is_awaiting_but_still_governed() -> None:
    """With no launcher the real interactive drive is deferred to the operator-run shell — no live
    call, node_state honest ('awaiting_live_conductor'), but the terminal IS governed/acquired."""
    gov = SubscriptionGovernor()
    session = spawn_conductor_pane(
        mcp_client=object(), governor=gov, subscription_ref="claude-sub",
        node_id="conductor-fable5", permission_profile_id="pp-conductor", live_auth=_authorized(),
        profile_loader=_loader(), operator_terms_confirmed=True, cli_present=True)  # real path, CLI "present"
    assert session.launched is False and session.handle is None
    assert session.chrome.node_state == "awaiting_live_conductor"
    assert session.chrome.governed is True
    assert gov.active_count("claude-sub") == 1
    session.teardown()
    assert gov.active_count("claude-sub") == 0


# ---- fail-closed refusals --------------------------------------------------------------------

def test_unauthorized_live_auth_refused_no_terminal_leaked() -> None:
    """Enforcement-by-absence: with no LIVE_OPERATION_AUTHORIZED config the profile-loader gate
    (assert_startup) refuses first (ProfileViolation wraps the live-auth denial) — fail closed,
    before any terminal is acquired."""
    gov = SubscriptionGovernor()
    with pytest.raises(ProfileViolation):
        _spawn(gov, launcher=_launcher(), live=_denied())
    assert gov.active_count("claude-sub") == 0  # nothing acquired


def test_unconfirmed_operator_terms_refused() -> None:
    gov = SubscriptionGovernor()
    with pytest.raises(LiveTermsNotConfirmed):
        _spawn(gov, launcher=_launcher(), terms=False)
    assert gov.active_count("claude-sub") == 0


def test_absent_cli_refused_on_real_path() -> None:
    """No launcher ⇒ real path ⇒ the `claude` CLI must be present; absent ⇒ fail closed."""
    gov = SubscriptionGovernor()
    with pytest.raises(ClaudeCliUnavailable):
        spawn_conductor_pane(
            mcp_client=object(), governor=gov, subscription_ref="claude-sub",
            node_id="conductor-fable5", permission_profile_id="pp-conductor",
            live_auth=_authorized(), profile_loader=_loader(), operator_terms_confirmed=True,
            cli_present=False)
    assert gov.active_count("claude-sub") == 0


@pytest.mark.parametrize("node_id,profile", [("", "pp"), ("c1", "")])
def test_naked_session_refused(node_id: str, profile: str) -> None:
    with pytest.raises(ConductorPaneRefused):
        spawn_conductor_pane(
            mcp_client=object(), governor=SubscriptionGovernor(), subscription_ref="claude-sub",
            node_id=node_id, permission_profile_id=profile, live_auth=_authorized(),
            profile_loader=_loader(), operator_terms_confirmed=True, launcher=_launcher())


def test_missing_subscription_ref_refused() -> None:
    with pytest.raises(ConductorPaneRefused) as ei:
        spawn_conductor_pane(
            mcp_client=object(), governor=SubscriptionGovernor(), subscription_ref="",
            node_id="c1", permission_profile_id="pp", live_auth=_authorized(),
            profile_loader=_loader(), operator_terms_confirmed=True, launcher=_launcher())
    assert "subscription" in str(ei.value).lower()


def test_teardown_idempotent() -> None:
    gov = SubscriptionGovernor()
    session = _spawn(gov, launcher=_launcher())
    session.teardown()
    session.teardown()  # second call must not raise or wedge the count
    assert gov.active_count("claude-sub") == 0


def test_ix3_second_conductor_pane_on_same_subscription_allowed_third_refused() -> None:
    """Allowance=2 (OP-6): two Anthropic terminals on one subscription are permitted (the loop plus
    a conductor pane); a third is refused by the governor — I-X3 enforced, not re-implemented here."""
    from node_runtime.supervisor.subscription_governor import SubscriptionLimitExceeded
    gov = SubscriptionGovernor()
    a = _spawn(gov, launcher=_launcher(), node_id="conductor-a")
    b = _spawn(gov, launcher=_launcher(), node_id="conductor-b")
    assert gov.active_count("claude-sub") == 2
    with pytest.raises(SubscriptionLimitExceeded):
        _spawn(gov, launcher=_launcher(), node_id="conductor-c")
    assert gov.active_count("claude-sub") == 2
    a.teardown(); b.teardown()
    assert gov.active_count("claude-sub") == 0
