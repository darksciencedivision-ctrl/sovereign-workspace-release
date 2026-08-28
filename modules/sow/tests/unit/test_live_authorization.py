"""Phase 15A .liveauth: the enforced LIVE_OPERATION_AUTHORIZED gate, rewritten for the OP-6
two-provider live scope (directive §10.1/§11; register OP-6). Deterministic, fail-closed
permission logic — never model output.

The gate must EXIST and be enforced BEFORE any live path is wired ("enforcement-by-absence
ends the moment a live path exists"). These tests pin its fail-closed behaviour under the
OP-6 scope `{providers: [claude_code, openai_codex_cli], terminals_per_subscription: 2}`:
  - no config present               -> DENIED (enforcement-by-absence), not authorized
  - flag explicitly false           -> DENIED
  - malformed / bad version (1.0)   -> raise (never silently authorize)
  - wrong register row (not OP-6)   -> raise (only OP-6 authorizes the two-provider scope)
  - provider outside the OP-6 set   -> raise (a THIRD provider needs new authorization)
  - terminals_per_subscription > 2  -> raise (OP-6 cap); < 1 -> raise; True -> raise (bool guard)
  - valid OP-6 config               -> authorizes BOTH providers, terminals_per_subscription == 2
  - "codex" shorthand alias         -> normalized to the schema id openai_codex_cli
and the profile-loader enforcement: a REAL subscription-backed frontier adapter cannot pass
startup unless live operation is authorized for its provider.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.base.contract import AdapterCapability
from control_plane.profiles.live_authorization import (
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation


def _write(tmp_path: Path, obj: object) -> Path:
    p = tmp_path / "live_operation.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


# canonical OP-6 config: both providers, 2 terminals/subscription, cites OP-6
_VALID = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-6",
    "scope": {"providers": ["claude_code", "openai_codex_cli"], "terminals_per_subscription": 2},
}


# ---- enforcement-by-absence: the safe default ----------------------------------------

def test_absent_config_is_denied_not_authorized(tmp_path: Path) -> None:
    auth = load_live_authorization(path=tmp_path / "does_not_exist.json")
    assert auth.authorized is False
    assert auth.providers == frozenset()
    assert "absence" in auth.reason.lower()


def test_denied_default_gate_refuses_every_provider(tmp_path: Path) -> None:
    auth = load_live_authorization(path=tmp_path / "nope.json")
    assert auth.is_provider_live("claude_code") is False
    assert auth.is_provider_live("openai_codex_cli") is False
    with pytest.raises(LiveAuthorizationError):
        auth.assert_provider_live("claude_code")
    with pytest.raises(LiveAuthorizationError):
        auth.assert_provider_live("openai_codex_cli")


def test_flag_explicitly_false_is_denied(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID, "live_operation_authorized": False})
    auth = load_live_authorization(path=p)
    assert auth.authorized is False
    with pytest.raises(LiveAuthorizationError):
        auth.assert_provider_live("claude_code")


# ---- malformed / out-of-scope: fail closed by RAISING (never authorize) --------------

def test_malformed_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "live_operation.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_old_1_0_config_version_raises(tmp_path: Path) -> None:
    # the OP-4 single-provider shape is superseded; a 1.0 config fails closed, never authorizes
    p = _write(tmp_path, {"config_version": "1.0", "live_operation_authorized": True,
                          "register_row": "OP-4", "scope": {"provider": "claude_code", "terminals": 1}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_bad_config_version_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID, "config_version": "9.9"})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_non_bool_flag_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID, "live_operation_authorized": "yes"})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_wrong_register_row_raises(tmp_path: Path) -> None:
    # an authorization not backed by the recorded operator ruling is refused; OP-4 no longer
    # authorizes the two-provider scope (only OP-6 does)
    for row in ("OP-4", "OP-9", None):
        p = _write(tmp_path, {**_VALID, "register_row": row})
        with pytest.raises(LiveAuthorizationError):
            load_live_authorization(path=p)


def test_third_provider_is_refused(tmp_path: Path) -> None:
    # OP-6 authorizes exactly two providers; a third needs a NEW operator authorization
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code", "openai_codex_cli", "gemini_cli"],
                         "terminals_per_subscription": 2}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_unknown_provider_alone_is_refused(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["some_future_frontier"], "terminals_per_subscription": 1}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_empty_providers_list_is_refused(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID, "scope": {"providers": [], "terminals_per_subscription": 2}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_non_string_provider_is_refused(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code", 7], "terminals_per_subscription": 2}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_more_than_two_terminals_is_refused(tmp_path: Path) -> None:
    # OP-6 cap: at most 2 terminals/subscription; a config can NARROW but never widen past 2
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code", "openai_codex_cli"], "terminals_per_subscription": 3}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_zero_terminals_is_refused(tmp_path: Path) -> None:
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code"], "terminals_per_subscription": 0}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


def test_bool_terminals_cannot_masquerade_as_one(tmp_path: Path) -> None:
    # True == 1 in Python; the isinstance-bool guard must reject it (fail closed)
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code"], "terminals_per_subscription": True}})
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


@pytest.mark.parametrize("missing", ["register_row", "scope", "live_operation_authorized"])
def test_missing_required_field_raises(tmp_path: Path, missing: str) -> None:
    obj = {k: v for k, v in _VALID.items() if k != missing}
    p = _write(tmp_path, obj)
    with pytest.raises(LiveAuthorizationError):
        load_live_authorization(path=p)


# ---- valid authorization: scoped to the two OP-6 providers, up to 2 terminals --------

def test_valid_config_authorizes_both_op6_providers(tmp_path: Path) -> None:
    p = _write(tmp_path, _VALID)
    auth = load_live_authorization(path=p)
    assert auth.authorized is True
    assert auth.providers == frozenset({"claude_code", "openai_codex_cli"})
    assert auth.terminals_per_subscription == 2
    assert auth.register_row == "OP-6"
    assert auth.is_provider_live("claude_code") is True
    assert auth.is_provider_live("openai_codex_cli") is True
    auth.assert_provider_live("claude_code")       # does not raise
    auth.assert_provider_live("openai_codex_cli")  # does not raise
    # scope holds: a provider OUTSIDE the OP-6 set is still refused even when live is authorized
    assert auth.is_provider_live("gemini_cli") is False
    with pytest.raises(LiveAuthorizationError):
        auth.assert_provider_live("gemini_cli")


def test_codex_shorthand_alias_normalizes_to_schema_id(tmp_path: Path) -> None:
    # the operator/directive shorthand "codex" maps to the frozen schema id openai_codex_cli
    p = _write(tmp_path, {**_VALID, "scope": {"providers": ["codex"], "terminals_per_subscription": 1}})
    auth = load_live_authorization(path=p)
    assert auth.providers == frozenset({"openai_codex_cli"})
    assert auth.is_provider_live("codex") is True
    assert auth.is_provider_live("openai_codex_cli") is True
    assert auth.terminals_per_subscription == 1  # a narrower config is honoured


def test_config_may_narrow_to_one_provider(tmp_path: Path) -> None:
    # authorizing fewer than the full OP-6 set is a narrowing (safe), not a widening
    p = _write(tmp_path, {**_VALID,
               "scope": {"providers": ["claude_code"], "terminals_per_subscription": 2}})
    auth = load_live_authorization(path=p)
    assert auth.providers == frozenset({"claude_code"})
    assert auth.is_provider_live("openai_codex_cli") is False


def test_env_override_path_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(tmp_path, _VALID)
    monkeypatch.setenv("SOVEREIGN_LIVE_OPERATION_CONFIG", str(p))
    auth = load_live_authorization()  # no explicit path -> env override wins
    assert auth.authorized and auth.is_provider_live("claude_code")


# ---- profile-loader enforcement: a real live frontier cap needs authorization --------

def _live_frontier(adapter: str) -> AdapterCapability:
    return AdapterCapability(
        adapter=adapter, node_class="worker_reasoning", locality="frontier",
        offline_profile_eligible=False, requires_network=True, local_runtime=False,
        capabilities=("reasoning",), subscription_backed=True)


_LIVE_CLAUDE = _live_frontier("claude_code")
_LIVE_CODEX = _live_frontier("openai_codex_cli")
_MOCK_FRONTIER = AdapterCapability(
    adapter="mock", node_class="worker_reasoning", locality="frontier",
    offline_profile_eligible=False, requires_network=True, local_runtime=False,
    capabilities=("reasoning",), subscription_backed=True)


def test_startup_refuses_live_frontier_without_authorization() -> None:
    loader = ProfileLoader(DeploymentProfile("cloud"))
    denied = LiveAuthorization.denied("test: no config")
    with pytest.raises(ProfileViolation):
        loader.assert_startup([_LIVE_CLAUDE], live_auth=denied)


def test_startup_refuses_live_frontier_when_live_auth_omitted() -> None:
    loader = ProfileLoader(DeploymentProfile("cloud"))
    with pytest.raises(ProfileViolation):
        loader.assert_startup([_LIVE_CLAUDE])


def test_startup_permits_both_op6_frontiers_with_authorization(tmp_path: Path) -> None:
    loader = ProfileLoader(DeploymentProfile("cloud"))
    auth = load_live_authorization(path=_write(tmp_path, _VALID))
    loader.assert_startup([_LIVE_CLAUDE, _LIVE_CODEX], live_auth=auth)  # does not raise


def test_startup_allows_mock_frontier_without_authorization() -> None:
    loader = ProfileLoader(DeploymentProfile("cloud"))
    loader.assert_startup([_MOCK_FRONTIER])  # does not raise
    loader.assert_startup([_MOCK_FRONTIER], live_auth=LiveAuthorization.denied("x"))


def test_startup_refuses_unknown_future_frontier_provider(tmp_path: Path) -> None:
    """Fail-closed DENYLIST, not an allowlist: a subscription-backed adapter that is NOT the
    reserved mock sentinel — e.g. a provider added to the enum later — requires authorization
    and is refused when the (OP-6) authorization does not cover it."""
    future = _live_frontier("gemini_cli")
    loader = ProfileLoader(DeploymentProfile("cloud"))
    auth = load_live_authorization(path=_write(tmp_path, _VALID))
    with pytest.raises(ProfileViolation):
        loader.assert_startup([future], live_auth=auth)
    with pytest.raises(ProfileViolation):
        loader.assert_startup([future])


# ---- W-15 / R-10: `load_live_authorization()` sat OUTSIDE every gate chain's `try` --------------
# Every malformed-config path in the loader RAISES by design, so `LiveAuthorizationError` could
# never reach `except _GOVERNANCE_REFUSALS`, and the gate id it is mapped to (`live_operation`) was
# unreachable. Reproduced: a config naming `grok_build` under `register_row: "OP-6"` -- whose scope
# is claude_code + codex -- produced an uncaught traceback and `refused_by: null` in the shell,
# even while launching a purely LOCAL ollama pane that needs no live authorization at all.
#
# Blast radius: the picker, the worker ticket and the conductor ticket together.

def _malformed_live_config(tmp_path, monkeypatch):
    """A config the loader refuses: OP-6's scope is claude_code + codex, so naming grok_build under
    it is outside the authorizing row. Installed via the env var the loader already resolves."""
    p = tmp_path / "live_operation.json"
    p.write_text(json.dumps({
        "config_version": "1.1",
        "live_operation_authorized": True,
        "register_row": "OP-6",
        # OP-6's scope is claude_code + openai_codex_cli. Rows do not lend each other scope, so
        # naming grok_build here fails closed -- see config/live_operation.example.json.
        "scope": {"providers": ["grok_build"], "terminals_per_subscription": 1},
    }), encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_LIVE_OPERATION_CONFIG", str(p))
    return p


def test_a_malformed_config_refuses_the_WORKER_ticket_by_gate_not_by_traceback(tmp_path, monkeypatch):
    """W-15 NEGATIVE. A LOCAL selection needs no live authorization, and used to die on a traceback
    with `refused_by: null` -- the shell could not even say which gate refused."""
    from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
    from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
    from tools.live.emit_worker_launch import build_worker_launch_ticket

    _malformed_live_config(tmp_path, monkeypatch)
    option = {"provider": "ollama_local", "adapter": "ollama_local", "locality": "local",
              "subscription_backed": False, "label": "qwen3:8b", "model_slug": "qwen3:8b",
              "verified": True, "is_fallback": False, "roles": ["reasoning"],
              "residency": "not_loaded", "available": True, "unavailable_reason": None}
    selection = {"option": option, "role": "reasoning", "mode": "attended"}

    ticket = build_worker_launch_ticket(
        holder_pid=4242, session_id="pane-2#1.1", pane_id="pane-2", selection=selection,
        offered_options=[dict(option, roles=["reasoning"])],
        ledger=TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: True),
        governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, workspace="D:/repo", registrar=None)

    assert ticket["refused"] is True
    assert ticket["refused_by"] == "live_operation", (
        "a malformed live config must name the gate that refused, not report `refused_by: null`")
    assert "LiveAuthorizationError" in str(ticket["reason"])


def test_a_malformed_config_refuses_the_CONDUCTOR_ticket_by_gate_not_by_traceback(tmp_path, monkeypatch):
    """W-15 NEGATIVE, the conductor half of the same blast radius."""
    from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
    from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
    from tools.live.emit_conductor_launch import build_conductor_launch_ticket

    _malformed_live_config(tmp_path, monkeypatch)
    ticket = build_conductor_launch_ticket(
        holder_pid=4242,
        ledger=TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: True),
        governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, cli_present=True)

    assert ticket["refused"] is True
    # The conductor's `_refusal_ticket` carries no `refused_by` field at all -- a pre-existing shape
    # difference from the worker emitter's `_refusal`, recorded rather than changed here: adding the
    # field would alter a ticket schema the shell parses, which is wider than this unit's property.
    # The gate is still NAMED, through the gate record the ticket does carry.
    assert ticket["gates"]["live_operation_authorized"] is False
    assert "LiveAuthorizationError" in str(ticket["reason"])


def test_a_malformed_config_makes_the_PICKER_report_json_not_a_traceback(tmp_path, monkeypatch, capsys):
    """W-15 NEGATIVE, the picker half. `main()` called `build_host_picker()` unguarded, so the shell
    got a traceback on stdout. It fails closed on non-JSON -- but with no reason to report."""
    from tools.live import enumerate_pane_picker as mod

    _malformed_live_config(tmp_path, monkeypatch)
    rc = mod.main(["--emit-picker"], op12_probes=mod.no_op12_probes())
    out = capsys.readouterr().out
    payload = json.loads(out)           # must be JSON at all
    assert rc != 0
    assert payload.get("refused_by") == "live_operation"
    assert "providers" not in payload, (
        "a refused enumeration must not look like a picker with zero options")


def test_a_VALID_config_still_produces_a_picker(tmp_path, monkeypatch, capsys):
    """POSITIVE. The guard must not swallow the working path."""
    from tools.live import enumerate_pane_picker as mod

    p = tmp_path / "live_operation.json"
    p.write_text(json.dumps({"config_version": "1.1",
                             "live_operation_authorized": True,
                             "register_row": "OP-12",
                             "scope": {"providers": ["claude_code"],
                                       "terminals_per_subscription": 1}}), encoding="utf-8")
    monkeypatch.setenv("SOVEREIGN_LIVE_OPERATION_CONFIG", str(p))
    rc = mod.main(["--emit-picker"], op12_probes=mod.no_op12_probes())
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "providers" in payload
