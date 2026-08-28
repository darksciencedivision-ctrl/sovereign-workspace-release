"""First LIVE frontier adapter — Claude Code (Anthropic first-party CLI). Phase 14B `.adapter`.

The one provider the operator authorized a live path for (register OP-4/OP-5, directive
§10.1). This module supplies the *backend* that plugs into the existing, already-governed
`ModelWorkerAdapter` contract (adapters/model_adapter.py): scoped context in from MCP, the
node-local gate before publish, a CANDIDATE artifact out with provenance. The backend is the
only new surface; the governance path is unchanged and reused verbatim.

Non-negotiables encoded here (directive §2.2 / §10.1; Plan §18.3–18.4):
  - **No credential handling, ever.** The adapter invokes the host's already-authenticated
    `claude` CLI, which holds its OAuth subscription token in a host-native store (a file/
    keychain the CLI manages, NOT an environment variable). This code NEVER reads, extracts,
    stores, or transmits that credential. As defence-in-depth the child environment is also
    scrubbed of every credential- or endpoint-bearing variable (any `ANTHROPIC_*`, `AWS_*`,
    `GOOGLE_*`, `CLAUDE_CODE_*`, or `*TOKEN*`/`*SECRET*`/`*API_KEY*` name — see
    `_is_credential_key`) so no key can be transmitted and no endpoint override can redirect
    the call: the *subscription* OAuth path via the host-native store is the only one left. If
    the operator's only auth were an in-env token, scrubbing it forces a fail-closed auth pause
    (transmitting it would violate §2.2) — the operator re-logs in via the CLI's own store.
  - **Mock-first.** `MockClaudeCliBackend` is deterministic and spawns nothing; the whole
    governed path is proven with it. `ClaudeCliBackend` (the real subprocess) is NEVER used
    by the deterministic test suite — only by the opt-in, operator-gated live smoke, exactly
    like `OllamaBackend`.
  - **Fail-closed on auth.** An expired/failed subscription surfaces as `ClaudeCodeAuthError`
    — the supervisor pauses the node (Plan §18.4); there is NO silent API-key fallback.

Live-spawn governance (LIVE_OPERATION_AUTHORIZED, I-X3, R8 operator terms, CLI presence)
lives in node_runtime/supervisor/frontier_spawn.py — the real supervisor/startup path.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from adapters.base.backend import Backend, BackendAuthPause, ConductorBackend
from adapters.base.contract import AdapterContext
from adapters.frontier.process_tree import run_managed_process
from adapters.model_adapter import ModelWorkerAdapter

# The provider id — must equal control_plane/profiles/live_authorization._AUTHORIZED_PROVIDER
# and the node.schema.json `adapter` enum member, so the live gate keys on it exactly.
CLAUDE_CODE_ADAPTER = "claude_code"

# Frontier reasoning/synthesis descriptors (mirrors the mock_frontier roster entry, now real).
CLAUDE_CODE_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                 "min_context": 128000, "locality": "frontier_ok"}},
    {"capability": "synthesis", "requirements": {"structured_output": True, "min_context": 128000}},
]

# The node_class this reasoning/synthesis worker maps to (node.schema.json). A conductor-capable
# binding of this same backend is Phase 15B `.conductor`; `.modelsel` only adds per-node model
# selection on the worker path.
CLAUDE_CODE_NODE_CLASS = "worker_reasoning"

# ---- Per-node model selection (Phase 15B `.modelsel`, directive §11 15B) --------------------
# The `claude` CLI selects a model with `--model <slug>` (its documented headless flag; R8 §2).
# There is NO offline "list models" subcommand, so the *accepted* slug for an operator-named model
# ("opus-4.8", "fable-5") is only CONFIRMED by a live `claude -p --model <slug>` smoke. This module
# therefore records the operator-named refs as UNVERIFIED candidates plus the structural fact that
# the selector exists; the accepted-id resolution (and any recorded fallback) is a `.conductor`/
# `.gate` live smoke — a slug is never fabricated here, and an unavailable model is a recorded
# roster fallback, never silent (directive §11 15B: "unavailable ⇒ recorded fallback surfaced in
# the roster, never silent").
CLAUDE_CODE_MODEL_FLAG = "--model"


@dataclass(frozen=True)
class CandidateModelRef:
    """An operator-named model the roster MAY offer for a claude_code node, and its verification
    state. `provisional_slug` is the operator's own label carried verbatim — NOT a confirmed CLI id.
    `verified` stays False until a live `claude -p --model <slug>` smoke confirms the CLI accepts it;
    an unaccepted slug becomes a recorded roster fallback (directive §11 15B — never silent)."""

    operator_name: str
    provisional_slug: str
    verified: bool = False
    registered: bool = True
    conductor_capable: bool = True
    worker_capable: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"operator_name": self.operator_name, "provisional_slug": self.provisional_slug,
                "verified": self.verified, "registered": self.registered,
                "conductor_capable": self.conductor_capable,
                "worker_capable": self.worker_capable, "note": self.note}


# The operator-named Anthropic models (OP-6; directive §11 15B names "opus-4.8", "fable-5", and the
# CLI default). Recorded as UNVERIFIED candidates: the claude CLI has no offline model-list command,
# so the accepted id is resolved by a live smoke at `.conductor`/`.gate` — these are not fabricated
# CLI slugs. The CLI default is the recorded fallback (no `--model`, `resolve_claude_model_ref(None)`).
CLAUDE_CANDIDATE_MODEL_REFS: tuple[CandidateModelRef, ...] = (
    CandidateModelRef(
        operator_name="Opus 4.8", provisional_slug="opus-4.8", verified=False,
        note="operator label; accepted `--model` slug resolved by live `claude` smoke at .conductor"),
    CandidateModelRef(
        operator_name="Fable 5", provisional_slug="fable-5", verified=False,
        note="operator label; accepted `--model` slug resolved by live `claude` smoke at .conductor"),
)


def resolve_claude_model_ref(requested: str | None) -> tuple[str | None, str]:
    """Resolve the per-node model slug for `--model`, honestly.

    The claude CLI has no offline model-list, so an operator-named candidate ("opus-4.8", "fable-5")
    is only *confirmed* by a live `claude -p --model <slug>` smoke. This returns `(slug_or_None,
    note)`: a requested slug is carried verbatim (still unverified until the smoke); `None` means
    "use the CLI default and record the fallback in the roster" — directive §11 15B ("unavailable ⇒
    recorded fallback surfaced in the roster, never silent"). Nothing is fabricated."""
    if requested and requested.strip():
        return requested.strip(), f"per-node model {requested.strip()!r} (accepted-id unverified until live smoke)"
    return None, "no model selected — CLI default (recorded roster fallback, directive §11 15B)"


def claude_code_roster_descriptor(requested_model: str | None = None) -> dict[str, Any]:
    """Roster/capability descriptor for a live claude_code node with the per-node model resolution
    SURFACED — directive §11 15B ("probe accepted model IDs … unavailable ⇒ recorded fallback
    surfaced in the roster, never silent"). Mirrors `codex_roster_descriptor` so both live providers
    expose one `model_ref` shape to the roster/Inspector.

    `resolve_claude_model_ref` decides the `--model` slug (carried verbatim, still unverified until a
    live smoke) or the CLI-default fallback (`resolved_slug=None`). This embeds that decision AND its
    human-readable note into a `model_ref` block on the descriptor the roster reads, so the fallback
    is a RECORDED field of the roster surface, not merely an assumption living in a helper's return
    value. Pure/deterministic; makes no CLI call and fabricates no slug."""
    slug, note = resolve_claude_model_ref(requested_model)
    return {
        "adapter": CLAUDE_CODE_ADAPTER,
        "node_class": CLAUDE_CODE_NODE_CLASS,
        "locality": "frontier",
        "subscription_backed": True,
        # deep copy so a caller mutating a nested `requirements` dict can never write back into the
        # module-level descriptor constants (immutability hygiene; matches the 15C .gate NIT fix).
        "capability_descriptors": copy.deepcopy(CLAUDE_CODE_CAPABILITY_DESCRIPTORS),
        "model_ref": {
            "requested": requested_model,       # operator label as given (may be None)
            "resolved_slug": slug,              # None => CLI default (fallback)
            "verified": False,                  # accepted-id only confirmable by a live smoke
            "is_fallback": slug is None,        # True ⇒ recorded CLI-default fallback (never silent)
            "note": note,
        },
        "candidate_models": [c.as_dict() for c in CLAUDE_CANDIDATE_MODEL_REFS],
    }

# Exact credential/endpoint env keys the `claude` CLI documents (API key, long-lived OAuth
# token, auth token, endpoint overrides, Bedrock/Vertex routing creds). Scrubbed from the child
# env so this adapter can neither transmit a credential nor redirect the call (§2.2 / R8 §4).
_CREDENTIAL_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_API_URL", "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
)
# Name-prefix / substring families that always denote a credential, routing override, or
# secret — a fail-closed superset so a NEW provider var (added by a future CLI release) is
# scrubbed by default rather than transmitted.
_CREDENTIAL_KEY_PREFIXES = ("ANTHROPIC_", "AWS_", "GOOGLE_", "CLAUDE_CODE_")
_CREDENTIAL_KEY_SUBSTRINGS = ("TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD")

