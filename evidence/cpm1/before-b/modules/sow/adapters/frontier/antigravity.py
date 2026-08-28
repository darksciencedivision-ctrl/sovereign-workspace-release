"""Gemini · Antigravity (`agy`) — headless worker adapter. Phase 18B `.adapter`, register OP-12.

The second of the two providers the operator authorized at OP-12 (directive §17), on the
operator's Google AI Pro subscription. Same shape as its sibling `grok_build`: a headless
reasoning worker behind the SAME governed `ModelWorkerAdapter` contract, sharing one argv/env
policy (`provider_cli_common`) so the two providers cannot drift apart. No parallel registry, no
second control path (operator directive §8).

**Never the retired CLI.** Operator directive §4.2/§14 forbids falling back to the personal-account
Gemini CLI, and `node@1.0`'s `gemini_cli` enum member names exactly that retired tool — so this
adapter does not borrow it as a vocabulary shortcut. The id is the operator's own OP-12 product-layer
id, and the display name is "Gemini · Antigravity" everywhere an operator can read it.

**The boundary this module sat behind, and where it moved (U227 → OP-12.1).** Through 18B/18C
`node@1.0`'s `adapter` enum had no member for `google_antigravity`, the enum is frozen and the
amendment was operator-reserved, so `NodeRegistry.register` refused. **The operator ruled on
2026-08-01 (OP-12.1, directive §17.1): by SUCCESSOR SCHEMA** — `schemas/node.schema@1.1.json`
beside the untouched `@1.0` — and a Sovereign node record can now name this provider. Note what
the successor did NOT do: it did not touch `gemini_cli`, whose meaning is still the retired
personal-account CLI above, and it did not authorize a live call, which still needs the operator's
switch, the terms determination and an I-X3 lease on `google_antigravity_subscription`
(allowance 1).

**Credential posture (§13 / build directive §2.2).** The adapter invokes the host's
already-authenticated `agy` CLI, which keeps its Google OAuth in its own host-native store. This
code never reads, stores, prints, or transmits it; the child environment is scrubbed of every key-
and endpoint-bearing variable, `GEMINI_API_KEY`/`GOOGLE_API_KEY` included.

**Command surface (§2 — the installed CLI is authoritative).** Read off this host's captured
`agy --help` (2026-07-31): `-p/--print`, `--output-format` (`text | json | stream-json`),
`--model`, `--mode` (`accept-edits, plan`), `--add-dir`. Recorded deltas: `agy` has **no `--cwd`
flag**, so the workspace is bound by the child's working directory plus `--add-dir`; and the
directive's §10 spelling `stream-json` is confirmed present, though this sub-step's one-shot
headless mode uses `json`.

**`--sandbox` is deliberately not emitted.** The flag exists, but its entire documented meaning is
"Run in a sandbox with terminal restrictions enabled" — which does not say what is restricted. 18A
recorded that an unverified containment claim is worse than none, and that holds here: enabling a
flag whose behaviour this build cannot describe would put an unfalsifiable safety claim into the
evidence. Revisited on live evidence at 18C (U261), never on a guess.
"""
from __future__ import annotations

from typing import Any, Sequence

from adapters.base.backend import Backend
from adapters.base.contract import AdapterContext
from adapters.frontier import provider_cli_common as C
from adapters.model_adapter import ModelWorkerAdapter
from control_plane.profiles.live_authorization import ANTIGRAVITY_PROVIDER
from node_runtime.supervisor.subscription_governor import canonical_subscription_ref

# Product-layer id from the control-plane export, never re-spelled as a literal here (U254).
ANTIGRAVITY_ADAPTER = ANTIGRAVITY_PROVIDER
ANTIGRAVITY_DISPLAY = "Gemini · Antigravity"
# Operator directive §12 — a SEPARATE subscription resource at allowance 1, never merged with
# Grok's and never raised without a new operator amendment. The spelling comes from the governor
# that owns it: the cap is enforced per ref, so two spellings would be two buckets (U76, Md-4).
ANTIGRAVITY_SUBSCRIPTION = canonical_subscription_ref(ANTIGRAVITY_PROVIDER)

MIN_ANTIGRAVITY_VERSION: tuple[int, int, int] = (0, 1, 0)

