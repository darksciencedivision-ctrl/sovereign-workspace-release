"""Phase 15C .adapter (unit): the live `openai_codex_cli` frontier backend + governed spawn gates.

Deterministic, no-subprocess proofs. The load-bearing invariants are (§2.2) — the real backend
must build a command and a child env carrying NO provider secret and no auth-passing/sandbox-bypass
flag, and cannot fall back to an API-key path — and (T2) — the sandbox is explicit and never
`danger-full-access`. `generate()` on the real backend is never called here (it would spawn
`codex`); only its pure command/env builders are tested.
"""
from __future__ import annotations

import os

import subprocess

import pytest

from adapters.base.backend import BackendAuthPause
from adapters.base.contract import AdapterContext, NakedLaunchRefused
from adapters.frontier.codex import (
    CODEX_ADAPTER,
    CODEX_CODING_NODE_CLASS,
    CODEX_REASONING_NODE_CLASS,
    SANDBOX_READ_ONLY,
    SANDBOX_WORKSPACE_WRITE,
    CodexAuthError,
    CodexCliBackend,
    MockCodexCliBackend,
    build_codex_adapter,
    codex_roster_descriptor,
    resolve_codex_model_ref,
)
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from node_runtime.supervisor.codex_spawn import (
    LiveTermsNotConfirmed,
    attempt_codex_live_smoke,
    capability_for_codex,
    spawn_codex_terminal,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor


def _supervised_ctx(node_id: str = "n1") -> AdapterContext:
    return AdapterContext(node_id=node_id, role="worker", project_id="proj",
                          permission_profile_id="pp", mcp_credential_id="ref",
                          subscription_ref="codex-sub", spawned_by_supervisor=True)


# ---- capability shape: a REAL live frontier the profile/live gate recognises --------------

def test_capability_is_live_codex_frontier() -> None:
    cap = capability_for_codex("reasoning")
    assert cap.adapter == "openai_codex_cli" and cap.adapter == CODEX_ADAPTER
    assert cap.subscription_backed is True and cap.locality == "frontier"
    assert cap.requires_network is True and cap.offline_profile_eligible is False
    assert cap.node_class == CODEX_REASONING_NODE_CLASS
    # the descriptor names openai_codex_cli, not the reserved "mock" sentinel -> a real live path
    loader = ProfileLoader(DeploymentProfile("cloud"))
    with pytest.raises(ProfileViolation):  # no authorization -> refused (fail closed)
        loader.assert_startup([cap], live_auth=LiveAuthorization.denied("unit"))


def test_coding_role_maps_to_coding_specialist_node_class() -> None:
    cap = capability_for_codex("coding")
    assert cap.node_class == CODEX_CODING_NODE_CLASS
    assert "coding" in cap.capabilities


def test_adapter_holds_no_credential_and_refuses_naked_launch() -> None:
    adapter = build_codex_adapter(_supervised_ctx(), mcp_client=object(),
                                  backend=MockCodexCliBackend(), role="reasoning")
    assert adapter.holds_provider_credential() is False
    assert adapter.capability().adapter == "openai_codex_cli"
    naked = AdapterContext(node_id="n", role="worker", project_id="proj",
                           permission_profile_id="pp", mcp_credential_id="ref",
                           spawned_by_supervisor=False)  # not supervisor-issued
    with pytest.raises(NakedLaunchRefused):
        build_codex_adapter(naked, mcp_client=object(), backend=MockCodexCliBackend())


# ---- mock backend: deterministic, spawns nothing ------------------------------------------

def test_mock_backend_is_deterministic() -> None:
    b = MockCodexCliBackend()
    a1 = b.generate("hello world")
    a2 = b.generate("hello world")
    assert a1 == a2 and b.calls == 2
    assert b.generate("different") != a1


# ---- CREDENTIAL INVARIANT (§2.2): the real backend transmits no secret --------------------

def test_real_backend_command_carries_no_credential_or_bypass() -> None:
    cmd = CodexCliBackend(executable="codex", model="5.5").build_command("summarise this")
    assert cmd[0] == "codex" and "exec" in cmd and "-m" in cmd and "5.5" in cmd
    assert "--sandbox" in cmd and SANDBOX_READ_ONLY in cmd  # reasoning role default
    joined = " ".join(cmd).lower()
    for forbidden in ("--with-api-key", "--with-access-token", "--api-key", "api_key", "token",
                      "--dangerously-bypass-approvals-and-sandbox",
                      "--dangerously-bypass-hook-trust", "danger-full-access", "--full-auto"):
        assert forbidden not in joined, forbidden


def test_coding_role_command_is_workspace_write_and_worktree_scoped() -> None:
    cmd = CodexCliBackend(executable="codex", model="5.5", role="coding",
                          workdir="/work/wt").build_command("edit the file")
    assert "--sandbox" in cmd and SANDBOX_WORKSPACE_WRITE in cmd
    assert "--cd" in cmd and "/work/wt" in cmd  # worktree isolation for the coding role (T2)
    assert "danger-full-access" not in " ".join(cmd)


def test_default_model_omits_model_flag() -> None:
    """No requested model -> no `-m` (CLI default, recorded roster fallback), never a fabricated slug."""
    cmd = CodexCliBackend(executable="codex").build_command("hello")
    assert "-m" not in cmd
    slug, note = resolve_codex_model_ref(None)
    assert slug is None and "fallback" in note.lower()
    slug2, note2 = resolve_codex_model_ref("5.5 Sol")
    assert slug2 == "5.5 Sol" and "unverified" in note2.lower()


def test_danger_full_access_sandbox_refused() -> None:
    with pytest.raises(ValueError):
        CodexCliBackend(executable="codex", sandbox_mode="danger-full-access")


def test_coding_role_without_worktree_refused_fail_closed() -> None:
    """T2 / Phase 10: a coding (workspace-write) backend with no isolated worktree is refused at
    construction — write access is NEVER granted unscoped (it would run at cwd=None = the
    supervisor's dir). A reasoning read-only backend needs no worktree."""
    with pytest.raises(ValueError):
        CodexCliBackend(executable="codex", role="coding")  # workspace-write, no --cd scope
    with pytest.raises(ValueError):  # same refusal if a read-only role is forced to write with no scope
        CodexCliBackend(executable="codex", role="reasoning", sandbox_mode=SANDBOX_WORKSPACE_WRITE)
    # a properly worktree-scoped coding backend is accepted and carries --cd
    cmd = CodexCliBackend(executable="codex", role="coding", workdir="/work/wt").build_command("edit")
    assert "--cd" in cmd and "/work/wt" in cmd and SANDBOX_WORKSPACE_WRITE in cmd
    CodexCliBackend(executable="codex", role="reasoning")  # read-only, no worktree needed: fine


def test_real_backend_env_scrubs_all_credential_and_endpoint_vars() -> None:
    """Even if the host env holds keys/tokens/endpoint overrides, the child env must NOT — the
    subscription OAuth store (host-native `~/.codex/auth.json`, not env) is the only auth path left
    (§2.2). CODEX_HOME (the config/auth dir pointer, not a secret) is preserved."""
    base = {
        "PATH": os.environ.get("PATH", ""), "HOME": "/home/x", "HTTP_PROXY": "http://p:8080",
        "LANG": "en_US.UTF-8", "TEMP": "/tmp", "CODEX_HOME": "/home/x/.codex",  # kept: not a secret
        "OPENAI_API_KEY": "sk-strip", "OPENAI_BASE_URL": "https://evil",
        "OPENAI_ORG_ID": "org-strip", "CODEX_API_KEY": "codex-strip",
        "AZURE_OPENAI_API_KEY": "az-strip", "AZURE_OPENAI_ENDPOINT": "https://evil2",
        "AWS_SECRET_ACCESS_KEY": "aws-secret", "ANTHROPIC_API_KEY": "ant-strip",
        "GOOGLE_APPLICATION_CREDENTIALS": "/g.json",
        "SOME_FUTURE_API_KEY": "future-strip", "VENDOR_SECRET": "vsecret",  # substring rule
        "MY_ACCESS_TOKEN": "tok-strip", "APP_CREDENTIAL": "cred-strip", "RANDOM_KEY": "key-strip",
    }
    env = CodexCliBackend(executable="codex").build_env(base)
    for stripped in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "CODEX_API_KEY",
                     "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AWS_SECRET_ACCESS_KEY",
                     "ANTHROPIC_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "SOME_FUTURE_API_KEY",
                     "VENDOR_SECRET", "MY_ACCESS_TOKEN", "APP_CREDENTIAL", "RANDOM_KEY"):
        assert stripped not in env, stripped
    for kept in ("PATH", "HOME", "HTTP_PROXY", "LANG", "TEMP", "CODEX_HOME"):
        assert kept in env, kept
    # no secret VALUE survives anywhere in the child env
    joined = "".join(env.values())
    for secret in ("sk-strip", "org-strip", "codex-strip", "az-strip", "aws-secret", "ant-strip",
                   "future-strip", "vsecret", "tok-strip", "cred-strip", "key-strip", "evil"):
        assert secret not in joined, secret


