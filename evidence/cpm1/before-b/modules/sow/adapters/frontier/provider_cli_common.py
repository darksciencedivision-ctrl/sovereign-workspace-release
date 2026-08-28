"""Shared trust/emission policy for the two OP-12 frontier provider CLIs. Phase 18B `.adapter`.

Register **OP-12** (directive §17) authorized `grok_build` (CLI `grok`) and `google_antigravity`
(CLI `agy`). Phase 18A built the operator-facing reconnaissance tool around them; 18B `.adapter`
builds the headless worker adapters. Both need the SAME answers to the same four questions:

  1. which environment variables must never reach a provider child (credential isolation, §13);
  2. which arguments this build refuses to emit (tool/permission policy, §11);
  3. what a provider's own `models` listing may be read to mean (inventory honesty, §8);
  4. how a CLI invocation's outcome is classified (exit-code-first, §6 — the Codex-period lesson).

Those four answers live here, once. The 18A tool `tools/providers/frontier_provider_recon.py`
imports and re-exports them rather than keeping its own copies: a policy stated in two places is
how `ollama_local`-class drift starts, and the 18A gate was reopened twice over findings of exactly
that shape. The dependency direction is product-layer-down — the tool imports the adapter layer,
never the reverse.

What is NOT shared, stated so the claim is not read wider than it is: `probe_provider_cli` below
and the tool's own `probe_status` both sequence the same metadata calls, and they are separate on
purpose — the tool's answer carries diagnostics, registration state and lease state for an operator
reading a status report, while this one carries only what a picker may act on. They share the
parsers, the classifier and the auth vocabulary, which is where a divergence would actually hurt.
Consolidating the sequencing is the `.picker` sub-step's call, once it has a real consumer (U269).

**Command-surface authority (operator directive §2).** Every flag this build EMITS, and every
provider-specific flag it refuses, was read off THIS host's captured `grok --help` /
`grok agent --help` / `agy --help` (2026-07-31, `docs/evidence/live/phase18a_host_recon.json`) —
never from memory. Where the operator directive quoted a flag the installed CLI does not have, the
installed CLI wins and the delta is recorded.

One honest exception, called out rather than folded into the claim: four entries in
`FORBIDDEN_PROVIDER_ARGS` (`--yolo`, `--dangerously-bypass-approvals-and-sandbox`, `--api-key`,
`--with-api-key`) are on NEITHER captured surface. They are Claude-Code/Codex-shaped flags carried
over from 18A and kept as harmless supersets, marked as such below. The first draft of this
paragraph said "every flag named below", which the capture falsifies — the exact direction §2
exists to prevent (U263).

**What this module does NOT do.** It grants no authority. Pinning a permission mode on an argv is
not containment in the invariant-29 sense — it is an argument the harness itself honours, and I-29
says never trust the harness. What IS enforced: no credential-, endpoint-, identity-, or
approval-widening argument can be emitted; no credential-bearing variable is passed to a provider
child; and the live spawn runs inside the repository's existing Windows job-object boundary
(`process_tree.run_managed_process`), so descendants are reaped rather than left behind. That
boundary is process-lifetime containment, not a filesystem/network sandbox — the latter is still
unbuilt for provider children (U25, owed).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from adapters.base.backend import BackendAuthPause

# ---------------------------------------------------------------------------------------------
# Credential isolation (operator directive §13; build directive §2.2)
# ---------------------------------------------------------------------------------------------
# Exact keys the xAI/Google toolchains document, scrubbed from any child environment this build
# constructs. Both CLIs authenticate through their OWN host-native OAuth stores; removing these
# means no API key can be transmitted and no PROVIDER-SPECIFIC endpoint variable
# (`XAI_API_BASE_URL` and its family) can redirect a call. That is the whole claim, and it is
# narrower than the one this comment used to make: `HTTP_PROXY`/`HTTPS_PROXY` survive deliberately
# (removing an operator's proxy breaks the CLI on a network that requires one), so a host-level
# proxy remains an environment route this build does not close — recorded, not claimed away (U264).
PROVIDER_CREDENTIAL_ENV_KEYS: tuple[str, ...] = (
    "XAI_API_KEY", "XAI_API_BASE_URL", "GROK_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_GENAI_API_KEY", "ANTIGRAVITY_API_KEY",
    # Not credentials, but both redirect or inject into an npm-installed Node CLI (`grok` is
    # installed with `npm install -g`): `NODE_OPTIONS` can inject a `--require` module into the
    # child, and `NODE_EXTRA_CA_CERTS` can make an interception proxy's certificate trusted.
    # Neither carries a prefix or substring the nets below would catch (U264).
    "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS",
    # W-32: the third member of that family, and it was missing. `NODE_PATH` prepends directories to
    # the module resolution order, so a `require("...")` inside an npm-installed Node CLI can be
    # answered by an attacker-chosen file without altering the CLI or its arguments at all. It is
    # the same class as `NODE_OPTIONS` — redirect rather than secret — and like the other two it
    # carries no prefix or substring the nets below catch, which is why it survived until it was
    # looked for by name.
    "NODE_PATH",
)
CREDENTIAL_KEY_PREFIXES: tuple[str, ...] = ("XAI_", "GROK_", "GEMINI_", "GOOGLE_", "ANTIGRAVITY_")
CREDENTIAL_KEY_SUBSTRINGS: tuple[str, ...] = (
    "TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "KEY", "AUTH", "CREDENTIAL",
)
# The ONE variable this allowlist exempts from a fail-closed classifier — and it is exempted on
# recorded evidence, not by analogy. The captured `grok --help` documents `--sandbox <PROFILE>`
# with `[env: GROK_SANDBOX=]`, i.e. the env form of the only filesystem/network containment lever
# that CLI exposes. Stripping it silently downgrades an operator who set it, on the very code path
# whose docstrings talk about containment: a scrubber that removes the sandbox is not a safety
# feature.
#
# `GROK_CONFIG_DIR`, `GROK_HOME`, `ANTIGRAVITY_HOME` and `ANTIGRAVITY_CONFIG_DIR` were in this set
# and have been REMOVED. Nothing in the capture documents them, so preserving them was an analogy
# to `codex.py`'s `CODEX_HOME` rather than evidence — and the analogy does not hold: `CODEX_HOME`
# survives passively (its name carries no marker the nets catch), whereas these four were being
# actively lifted over a fail-closed classifier, on the config/auth-directory surface this module
# elsewhere calls untrusted. Fail closed until a capture says otherwise (U265).
PRESERVED_PROVIDER_CONFIG_KEYS: frozenset[str] = frozenset({
    "GROK_SANDBOX",     # `--sandbox <PROFILE>` env form — documented in the capture
})


def is_provider_credential_env_key(name: str) -> bool:
    """Fail-closed classifier: True if `name` is a known xAI/Google credential or endpoint key,
    carries a provider prefix, or contains a secret-token substring.

    Deliberately a superset (a future `XAI_SESSION_TOKEN` is caught by prefix AND substring): the
    dishonest direction is leaving a new key un-scrubbed, so the default is to drop it — with the
    narrow, enumerated exception of `PRESERVED_PROVIDER_CONFIG_KEYS`."""
    up = name.upper()
    if up in PRESERVED_PROVIDER_CONFIG_KEYS:
        return False
    if up in PROVIDER_CREDENTIAL_ENV_KEYS:
        return True
    if up.startswith(CREDENTIAL_KEY_PREFIXES):
        return True
    return any(tok in up for tok in CREDENTIAL_KEY_SUBSTRINGS)


def scrub_provider_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Child environment with every credential/endpoint-bearing key REMOVED. Non-secret vars
    (PATH, HOME, USERPROFILE, temp, locale, and deliberately the proxy variables — see U264) are
    preserved so the CLI still runs and can still reach its OWN credential store, which this build
    never reads (§13)."""
    env = dict(os.environ if base_env is None else base_env)
    for key in [k for k in env if is_provider_credential_env_key(k)]:
        env.pop(key, None)
    return env


# Tests whose EXISTENCE is the evidence for `reads_credentials_by_design`. A bare boolean is a
# constant asserted against itself — it cannot go false when the code misbehaves, which is the
# defect round 4 corrected in the recon tool's report and which was re-created one layer down when
# the policy moved here (spec-audit Md-6). Rename or delete one of these and the pin goes red.
_CREDENTIAL_CLAIM_TESTS: tuple[str, ...] = (
    "tests/unit/test_op12_frontier_adapters.py::TestCredentialIsolation",
    "tests/unit/test_frontier_provider_recon.py::TestCredentialIsolation",
    "tests/unit/test_run_frontier_providers_ps1.py::TestRunnerProhibitions",
)


def credential_policy() -> dict[str, Any]:
    """The credential policy as a recordable document — the ENVIRONMENT policy, exceptions and
    claim basis included. It is not the whole §13 posture: the argv guard
    (`FORBIDDEN_PROVIDER_ARGS`) and the diagnostic redactor (`SECRET_PATTERNS`) are the other two
    halves, and an evidence surface that wants all three must say so itself."""
    return {
        "reads_credentials_by_design": False,
        "claim_basis": {
            "kind": "structural — no code path in this module, in either OP-12 adapter, or in "
                    "tools/providers/ opens a credential store; the claim is a design property, "
                    "not a per-run observation",
            "enforced_by": list(_CREDENTIAL_CLAIM_TESTS),
        },
        "scrubbed_env_keys": list(PROVIDER_CREDENTIAL_ENV_KEYS),
        "scrubbed_key_prefixes": list(CREDENTIAL_KEY_PREFIXES),
        "scrubbed_key_substrings": list(CREDENTIAL_KEY_SUBSTRINGS),
        "preserved_non_secret_config_keys": sorted(PRESERVED_PROVIDER_CONFIG_KEYS),
        "note": "the CLIs authenticate through their own host-native stores; this build never "
                "reads, stores, prints, or transmits a token (operator directive §13). The "
                "preserved keys are documented CONFIG pointers, not credentials: scrubbing them "
                "protects nothing and breaks containment (GROK_SANDBOX).",
    }


