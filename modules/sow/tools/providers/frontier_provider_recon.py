"""Grok Build / Gemini-Antigravity — host reconnaissance and provider status engine. Phase 18A.

Register **OP-12** (directive §17) authorized two new live frontier providers:

    grok_build          · display "Grok Build"          · CLI `grok`
    google_antigravity  · display "Gemini · Antigravity" · CLI `agy`

This module is the deterministic brain behind `tools/providers/run_frontier_providers.ps1`
(the operator's bootstrap/diagnostic surface, operator directive §3). It discovers the CLIs,
parses their *own* metadata output, classifies status, builds the argv for the one harmless
live probe per provider — and, under `--action probe` only, **executes** that probe once the
live gate allows it (`run_probe`). An earlier version of this paragraph said "diagnostic only",
which was true of every caller when it was written and stopped being true the moment the probe
path landed; the same defect class this file records as F-8 is not going to live in its own
summary. It is not a second orchestration system (operator directive §1): it publishes no
artifact and registers nothing. The registry/adapter/governor/picker work is Phase 18B; while it
was owed, every provider here reported `NOT_REGISTERED`, honestly. **It has since landed**, and
both providers now report `REGISTERED` — see `provider_registration` for what that verdict does
and does not assert.

**The probe child is a GOVERNED, SUPERVISED session as of 18C `.probe-path` — U234 discharged.**
Through 18A and 18B this module executed (or rather, refused to execute) the provider CLI through a
bare `subprocess.run`: no node identity, no I-X3 subscription lease, no job object, no teardown
accounting. In 18A that gap was held shut by an IMPOSSIBILITY — no config could name either
provider, so the live gate could never allow the probe. `.scope` removed the impossibility by
adding the OP-12 row, which left an operator's config as the only thing in front of a bare
`subprocess.run` of a frontier CLI, so `run_probe` refused AFTER the gate allowed, on its own
supervision outcome.

`run_probe` now enters `node_runtime.supervisor.provider_probe_session.governed_probe_session`
before it spends anything: the same gate chain the interactive pane authorization runs (roster
profile + `LIVE_OPERATION_AUTHORIZED` → provider-live → R8 §6 operator terms → per-provider CLI
presence with a RESOLVED binary), then ONE durable I-X3 lease on that provider's own subscription
resource, then the child inside the repository's job-object boundary, then release-on-every-path
with the release MEASURED into the verdict. `_SUPERVISED_PROBE_PATH` is now True and says what it
always said: the flag names a path, and it moved in the commit that wired the path. **What is still
not claimed:** no Sovereign node RECORD exists for either provider — since OP-12.1 the vocabulary
admits one (`node@1.1`) but nothing here creates one (18D `.close`) — and
the CLIs' own `--permission-mode plan` / `--mode plan` remain arguments a harness honours rather
than containment (invariant 29; U25 owed). An INJECTED runner (the deterministic suite) bypasses the
job object by construction, so the verdict records `supervised_execution` rather than assuming it.

Non-negotiables encoded here (operator directive §6/§13, build directive §2.2):

  - **Exit-code-first classification.** A process that exits 0 is a SUCCESS, full stop. Its
    transcript is never re-read for the words "login", "quota", or "rate limit" to demote it
    (`classify_provider_outcome`). This is the Codex-period lesson made binding for every
    provider: keyword matching on a successful transcript once turned working providers into
    phantom auth failures. Failure is determined by exit code first, then structured error
    fields, then — only on a NONZERO exit — diagnostic text.
  - **Never infer authentication from mere presence.** An executable on PATH proves nothing.
    Auth state comes from the CLI's own auth-reporting output where one exists (`grok models`
    prints its login line), and is otherwise reported `UNVERIFIED` — never assumed either way.
  - **No credential handling, ever.** Nothing here reads, copies, or prints a token, a
    credential file, a browser cookie, or a Credential Manager entry. Both CLIs keep their own
    OAuth in their own host-native stores; we invoke them and read exit codes plus bounded,
    redacted diagnostics (`redact_diagnostics`). No `XAI_API_KEY`/`GEMINI_API_KEY`/
    `GOOGLE_API_KEY` path is ever enabled: those names are *scrubbed* from child environments
    (`scrub_provider_env`), never supplied.
  - **Never fabricate an inventory.** Model lists come from `grok models` / `agy models` and
    nothing else; an unparseable or empty listing yields an EMPTY list plus a reason, which
    fails the picker closed (operator directive §8) rather than inventing a slug.
  - **Nothing is installed or authenticated as a side effect.** This module never runs an
    install, never launches an interactive login, and never mutates the repo, git state, or
    `docs/loop/LOOP_STATE.json`. Install/login are explicit operator actions in the runner.

Command-surface authority (operator directive §2: "the installed command surface is
authoritative"): every flag used below was read off THIS host's `grok --help` /
`grok agent --help` / `grok models --help` / `agy --help` / `agy models --help` on 2026-07-31
and is captured verbatim in `docs/evidence/live/phase18a_host_recon.json`. Where the operator
directive quoted a flag the installed CLI does not have, the installed CLI wins and the delta
is recorded (see `RECORDED_FLAG_DELTAS`).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

# Run as a script (`py -3.12 tools/providers/frontier_provider_recon.py`) and Python puts THIS
# directory on sys.path, not the repo root. Bootstrap the root exactly as the sibling emitters in
# tools/live/ do, so the import below works under pytest and as a script alike.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The ONE trust/emission policy for these two provider CLIs, built at 18B `.adapter` and shared
# with the headless adapters (`adapters/frontier/grok_build.py`, `.../antigravity.py`). This module
# RE-EXPORTS it under the names it has always published rather than keeping a second copy: a policy
# stated twice is how drift starts, and the 18A gate was reopened twice over findings of exactly
# that shape. The import is deliberately NOT lazy/exception-wrapped like the control-plane lookups
# below: those are diagnostics ABOUT the application, and a broken one must not crash the tool that
# reports it — whereas the credential scrub and the argv guard are load-bearing, and a diagnostic
# that could not load them must not run at all (fail closed).
from adapters.frontier import provider_cli_common as _P  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Provider identity (operator directive §8). Ids are the ONLY spelling used programmatically;
# display names are the ONLY spelling shown to the operator (§14 — never "Gemini CLI" for the
# Google AI Pro path).
# ---------------------------------------------------------------------------------------------
# DELIBERATE duplication of `control_plane.profiles.live_authorization`'s exports (which exist so
# no other module spells these as literals). This module is a DIAGNOSTIC: every control-plane import
# it makes is lazy and exception-wrapped so a broken control plane cannot crash the tool that
# diagnoses it — a module-level import would defeat that. The copies are pinned equal by
# `test_recon_ids_equal_the_control_plane_exports`, so they cannot drift silently.
GROK_PROVIDER = "grok_build"
ANTIGRAVITY_PROVIDER = "google_antigravity"

GROK_DISPLAY = "Grok Build"
ANTIGRAVITY_DISPLAY = "Gemini · Antigravity"

# Subscription resources (operator directive §12) — SEPARATE, allowance 1 each, never merged.
# Declared here so 18A's status output can already name the lease resource it will consult;
# the governor registration itself is 18B.
GROK_SUBSCRIPTION = "grok_build_subscription"
ANTIGRAVITY_SUBSCRIPTION = "google_antigravity_subscription"
DEFAULT_TERMINAL_ALLOWANCE = 1

# Install commands — RECORDED, never executed by this module (the runner executes them only
# under an explicit `-InstallMissing`, operator directive §4).
GROK_INSTALL_COMMAND = "npm install -g @xai-official/grok"
ANTIGRAVITY_INSTALL_COMMAND = "irm https://antigravity.google/cli/install.ps1 | iex"

# Probe tokens (operator directive §7). The probe asks for an exact string back; acceptance
# requires it, so a truncated/garbled/refused answer cannot pass.
GROK_PROBE_TOKEN = "GROK_PROVIDER_OK"
ANTIGRAVITY_PROBE_TOKEN = "GEMINI_PROVIDER_OK"

# §6 status states. Kept as a closed set so a typo cannot invent a state the runner then
# renders as if it were meaningful.
STATE_AVAILABLE = "AVAILABLE"
STATE_NOT_INSTALLED = "NOT_INSTALLED"
STATE_AUTH_REQUIRED = "AUTH_REQUIRED"
STATE_PROBE_FAILED = "PROBE_FAILED"
STATE_UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
PROVIDER_STATES = frozenset({STATE_AVAILABLE, STATE_NOT_INSTALLED, STATE_AUTH_REQUIRED,
                             STATE_PROBE_FAILED, STATE_UNSUPPORTED_VERSION})

STATE_REGISTERED = "REGISTERED"
STATE_NOT_REGISTERED = "NOT_REGISTERED"

# Auth-probe states. Deliberately three-valued: a CLI with no offline auth-reporting surface
# yields UNVERIFIED, which is NOT the same as authenticated and NOT the same as auth-required.
AUTH_AUTHENTICATED = _P.AUTH_AUTHENTICATED
AUTH_REQUIRED = _P.AUTH_REQUIRED
AUTH_UNVERIFIED = _P.AUTH_UNVERIFIED
AUTH_PROBE_FAILED = _P.AUTH_PROBE_FAILED

# Outcome classes from `classify_provider_outcome`.
OUTCOME_SUCCESS = _P.OUTCOME_SUCCESS
OUTCOME_AUTH_REQUIRED = _P.OUTCOME_AUTH_REQUIRED
OUTCOME_USAGE_LIMIT = _P.OUTCOME_USAGE_LIMIT
OUTCOME_FAILED = _P.OUTCOME_FAILED
OUTCOME_TIMEOUT = _P.OUTCOME_TIMEOUT
OUTCOME_NOT_SPAWNABLE = _P.OUTCOME_NOT_SPAWNABLE

# Minimum parseable versions. As with the Codex adapter, the bar is "a real, parseable release",
# not a brittle exact build; an unparseable version fails CLOSED to UNSUPPORTED_VERSION.
MIN_GROK_VERSION: tuple[int, int, int] = (0, 1, 0)
MIN_ANTIGRAVITY_VERSION: tuple[int, int, int] = (0, 1, 0)

# ---------------------------------------------------------------------------------------------
# Credential isolation (§13) and the argv emission policy (§11) — RE-EXPORTED, never restated.
# ---------------------------------------------------------------------------------------------
# These names have been this module's published surface since 18A and stay exactly that; the
# definitions moved to `adapters/frontier/provider_cli_common.py` at 18B `.adapter`, where the
# headless adapters use the SAME objects. `is` -identity between the two is pinned by
# `tests/unit/test_op12_frontier_adapters.py::TestNoPolicyDrift`, so a second copy cannot reappear.
#
# What 18B changed in the policy itself (both closing 18A-gate findings, both widenings):
#   * **U249** — the guard now compares flags dash-normalised, so `-dangerously-skip-permissions`
#     and `-mode=accept-edits` are refused like their double-dash twins. `agy --help` is Go
#     `flag`-package output, where the two spellings are interchangeable.
#   * **U250** — the endpoint-override (`--xai-api-base-url`, `--cli-chat-proxy-base-url`,
#     `--grok-ws-url`, `--grok-ws-origin`, `--leader-socket`), agent-identity (`--agent`,
#     `--agent-profile`), auth-initiating (`--reauth`) and state-creating (`--worktree`,
#     `--worktree-ref`, `--new-project`) flags the recorded capture documents are refused too. The
#     env scrub already removed `XAI_API_BASE_URL`; the argv twins now agree with it.
# `--system-prompt-override` and `--rules` remain deliberately OUT of the permission list (U235) —
# they are instruction injection, not permission widening, and live in the separately-named
# `assert_no_untrusted_instruction_args` guard the adapters call.
_PROVIDER_CREDENTIAL_ENV_KEYS = _P.PROVIDER_CREDENTIAL_ENV_KEYS
_CREDENTIAL_KEY_PREFIXES = _P.CREDENTIAL_KEY_PREFIXES
_CREDENTIAL_KEY_SUBSTRINGS = _P.CREDENTIAL_KEY_SUBSTRINGS
_PRESERVED_PROVIDER_CONFIG_KEYS = _P.PRESERVED_PROVIDER_CONFIG_KEYS
_FORBIDDEN_PROVIDER_ARGS = _P.FORBIDDEN_PROVIDER_ARGS
_FORBIDDEN_PERMISSION_MODES = _P.FORBIDDEN_PERMISSION_MODES
_MODE_FLAGS = _P.MODE_FLAGS

# The mode each provider's probe is PINNED to. Pinning it means the probe cannot inherit whatever
# a node-controlled config file defaults to (§11) — that, and only that, is what the pin buys.
#
# Two corrections the round-3 audit was right about. First, this is NOT containment in the
# invariant-29 sense and I-29 must not be cited in its support: I-29 says never trust the harness,
# and a permission mode is an argument the harness itself honours. OS/process-layer containment
# for provider children is unbuilt (U25, owed). Second, a pin is a REASONED choice, not a
# documented ranking: `agy`'s enum is only (accept-edits, plan), so plan is plainly the narrower
# of two; `grok`'s enum (default, acceptEdits, auto, dontAsk, bypassPermissions, plan) is not
# ranked by its help, and calling plan "the most restrictive value" was an inference stated as
# evidence — the same fabrication line this file draws when it refuses to invent a `--sandbox`
# profile value (round-3 spec-audit MEDIUM-6 / MINOR-16).
#
# BOTH PINS WERE MEASURED LIVE, 2026-08-02 (18E `.live.shape`, U305/U310), and NEITHER moved.
# Antigravity's `plan` was ACCEPTED: a flat `{"response": "GEMINI_PROVIDER_OK\n", …}` document, the
# narrower of its two modes, answering. Grok's `plan` run exited ZERO and the CLI SAID NOTHING —
# `{"text": "", "stopReason": "cancelled", …}` with the token only in the `thought` trace — which
# read at first as plan mode having no approval channel to hand a plan to. A SECOND governed live
# probe with `--permission-mode default` tested exactly that and cancelled IDENTICALLY, so the mode
# is not the cause and the pin stays where it is: moving it would have been a widening bought with
# a refuted hypothesis. The cause of the cancellation is open and owned by U310.
#
# BOTH RESTORED at Phase 19 unit 1: the antigravity pin by operator ruling OP-13, the grok pin by
# U327's settlement (D-P19-1). The two live receipts above are still on disk and still say this.
GROK_PROBE_PERMISSION_MODE = "plan"      # `grok --permission-mode [default|acceptEdits|auto|dontAsk|bypassPermissions|plan]`
ANTIGRAVITY_PROBE_MODE = "plan"          # `agy --mode (accept-edits, plan)`

# Secret-shaped material removed from every diagnostic string before it can reach a log, a
# receipt, or the operator's console (§13 — bounded diagnostics, never credential material).
# Re-exported with the rest of the policy; see the note above.
_SECRET_PATTERNS = _P.SECRET_PATTERNS
MAX_DIAGNOSTIC_CHARS = _P.MAX_DIAGNOSTIC_CHARS

is_provider_credential_env_key = _P.is_provider_credential_env_key
scrub_provider_env = _P.scrub_provider_env
redact_diagnostics = _P.redact_diagnostics

# ---------------------------------------------------------------------------------------------
# Exit-code-first outcome classification (operator directive §6 — the binding lesson)
# ---------------------------------------------------------------------------------------------
# Also shared, and this one most of all: a provider whose diagnostic text mentions historical login
# or quota language while the process exits successfully is AVAILABLE. Two copies of that rule
# would be two chances to lose it.
_AUTH_MARKERS = _P.AUTH_MARKERS
_USAGE_MARKERS = _P.USAGE_MARKERS
ProviderOutcome = _P.ProviderOutcome
classify_provider_outcome = _P.classify_provider_outcome
parse_version = _P.parse_version
#: W-52: the declaration reader both probes share (line + tuple from one pass).
extract_version = _P.extract_version


# ---------------------------------------------------------------------------------------------
# Model enumeration — provider-specific, conservative, fail-closed (operator directive §8)
# ---------------------------------------------------------------------------------------------
# Shared with the adapters, for the reason the whole policy is: the picker and this diagnostic must
# read a provider's own listing the SAME way, or one of them will offer a slug the other rejected.
# A model id we will accept from a CLI listing; anything else (prose, banners, blank lines) is
# discarded rather than guessed at.
_MODEL_SLUG_RE = _P.MODEL_SLUG_RE
ModelInventory = _P.ModelInventory
parse_grok_models = _P.parse_grok_models
#: W-49: the ONE models-call auth policy, re-exported so this module's callers and tests see
#: the same function object the adapter path uses -- two names for one implementation is how a
#: shared policy quietly becomes two again.
classify_models_call = _P.classify_models_call
parse_antigravity_models = _P.parse_antigravity_models

# ---------------------------------------------------------------------------------------------
# Probe argv construction (operator directive §7) — pure, testable, never auto-approving
# ---------------------------------------------------------------------------------------------
# The guard is the shared one (see the policy note above). It normalises `--flag=value` into
# (name, value) pairs AND strips leading dashes before comparing, so neither the inline form nor a
# single-dash spelling can walk through a check this module describes as structural (U249).
_assert_no_forbidden = _P.assert_no_forbidden_provider_args


def build_grok_probe_command(executable: str = "grok", *, repo_root: str | Path = REPO_ROOT,
                             prompt: str | None = None, model: str | None = None,
                             output_format: str = "json") -> list[str]:
    """Argv for the ONE harmless Grok probe (operator directive §7.1).

    Uses the flags THIS host's `grok --help` actually documents:
      `grok --cwd <root> --permission-mode plan --no-memory [-m <model>] --output-format json ...`

    Recorded delta (§2 — the installed surface is authoritative): the operator directive's
    example carried `--no-auto-update`, which **this build of `grok` does not have**; including
    it would abort the probe on an unknown flag. It is therefore omitted, not silently
    substituted.

    `--permission-mode plan` is pinned explicitly, so a node-controlled `~/.grok/config.toml`
    cannot supply a permissive default instead (§11); no `--allow` rule is emitted at all (U340).
    The enum this build documents (default, acceptEdits, auto, dontAsk,
    bypassPermissions, plan) is NOT ranked by its help, so `plan` is a reasoned choice and is not
    described as the documented-most-restrictive value (round-3 spec-audit MINOR-16). It was TESTED
    against `default` on live evidence at 18E and kept; Phase 19 unit 1 re-read those receipts when
    settling U327 and kept it again — see `GROK_PROBE_PERMISSION_MODE` and U310.

    What it is NOT: containment in the invariant-29 sense. It is an argument the harness itself
    honours, and I-29 says never trust the harness — OS/process-layer containment for provider
    children is unbuilt in this repo (U25, owed). The enforced facts here are narrower and worth
    stating plainly: no auto-approval or tool-widening flag can be emitted (`_assert_no_forbidden`),
    and `_repo_state_snapshot` DETECTS tracked-tree changes afterwards — "structurally" was the
    word this used to reach for, and the shared guard's own comment now disclaims it: the list is
    ENUMERATED, not exhaustive-by-construction. Grok's `--sandbox <PROFILE>`
    would be the stronger lever; its help enumerates no profile values on this build, so choosing
    one would be fabrication — recorded in `RECORDED_FLAG_DELTAS` rather than silently skipped."""
    text = prompt if prompt is not None else f"Reply with exactly: {GROK_PROBE_TOKEN}"
    argv = [executable, "--cwd", str(repo_root), "--permission-mode", GROK_PROBE_PERMISSION_MODE,
            "--no-memory", "--no-subagents", "--disable-web-search"]
    if model and model.strip():
        argv += ["-m", model.strip()]
    argv += ["--output-format", output_format]
    # Guard the FLAGS, then append the prompt — the ordering the 18B adapters use. Guarding after
    # the prompt was harmless while the guard matched whole double-dash tokens; once U249 made it
    # dash-normalising, an operator `-Prompt agents` began colliding with `--agents` and the probe
    # refused its own benign prompt (gate-validator finding 8). The prompt is a VALUE in an argv
    # list, so it can never be parsed as a flag by the child.
    _assert_no_forbidden(argv)
    argv += ["-p", text]
    return argv


def build_antigravity_probe_command(executable: str = "agy", *, prompt: str | None = None,
                                    model: str | None = None,
                                    output_format: str = "json") -> list[str]:
    """Argv for the ONE harmless Antigravity probe (operator directive §7.2).

    Uses the flags THIS host's `agy --help` documents:
      `agy --mode plan [--model <model>] --output-format json -p "<prompt>"`

    Recorded deltas: `agy` has **no `--cwd` flag**, so the workspace is bound by the child
    process's working directory (`subprocess_runner(cwd=...)`, which `run_probe` sets to the repo
    root) plus the existing `--add-dir` when 18B binds a node workspace.

    Mode pin (NOT containment): `--mode plan` is pinned — the narrower of the two values this
    CLI's own enum offers (`accept-edits, plan`) — so a node-controlled config cannot supply the
    permissive one instead. It is an argument the harness honours, not enforcement, and I-29 says
    never trust the harness; this heading used to read "Containment:" and that was wrong
    (round-3 spec-audit MEDIUM-6). `--sandbox` exists but its help states only "terminal
    restrictions" without saying what it restricts, so no claim is made for it either. What IS
    enforced here: no forbidden flag can be emitted (`_assert_no_forbidden` refuses
    `--dangerously-skip-permissions` and its single-dash and `=`-joined spellings, from an
    ENUMERATED list — not an exhaustive-by-construction one) and `_repo_state_snapshot` DETECTS
    tracked-tree changes afterwards. OS-layer containment for provider children remains owed (U25)."""
    text = prompt if prompt is not None else f"Reply with exactly: {ANTIGRAVITY_PROBE_TOKEN}"
    argv = [executable, "--mode", ANTIGRAVITY_PROBE_MODE]
    if model and model.strip():
        argv += ["--model", model.strip()]
    argv += ["--output-format", output_format]
    _assert_no_forbidden(argv)          # flags only — see the Grok builder on ordering (U249)
    argv += ["-p", text]
    return argv


# All three are the shared accessors: the adapters read a provider's structured output with the
# same rules this diagnostic does, so "the CLI answered" cannot mean two different things.
#
# `extract_probe_text` is the BEST-EFFORT reader (display, `response_excerpt`) and keeps its
# whole-document fallback. `extract_probe_response_field` is the STRICT one and is the only reader
# `accept_probe` may use: U238 hole 2 was that acceptance ran on the best-effort reader, so
# `{"status":"done","debug":"GROK_PROVIDER_OK"}` — a document in which the CLI said nothing —
# certified the provider. Two names, two jobs, neither tightened or loosened by accident.
extract_probe_text = _P.extract_provider_text
extract_probe_response_field = _P.extract_provider_response_field
structured_error_of = _P.structured_error_of
# The instrument for U305: what the strict reader above was actually pointed at. Structure only —
# key names, types, paths, and where the token sits — never a value, because the shape is published.
describe_probe_document = _P.describe_provider_document


@dataclass(frozen=True)
class ProbeVerdict:
    """Acceptance of one harmless live probe (operator directive §7): exit zero AND structured
    output parsed AND the exact token present AND the repository unchanged. Any missing condition
    is a refusal with the reason recorded."""

    accepted: bool
    provider: str
    token: str
    token_seen: bool
    structured_output_parsed: bool
    repo_unchanged: bool
    outcome: ProviderOutcome
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"accepted": self.accepted, "provider": self.provider, "token": self.token,
                "token_seen": self.token_seen,
                "structured_output_parsed": self.structured_output_parsed,
                "repo_unchanged": self.repo_unchanged, "outcome": self.outcome.as_dict(),
                "reason": self.reason}


def _token_answered(response: str, token: str, echoed_prompt: str) -> bool:
    """True only if the model ANSWERED with the token rather than echoing the request.

    Exact-substring removal of the prompt was not enough: a re-wrapped, re-cased, or re-spaced
    echo left the prompt unmatched and the token intact, so a pure echo still passed
    (gate-validator F1 / spec-audit N-8). Both sides are therefore normalised — case-folded, all
    whitespace collapsed — before the prompt is removed, and the token must survive that removal.

    A model that answers correctly says the token (optionally with punctuation or a short
    courtesy); a model that parrots the instruction VERBATIM has nothing left once the instruction
    is taken out. Where the prompt itself is degenerate (an operator `-Prompt` that is nothing but
    the token), the removal would erase a genuine answer too — so that case falls back to
    requiring the token, which is exactly what such a prompt asked for.

    "Verbatim" is the honest limit and is stated rather than glossed: the subtraction removes a
    CONTIGUOUS occurrence of the folded prompt, so an echo that PARAPHRASES — inserting a word, as
    in `Reply with exactly the following: GROK_PROVIDER_OK` — survives it and is still accepted.
    That is a narrower hole than the one U238 named and it is recorded as U304, not silently
    absorbed into a claim of having defeated echoes in general.

    U238 hole 1, closed at 18E before the live legs: whitespace-collapse is not whitespace
    DELETION, and it says nothing about punctuation. `Reply with exactly:GROK_PROVIDER_OK`,
    `Reply with exactly - GROK_PROVIDER_OK`, `**Reply with exactly:** GROK_PROVIDER_OK` and a
    letter-spaced instruction were all MEASURED as accepted — six shapes of pure echo certifying a
    provider that answered nothing. So the two questions are now asked with two folds:

      * PRESENCE of the token is judged on the whitespace-collapsed fold, UNCHANGED — which means
        unchanged in its laxity too: that fold case-folds, so `grok_provider_ok` in lower case has
        always passed and still does. §17's "exactly" is therefore enforced up to case and
        surrounding whitespace, not to the byte. The point of leaving it alone is that the stricter
        fold below would read `GROK-PROVIDER-OK` as the token, which is further from §17 than
        case-insensitivity is: that fold is for subtracting an echo, never for recognising an
        answer.
      * SUBTRACTION of the echo is judged on an alphanumeric-only fold, where every space, dash,
        colon, asterisk and quote is gone from both sides — so no rewriting of the instruction's
        punctuation can hide it from the removal, and the token must survive anyway."""
    def norm(s: str) -> str:
        return " ".join((s or "").split()).casefold()

    def fold(s: str) -> str:
        """Alphanumerics only, case-folded — the echo-subtraction fold. Deliberately destructive:
        anything that is not a letter or a digit is a formatting choice a model may make freely,
        and none of them may change whether a restatement is recognised as a restatement."""
        return "".join(ch for ch in (s or "") if ch.isalnum()).casefold()

    n_response, n_token, n_prompt = norm(response), norm(token), norm(echoed_prompt)
    if not n_token or n_token not in n_response:
        return False
    if n_prompt == n_token:          # degenerate prompt: nothing to subtract
        return True
    f_response, f_token, f_prompt = fold(response), fold(token), fold(echoed_prompt)
    if not f_prompt or f_prompt == f_token:
        # Nothing to subtract: an all-punctuation prompt, or one that reduces to the token itself.
        # `str.replace("", ...)` would shred the response, and refusing on that would be a wrong
        # refusal — the degenerate case above, reached by the stricter fold.
        return True
    return f_token in f_response.replace(f_prompt, " ")


def accept_probe(provider: str, token: str, *, exit_code: int | None, stdout: str = "",
                 stderr: str = "", git_status_before: str | None = None,
                 git_status_after: str | None = None, timed_out: bool = False,
                 spawn_error: str | None = None, prompt: str | None = None) -> ProbeVerdict:
    """Decide whether a provider probe is ACCEPTED. All four conditions must hold (§7):

      1. exit code zero (via `classify_provider_outcome` — exit-code-first);
      2. structured output parses;
      3. **the model's own response** contains the exact probe token;
      4. the repository state snapshot is byte-identical before and after.

    Condition 3 is deliberately narrow. The probe prompt CONTAINS the token, so an earlier version
    that searched the whole transcript accepted a CLI that merely echoed the request back —
    `{"result": "", "prompt": "Reply with exactly: GROK_PROVIDER_OK"}` passed (gate-validator R5).
    The token is now sought only in the extracted response, with the prompt text removed from it
    first, so a certified probe means the model answered.

    "The extracted response" means `extract_probe_response_field` — a recognised response field, or
    the whole document when that document IS a bare JSON string, or nothing — and not the
    best-effort `extract_probe_text` this used to call. That was U238 hole 2: the best-effort reader
    falls back to the whole JSON document, so a token in any field at all
    (`{"status":"done","debug":"GROK_PROVIDER_OK"}`) read as an answer.

    Both holes were closed at 18E `.hardening`, before the first in-Electron live acceptance LEG ran
    (directive §17.2(2)). Two things that closure does NOT claim, because they are not true:

      * The operator's own recon probe of 2026-08-02 was accepted by the PRE-FIX code — §17.2 records
        it as having returned the exact tokens, and the directive's own words for this work are
        "hardening the acceptance, not repairing a result". A live verdict already exists and it
        rests on the old reader; what is guaranteed is that no verdict taken from here on does.
      * Neither provider's real `-p --output-format json` document has been read against the strict
        reader — `docs/evidence/live/` holds help/version/models captures and no probe response. If
        a CLI nests its answer (`{"response": {"text": …}}`) or emits content blocks, acceptance now
        REFUSES a genuine live answer. That direction is the safe one and the ordering was ordered,
        but it is an open assumption (U305), not a verified fact, until the live legs run.

    Condition 4 compares snapshots the CALLER captured; `None` for either means "not captured",
    which is treated as NOT verified — refused rather than assumed clean. What that snapshot does
    and does not cover is `_repo_state_snapshot`'s business, and it is documented there."""
    outcome = classify_provider_outcome(exit_code, stdout, stderr, timed_out=timed_out,
                                        spawn_error=spawn_error,
                                        structured_error=structured_error_of(stdout))
    parsed = True
    try:
        json.loads((stdout or "").strip())
    except (ValueError, TypeError):
        parsed = False
    response = extract_probe_response_field(stdout)      # strict reader only (U238 hole 2)
    echoed = prompt if prompt is not None else f"Reply with exactly: {token}"
    token_seen = _token_answered(response, token, echoed)
    repo_unchanged = (git_status_before is not None and git_status_after is not None
                      and git_status_before == git_status_after)
    reasons: list[str] = []
    if not outcome.ok:
        reasons.append(f"process outcome {outcome.outcome} ({outcome.basis})")
    if not parsed:
        reasons.append("structured output did not parse")
    if not token_seen:
        # Two DIFFERENT things go wrong here and an operator has to be able to tell them apart:
        # the CLI said something that was not an answer, or the CLI's document has no place for it
        # to have said anything. Both refuse — but reporting the second as "a prompt echo does not
        # count" would send a reader hunting for an echo in a document whose token is sitting in a
        # `debug` field. The token IS in the transcript in that case, which is exactly why the
        # reason has to name the field set rather than the token.
        if parsed and not response:
            reasons.append(
                "the CLI's structured output carried no recognised response field "
                f"({'/'.join(_P.PROVIDER_RESPONSE_KEYS)}), so the model's own response is empty; "
                f"{token} appearing elsewhere in the document is not an answer")
        else:
            reasons.append(f"the model's own response did not contain {token} "
                           f"(a prompt echo does not count)")
    if not repo_unchanged:
        reasons.append("the repository state snapshot was not captured identically before and after")
    accepted = not reasons
    return ProbeVerdict(accepted, provider, token, token_seen, parsed, repo_unchanged, outcome,
                        "accepted" if accepted else "; ".join(reasons))