def test_auth_markers_classify_as_auth_error() -> None:
    b = CodexCliBackend(executable="codex")
    assert b._classify("Error: Please run `codex login` to authenticate") is True
    assert b._classify("HTTP 401 Unauthorized") is True
    assert b._classify("You have hit your usage limit for this month") is True
    assert b._classify("insufficient_quota: add credits") is True
    # specific-enough markers: an ordinary result mentioning a word is NOT auth
    assert b._classify("some ordinary model text about compare-and-swap keys in a b-tree") is False


def test_codex_auth_error_is_a_backend_auth_pause() -> None:
    assert issubclass(CodexAuthError, BackendAuthPause)


# ---- spawn gate: R8 operator-terms confirmation is enforced at the real entrypoint --------

def test_spawn_refuses_when_operator_terms_unconfirmed(tmp_path) -> None:
    """Even with a valid live authorization, an unconfirmed R8 §6 [OPERATOR] terms item blocks the
    live spawn (fail closed) — and does not leak a subscription terminal."""
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
        spawn_codex_terminal(
            mcp_client=object(), governor=gov, subscription_ref="codex-sub", node_id="n1",
            permission_profile_id="pp", live_auth=auth,
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=False, backend=MockCodexCliBackend())
    assert gov.active_count("codex-sub") == 0  # no terminal acquired on the refused path


