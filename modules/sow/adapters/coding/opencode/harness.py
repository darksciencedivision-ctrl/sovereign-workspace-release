"""First LIVE local coding harness — OpenCode (Phase 14C `.harness`).

Phase 6 stood up a `coding_node` roster entry but recorded (spec-audit F1) that it was a
*direct* local coder (single-shot Ollama `generate`), NOT a driven coding-TUI harness, and so
advertised **no** `harness_class`. Phase 14C closes exactly that gap: it proves OpenCode
*itself* is driven as a first-class coding harness (invariant 23 — coding harnesses
interchangeable behind one contract), spawned by the Node Runtime supervisor.

This module is the OpenCode side of that contract. It is deliberately small and, like the
frontier backend (`adapters/frontier/claude_code.py`), splits into:
  - `MockOpenCodeHarness` — deterministic, spawns nothing; the mock-first proof of the whole
    supervised/gated path uses it.
  - `OpenCodeCliHarness` — the REAL harness that invokes the host's `opencode` CLI. Its
    `version()` spawns `opencode --version` (a benign, local, credential-free probe); its
    `build_run_command`/`build_env` are pure and separately testable so the two load-bearing
    safety properties are proven WITHOUT a heavy drive:
      * **§2.2 — no credential handling.** `build_env` scrubs every provider credential/API-key
        var from the child environment, so a driven OpenCode session cannot transmit a secret.
        The one exception is the workspace's OWN loopback router key, which is kept only while the
        endpoint it authenticates to resolves to loopback (see `_LOCAL_ENDPOINT_ENV_KEYS`).
      * **§2.3 — no paid services.** The sovereignty guarantee is ENFORCED, not conventional:
        `build_run_command` fail-closed refuses any model that is not a local
        `sovereign-llamacpp/*` ref (`ModelNotLocal`), and `build_env` scrubs every cloud provider
        key AND drops any endpoint override that is not loopback (which would route a "local"
        model to a remote/paid endpoint). With no reachable cloud key and a loopback-pinned local
        model, the supervised llama.cpp router is the only model path left.

OpenCode + the local llama.cpp router are LOCAL (no subscription, no cloud credential), so — unlike
the frontier path — this harness is NOT subject to `LIVE_OPERATION_AUTHORIZED` (that gate is
frontier-only, directive §10.1) and NOT counted by the `SubscriptionGovernor` (local terminals are
never subscription-bounded; see subscription_governor.py). §10.2 authorized downloading the OpenCode
binary; on this host it is already present, so NO download is performed this session (recorded in
evidence). The supervised spawn gate + presence/version gate live in
node_runtime/supervisor/opencode_spawn.py.

The actual code-editing drive (scoped MCP context → isolated worktree edit → tests → CANDIDATE
→ controlled merge) is the `.worktree`/`.gate` sub-steps; this `.harness` sub-step delivers the
harness contract, the presence/version gate, and the supervised spawn.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from adapters.cmd_shim import assert_cmd_shim_argv_safe

# The harness id — must equal the roster `harness` / capability `harness_class` value so a
# coding_tui task can only match a node that really drives OpenCode (Phase 6 F1).
OPENCODE_HARNESS = "opencode"
OPENCODE_HARNESS_CLASS = "coding_tui"

# Minimum acceptable version: proves a parseable, real release rather than pinning a brittle
# exact version. The gate's job is presence + a real, parseable version, not a specific build.
MIN_OPENCODE_VERSION: tuple[int, int, int] = (0, 1, 0)

# Coder-model preferences for the driven harness, in llama.cpp router id form (first detected
# wins). Names live here, never in the control plane. Includes the coder families plus devstral
# (Mistral's coding model) and codestral, so a real coder is found on a host that carries one;
# the qwen3 chat tiers follow so a harness with no coder model still has a local model to drive.
OPENCODE_CODER_MODELS: tuple[str, ...] = (
    "qwen3-coder-30b", "qwen2-5-coder-32b", "qwen2-5-coder-3b-instruct",
    "qwen3-coder-next-latest", "devstral-small-2-latest", "codestral-latest",
    "qwen3-8b", "qwen3-14b",
)

# Provider credential / API-key env vars OpenCode consults for cloud backends. Scrubbed from the
# child env (defence-in-depth §2.2) AND to remove every paid path (§2.3): with these gone and the
# model pinned to the local provider, the supervised loopback router is the only reachable backend.
# Exact documented keys…
_CREDENTIAL_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY", "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
    "AZURE_API_KEY", "OPENCODE_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS",
)
# …plus a fail-closed superset so a NEW provider var (a future OpenCode release, another vendor)
# is scrubbed by default rather than transmitted. The substring net includes a bare `KEY`/`AUTH`/
# `CREDENTIAL` catch (not only `API_KEY`) so a `<VENDOR>_KEY`-style secret does not survive —
# closing, for this adapter, the bare-`_KEY` gap recorded as U29 on the frontier adapter.
_CREDENTIAL_KEY_PREFIXES: tuple[str, ...] = (
    "OPENAI_", "ANTHROPIC_", "OPENROUTER_", "GROQ_", "GEMINI_", "GOOGLE_", "MISTRAL_",
    "DEEPSEEK_", "XAI_", "AZURE_", "AWS_", "CLAUDE_CODE_", "OPENCODE_",
)
_CREDENTIAL_KEY_SUBSTRINGS: tuple[str, ...] = (
    "TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "KEY", "AUTH", "CREDENTIAL",
)

# The one local model provider OpenCode is pinned to.  It is the loopback llama.cpp provider the
# workspace declares for OpenCode, and the pin is what makes an OpenCode pane unable to spend.
_LOCAL_MODEL_PREFIX = "sovereign-llamacpp/"
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")

#: The workspace's OWN local-endpoint variables. `SOVEREIGN_LLAMA_CPP_API_KEY` is a loopback router
#: key, not a cloud credential — but it matches the `API_KEY` substring, and OpenCode reads exactly
#: this name out of its provider config (`apiKey: {env:SOVEREIGN_LLAMA_CPP_API_KEY}`). Scrubbing it
#: leaves a correctly-pinned pane unable to authenticate to the workspace's own server, so it is
#: preserved by name ONLY, and only while the endpoint it guards is loopback (see `build_env`).
#: An attacker who could set this variable could also set the endpoint; neither reaches anything off
#: this machine, which is the property §2.2 and §2.3 are actually protecting.
_LOCAL_ROUTER_KEY_ENV = "SOVEREIGN_LLAMA_CPP_API_KEY"
_LOCAL_ENDPOINT_ENV_KEYS: frozenset[str] = frozenset({_LOCAL_ROUTER_KEY_ENV})
#: Every endpoint-bearing var the loopback test is run over. A non-loopback value here is dropped
#: outright, and dropping it takes its key with it.
_ENDPOINT_ENV_KEYS: tuple[str, ...] = (
    "SOVEREIGN_LLAMACPP_HOST", "SOVEREIGN_LLAMA_CPP_BASE_URL",
)

_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class OpenCodeUnavailable(Exception):
    """The `opencode` CLI is not present/spawnable on the host — fail closed, no spawn."""


class OpenCodeVersionError(Exception):
    """The `opencode` version could not be parsed, or is below the minimum — fail closed."""


class ModelNotLocal(Exception):
    """A non-local (cloud/paid) model was handed to the OpenCode drive command — fail closed
    (§2.3). Only `sovereign-llamacpp/*` refs are permitted; the sovereignty pin is enforced, not
    conventional."""


def local_model_ref(model_name: str) -> str:
    """Bridge a bare coder-model name (as the probe reports it) to the enforced local pin
    `sovereign-llamacpp/<name>`. Idempotent if already prefixed."""
    name = (model_name or "").strip()
    return name if name.startswith(_LOCAL_MODEL_PREFIX) else f"{_LOCAL_MODEL_PREFIX}{name}"


def _require_local_model(model: str) -> None:
    """§2.3 fail-closed pin, enforced at the command-build site (Buildout Directive §4 —
    deterministic gate, never caller convention). Refuses any non-`sovereign-llamacpp/*` model."""
    if not (model or "").startswith(_LOCAL_MODEL_PREFIX):
        raise ModelNotLocal(
            f"model {model!r} is not a local {_LOCAL_MODEL_PREFIX}* ref — refuse to build a "
            f"non-local (paid/cloud) OpenCode command (§2.3, fail closed)")


def _is_loopback_endpoint(value: str) -> bool:
    """True iff a model-endpoint value resolves to a loopback host. A non-loopback value would send
    the "local" model off-box (potentially to a paid/hosted endpoint) — so it is dropped (§2.3)."""
    v = (value or "").strip()
    if not v:
        return True  # empty ⇒ the client uses its own loopback default — harmless
    if "://" not in v:
        v = "http://" + v
    host = (urlparse(v).hostname or "").lower()
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def _opencode_run_argv(executable: str, prompt: str, *, model: str, workdir: str | None,
                       auto: bool, pure: bool) -> list[str]:
    """Assemble the `opencode run` argv shared by the mock and real harness. Callers have already
    enforced the local-model pin (`_require_local_model`); this is pure string assembly. Flag order
    matches OpenCode's parser: global-ish flags before `-m/--format`, the prompt last (positional)."""
    argv: list[str] = [executable, "run"]
    if pure:
        argv.append("--pure")
    if auto:
        argv.append("--auto")
    if workdir:
        argv += ["--dir", str(workdir)]
    argv += ["-m", model, "--format", "json", prompt]
    assert_cmd_shim_argv_safe(argv)
    return argv