# ---------------------------------------------------------------------------------------------
# Argv emission policy (operator directive §11) — permission widening
# ---------------------------------------------------------------------------------------------
# Arguments this build refuses to emit for either provider: auto-approval, permission bypass,
# trust widening, credential passing, endpoint redirection, agent-identity substitution, and
# anything that creates git/project state behind the supervisor's back.
#
# The list is ENUMERATED, not exhaustive-by-construction — it is an emission guard over argv this
# build itself constructs, and it claims nothing about what a provider CLI would accept from
# elsewhere. Each group's warrant:
#
#   * approval/permission — `--always-approve` (grok) and `--dangerously-skip-permissions` (agy)
#     are on the captured surfaces; auto-approval is exactly what §11 forbids. `--yolo` and
#     `--dangerously-bypass-approvals-and-sandbox` are NOT on either — they are Claude-Code/Codex
#     spellings carried over from 18A and kept as harmless supersets (U263). Refusing a flag a CLI
#     does not have costs nothing; CLAIMING it came from the capture would have been the lie.
#   * tool/trust widening — `--allow`/`--allowedtools`/`--tools` (permission rules),
#     `--no-plan` (undoes the pinned plan mode), `--plugin-dir` (its own help: "always trusted —
#     hooks and MCP servers activate without a prompt"), `--agents` (inline subagent definitions).
#   * credential passing — `--api-key`, `--with-api-key`: never, on any surface (§13). Also not on
#     either captured surface — same superset status as the two above (U263).
#   * **endpoint redirection (U250)** — `--xai-api-base-url`, `--cli-chat-proxy-base-url`,
#     `--grok-ws-url`, `--grok-ws-origin`, `--leader-socket`. These are the argv twins of
#     `XAI_API_BASE_URL`, which the env scrub removes. Until now the build claimed "no endpoint
#     override can redirect a call" on the strength of the environment half alone; the two
#     policies agree now. `--leader-socket` belongs here for the same reason: it points the agent
#     at an arbitrary leader process instead of the child this build supervises.
#   * **agent identity (U250)** — `--agent`, `--agent-profile`. These widen *who acts*, which is
#     the module's own stated rationale for guarding `--agents`.
#   * **authentication initiation** — `--reauth` starts an auth flow inside a headless child.
#     Authentication is an explicit operator action through the runner (§5), never an adapter's.
#   * **state creation** — `--worktree`, `--worktree-ref`, `--new-project`. A node's worktree is
#     created by the Sovereign worktree-isolation path (Phase 10); a provider CLI making git or
#     project state of its own reaches around the supervisor that is supposed to own it.
#
# Deliberately NOT here, decided rather than left ambiguous (U250 left the call to 18B):
#   * `--cwd` (grok) and `--add-dir` (agy) BIND a workspace, which is what the isolation path
#     needs — banning them would ban the adapter's own containment, and this build emits them
#     itself. `--project` is NOT one of them: the capture describes it as "Project ID for the
#     current CLI session", a session selector rather than a directory bind, and this build never
#     emits it. It stays unbanned because U250 left the call to 18B and banning a selector nothing
#     emits is noise — but the workspace-binding warrant does not apply to it, and grouping it with
#     the other two by adjacency was wrong (U266).
#   * `--deny` / `--disallowed-tools` / `--no-subagents` / `--disable-web-search` / `--max-turns`
#     NARROW authority. A guard that refused them would be refusing safety.
#   * `--leader` / `--no-leader` select a leader-process mode without naming a socket, so they are
#     not endpoint redirection and are not banned. But they are NOT inert either, and the honest
#     statement is that this build cannot pin them: `--leader` "Defaults to [cli] use_leader in
#     config.toml" per the capture, and `--no-leader` exists only on the `grok agent` surface, not
#     on the top-level `grok -p` surface this adapter uses. A node- or host-controlled config can
#     therefore route the work into a shared leader process that is not the child this build
#     spawns. Recorded as T2 residue (U267), not pinned, and not claimed away.
#   * the instruction-injection flags — see `UNTRUSTED_INSTRUCTION_ARGS` (U235).
FORBIDDEN_PROVIDER_ARGS: tuple[str, ...] = (
    # approval / permission bypass
    "--always-approve", "--dangerously-skip-permissions", "--yolo",
    "--dangerously-bypass-approvals-and-sandbox",
    # credential passing
    "--api-key", "--with-api-key",
    # tool / trust widening. `--allow` and `--no-plan` are BACK on this list at Phase 19 unit 1
    # (U327 / U340), both removed by the untagged post-18E range: `--no-plan` because the installed
    # capture reads "Disable plan mode", so emitting it beside the restored `--permission-mode plan`
    # pin cancels that pin under a second name; `--allow` because the capture calls it
    # "Permission allow rule (compat alias: --allowedTools)" — provider tool permission granted by
    # an argv, which is the one thing this function's own docstring says never happens.
    "--allow", "--allowedtools", "--tools", "--no-plan", "--plugin-dir", "--agents",
    # endpoint redirection (U250)
    "--xai-api-base-url", "--cli-chat-proxy-base-url", "--grok-ws-url", "--grok-ws-origin",
    "--leader-socket",
    # agent identity (U250)
    "--agent", "--agent-profile",
    # authentication initiation
    "--reauth",
    # state creation outside the supervisor's worktree path
    "--worktree", "--worktree-ref", "--new-project",
)

# The four entries above that are on NEITHER captured surface (U263). Declared rather than left
# implicit so the §2 command-surface claim is CHECKABLE: a test reads the capture and requires every
# other forbidden flag to appear in it, so adding a remembered flag without evidence goes red.
CAPTURE_ABSENT_SUPERSET_ARGS: tuple[str, ...] = (
    "--yolo", "--dangerously-bypass-approvals-and-sandbox", "--api-key", "--with-api-key",
)

# Values refused for the two providers' mode selectors. `acceptEdits`/`accept-edits` auto-approve
# file edits, which is the unrestricted-write default §11 forbids.
FORBIDDEN_PERMISSION_MODES: tuple[str, ...] = (
    "bypasspermissions", "dontask", "auto", "acceptedits", "accept-edits",
)
MODE_FLAGS: tuple[str, ...] = ("--permission-mode", "--mode")

# Node-controlled untrusted INPUT (T2), NOT permission widening — the distinction U235 drew and
# this build keeps. `grok --help` documents `--system-prompt-override` (compat alias
# `--system-prompt`) and `--rules`: they inject instructions into the agent's own prompt. Folding
# them into the permission list would make that guard's name inaccurate in the other direction;
# leaving them unguarded entirely was the gap U235 recorded. So they get their own guard, named
# for what it does, and the adapters call BOTH. This is the same footing as the Codex adapter's
# `AGENTS.md` handling: node-controlled instruction sources are never emitted by this build, and
# the residue a flag cannot override is recorded rather than claimed away (U259).
UNTRUSTED_INSTRUCTION_ARGS: tuple[str, ...] = (
    "--system-prompt-override", "--system-prompt", "--rules",
)


def _normalise_flag(token: str) -> str:
    """Compare flags by NAME, independent of dash count. `agy --help` is Go `flag`-package output:
    single- and double-dash spellings are interchangeable there (`-p`, `-c`, `-h`/`--help` are all
    listed), so `-dangerously-skip-permissions` reached the same code path as its double-dash twin
    while passing a guard whose docstring called itself structural (U249)."""
    return token.lower().lstrip("-")


def _flag_pairs(argv: Sequence[str]) -> list[tuple[str, str | None]]:
    """(name, value) pairs, dash-normalised, with `--flag=value` split. Both CLIs accept the
    inline form as well as the separated one, so a guard that matched whole tokens only let
    `--permission-mode=bypassPermissions` walk straight through."""
    pairs: list[tuple[str, str | None]] = []
    tokens = [str(a) for a in argv]
    for i, tok in enumerate(tokens):
        # W-54 (R-85). A NAME candidate must be DASH-PREFIXED. This loop used to make one out of
        # EVERY token, so a legitimate model slug that happens to spell a flag name was refused:
        # `--model tools`, `--model agent`, `--model allow`, `--model worktree` all raised. A
        # provider is free to name a model `tools`; this build is not free to refuse it for
        # resembling one of OUR flag names.
        #
        # Safe because every entry in the forbidden lists is a FLAG -- `--reauth`, `--worktree`,
        # `--new-project` and the rest were read off this host captured `--help`, and none of them
        # is a bare subcommand. So skipping non-dash tokens cannot open a subcommand hole.
        #
        # And it stays safe in the other direction: a token CARRYING a dash is treated as a flag
        # WHEREVER it appears, including in value position, so smuggling `--always-approve` in as a
        # model slug or a workdir is still refused. The value position is what makes a value; a
        # dash is what makes a flag.
        if not tok.startswith("-"):
            continue
        name, sep, inline = tok.lower().partition("=")
        if sep:
            pairs.append((_normalise_flag(name), inline))
        else:
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else None
            pairs.append((_normalise_flag(tok), nxt))
    return pairs


_FORBIDDEN_NAMES = frozenset(_normalise_flag(a) for a in FORBIDDEN_PROVIDER_ARGS)
_MODE_FLAG_NAMES = frozenset(_normalise_flag(a) for a in MODE_FLAGS)
_UNTRUSTED_NAMES = frozenset(_normalise_flag(a) for a in UNTRUSTED_INSTRUCTION_ARGS)


def assert_no_forbidden_provider_args(argv: Sequence[str]) -> None:
    """Refuse to emit an auto-approval / permission-bypass / credential / endpoint-redirection /
    identity-substitution argument. Deterministic permission logic (build directive §4): provider
    tool permission is subordinate to the Sovereign launch ticket, never granted by an argv.

    UNCONDITIONAL, and restored to that at Phase 19 unit 1 by operator ruling **OP-13**. The
    untagged post-18E range put two exemptions in this function: an `execution_profile` parameter
    whose only effect was to let `google_antigravity` emit `--mode accept-edits`, and a value
    exemption that permitted one exact `--allow` rule. Both are gone. `D-P18-13` / `U317` say a
    provider CLI's own always-approve setting is never operator approval, and that is a statement
    about the CLASS, not about one enum. The parameter is GONE rather than defaulted-off — a
    keyword a caller can pass is a carve-out waiting to be re-armed — and
    `TestTheGuardHasNoExecutionProfileCarveOut` asserts the TypeError that proves it absent.

    The sentence above is therefore true again without qualification: this function now permits no
    argv that grants provider tool permission. It did not hold while the `--allow` exemption stood
    (spec-audit MAJOR-2, U340)."""
    for name, value in _flag_pairs(argv):
        if name in _FORBIDDEN_NAMES:
            raise ValueError(f"refuse to build a provider command containing {name!r} — provider "
                             f"tool permission is subordinate to the Sovereign launch ticket "
                             f"(operator directive §11, fail closed)")
        if name in _MODE_FLAG_NAMES and value in FORBIDDEN_PERMISSION_MODES:
            raise ValueError(f"refuse mode {value!r} — never auto-approved "
                             f"(operator directive §11, fail closed)")


