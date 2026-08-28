"""Phase 14B .adapter (unit): the Claude Code live-frontier backend + governed spawn gates.

These are the deterministic, no-subprocess proofs. The credential invariant (§2.2) is the
load-bearing one: the real backend must build a command and a child env that carry NO
provider secret and cannot fall back to an API-key path. `generate()` on the real backend is
never called here (it would spawn `claude`); only its pure command/env builders are tested.
"""
from __future__ import annotations

import json
import os
import types

import pytest

from adapters.base.contract import AdapterContext, NakedLaunchRefused
from adapters.frontier.claude_code import (
    CLAUDE_CANDIDATE_MODEL_REFS,
    CLAUDE_CODE_ADAPTER,
    CLAUDE_CODE_MODEL_FLAG,
    ClaudeCliBackend,
    ClaudeCodeAuthError,
    MockClaudeCliBackend,
    build_claude_code_adapter,
    claude_code_roster_descriptor,
    resolve_claude_model_ref,
)
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from node_runtime.supervisor.frontier_spawn import (
    LiveTermsNotConfirmed,
    capability_for_claude_code,
    spawn_claude_code_terminal,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


def _supervised_ctx(node_id: str = "n1") -> AdapterContext:
    return AdapterContext(node_id=node_id, role="worker", project_id="proj",
                          permission_profile_id="pp", mcp_credential_id="ref",
                          subscription_ref="claude-sub", spawned_by_supervisor=True)


# ---- capability shape: a REAL live frontier the profile/live gate recognises --------------

def test_capability_is_live_claude_code_frontier() -> None:
    cap = capability_for_claude_code()
    assert cap.adapter == "claude_code" and cap.adapter == CLAUDE_CODE_ADAPTER
    assert cap.subscription_backed is True and cap.locality == "frontier"
    assert cap.requires_network is True and cap.offline_profile_eligible is False
    # the descriptor names claude_code, not the reserved "mock" sentinel -> a real live path
    loader = ProfileLoader(DeploymentProfile("cloud"))
    with pytest.raises(ProfileViolation):  # no authorization -> refused (fail closed)
        loader.assert_startup([cap], live_auth=LiveAuthorization.denied("unit"))


def test_adapter_holds_no_credential_and_refuses_naked_launch() -> None:
    adapter = build_claude_code_adapter(_supervised_ctx(), mcp_client=object(),
                                        backend=MockClaudeCliBackend())
    assert adapter.holds_provider_credential() is False
    assert adapter.capability().adapter == "claude_code"
    naked = AdapterContext(node_id="n", role="worker", project_id="proj",
                           permission_profile_id="pp", mcp_credential_id="ref",
                           spawned_by_supervisor=False)  # not supervisor-issued
    with pytest.raises(NakedLaunchRefused):
        build_claude_code_adapter(naked, mcp_client=object(), backend=MockClaudeCliBackend())


# ---- mock backend: deterministic, spawns nothing ------------------------------------------

def test_mock_backend_is_deterministic() -> None:
    b = MockClaudeCliBackend()
    a1 = b.generate("hello world")
    a2 = b.generate("hello world")
    assert a1 == a2 and b.calls == 2
    assert b.generate("different") != a1


# ---- CREDENTIAL INVARIANT (§2.2): the real backend transmits no secret --------------------

def test_real_backend_command_carries_no_credential() -> None:
    cmd = ClaudeCliBackend().build_command("summarise this")
    assert cmd[0] == "claude" and "-p" in cmd and "--output-format" in cmd
    joined = " ".join(cmd).lower()
    for forbidden in ("api-key", "api_key", "token", "--dangerously"):
        assert forbidden not in joined  # no key on the command line, no permission bypass


def test_real_backend_env_scrubs_all_credential_and_endpoint_vars() -> None:
    """Even if the host env holds keys/tokens/endpoint overrides, the child env must NOT — the
    subscription OAuth store (host-native, not env) is the only auth path left (§2.2)."""
    base = {
        "PATH": os.environ.get("PATH", ""), "HOME": "/home/x", "HTTP_PROXY": "http://p:8080",
        "LANG": "en_US.UTF-8", "TEMP": "/tmp",  # non-secrets — must be preserved so `claude` runs
        "ANTHROPIC_API_KEY": "sk-strip", "ANTHROPIC_AUTH_TOKEN": "tok-strip",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-strip", "ANTHROPIC_BASE_URL": "https://evil",
        "ANTHROPIC_API_URL": "https://evil2", "AWS_BEARER_TOKEN_BEDROCK": "aws-strip",
        "AWS_SECRET_ACCESS_KEY": "aws-secret", "GOOGLE_APPLICATION_CREDENTIALS": "/g.json",
        "SOME_FUTURE_API_KEY": "future-strip", "VENDOR_SECRET": "vsecret",  # caught by substring rule
    }
    env = ClaudeCliBackend().build_env(base)
    for stripped in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                     "ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL", "AWS_BEARER_TOKEN_BEDROCK",
                     "AWS_SECRET_ACCESS_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
                     "SOME_FUTURE_API_KEY", "VENDOR_SECRET"):
        assert stripped not in env, stripped
    for kept in ("PATH", "HOME", "HTTP_PROXY", "LANG", "TEMP"):
        assert kept in env, kept
    # no secret VALUE survives anywhere in the child env
    joined = "".join(env.values())
    for secret in ("sk-strip", "tok-strip", "oauth-strip", "aws-strip", "aws-secret",
                   "future-strip", "vsecret", "evil"):
        assert secret not in joined, secret


