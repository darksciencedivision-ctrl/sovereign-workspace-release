"""OpenAI Codex CLI — detection / probe surface. Phase 15C `.detect`.

The second live frontier provider the operator authorized (register **OP-6**, directive §11
track 15C; §12 OP-7 revised order 15A→15C). This module is the `.detect` sub-step ONLY: it
proves the host `codex` CLI is present, at a parseable version, and authenticated — and it
records what the CLI structurally accepts for per-node model selection. It makes **no live
model call** (`codex exec` is never invoked here): every probe is a benign, local, credential-
free metadata call (`codex --version`, `codex login status`, `codex exec --help`).

Deliberately NOT here (owed to `.adapter` / `.gate`, kept honest):
  - the live `CodexCliBackend` behind the governed `ModelWorkerAdapter` contract;
  - the fail-closed supervised spawn path (mirrors node_runtime/supervisor/frontier_spawn.py:
    assert_startup + assert_provider_live('openai_codex_cli') + [OPERATOR] live-terms + CLI
    presence + I-X3 governor at allowance=live_auth.terminals_per_subscription);
  - the env-scrub SUPERSET applied to the child of `codex exec` (OPENAI_*/key families) and the
    node-controlled-untrusted `AGENTS.md`/`~/.codex` config pin (T2, like OpenCode's U30);
  - the one live smoke per available model.

Non-negotiables already binding at detection (directive §2.2):
  - **No credential handling, ever.** `codex login status` reports auth *state* ("Logged in
    using ChatGPT") — it does not expose the OAuth token. This module NEVER reads `~/.codex/
    auth.json`, NEVER uses `--with-api-key`/`--with-access-token`, and NEVER stores/transmits a
    credential. The token stays in the CLI's own host-native store.

Model-id honesty (directive §11 15C — "probe accepted model IDs … record what the CLI really
accepts, unavailable ⇒ recorded fallback surfaced in the roster, never silent"):
  The Codex CLI's `-m/--model` accepts an arbitrary slug that is validated only at `codex exec`
  time; there is **no offline `models list` subcommand**. So the specific accepted ids for the
  operator-named GPT-5.5 line ("5.5", "5.5 Sol") CANNOT be confirmed without a live call. This
  module therefore records them as *unverified candidates* (`verified=False`) plus the
  structural fact that the `-m/--model` selector exists; the accepted-id resolution (and any
  recorded fallback) is a `.adapter`/`.gate` live smoke — never fabricated here.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from adapters.base.backend import Backend, BackendAuthPause
from adapters.base.contract import AdapterContext
from adapters.model_adapter import ModelWorkerAdapter

# Provider id — MUST equal the frozen node.schema.json `adapter` enum member and
# control_plane/profiles/live_authorization._AUTHORIZED_PROVIDERS, so the live gate keys on it
# exactly (the operator/directive shorthand "codex" normalizes to this in live_authorization).
CODEX_ADAPTER = "openai_codex_cli"

# Minimum acceptable version: proves a parseable, real release rather than pinning a brittle exact
# build. The gate's job is presence + a real parseable version, not a specific build.
MIN_CODEX_VERSION: tuple[int, int, int] = (0, 1, 0)

_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

# stderr/stdout markers from `codex login status` meaning "authenticated". Kept specific; the
# absence of a positive marker fails closed to unauthenticated (never assume auth on silence).
# W-47 (R-05). ANCHORED per line, and it was a bare substring. `"logged in" in low` is true of
# every SIGNED-OUT sentence that names the state it is denying, and the exact-substring blacklist
# below caught only the phrasings someone thought of. Measured at rc==0: "You are no longer logged
# in", "You are not currently logged in", "You were logged in previously", "Never logged in on
# this machine", "You aren't logged in" and "Failed to check whether you are logged in" ALL
# classified as AUTHENTICATED -- six ways of saying the opposite, plus one saying the check failed.
#
# A login report is a DECLARATION, so the line must open with it (optionally after "you are" /
# "you're"). Widening the blacklist would have been chasing phrasings forever; this reads the
# shape of the sentence instead. The blacklist is kept as defence in depth, not as the gate.
_LOGGED_IN_RE = re.compile(
    r"^\s*(?:you(?:'|’)?(?:re| are)?\s+)?logged in\b", re.I | re.M)
_NOT_LOGGED_IN_MARKERS = ("not logged in", "no login", "please log in", "run `codex login`",
                          "run 'codex login'")
# Recognised auth METHODS. `login_status` records a NORMALIZED detail (state + method) rather than
# echoing the raw CLI line, because some `codex login status` builds print the account email
# ("Logged in as user@…") — PII, not a credential, but it must not land verbatim in an
# evidence-bound field (spec-audit MINOR-1). The method token is matched, the raw line discarded.
_AUTH_METHOD_MARKERS = ("chatgpt", "api key", "api-key")


class CodexUnavailable(Exception):
    """The `codex` CLI is not present/spawnable on the host — fail closed, no probe result."""


class CodexVersionError(Exception):
    """The `codex` version could not be parsed — fail closed (unparseable ⇒ does not meet min)."""


def parse_codex_version(text: str) -> tuple[int, int, int]:
    """Extract the first MAJOR.MINOR.PATCH triple (e.g. from `codex-cli 0.144.6`). Raises
    CodexVersionError if none is present, so an unparseable version fails the gate closed."""
    m = _SEMVER_RE.search(text or "")
    if not m:
        raise CodexVersionError(f"no semantic version found in {text!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


@dataclass(frozen=True)
class CandidateModelRef:
    """An operator-named model the roster MAY offer for a Codex node, and its verification state.

    `provisional_slug` is the operator's own label ("5.5", "5.5 Sol") carried verbatim — NOT a
    confirmed CLI id. `verified` stays False until a live `codex exec -m <slug>` smoke at
    `.adapter`/`.gate` confirms the CLI accepts it; an unaccepted slug becomes a recorded roster
    fallback (directive §11 15C — never silent)."""

    operator_name: str
    provisional_slug: str
    verified: bool = False
    registered: bool = True
    conductor_capable: bool = False
    worker_capable: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"operator_name": self.operator_name, "provisional_slug": self.provisional_slug,
                "verified": self.verified, "registered": self.registered,
                "conductor_capable": self.conductor_capable,
                "worker_capable": self.worker_capable, "note": self.note}


# The operator-named GPT-5.5 line (OP-6; directive §11 15C names "5.5" and "5.5 Sol"). Recorded
# as UNVERIFIED candidates: the Codex CLI has no offline model-list command, so the accepted id
# is resolved by a live smoke at `.adapter` — these are not fabricated CLI slugs.
CODEX_CANDIDATE_MODEL_REFS: tuple[CandidateModelRef, ...] = (
    CandidateModelRef(
        operator_name="ChatGPT 5.6 Sol", provisional_slug="gpt-5.6-sol", verified=True,
        conductor_capable=True,
        note="exact host-supported Codex slug registered by the operator amendment"),
    CandidateModelRef(
        operator_name="5.5", provisional_slug="5.5", verified=False,
        note="operator label; accepted `-m` slug resolved by live `codex exec` smoke at .adapter"),
    CandidateModelRef(
        operator_name="5.5 Sol", provisional_slug="5.5 Sol", verified=False,
        note="operator label; accepted `-m` slug resolved by live `codex exec` smoke at .adapter"),
)


@dataclass(frozen=True)
class CodexProbe:
    """Observable evidence the `.adapter`/`.gate` supervised spawn gate will act on. Every field is
    derived from a benign, no-model-call probe; never raises to build one (fail-closed data)."""

    present: bool
    version: str | None
    version_tuple: tuple[int, int, int] | None
    meets_minimum: bool
    executable: str | None
    authenticated: bool
    auth_detail: str
    noninteractive_exec_supported: bool
    model_flag_supported: bool
    candidate_models: tuple[CandidateModelRef, ...]
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "present": self.present, "version": self.version,
            "version_tuple": list(self.version_tuple) if self.version_tuple else None,
            "meets_minimum": self.meets_minimum, "executable": self.executable,
            "authenticated": self.authenticated, "auth_detail": self.auth_detail,
            "noninteractive_exec_supported": self.noninteractive_exec_supported,
            "model_flag_supported": self.model_flag_supported,
            "candidate_models": [c.as_dict() for c in self.candidate_models],
            "detail": self.detail,
        }


@runtime_checkable
class CodexCliProbe(Protocol):
    """The minimal probe contract `probe_codex` needs. The real CLI and the mock both satisfy it,
    so the probe logic is spawn-agnostic and deterministically testable."""

    executable: str | None

    def version(self) -> str: ...

    def login_status(self) -> tuple[bool, str]: ...

    def exec_help(self) -> str: ...


class MockCodexCli:
    """Deterministic stand-in — spawns nothing (build §2.4 substitution). Lets the probe logic be
    tested for every branch (present/authed, unparseable version, unauthenticated) with no host."""

    def __init__(self, *, version: str = "codex-cli 0.144.6", authenticated: bool = True,
                 auth_detail: str = "Logged in using ChatGPT",
                 exec_help_text: str = "Run Codex non-interactively\n  -m, --model <MODEL>\n") -> None:
        self.executable = "codex:mock"
        self._version = version
        self._authenticated = authenticated
        self._auth_detail = auth_detail
        self._exec_help = exec_help_text

    def version(self) -> str:
        return self._version

    def login_status(self) -> tuple[bool, str]:
        return self._authenticated, self._auth_detail

    def exec_help(self) -> str:
        return self._exec_help


class CodexCli:
    """Real probe: invokes the host `codex` CLI for benign metadata only. NONE of these calls run
    a model (`codex exec` is NOT here — that is `.adapter`). Each is local + credential-free:
      - `version()`      → `codex --version`
      - `login_status()` → `codex login status` (reports auth STATE, never the token)
      - `exec_help()`    → `codex exec --help` (structural: does the `-m/--model` selector exist)
    """

    def __init__(self, executable: str | None = None, *, timeout_s: float = 60.0) -> None:
        self.executable = executable if executable is not None else (
            shutil.which("codex") or shutil.which("codex.cmd")
            or shutil.which("codex.exe") or shutil.which("codex.ps1"))
        self.name = "codex:cli"
        self._timeout_s = timeout_s

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        if not self.executable:
            raise CodexUnavailable("`codex` CLI not found on PATH — fail closed")
        try:
            # stdin CLOSED (parity with `ClaudeCliBackend.generate`): an inherited non-TTY stdin
            # lets the CLI block waiting on input that never arrives, turning a probe into a timeout
            return subprocess.run([self.executable, *args], capture_output=True, text=True,
                                  timeout=self._timeout_s, check=False, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise CodexUnavailable(
                f"`codex {' '.join(args)}` timed out after {self._timeout_s}s — fail closed") from exc
        except (FileNotFoundError, OSError) as exc:
            raise CodexUnavailable(f"cannot spawn `codex`: {exc}") from exc

    def version(self) -> str:
        proc = self._run(["--version"])
        out = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0 or not out:
            raise CodexUnavailable(
                f"`codex --version` exited {proc.returncode} with output {out[:120]!r}")
        return out

    def login_status(self) -> tuple[bool, str]:
        """Return (authenticated, NORMALIZED detail) from `codex login status`. Fail-closed: any
        non-positive or ambiguous result ⇒ authenticated=False (never assume auth on silence).

        The detail is a CLASSIFIED state (+ matched auth method), NOT the raw CLI line: some builds
        print the account email, which is PII that must not enter an evidence-bound field
        (spec-audit MINOR-1). No credential is ever in the output regardless — `login status`
        reports state, not the token."""
        proc = self._run(["login", "status"])
        low = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().lower()
        authed = (proc.returncode == 0
                  and bool(_LOGGED_IN_RE.search(low))
                  and not any(m in low for m in _NOT_LOGGED_IN_MARKERS))
        if authed:
            method = next((m for m in _AUTH_METHOD_MARKERS if m in low), None)
            return True, f"logged in ({method})" if method else "logged in"
        if any(m in low for m in _NOT_LOGGED_IN_MARKERS):
            return False, "not logged in"
        return False, f"unauthenticated (login status rc={proc.returncode})"

    def exec_help(self) -> str:
        proc = self._run(["exec", "--help"])
        return (proc.stdout or proc.stderr or "")


def probe_codex(cli: CodexCliProbe | None = None) -> CodexProbe:
    """Probe the Codex CLI for the `.adapter` presence/version/auth gate. Injected `cli` is used by
    the deterministic suite; when None the real host CLI is probed. NEVER raises — every failure is
    captured in the returned probe so the caller gates on data (Buildout Directive §4, fail-closed).
    Makes NO live model call."""
    if cli is None:
        cli = CodexCli()
    executable = getattr(cli, "executable", None)

    try:
        raw = cli.version()
    except CodexUnavailable as exc:
        return CodexProbe(
            present=False, version=None, version_tuple=None, meets_minimum=False,
            executable=executable, authenticated=False, auth_detail="(cli absent)",
            noninteractive_exec_supported=False, model_flag_supported=False,
            candidate_models=CODEX_CANDIDATE_MODEL_REFS, detail=f"absent: {exc}")

    try:
        vt: tuple[int, int, int] | None = parse_codex_version(raw)
    except CodexVersionError:
        vt = None

    # auth state (fail-closed to False if the status probe cannot run)
    try:
        authed, auth_detail = cli.login_status()
    except CodexUnavailable as exc:
        authed, auth_detail = False, f"login status unavailable: {exc}"

    # structural non-interactive/model-selection support (no model call)
    try:
        help_text = cli.exec_help().lower()
    except CodexUnavailable:
        help_text = ""
    model_flag = "--model" in help_text or bool(re.search(r"(^|\s)-m\b", help_text))
    noninteractive = "non-interactive" in help_text or "run codex" in help_text

    meets = vt is not None and vt >= MIN_CODEX_VERSION
    if vt is None:
        detail = f"unparseable version: {raw!r}"
    elif not meets:
        detail = f"below minimum {MIN_CODEX_VERSION}"
    elif not authed:
        detail = "present but not authenticated"
    else:
        detail = "ok"
    return CodexProbe(
        present=True, version=raw, version_tuple=vt, meets_minimum=meets, executable=executable,
        authenticated=authed, auth_detail=auth_detail,
        noninteractive_exec_supported=noninteractive, model_flag_supported=model_flag,
        candidate_models=CODEX_CANDIDATE_MODEL_REFS, detail=detail)


# assert the mock satisfies the probe protocol at import
_MOCK: CodexCliProbe = MockCodexCli()


# ============================================================================================
# Phase 15C `.adapter` — the LIVE Codex backend behind the governed ModelWorkerAdapter contract.
#
# Mirrors adapters/frontier/claude_code.py exactly: the backend is the only new surface; the
# governance path (scoped MCP context in → node-local gate → CANDIDATE out with provenance) is
# the shared, already-governed ModelWorkerAdapter, reused verbatim. The fail-closed supervised
# spawn (LIVE_OPERATION_AUTHORIZED / I-X3 / R8 operator-terms / CLI presence) lives in the real
# startup path node_runtime/supervisor/codex_spawn.py — never here.
#
# Non-negotiables encoded here (directive §2.2 / §11 track 15C; Plan §18.3–18.4):
#   - **No credential handling, ever.** The adapter invokes the host's already-authenticated
#     `codex` CLI, which holds its ChatGPT-subscription OAuth token in a host-native store
#     (`~/.codex/auth.json`, managed by the CLI — NOT an environment variable). This code NEVER
#     reads that file, NEVER passes `--with-api-key`/`--with-access-token`, and NEVER stores or
#     transmits a credential. As defence-in-depth the child env is scrubbed of every credential/
#     endpoint var (OpenAI/Azure/other key families + a bare KEY/AUTH/TOKEN/SECRET/CREDENTIAL
#     superset — see `_is_credential_key`), so no key can be transmitted and no endpoint override
#     can redirect the call: the subscription OAuth path via the CLI's own store is the only one
#     left.
#   - **T2 — node-controlled config is untrusted (like OpenCode's U30).** `codex exec` reads
#     `AGENTS.md` from the working tree and `~/.codex/config.toml` (host-global). Containment is
#     pinned by CLI flags that take precedence over config: an explicit `--sandbox` (read-only for
#     reasoning, workspace-write for coding — NEVER `danger-full-access`), an explicit model, and
#     `--cd` scoping a coding run to the node's OWN isolated worktree (Phase 10). The dangerous
#     bypass flags are refused structurally (`_FORBIDDEN_CODEX_ARGS`). Residual host-`config.toml`
#     keys the flags do not override (e.g. declared MCP servers/hooks) are a recorded live-run item
#     (U32) — the CODEX_HOME auth dir is deliberately NOT relocated, because that would sever the
#     host OAuth the §2.2 path depends on (relocating it and copying auth.json would BE credential
#     handling).
#   - **Mock-first.** `MockCodexCliBackend` is deterministic and spawns nothing; the whole governed
#     path is proven with it. `CodexCliBackend` (the real subprocess) is NEVER used by the
#     deterministic suite — only by the opt-in, operator-gated live smoke.
#   - **Fail-closed on auth.** An expired/failed subscription surfaces as `CodexAuthError` — the
#     supervisor pauses the node (Plan §18.4); there is NO silent API-key fallback.
# ============================================================================================

# node.schema.json node_class values this adapter maps its two worker roles to.
CODEX_REASONING_NODE_CLASS = "worker_reasoning"
CODEX_CODING_NODE_CLASS = "worker_coding_specialist"

# Frontier reasoning/synthesis descriptors (a Codex reasoning worker; mirrors the claude_code shape).
CODEX_REASONING_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                 "min_context": 128000, "locality": "frontier_ok"}},
    {"capability": "synthesis", "requirements": {"structured_output": True, "min_context": 128000}},
]
# Coding-specialist descriptor (a Codex coding worker; worktree-isolated, §11 track 15C).
CODEX_CODING_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "coding", "requirements": {"tool_use": True, "structured_output": True,
                                              "min_context": 128000, "locality": "frontier_ok"}},
]

# `codex exec` argv building blocks. Kept as named constants so the exact CLI spelling is easy to
# confirm/adjust at the live smoke; the load-bearing safety (no credential/bypass flag, explicit
# sandbox) does not depend on their spelling.
CODEX_EXEC_SUBCOMMAND = "exec"
CODEX_MODEL_FLAG = "-m"
CODEX_SANDBOX_FLAG = "--sandbox"
CODEX_CD_FLAG = "--cd"
SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
_SANDBOX_DANGER = "danger-full-access"
# The two worker roles and the sandbox each is pinned to (fail-closed default; coding gets write
# ONLY inside its own worktree via --cd, reasoning is read-only).
_ROLE_SANDBOX = {"reasoning": SANDBOX_READ_ONLY, "coding": SANDBOX_WORKSPACE_WRITE}
_ROLE_NODE_CLASS = {"reasoning": CODEX_REASONING_NODE_CLASS, "coding": CODEX_CODING_NODE_CLASS}
_ROLE_DESCRIPTORS = {"reasoning": CODEX_REASONING_CAPABILITY_DESCRIPTORS,
                     "coding": CODEX_CODING_CAPABILITY_DESCRIPTORS}

# Flags/values this adapter must NEVER emit: credential-passing flags and the sandbox/approval
# bypasses. A build that would contain one fails closed (`_assert_no_forbidden`).
_FORBIDDEN_CODEX_ARGS: tuple[str, ...] = (
    "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust",
    "--with-api-key", "--with-access-token", "--api-key", _SANDBOX_DANGER, "--full-auto",
)

# Exact credential/endpoint env keys the OpenAI/Codex/Azure toolchains document. Scrubbed from the
# child env so this adapter can neither transmit a credential nor redirect the call (§2.2).
_CREDENTIAL_ENV_KEYS: tuple[str, ...] = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_ORG_ID", "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT", "OPENAI_PROJECT_ID", "CODEX_API_KEY", "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT", "AZURE_API_KEY", "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
# Name-prefix / substring families that always denote a credential, routing override, or secret —
# a fail-closed superset so a NEW provider var (a future CLI release) is scrubbed by default rather
# than transmitted. The substring net includes bare KEY/AUTH/CREDENTIAL (not only API_KEY), matching
# the OpenCode harness (which closed U29's class for that adapter). Note `CODEX_HOME` carries none of
# these substrings, so the CLI's config/auth dir pointer is preserved (the OAuth path stays intact).
_CREDENTIAL_KEY_PREFIXES: tuple[str, ...] = (
    "OPENAI_", "AZURE_", "AZURE_OPENAI_", "ANTHROPIC_", "AWS_", "GOOGLE_",
)
_CREDENTIAL_KEY_SUBSTRINGS: tuple[str, ...] = (
    "TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "KEY", "AUTH", "CREDENTIAL",
)

# stderr/stdout markers meaning "not authenticated / credit exhausted / rate limited" — a
# fail-closed PAUSE (Plan §18.4), not an ordinary task-level failure. Kept specific enough to avoid
# mislabelling a normal runtime fault as an auth pause.
#: W-48 (A-6). The shapes a CLI uses to DECLARE a failure, as opposed to an answer that discusses
#: one. Deliberately short: the point is not to enumerate error vocabulary, it is that a report
#: announces itself at the start of a line and a paragraph of prose does not.
_ERROR_PREFIX_RE = re.compile(r"^(?:error|fatal|failure|failed|codex(?:\s+exec)?)\s*[:\-]\s*")
_AUTH_FAILURE_MARKERS: tuple[str, ...] = (
    "not authenticated", "unauthenticated", "please log in", "please run `codex login`",
    "please run 'codex login'", "run codex login", "not logged in", "invalid api key",
    "session expired", "token expired", "credit balance", "usage limit", "quota", "insufficient_quota",
    "rate limit", "rate-limit", "http 401", "http 403", "http 429",
    "status 401", "status 403", "status 429", "error 429",
)


class CodexAuthError(BackendAuthPause):
    """The `codex` CLI reported an auth/credit/rate-limit condition. Fail-closed pause signal
    (Plan §18.4): the generic adapter re-raises it, the supervisor pauses the node; NO silent
    API-key fallback."""


def _assert_no_forbidden(argv: list[str]) -> None:
    """Fail-closed guard: refuse to emit any credential-passing or sandbox/approval-bypass arg.
    Deterministic permission logic (Buildout Directive §4), not caller convention."""
    lowered = [a.lower() for a in argv]
    for bad in _FORBIDDEN_CODEX_ARGS:
        if bad in lowered:
            raise ValueError(
                f"refuse to build a codex command containing {bad!r} — no credential/bypass flag "
                f"is ever permitted (§2.2 / T2, fail closed)")


def is_credential_env_key(name: str) -> bool:
    """Fail-closed classifier: True if `name` is a known credential/endpoint key, starts with a
    provider prefix, or contains a secret-token substring (§2.2 / R8 §4).

    Module-level (mirroring `claude_code.is_credential_env_key`) so every launch path scrubs by the
    ONE rule — the one-shot `codex exec` worker env (`CodexCliBackend.build_env`, which delegates
    here) AND the INTERACTIVE worker pane (Phase 17B `.ticket`, which reports the names the shell
    must drop). A second copy could drift and leave a key un-scrubbed on one path only."""
    up = name.upper()
    if up in _CREDENTIAL_ENV_KEYS:
        return True
    if up.startswith(_CREDENTIAL_KEY_PREFIXES):
        return True
    return any(tok in up for tok in _CREDENTIAL_KEY_SUBSTRINGS)


def build_interactive_codex_command(
    executable: str = "codex", *, model: str | None = None,
    sandbox: str = SANDBOX_READ_ONLY, workdir: str | None = None,
) -> list[str]:
    """Argv for an INTERACTIVE `codex` session — a worker pane the operator can watch and type into
    (Phase 17B `.ticket`; OP-7 §12.3 attended/autonomous). Distinct from `CodexCliBackend.build_command`,
    which is the one-shot `codex exec … <prompt>` headless worker mode.

    NO `exec` subcommand and NO prompt argument: the CLI opens its interactive surface. The governed
    facts the headless path pins are pinned identically here — an explicit `-m` (per-node model,
    unverified until a live smoke), an explicit `--sandbox` (never `danger-full-access`), and `--cd`
    scoping the session to the workspace it was authorized for — because a node-controlled
    `~/.codex/config.toml` must never be able to widen either (T2 containment). `workspace-write`
    without a `--cd` scope is refused, exactly as the exec path refuses it (Phase 10 / T2).

    Pure and deterministic: it builds argv only. The ConPTY spawn and the host-native OAuth
    credential stay entirely outside this function (the credential is never read/stored/transmitted).
    """
    if sandbox == _SANDBOX_DANGER:
        raise ValueError(
            f"refuse to build a codex command with sandbox {_SANDBOX_DANGER!r} — never permitted "
            f"(§2.2 / T2, fail closed)")
    scope = str(workdir).strip() if workdir and str(workdir).strip() else None
    if sandbox == SANDBOX_WORKSPACE_WRITE and not scope:
        raise ValueError(
            "codex workspace-write requires an isolated worktree (--cd) — an interactive coding "
            "session never gets unscoped write access (T2 / Phase 10, fail closed)")
    slug = model.strip() if model and model.strip() else None
    argv: list[str] = [executable]
    if slug:
        argv += [CODEX_MODEL_FLAG, slug]
    argv += [CODEX_SANDBOX_FLAG, sandbox]
    if scope:
        argv += [CODEX_CD_FLAG, scope]
    _assert_no_forbidden(argv)
    return argv


def resolve_codex_model_ref(requested: str | None) -> tuple[str | None, str]:
    """Resolve the per-node model slug for `-m`, honestly.

    The Codex CLI has no offline model-list (see `.detect`), so an operator-named candidate ("5.5",
    "5.5 Sol") is only *confirmed* by a live `codex exec -m <slug>` smoke. This returns
    `(slug_or_None, note)`: a requested slug is carried verbatim (still unverified until the smoke);
    `None` means "use the CLI default and record the fallback in the roster" — directive §11 15C
    ("unavailable ⇒ recorded fallback surfaced in the roster, never silent"). Nothing is fabricated."""
    if requested and requested.strip():
        return requested.strip(), f"per-node model {requested.strip()!r} (accepted-id unverified until live smoke)"
    return None, "no model selected — CLI default (recorded roster fallback, directive §11 15C)"


def codex_roster_descriptor(role: str = "reasoning", requested_model: str | None = None) -> dict[str, Any]:
    """Roster/capability descriptor for a live Codex node with the per-node model resolution
    SURFACED — directive §11 15C ("probe accepted model IDs … unavailable ⇒ recorded fallback
    surfaced in the roster, never silent").

    `resolve_codex_model_ref` decides the `-m` slug (carried verbatim, still unverified until a
    live smoke) or the CLI-default fallback (`resolved_slug=None`). This embeds that decision AND
    its human-readable note into a `model_ref` block on the descriptor the roster/Inspector reads,
    so the fallback is a RECORDED field of the roster surface, not merely an assumption living in a
    helper's return value. Pure/deterministic; makes no CLI call and fabricates no slug."""
    if role not in _ROLE_DESCRIPTORS:
        raise ValueError(f"unknown codex worker role {role!r} — expected reasoning|coding")
    slug, note = resolve_codex_model_ref(requested_model)
    return {
        "adapter": CODEX_ADAPTER,
        "node_class": _ROLE_NODE_CLASS[role],
        "locality": "frontier",
        "subscription_backed": True,
        # deep copy so a caller mutating a nested `requirements` dict can never write back into the
        # module-level descriptor constants (immutability hygiene; spec-audit 15C .gate NIT).
        "capability_descriptors": copy.deepcopy(_ROLE_DESCRIPTORS[role]),
        "model_ref": {
            "requested": requested_model,       # operator label as given (may be None)
            "resolved_slug": slug,              # None => CLI default (fallback)
            "verified": False,                  # accepted-id only confirmable by a live smoke
            "is_fallback": slug is None,        # True ⇒ recorded CLI-default fallback (never silent)
            "note": note,
        },
    }


class MockCodexCliBackend:
    """Deterministic stand-in for the `codex` CLI — no subprocess, replayable (build §2.4
    substitution). Shapes output like the final assistant message of `codex exec` so the mock-first
    proof exercises the exact same downstream path as the live backend."""

    def __init__(self, *, model: str | None = None, role: str = "reasoning") -> None:
        self.model = model
        self.role = role
        self.name = f"codex:mock:{model or 'default'}"
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return (f"[{self.name}] deterministic Codex result (h={h}) for prompt: {prompt[:120]}")


class CodexCliBackend:
    """Real backend: invokes the host's already-authenticated `codex` CLI as a subprocess.

    NEVER used by the deterministic suite. `generate` is only reached from the operator-gated live
    smoke (codex_spawn.attempt_codex_live_smoke) after every LIVE_OPERATION_AUTHORIZED / I-X3 /
    R8-operator-terms gate has passed. `build_command`/`build_env` are pure and separately testable
    so the credential (§2.2) and containment (T2) invariants are verified without spawning anything.
    """

    def __init__(self, executable: str | None = None, *, model: str | None = None,
                 role: str = "reasoning", workdir: str | None = None,
                 sandbox_mode: str | None = None, timeout_s: float = 180.0) -> None:
        if role not in _ROLE_SANDBOX:
            raise ValueError(f"unknown codex worker role {role!r} — expected reasoning|coding")
        self.executable = executable if executable is not None else (
            shutil.which("codex") or shutil.which("codex.cmd")
            or shutil.which("codex.exe") or shutil.which("codex.ps1") or "codex")
        self.model = (model.strip() if model and model.strip() else None)
        self.role = role
        self.workdir = workdir
        mode = sandbox_mode or _ROLE_SANDBOX[role]
        if mode == _SANDBOX_DANGER:
            raise ValueError(
                f"refuse sandbox mode {mode!r} — the codex adapter never grants full disk access "
                f"(T2, fail closed); use {SANDBOX_READ_ONLY!r} or {SANDBOX_WORKSPACE_WRITE!r}")
        # A write sandbox MUST be scoped to the node's own isolated worktree (--cd). Refuse an
        # unscoped workspace-write at construction: otherwise `codex exec --sandbox workspace-write`
        # would run with cwd=None (the supervisor's dir, typically the repo root), giving a coding
        # node write access to the whole tree — exactly what Phase-10 worktree isolation prevents
        # (T2, fail closed; spec-audit 15C .adapter MINOR-1).
        if mode == SANDBOX_WORKSPACE_WRITE and not (workdir and str(workdir).strip()):
            raise ValueError(
                "codex workspace-write requires an isolated worktree (--cd) — the coding role never "
                "gets unscoped write access (T2 / Phase 10, fail closed)")
        self._sandbox_mode = mode
        self.name = f"codex:cli:{self.model or 'default'}"
        self._timeout_s = timeout_s
        # cost-to-accepted-output instrumentation (Buildout §4). The mock backends count calls;
        # without this the REAL backend reports 0 for exactly the legs that spend the subscription.
        self.calls = 0

    def build_command(self, prompt: str) -> list[str]:
        """`codex exec [-m <slug>] --sandbox <mode> [--cd <worktree>] <prompt>` — the CLI's
        documented non-interactive mode (R8/.detect). No `--with-api-key`/`--with-access-token`,
        no `--dangerously-bypass-*`, never `danger-full-access`: nothing that carries auth or weakens
        the sandbox. An explicit `--sandbox` + `-m` take precedence over any node-controlled
        `~/.codex/config.toml` (T2 containment)."""
        argv: list[str] = [self.executable, CODEX_EXEC_SUBCOMMAND]
        if self.model:
            argv += [CODEX_MODEL_FLAG, self.model]
        argv += [CODEX_SANDBOX_FLAG, self._sandbox_mode]
        if self.workdir:                    # coding role: scope the run to the node's own worktree
            argv += [CODEX_CD_FLAG, str(self.workdir)]
        # Defense in depth (unreachable via the guarded constructor, but never emit a write sandbox
        # without a worktree scope): workspace-write MUST carry --cd (T2, fail closed).
        if self._sandbox_mode == SANDBOX_WORKSPACE_WRITE and not self.workdir:
            raise ValueError(
                "refuse workspace-write without an isolated worktree (--cd) — coding writes are "
                "confined to the node's own worktree (T2 / Phase 10, fail closed)")
        # Guard the FLAGS only (prompt not yet appended) so a benign prompt that happens to equal a
        # flag token is never misread as smuggling one; the argv is a list, so subprocess never
        # word-splits a value into a separate flag anyway (spec-audit 15C .adapter NIT-1).
        _assert_no_forbidden(argv)
        argv.append(prompt)
        return argv

    @staticmethod
    def _is_credential_key(name: str) -> bool:
        """Fail-closed classifier: a var is credential/endpoint-bearing if it is a known key, starts
        with a provider prefix, or contains a secret-token substring. Delegates to the module-level
        `is_credential_env_key` so the headless and interactive launch paths can never drift apart."""
        return is_credential_env_key(name)

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Child environment with every credential- or endpoint-bearing key REMOVED (see
        `_is_credential_key`). The subscription OAuth token lives in the CLI's own host-native store
        (`~/.codex/auth.json`), which we never touch; scrubbing the env means no key can be
        transmitted and no endpoint override can redirect the call — the subscription path is the
        only one left. `CODEX_HOME` (the CLI's config/auth dir pointer — not a secret) is preserved
        so the OAuth path stays reachable; non-secret vars (PATH, HOME, proxies, locale, temp) are
        preserved so the CLI still runs."""
        env = dict(os.environ if base_env is None else base_env)
        for key in [k for k in env if self._is_credential_key(k)]:
            env.pop(key, None)
        return env

    def _classify(self, text: str) -> bool:
        """Does this text carry an auth/credit/rate marker anywhere? Used on the NON-ZERO exit
        path, where the CLI has already told us the call failed and the only question left is
        WHY."""
        low = text.lower()
        return any(marker in low for marker in _AUTH_FAILURE_MARKERS)

    def _classify_error_report(self, text: str) -> bool:
        """W-48 (A-6). Does this ZERO-EXIT stdout READ AS an error report rather than an answer?

        The distinction the whole unit turns on: an error report DECLARES the condition, an answer
        MENTIONS it. So a marker counts only on a line that opens like a report -- an `error:` /
        `fatal:` / `codex:` prefix, or the marker itself starting the line -- and never merely
        because the word appears somewhere in prose the model wrote.

        DECLARED BOUND: a CLI that reports an auth condition on a zero exit in some other shape is
        NOT paused by this path. That is the fail-closed direction for the WRONG failure here --
        pausing a whole node on an answer is worse than missing a signal that the non-zero path,
        the login-status probe and the launch gate all also carry."""
        for raw in (text or "").splitlines():
            line = raw.strip().lower()
            if not line:
                continue
            body = _ERROR_PREFIX_RE.sub("", line, count=1)
            if body != line and any(m in body for m in _AUTH_FAILURE_MARKERS):
                return True          # `error: rate limit exceeded`
            if any(body.startswith(m) for m in _AUTH_FAILURE_MARKERS):
                return True          # `not logged in` as the whole report
        return False

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        cmd = self.build_command(prompt)
        env = self.build_env()
        cwd = self.workdir if self.workdir else None
        # counted BEFORE the call: a subscription call that fails still consumed the attempt, and
        # under-reporting spend is the dishonest direction (Buildout §4)
        self.calls += 1
        try:
            # stdin CLOSED — see `_run` above and `ClaudeCliBackend.generate`: the prompt is in
            # argv, and an inherited non-TTY stdin turns a live call into a timeout
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self._timeout_s,
                                  # W-03/A-2: see `process_tree`. Without this the
                                  # host ANSI codepage decodes the transcript and an
                                  # undefined byte yields stdout=None at exit 0.
                                  encoding="utf-8", errors="replace",
                                  env=env, cwd=cwd, check=False, stdin=subprocess.DEVNULL)
        except FileNotFoundError as exc:  # CLI vanished between detection and spawn — fail closed
            raise CodexAuthError(f"`{self.executable}` not found on PATH — fail closed") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            # W-50 (R-24), the same defect on this second live `generate`. The CLASSIFICATION now
            # reads BOTH streams; `detail` stays `stderr or stdout` because it is the human-facing
            # excerpt in the message, not the evidence. Measured before repair: an auth failure
            # reported on STDOUT with any ordinary stderr noise raised RuntimeError and the node
            # was never paused, because `stderr or stdout` picked the stream without the marker.
            combined = (proc.stdout or '') + "\n" + (proc.stderr or '')
            if self._classify(combined):
                raise CodexAuthError(f"codex CLI auth/rate failure: {detail[:200]} — pause (Plan §18.4)")
            raise RuntimeError(f"codex CLI exited {proc.returncode}: {detail[:200]}")
        out = (proc.stdout or "").strip()
        # An auth/rate condition can surface on a zero exit with an error message on stdout too.
        # W-48 (A-6): but a SUCCESSFUL ANSWER that merely DISCUSSES one is not that condition, and
        # this used to scan the whole answer for the markers. Measured: "apply a rate limit of 100
        # requests per minute", "reject writes once the tenant exceeds its usage limit", "handle
        # HTTP 429 by backing off", "if the user is not logged in, redirect them" and "check for an
        # invalid api key" each PAUSED THE NODE. Five ordinary engineering answers, and the pause is
        # node-wide, not task-level -- so asking the model about rate limiting took the node down.
        #
        # rc == 0 is STRUCTURED evidence that the call succeeded, and this tier ruling is that
        # structured evidence outranks prose. So on a zero exit the marker is only believed when it
        # appears in a line SHAPED LIKE AN ERROR REPORT rather than anywhere in the text. The
        # stdout-only auth failure this branch exists for still pauses; an answer about the same
        # subject does not.
        if self._classify_error_report(out) and not out.startswith("{"):
            raise CodexAuthError(f"codex CLI reported: {out[:200]} — pause (Plan §18.4)")
        if not out:
            # W-03/A-2: a zero exit that produced NOTHING is not an answer. This
            # used to synthesize `{"codex_exec": "empty"}` and return it as a
            # RESULT, so an invocation with nothing to show published a candidate
            # no model ever wrote. Reporting the failure is the honest direction.
            raise RuntimeError(
                "codex CLI exited 0 but produced no readable output "
                f"(stderr: {(proc.stderr or '')[:200]!r}) — no candidate published")
        return out


# assert the Backend protocol is satisfied at import (both are structural Backends)
_MOCK_BACKEND: Backend = MockCodexCliBackend()


def build_codex_adapter(context: AdapterContext, mcp_client: Any, backend: Backend, *,
                        role: str = "reasoning") -> ModelWorkerAdapter:
    """Configure the shared, already-governed ModelWorkerAdapter as a live `openai_codex_cli`
    frontier worker in one of two roles (reasoning | coding-specialist). `context` MUST come from
    the supervisor (spawned_by_supervisor=True) — the base contract refuses a naked launch (I-C1).
    Holds no credential (base default False)."""
    if role not in _ROLE_NODE_CLASS:
        raise ValueError(f"unknown codex worker role {role!r} — expected reasoning|coding")
    return ModelWorkerAdapter(
        context, mcp_client, backend,
        adapter_name=CODEX_ADAPTER, node_class=_ROLE_NODE_CLASS[role], locality="frontier",
        offline_profile_eligible=False, requires_network=True,
        capability_descriptors=_ROLE_DESCRIPTORS[role], subscription_backed=True)