# Flags this adapter must NEVER emit: credential-passing flags and the permission/sandbox
# bypasses in the `claude` CLI's own surface. A build that would contain one fails closed
# (`_assert_no_forbidden`). Defense-in-depth parity with the codex adapter — under list-argv
# semantics an operator-supplied slug is emitted as the VALUE of `--model` (never word-split into
# an active flag), but the `claude` CLI has real bypass flags so the guard is applied regardless.
_FORBIDDEN_CLAUDE_ARGS: tuple[str, ...] = (
    "--dangerously-skip-permissions", "--api-key", "--with-api-key", "--with-access-token",
)

# stderr/stdout markers specific enough to mean "not authenticated / credit exhausted / rate
# limited" — a fail-closed pause, not a task-level generation failure (Plan §18.4). Kept
# specific to avoid mislabelling an ordinary runtime fault as an auth pause (spec-audit MINOR-1).
_AUTH_FAILURE_MARKERS = (
    "not authenticated", "unauthenticated", "please log in", "please run /login",
    "invalid api key", "session expired", "credit balance", "rate limit", "rate-limit",
    "http 401", "http 403", "status 401", "status 403", "error 429",
)


def is_credential_env_key(name: str) -> bool:
    """Fail-closed classifier: True if `name` is a known credential/endpoint key, starts with a
    provider prefix, or contains a secret-token substring (§2.2 / R8 §4).

    Module-level so every launch path scrubs by the ONE rule — the one-shot worker command
    (`ClaudeCliBackend.build_env`) AND the interactive conductor pane (`.conductor-pane`,
    `scrub_credential_env`). A second copy could drift and leave a key un-scrubbed on one path only."""
    up = name.upper()
    if up in _CREDENTIAL_ENV_KEYS:
        return True
    if up.startswith(_CREDENTIAL_KEY_PREFIXES):
        return True
    return any(tok in up for tok in _CREDENTIAL_KEY_SUBSTRINGS)