def test_auth_markers_classify_as_auth_error() -> None:
    b = ClaudeCliBackend()
    assert b._classify("Error: Please run /login to authenticate") is True
    assert b._classify("HTTP 401 Unauthorized") is True
    assert b._classify("Your credit balance is too low") is True
    # specific-enough markers: an ordinary result that merely mentions a number/word is NOT auth
    assert b._classify("some ordinary model text about compare-and-swap") is False
    assert b._classify("the HTTP spec defines 403 for forbidden resources generally") is False


def test_claude_auth_error_is_a_backend_auth_pause() -> None:
    from adapters.base.backend import BackendAuthPause
    assert issubclass(ClaudeCodeAuthError, BackendAuthPause)


# ---- spawn gate: R8 operator-terms confirmation is enforced at the real entrypoint --------

def test_spawn_refuses_when_operator_terms_unconfirmed(tmp_path) -> None:
    """Even with a valid live authorization, an unconfirmed R8 §6 [OPERATOR] terms item blocks
    the live spawn (fail closed) — and does not leak a subscription terminal."""
    import json
    from control_plane.profiles.live_authorization import load_live_authorization
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps({"config_version": "1.1", "live_operation_authorized": True,
                               "register_row": "OP-6",
                               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                                         "terminals_per_subscription": 2}}), encoding="utf-8")
    auth = load_live_authorization(path=cfg)
    gov = SubscriptionGovernor()
    with pytest.raises(LiveTermsNotConfirmed):
        spawn_claude_code_terminal(
            mcp_client=object(), governor=gov, subscription_ref="claude-sub", node_id="n1",
            permission_profile_id="pp", live_auth=auth,
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=False, backend=MockClaudeCliBackend())
    assert gov.active_count("claude-sub") == 0  # no terminal acquired on the refused path


# ---- PER-NODE MODEL SELECTION (Phase 15B `.modelsel`, directive §11 15B) -------------------

def test_resolver_carries_requested_slug_and_falls_back_honestly() -> None:
    """A requested model is carried verbatim (unverified until a live smoke); None ⇒ CLI default
    with a RECORDED fallback note (never silent, never a fabricated slug)."""
    slug, note = resolve_claude_model_ref("opus-4.8")
    assert slug == "opus-4.8" and "unverified" in note.lower()
    slug_ws, _ = resolve_claude_model_ref("  fable-5  ")
    assert slug_ws == "fable-5"  # trimmed, carried verbatim
    slug_none, note_none = resolve_claude_model_ref(None)
    assert slug_none is None and "fallback" in note_none.lower()
    slug_blank, _ = resolve_claude_model_ref("   ")
    assert slug_blank is None  # blank ⇒ CLI default, not an empty-string slug


def test_real_backend_command_selects_model_when_requested() -> None:
    """`--model <slug>` is emitted only when a model is requested; default omits it (CLI default).
    The slug carries no credential/bypass, so the §2.2 command invariant still holds."""
    cmd_default = ClaudeCliBackend().build_command("hi")
    assert CLAUDE_CODE_MODEL_FLAG not in cmd_default  # default ⇒ no --model (recorded fallback)
    cmd_model = ClaudeCliBackend(model="opus-4.8").build_command("hi")
    assert CLAUDE_CODE_MODEL_FLAG in cmd_model and "opus-4.8" in cmd_model
    assert cmd_model[0] == "claude" and "-p" in cmd_model and "--output-format" in cmd_model
    joined = " ".join(cmd_model).lower()
    for forbidden in ("api-key", "api_key", "token", "--dangerously"):
        assert forbidden not in joined  # per-node model must not weaken the credential invariant
    # a blank model is treated as CLI default, never emitted as an empty slug
    assert CLAUDE_CODE_MODEL_FLAG not in ClaudeCliBackend(model="   ").build_command("hi")


def test_roster_descriptor_surfaces_model_ref_and_fallback() -> None:
    """directive §11 15B — the per-node model resolution is a RECORDED field of the roster surface
    (requested/resolved_slug/verified/is_fallback/note + the candidate mapping), never silent."""
    d = claude_code_roster_descriptor("fable-5")
    assert d["adapter"] == CLAUDE_CODE_ADAPTER and d["subscription_backed"] is True
    mr = d["model_ref"]
    assert mr["requested"] == "fable-5" and mr["resolved_slug"] == "fable-5"
    assert mr["verified"] is False and mr["is_fallback"] is False  # unverified until a live smoke
    # CLI-default fallback branch is explicit, not silent
    fb = claude_code_roster_descriptor(None)["model_ref"]
    assert fb["resolved_slug"] is None and fb["is_fallback"] is True and "fallback" in fb["note"].lower()
    # the operator-named candidate mapping (opus-4.8, fable-5) is recorded, all unverified
    slugs = {c["provisional_slug"] for c in d["candidate_models"]}
    assert {"opus-4.8", "fable-5"} <= slugs
    assert all(c["verified"] is False for c in d["candidate_models"])
    assert {c.provisional_slug for c in CLAUDE_CANDIDATE_MODEL_REFS} == {"opus-4.8", "fable-5"}


