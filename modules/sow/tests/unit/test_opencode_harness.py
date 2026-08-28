"""Phase 14C `.harness` (unit): the OpenCode coding harness + supervised presence/version gate.

Deterministic, no-subprocess proofs. The two load-bearing invariants are:
  - §2.2/§2.3 — the real harness's child env carries NO provider credential and the run command
    is pinned to a local `ollama/*` model, so a driven session can neither transmit a secret nor
    reach a paid/cloud backend.
  - invariant 2 — a harness is spawnable only with a supervisor-issued identity (no naked session).
`OpenCodeCliHarness.version()` (which would spawn `opencode`) is NEVER called here; only its pure
builders are tested. The live presence/version probe is in the integration suite.
"""
from __future__ import annotations

import os

import pytest

from adapters.base.contract import NakedLaunchRefused
from adapters.coding.opencode.harness import (
    MIN_OPENCODE_VERSION,
    OPENCODE_HARNESS_CLASS,
    ModelNotLocal,
    MockOpenCodeHarness,
    OpenCodeCliHarness,
    OpenCodeUnavailable,
    OpenCodeVersionError,
    coding_capability_descriptors,
    local_model_ref,
    parse_semver,
)
from node_runtime.supervisor.opencode_spawn import (
    SupervisedOpenCode,
    probe_opencode,
    spawn_opencode_harness,
)

_MODELS = ["nomic-embed-text:latest", "devstral-small-2:latest", "qwen3:14b"]


# ---- version parsing: fail closed on garbage ----------------------------------------------

def test_parse_semver_extracts_first_triple() -> None:
    assert parse_semver("1.17.13") == (1, 17, 13)
    assert parse_semver("opencode 0.99.0-mock\n") == (0, 99, 0)


def test_parse_semver_raises_on_unparseable() -> None:
    with pytest.raises(OpenCodeVersionError):
        parse_semver("not-a-version")
    with pytest.raises(OpenCodeVersionError):
        parse_semver("")


# ---- mock harness: deterministic, spawns nothing ------------------------------------------

def test_mock_harness_is_deterministic_and_spawns_nothing() -> None:
    h = MockOpenCodeHarness()
    assert h.version() == h.version()  # stable
    assert h.calls == 2
    r1 = h.run("edit foo", model="ollama/devstral-small-2:latest")
    r2 = h.run("edit foo", model="ollama/devstral-small-2:latest")
    assert r1 == r2 and r1["ok"] is True


# ---- CREDENTIAL (§2.2) + PAID-PATH (§2.3): the real harness leaks no secret, reaches no cloud

def test_real_harness_env_scrubs_all_provider_credentials() -> None:
    base = {
        "PATH": os.environ.get("PATH", ""), "HOME": "/home/x", "TEMP": "/tmp",
        "LANG": "en_US.UTF-8", "OLLAMA_HOST": "http://127.0.0.1:11434",  # local — must survive
        "OPENAI_API_KEY": "sk-openai", "ANTHROPIC_API_KEY": "sk-anthropic",
        "OPENROUTER_API_KEY": "or-key", "GROQ_API_KEY": "groq-key", "GEMINI_API_KEY": "gem",
        "MISTRAL_API_KEY": "mistral", "DEEPSEEK_API_KEY": "deep", "XAI_API_KEY": "xai",
        "AWS_SECRET_ACCESS_KEY": "aws-secret", "OPENCODE_API_KEY": "oc-key",
        "SOME_FUTURE_API_KEY": "future", "VENDOR_TOKEN": "vtok",  # caught by substring rule
    }
    env = OpenCodeCliHarness(executable="opencode").build_env(base)
    for stripped in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY",
                     "GEMINI_API_KEY", "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
                     "AWS_SECRET_ACCESS_KEY", "OPENCODE_API_KEY", "SOME_FUTURE_API_KEY",
                     "VENDOR_TOKEN"):
        assert stripped not in env, stripped
    for kept in ("PATH", "HOME", "TEMP", "LANG", "OLLAMA_HOST"):  # local + non-secret survive
        assert kept in env, kept
    joined = "".join(env.values())
    for secret in ("sk-openai", "sk-anthropic", "or-key", "groq-key", "mistral", "aws-secret",
                   "oc-key", "future", "vtok"):
        assert secret not in joined, secret