ANTIGRAVITY_PROMPT_FLAG = "-p"             # `-p` / `--print`: run one prompt and print the response
ANTIGRAVITY_MODEL_FLAG = "--model"
ANTIGRAVITY_ADD_DIR_FLAG = "--add-dir"     # workspace binding; this CLI has no `--cwd`
ANTIGRAVITY_OUTPUT_FORMAT_FLAG = "--output-format"
ANTIGRAVITY_OUTPUT_FORMAT = "json"         # `text | json | stream-json`
ANTIGRAVITY_MODE_FLAG = "--mode"
# The narrower of the two values this CLI's own enum offers (`accept-edits, plan`), pinned so a
# node-controlled config cannot supply the permissive one instead (§11). An argument the harness
# honours — not OS-level containment (I-29; U25 remains owed).
#
# RESTORED at Phase 19 unit 1 by operator ruling OP-13, with this comment rather than a new one:
# the untagged post-18E range moved the pin to `accept-edits` and replaced the sentence above with
# an assertion that Antigravity's own native permission settings narrow it separately. Invariant 29
# — never trust the harness — forbids that basis, and D-P18-13/U317 say a provider CLI's own
# always-approve mode is never operator approval. The deleted reasoning is the finding; it is back.
ANTIGRAVITY_HEADLESS_MODE = "plan"

ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                 "min_context": 128000, "locality": "frontier_ok"}},
    {"capability": "synthesis", "requirements": {"structured_output": True, "min_context": 128000}},
]


class AntigravityCliBackend(C.FrontierProviderCliBackend):
    """Live headless backend: `agy --mode plan [--model <slug>] [--add-dir <ws>]
    --output-format json -p <prompt>`, spawned with the workspace as its working directory.

    Never used by the deterministic suite. `generate` REFUSES while `_LIVE_SPAWN_PATH_WIRED` is
    False — a fence, not the absence of a caller (U268; see the base class)."""

    provider = ANTIGRAVITY_ADAPTER
    executable_candidates = ("agy", "agy.cmd", "agy.exe", "agy.ps1")
    # No supervised, governor-leased launch path exists for this provider yet (U268).
    _LIVE_SPAWN_PATH_WIRED = False

    def build_command(self, prompt: str) -> list[str]:
        argv: list[str] = [self.executable, ANTIGRAVITY_MODE_FLAG, ANTIGRAVITY_HEADLESS_MODE]
        if self.model:
            argv += [ANTIGRAVITY_MODEL_FLAG, self.model]
        if self.workdir:
            # No `--cwd` on this CLI: the workspace is the child's working directory — which
            # `generate` sets THROUGH the job-object boundary (`run_managed_process(cwd=...)`, an
            # optional parameter added for exactly this) — and `--add-dir` states it explicitly to
            # the agent as well.
            argv += [ANTIGRAVITY_ADD_DIR_FLAG, self.workdir]
        argv += [ANTIGRAVITY_OUTPUT_FORMAT_FLAG, ANTIGRAVITY_OUTPUT_FORMAT]
        self._guard(argv)          # flags only — the prompt is appended after the guard
        argv += [ANTIGRAVITY_PROMPT_FLAG, prompt]
        return argv


def build_interactive_antigravity_command(executable: str, *, model: str | None = None,
                                          workdir: str | None = None) -> list[str]:
    """Argv for an INTERACTIVE `agy` TUI session in a supervised pane (18B `.picker`;
    operator directive §9).

    Distinct from `AntigravityCliBackend.build_command` (the one-shot `-p … --output-format json`
    worker). No `-p`/`--print`, no `--output-format`, and no `--prompt-interactive`: bare `agy` with
    flags opens the session the operator types into. `--prompt-interactive` is omitted for the same
    reason grok's positional `[PROMPT]` is — an initial prompt would be this build speaking in a
    session the operator owns.

    Pinned, each for a reason (§11 / T2 — agy reads project config and rules files the node's own
    tree may contain):
      * `--mode plan` — the narrower of this CLI's own two values (`accept-edits, plan`), the same
        one the headless path pins, so a config default cannot supply the permissive one. Never
        `--dangerously-skip-permissions`: the shared guard refuses it;
      * `--add-dir <workspace>` — this CLI has NO `--cwd`, so the workspace binding is two facts:
        the child's working directory (the launch ticket's `cwd`, which the shell's ConPTY spawn
        applies) and this explicit statement of it to the agent. Emitting `--add-dir` without the
        ticket's `cwd` would be a claim about a binding only half made;
      * `--model <slug>` when one was selected; `None` ⇒ CLI default, RECORDED as a fallback.

    Pure and deterministic; the credential stays entirely outside (§13)."""
    argv: list[str] = [executable, ANTIGRAVITY_MODE_FLAG, ANTIGRAVITY_HEADLESS_MODE]
    slug = model.strip() if model and model.strip() else None
    if slug:
        argv += [ANTIGRAVITY_MODEL_FLAG, slug]
    ws = str(workdir).strip() if workdir and str(workdir).strip() else None
    if ws:
        argv += [ANTIGRAVITY_ADD_DIR_FLAG, ws]
    C.assert_no_forbidden_provider_args(argv)
    C.assert_no_untrusted_instruction_args(argv)
    return argv