# ---------------------------------------------------------------------------------------------
# Provider specs + status assembly
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    display: str
    command: str
    selector: str                     # `-Provider` value in the PowerShell runner
    install_command: str
    login_command: tuple[str, ...]    # argv the runner runs for `-Action login` (interactive)
    models_command: tuple[str, ...]
    version_args: tuple[str, ...]
    probe_token: str
    subscription_resource: str
    terminal_allowance: int
    min_version: tuple[int, int, int]
    interactive_supported: bool
    headless_supported: bool
    structured_output_supported: bool
    auth_reporting_command: tuple[str, ...] | None   # None ⇒ no offline auth surface ⇒ UNVERIFIED
    #: W-49 / [[U463]]. The spec NAMES its own listing parser. `probe_status` used to choose with
    #: `parse_grok_models(out) if spec.provider == GROK_PROVIDER else parse_antigravity_models(out)`,
    #: so every provider that was not grok silently got the ANTIGRAVITY parser by falling through
    #: the `else` -- a provider read by a parser written for a different format, which is the exact
    #: class W-44 repaired. A required field cannot be fallen through.
    parse_models: Any
    notes: str = ""


GROK_SPEC = ProviderSpec(
    provider=GROK_PROVIDER, display=GROK_DISPLAY, command="grok", selector="grok",
    install_command=GROK_INSTALL_COMMAND,
    # `grok login` IS present on this build — the captured `grok --help` lists it plainly
    # ("login        Sign in to Grok"), with `--oauth` / `--device-auth` modes on
    # `grok login --help`. An earlier note here called it "hidden from the top-level Commands
    # list", which the very capture it cites contradicts (round-3 spec-audit MINOR-11 /
    # gate-validator A-2). The runner runs it interactively and lets Grok drive its own browser
    # flow (§5.1).
    login_command=("login",),
    models_command=("models",),
    version_args=("--version",),
    probe_token=GROK_PROBE_TOKEN,
    subscription_resource=GROK_SUBSCRIPTION,
    terminal_allowance=DEFAULT_TERMINAL_ALLOWANCE,
    min_version=MIN_GROK_VERSION,
    parse_models=parse_grok_models,
    interactive_supported=True,      # `grok` with no args is the Grok Build TUI
    headless_supported=True,         # `-p/--single`, plus `grok agent stdio` (ACP)
    structured_output_supported=True,  # `--output-format json|streaming-json|streaming-messages-json`
    auth_reporting_command=("models",),  # prints "You are logged in with <service>."
    notes="`grok models` doubles as the auth-reporting surface on this build; no `--no-auto-update` "
          "flag exists here (operator directive example superseded by the installed surface).",
)