def assert_no_untrusted_instruction_args(argv: Sequence[str]) -> None:
    """Refuse to emit a system-prompt or rules override (T2, U235). Separate from the permission
    guard on purpose: these do not widen authority, they replace the agent's instructions, and
    naming them accurately is what makes both guards mean something."""
    for name, _value in _flag_pairs(argv):
        if name in _UNTRUSTED_NAMES:
            raise ValueError(f"refuse to build a provider command containing {name!r} — "
                             f"node-controlled instruction sources are untrusted input, never "
                             f"emitted by this build (T2 / U235, fail closed)")


# ---------------------------------------------------------------------------------------------
# Bounded, secret-scrubbed diagnostics (operator directive §13)
# ---------------------------------------------------------------------------------------------
# Each pattern is anchored on a real key PREFIX and refuses to start mid-token: a looser version
# matched `sk` inside `--dangerously-skip-permissions` and `xai` inside `--xai-api-base-url`,
# corrupting the very help capture this build cites as its authority. Redaction that damages
# evidence is not safety.
_NOT_AFTER_TOKEN_CHAR = r"(?<![A-Za-z0-9_\-])"
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # The token bodies admit `-` because real keys are hyphen-segmented (`sk-proj-…`, `sk-ant-…`):
    # with the class limited to `[A-Za-z0-9_]`, `sk-proj-DEADBEEFDEADBEEF` matched only four
    # characters past `sk-` and passed through unredacted. Found at 18E `.live.shape` while
    # measuring what a provider-controlled KEY NAME could carry into published evidence. Strictly
    # more redaction than before, never less.
    (re.compile(_NOT_AFTER_TOKEN_CHAR + r"xai-[A-Za-z0-9_\-]{16,}"), "[REDACTED-KEYLIKE]"),
    (re.compile(_NOT_AFTER_TOKEN_CHAR + r"sk-[A-Za-z0-9_\-]{16,}"), "[REDACTED-KEYLIKE]"),
    (re.compile(_NOT_AFTER_TOKEN_CHAR + r"gsk_[A-Za-z0-9_]{16,}"), "[REDACTED-KEYLIKE]"),
    (re.compile(_NOT_AFTER_TOKEN_CHAR + r"AIza[A-Za-z0-9_\-]{20,}"), "[REDACTED-KEYLIKE]"),
    (re.compile(_NOT_AFTER_TOKEN_CHAR + r"ya29\.[A-Za-z0-9_\-]{20,}"), "[REDACTED-KEYLIKE]"),
    (re.compile(r"\beyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{5,}"), "[REDACTED-JWT]"),
    # A header, not prose: the separator is REQUIRED and the value must be a long unbroken token.
    # Without that, `authorization required, run \`grok login\`` — the exact AUTH_REQUIRED
    # diagnostic an auditor needs — was replaced wholesale.
    (re.compile(r"\b(?:bearer|authorization)\s*[:=]\s*[^\s\"']{16,}", re.I), "[REDACTED-AUTHHEADER]"),
    (re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{12,}", re.I), "[REDACTED-AUTHHEADER]"),
    (re.compile(r"\b(?:access|refresh|id)[_-]?token\s*[\"':=]+\s*\S{8,}", re.I), "[REDACTED-TOKEN]"),
)
MAX_DIAGNOSTIC_CHARS = 600


def redact_diagnostics(text: str | None, *, limit: int = MAX_DIAGNOSTIC_CHARS) -> str:
    """Bounded, secret-scrubbed DIAGNOSTIC text — every transcript that is recorded as evidence or
    printed to the operator goes through it, because provider diagnostics are useful and provider
    credentials are never ours to hold (§13). Truncation is marked so a reader knows the text is
    partial.

    Not applied to a successful model RESPONSE: that is the product the node publishes, and
    redacting it would corrupt the artifact (same treatment as the Codex and Claude backends).
    The word "every" here used to be unqualified and was false of that path."""
    s = (text or "").strip()
    for pattern, replacement in SECRET_PATTERNS:
        s = pattern.sub(replacement, s)
    if len(s) > limit:
        s = s[:limit] + "…[truncated]"
    return s


# ---------------------------------------------------------------------------------------------
# Exit-code-first outcome classification (operator directive §6 — the binding lesson)
# ---------------------------------------------------------------------------------------------
OUTCOME_SUCCESS = "SUCCESS"
OUTCOME_AUTH_REQUIRED = "AUTH_REQUIRED"
OUTCOME_USAGE_LIMIT = "USAGE_LIMIT"
OUTCOME_FAILED = "FAILED"
OUTCOME_TIMEOUT = "TIMEOUT"
OUTCOME_NOT_SPAWNABLE = "NOT_SPAWNABLE"
#: Exited 0 and produced NO READABLE STREAM at all. Not NOT_SPAWNABLE (the process ran) and
#: not FAILED (the exit code says otherwise) -- its own state, so a lost transcript can never
#: be published as an answer. See `classify_provider_outcome` for why this does not weaken
#: the exit-code-first rule.
OUTCOME_NO_OUTPUT = "NO_OUTPUT"

# Auth-probe states. Deliberately three-valued: a CLI with no offline auth-reporting surface
# yields UNVERIFIED, which is NOT the same as authenticated and NOT the same as auth-required.
AUTH_AUTHENTICATED = "AUTHENTICATED"
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_UNVERIFIED = "UNVERIFIED"
AUTH_PROBE_FAILED = "PROBE_FAILED"

# Markers consulted ONLY when the process already failed (nonzero exit / timeout / no spawn), or —
# for `is_auth_pause_text` — when a backend is deciding whether a failure is a fail-closed PAUSE
# rather than an ordinary task failure (Plan §18.4).
AUTH_MARKERS: tuple[str, ...] = (
    "not logged in", "not authenticated", "unauthenticated", "please log in", "please sign in",
    "run `grok login`", "run 'grok login'", "grok login", "sign in to continue",
    "authentication required", "invalid credentials", "session expired", "token expired",
    "http 401", "status 401", "error 401", "403 forbidden", "http 403", "status 403",
)
USAGE_MARKERS: tuple[str, ...] = (
    "usage limit", "quota", "rate limit", "rate-limit", "too many requests",
    "http 429", "status 429", "error 429", "insufficient credit", "credit balance",
)


@dataclass(frozen=True)
class ProviderOutcome:
    """Classification of one CLI invocation. `outcome` is derived exit-code-FIRST; `basis` names
    which rule decided it, so an evidence reader can see that a zero exit was never overridden."""

    outcome: str
    exit_code: int | None
    basis: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_SUCCESS

    def as_dict(self) -> dict[str, object]:
        return {"outcome": self.outcome, "exit_code": self.exit_code, "basis": self.basis,
                "detail": self.detail}


def classify_provider_outcome(exit_code: int | None, stdout: str | None = "", stderr: str = "", *,
                              timed_out: bool = False, spawn_error: str | None = None,
                              structured_error: object | None = None) -> ProviderOutcome:
    """Classify a provider CLI invocation. **Exit code first, always.**

    Order of authority (operator directive §6):
      1. the actual process exit code — `0` is SUCCESS and is NEVER demoted by transcript text;
      2. an explicit structured error field, when the CLI emitted one (`{"error": ...}`);
      3. explicit diagnostic text — consulted ONLY for an already-failed invocation.

    The rule that matters: a provider whose diagnostic text mentions historical login or quota
    language while the process exits successfully is AVAILABLE. That mistake (made against the
    Codex CLI earlier in this build) is what this function exists to prevent."""
    if spawn_error:
        return ProviderOutcome(OUTCOME_NOT_SPAWNABLE, None, "spawn-error",
                               redact_diagnostics(spawn_error))
    if timed_out:
        return ProviderOutcome(OUTCOME_TIMEOUT, None, "timeout", redact_diagnostics(stderr or stdout))
    if exit_code == 0:
        # Rule 2 applies to a zero exit ONLY through a real structured error field — never through
        # keyword matching on the transcript.
        if isinstance(structured_error, dict) and structured_error:
            return ProviderOutcome(OUTCOME_FAILED, 0, "structured-error-field",
                                   redact_diagnostics(json.dumps(structured_error)[:400]))
        if isinstance(structured_error, str) and structured_error.strip():
            return ProviderOutcome(OUTCOME_FAILED, 0, "structured-error-field",
                                   redact_diagnostics(structured_error))
        if stdout is None:
            # W-03/A-2. `stdout is None` is the signature of a reader thread that DIED --
            # subprocess swallows the decode exception -- not of a command that chose to say
            # nothing. Exit-code-first (§6) is NOT weakened: this reads the ABSENCE of a
            # stream, never the CONTENT of one, and an empty string still classifies SUCCESS
            # exactly as before, because after the codec is pinned a silent command really is
            # silent. Demoting `""` here would redefine SUCCESS for every quiet zero-exit
            # command in the tree, which is far wider than this defect.
            return ProviderOutcome(OUTCOME_NO_OUTPUT, 0, "exit-zero-no-readable-stream",
                                   redact_diagnostics(stderr or "", limit=200))
        return ProviderOutcome(OUTCOME_SUCCESS, 0, "exit-code-zero",
                               redact_diagnostics(stdout, limit=200))
    combined = f"{stdout or ''}\n{stderr or ''}".lower()
    if any(m in combined for m in AUTH_MARKERS):
        return ProviderOutcome(OUTCOME_AUTH_REQUIRED, exit_code, "nonzero-exit+auth-marker",
                               redact_diagnostics(stderr or stdout))
    if any(m in combined for m in USAGE_MARKERS):
        return ProviderOutcome(OUTCOME_USAGE_LIMIT, exit_code, "nonzero-exit+usage-marker",
                               redact_diagnostics(stderr or stdout))
    return ProviderOutcome(OUTCOME_FAILED, exit_code, "nonzero-exit",
                           redact_diagnostics(stderr or stdout))