def test_roster_descriptor_is_immutable_against_caller_mutation() -> None:
    """A caller mutating a nested requirements dict must not corrupt the module-level constant
    (deep-copy hygiene, matches the 15C .gate NIT fix)."""
    d1 = claude_code_roster_descriptor("opus-4.8")
    d1["capability_descriptors"][0]["requirements"]["min_context"] = 1
    d2 = claude_code_roster_descriptor("opus-4.8")
    assert d2["capability_descriptors"][0]["requirements"]["min_context"] == 128000


def test_mock_backend_name_reflects_selected_model() -> None:
    assert MockClaudeCliBackend(model="opus-4.8").name.endswith("opus-4.8")
    assert MockClaudeCliBackend().name.endswith("default")  # no model ⇒ CLI default label


def test_build_command_refuses_permission_bypass_slug() -> None:
    """Defense-in-depth (codex parity): a slug that IS a real claude bypass flag is refused at
    build time (fail closed) — the model selector can never smuggle a permission bypass. A benign
    prompt that happens to look like a flag is NOT a build failure (guard runs before prompt append)."""
    with pytest.raises(ValueError):
        ClaudeCliBackend(model="--dangerously-skip-permissions").build_command("hi")
    # a benign prompt equal to a flag token is fine — it is a positional value, not a flag
    cmd = ClaudeCliBackend(model="opus-4.8").build_command("--dangerously-skip-permissions")
    assert cmd[-1] == "--dangerously-skip-permissions" and "opus-4.8" in cmd


def test_failure_detail_surfaces_the_cli_s_own_message_not_its_envelope_header() -> None:
    """Phase 17A `.roundtrip`: a non-zero exit still prints the CLI's JSON envelope, and the REASON
    lives past any sane truncation — a caller saw 200 characters of `duration_api_ms`/`session_id`
    and none of "There's an issue with the selected model". That mis-classified a model-unavailable
    answer as an unrelated CLI error and cost a live run."""
    envelope = json.dumps({
        "is_error": True, "duration_api_ms": 0, "num_turns": 1, "stop_reason": "stop_sequence",
        "session_id": "21734cc6-fbbb-4da7-a867-2f623246ce48", "total_cost_usd": 0,
        "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0},
        "result": "There's an issue with the selected model (fable-5). It may not exist or you may "
                  "not have access to it.",
    })
    assert ClaudeCliBackend._human_detail(envelope).startswith("There's an issue with the selected")
    # non-JSON output is carried through verbatim (fail closed to MORE information, never less)
    assert ClaudeCliBackend._human_detail("bash: claude: command not found") \
        == "bash: claude: command not found"
    assert ClaudeCliBackend._human_detail("[1, 2, 3]") == "[1, 2, 3]"
    assert ClaudeCliBackend._human_detail(json.dumps({"is_error": True})) == '{"is_error": true}'


def test_generate_never_inherits_the_parent_stdin(monkeypatch) -> None:
    """Phase 17B `.legs`: a non-interactive worker call must hand the CLI a CLOSED stdin.

    `claude -p` reads piped stdin when stdin is not a TTY. A supervised worker inherits whatever
    stdin its parent had — under the build loop that is a pipe which never reaches EOF — so the CLI
    blocked waiting for input that was never coming and the call died at its timeout instead of
    answering. Measured on this host: 150 s timeout when inherited, 3.5 s with DEVNULL. That is what
    made the first two `.legs` live dispatches spend a real subscription call for an `attempted` leg.

    The prompt travels in argv, so closing stdin loses nothing — and a governed node reading the
    supervisor's console would be a containment hole in its own right (invariant 29).
    """
    import subprocess

    from adapters.frontier import claude_code as mod

    seen: dict[str, object] = {}

    def _fake_run(cmd, **kwargs):
        seen.update(kwargs)
        payload = json.dumps({"is_error": False, "result": "ok", "model": "claude-x"})
        return types.SimpleNamespace(
            args=cmd, returncode=0, stdout=payload, stderr="", spawned_pids=(123,))

    monkeypatch.setattr(mod, "run_managed_process", _fake_run)
    backend = ClaudeCliBackend()
    backend.generate("hello")
    assert seen.get("stdin") is subprocess.DEVNULL, (
        "the CLI inherited the parent's stdin and can block forever waiting on it")
    assert backend.last_spawned_pids == (123,)
    assert backend.spawned_pids == (123,)