ANTIGRAVITY_SPEC = ProviderSpec(
    provider=ANTIGRAVITY_PROVIDER, display=ANTIGRAVITY_DISPLAY, command="agy", selector="gemini",
    install_command=ANTIGRAVITY_INSTALL_COMMAND,
    # No login subcommand exists: `agy` starts the TUI and Antigravity drives its own Google
    # browser sign-in (§5.2). The runner therefore launches the TUI for `-Action login`.
    login_command=(),
    models_command=("models",),
    version_args=("--version",),
    probe_token=ANTIGRAVITY_PROBE_TOKEN,
    subscription_resource=ANTIGRAVITY_SUBSCRIPTION,
    terminal_allowance=DEFAULT_TERMINAL_ALLOWANCE,
    min_version=MIN_ANTIGRAVITY_VERSION,
    parse_models=parse_antigravity_models,
    interactive_supported=True,      # `agy` with no args is the Antigravity TUI
    headless_supported=True,         # `-p/--print` with `--output-format text|json|stream-json`
    structured_output_supported=True,
    auth_reporting_command=None,     # nothing reports auth state offline ⇒ UNVERIFIED, never assumed
    notes="No offline auth-state surface: authentication is only confirmable by the live probe. "
          "No `--cwd`; workspace binding is the child's working directory (+ `--add-dir`).",
)