def is_auth_pause_text(text: str) -> bool:
    """True if `text` reports an auth/credit/rate condition — a fail-closed PAUSE signal (Plan
    §18.4), not an ordinary task failure. Callers must consult this ONLY about an invocation that
    already failed: on a zero exit the transcript is never re-read (§6)."""
    low = (text or "").lower()
    return any(m in low for m in AUTH_MARKERS) or any(m in low for m in USAGE_MARKERS)


class ProviderAuthPause(BackendAuthPause):
    """A provider CLI reported an auth/credit/rate condition. The generic worker adapter re-raises
    it and the supervisor pauses the node (Plan §18.4); there is NO silent API-key fallback —
    there is no API-key path at all in this build (§13)."""


class ProviderNotSpawnable(ProviderAuthPause):
    """The provider executable could not be spawned at all. A pause like its parent (the node must
    stop, fail-closed), but a DISTINCT one: operator directive §14 requires "provider executable
    not installed" and "authentication required" to read differently to the operator, and folding
    the first into the second is how a missing CLI gets reported as a login problem."""


#: The JSON keys this build will read as "the provider's own response". One list, two readers —
#: the best-effort one below and the strict one after it — so "what the model said" and "what the
#: model said, for acceptance purposes" can never drift onto different key sets.
PROVIDER_RESPONSE_KEYS = ("result", "response", "text", "content", "message", "output")


def extract_provider_text(stdout: str) -> str:
    """Best-effort text of a provider response, for DISPLAY and for a worker's result payload.
    Structured output is preferred (the JSON `result` / `response` / `text` field); anything
    unparseable falls back to the raw transcript, and a parsed document with no recognised field
    falls back to the document, because an operator reading a transcript is better served by the
    whole thing than by an empty string.

    This is deliberately NOT the acceptance reader. Its whole-document fallback is exactly hole 2
    of U238: it makes a token appearing in ANY field count as an answer. Anything deciding whether
    a provider ANSWERED must call `extract_provider_response_field`."""
    s = (stdout or "").strip()
    if not s:
        return ""
    try:
        doc = json.loads(s)
    except (ValueError, TypeError):
        return s
    if isinstance(doc, dict):
        for key in PROVIDER_RESPONSE_KEYS:
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return json.dumps(doc)
    return s


def extract_provider_response_field(stdout: str) -> str:
    """The provider's OWN response field, or `""` — the reader ACCEPTANCE uses (U238, hole 2).

    The difference from `extract_provider_text` is the fallback, and the fallback is the whole
    point. That function answers "what is there to show the operator" and will hand back the raw
    transcript or `json.dumps(doc)` rather than nothing; this one answers "what did the model say",
    where a wrong answer certifies a live provider. `{"status":"done","debug":"GROK_PROVIDER_OK"}`
    is a document in which the CLI said nothing, and it must read as nothing.

    Fail closed in both directions: output that does not parse yields `""` (acceptance separately
    requires the document to parse, so this only ever adds a reason, never removes one), and a
    parsed document with no recognised response field yields `""` rather than the document. A bare
    JSON string document is the one whole-document case that IS a response — `json.dumps("...")`
    has no field to look in because the string is the payload."""
    s = (stdout or "").strip()
    if not s:
        return ""
    try:
        doc = json.loads(s)
    except (ValueError, TypeError):
        return ""
    if isinstance(doc, str):
        return doc
    if isinstance(doc, dict):
        for key in PROVIDER_RESPONSE_KEYS:
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


def structured_error_of(stdout: str) -> object | None:
    """The CLI's own structured error field, if it emitted parseable JSON carrying one. This is
    authority rule 2 in `classify_provider_outcome` — an explicit error FIELD, never a keyword."""
    try:
        doc = json.loads((stdout or "").strip())
    except (ValueError, TypeError):
        return None
    if isinstance(doc, dict):
        err = doc.get("error")
        if isinstance(err, (dict, str)) and err:
            return err
        if doc.get("is_error") is True:
            return doc.get("result") or doc.get("message") or "is_error"
    return None


# ---------------------------------------------------------------------------------------------
# Document SHAPE (U305) — what the reader above is actually being pointed at
# ---------------------------------------------------------------------------------------------
#: Value types the skeleton keeps verbatim. Booleans are classification-relevant (`is_error` is
#: read by `structured_error_of` above) and carry nothing; every string is a placeholder and every
#: number is flattened to 0, because a number can be an identifier.
_SHAPE_MAX_NODES = 400
_SHAPE_MAX_DEPTH = 8
#: A provider-chosen key is untrusted input of unbounded LENGTH; `max_nodes` bounds only how MANY
#: nodes are described. Keys are also secret-scrubbed — see `describe_provider_document`.
_SHAPE_MAX_KEY_CHARS = 120


@dataclass(frozen=True)
class ProviderDocumentShape:
    """The STRUCTURE of a provider's structured output — never its values.

    This exists because `extract_provider_response_field` and "the model said nothing" are
    indistinguishable in a verdict and opposite in a shape. Acceptance asks "did the model answer";
    when the answer is no, the next question is always "no, or nowhere this reader looks?", and
    without this instrument that question is answered by assumption (U305).

    `token_visible_to_strict_reader` is `None` when no token was supplied OR the token is empty —
    absence of a claim, never a false one. (The empty case is explicit because `"" in response` is
    unconditionally true, so the field would have published `True` for a token nobody asked
    about — validator NIT-17.)"""

    parsed: bool
    top_level_type: str
    top_level_keys: tuple[str, ...] = ()
    key_types: dict[str, str] = field(default_factory=dict)
    string_paths: tuple[str, ...] = ()
    number_paths: tuple[str, ...] = ()
    response_key_matched: str | None = None
    strict_response_found: bool = False
    token_paths: tuple[str, ...] = ()
    token_visible_to_strict_reader: bool | None = None
    skeleton: object = None
    truncated: bool = False
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"parsed": self.parsed, "top_level_type": self.top_level_type,
                "top_level_keys": list(self.top_level_keys), "key_types": dict(self.key_types),
                "string_paths": list(self.string_paths),
                "number_paths": list(self.number_paths),
                "response_key_matched": self.response_key_matched,
                "strict_response_found": self.strict_response_found,
                "token_paths": list(self.token_paths),
                "token_visible_to_strict_reader": self.token_visible_to_strict_reader,
                # deep-copied via a JSON round trip: `frozen=True` freezes the reference, not the
                # nested dict behind it, and every other field here is copied (validator NIT).
                "skeleton": json.loads(json.dumps(self.skeleton)),
                "truncated": self.truncated, "note": self.note}


def _json_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "null"