# ---- NIT-2 (15C .gate): the recorded model-ref fallback is SURFACED in a roster descriptor ---

def test_roster_descriptor_surfaces_cli_default_fallback() -> None:
    """No requested model ⇒ the descriptor records the CLI-default fallback explicitly (directive
    §11 15C, "never silent"): resolved_slug None, is_fallback True, verified False, note recorded."""
    d = codex_roster_descriptor("reasoning", None)
    assert d["adapter"] == CODEX_ADAPTER and d["node_class"] == CODEX_REASONING_NODE_CLASS
    assert d["locality"] == "frontier" and d["subscription_backed"] is True
    assert d["capability_descriptors"] and all("capability" in c for c in d["capability_descriptors"])
    mr = d["model_ref"]
    assert mr["requested"] is None and mr["resolved_slug"] is None
    assert mr["is_fallback"] is True and mr["verified"] is False
    assert "fallback" in mr["note"].lower()
    # the resolver is the single source of the slug/note the descriptor surfaces
    slug, note = resolve_codex_model_ref(None)
    assert mr["resolved_slug"] == slug and mr["note"] == note


def test_roster_descriptor_surfaces_requested_slug_unverified() -> None:
    """A requested operator label is carried verbatim, marked NOT a fallback and NOT yet verified
    (accepted-id only confirmed by a live smoke) — no fabricated CLI slug."""
    d = codex_roster_descriptor("coding", "5.5 Sol")
    assert d["node_class"] == CODEX_CODING_NODE_CLASS
    mr = d["model_ref"]
    assert mr["requested"] == "5.5 Sol" and mr["resolved_slug"] == "5.5 Sol"
    assert mr["is_fallback"] is False and mr["verified"] is False
    assert "unverified" in mr["note"].lower()


def test_roster_descriptor_unknown_role_refused() -> None:
    with pytest.raises(ValueError):
        codex_roster_descriptor("overseer", None)


def test_roster_descriptor_capabilities_are_independent_copies() -> None:
    """Mutating a returned descriptor's nested requirements must not write back into the shared
    module-level constants (immutability hygiene)."""
    d1 = codex_roster_descriptor("reasoning", None)
    d1["capability_descriptors"][0]["requirements"]["min_context"] = 1
    d2 = codex_roster_descriptor("reasoning", None)
    assert d2["capability_descriptors"][0]["requirements"]["min_context"] != 1