def MockAntigravityCliBackend(*, model: str | None = None) -> C.MockFrontierProviderBackend:  # noqa: N802
    """Deterministic stand-in, spawning nothing (build §2.4 substitution)."""
    return C.MockFrontierProviderBackend(ANTIGRAVITY_ADAPTER, model=model)


mock_backend = MockAntigravityCliBackend


def probe_antigravity(*, runner: Any = None, executable: str | None = None) -> C.ProviderCliProbe:
    """Presence, version and the model inventory from `agy models` — the CLI's own listing and
    nothing else (operator directive §8). Spends no tokens and never raises.

    This CLI has **no offline auth-reporting surface**: nothing it prints without a live call says
    whether the operator is signed in, so the auth state is UNVERIFIED — never AUTHENTICATED (that
    would assume a session) and never AUTH_REQUIRED (that would be a verdict about the operator's
    login that nothing here observed)."""
    if runner is None:
        raise ValueError("probe_antigravity needs a runner: this module does not spawn a CLI "
                         "implicitly")
    return C.probe_provider_cli(provider=ANTIGRAVITY_ADAPTER, executable=executable, runner=runner,
                                min_version=MIN_ANTIGRAVITY_VERSION,
                                parse_models=C.parse_antigravity_models, reports_auth=False)


def roster_descriptor(requested_model: str | None = None,
                      available: Sequence[str] | None = None) -> dict[str, Any]:
    """Roster/capability descriptor for an Antigravity node with the per-node model resolution
    SURFACED (recorded fallback, never silent). A slug outside a known inventory is REFUSED
    (§8: model identifiers are never invented).

    Note for the picker sub-step: this subscription's own listing includes models from two OTHER
    vendors (`claude-sonnet-4-6`, `gpt-oss-120b-medium`). That is the provider's inventory, not a
    parsing error, and this build reports it verbatim — but presenting a third party's model under
    a Google subscription badge is an I-21 accounting and UI-honesty question, recorded as U246."""
    import copy  # noqa: PLC0415

    slug, note = C.resolve_model_ref(requested_model, available)
    return {
        "adapter": ANTIGRAVITY_ADAPTER,
        "display": ANTIGRAVITY_DISPLAY,
        "node_class": AntigravityCliBackend.node_class,
        "locality": "frontier",
        "subscription_backed": True,
        "subscription_resource": ANTIGRAVITY_SUBSCRIPTION,
        "capability_descriptors": copy.deepcopy(ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS),
        "roles": list(AntigravityCliBackend.supported_roles),
        "model_ref": {
            "requested": requested_model,
            "resolved_slug": slug,
            "verified": bool(slug and available),
            "is_fallback": slug is None,
            "note": note,
        },
    }


def build_adapter(context: AdapterContext, mcp_client: Any, backend: Backend) -> ModelWorkerAdapter:
    """Configure the shared, already-governed `ModelWorkerAdapter` as a live `google_antigravity`
    frontier reasoning worker. `context` MUST come from the supervisor — the base contract refuses
    a naked launch (I-C1). Holds no credential (base default False)."""
    return ModelWorkerAdapter(
        context, mcp_client, backend,
        adapter_name=ANTIGRAVITY_ADAPTER, node_class=AntigravityCliBackend.node_class,
        locality="frontier", offline_profile_eligible=False, requires_network=True,
        capability_descriptors=ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS,
        subscription_backed=True)