def describe_provider_document(stdout: str, *, token: str | None = None,
                               max_nodes: int = _SHAPE_MAX_NODES,
                               max_depth: int = _SHAPE_MAX_DEPTH) -> ProviderDocumentShape:
    """Describe a provider's structured output STRUCTURALLY — key names, value types, dotted paths,
    where `token` sits, and whether `extract_provider_response_field` can see it.

    **It never reports a string or numeric LEAF VALUE.** Not as a convenience: a shape record is
    published as evidence, so a describer that copied string values would publish whatever the CLI
    wrote into them (§2.2/§13). String leaves are reported as paths and as `<str:LEN>` placeholders;
    numbers are flattened to 0; booleans survive because they classify and cannot carry a secret.

    **KEY NAMES ARE REPORTED, and they are provider-controlled data, not schema.** This is stated
    rather than glossed because the first version of this docstring said "it never reports a value"
    flatly, and the published evidence falsifies the wide reading: `modelUsage.grok-4.5.costUSD`
    puts a MODEL IDENTIFIER from the response payload in a key position, and a CLI is equally free
    to key a map by account or session. Key names therefore go through `redact_diagnostics` (the
    same `SECRET_PATTERNS` every other evidence surface in this module uses) and are length-bounded;
    what remains is a provider-controlled string in a published artifact, and a reader should treat
    it as one. Found by the round-1 gate-validator (MEDIUM-5) and spec-auditor (MEDIUM-1).

    The one deliberate exception on the value side is `token`: a string leaf CONTAINING it becomes
    the token itself in the skeleton. That is what makes the skeleton a replayable fixture of a real
    document — the strict reader run against `json.dumps(shape.skeleton)` answers the same question
    it answered against the original — while the model's prose around it does not survive.

    **The replay property is exactly that narrow, and both edges are load-bearing:**

      * It holds for `extract_provider_response_field` ONLY. It does NOT hold for `accept_probe`,
        because replacing a token-BEARING string with the bare token deletes the prose that echo
        subtraction exists to remove: `{"result": "Reply with exactly: TOKEN"}` is a pure echo and
        is REFUSED, while its skeleton `{"result": "TOKEN"}` is ACCEPTED. A skeleton is never a
        fixture for an echo or acceptance test — that is U238/U304 territory and this would walk
        straight back into it.
      * Under truncation it does not hold at all, and it fails CLOSED. Past `max_nodes`/`max_depth`
        a value becomes `null`, which no reader matches, so a truncated skeleton can lose a response
        the original had — never invent one it did not. `null` rather than a `"<truncated>"` marker
        precisely because that marker is a NON-EMPTY STRING: under a recognised key it would read as
        a response, which is the blankness inversion below by another route (validator MEDIUM-3).

    Bounded by construction (`max_nodes`, `max_depth`) — a CLI's document is untrusted input (T2) —
    and `truncated` says so rather than a partial description pretending to be a whole one. The
    bound covers the key inventory too: `top_level_keys`/`key_types` were built outside the walk and
    could enumerate 50,000 provider-chosen keys beside `truncated: true` (validator MEDIUM-4)."""
    s = (stdout or "").strip()
    if not s:
        return ProviderDocumentShape(
            parsed=False, top_level_type="empty",
            token_visible_to_strict_reader=None if token is None else False,
            note="no output was read — the child produced none, or none was captured. This is NOT "
                 "a report that the provider returned an empty document: on the spawn-error, "
                 "timeout and containment-failure branches no provider was contacted at all "
                 "(spec-audit MINOR-3)")
    try:
        doc = json.loads(s)
    except (ValueError, TypeError, RecursionError):
        return ProviderDocumentShape(
            parsed=False, top_level_type="unparseable",
            token_visible_to_strict_reader=None if token is None else False,
            note="output did not parse as JSON; acceptance refuses it on condition 2 and the "
                 "strict reader reports no response field, so there is no structure to describe")

    budget = {"nodes": 0, "truncated": False}
    strings: list[str] = []
    numbers: list[str] = []
    tokens: list[str] = []

    def key_name(key: object) -> str:
        """A provider-controlled key, made publishable: secret-scrubbed by the module's own
        patterns and length-bounded. `max_nodes` bounds the COUNT of nodes and says nothing about
        the LENGTH of any one key."""
        return redact_diagnostics(str(key), limit=_SHAPE_MAX_KEY_CHARS)

    def walk(value: object, path: str, depth: int) -> object:
        budget["nodes"] += 1
        if budget["nodes"] > max_nodes or depth > max_depth:
            budget["truncated"] = True
            # `null`, NOT a `"<truncated>"` marker: a non-empty string under a recognised key would
            # read as a response the CLI never gave — the same inversion the blank-string branch
            # below exists to prevent. Truncation therefore loses answers and never invents them.
            return None
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            numbers.append(path)
            return 0
        if isinstance(value, str):
            strings.append(path)
            if token and token in value:
                tokens.append(path)
                return token
            if not value.strip():
                # BLANKNESS IS LOAD-BEARING and must survive into the skeleton. Both readers test
                # `val.strip()`, so a recognised key holding "" is NOT a match — and the first
                # version of this describer mapped it to `<str:0>`, a non-empty string, which
                # turned the real Grok document (`"text": ""`, `stopReason: cancelled` — the CLI
                # said nothing) into a skeleton whose `text` field READ AS AN ANSWER. A skeleton
                # that inverts the fact it exists to record is worse than no skeleton. A
                # whitespace-only string carries no information and no secret, so it is kept as
                # itself rather than described.
                return value
            return f"<str:{len(value)}>"
        if isinstance(value, dict):
            out: dict[str, object] = {}
            for key in value:
                # The budget is checked HERE, not only on entry: `walk` charges one node per value,
                # so a 5,000-key map still wrote 5,000 keys into the skeleton (each with a `null`
                # value) while reporting itself truncated. The key inventory being bounded and the
                # skeleton not being bounded is the same defect twice (validator MEDIUM-4).
                if budget["nodes"] > max_nodes:
                    budget["truncated"] = True
                    break
                name = key_name(key)
                child = f"{path}.{name}" if path else name
                out[name] = walk(value[key], child, depth + 1)
            return out
        if isinstance(value, list):
            return [walk(item, f"{path}[{i}]", depth + 1) for i, item in enumerate(value)]
        # Anything json.loads cannot produce; described rather than trusted.
        budget["truncated"] = True
        return None

    skeleton = walk(doc, "", 0)
    if isinstance(doc, str) and token and token in doc:
        tokens[:] = ["(document)"]

    matched: str | None = None
    if isinstance(doc, dict):
        for key in PROVIDER_RESPONSE_KEYS:
            val = doc.get(key)
            if isinstance(val, str) and val.strip():
                matched = key
                break
    response = extract_provider_response_field(s)
    # The key inventory is bounded by the SAME budget as the walk (validator MEDIUM-4): built
    # outside it, these two fields enumerated every provider-chosen key in the document while
    # `truncated: true` sat beside them, so a reader could not tell which half had been bounded.
    keys = [key_name(k) for k in doc][:max_nodes] if isinstance(doc, dict) else []
    if isinstance(doc, dict) and len(doc) > max_nodes:
        budget["truncated"] = True
    types = ({key_name(k): _json_type(v) for k, v in list(doc.items())[:max_nodes]}
             if isinstance(doc, dict) else {})
    return ProviderDocumentShape(
        parsed=True,
        top_level_type=_json_type(doc),
        top_level_keys=tuple(sorted(keys)),
        key_types=types,
        string_paths=tuple(strings),
        number_paths=tuple(numbers),
        response_key_matched=matched,
        strict_response_found=bool(response),
        token_paths=tuple(tokens),
        # EXACT substring, deliberately — `token_paths` and this field answer "is the token there",
        # and the folds `_token_answered` uses for ACCEPTANCE are laxer (case-insensitive presence,
        # punctuation-destructive subtraction). The two therefore disagree at the edges by design:
        # `{"response": "grok_provider_ok"}` is accepted and reports `false` here; a pure echo is
        # refused and reports `true`. Stated because both are published side by side and a reader
        # comparing them needs to know which question each answers (validator MINOR-8/9).
        token_visible_to_strict_reader=None if not token else (token in response),
        skeleton=skeleton,
        truncated=budget["truncated"],
        note="")


# ---------------------------------------------------------------------------------------------
# Version + model inventory (operator directive §8) — conservative, fail-closed, never invented
# ---------------------------------------------------------------------------------------------
_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


#: W-52 (R-48). The two DECLARATION shapes this tree has actually captured, and no others:
#:   BARE   `1.1.9`                                             -- `agy --version`
#:   NAMED  `grok 0.2.118 (1e1687c1cf)`, `codex-cli 0.144.6`,
#:          `opencode 0.99.0-mock`                              -- name, then the version
#: Chosen by reading the existing fixtures, not by generalising from the two adversarial npm
#: transcripts: a regex derived from its own exam questions passes the exam and nothing else.
_VERSION_BARE_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.\-]+)?\s*$")
_VERSION_NAMED_RE = re.compile(r"^\s*[A-Za-z][A-Za-z0-9._@\-]*\s+v?(\d+)\.(\d+)\.(\d+)\b")


def extract_version(text: str) -> tuple[str, tuple[int, int, int] | None]:
    """The provider's own version DECLARATION: `(line, tuple)`, or `("", None)` when it made none.

    W-52 (R-48). Both probes used to take `splitlines()[0]` and hand that ONE line to a parser that
    `search`ed it for the first semver anywhere. That failed in both directions at once, measured:

        '> agy@1.1.9 start' + 'grok 0.2.118'                 -> (1,1,9)  from the BANNER
        'npm WARN update available 1.2.3 -> 2.0.0' + 'grok..' -> (1,2,3)  the npm OLD version
        'npm WARN update available 9.9.9 -> 10.0.0' alone     -> (9,9,9)  meets_minimum=True

    Searching every line instead fixes only the first and makes the other two worse, because the
    npm numbers still win. **A version counts only when it is STRUCTURALLY ASSOCIATED with the
    provider's own declaration** — not "the first semver", not "any semver anywhere".

    TWO structural rules, and both are shape rules rather than a list of npm phrasings — the same
    reason W-46/W-47 anchored declarations instead of blacklisting words:
      * the line must MATCH a declaration shape (bare, or name-then-version);
      * it must carry EXACTLY ONE version. `old -> new` is a comparison, and a declaration is not.

    DECLARED BOUND: a line naming some OTHER program in the same shape (a hypothetical `npm 10.0.0`
    on its own line) would be accepted. Anchoring on the provider's identity would close that, and
    is deliberately NOT done here: `agy` prints a BARE version with no identity to anchor on, and
    `codex-cli` is not spelled `codex`. The shape rule is what the captured evidence supports.

    Returns the LINE as well as the tuple so a caller shows the operator the same line it parsed.
    """
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(_SEMVER_RE.findall(line)) != 1:
            continue                      # a comparison (`1.2.3 -> 2.0.0`), never a declaration
        m = _VERSION_BARE_RE.match(line) or _VERSION_NAMED_RE.match(line)
        if m:
            return line, (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return "", None


def parse_version(text: str) -> tuple[int, int, int] | None:
    """The version tuple of the provider's own declaration in `text`, or None — in which case the
    caller fails closed. Thin wrapper over `extract_version`, kept so existing callers and tests
    that want only the tuple are unchanged."""
    return extract_version(text)[1]


# A model id this build will accept from a CLI listing. Anything else (prose, banners, blank
# lines) is discarded rather than guessed at: an empty inventory fails the picker closed; a
# fabricated one would put a nonexistent slug in front of the operator.
MODEL_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@\-]{1,80}$")
# W-46 (A-8). ANCHORED to the whole line, and it was not. Applied with `.search()`, this matched
# any line CONTAINING the phrase -- so "If you are logged in elsewhere, run `grok logout` first.",
# "To check whether you are logged in, run `grok whoami`." and "Error: you are logged in on another
# device" all reported a logged-in session. `probe_status` turns `login_reported` straight into
# AUTH_AUTHENTICATED, so a help paragraph became a verdict about the operator.
#
# The login line is the CLI OWN DECLARATIVE report of its auth state and the only auth evidence
# available without a live call. A sentence that merely mentions the phrase is prose, and the tier
# rule is that prose is never authoritative. This mirrors the `you are not authenticated.` branch
# below, which was already an exact-line comparison.
_GROK_LOGIN_MARKER_RE = re.compile(
    r"^\s*you are logged in(?:\s+with\s+(?P<account>\S+))?\s*\.?\s*$", re.I)