def test_live_smoke_outcome_surfaces_model_resolution_even_on_skip(tmp_path) -> None:
    """A skip-with-record outcome (unconfirmed operator terms) STILL surfaces the model resolution,
    so which model / CLI-default fallback would have run is never silent (directive §11 15C)."""
    import json
    from control_plane.profiles.live_authorization import load_live_authorization
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps({"config_version": "1.1", "live_operation_authorized": True,
                               "register_row": "OP-6",
                               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                                         "terminals_per_subscription": 2}}), encoding="utf-8")
    auth = load_live_authorization(path=cfg)
    gov = SubscriptionGovernor()
    outcome = attempt_codex_live_smoke(
        objective_entry_id="e1", task_id="t1", mcp_client=object(), governor=gov,
        subscription_ref="codex-sub", node_id="n1", permission_profile_id="pp", live_auth=auth,
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, model=None, backend=MockCodexCliBackend())
    assert outcome.ran is False and outcome.skipped_with_record is True  # no live call
    assert outcome.model_resolution is not None                          # never silent
    assert outcome.model_resolution["model_ref"]["is_fallback"] is True
    assert gov.active_count("codex-sub") == 0                            # no leaked terminal


def test_generate_never_inherits_the_parent_stdin(monkeypatch) -> None:
    """Parity with `ClaudeCliBackend` (validator R6 — the claude fix shipped tested, this one did
    not, and an untested parity change is the kind that silently reverts).

    A CLI that reads piped stdin blocks forever on a supervisor's never-EOF stdin; the prompt
    travels in argv, so handing the child a closed stdin loses nothing.
    """
    import subprocess

    from adapters.frontier import codex as mod

    seen: dict[str, object] = {}

    def _fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 1.0.0", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    # (a) the PROBE transport (`CodexCli._run`) - version/auth checks
    probe = mod.CodexCli()
    probe.executable = "codex"            # it refuses before spawning when unset
    probe._run(["--version"])             # noqa: SLF001 - the shared transport for every probe
    assert seen.get("stdin") is subprocess.DEVNULL, (
        "the codex probe inherited the parent stdin and can block forever waiting on it")

    # (b) the LIVE call path (`CodexCliBackend.generate`)
    seen.clear()
    backend = CodexCliBackend()
    backend.executable = "codex"
    try:
        backend.generate("hello")
    except Exception:                     # the fake stdout is not the CLI's real envelope
        pass
    assert seen.get("stdin") is subprocess.DEVNULL, (
        "the codex live call inherited the parent stdin and can block forever waiting on it")


def test_a_zero_exit_that_produced_no_output_is_not_an_answer(monkeypatch) -> None:
    """W-03 / A-2. `generate()` synthesized `{"codex_exec": "empty"}` and returned it as a RESULT,
    so an invocation that produced nothing published a candidate no model ever wrote. A run with
    nothing to show is a failure to report, not an answer to publish."""
    import subprocess as sp

    from adapters.frontier import codex as mod

    monkeypatch.setattr(mod.subprocess, "run",
                        lambda cmd, **kw: sp.CompletedProcess(cmd, 0, stdout="", stderr=""))
    backend = mod.CodexCliBackend()
    backend.executable = "codex"
    with pytest.raises(RuntimeError) as exc:
        backend.generate("hello")
    assert "codex_exec" not in str(exc.value), (
        "the fabricated empty-envelope must not survive as the reported detail")


def test_ordinary_codex_output_is_still_returned_unchanged(monkeypatch) -> None:
    """The positive control for the above: a real answer is still an answer."""
    import subprocess as sp

    from adapters.frontier import codex as mod

    monkeypatch.setattr(mod.subprocess, "run",
                        lambda cmd, **kw: sp.CompletedProcess(cmd, 0, stdout="  a real answer  ",
                                                              stderr=""))
    backend = mod.CodexCliBackend()
    backend.executable = "codex"
    assert backend.generate("hello") == "a real answer"


# ---- W-48 (A-6): a successful answer that DISCUSSES a rate limit is not one ------------------
# `generate()` scanned the whole of a ZERO-EXIT stdout for the auth/credit/rate markers, so any
# answer whose subject happened to be rate limiting, quotas, HTTP 429, login redirects or API keys
# raised `CodexAuthError`. That is a NODE-WIDE pause (Plan 18.4), not a task-level failure -- so
# asking the model how to rate-limit an endpoint took the node down. Five measured before repair.