def scrub_credential_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """A child environment with every credential- or endpoint-bearing key REMOVED (see
    `is_credential_env_key`). The subscription OAuth token lives in the `claude` CLI's own
    host-native store, which we never touch; scrubbing the env means no key can be transmitted and
    no endpoint override can redirect the call — the subscription path is the only one left (§2.2).
    Non-secret vars (PATH, proxies, locale, temp dirs) are preserved so the CLI still runs."""
    env = dict(os.environ if base_env is None else base_env)
    for key in [k for k in env if is_credential_env_key(k)]:
        env.pop(key, None)
    return env


class ClaudeCodeAuthError(BackendAuthPause):
    """The `claude` CLI reported an auth/credit/rate-limit condition. Fail-closed pause signal
    (Plan §18.4): the generic adapter re-raises it, the supervisor pauses the node; NO silent
    API-key fallback."""


def extract_reported_model(payload: Any) -> str | None:
    """Reconcile the EXECUTING model from a `claude -p --output-format json` response, fail-closed.

    Phase 15B `.gate` (spec-audit owed item): a per-node decision must record the model the CLI
    *actually ran*, read back from its own JSON response — NOT the requested `--model` slug, which
    is only an unverified label until a live call confirms it (directive §11 15B honesty).

    RECONCILED AGAINST THE REAL SHAPE (Phase 15D `.flow` LIVE re-run, OP-9 — the operator-gated
    live smoke the earlier drafts deferred to). The captured `claude -p --output-format json`
    envelope (`tools/live/claude_json_shape.captured.json`) carries NO top-level `model` string;
    the executing checkpoint lives in `modelUsage`, a map of `model_id -> {..., costUSD, ...}`, and
    on a real call it holds MORE THAN ONE key — the primary conductor model plus the CLI's own
    auxiliary fast-model helper (e.g. `claude-haiku-4-5-*`). Resolution, all deterministic and fail
    closed (a checkpoint id is NEVER guessed):

      * a top-level string `model` wins if present (some builds / future shapes);
      * a single-key `modelUsage` is unambiguous — that key is the model;
      * a MULTI-key `modelUsage` is reconciled to the COST-DOMINANT model: the entry with the
        strictly-greatest numeric `costUSD`, the CLI's own integrated measure of which checkpoint
        did the work (the primary always dwarfs the fast-model helper in billed cost). A TIE, a
        missing/non-numeric `costUSD` on any entry, a non-dict entry, or a non-string/blank key ⇒
        `None` (ambiguous ⇒ unverified, never a coin-flip between two real checkpoints).

    STATED LIMIT (U57): cost-dominance is a reconciliation, not a field the CLI labels "primary".
    It is correct for the observed shape (a primary model + a cheaper helper) and fails closed when
    it cannot tell; a hypothetical future config in which a helper outspends the primary would be
    misattributed. The full `modelUsage` key set is surfaced by callers (never hidden) so the
    reconciliation is auditable."""
    if not isinstance(payload, dict):
        return None
    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    usage = payload.get("modelUsage")
    if not isinstance(usage, dict) or not usage:
        return None
    keys = list(usage.keys())
    if any(not isinstance(k, str) or not k.strip() for k in keys):
        return None  # a non-string / blank key ⇒ the map cannot be trusted, fail closed
    if len(keys) == 1:
        return keys[0].strip()
    ranked: list[tuple[Decimal, str]] = []
    for k in keys:
        entry = usage[k]
        if not isinstance(entry, dict):
            return None
        cost = entry.get("costUSD")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            return None  # no billed-cost signal ⇒ cannot disambiguate ⇒ unverified
        # Money as Decimal, never float (CLAUDE.md / Buildout §4): `str(cost)` gives the exact
        # decimal the JSON meant, so a genuine sub-cent difference is not lost to float noise and a
        # true tie is detected exactly. (json.loads already parsed a float; going through its repr
        # is the closest faithful decimal available at this boundary.)
        try:
            cost_dec = Decimal(str(cost))
        except (InvalidOperation, ValueError):
            return None  # unparseable cost ⇒ no usable signal ⇒ fail closed
        if not cost_dec.is_finite():
            return None  # NaN / Infinity ⇒ uncomparable ⇒ fail closed
        ranked.append((cost_dec, k.strip()))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    if ranked[0][0] <= ranked[1][0]:
        return None  # not a STRICT cost maximum ⇒ ambiguous ⇒ unverified
    return ranked[0][1]


def reported_models(payload: Any) -> tuple[str, ...]:
    """Every model id the CLI's `modelUsage` names (or the top-level `model`), for TRANSPARENCY.

    The executing-checkpoint CLAIM is the single `extract_reported_model` value; this surfaces the
    FULL set beside it so a multi-model response (primary + auxiliary helper) is recorded, never
    hidden — the auditability half of the U57 reconciliation. Deterministic order (sorted)."""
    if not isinstance(payload, dict):
        return ()
    ids: set[str] = set()
    model = payload.get("model")
    if isinstance(model, str) and model.strip():
        ids.add(model.strip())
    usage = payload.get("modelUsage")
    if isinstance(usage, dict):
        for k in usage:
            if isinstance(k, str) and k.strip():
                ids.add(k.strip())
    return tuple(sorted(ids))