_GROK_MODEL_LINE_RE = re.compile(r"^\s*[*\-•]\s*(?P<slug>\S+)(?P<rest>.*)$")
_GROK_DEFAULT_RE = re.compile(r"^\s*default model:\s*(?P<slug>\S+)\s*$", re.I)
# A bulleted model line may carry ONLY an annotation of the observed shape `(default)`; anything
# else after the slug means the line is prose and the "slug" is really a word.
_GROK_MODEL_ANNOTATION_RE = re.compile(r"^\s*(?:\((?:default|current)\))?\s*$", re.I)
_GROK_MODELS_HEADER_RE = re.compile(r"^\s*available models\s*:\s*$", re.I)
# W-44, `parse_antigravity_models`. That CLI prints no header and no auth line on this host, so it
# has no section to scope a slug to the way grok's `Available models:` does. The SHAPE of the id is
# therefore carrying the weight the section carries there, and it has to be stricter than
# MODEL_SLUG_RE — which admits any bare word — or a stray `Traceback` is an inventory.
#: Alphanumeric runs joined by SINGLE separators, so an id can neither begin nor end with one and
#: `Error:` is not one.
_AGY_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9]+(?:[._:@-][A-Za-z0-9]+)*$")
#: …and it must carry at least one digit or separator. This is the whole of the second repair: an
#: English word is not a model id. Admits `o3` (digit) and `gemini-3-pro` (both); refuses
#: `Traceback`, `unauthenticated`, `Warning`, `FAILED`, `None`, `null`, `true`.
_AGY_ID_EVIDENCE_RE = re.compile(r"[0-9._:@-]")
#: W-45 (A-7). …and it must carry a LETTER. The rule above is evidence AGAINST a token being
#: an English word; it is NOT evidence FOR it being a model id, and W-44 conflated the two. A
#: bare `401` printed by an authorization failure satisfies it, as do `403`, `429`, `500` and
#: `4-0-1` (which carries separators too), so an HTTP status line became the provider entire
#: inventory and the picker offered it as `verified: True`. Deliberately a SHAPE rule and NOT a
#: list of auth words: a blacklist would have made the observed rows green while leaving every
#: future status code minted. Real model ids are digit-heavy but never digit-only.
_AGY_ID_LETTER_RE = re.compile(r"[A-Za-z]")
#: A list bullet, in the three spellings observed across these CLIs.
_AGY_BULLET_RE = re.compile(r"^[*\-•]\s+")
#: A section header — structure, so skipped rather than counted as a discarded line.
_AGY_HEADER_RE = re.compile(r"^[A-Za-z][A-Za-z ]*:$")
#: The only annotation a slug may carry when it is separated from it by a SINGLE space. Mirrors the
#: grok rule deliberately: `(most recent call last)` must not read as an annotation.
_AGY_ANNOTATION_RE = re.compile(r"^\((?:default|current)\)$", re.I)
#: A COLUMN delimiter. A tab, or a run of two or more spaces — neither occurs in English word
#: spacing, which is why a single space is deliberately absent from this pattern.
_AGY_COLUMN_RE = re.compile(r"\t| {2,}")
# A SERVICE name — the only thing `account_hint` may ever carry. An account identity (anything
# with an `@`, or a bare word that is not a dotted domain) is withheld rather than recorded.
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)+$", re.I)


@dataclass(frozen=True)
class ModelInventory:
    """What a provider's own `models` command reported. `models` is empty whenever parsing found
    nothing it could trust — the picker then has nothing to offer for that provider, which is the
    fail-closed answer (never a placeholder)."""

    models: tuple[str, ...] = ()
    default_model: str | None = None
    account_hint: str | None = None      # e.g. "grok.com" — a SERVICE name, never an identity
    login_reported: bool = False
    auth_required_reported: bool = False
    parse_note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"models": list(self.models), "default_model": self.default_model,
                "account_hint": self.account_hint, "login_reported": self.login_reported,
                "auth_required_reported": self.auth_required_reported,
                "parse_note": self.parse_note}


def parse_grok_models(stdout: str) -> ModelInventory:
    """Parse `grok models` (plain text on this host, no structured mode offered):

        You are logged in with grok.com.

        Default model: grok-4.5

        Available models:
          * grok-4.5 (default)

    The login line is the CLI's OWN report of its auth state — the only auth evidence available
    without a live call — and `grok.com` is a SERVICE, not an account identity, so it is safe to
    record; anything that is not service-shaped is withheld.

    Conservative on three axes: a bullet is read as a model ONLY inside the `Available models:`
    section, ONLY when the slug matches the id shape, and ONLY when whatever follows it is an
    annotation like `(default)`. `  - Error: could not reach the model service` used to yield the
    model `Error:`; it now yields nothing, and the rejection is stated in `parse_note`."""
    models: list[str] = []
    rejected: list[str] = []
    default_model: str | None = None
    account: str | None = None
    login = False
    auth_required = False
    in_models_section = False
    for raw in (stdout or "").splitlines():
        line = raw.rstrip()
        # Grok 0.2.118 deliberately exits zero and still lists the public default model when the
        # operator is signed out.  This is not failure-keyword guessing: `models` is the CLI's
        # metadata/auth-reporting surface and this exact declarative line is its negative state.
        if line.strip().lower() == "you are not authenticated.":
            auth_required = True
            continue
        m = _GROK_LOGIN_MARKER_RE.search(line)
        if m:
            login = True
            candidate = (m.group("account") or "").strip().rstrip(".")
            account = candidate if candidate and _SERVICE_NAME_RE.match(candidate) else None
            continue
        if _GROK_MODELS_HEADER_RE.match(line):
            in_models_section = True
            continue
        d = _GROK_DEFAULT_RE.match(line)
        if d:
            slug = d.group("slug").strip()
            if MODEL_SLUG_RE.match(slug):
                default_model = slug
            continue
        b = _GROK_MODEL_LINE_RE.match(line)
        if b:
            if not in_models_section:
                rejected.append(line.strip())
                continue
            slug = b.group("slug").strip()
            if not MODEL_SLUG_RE.match(slug) or not _GROK_MODEL_ANNOTATION_RE.match(b.group("rest")):
                rejected.append(line.strip())
                continue
            if slug not in models:
                models.append(slug)
    # The default is added to the inventory only when the CLI actually listed an inventory. A
    # `Default model:` line on its own is a setting, not a listing, and promoting it produced a
    # one-entry inventory with parse_note "ok".
    if default_model and models and default_model not in models:
        models.append(default_model)
    if not models:
        note = "no model lines recognised in `grok models` output (fail closed)"
    elif rejected:
        note = f"ok; {len(rejected)} unrecognised line(s) discarded rather than guessed at"
    else:
        note = "ok"
    return ModelInventory(tuple(models), default_model, account, login, auth_required, note)


def parse_antigravity_models(stdout: str) -> ModelInventory:
    """Parse `agy models` (a bare newline-separated slug list on this host).

    W-44. The filter this replaces was `not line or line.endswith(":") or " " in line`, and it was
    wrong in TWO OPPOSITE DIRECTIONS at once — which is why neither half could be fixed alone:

      * it rejected every listing that carried any LAYOUT. Bullets, tab columns and space columns
        all yielded an EMPTY inventory, which fails the picker closed for a provider that is
        working. Worse, `gemini-3-pro (default)` was dropped while its unannotated sibling
        survived and `parse_note` still said `ok` — a silently PARTIAL inventory, the one outcome
        neither the operator nor a later reader can detect;
      * it accepted any bare one-word line. A stray `Traceback`, `Error` or `unauthenticated`
        became the provider's entire inventory, and the picker then offered that word as a model
        with `verified: True` and the note *"confirmed present in the CLI's own listing"*.

    Splitting columns without also tightening the id shape makes the second fault strictly worse,
    so this follows `parse_grok_models` and is conservative on THREE axes:

      1. WHAT A LINE MAY BE — an optional bullet, a candidate slug, then a rest;
      2. WHAT A SLUG MAY BE — alphanumeric runs joined by single separators, carrying at
         least one digit or separator AND at least one letter. A model id is neither an English
         word nor a bare number, which is what refuses `Traceback` and (W-45/A-7) `401` while
         admitting `o3` and `gemini-3.6-flash-high`;
      3. WHAT MAY FOLLOW IT — nothing, an annotation of the observed `(default)` shape, or a
         display column introduced by a STRUCTURAL delimiter (a tab, or a run of two or more
         spaces). A single space is not a delimiter, which is what refuses
         `gpt-4 is not available in your region` — a sentence whose first token is a genuine model
         id, and therefore the case that a shape rule alone would not have caught.

    DELIBERATE BOUND, stated rather than left to be discovered: a model id that is a single
    alphabetic word with no digit — a hypothetical `sonnet` — is refused. That is the fail-closed
    direction, and the line is COUNTED IN `parse_note` rather than dropped in silence, so the
    refusal is visible instead of looking like an empty listing.

    The CLI reports no default and no auth state here — hence `login_reported=False`, which the
    status layer turns into `UNVERIFIED`, never AUTHENTICATED."""
    models: list[str] = []
    rejected: list[str] = []
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _AGY_HEADER_RE.match(line):
            continue                       # a section header is structure, not a discarded line
        body = _AGY_BULLET_RE.sub("", line, count=1).strip()
        col = _AGY_COLUMN_RE.search(body)
        if col:
            # A structural delimiter means the remainder is a display column, which may say
            # anything — the slug's own shape is then the only thing standing between the operator
            # and a fabricated entry.
            slug, rest_ok = body[:col.start()].strip(), True
        else:
            head, _, tail = body.partition(" ")
            slug = head.strip()
            rest = tail.strip()
            rest_ok = not rest or bool(_AGY_ANNOTATION_RE.match(rest))
        if not (rest_ok and MODEL_SLUG_RE.match(slug) and _AGY_MODEL_ID_RE.match(slug)
                and _AGY_ID_EVIDENCE_RE.search(slug) and _AGY_ID_LETTER_RE.search(slug)):
            rejected.append(line)
            continue
        if slug not in models:
            models.append(slug)
    if models:
        note = ("ok" if not rejected else
                f"ok; {len(rejected)} unrecognised line(s) discarded rather than guessed at")
    else:
        note = "no model slugs recognised in `agy models` output (fail closed)"
        if rejected:
            # Said even when nothing was found, which is where `parse_grok_models` stays silent: an
            # empty inventory from a prose page and an empty inventory from an empty page are very
            # different facts, and this note is the only place that difference can surface.
            note += f"; {len(rejected)} line(s) discarded rather than guessed at"
    return ModelInventory(tuple(models), None, None, False, False, note)


# ---------------------------------------------------------------------------------------------
# The shared probe — presence, version, inventory. Makes no model call and spends nothing.
# ---------------------------------------------------------------------------------------------
# A runner is any callable (argv) -> (exit_code|None, stdout, stderr, timed_out, spawn_error) —
# the same shape the 18A tool uses, so a fake runner written for one works for the other.
RunResult = tuple[int | None, str, str, bool, str | None]