def test_real_harness_run_command_pins_local_model_and_no_auth_flags() -> None:
    cmd = OpenCodeCliHarness(executable="opencode").build_run_command(
        "refactor the parser", model="ollama/devstral-small-2:latest", cwd="/w")
    assert cmd[:2] == ["opencode", "run"]
    assert "-m" in cmd and "ollama/devstral-small-2:latest" in cmd  # local model pin
    assert "--format" in cmd and "json" in cmd
    joined = " ".join(cmd).lower()
    for forbidden in ("api-key", "api_key", "token", "--share"):
        assert forbidden not in joined


def test_version_command_is_pure() -> None:
    assert OpenCodeCliHarness(executable="opencode").build_version_command() == ["opencode", "--version"]


# ---- §2.3 the local-model pin is ENFORCED, not conventional (spec-audit MAJOR-1) ----------

def test_run_command_refuses_non_local_model() -> None:
    h = OpenCodeCliHarness(executable="opencode")
    for cloud in ("openai/gpt-4o", "anthropic/claude-3-5-sonnet", "gpt-4o", "openrouter/x"):
        with pytest.raises(ModelNotLocal):
            h.build_run_command("edit", model=cloud)
    # the mock harness enforces the same pin (contract symmetry), incl. via run()
    with pytest.raises(ModelNotLocal):
        MockOpenCodeHarness().build_run_command("edit", model="openai/gpt-4o")
    with pytest.raises(ModelNotLocal):
        MockOpenCodeHarness().run("edit", model="openai/gpt-4o")


def test_local_model_ref_prefixes_bare_name() -> None:
    assert local_model_ref("devstral-small-2:latest") == "ollama/devstral-small-2:latest"
    assert local_model_ref("ollama/qwen2.5-coder:7b") == "ollama/qwen2.5-coder:7b"  # idempotent


# ---- §2.3 a non-loopback OLLAMA_HOST is dropped (spec-audit MAJOR-2) -----------------------

def test_build_env_drops_non_loopback_ollama_host() -> None:
    h = OpenCodeCliHarness(executable="opencode")
    off_box = h.build_env({"PATH": "/x", "OLLAMA_HOST": "http://10.0.0.5:11434"})
    assert "OLLAMA_HOST" not in off_box  # off-box endpoint dropped — no remote/paid routing
    for loopback in ("http://127.0.0.1:11434", "localhost:11434", "http://[::1]:11434"):
        kept = h.build_env({"PATH": "/x", "OLLAMA_HOST": loopback})
        assert kept["OLLAMA_HOST"] == loopback  # loopback preserved so the local daemon is reached


# ---- §2.2 the scrub catches a bare `<VENDOR>_KEY` (spec-audit MINOR-2 / R1) ----------------

def test_credential_scrub_catches_bare_key_and_auth_suffixes() -> None:
    h = OpenCodeCliHarness(executable="opencode")
    base = {"PATH": "/x", "VERTEX_AI_KEY": "vk", "PERPLEXITY_KEY": "pk",
            "LITELLM_MASTER_KEY": "lk", "SOME_VENDOR_AUTH": "va", "X_CREDENTIAL": "xc"}
    env = h.build_env(base)
    for stripped in ("VERTEX_AI_KEY", "PERPLEXITY_KEY", "LITELLM_MASTER_KEY",
                     "SOME_VENDOR_AUTH", "X_CREDENTIAL"):
        assert stripped not in env, stripped
    assert "PATH" in env


# ---- probe: presence/version evidence the gate acts on ------------------------------------

def test_probe_reports_present_meets_minimum_and_coder_model() -> None:
    probe = probe_opencode(MockOpenCodeHarness(version="1.17.13"), available_models=_MODELS)
    assert probe.present is True and probe.meets_minimum is True
    assert probe.version_tuple == (1, 17, 13)
    assert probe.coder_model == "devstral-small-2:latest"  # picked from available local models