def parse_semver(text: str) -> tuple[int, int, int]:
    """Extract the first `MAJOR.MINOR.PATCH` triple from `text`. Raises OpenCodeVersionError if
    none is present (so an unparseable/garbage version fails the gate closed, never passes)."""
    m = _SEMVER_RE.search(text or "")
    if not m:
        raise OpenCodeVersionError(f"no semantic version found in {text!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


@runtime_checkable
class CodingHarness(Protocol):
    """The minimal harness contract the supervisor's presence/version gate needs. Concrete
    harnesses (OpenCode now; Aider/Codex later) satisfy it so the gate is harness-agnostic."""

    name: str

    def version(self) -> str: ...


@dataclass(frozen=True)
class HarnessProbe:
    """Result of probing a coding harness — the observable evidence the gate acts on."""

    present: bool
    version: str | None
    version_tuple: tuple[int, int, int] | None
    meets_minimum: bool
    executable: str | None
    coder_model: str | None
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "present": self.present, "version": self.version,
            "version_tuple": list(self.version_tuple) if self.version_tuple else None,
            "meets_minimum": self.meets_minimum, "executable": self.executable,
            "coder_model": self.coder_model, "detail": self.detail,
        }


class MockOpenCodeHarness:
    """Deterministic stand-in for the `opencode` CLI — spawns nothing, replayable (build §2.4
    substitution). Reports a parseable, clearly-mock version so the mock-first proof exercises
    the SAME presence/version gate the real harness does."""

    def __init__(self, name: str = "opencode:mock", version: str = "0.99.0-mock") -> None:
        self.name = name
        self._version = version
        self.calls = 0

    def version(self) -> str:
        self.calls += 1
        return self._version

    def build_run_command(self, prompt: str, *, model: str, cwd: str | None = None,
                          workdir: str | None = None, auto: bool = False,
                          pure: bool = False) -> list[str]:
        _require_local_model(model)  # same §2.3 pin as the real harness (contract symmetry)
        return _opencode_run_argv("opencode", prompt, model=model, workdir=workdir,
                                  auto=auto, pure=pure)

    def run(self, prompt: str, *, model: str, cwd: str | None = None) -> dict[str, object]:
        """Deterministic mock drive result (no subprocess). The real edit/test loop is `.worktree`."""
        self.build_run_command(prompt, model=model, cwd=cwd)  # enforce the local-model pin
        h = hashlib.sha256(f"{model}:{prompt}".encode("utf-8")).hexdigest()[:12]
        return {"ok": True, "model": model, "summary": f"[{self.name}] deterministic drive (h={h})"}