@dataclass(frozen=True)
class ProviderCliProbe:
    """What the picker and the roster may know about a provider WITHOUT spending a token. Every
    field is derived from metadata calls; the probe converts every outcome the runner REPORTS —
    nonzero exit, timeout, spawn error, unparseable version — into data rather than an exception,
    so callers gate on data (build directive §4, fail closed). See `probe_provider_cli` for the one
    thing that does propagate."""

    provider: str
    present: bool
    executable: str | None
    version: str | None
    version_tuple: tuple[int, int, int] | None
    meets_minimum: bool
    auth_state: str
    auth_detail: str
    models: tuple[str, ...]
    default_model: str | None
    model_note: str
    detail: str

    def selectable_models(self) -> tuple[str, ...]:
        """The slugs a picker may OFFER: none unless the CLI is present, at a parseable supported
        version, and not reporting that a login is required. Selectability is not availability —
        a live leg additionally needs the live switch, a governor lease, and a node record — which
        the vocabulary now admits (OP-12.1, `node@1.1`) but which nothing yet creates."""
        if not (self.present and self.meets_minimum) or self.auth_state == AUTH_REQUIRED:
            return ()
        return self.models

    def as_dict(self) -> dict[str, object]:
        return {"provider": self.provider, "present": self.present, "executable": self.executable,
                "version": self.version,
                "version_tuple": list(self.version_tuple) if self.version_tuple else None,
                "meets_minimum": self.meets_minimum, "auth_state": self.auth_state,
                "auth_detail": self.auth_detail, "models": list(self.models),
                "default_model": self.default_model, "model_note": self.model_note,
                "selectable_models": list(self.selectable_models()), "detail": self.detail}


def classify_models_call(*, stdout: str, stderr: str, parse_models: Any, reports_auth: bool,
                         confirm_hint: str = "") -> tuple[ModelInventory, str, str]:
    """THE one implementation of "what did the `models` call tell us about auth?" (W-49 / R-08).

    Two callers: `probe_provider_cli` here, and `tools.providers.frontier_provider_recon.
    probe_status`. They used to carry SEPARATE COPIES of this policy and had already drifted:
    this one fed the parser `stdout + stderr`, the recon copy fed it `stdout` alone. Grok 0.2.118
    writes its declarative authentication line to STDERR while returning the inventory on stdout
    at exit zero -- so on the REAL CLI the two probes disagreed, `probe_provider_cli` reporting
    AUTHENTICATED and `probe_status` UNVERIFIED for the very same call.

    WHICH STREAM THE PARSER SEES IS AUTH POLICY, not a formatting detail, which is exactly why it
    may not live in two places. `reports_auth` is the only knob: a CLI with an offline auth
    surface has both streams read, one without keeps the strict stdout-only inventory.

    `confirm_hint` names the surface a caller would point an operator at, and is the ONLY
    presentational difference the two callers are allowed -- a second copy of the policy to carry
    a different sentence is how this drifted the first time.
    """
    inv = parse_models(f"{stdout}\n{stderr}" if reports_auth else stdout)
    confirm = confirm_hint or "a live call"
    if not reports_auth:
        return inv, AUTH_UNVERIFIED, (
            f"no offline auth-state surface on this CLI — authentication is only "
            f"confirmable by {confirm}")
    if inv.auth_required_reported:
        return inv, AUTH_REQUIRED, "the CLI explicitly reports that the operator is not authenticated"
    if inv.login_reported:
        return inv, AUTH_AUTHENTICATED, ("the CLI reports a logged-in session"
                                         + (f" with {inv.account_hint}" if inv.account_hint else ""))
    # Silence is UNVERIFIED: never AUTHENTICATED (that would assume a session) and never
    # AUTH_REQUIRED (that would be a verdict about the operator login that nothing here observed).
    return inv, AUTH_UNVERIFIED, (
        "the CLI printed no login line this build recognises — auth state UNVERIFIED "
        "(never assumed either way)" + (f"; confirm with {confirm_hint}" if confirm_hint else ""))

def probe_provider_cli(*, provider: str, executable: str | None, runner: Any,
                       min_version: tuple[int, int, int], parse_models: Any,
                       reports_auth: bool) -> ProviderCliProbe:
    """Presence → `--version` → `models`, classified exit-code-first.

    **Raises nothing of its own.** Every provider outcome — absent binary, nonzero exit, timeout,
    spawn error, garbage version, empty model list — becomes a `ProviderCliProbe` field, so no
    caller has to wrap this in a `try` to stay fail-closed. What it does NOT do is swallow a
    RUNNER that raises: the runner's contract is to return the five-tuple (the production
    `subprocess_runner` catches `TimeoutExpired`/`OSError` itself and does), and a runner that
    raises anyway is a fault in the *harness*, not a provider outcome. The live-call tripwire
    `tests/live_call_guard` is exactly such a runner — it raises `SpawnRefused` to stop a
    deterministic test reaching a real CLI — and catching it here would silently disarm the
    guard. It propagates, deliberately. The docstring said the flat "Never raises" until the 18B
    close, which was wider than the code held (validator MEDIUM-2).

    `reports_auth` says whether this CLI has an offline auth-reporting surface at all. Grok's
    `models` prints its own login line; `agy` prints nothing of the kind, and silence there is
    UNVERIFIED — never AUTHENTICATED (that would assume a session) and never AUTH_REQUIRED (that
    would be a verdict about the operator's login that nothing here observed)."""
    if not executable:
        return ProviderCliProbe(provider, False, None, None, None, False, AUTH_UNVERIFIED,
                                "executable not found on PATH", (), None,
                                "not enumerated: CLI absent", "not found on PATH — fail closed")

    rc, out, err, timed, spawn = runner([executable, "--version"])
    version_outcome = classify_provider_outcome(rc, out, err, timed_out=timed, spawn_error=spawn)
    # W-52: the DECLARATION line and its tuple come from ONE call over the WHOLE output, so the
    # version shown to the operator is the line that was parsed. This used to be `splitlines()[0]`
    # here AND, separately, in `probe_status` -- the same policy written out twice, which is the
    # duplication class W-49 repaired. `extract_version` is now the single owner.
    raw_version, version_tuple = extract_version(out or err or "")
    if not raw_version:
        lines = (out or err or "").strip().splitlines()
        raw_version = lines[0].strip() if lines else ""      # nothing declared: show what it said
    meets = version_outcome.ok and version_tuple is not None and version_tuple >= min_version

    if not version_outcome.ok:
        return ProviderCliProbe(provider, True, executable,
                                redact_diagnostics(raw_version, limit=120) or None, version_tuple,
                                False, AUTH_PROBE_FAILED,
                                f"`--version` {version_outcome.outcome}", (), None,
                                "not enumerated: the CLI did not report a version",
                                f"version call {version_outcome.outcome} ({version_outcome.basis})")

    rc, out, err, timed, spawn = runner([executable, "models"])
    models_outcome = classify_provider_outcome(rc, out, err, timed_out=timed, spawn_error=spawn)
    if models_outcome.ok:
        # Grok 0.2.118 writes its declarative authentication line to stderr while returning the
        # model inventory on stdout with exit code zero.  Its metadata parser therefore receives
        # both streams; Antigravity has no offline auth surface and keeps the strict stdout-only
        # model list.
        # W-49: the ONE implementation, shared with `probe_status`. See `classify_models_call`.
        inv, auth_state, auth_detail = classify_models_call(
            stdout=out, stderr=err, parse_models=parse_models, reports_auth=reports_auth)

        detail = "ok" if meets else f"version below minimum {'.'.join(map(str, min_version))}"
        return ProviderCliProbe(provider, True, executable,
                                redact_diagnostics(raw_version, limit=120) or None, version_tuple,
                                meets, auth_state, auth_detail, inv.models, inv.default_model,
                                inv.parse_note, detail)

    auth_state = (AUTH_REQUIRED if models_outcome.outcome == OUTCOME_AUTH_REQUIRED
                  else AUTH_PROBE_FAILED)
    return ProviderCliProbe(provider, True, executable,
                            redact_diagnostics(raw_version, limit=120) or None, version_tuple,
                            meets, auth_state, models_outcome.detail, (), None,
                            f"model enumeration {models_outcome.outcome} ({models_outcome.basis}) "
                            f"— fail closed, nothing invented",
                            f"model enumeration {models_outcome.outcome}")