def test_probe_flags_below_minimum() -> None:
    probe = probe_opencode(MockOpenCodeHarness(version="0.0.1"), available_models=_MODELS)
    assert probe.present is True and probe.meets_minimum is False
    assert probe.version_tuple == (0, 0, 1) and probe.version_tuple < MIN_OPENCODE_VERSION


def test_probe_flags_unparseable_version() -> None:
    probe = probe_opencode(MockOpenCodeHarness(version="dev-build"), available_models=_MODELS)
    assert probe.present is True and probe.version_tuple is None and probe.meets_minimum is False


def test_probe_reports_absent_when_cli_missing() -> None:
    class _Absent:
        name = "opencode:cli"
        executable = None

        def version(self) -> str:
            raise OpenCodeUnavailable("not on PATH")

    probe = probe_opencode(_Absent(), available_models=_MODELS)
    assert probe.present is False and probe.meets_minimum is False and probe.coder_model is None


# ---- supervised spawn gate: fail closed on every missing precondition ----------------------

def _spawn(**over):
    kw = dict(mcp_client=object(), node_id="oc-1", permission_profile_id="pp-coding",
              workspace_root="/w", harness=MockOpenCodeHarness(version="1.17.13"),
              available_models=_MODELS)
    kw.update(over)
    return spawn_opencode_harness(**kw)


def test_spawn_issues_supervised_identity() -> None:
    sup = _spawn()
    assert isinstance(sup, SupervisedOpenCode)
    assert sup.context.spawned_by_supervisor is True
    assert sup.context.subscription_ref is None  # local: not subscription-bounded (no I-X3)
    assert sup.probe.present and sup.probe.meets_minimum
    assert sup.probe.coder_model == "devstral-small-2:latest"


def test_spawn_refuses_absent_cli() -> None:
    class _Absent:
        name = "opencode:cli"
        executable = None

        def version(self) -> str:
            raise OpenCodeUnavailable("not on PATH")

    with pytest.raises(OpenCodeUnavailable):
        _spawn(harness=_Absent())


def test_spawn_refuses_below_min_version() -> None:
    with pytest.raises(OpenCodeVersionError):
        _spawn(harness=MockOpenCodeHarness(version="0.0.1"))


def test_spawn_refuses_naked_no_permission_profile() -> None:
    with pytest.raises(NakedLaunchRefused):
        _spawn(permission_profile_id="")


def test_spawn_refuses_naked_no_node_identity() -> None:
    with pytest.raises(NakedLaunchRefused):
        _spawn(node_id="")


def test_spawn_refuses_when_no_local_coder_model() -> None:
    """A coding harness with no local model to drive is refused fail-closed (§2.3) — else a later
    drive would be tempted toward a non-local fallback."""
    with pytest.raises(OpenCodeUnavailable):
        _spawn(available_models=[])  # opencode present + version ok, but no coder model


def test_spawn_allows_no_coder_model_only_with_explicit_override() -> None:
    sup = _spawn(available_models=[], require_coder_model=False)  # explicit mock-drive opt-in
    assert sup.context.spawned_by_supervisor is True and sup.probe.coder_model is None


# ---- version probe fails closed on a hung CLI (spec-audit MINOR-1) -------------------------

def test_version_fails_closed_on_timeout(monkeypatch) -> None:
    import subprocess

    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="opencode --version", timeout=1)

    monkeypatch.setattr(subprocess, "run", _hang)
    with pytest.raises(OpenCodeUnavailable):
        OpenCodeCliHarness(executable="opencode").version()


# ---- capability descriptor advertises the coding_tui harness_class (Phase 6 F1 closed) -----

def test_coding_descriptor_advertises_harness_class() -> None:
    descs = coding_capability_descriptors()
    assert descs[0]["capability"] == "coding"
    assert descs[0]["requirements"]["harness_class"] == OPENCODE_HARNESS_CLASS == "coding_tui"