def _assert_no_forbidden(argv: list[str]) -> None:
    """Fail-closed guard: refuse to emit any credential-passing or permission-bypass flag.
    Deterministic permission logic (Buildout Directive §4), not caller convention. Guards the
    FLAGS only (call before the prompt is appended) so a benign prompt that happens to equal a
    flag token is never misread as smuggling one."""
    lowered = [a.lower() for a in argv]
    for bad in _FORBIDDEN_CLAUDE_ARGS:
        if bad in lowered:
            raise ValueError(
                f"refuse to build a claude command containing {bad!r} — no credential/permission-"
                f"bypass flag is ever permitted (§2.2, fail closed)")


def build_interactive_command(executable: str = "claude", *, model: str | None = None) -> list[str]:
    """Argv for an INTERACTIVE conductor session — the operator's live agentic CONDUCTOR chat pane
    (directive §13 / OP-8; §12.4 conductor-first startup). Distinct from `ClaudeCliBackend.build_command`,
    which is the one-shot `-p --output-format json` headless WORKER mode.

    NO `-p`, NO `--output-format json`: an interactive `claude` session the operator types into and
    the CLI answers in the pane in real time (OP-8 §13.1–2). An explicit `--model <slug>` selects the
    per-node model (the conductor SELECTION, carried verbatim — still unverified until a live reply);
    `None` ⇒ the CLI default (recorded fallback, directive §11 15B). The same fail-closed guard as the
    headless path applies: no credential-passing or permission-bypass flag is ever emitted (§2.2). Pure
    and deterministic — it builds argv only; the ConPTY spawn and the host-native OAuth credential stay
    entirely outside this function (the credential is never read/stored/transmitted)."""
    slug = model.strip() if model and model.strip() else None
    cmd = [executable]
    if slug:
        cmd += [CLAUDE_CODE_MODEL_FLAG, slug]
    # Guard the flags (no prompt is ever appended — an interactive session has no prompt arg) so a
    # credential/permission-bypass flag can never be emitted, same rule as the headless command.
    _assert_no_forbidden(cmd)
    return cmd


class MockClaudeCliBackend:
    """Deterministic stand-in for the `claude` CLI — no subprocess, replayable (build §2.4
    substitution). Shapes output like the parsed `result` field of `claude -p --output-format
    json` so the mock-first proof exercises the exact same downstream path as the live backend."""

    def __init__(self, name: str | None = None, *, model: str | None = None) -> None:
        self.model = (model.strip() if model and model.strip() else None)
        self.name = name if name is not None else f"claude_code:mock:{self.model or 'default'}"
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return (f"[{self.name}] deterministic Claude Code result (h={h}) for prompt: "
                f"{prompt[:120]}")