class FrontierProviderCliBackend:
    """Base for the two live OP-12 backends: invokes the host's already-authenticated provider CLI
    as a one-shot headless subprocess.

    NEVER used by the deterministic suite — every test constructs a mock or calls the pure
    `build_command`/`build_env`, which is what makes the credential (§13) and emission (§11)
    invariants verifiable without spawning anything.

    **`generate` REFUSES, and that is a fence rather than a sentence.** An earlier draft said it
    was "reachable only from a governed live path" because no node could be registered for either
    provider while U227 was unruled. True at the time (and no longer true at all — OP-12.1 admitted
    both ids into `node@1.1`, which is precisely why leaning on it was the wrong move: the argument
    expired and the fence did not). But even then, `NodeRegistry.register` gates node
    RECORDS — it does not gate backend construction, and `build_adapter` needs only an
    `AdapterContext` whose `spawned_by_supervisor` is a caller-set bool. So the protection was the
    absence of a caller, which is not a mechanism. `_LIVE_SPAWN_PATH_WIRED` is now the mechanism:
    `generate` raises until the supervised launch path for these providers exists, exactly as
    `frontier_provider_recon._SUPERVISED_PROBE_PATH` does for the 18A probe. The flag flips in the
    same commit that wires the path IT guards — the HEADLESS one this backend's `generate` runs on.
    18B `.picker` wired a different path (the supervised INTERACTIVE pane, which never calls
    `generate`), so the flag correctly did not move; saying "the path" while two exist is how a flag
    gets flipped for the wrong reason (spec-audit N-3). Never by config (U268).

    **Roles.** Reasoning only, and that is a decision rather than an omission. A coding role would
    need either an auto-approving permission mode (`acceptEdits`/`auto`/`dontAsk` — exactly what
    operator directive §11 forbids) or a sandbox profile value neither CLI documents (`grok
    --sandbox <PROFILE>` enumerates none; `agy --sandbox` says only "terminal restrictions"), and
    inventing one is the fabrication this build refuses. Directive **§11**'s own description of
    initial provider behaviour — read assigned context, reason, respond, publish CANDIDATE output,
    request protected actions through existing mechanisms — IS the reasoning role. Recorded as
    U260; revisited on live evidence, never on a guess.

    **T2 — node-controlled config is untrusted.** Both CLIs read config the operator's tree or
    home directory may contain (`~/.grok/config.toml`, agy's project config, rules files). What a
    flag ON THE SURFACE THIS BUILD USES can pin, it pins explicitly — the permission mode, the
    model, the workspace, and cross-session memory (`--no-memory`) — so a config default cannot
    supply something more permissive. That qualifier is load-bearing and was missing from the first
    draft: `--no-leader` exists only on the `grok agent` surface, so leader mode genuinely cannot
    be pinned from `grok -p`.

    Residue, recorded rather than claimed away (U259, the same class as the Codex adapter's U32):
    MCP servers and hooks declared in host config; plugin scopes already installed; and leader mode
    (U267), which a config can enable to route work into a process this build did not spawn and
    does not reap.
    """

    provider: str = ""
    executable_candidates: tuple[str, ...] = ()
    supported_roles: tuple[str, ...] = ("reasoning",)
    node_class: str = "worker_reasoning"

    #: FALSE until a supervised, governor-leased launch path for these providers exists. A `True`
    #: here is a claim that that path is wired; flipping it without wiring it is the fabrication
    #: this build refuses, and `test_generate_refuses_while_no_supervised_path_exists` fails closed
    #: on it. Set per-subclass, never per-instance and never from config (U268).
    _LIVE_SPAWN_PATH_WIRED: bool = False

    def __init__(self, executable: str | None = None, *, model: str | None = None,
                 role: str = "reasoning", workdir: str | None = None,
                 timeout_s: float = 180.0) -> None:
        if role not in self.supported_roles:
            raise ValueError(
                f"unknown {self.provider} worker role {role!r} — this adapter ships "
                f"{list(self.supported_roles)} only. A coding role would require an auto-approving "
                f"permission mode (operator directive §11 forbids it) or an undocumented sandbox "
                f"profile (fabrication); refused rather than faked (U260)")
        self.executable = executable if executable is not None else self._discover()
        self.model = model.strip() if model and model.strip() else None
        self.role = role
        self.workdir = str(workdir).strip() if workdir and str(workdir).strip() else None
        self.name = f"{self.provider}:cli:{self.model or 'default'}"
        self._timeout_s = timeout_s
        # cost-to-accepted-output instrumentation (Buildout §4): a real backend without a counter
        # reports 0 for exactly the legs that spend the subscription.
        self.calls = 0
        # Every pid the job-object boundary saw, so teardown accounting has something to check.
        self.spawned_pids: tuple[int, ...] = ()

    @classmethod
    def _discover(cls) -> str:
        import shutil  # noqa: PLC0415 — local: discovery is the only use, and only when unspecified
        for candidate in cls.executable_candidates:
            found = shutil.which(candidate)
            if found:
                return found
        return cls.executable_candidates[0] if cls.executable_candidates else cls.provider

    def build_command(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Child environment with every credential- or endpoint-bearing key REMOVED. The
        subscription OAuth token lives in the CLI's own host-native store, which this build never
        touches; scrubbing the env means no key can be transmitted and no endpoint override can
        redirect the call through the environment — and the argv guard closes the other half."""
        return scrub_provider_env(base_env)

    def _guard(self, argv: Sequence[str]) -> None:
        """Both guards, on every emitted argv: permission widening (§11) and instruction
        injection (T2 / U235). Called on the FLAGS only, before the prompt is appended, so a
        benign prompt whose text happens to equal a flag token is never read as smuggling one."""
        assert_no_forbidden_provider_args(argv)
        assert_no_untrusted_instruction_args(argv)

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        import subprocess  # noqa: PLC0415 — local: the deterministic suite never reaches this

        from adapters.frontier.process_tree import run_managed_process  # noqa: PLC0415

        if not self._LIVE_SPAWN_PATH_WIRED:
            # Invariant 2 / I-C1: no naked session. This refusal is deliberately BEFORE the call
            # counter — nothing was attempted, so nothing is counted.
            raise ProviderAuthPause(
                f"refuse to run the {self.provider} CLI: the supervised launch path (SessionManager "
                f"+ node identity + I-X3 lease on this provider's own subscription + teardown "
                f"accounting) is not wired for this provider, so the child would be a naked, "
                f"unleased session (invariant 2 / I-C1, fail closed; U268). Nothing was spawned "
                f"and nothing was spent.")
        cmd = self.build_command(prompt)
        env = self.build_env()
        # counted BEFORE the call: a subscription call that fails still consumed the attempt, and
        # under-reporting spend is the dishonest direction (Buildout §4)
        self.calls += 1
        try:
            # Inside the repository's Windows job-object boundary, so a CLI that spawns helpers
            # (grok's leader/agent processes) cannot leave descendants behind when this returns or
            # times out — the same boundary the live `claude_code` backend uses, and what operator
            # directive §12 means by process-tree termination on every exit path.
            # stdin CLOSED: an inherited non-TTY stdin lets a TUI-capable CLI block forever waiting
            # on input that never arrives, turning a live call into a timeout.
            proc = run_managed_process(cmd, timeout=self._timeout_s, env=env,
                                       stdin=subprocess.DEVNULL, cwd=self.workdir)
            self.spawned_pids = tuple(sorted(set(self.spawned_pids) | set(proc.spawned_pids)))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`{self.provider}` CLI timed out after {self._timeout_s}s") from exc
        except (FileNotFoundError, OSError) as exc:
            raise ProviderNotSpawnable(
                f"cannot spawn `{self.executable}`: {exc} — fail closed. This is an executable "
                f"problem, not an authentication one (§14)") from exc
        out, err = proc.stdout or "", proc.stderr or ""
        outcome = classify_provider_outcome(proc.returncode, out, err,
                                            structured_error=structured_error_of(out))
        if not outcome.ok:
            # W-50 (R-24). CONSUME THE CLASSIFIER VERDICT. This used to re-derive the pause by
            # searching `outcome.detail` -- which is `redact_diagnostics(stderr or stdout)`, i.e.
            # ONE stream and at most MAX_DIAGNOSTIC_CHARS of it. The classifier had already read
            # BOTH streams in full and recorded AUTH_REQUIRED; the re-scan then disagreed with it
            # two ways, measured:
            #   auth marker on STDOUT with any stderr noise -> detail is the stderr, no marker;
            #   auth marker beyond the 600-char redaction limit -> truncated away.
            # Both turned a real authentication failure into an ordinary RuntimeError and the node
            # was never paused. The verdict is the fact; the detail is a human-readable excerpt,
            # and an excerpt is not evidence.
            if outcome.outcome in (OUTCOME_AUTH_REQUIRED, OUTCOME_USAGE_LIMIT):
                raise ProviderAuthPause(
                    f"{self.provider} CLI auth/quota condition: {outcome.detail} — pause "
                    f"(Plan §18.4)")
            raise RuntimeError(f"{self.provider} CLI {outcome.outcome} "
                               f"({outcome.basis}): {outcome.detail}")
        return extract_provider_text(out)


class MockFrontierProviderBackend:
    """Deterministic stand-in — spawns nothing, replayable (build §2.4 substitution). Shapes its
    output like the final assistant message of a headless run, so the mock-first proof exercises
    the same downstream governance path as the live backend."""

    def __init__(self, provider: str, *, model: str | None = None) -> None:
        self.provider = provider
        self.model = model
        self.name = f"{provider}:mock:{model or 'default'}"
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        import hashlib  # noqa: PLC0415

        self.calls += 1
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return f"[{self.name}] deterministic result (h={h}) for prompt: {prompt[:120]}"


def resolve_model_ref(requested: str | None, available: Sequence[str] | None = None
                      ) -> tuple[str | None, str]:
    """Resolve the per-node model slug, honestly. Returns `(slug_or_None, note)`.

    `None` means "use the CLI default and RECORD the fallback in the roster" — never silent.
    When an inventory IS known, a requested slug outside it is REFUSED rather than passed through
    to fail at spend time: operator directive §8 forbids inventing model identifiers, and quietly
    forwarding one this build has no evidence for is the same fabrication one step later."""
    slug = requested.strip() if requested and requested.strip() else None
    if slug is None:
        return None, ("no model selected — the CLI's own default is used and this fallback is "
                      "recorded on the roster (operator directive §8, never silent)")
    # W-51 (R-25). This used to read `if available:` — so an EMPTY or UNESTABLISHED inventory
    # disabled the very check meant to stop an unverified label, and the slug was returned "carried
    # unverified". Measured: `resolve_model_ref("attacker-or-unprobed-label", ())` returned it, and
    # it reached argv as `--model attacker-or-unprobed-label`.
    #
    # EMPTY MEANS "no verified model information", NEVER "therefore every requested model is
    # permitted". That is the same optimistic reading of emptiness W-44/W-45 repaired one layer up,
    # and it is why an explicit non-null request is now corroborated or refused — never carried.
    #
    # `None` is untouched and is NOT an unverified label: it means "omit the flag, let the CLI use
    # its own configured default", and that path returns above.
    #
    # THE TWO EMPTY STATES REACH THE SAME DECISION AND ARE NOT THE SAME FACT, so they do not get the
    # same sentence: a provider that legitimately lists nothing is a different diagnostic from an
    # inventory that was never established (probe failed, parser refused, call errored). Collapsing
    # them is how "empty" starts reading as "fine".
    if available is None:
        raise ValueError(
            f"model {slug!r} cannot be corroborated: the provider inventory was NOT ESTABLISHED "
            f"(no listing was supplied to resolve against) — refused rather than carried "
            f"unverified (operator directive §8: model identifiers are never invented)")
    inventory = tuple(available)
    if not inventory:
        raise ValueError(
            f"model {slug!r} cannot be corroborated: the provider's own listing is EMPTY, which is "
            f"an absence of evidence and not a permission — refused (operator directive §8)")
    if slug not in inventory:
        raise ValueError(
            f"model {slug!r} is not in the provider's own listing {sorted(inventory)!r} — "
            f"refused (operator directive §8: model identifiers are never invented)")
    return slug, f"per-node model {slug!r}, confirmed present in the CLI's own listing"