class OpenCodeCliHarness:
    """Real harness: invokes the host's `opencode` CLI. `version()` spawns `opencode --version`
    (benign, local, credential-free). The heavy `run` drive is added in `.worktree`; here the
    pure `build_run_command`/`build_env` builders are what carry — and let us prove — the §2.2 /
    §2.3 safety properties without a spawn."""

    def __init__(self, executable: str | None = None, *, timeout_s: float = 60.0) -> None:
        # Resolve the real path (Windows shims are `opencode.CMD`; shutil.which honours PATHEXT).
        self.executable = executable if executable is not None else (
            shutil.which("opencode") or shutil.which("opencode.cmd") or shutil.which("opencode.ps1"))
        self.name = "opencode:cli"
        self._timeout_s = timeout_s

    def build_version_command(self) -> list[str]:
        return [self.executable or "opencode", "--version"]

    def build_run_command(self, prompt: str, *, model: str, cwd: str | None = None,
                          workdir: str | None = None, auto: bool = False,
                          pure: bool = False) -> list[str]:
        """Non-interactive drive: `opencode run [--pure] [--auto] [--dir <workdir>] -m
        sovereign-llamacpp/<model> --format json <prompt>`. The model MUST be a local
        `sovereign-llamacpp/*` ref (sovereignty, §2.3) — enforced fail-closed by
        `_require_local_model`, NOT left to caller convention; no `--api-key`, no share/plugin flags
        that would carry auth or reach a network service. `workdir` (`--dir`) scopes the driven
        session to the node's own worktree (Phase 10 isolation, `.worktree`); `auto` (`--auto`) lets
        a headless edit land without an interactive approval prompt; `pure` (`--pure`) runs without
        external plugins."""
        _require_local_model(model)
        return _opencode_run_argv(self.executable or "opencode", prompt, model=model,
                                  workdir=workdir, auto=auto, pure=pure)

    @staticmethod
    def _is_credential_key(name: str) -> bool:
        up = name.upper()
        if up in _CREDENTIAL_ENV_KEYS:
            return True
        if up.startswith(_CREDENTIAL_KEY_PREFIXES):
            return True
        return any(tok in up for tok in _CREDENTIAL_KEY_SUBSTRINGS)

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Child environment with every provider credential/API-key var REMOVED. With these gone
        and the model pinned to the loopback llama.cpp provider, OpenCode has no reachable
        paid/cloud backend (§2.3) and can transmit no secret (§2.2) — the supervised local router is
        the only path left.

        THREE things this has to get right at once, and the third is the one that bit this host:

        * the cloud nets stay as wide as they are (prefixes, and the bare `KEY`/`AUTH`/`TOKEN`…
          substrings that close U29 for a `<VENDOR>_KEY` nobody thought to list);
        * an endpoint override that is not loopback is DROPPED, because it would route a "local"
          model off-box to a hosted endpoint (§2.3);
        * the workspace's OWN router vars survive. `SOVEREIGN_LLAMA_CPP_API_KEY` is a loopback
          router key, but it matches the `API_KEY` substring — and OpenCode's local provider reads
          it out of its config (`apiKey: {env:SOVEREIGN_LLAMA_CPP_API_KEY}`). Scrubbing it is what
          made a correctly-pinned pane fail with an auth error against 127.0.0.1: it was never a
          cloud credential, it is the price of admission to a process the launcher started on this
          machine. It is therefore kept ONLY while the endpoint it authenticates to is loopback;
          point `SOVEREIGN_LLAMA_CPP_BASE_URL` off-box and both the URL and its key go, and the
          client falls back to its loopback default. `OLLAMA_HOST` is dropped outright: an OpenCode
          pane has no Ollama path to keep.
        """
        env = dict(os.environ if base_env is None else base_env)
        endpoint_loopback = all(_is_loopback_endpoint(env.get(name, ""))
                                for name in _ENDPOINT_ENV_KEYS)
        for key in [k for k in env if self._is_credential_key(k)]:
            if endpoint_loopback and key.upper() in _LOCAL_ENDPOINT_ENV_KEYS:
                continue  # local router admission, not a cloud credential (§2.2 note above)
            env.pop(key, None)
        for name in _ENDPOINT_ENV_KEYS:
            if not _is_loopback_endpoint(env.get(name, "")):
                env.pop(name, None)      # off-box endpoint ⇒ drop, and its key with it
        env.pop("OLLAMA_HOST", None)     # no Ollama path exists for this harness to preserve
        return env

    def version(self) -> str:
        """Spawn `opencode --version` and return its trimmed output. Raises OpenCodeUnavailable if
        the CLI is absent or cannot be spawned (fail closed). Local + credential-free — the env is
        still scrubbed as defence-in-depth."""
        import subprocess
        if not self.executable:
            raise OpenCodeUnavailable("`opencode` CLI not found on PATH — fail closed")
        try:
            proc = subprocess.run(
                self.build_version_command(), capture_output=True, text=True,
                timeout=self._timeout_s, env=self.build_env(), check=False)
        except subprocess.TimeoutExpired as exc:
            raise OpenCodeUnavailable(
                f"`opencode --version` timed out after {self._timeout_s}s — fail closed") from exc
        except (FileNotFoundError, OSError) as exc:
            raise OpenCodeUnavailable(f"cannot spawn `opencode`: {exc}") from exc
        out = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0 or not out:
            raise OpenCodeUnavailable(
                f"`opencode --version` exited {proc.returncode} with output {out[:120]!r}")
        return out


def coding_capability_descriptors(*, min_context: int = 32000) -> list[dict[str, object]]:
    """The coding capability descriptor OpenCode advertises — now WITH `harness_class` set to the
    coding_tui id (the thing Phase 6 F1 said would only be advertised once OpenCode is really
    driven). A coding_tui task matches this node; a plain single-shot coder still does not."""
    return [
        {"capability": "coding", "requirements": {"tool_use": True, "structured_output": True,
                                                  "min_context": min_context,
                                                  "harness_class": OPENCODE_HARNESS_CLASS}},
    ]


# assert the mock satisfies the harness protocol at import
_MOCK: CodingHarness = MockOpenCodeHarness()