PROVIDER_SPECS: dict[str, ProviderSpec] = {GROK_PROVIDER: GROK_SPEC,
                                           ANTIGRAVITY_PROVIDER: ANTIGRAVITY_SPEC}
SELECTOR_TO_PROVIDER: dict[str, str] = {"grok": GROK_PROVIDER, "gemini": ANTIGRAVITY_PROVIDER}

# Deltas between the operator directive's assumed command surface and the installed one. Recorded
# because §2 makes the installed CLI authoritative and the loop never silently "fixes" a directive.
RECORDED_FLAG_DELTAS: tuple[dict[str, str], ...] = (
    {"provider": GROK_PROVIDER, "directive": "§7.1/§10 `--no-auto-update`",
     "installed": "flag absent from `grok --help` on this build",
     "resolution": "omitted from every built argv; recorded, never silently substituted"},
    {"provider": GROK_PROVIDER, "directive": "§10 `--output-format streaming-json` for live panes",
     "installed": "present: plain | json | streaming-json | streaming-messages-json",
     "resolution": "available to 18B; 18A probes with `json` (single-shot acceptance)"},
    {"provider": GROK_PROVIDER, "directive": "§5.1 `grok login`",
     "installed": "present and listed in `grok --help` (`login  Sign in to Grok`); `--oauth` / "
                  "`--device-auth` modes on `grok login --help`",
     "resolution": "runner runs it interactively; no credential is read"},
    {"provider": ANTIGRAVITY_PROVIDER, "directive": "§10 `--output-format stream-json`",
     "installed": "present: text | json | stream-json (spelling confirmed)",
     "resolution": "18A probes with `json`; 18B may use `stream-json` for live panes"},
    {"provider": GROK_PROVIDER, "directive": "§7.2-equivalent restrictive sandbox flag",
     "installed": "`--sandbox <PROFILE>` exists (env form GROK_SANDBOX) but its help enumerates "
                  "NO profile values",
     "resolution": "NOT used — passing an invented profile name would be fabrication; the probe "
                   "pins `--permission-mode plan` instead and the gap is recorded. `GROK_SANDBOX` "
                   "is deliberately preserved through the env "
                   "scrub so an operator who sets it keeps it"},
    {"provider": ANTIGRAVITY_PROVIDER, "directive": "§7.2 optional read-only sandbox flag",
     "installed": "`--sandbox` exists but its help states only 'terminal restrictions'",
     "resolution": "NOT used by the probe — an unverified containment claim is worse than none; "
                   "18B decides on evidence"},
    {"provider": ANTIGRAVITY_PROVIDER, "directive": "workspace flag equivalent to `--cwd`",
     "installed": "no `--cwd`; `--add-dir` adds workspace directories",
     "resolution": "workspace bound by the child's working directory; recorded for 18B"},
)


@dataclass
class ProviderStatus:
    """Everything operator directive §6 requires reported, per provider, independently."""

    provider: str
    display: str
    command: str
    command_found: bool = False
    executable: str | None = None
    version: str | None = None
    version_tuple: tuple[int, int, int] | None = None
    state: str = STATE_NOT_INSTALLED
    state_caveat: str = ""          # non-empty ⇒ the state is narrower than it reads
    # AVAILABLE *and* the CLI itself reported a signed-in session. Named for what it measures:
    # an earlier `launch_ready` claimed readiness for a provider that is NOT_REGISTERED, holds no
    # lease, and whose live legs the switch DENIES — three separate reasons it is not ready to
    # launch anything (spec-audit N-5).
    auth_confirmed: bool = False
    auth_state: str = AUTH_UNVERIFIED
    auth_detail: str = ""
    models: tuple[str, ...] = ()
    default_model: str | None = None
    model_note: str = ""
    headless_supported: bool = False
    interactive_supported: bool = False
    structured_output_supported: bool = False
    subscription_resource: str = ""
    terminal_allowance: int = DEFAULT_TERMINAL_ALLOWANCE
    lease_state: str = "not_registered"
    registration_state: str = STATE_NOT_REGISTERED
    registration_detail: str = ""
    install_command: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider, "display": self.display, "command": self.command,
            "command_found": self.command_found, "executable": self.executable,
            "version": self.version,
            "version_tuple": list(self.version_tuple) if self.version_tuple else None,
            "state": self.state, "state_caveat": self.state_caveat,
            "auth_confirmed": self.auth_confirmed,
            "auth_state": self.auth_state, "auth_detail": self.auth_detail,
            "models": list(self.models), "default_model": self.default_model,
            "model_note": self.model_note,
            "headless_supported": self.headless_supported,
            "interactive_supported": self.interactive_supported,
            "structured_output_supported": self.structured_output_supported,
            "subscription_resource": self.subscription_resource,
            "terminal_allowance": self.terminal_allowance, "lease_state": self.lease_state,
            "registration_state": self.registration_state,
            "registration_detail": self.registration_detail,
            "install_command": self.install_command, "diagnostics": self.diagnostics,
            "notes": self.notes,
        }


# A runner is any callable (argv) -> (exit_code|None, stdout, stderr, timed_out, spawn_error).
RunResult = tuple[int | None, str, str, bool, str | None]
Runner = Callable[[Sequence[str]], RunResult]


def subprocess_runner(timeout_s: float = 90.0, cwd: str | Path | None = None) -> Runner:
    """Real runner: invokes a provider CLI with stdin CLOSED (an inherited non-TTY stdin makes a
    TUI-capable CLI block forever and turns a probe into a timeout) and a credential-scrubbed
    environment.

    Used for metadata calls only (`--version`, `--help`, `models`). It is NOT the probe's runner:
    since 18C `.probe-path`, `run_probe` executes its one live prompt through `_supervised_runner`,
    which holds a node identity, an I-X3 lease and a process-tree boundary — none of which this
    runner has (U234). The claim in this docstring has now been wrong in BOTH directions across two
    phases (it once said "benign metadata only" while the probe used it, spec-audit F8; it then
    said it carried the live prompt after the probe stopped using it, 18C spec-audit MEDIUM-4), so
    `test_the_metadata_runner_is_not_the_probes_runner` pins the current statement to the code."""

    def run(argv: Sequence[str]) -> RunResult:
        try:
            proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout_s,
                                  check=False, stdin=subprocess.DEVNULL,
                                  env=scrub_provider_env(), cwd=str(cwd) if cwd else None,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return None, "", "", True, None
        except (FileNotFoundError, OSError) as exc:
            return None, "", "", False, f"{type(exc).__name__}: {exc}"
        return proc.returncode, proc.stdout or "", proc.stderr or "", False, None

    return run