class ClaudeCliBackend:
    """Real backend: invokes the host's already-authenticated `claude` CLI as a subprocess.

    NEVER used by the deterministic suite. `generate` is only reached from the operator-gated
    live smoke (frontier_spawn.attempt_live_smoke) after every LIVE_OPERATION_AUTHORIZED / I-X3
    / R8-operator-terms gate has passed. `build_command`/`build_env` are pure and separately
    testable so the credential invariant (§2.2) is verified without spawning anything.
    """

    def __init__(self, executable: str = "claude", *, model: str | None = None,
                 timeout_s: float = 180.0) -> None:
        self.executable = executable
        # Per-node model selection (Phase 15B `.modelsel`). A blank/absent model ⇒ CLI default
        # (no `--model` emitted, recorded roster fallback). The slug is carried verbatim; it is
        # only *confirmed* accepted by a live smoke — never fabricated.
        self.model = (model.strip() if model and model.strip() else None)
        self.name = f"claude_code:cli:{self.model or 'default'}"
        self._timeout_s = timeout_s
        # The model the CLI reported it actually ran on the last `generate`, read back from its
        # JSON response (Phase 15B `.gate`). None until a live call reports one — never the
        # requested slug, never fabricated. Consumers reconcile the executing model from this.
        self.reported_model: str | None = None
        # The value of `calls` at the moment `reported_model` was last set by a SUCCESSFUL call.
        # `reported_model` alone cannot date itself: it is never cleared, so a checkpoint reported
        # in an earlier debate survives into a later one in which every call failed, and a consumer
        # reading it would claim a live result for a debate where nothing ran. Consumers that must
        # prove "a real call succeeded AFTER this point" snapshot `calls` and compare (Phase 15D
        # `.debate`). None until a successful call reports a checkpoint.
        self.reported_model_at_call: int | None = None
        # cost-to-accepted-output instrumentation (Buildout §4). The mock backends count calls;
        # without this the REAL backend reports 0 for exactly the legs that spend the subscription.
        self.calls = 0
        # Every PID assigned to the last live CLI process boundary, for teardown evidence.
        self.last_spawned_pids: tuple[int, ...] = ()
        self.spawned_pids: tuple[int, ...] = ()

    def build_command(self, prompt: str) -> list[str]:
        # print mode + machine-readable JSON (R8 §2: the CLI's documented headless mode). No
        # `--api-key`, no permission-bypass flags: nothing that carries or weakens auth. An
        # explicit `--model <slug>` selects the per-node model; omitted ⇒ CLI default (fallback).
        cmd = [self.executable, "-p"]
        if self.model:
            cmd += [CLAUDE_CODE_MODEL_FLAG, self.model]
        cmd += ["--output-format", "json"]
        # Guard the FLAGS only (prompt not yet appended) so a benign prompt equal to a flag token is
        # never misread as one; argv is a list so subprocess never word-splits a value into a flag.
        _assert_no_forbidden(cmd)
        cmd.append(prompt)
        return cmd

    @staticmethod
    def _is_credential_key(name: str) -> bool:
        """Thin delegate to the module-level `is_credential_env_key` (kept so existing callers/tests
        referencing the method stay valid; the classification rule lives in ONE place)."""
        return is_credential_env_key(name)

    def build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Child environment with every credential- or endpoint-bearing key REMOVED. Delegates to
        the module-level `scrub_credential_env` so the one-shot worker command and the interactive
        conductor pane scrub by the exact same rule (§2.2)."""
        return scrub_credential_env(base_env)

    def _classify(self, text: str) -> bool:
        low = text.lower()
        return any(marker in low for marker in _AUTH_FAILURE_MARKERS)

    @staticmethod
    def _human_detail(raw: str) -> str:
        """The CLI's own MESSAGE, when its failure output is its JSON envelope.

        A non-zero exit still prints `{"is_error":true, ..., "result":"<the actual reason>"}`, and
        the reason lives well past any sane truncation point — so a caller (or an operator reading a
        log) saw 200 characters of `duration_api_ms`/`session_id` and none of "There's an issue with
        the selected model (fable-5)". That cost `.roundtrip` a whole live run: the model-probe
        classified an unmistakable model-unavailable answer as an unrelated CLI error and stopped.
        Falls back to the raw text whenever the output is not that envelope (fail closed to MORE
        information, never less)."""
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return raw
        if not isinstance(payload, dict):
            return raw
        for key in ("result", "error", "message", "subtype"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return raw

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        cmd = self.build_command(prompt)
        env = self.build_env()
        # counted BEFORE the call: a subscription call that fails still consumed the attempt, and
        # under-reporting spend is the dishonest direction (Buildout §4)
        self.calls += 1
        try:
            # stdin CLOSED, never inherited: `claude -p` reads piped stdin when stdin is not a TTY,
            # so a supervised worker inherits the supervisor's stdin and blocks forever on input
            # that never arrives (measured: 150 s timeout inherited, 3.5 s with DEVNULL — it is what
            # made the first `.legs` live dispatches spend a real call for an `attempted` leg). The
            # prompt travels in argv, so nothing is lost; and a governed node must not be able to
            # read the supervisor's console anyway (invariant 29).
            proc = run_managed_process(
                cmd, timeout=self._timeout_s, env=env, stdin=subprocess.DEVNULL)
            self.last_spawned_pids = proc.spawned_pids
            self.spawned_pids = tuple(sorted(set(self.spawned_pids) | set(proc.spawned_pids)))
        except FileNotFoundError as exc:  # CLI vanished between detection and spawn — fail closed
            raise ClaudeCodeAuthError(f"`{self.executable}` not found on PATH — fail closed") from exc
        if proc.returncode != 0:
            detail = self._human_detail((proc.stderr or proc.stdout or "").strip())
            if self._classify(detail):
                raise ClaudeCodeAuthError(f"claude CLI auth/rate failure: {detail[:200]} — pause (Plan §18.4)")
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {detail[:200]}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"claude CLI returned non-JSON output: {proc.stdout[:200]!r}") from exc
        # `claude -p --output-format json` shape: {type, subtype, is_error, result, ...}
        if isinstance(payload, dict) and payload.get("is_error"):
            detail = str(payload.get("result") or payload.get("subtype") or payload)
            if self._classify(detail):
                raise ClaudeCodeAuthError(f"claude CLI reported error: {detail[:200]} — pause (Plan §18.4)")
            raise RuntimeError(f"claude CLI reported error: {detail[:200]}")
        # Reconcile the EXECUTING model from the CLI's own JSON (Phase 15B `.gate`), fail-closed:
        # a checkpoint the CLI didn't report leaves `reported_model=None` (never the requested slug).
        self.reported_model = extract_reported_model(payload)
        # Stamped only when the CLI actually reported one, so the pair (model, at_call) is either
        # both-absent or a checkpoint datable to a specific successful call — never a stale model
        # carrying a fresh-looking date.
        self.reported_model_at_call = self.calls if self.reported_model else None
        result = payload.get("result") if isinstance(payload, dict) else None
        return result if isinstance(result, str) else json.dumps(payload)


# ---- The ONE rule that backs a `live` claim (Phase 15D `.gate`, U45) -------------------------
# `.debate` established this rule and applied it in one module; U45 recorded that three
# already-gated sites kept the pre-fix behaviour and could package a run that never reached a
# provider as `live`. The rule now lives HERE, beside the class it names, and every site imports
# it — one definition, so the sites cannot drift apart again (the U42 shape).


def is_live_cli_backend(backend: Any) -> bool:
    """True only for the real vendor CLI backend, decided by EXACT TYPE.

    `type(...) is` rather than `isinstance`, deliberately: a SUBCLASS may override `generate`,
    spawn nothing, set the instrumentation itself, and inherit the class identity. That is a mock
    presented as a real-provider result, which §6/§10.4 forbid outright.

    What this does NOT establish: exact type constrains an object's CLASS, not its behaviour. An
    instance whose `generate` was replaced, or a mock whose `__class__` was reassigned, still
    passes. Those are deliberate-falsification routes (U43), not closable in-process.
    """
    return type(backend) is ClaudeCliBackend


def _wrapped_cli_backend(backend: Any) -> ClaudeCliBackend | None:
    """The vendor CLI backend `backend` IS, or the one it demonstrably WRAPS (ONE documented level
    — the conductor binding), or None.

    Only a `ClaudeCodeConductorBackend` is unwrapped — checked by TYPE, not by the presence of a
    `wrapped_backend` attribute. An earlier draft used a bare `getattr`, which meant any object
    exposing that attribute name was followed: duck-typing the unwrap step in a rule whose whole
    justification is that class identity must not be inferable from shape. It did not launder a
    live claim (the inner backend is still exact-type checked) but the code did not do what its
    own docstring said, which is the defect class this unit exists to remove.

    One level, not a search: an unbounded unwrap would make "which counter am I reading?"
    unanswerable, and the freshness check is meaningless unless the snapshot and the stamp come
    from the same object.
    """
    if is_live_cli_backend(backend):
        return backend
    if not isinstance(backend, ClaudeCodeConductorBackend):
        return None
    inner = backend.wrapped_backend
    return inner if is_live_cli_backend(inner) else None


def calls_or_none(backend: Any) -> int | None:
    """Counted calls, or None when the counter is UNREADABLE — which is not the same as zero.

    ABSENT counts as unreadable too. An earlier draft defaulted a missing `calls` attribute to 0,
    which is the one reading the docstring explicitly disclaims: "no counter at all" and "a counter
    reading zero" are different facts, and only the second is evidence of anything.
    """
    try:
        calls = getattr(backend, "calls")
    except Exception:  # noqa: BLE001 — unreadable, NOT zero
        return None
    if calls is None or isinstance(calls, bool):
        return None
    try:
        return int(calls)
    except Exception:  # noqa: BLE001 — unreadable, NOT zero
        return None


def bind_calls_snapshot(backend: Any) -> int | None:
    """The bind-time call count that a later `verify_reported_checkpoint` will measure freshness
    against, or None when there is no vendor backend behind `backend` at all.

    Callers MUST take the snapshot through this function rather than reading `.calls` directly:
    it resolves the same object `verify_reported_checkpoint` will read, so the two numbers describe
    one counter. A conductor wrapper keeps its OWN `calls` tally, which is not the counter that
    stamps checkpoints — comparing across the two would compare unrelated numbers.
    """
    cli = _wrapped_cli_backend(backend)
    return calls_or_none(cli) if cli is not None else None


def verify_reported_checkpoint(backend: Any, *, calls_before: int | None) -> dict[str, Any] | None:
    """The verification record backing a `live` claim, or None. FOUR conditions, ALL required:

    1. the backend IS (or directly wraps) the exact vendor CLI class — not a subclass, not a duck;
    2. a call was SPENT since `calls_before` (an unreadable counter fails closed to "spent", since
       under-reporting spend is the dishonest direction);
    3. it carries a non-blank checkpoint STRING that its own `generate` read back out of the CLI's
       JSON response (`extract_reported_model`) — a requested `--model` slug never reaches it;
    4. that checkpoint is datable to a call made AFTER `calls_before`. `reported_model` is never
       cleared and `calls` is a LIFETIME counter, so without (4) a backend reused from an earlier
       run — every call in THIS one having failed — still presents a verified checkpoint for a run
       in which nothing succeeded.

    `calls_before=None` means "no snapshot was taken", which cannot satisfy (4) and therefore
    cannot yield a record. Fail closed: the absence of evidence is not evidence. Because of that,
    condition (2) is evaluated only against a real snapshot — there is no "any call at all" fallback
    here, and an UNREADABLE counter fails CLOSED (no verification), not open. That is the opposite
    of the leg vocabulary's treatment of an unreadable counter, deliberately: for reporting SPEND,
    over-reporting is the honest direction, but for verifying a LIVE claim, under-claiming is.

    STATED LIMIT (U43): these are instrumentation attributes on an object the CALLER supplies, and
    exact-type checking constrains its class, not its behaviour. Forging both stamps on a genuine
    backend, reassigning `__class__`, or replacing `generate` on a genuine instance all still pass.
    What this rules out is every ACCIDENTAL and every mock-SHAPED path. `live` is trustworthy
    exactly as far as the caller is.
    """
    cli = _wrapped_cli_backend(backend)
    if cli is None:
        return None
    if calls_before is None:
        return None
    calls = calls_or_none(cli)
    if calls is None or calls <= calls_before:
        # No call spent since the snapshot — a checkpoint with no counted call is CONTRADICTORY
        # evidence (nothing ran, yet something reported), and an unreadable counter is no evidence
        # at all. Both fail closed to "unverified".
        return None
    reported = getattr(cli, "reported_model", None)
    if not isinstance(reported, str) or not reported.strip():
        return None
    at_call = getattr(cli, "reported_model_at_call", None)
    if not isinstance(at_call, int) or isinstance(at_call, bool):
        return None
    if at_call <= calls_before:
        return None
    return {"model": reported.strip(), "verified": True}


# ---- Conductor-capable binding (Phase 15B `.conductor`, directive §11 15B) ------------------
# The conductor is an INTERFACE + runtime selection (invariant 3, current selection Fable 5).
# Phase 4's ConductorAdapter binds a reasoning backend exposing {model_name, calls, propose_plan}
# (the `ConductorBackend` protocol). The live worker backend above exposes `generate` instead, so
# this bridges the two: it wraps a claude_code `Backend` and produces conductor DECISION dicts.
# It adds NO authority — it neither spawns nor self-authorizes (the governed live-conductor spawn
# in node_runtime/supervisor/conductor_spawn.py gates the live path; the ConductorAdapter owns the
# subscription governor + the MCP publish) — and holds NO credential (§2.2): the wrapped backend
# invokes the host `claude` CLI whose OAuth token stays in its host-native store, never here.

# The node_class a conductor-bound claude_code backend maps to (node.schema.json). Distinct from
# the worker `CLAUDE_CODE_NODE_CLASS` above so the roster/Inspector can tell a conductor binding
# from a reasoning worker.
CLAUDE_CODE_CONDUCTOR_NODE_CLASS = "conductor"

# A conductor decomposition can be larger than a worker answer; still bounded (cost governance).
CLAUDE_CODE_CONDUCTOR_MAX_TOKENS = 1024

# Per-file excerpt bound so the conductor prompt names AND samples its governing policies without
# blanket-forwarding whole files (invariant 8 — scoped context; these are the conductor's OWN
# policy files, but the prompt stays bounded and deterministic regardless of file size).
_CONDUCTOR_FILE_EXCERPT = 300

_DECOMPOSITION_INSTRUCTION = (
    "You are the Sovereign conductor. Decompose the objective into a small set of worker "
    "subtasks. Reply with ONLY a JSON object of the form "
    '{"proposed_tasks": [{"desc": "<subtask>", "capability": "reasoning|coding|review"}], '
    '"rationale": "<one line>"}. Emit no prose outside the JSON.'
)


def _build_decomposition_prompt(objective: str, conductor_files: dict[str, str], cycle: int) -> str:
    """Pure, deterministic conductor prompt: the governing policy files (named + bounded excerpt),
    the cycle, and the objective. No credential, no external state; the conductor reasons over its
    OWN policies (not other nodes' transcripts — invariant 8 is about blanket cross-node forwarding,
    which this is not)."""
    policy_lines = []
    for name in sorted(conductor_files):
        body = (conductor_files[name] or "").strip().replace("\r\n", "\n")
        excerpt = body[:_CONDUCTOR_FILE_EXCERPT]
        policy_lines.append(f"- {name}: {excerpt}")
    policies = "\n".join(policy_lines) if policy_lines else "(none loaded)"
    return (
        f"{_DECOMPOSITION_INSTRUCTION}\n\n"
        f"Governing conductor policy files (from shared memory):\n{policies}\n\n"
        f"Cycle: {cycle}\n"
        f"Objective:\n{objective}\n"
    )


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    """Best-effort, fail-closed extraction of a single JSON object from a model reply. Tries the
    whole string, any fenced ```json block, then the first `{`…last `}` slice. Returns None if no
    valid JSON object is present — never guesses."""
    text = (raw or "").strip()
    candidates: list[str] = []
    if "```" in text:
        for seg in text.split("```"):
            seg = seg.strip()
            if seg[:4].lower() == "json":
                seg = seg[4:].strip()
            if seg:
                candidates.append(seg)
    candidates.append(text)
    i, j = text.find("{"), text.rfind("}")
    if 0 <= i < j:
        candidates.append(text[i : j + 1])
    for cand in candidates:
        try:
            val = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(val, dict):
            return val
    return None