ANSWERS_THAT_MERELY_DISCUSS = [
    "To protect the endpoint you should apply a rate limit of 100 requests per minute.",
    "The quota system should reject writes once the tenant exceeds its usage limit.",
    "Handle HTTP 429 by backing off exponentially; do not retry immediately.",
    "If the user is not logged in, redirect them to the sign-in page.",
    "Check for an invalid api key before calling the upstream service.",
    "Document the usage limit in the README so callers know the quota.",
]

ERROR_REPORTS = [
    "error: rate limit exceeded",
    "Error: you are not authenticated",
    "not logged in",
    "codex: usage limit reached for this account",
    "fatal: invalid api key",
]


def _codex_stdout(monkeypatch, text, rc=0):
    backend = CodexCliBackend(executable="codex")
    backend._LIVE_SPAWN_PATH_WIRED = True
    monkeypatch.setattr(subprocess, "run",
                        lambda _c, **_k: subprocess.CompletedProcess(_c, rc, stdout=text + chr(10), stderr=""))
    return backend


@pytest.mark.parametrize("answer", ANSWERS_THAT_MERELY_DISCUSS)
def test_a_successful_answer_discussing_limits_does_NOT_pause_the_node(answer, monkeypatch) -> None:
    """A-6. rc == 0 is STRUCTURED evidence the call succeeded, and this tier ruling is that
    structured evidence outranks prose. The answer is returned unchanged."""
    backend = _codex_stdout(monkeypatch, answer)
    assert backend.generate("how should I protect this endpoint?") == answer


@pytest.mark.parametrize("report", ERROR_REPORTS)
def test_a_zero_exit_ERROR_REPORT_still_pauses_the_node(report, monkeypatch) -> None:
    """The other direction, and the reason this is a shape rule rather than a deletion of the
    branch: an auth condition really can surface on a zero exit, and it must still pause. Without
    this leg the unit would be satisfied by removing the check altogether."""
    backend = _codex_stdout(monkeypatch, report)
    with pytest.raises(CodexAuthError):
        backend.generate("q")


def test_the_NONZERO_exit_path_still_reads_the_marker_anywhere(monkeypatch) -> None:
    """The non-zero path is unchanged and must stay that way: there the CLI has already said the
    call FAILED, and the only question left is why -- so a marker anywhere in the text is the right
    evidence. Pinned so the two paths cannot be collapsed into one rule later."""
    backend = _codex_stdout(monkeypatch, "something went wrong: rate limit exceeded", rc=1)
    with pytest.raises(CodexAuthError):
        backend.generate("q")


def test_an_answer_that_merely_MENTIONS_an_error_prefix_is_not_a_report(monkeypatch) -> None:
    """The prefix must open the LINE. An answer explaining what an error message looks like is
    still an answer."""
    answer = "When the call fails the CLI prints error: rate limit exceeded on stderr."
    backend = _codex_stdout(monkeypatch, answer)
    assert backend.generate("what does it print?") == answer


def test_W50_a_codex_auth_failure_on_STDOUT_pauses_even_with_stderr_noise(monkeypatch) -> None:
    """W-50 (R-24) on the SECOND live `generate`. This path classified `stderr or stdout`, so an
    auth failure reported on stdout with any ordinary stderr noise picked the stream WITHOUT the
    marker and raised RuntimeError -- the node was never paused. Measured before repair.

    Included in W-50 rather than left for a later unit because acceptance 1 ("a stdout-only auth
    failure pauses") is a property of the SYSTEM, and this build has two live generate paths."""
    backend = _codex_stdout(monkeypatch, "", rc=1)
    monkeypatch.setattr(
        subprocess, "run",
        lambda _c, **_k: subprocess.CompletedProcess(
            _c, 1, stdout="Error: not authenticated. Please run codex login.",
            stderr="warning: config file not found"))
    with pytest.raises(CodexAuthError):
        backend.generate("q")


def test_W50_an_ordinary_codex_failure_is_still_not_a_pause(monkeypatch) -> None:
    backend = _codex_stdout(monkeypatch, "", rc=1)
    monkeypatch.setattr(
        subprocess, "run",
        lambda _c, **_k: subprocess.CompletedProcess(_c, 1, stdout="boom", stderr="segfault"))
    with pytest.raises(RuntimeError) as exc:
        backend.generate("q")
    assert not isinstance(exc.value, CodexAuthError)