def which_provider(spec: ProviderSpec) -> str | None:
    """Resolve the provider executable through normal PATH discovery. Never a hardcoded npm
    roaming path (operator directive §4.1) — the resolved path is reported, not assumed."""
    for candidate in (spec.command, f"{spec.command}.cmd", f"{spec.command}.exe",
                      f"{spec.command}.ps1"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def provider_registration(provider: str) -> tuple[str, str]:
    """Is this provider wired into the application's EXISTING registries yet? Reports
    (state, detail) from the two sources that actually decide it: the code-pinned
    live-authorization scope, and the pane picker's own registered-provider set.

    **What changed at 18B `.scope`, and why.** The second source used to be the frozen
    `node.schema.json` `adapter` enum. That check could not pass for either provider while U227
    was unruled: the enum is frozen at Phase 0 AND pinned by Architecture Plan §9.1, so extending
    it was an operator-reserved canonical amendment that directive §17 put out of bounds for that
    phase. Leaving it as a REGISTRATION gate would have made the diagnostic permanently report a
    cause 18B was forbidden to fix, while hiding the cause it can — so the schema fact is now
    reported as a DECLARED note (never removed, never softened) and the gating source is the
    product-layer registry the operator actually selects from. While `.scope` was the head of the
    track that meant both new providers read NOT_REGISTERED, for the true reason: the picker could
    not offer them yet.

    **The "never will" is gone, and its removal is the point (18D, validator MAJOR-1).** This
    docstring said the amendment "never will" pass — a prediction about an operator decision,
    written by the app. The operator ruled OP-12.1 on 2026-08-01: `node@1.1` admits both ids and
    `NodeRegistry.register` accepts them. The DECLARED schema note below is now true in the other
    direction, and the gating sources are unchanged — an admissible vocabulary is not a
    registration, and nothing here is wired to create a node record.

    **Corrected at the 18B close (validator MAJOR-1 / spec-audit MEDIUM-2).** `.picker` landed the
    offer and the dispatch, so both providers now read **REGISTERED** and this docstring — the one
    attached to the function whose return value disproved it — said the opposite for three commits.
    Note precisely what REGISTERED asserts: the id is in a recorded operator ruling's scope AND the
    picker offers it AND the pane authorizer will dispatch it. It does NOT assert that a live leg
    will run (the operator's own live switch still has to cite the authorizing row), and it does NOT
    assert a schema-valid node record EXISTS — only the vocabulary note says whether one could, and
    since OP-12.1 the answer for these two is yes (`node@1.1`) while the count remains zero. That is
    why the note is appended to every answer rather than folded into the verdict.

    Each lookup contributes a BOOLEAN, and an unreadable source contributes `False`. An earlier
    version accumulated prose reasons and derived the verdict by prefix-matching them, so two
    failed lookups produced REGISTERED — a fail-OPEN verdict claiming a lease no governor holds
    (spec-audit F-1). Unverifiable is not registered."""
    checks: list[tuple[bool, str]] = []
    try:
        # U230: read through the PUBLIC accessor, not `_AUTHORIZED_PROVIDERS`. Membership means
        # "some recorded operator ruling covers this id" — the operator's own live switch still
        # has to cite the authorizing row before any live leg runs.
        from control_plane.profiles.live_authorization import authorized_providers  # noqa: PLC0415
        in_scope = provider in authorized_providers()
        checks.append((in_scope, "in the live_authorization code-pinned scope" if in_scope else
                       "no register row authorizes this provider (live legs fail closed)"))
    except Exception as exc:  # import failure must not crash a diagnostic — and must not pass it
        checks.append((False, f"live_authorization unreadable ({type(exc).__name__}) — "
                              f"unverifiable, so NOT registered"))
    try:
        from control_plane.nodes.pane_picker import registered_providers  # noqa: PLC0415
        offered = provider in registered_providers()
        checks.append((offered, "offered by the pane picker" if offered else
                       "not offered by the pane picker (no selectable option exists yet)"))
    except Exception as exc:
        checks.append((False, f"pane_picker unreadable ({type(exc).__name__}) — "
                              f"unverifiable, so NOT registered"))
    registered = all(ok for ok, _ in checks)
    detail = "; ".join(d for _, d in checks) + "; " + _schema_vocabulary_note(provider)
    return (STATE_REGISTERED if registered else STATE_NOT_REGISTERED), detail


def _schema_vocabulary_note(provider: str) -> str:
    """The node-schema vocabulary fact, DECLARED on every registration answer rather than gating it.
    Stated for every provider, so the note cannot read as special pleading for any of them.

    Since OP-12.1 (2026-08-01) there is more than one version to report against, so the note names
    WHICH version admits the id — a `node@1.0` member and a `node@1.1` member are different
    provenance claims (see `registry.adapter_version_map`). Derived from the same accessor the
    registry fence uses, never from a second reading of the files: a diagnostic that disagreed with
    the fence would be worse than no diagnostic."""
    try:
        from control_plane.nodes.registry import adapter_version_map  # noqa: PLC0415

        admitted = adapter_version_map()
    except Exception as exc:
        return (f"declared: the node adapter vocabulary is unreadable ({type(exc).__name__}), so "
                f"the adapter-enum fact is UNVERIFIED")
    version = admitted.get(provider)
    if version == "node@1.0":
        return "declared: in the frozen node@1.0 adapter enum"
    if version:
        return (f"declared: NOT in the frozen node@1.0 adapter enum, but admitted by {version} — "
                f"the additive successor schema the operator authorized in OP-12.1; a schema-valid "
                f"node RECORD may name this provider")
    return ("declared: in NO node schema version's adapter enum — no schema-valid node RECORD can "
            "name this provider; admitting one is an operator decision (U227/OP-12.1 is the "
            "precedent, and it was a ruling, not a code change)")


# Deployment profile (I-20 air-gap honesty), stated exactly as it is:
#
# This build has NO ambient profile service. `control_plane.profiles.loader.DeploymentProfile` is
# the canonical type, but every caller constructs it explicitly and the existing live tools pass
# "cloud" literally — so a standalone diagnostic has no profile signal to read. `SOVEREIGN_
# DEPLOYMENT_PROFILE` is therefore THIS TOOL'S OWN opt-in switch, not a pre-existing operator
# convention (an earlier comment claimed it was — spec-audit N-4). It defaults to "cloud",
# matching the other tools; that default is open, and saying so is the honest part.
#
# What IS enforced: when the switch names the air-gapped profile, `_guarded_run` refuses on EVERY
# path — status, recon, and probe alike. The first version guarded `probe_status` only, while the
# module claimed no frontier CLI was contacted at all (spec-audit N-3). The value is validated
# through the canonical `DeploymentProfile` so an unknown id fails closed rather than reading as
# "not air-gapped".
_PROFILE_ENV = "SOVEREIGN_DEPLOYMENT_PROFILE"
_AIRGAP_PROFILE = "offline_airgapped"


def airgapped() -> bool:
    raw = os.environ.get(_PROFILE_ENV, "cloud").strip() or "cloud"
    if raw == _AIRGAP_PROFILE:
        return True
    try:
        from control_plane.profiles.loader import DeploymentProfile  # noqa: PLC0415
        profile = DeploymentProfile(raw)
        _ = profile.network      # raises ProfileViolation on an unknown id — validate, don't guess
        return profile.is_airgapped
    except Exception:
        # An unrecognised profile id is not a licence to call a cloud CLI (I-20, fail closed).
        return raw not in ("cloud", "hybrid")


class AirgapRefusal(Exception):
    """A frontier provider CLI was about to be invoked under an air-gapped profile."""


def _guarded_run(run: Runner, argv: Sequence[str]) -> RunResult:
    """The ONE place a provider CLI is actually invoked from. Every caller in this module goes
    through it, so the air-gap refusal cannot be true on one path and false on two."""
    if airgapped():
        return None, "", "", False, (
            f"refused: deployment profile {os.environ.get(_PROFILE_ENV, 'cloud')!r} is air-gapped — "
            f"no frontier provider CLI is contacted (invariant 20, fail closed)")
    return run(argv)


class _Unset:
    """Sentinel distinguishing "caller supplied no executable, discover one" from the caller
    asserting "there is NO executable" — passing `executable=None` must mean the latter, or a test
    for the absent-CLI branch would silently probe the host's real CLI."""


_UNSET = _Unset()


def probe_status(spec: ProviderSpec, runner: Runner | None = None, *,
                 check_registration: bool = True,
                 executable: str | None | _Unset = _UNSET) -> ProviderStatus:
    """Assemble the §6 status report for one provider. Makes NO model call and NEVER raises: every
    failure is captured as data so the caller (and the operator) gate on evidence.

    Sequence: resolve the executable → `--version` → the provider's models command (which for Grok
    also carries its login line) → registration lookup. These are metadata calls that spend no
    tokens — but `<cli> models` is an inventory the provider CLI may fetch from its own service, so
    the sequence is NOT purely local (spec-audit F-8, correcting an earlier claim that it was).
    Under an air-gapped deployment profile it is therefore refused outright (I-20)."""
    status = ProviderStatus(provider=spec.provider, display=spec.display, command=spec.command,
                            subscription_resource=spec.subscription_resource,
                            terminal_allowance=spec.terminal_allowance,
                            install_command=spec.install_command, notes=spec.notes)
    if airgapped():
        status.state = STATE_PROBE_FAILED
        status.auth_state = AUTH_UNVERIFIED
        status.auth_detail = (f"deployment profile is air-gapped ({_AIRGAP_PROFILE!r}) — a frontier "
                              f"provider CLI is not contacted at all (invariant 20, fail closed)")
        status.model_note = "not enumerated: air-gapped profile"
        # PROBE_FAILED is the closest member of §6's closed state set, but nothing failed here —
        # the probe was refused by policy. Without this the capability table reads as a broken
        # provider (spec-audit N-13).
        status.state_caveat = ("not a provider fault: the probe was REFUSED by the air-gapped "
                               "deployment profile, so nothing was contacted")
        status.registration_state, status.registration_detail = (
            provider_registration(spec.provider) if check_registration
            else (STATE_NOT_REGISTERED, "registration check skipped"))
        return status
    exe = which_provider(spec) if isinstance(executable, _Unset) else executable
    if not exe:
        status.state = STATE_NOT_INSTALLED
        status.auth_state = AUTH_UNVERIFIED
        status.auth_detail = "executable not found on PATH"
        status.registration_state, status.registration_detail = (
            provider_registration(spec.provider) if check_registration
            else (STATE_NOT_REGISTERED, "registration check skipped"))
        return status
    status.command_found = True
    status.executable = exe
    run = runner if runner is not None else subprocess_runner()

    rc, out, err, timed, spawn = _guarded_run(run, [exe, *spec.version_args])
    version_outcome = classify_provider_outcome(rc, out, err, timed_out=timed, spawn_error=spawn)
    status.diagnostics.append({"call": " ".join(spec.version_args),
                               **version_outcome.as_dict()})
    # `.strip().splitlines()` is EMPTY for whitespace-only output, which is truthy — indexing [0]
    # there raised IndexError out of a function whose contract is "never raises" (spec-audit F-7).
    # W-52 (R-48): the same ONE owner the adapter probe uses. This branch carried its own copy of
    # the `splitlines()[0]` rule, so a banner or an npm update notice above the real declaration
    # decided the version here independently of the other probe.
    raw_version, version_tuple = extract_version(out or err or "")
    if not raw_version:
        _version_lines = (out or err or "").strip().splitlines()
        raw_version = _version_lines[0].strip() if _version_lines else ""
    status.version = redact_diagnostics(raw_version, limit=120) or None
    status.version_tuple = version_tuple

    if not version_outcome.ok:
        status.state = STATE_PROBE_FAILED
        status.auth_state = AUTH_PROBE_FAILED
        status.auth_detail = f"`{spec.command} {' '.join(spec.version_args)}` {version_outcome.outcome}"
    elif status.version_tuple is None or status.version_tuple < spec.min_version:
        status.state = STATE_UNSUPPORTED_VERSION
        status.auth_detail = (f"version {raw_version!r} unparseable or below "
                              f"{'.'.join(map(str, spec.min_version))} (fail closed)")

    # Model inventory + (for Grok) the CLI's own auth report.
    rc, out, err, timed, spawn = _guarded_run(run, [exe, *spec.models_command])
    models_outcome = classify_provider_outcome(rc, out, err, timed_out=timed, spawn_error=spawn)
    status.diagnostics.append({"call": " ".join(spec.models_command), **models_outcome.as_dict()})
    if models_outcome.ok:
        # W-49 / R-08. THE shared policy, not a second copy. This branch used to parse `out`
        # ALONE while `probe_provider_cli` parsed `out + err`, and grok writes its declarative
        # login line to STDERR -- so on the real CLI the two probes disagreed about whether the
        # operator was signed in, for the very same call. Which stream the parser sees is auth
        # policy, and it now has one home.
        inv, auth_state, auth_detail = classify_models_call(
            stdout=out, stderr=err, parse_models=spec.parse_models,
            reports_auth=spec.auth_reporting_command is not None,
            confirm_hint="the live probe (-Action probe)")
        status.models = inv.models
        status.default_model = inv.default_model
        status.model_note = inv.parse_note
        # W-49: the VERDICT is the shared one too, not just the parse. The branches that used to
        # stand here had no `auth_required_reported` case at all, so a CLI EXPLICITLY reporting
        # that the operator is not authenticated was recorded as UNVERIFIED -- the evidence was
        # parsed and then dropped one line later. That is the other half of R-08.
        status.auth_state = auth_state
        status.auth_detail = auth_detail

    else:
        status.model_note = f"model enumeration {models_outcome.outcome} ({models_outcome.basis})"
        if models_outcome.outcome == OUTCOME_AUTH_REQUIRED:
            status.auth_state = AUTH_REQUIRED
            status.auth_detail = models_outcome.detail
        else:
            status.auth_state = AUTH_PROBE_FAILED
            status.auth_detail = models_outcome.detail

    status.headless_supported = spec.headless_supported
    status.interactive_supported = spec.interactive_supported
    status.structured_output_supported = spec.structured_output_supported

    # Final state, fail-closed order: an earlier hard failure is never upgraded by a later success.
    if status.state in (STATE_PROBE_FAILED, STATE_UNSUPPORTED_VERSION):
        pass
    elif status.auth_state == AUTH_REQUIRED:
        status.state = STATE_AUTH_REQUIRED
    elif status.auth_state == AUTH_PROBE_FAILED or not models_outcome.ok:
        status.state = STATE_PROBE_FAILED
    else:
        status.state = STATE_AVAILABLE

    # AVAILABLE means "installed, responding, inventory readable" — it does NOT mean the operator's
    # session is authenticated when nothing could check. §6's state set has no fourth value for
    # that, so the caveat rides alongside the state and every surface that prints AVAILABLE must
    # print it too (spec-audit F-2). `auth_confirmed` is the narrow derived fact — auth reported by
    # the CLI itself — and nothing more: readiness to LAUNCH additionally needs registration, a
    # governor lease, and the live switch. Since 18B `.picker` the first of those three exists; the
    # other two still do not, which is why this stays a narrow field and not a readiness verdict.
    if status.state == STATE_AVAILABLE and status.auth_state != AUTH_AUTHENTICATED:
        status.state_caveat = ("AVAILABLE on an UNVERIFIED session: the CLI is installed and "
                               "responding, but nothing here can confirm the operator is signed "
                               "in — only a live probe can")
    status.auth_confirmed = (status.state == STATE_AVAILABLE
                           and status.auth_state == AUTH_AUTHENTICATED)

    status.registration_state, status.registration_detail = (
        provider_registration(spec.provider) if check_registration
        else (STATE_NOT_REGISTERED, "registration check skipped"))
    # The lease line describes THIS diagnostic's knowledge, not the product's state. Nothing here
    # reads the durable lease ledger, so the registered branch must not say "registered" and let a
    # reader hear "a terminal is held": what registration bought is that the governor now KNOWS this
    # resource and a pane could take its one terminal. Saying more would be the launch-readiness
    # over-claim the `launch_ready` rename removed from the field next to it.
    status.lease_state = (
        f"not_registered — no pane can hold {spec.subscription_resource}"
        if status.registration_state == STATE_NOT_REGISTERED else
        f"registered, none held here — {spec.subscription_resource} is governed at allowance "
        f"{status.terminal_allowance}; this diagnostic reads no lease ledger and holds no terminal")
    return status


def resolve_selection(selector: str) -> list[ProviderSpec]:
    """`all|grok|gemini` -> specs. Any other value is a hard error (the runner validates too, but a
    diagnostic must never quietly widen a selection)."""
    sel = (selector or "all").strip().lower()
    if sel == "all":
        return [GROK_SPEC, ANTIGRAVITY_SPEC]
    if sel in SELECTOR_TO_PROVIDER:
        return [PROVIDER_SPECS[SELECTOR_TO_PROVIDER[sel]]]
    raise ValueError(f"unknown provider selector {selector!r} — expected all|grok|gemini")


def build_report(selector: str = "all", *, runner: Runner | None = None,
                 check_registration: bool = True) -> dict[str, Any]:
    """Full §6 status report for the selection, plus the recorded command-surface deltas."""
    specs = resolve_selection(selector)
    return {
        "schema": "sovereign.frontier_provider_recon/1.0",
        "phase": "18A",
        "authorization": "OP-12 (operator, 2026-07-31)",
        "selector": (selector or "all").strip().lower(),
        "repo_root": str(REPO_ROOT),
        "providers": [probe_status(s, runner, check_registration=check_registration).as_dict()
                      for s in specs],
        "flag_deltas": [dict(d) for d in RECORDED_FLAG_DELTAS],
        # The whole policy, not just its named half. Recording only the nine exact keys understated
        # what the classifier actually does — it also drops five prefixes and eight substrings, and
        # it PRESERVES an allowlist whose existence is the entire substance of the N-1 finding
        # (`GROK_SANDBOX`, the CLI's only containment lever). Evidence that omits the exception
        # cannot be checked against the code (round-3 spec-audit MINOR-13).
        # The WHOLE recorded policy comes from the shared object — enumeration, preserve list,
        # and the claim basis (the named tests whose existence is the evidence for
        # `reads_credentials_by_design`, round-4 finding 9's correction, now owned by the policy
        # itself rather than bolted on here).
        #
        # The first draft of this splat kept the old literals BELOW it. In a dict literal the later
        # keys win, so the splat was dead: a mutated `credential_policy()` left this report
        # unchanged, and the comment claiming the report could not describe a scrub the adapters do
        # not perform was true only by coincidence of shared objects (gate-validator finding 4).
        "credential_policy": _P.credential_policy(),
    }


def _capture_help(spec: ProviderSpec, exe: str, argv: Sequence[str], runner: Runner) -> dict[str, Any]:
    rc, out, err, timed, spawn = _guarded_run(runner, [exe, *argv])
    outcome = classify_provider_outcome(rc, out, err, timed_out=timed, spawn_error=spawn)
    # help text is not secret, but it goes through the same redaction path on principle
    return {"call": f"{spec.command} {' '.join(argv)}", "outcome": outcome.as_dict(),
            "stdout": redact_diagnostics(out, limit=20000),
            "stderr": redact_diagnostics(err, limit=20000)}


def build_recon(selector: str = "all", *, runner: Runner | None = None) -> dict[str, Any]:
    """Reconnaissance capture (operator directive §2): the installed command surface, verbatim, so
    every flag this build relies on is auditable against the host that produced it."""
    specs = resolve_selection(selector)
    run = runner if runner is not None else subprocess_runner()
    captures: list[dict[str, Any]] = []
    for spec in specs:
        exe = which_provider(spec)
        entry: dict[str, Any] = {"provider": spec.provider, "display": spec.display,
                                 "command": spec.command, "executable": exe}
        if exe:
            calls = [spec.version_args, ("--help",), spec.models_command]
            if spec.provider == GROK_PROVIDER:
                calls += [("agent", "--help"), ("login", "--help"), ("models", "--help")]
            else:
                calls += [("models", "--help"),]
            entry["surface"] = [_capture_help(spec, exe, c, run) for c in calls]
        else:
            entry["surface"] = []
            entry["note"] = "executable not found on PATH — recorded fact, not a failure"
        captures.append(entry)
    report = build_report(selector, runner=run)
    return {"schema": "sovereign.frontier_provider_recon.capture/1.0", "phase": "18A",
            "authorization": "OP-12 (operator, 2026-07-31)",
            "recorded": "2026-07-31", "host_platform": sys.platform,
            "status": report, "command_surface": captures}


# ---------------------------------------------------------------------------------------------
# The one harmless live probe (operator directive §7) — gated by the SAME fail-closed switch
# every other live path in this build obeys.
# ---------------------------------------------------------------------------------------------
def live_probe_gate(provider: str, *, config_path: str | Path | None = None) -> tuple[bool, str]:
    """May a live probe be spent on `provider`? (allowed, reason).

    The probe costs a real subscription call, so it goes through `config/live_operation.json` —
    the operator's one-time "live sessions allowed" switch — through the same `is_provider_live`
    gate every live-spawn path already calls (directive §11(c), 18C entry condition). Absence of
    the file, or a scope that does not name this provider, is a DENIAL, not a warning: that is the
    fail-closed switch working as designed.

    **Scope of this gate, stated rather than implied:** it governs the PROBE — the only thing here
    that spends subscription tokens. It does NOT govern `-Action status`, whose `--version` and
    `models` calls are authenticated, token-free vendor metadata calls gated only by the
    deployment-profile air-gap switch (`_guarded_run`). That asymmetry is operator-directed
    (§2/§6) and defensible, but it is an asymmetry (round-3 spec-audit MEDIUM-8, U236).

    **How this is actually opened at 18C — the printed instruction used to be impossible.** Four
    artifacts, this one included, told the operator to "extend `config/live_operation.json`" to
    name the new providers. `live_authorization._AUTHORIZED_PROVIDERS` is code-pinned to the OP-6
    pair and `_validate_providers` RAISES on any other id, so an operator following that
    instruction would have got a `LiveAuthorizationError` denying not just grok/antigravity but
    `claude_code` and `openai_codex_cli` too — every live path in the build. The failure direction
    is safe (invariant 1 upheld: config cannot widen code-pinned scope) but the instruction was
    wrong (round-3 spec-audit MAJOR-2, U237). **18B `.scope` shipped that extension**, so for the
    two OP-12 providers the config edit is now the ONLY remaining step — and the denial text no
    longer says otherwise: `_how_to_open` DERIVES the instruction from the code-pinned scope rather
    than repeating the sentence that was true in July (18C `.close`, U289)."""
    try:
        from control_plane.profiles import live_authorization as la  # noqa: PLC0415
    except Exception as exc:
        return False, f"live-authorization module unreadable ({type(exc).__name__}) — fail closed"
    try:
        auth = la.load_live_authorization(config_path)
    except Exception as exc:
        return False, f"live operation not authorized: {exc}"
    # `is_provider_live` is the existing gate every live-spawn path already calls (it folds in
    # `authorized` AND the scoped provider set) — reused rather than reimplemented, so a probe can
    # never be permitted by a looser rule than a session.
    if not auth.is_provider_live(provider):
        # `is_provider_live` folds the master flag together with the scoped set, and the loader
        # returns a DENIED authorization (not an exception) when the file is ABSENT or when
        # `live_operation_authorized` is false. Telling an operator in those worlds to "add the
        # provider to `scope.providers`" is wrong — there may be no list, and with the master flag
        # off adding to it opens nothing. So the loader's OWN reason is carried, and the
        # add-to-the-list instruction is printed only for the world it is true in: a present,
        # authorized config that merely does not name this provider (spec-audit MEDIUM-5).
        if not getattr(auth, "authorized", False):
            return False, (f"live operation is not authorized on this host — DENIED (fail closed): "
                           f"{auth.reason}. Start from config/live_operation.example.json (copy it "
                           f"to config/live_operation.json and keep `live_operation_authorized` "
                           f"true); that file is never committed, and this build cannot write it — "
                           f"the switch is the operator's (invariant 1)")
        return False, (f"{provider} is not in the authorized live scope of "
                       f"config/live_operation.json — DENIED (fail closed). "
                       + _how_to_open(la, provider))
    return True, f"{provider} is within the authorized live scope"


#: The providers whose code-pinned scope arrived with 18B `.scope` (the U237 fix). Claiming that
#: provenance for `claude_code`/`openai_codex_cli` — covered since OP-6, Phase 15 — was a false
#: statement in the one text an operator acts on (spec-audit MINOR-10).
_SCOPE_EXTENSION_18B = (GROK_PROVIDER, ANTIGRAVITY_PROVIDER)


def _how_to_open(la: Any, provider: str) -> str:
    """The ONE instruction an operator reads when 18C blocks — DERIVED from the code-pinned scope,
    never asserted.

    It used to be a fixed sentence: "editing that file is NOT sufficient and NOT safe on its own …
    it takes the operator's register row plus the 18B scope extension". That was exactly true when
    U237 was written and false the moment 18B `.scope` shipped the OP-12 row — so the surface the
    operator consults to satisfy 18C's entry condition told them a code change was still owed that
    had already landed. Invariant 1 is about INFORMED final authority, which is why this reads the
    state instead of remembering a moment (18C `.close`).

    For an id no recorded ruling covers, the original warning is still the truth and is still
    printed: `_validate_providers` RAISES on an unknown id, so naming one in the config would deny
    every live provider, `claude_code` included."""
    try:
        covered = provider in la.authorized_providers()
        rows = [row for row in la.authorizing_register_rows()
                if provider in la.authorized_providers(row)] if covered else []
    except Exception:   # noqa: BLE001 - a scope lookup that fails tells the operator the safe thing
        covered, rows = False, []
    if not covered:
        return ("To open it, editing that file is NOT sufficient and NOT safe on its own: the "
                "authorized-provider set is code-pinned and raises on an unknown id, which would "
                "deny EVERY live provider. It takes an operator register row plus a scope "
                "extension in control_plane/profiles/live_authorization.py (U237)")
    provenance = " (shipped at 18B `.scope`, closing U237)" if provider in _SCOPE_EXTENSION_18B else ""
    which = (f"register row {rows[0]}" if len(rows) == 1
             else f"one of register rows {', '.join(rows)}" if rows
             else "a recorded ruling")
    return (f"The code-pinned scope ALREADY covers it under {which}{provenance}, so the ONE "
            f"remaining step is the operator's own: add {provider!r} to the `scope.providers` list "
            f"in config/live_operation.json and cite that row in `register_row`. That file is never "
            f"committed, and this build cannot write it — the switch is the operator's "
            f"(invariant 1)")


# U234, enforced rather than merely disclosed. It was FALSE until this module's probe child was
# routed through a supervised, governor-leased launch path (node identity + I-X3 lease + job-object
# boundary + teardown accounting). A `True` here is a CLAIM THAT THAT PATH EXISTS, so it moved in
# the same commit that wired it — 18C `.probe-path`, `node_runtime.supervisor.provider_probe_session`
# — and never by config. `TestTheFlagNamesAPathThatExists` asserts the claim rather than the value:
# it imports the module the flag stands for and checks the entry point is callable, so deleting or
# renaming the path turns the flag red instead of leaving a True pointing at nothing.
_SUPERVISED_PROBE_PATH = True
#: The refusal that stood here while the path was missing. KEPT (not deleted) as the fail-closed
#: branch for a build where the supervised path cannot be reached at all — see `_open_probe_session`,
#: which returns this outcome when the supervisor module is unimportable. A missing supervisor must
#: refuse the probe, not silently downgrade it to the naked spawn this text describes.
_UNSUPERVISED_PROBE_REFUSAL = (
    "live probe REFUSED after an allowed gate: the probe child would be an unsupervised "
    "`subprocess.run` with no node identity, no I-X3 lease and no teardown accounting — a naked "
    "session (invariant 2 / I-C1). {provider} spends nothing unless the child runs inside the "
    "governed probe session (node identity + I-X3 lease + process-tree boundary + measured "
    "teardown) that 18C `.probe-path` built — U234. That path EXISTS; reaching this text means it "
    "could not be reached from here, and an unreachable supervisor refuses rather than downgrading "
    "to the naked spawn described above. The live authorization is correct and is NOT the thing "
    "refusing here.")

#: The supervised-session entry point, resolved lazily and by NAME so this diagnostic keeps working
#: (fail-closed) on a host where the control plane is broken — the same convention `live_probe_gate`
#: uses for its imports.
_PROBE_SESSION_MODULE = "node_runtime.supervisor.provider_probe_session"


def _open_probe_session(spec: "ProviderSpec", stack: contextlib.ExitStack, *,
                        repo_root: str | Path, executable: str,
                        config_path: str | Path | None,
                        open_session: Callable[..., Any] | None = None):
    """ENTER the governed probe session on `stack`, or return a refusal document.

    Returns `(session, None)` on success and `(None, refusal_dict)` on any governed refusal. The
    session is entered here rather than merely constructed, because a `@contextmanager` runs no gate
    until `__enter__` — building one and returning it would have moved every refusal out of this
    function's `except` and out of the verdict, into a traceback. Every gate's own exception becomes
    a verdict naming the gate that refused: a `SubscriptionLimitExceeded` escaping a diagnostic
    would read as a crash rather than as I-X3 doing its job.

    `open_session` injects the factory for the deterministic suite (host-free seam) — it is entered
    on the same stack and refuses through the same branch, so the injected path cannot be governed
    by weaker rules than the real one.

    **Both externally-sourced gates are passed EXPLICITLY**, never left to a default in the
    supervisor module: `profile_loader` is built from the host's real `SOVEREIGN_DEPLOYMENT_PROFILE`
    (so an air-gapped host refuses at gate 1, before any lease is written, rather than at
    `_guarded_run` after one has been taken and released), and `operator_terms_confirmed` carries
    the OP-12 recorded basis and names it here."""
    factory = open_session
    loader_factory = None
    if factory is None:
        try:
            import importlib  # noqa: PLC0415
            module = importlib.import_module(_PROBE_SESSION_MODULE)
            factory = module.governed_probe_session
            loader_factory = module.profile_loader_from_host
        except Exception as exc:      # noqa: BLE001 — an unreachable supervisor must fail CLOSED
            return None, {"refused_by": "supervision",
                          "reason": _UNSUPERVISED_PROBE_REFUSAL.format(provider=spec.provider)
                          + f" [supervised path unreachable: {type(exc).__name__}: {exc}]"}
    try:
        from control_plane.profiles.live_authorization import (  # noqa: PLC0415
            load_live_authorization,
        )
        from control_plane.profiles.loader import DeploymentProfile, ProfileLoader  # noqa: PLC0415
        auth = load_live_authorization(config_path)
        # An unknown profile id raises here and becomes a refusal verdict — never a permit.
        loader = (loader_factory() if loader_factory is not None
                  else ProfileLoader(DeploymentProfile(
                      (os.environ.get(_PROFILE_ENV) or "cloud").strip() or "cloud")))
        # The durable per-host node log (`.sovereign_store/nodes/`), so a probe that runs leaves a
        # `node@1.1` record behind — 18D `.close`, the wiring OP-12.1 authorized. Built here rather
        # than defaulted inside the supervisor: whether a session becomes a Sovereign node is the
        # caller's fact. A registrar that cannot be constructed (an unwritable store) refuses the
        # probe through the same branch every other gate refuses through — never a silent
        # downgrade to an unregistered session.
        from node_runtime.supervisor.provider_node_registration import (  # noqa: PLC0415
            default_provider_node_registrar,
        )
        session = stack.enter_context(factory(
            spec.provider, probe_id=spec.command, workspace=str(repo_root), live_auth=auth,
            profile_loader=loader, registrar=default_provider_node_registrar(repo_root),
            # AUTONOMOUS_BUILD_DIRECTIVE.md §17 (OP-12): "the operator confirms both subscriptions
            # permit supervised first-party-CLI use, same R8 class as OP-9". The OPERATOR's recorded
            # determination, cited at the call site — not this build's judgement (invariant 1).
            operator_terms_confirmed=True,
            executable=executable))
    except Exception as exc:      # noqa: BLE001 — every gate refusal is a verdict, never a crash
        return None, {"refused_by": getattr(exc, "gate", None) or type(exc).__name__,
                      "reason": f"governed probe session refused: {type(exc).__name__}: {exc}"}
    return session, None


def run_probe(spec: ProviderSpec, *, repo_root: str | Path = REPO_ROOT, model: str | None = None,
              prompt: str | None = None, runner: Runner | None = None,
              git_status: Callable[[], str | None] | None = None,
              config_path: str | Path | None = None,
              open_session: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Execute (or refuse) the ONE harmless probe for `spec` and return a verdict document.

    Order is deliberate and fail-closed: live gate → executable → argv → **governed session**
    (identity + I-X3 lease + supervision) → repo-status snapshot → run → second snapshot →
    acceptance → lease released and MEASURED. A denied gate spends nothing and returns before any
    argv exists; a refused session spends nothing and returns before any child exists.

    Through 18A/18B this spawned a bare `subprocess.run` — or rather refused to, because it would
    have been unsupervised, with no node identity and no I-X3 lease (U234). **18B `.scope` removed
    the impossibility that had kept the refusal academic** by adding the OP-12 row, leaving an
    operator config as the only thing standing between `-Action probe` and an unsupervised frontier
    CLI. 18C `.probe-path` wires the path itself, so the refusal branch is now reached only when the
    supervisor is genuinely unreachable — a missing supervisor refuses, it never downgrades.

    `runner` (deterministic suite) executes the argv WITHOUT the job-object boundary by
    construction, so the verdict reports `supervised_execution: false` for it rather than inheriting
    the claim from the session. The gates still run either way — the seam is the child, not the
    authorization."""
    allowed, reason = live_probe_gate(spec.provider, config_path=config_path)
    if not allowed:
        return {"provider": spec.provider, "display": spec.display, "executed": False,
                "accepted": False, "gate": {"allowed": False, "reason": reason},
                "reason": f"probe refused before spending anything: {reason}"}
    if not _SUPERVISED_PROBE_PATH:
        # Invariant 2 / I-C1 / invariant 29: no naked session, and never trust the harness. This is
        # a SECOND refusal after an ALLOWED gate — a governed refusal with its own outcome kind, not
        # a spawn error (U240's class) and not a gate denial.
        return {"provider": spec.provider, "display": spec.display, "executed": False,
                "accepted": False, "gate": {"allowed": True, "reason": reason},
                "refused_by": "supervision",
                "reason": _UNSUPERVISED_PROBE_REFUSAL.format(provider=spec.provider)}
    exe = which_provider(spec)
    if not exe:
        return {"provider": spec.provider, "display": spec.display, "executed": False,
                "accepted": False, "gate": {"allowed": True, "reason": reason},
                "reason": f"`{spec.command}` not found on PATH"}
    argv = (build_grok_probe_command(exe, repo_root=repo_root, prompt=prompt, model=model)
            if spec.provider == GROK_PROVIDER
            else build_antigravity_probe_command(exe, prompt=prompt, model=model))
    stack = contextlib.ExitStack()
    session, refusal = _open_probe_session(spec, stack, repo_root=repo_root, executable=exe,
                                           config_path=config_path, open_session=open_session)
    if refusal is not None:
        stack.close()
        return {"provider": spec.provider, "display": spec.display, "executed": False,
                "accepted": False, "gate": {"allowed": True, "reason": reason}, **refusal}
    with stack:                     # the lease is released here on EVERY exit path (D-LOOP-1)
        snap = git_status if git_status is not None else (lambda: _repo_state_snapshot(repo_root))
        before = snap()
        run = runner if runner is not None else _supervised_runner(session)
        try:
            rc, out, err, timed, spawn = _guarded_run(run, argv)
        except Exception as exc:    # noqa: BLE001 — a refusal at the child is a verdict, not a crash
            # `supervised_probe_runner` refuses (rather than reports) when argv[0] is not the file
            # the gate resolved: nothing was spawned, so this is a governed refusal with its own
            # outcome kind, reported through the same shape as every other gate saying no.
            rc, out, err, timed = None, "", "", False
            spawn = f"refused before spawn: {type(exc).__name__}: {exc}"
        after = snap()
    verdict = accept_probe(spec.provider, spec.probe_token, exit_code=rc, stdout=out, stderr=err,
                           git_status_before=before, git_status_after=after, timed_out=timed,
                           spawn_error=spawn, prompt=argv[-1])
    return {"provider": spec.provider, "display": spec.display, "executed": True,
            "gate": {"allowed": True, "reason": reason},
            # argv is recorded WITHOUT the resolved absolute path's surroundings redacted — it
            # carries no secret (no credential ever appears in a command line here)
            "command": [argv[0], *argv[1:]],
            "response_excerpt": redact_diagnostics(extract_probe_text(out), limit=300),
            # U305. `accepted:false` with `token_seen:false` has two causes that read identically in
            # a verdict and opposite in a shape: the model said nothing, or it said it somewhere the
            # strict reader does not look. Recorded on EVERY probe — including accepted ones, where
            # it is the positive record that this provider's document really is the flat shape the
            # reader was built for. Structure only, never a value (§2.2/§13).
            "document_shape": describe_probe_document(out, token=spec.probe_token).as_dict(),
            # The governed facts, read AFTER teardown so `teardown` carries the MEASURED release
            # rather than an intention. `env_scrub_names` are names only — never values (§2.2).
            "governed": session.as_dict(),
            "supervised_execution": runner is None,
            **verdict.as_dict()}


def _supervised_runner(session: Any) -> Runner:
    """The real child executor: the provider CLI inside the repository's job-object boundary, with a
    credential-scrubbed environment and the workspace as its working directory. Imported lazily from
    the module that owns supervision, so this diagnostic has exactly one implementation of it."""
    import importlib  # noqa: PLC0415

    return importlib.import_module(_PROBE_SESSION_MODULE).supervised_probe_runner(session)


def _repo_state_snapshot(repo_root: str | Path) -> str | None:
    """Snapshot used to prove a probe changed nothing (§7). Returns None if it cannot be taken —
    which `accept_probe` treats as NOT verified, never as clean.

    **What it covers, exactly:** every tracked-file change `git status --short` reports, PLUS a
    content digest of `config/live_operation.json`. The second half exists because the first half
    does not cover gitignored paths, and the live-operation switch — the file that decides whether
    any live call is permitted at all — is gitignored (spec-audit F-5). A probe that rewrote the
    switch would otherwise have left `repo_unchanged=True` behind it.

    **What it does NOT cover, stated rather than implied:** other gitignored paths
    (`node_modules/`, `.recovery/`, build output), files outside the repository, and host state.
    Those are the supervisor's and the OS's business — this is a diagnostic's bounded check, and
    the only guarantee it may claim."""
    try:
        proc = subprocess.run(["git", "status", "--short"], capture_output=True, text=True,
                              timeout=60, check=False, cwd=str(repo_root),
                              stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    switch = Path(repo_root) / "config" / "live_operation.json"
    try:
        digest = hashlib.sha256(switch.read_bytes()).hexdigest() if switch.exists() else "(absent)"
    except OSError:
        return None
    return f"{proc.stdout}\n#live_operation.json={digest}"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Grok Build / Gemini-Antigravity host reconnaissance, "
                                             "status and live-probe engine. --action status/recon "
                                             "are read-only. --action probe MAKES ONE LIVE, "
                                             "BILLABLE CALL to the provider - it is admitted only "
                                             "through the live-operation switch AND a governed, "
                                             "I-X3-leased, supervised session (18C, U234), and it "
                                             "is refused if either says no.")
    ap.add_argument("--provider", default="all", choices=["all", "grok", "gemini"])
    ap.add_argument("--action", default="status", choices=["status", "recon", "probe"])
    ap.add_argument("--model", help="model slug for a probe (must come from the CLI's own list)")
    ap.add_argument("--prompt", help="override the probe prompt (the token must still come back)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON on stdout")
    ap.add_argument("--emit", metavar="PATH", help="write the report to PATH (JSON)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.action == "probe":
        results = [run_probe(s, model=args.model, prompt=args.prompt)
                   for s in resolve_selection(args.provider)]
        report: dict[str, Any] = {"schema": "sovereign.frontier_provider_recon.probe/1.0",
                                  "phase": "18A", "authorization": "OP-12 (operator, 2026-07-31)",
                                  "probes": results}
    else:
        report = (build_recon(args.provider) if args.action == "recon"
                  else build_report(args.provider))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.emit:
        out = Path(args.emit)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    if args.json or not args.emit:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        print(text)
    # A refused or failed probe must not report success to the shell (the runner passes this on).
    if args.action == "probe" and not all(p.get("accepted") for p in report["probes"]):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