def _parse_decomposition(raw: str) -> tuple[list[dict[str, Any]], str]:
    """Turn a model reply into a validated task list, FAIL-CLOSED. Returns (tasks, mode):
    `mode="structured"` only when every task has a non-empty string `desc` and `capability`, plus
    an optional `deps` list of 1-based integer indices naming other proposed tasks; any
    missing/malformed element ⇒ `([], "unstructured")`. A conductor decision NEVER fabricates a
    decomposition the model did not actually produce (honesty; the operator sees the raw excerpt
    and can re-prompt).

    `deps` is carried (rather than dropped) because a decomposition's ORDERING is part of what the
    conductor proposed: the task graph consumes it and the plan gate's `plan_acyclic` criterion
    evaluates it (Phase 15D `.flow`). It is validated here and never inferred — a task with no
    declared deps gets `[]`, never a guessed dependency."""
    obj = _extract_json_object(raw)
    if not isinstance(obj, dict):
        return [], "unstructured"
    tasks_raw = obj.get("proposed_tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        return [], "unstructured"
    tasks: list[dict[str, Any]] = []
    for task in tasks_raw:
        if not isinstance(task, dict):
            return [], "unstructured"
        desc, cap = task.get("desc"), task.get("capability")
        if not (isinstance(desc, str) and desc.strip() and isinstance(cap, str) and cap.strip()):
            return [], "unstructured"
        deps = task.get("deps", [])
        # bool is an int subclass: `deps: [True]` must not pass as an index (fail closed)
        if not isinstance(deps, list) or any(isinstance(d, bool) or not isinstance(d, int)
                                             for d in deps):
            return [], "unstructured"
        # enforce the range this docstring promises, so a SECOND consumer of this parser does not
        # inherit unvalidated indices (`control_plane` re-checks ordering, which is its own concern)
        if any(d < 1 or d > len(tasks_raw) for d in deps):
            return [], "unstructured"
        tasks.append({"desc": desc.strip(), "capability": cap.strip(), "deps": list(deps)})
    return tasks, "structured"


class ClaudeCodeConductorBackend:
    """Conductor-capable wrapper over a claude_code worker `Backend` (`generate`-based). Exposes
    the `ConductorBackend` contract (`model_name`, `calls`, `propose_plan`) so the Phase-4
    ConductorAdapter can bind the LIVE claude_code backend as its runtime selection (I-CN1), while
    the whole governed conductor path — file load order, CANDIDATE-only publish, subscription
    governor, succession export — is reused verbatim from Phase 4.

    Holds NO credential (§2.2): it only calls the wrapped backend's `generate`, which invokes the
    host `claude` CLI (host-native OAuth store). Adds NO authority: no spawn, no self-authorization.
    A `BackendAuthPause` from the wrapped backend propagates unswallowed so the supervisor pauses
    fail-closed (Plan §18.4)."""

    def __init__(self, backend: Backend, *, model_name: str | None = None) -> None:
        self._backend = backend
        # The EXECUTING model recorded on every decision. Defaults to the wrapped backend's name so
        # the decision is honest about which checkpoint actually ran (the conductor's *selection*
        # label lives on the adapter capability and may differ — directive §11 15D).
        self.model_name = model_name or getattr(backend, "name", CLAUDE_CODE_ADAPTER)
        self.calls = 0

    @property
    def wrapped_backend(self) -> Backend:
        """The backend this conductor binding wraps, read-only.

        Exposed so a governed caller can apply `verify_reported_checkpoint` to the object that
        actually stamps checkpoints, instead of reaching into `_backend` from another module or
        reading this wrapper's own `calls` tally (which counts `propose_plan` invocations, not CLI
        calls). Grants no authority: the backend only produces text.
        """
        return self._backend

    @property
    def reported_model(self) -> str | None:
        """The RAW checkpoint the wrapped backend last read back from a live CLI JSON, or None.

        Delegating (rather than caching) keeps one source of truth. Fail closed on blank/absent/
        non-string. **This value is LIFETIME-scoped and carries no freshness**: it is raw evidence,
        not a verification. Any consumer deciding whether a run was live must go through
        `verify_reported_checkpoint` with a bind-time snapshot — reading this property and treating
        a non-blank string as proof is exactly the defect U45 recorded at three sites.
        """
        reported = getattr(self._backend, "reported_model", None)
        return reported if isinstance(reported, str) and reported.strip() else None

    def propose_plan(self, objective: str, conductor_files: dict[str, str], cycle: int) -> dict[str, Any]:
        """Decompose an objective into a conductor DECISION dict (the conductor PROPOSES; the
        ConductorAdapter records it as CANDIDATE — invariant 16). Deterministic wrapper: builds a
        bounded prompt, calls the wrapped backend once, parses the reply fail-closed. Never
        fabricates tasks the model did not return."""
        self.calls += 1
        prompt = _build_decomposition_prompt(objective, conductor_files, cycle)
        # Snapshotted BEFORE the call, so the freshness check below is scoped to THIS call and not
        # to the backend's lifetime (U45 site 3: pre-fix, a checkpoint reported by an earlier call
        # verified a decision in which the CLI reported nothing — the exact staleness weakness
        # `.debate` had already fixed for debate).
        calls_before = bind_calls_snapshot(self._backend)
        raw = self._backend.generate(prompt, max_tokens=CLAUDE_CODE_CONDUCTOR_MAX_TOKENS)
        tasks, mode = _parse_decomposition(raw)
        # Reconcile the EXECUTING model (Phase 15B `.gate`) under the ONE verification rule: the
        # checkpoint must come from the exact vendor CLI class AND be datable to the call just
        # made. When it is not (mock path, a CLI that reported nothing, a stale checkpoint) the
        # recorded `model` stays the SELECTION label and `model_verified=False` — a CANDIDATE is
        # never read as a confirmed checkpoint, and a checkpoint id is never fabricated.
        verification = verify_reported_checkpoint(self._backend, calls_before=calls_before)
        verified = verification is not None
        return {
            "model": verification["model"] if verification else self.model_name,
            "model_selection": self.model_name,  # the requested slug / selection label (always)
            "model_verified": verified,
            "cycle": cycle,
            "objective_ack": objective,
            "proposed_tasks": tasks,
            "files_considered": sorted(conductor_files),
            "parse_mode": mode,                 # "structured" | "unstructured" (fail-closed)
            "raw_excerpt": (raw or "")[:500],   # bounded; the operator sees what the model said
            "rationale": (f"live conductor decomposition via {self.model_name} "
                          f"({mode}; {len(tasks)} task(s))"),
        }


def claude_code_conductor_descriptor(requested_model: str | None = None) -> dict[str, Any]:
    """Roster/capability descriptor for a conductor-bound live claude_code node, with the per-node
    model resolution SURFACED (directive §11 15B, never silent). Reuses `claude_code_roster_descriptor`
    (same `model_ref` honesty) and re-labels it as the conductor node_class + `conductor_capable`."""
    descriptor = claude_code_roster_descriptor(requested_model)
    descriptor["node_class"] = CLAUDE_CODE_CONDUCTOR_NODE_CLASS
    descriptor["role"] = "conductor"
    descriptor["conductor_capable"] = True
    return descriptor


# assert the Backend protocol is satisfied at import (both are structural Backends)
_MOCK: Backend = MockClaudeCliBackend()
# assert the conductor wrapper structurally satisfies the ConductorBackend contract at import
_MOCK_CONDUCTOR: ConductorBackend = ClaudeCodeConductorBackend(MockClaudeCliBackend())


def build_claude_code_adapter(context: AdapterContext, mcp_client: Any, backend: Backend) -> ModelWorkerAdapter:
    """Configure the shared, already-governed ModelWorkerAdapter as the live `claude_code`
    frontier worker. `context` MUST come from the supervisor (spawned_by_supervisor=True) — the
    base contract refuses a naked launch (I-C1). Holds no credential (base default False)."""
    return ModelWorkerAdapter(
        context, mcp_client, backend,
        adapter_name=CLAUDE_CODE_ADAPTER, node_class="worker_reasoning", locality="frontier",
        offline_profile_eligible=False, requires_network=True,
        capability_descriptors=CLAUDE_CODE_CAPABILITY_DESCRIPTORS, subscription_backed=True)
