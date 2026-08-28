"""Grok Build (`grok`) — headless worker adapter. Phase 18B `.adapter`, register OP-12.

The first of the two providers the operator authorized at OP-12 (directive §17). This module is
the `.adapter` sub-step: a headless reasoning worker behind the SAME governed contract every other
model node in this build uses — `ModelWorkerAdapter`, which reads scoped context from MCP, runs
the node-local gate, and publishes CANDIDATE with provenance. The backend is the only new surface.
There is no parallel registry and no second control path (operator directive §8).

Deliberately NOT here, and owed to the sub-steps that follow:
  * the picker option and the launch ticket (`.picker`, since done — that sub-step also added
    `build_interactive_grok_command` BELOW, the argv for the supervised ConPTY pane, because the
    interactive argv is this provider's own knowledge and belongs beside its headless twin);
  * the I-X3 governor lease on `grok_build_subscription` (allowance 1, never merged with the
    Antigravity subscription — operator directive §12);
  * any live call at all (`18C`, and only behind the operator's own `config/live_operation.json`).

**The boundary this module sat behind, and where it moved (U227 → OP-12.1).** Through 18B/18C:
`node@1.0`'s `adapter` enum had no member for `grok_build`, the enum is frozen at Phase 0 and
pinned by Architecture Plan §9.1, and the amendment was operator-reserved — so `NodeRegistry.
register` refused, and `gate/phase-18b` deliberately did not close on "U227 is answered". **The
operator ruled on 2026-08-01 (OP-12.1, directive §17.1): by SUCCESSOR SCHEMA.**
`schemas/node.schema@1.1.json` sits beside the still-untouched `@1.0` and admits `grok_build`, so
a Sovereign node record CAN now name this provider. Two things did not change with it: the frozen
`@1.0` file and Plan §9.1 are exactly as they were, and admitting the vocabulary admits nothing
else — a live call still needs the operator's `config/live_operation.json`, the OP-9-class terms
determination, and an I-X3 lease on `grok_build_subscription` (allowance 1).

**Credential posture (§13 / build directive §2.2).** The adapter invokes the host's
already-authenticated `grok` CLI, which keeps its xAI OAuth in its own host-native store. This
code never reads, stores, prints, or transmits that credential; there is no API-key path at all,
and the child environment is scrubbed of every key- and endpoint-bearing variable
(`provider_cli_common.scrub_provider_env`) so none could be transmitted even by accident.

**Command surface (§2 — the installed CLI is authoritative).** Every flag below was read off this
host's captured `grok --help` (2026-07-31, `docs/evidence/live/phase18a_host_recon.json`):
`-p/--single` (single-turn headless prompt), `--output-format json`, `--cwd`, `--permission-mode`,
`--no-memory`, `-m/--model`. Recorded deltas: the operator directive's §10 example carried
`--no-auto-update`, which **this build of `grok` does not have** — omitted, not silently
substituted; and §10 preferred `--output-format streaming-json` "for live pane updates", which this
sub-step does not use because a one-shot headless worker consumes a single final answer. The
streaming spelling is confirmed present and is the `.picker` sub-step's to use for a live pane. `grok
agent stdio` (ACP) is not used: directive §10 permits it only if a fitting JSON-RPC/ACP client
already exists in this repository, and none does, so building one would be a new general framework
the directive tells us not to write — recorded as **U262**, because "we did not use the transport
the directive mentioned" is a decision an auditor should find written down rather than infer from
absence.
"""
from __future__ import annotations

from typing import Any, Sequence

from adapters.base.backend import Backend
from adapters.base.contract import AdapterContext
from adapters.frontier import provider_cli_common as C
from adapters.model_adapter import ModelWorkerAdapter
from control_plane.profiles.live_authorization import GROK_PROVIDER
from node_runtime.supervisor.subscription_governor import canonical_subscription_ref

# The product-layer provider id, taken from the control-plane export rather than spelled again
# here: a literal in two places is how `ollama_local`-class drift starts (U254).
GROK_ADAPTER = GROK_PROVIDER
GROK_DISPLAY = "Grok Build"
# ...and the subscription ref from the governor that OWNS the spelling, for the same reason at
# higher stakes: the I-X3 cap is enforced per ref, so a second spelling of one real subscription is
# a second bucket, each "at allowance" — the U76 defect. The first draft of this file re-spelled it
# as a literal two lines after citing U254 against exactly that (spec-audit Md-4).
GROK_SUBSCRIPTION = canonical_subscription_ref(GROK_PROVIDER)   # allowance 1, never merged (§12)

# A real, parseable release is the bar — not a brittle exact build. Unparseable ⇒ fails closed.
# Equal to the 18A tool's `MIN_GROK_VERSION` by test, not by hope.
MIN_GROK_VERSION: tuple[int, int, int] = (0, 1, 0)

# `grok` argv building blocks, named so the exact CLI spelling is easy to confirm against the
# capture; the load-bearing safety (no widening flag, no credential, an explicit mode) does not
# depend on their spelling.
GROK_PROMPT_FLAG = "-p"              # `-p, --single <PROMPT>`: prints the response and exits
GROK_MODEL_FLAG = "-m"
GROK_CWD_FLAG = "--cwd"
GROK_OUTPUT_FORMAT_FLAG = "--output-format"
GROK_OUTPUT_FORMAT = "json"          # `plain | json | streaming-json | streaming-messages-json`
GROK_PERMISSION_MODE_FLAG = "--permission-mode"
# `--no-memory` ("Disable cross-session memory for this session") is emitted because the capture
# documents it on the surface this build uses and cross-session memory is a blanket-context vector:
# a node's prior conversations would enter this one without passing the scoped-context compiler
# (invariants 8/9). Narrowing, node-controlled by default, pinnable here — so it is pinned.
GROK_NO_MEMORY_FLAG = "--no-memory"
# Pinned so a node-controlled `~/.grok/config.toml` cannot supply a permissive default instead
# (§11). `plan` is a REASONED choice, not a documented ranking: the CLI's enum (default,
# acceptEdits, auto, dontAsk, bypassPermissions, plan) is not ordered by its help, and calling it
# "the most restrictive value" would be an inference stated as evidence. What is enforced is
# narrower: none of the auto-approving values can be emitted at all (`FORBIDDEN_PERMISSION_MODES`).
#
# MEASURED AND LEFT ALONE (18E `.live.shape`, 2026-08-02, U310). Grok's single-turn `-p` run
# returns `{"text": "", "stopReason": "cancelled", …}` on this host — the CLI says nothing — and
# the first reading of that was that `plan` had no approval channel to hand a plan to. A second
# governed live probe with `--permission-mode default` was run to test exactly that, and it
# CANCELLED IDENTICALLY. The mode is not the cause, so the pin does not move: changing it would
# have been a widening bought with a refuted hypothesis. The real cause is open (U310).
#
# RE-EXAMINED AND RESTORED at Phase 19 unit 1 (U327 settled, D-P19-1). The untagged post-18E range
# moved this to `default` and DELETED the paragraph above; the loop re-read the two live receipts
# it cites (`docs/evidence/live/phase18e_probe_document_shape_20260802T0219Z.json`, `plan`,
# `accepted: false`; `..._grok_default_mode_20260802T0224Z.json`, `default`, `accepted: false`) and
# they still say what they said — the widening buys no measured behaviour. `--no-plan`, which the
# same range emitted beside `default` and removed from `FORBIDDEN_PROVIDER_ARGS`, is gone with it:
# the installed capture reads "Disable plan mode", so it is this pin's cancellation under another
# name. If a live run ever shows plan mode blocking a governed worker, that is a MEASUREMENT and
# the basis for an amendment — it is not an assumption this build gets to make in advance.
GROK_HEADLESS_PERMISSION_MODE = "plan"
GROK_MINIMAL_FLAG = "--minimal"
GROK_NO_ALT_SCREEN_FLAG = "--no-alt-screen"
GROK_NO_SUBAGENTS_FLAG = "--no-subagents"
GROK_DISABLE_WEB_SEARCH_FLAG = "--disable-web-search"
# `--allow` is NOT here and is forbidden by the shared guard again (U340, Phase 19 unit 1). The
# untagged post-18E range emitted `--allow mcp__sovereign__*` and took `--allow` off the forbidden
# list to do it; the installed capture calls that flag "Permission allow rule", i.e. provider tool
# permission granted by an argv. A pane still REACHES Sovereign MCP — `.grok/config.toml` declares
# the server — it simply no longer arrives with its tool calls pre-approved, which is the
# fail-closed direction while the authority path itself is still being restored (U326, unit 19.2).

GROK_REASONING_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                 "min_context": 128000, "locality": "frontier_ok"}},
    {"capability": "synthesis", "requirements": {"structured_output": True, "min_context": 128000}},
]


class GrokCliBackend(C.FrontierProviderCliBackend):
    """Live headless backend: `grok --cwd <ws> --permission-mode plan --no-memory
    --no-subagents --disable-web-search [-m <slug>] --output-format json -p <prompt>`.

    Never used by the deterministic suite — `build_command` and `build_env` are pure and separately
    tested. `generate` REFUSES while `_LIVE_SPAWN_PATH_WIRED` is False, which is the mechanism, not
    the absence of a caller (U268; see the base class)."""

    provider = GROK_ADAPTER
    executable_candidates = ("grok", "grok.cmd", "grok.exe", "grok.ps1")
    # No supervised, governor-leased launch path exists for this provider yet — `generate` refuses
    # while this is False (U268). It flips in the commit that wires that path, not before.
    _LIVE_SPAWN_PATH_WIRED = False

    def build_command(self, prompt: str) -> list[str]:
        argv: list[str] = [self.executable]
        if self.workdir:
            argv += [GROK_CWD_FLAG, self.workdir]
        argv += [GROK_PERMISSION_MODE_FLAG, GROK_HEADLESS_PERMISSION_MODE,
                 GROK_NO_MEMORY_FLAG, GROK_NO_SUBAGENTS_FLAG, GROK_DISABLE_WEB_SEARCH_FLAG]
        if self.model:
            argv += [GROK_MODEL_FLAG, self.model]
        argv += [GROK_OUTPUT_FORMAT_FLAG, GROK_OUTPUT_FORMAT]
        # Guard the FLAGS only — the prompt is appended afterwards, so a benign prompt that happens
        # to equal a flag token is never misread as smuggling one (argv is a list; subprocess never
        # word-splits a value into a separate flag).
        self._guard(argv)
        argv += [GROK_PROMPT_FLAG, prompt]
        return argv


def build_interactive_grok_command(executable: str, *, model: str | None = None,
                                   workdir: str | None = None) -> list[str]:
    """Argv for an INTERACTIVE `grok` TUI session in a supervised pane (18B `.picker`;
    operator directive §9).

    Distinct from `GrokCliBackend.build_command`, which is the one-shot headless worker
    (`-p … --output-format json`). Here there is NO `-p`, NO `--output-format` and NO positional
    PROMPT: `grok [OPTIONS]` with no prompt argument opens the TUI the operator types into, which is
    what §9 asks for. The captured usage line — `grok [OPTIONS] [PROMPT] [COMMAND]` — is the
    authority for that shape, and the omitted `[PROMPT]` is deliberate: an initial prompt would be
    this build putting words in a session the operator owns.

    What IS pinned, and why each one (§11 — provider tool permission is subordinate to the launch
    ticket, and T2 — `~/.grok/config.toml` is node-controlled untrusted input):
      * `--cwd <workspace>` — the governed workspace binding the ticket authorized;
      * `--permission-mode plan` — the same value the headless path pins, so a config default
        cannot supply an auto-approving one. Never `--always-approve`/`bypassPermissions`: the
        shared guard refuses them, and this session gets no wider authority than the headless one.
        `--no-plan` is not emitted and is forbidden again (U327, 19.1): "Disable plan mode" would
        cancel this pin, and cancelling a pin silently is what the operator ruled against;
      * `--no-memory` — cross-session memory would carry a prior conversation into this one without
        passing the scoped-context compiler (invariants 8/9);
      * `--no-subagents` / `--disable-web-search` — side channels that NARROW authority, which is
        why the guard has never refused them. No `--allow` rule: MCP attachment comes from the
        declared server, never from a pre-approval this build emits (U340);
      * `-m <slug>` only when a slug was selected. `None` ⇒ the CLI default, RECORDED as a fallback
        by the caller (directive §11 15B, never silent).

    Pure and deterministic: it builds argv. The ConPTY spawn, the I-X3 lease and the host-native
    OAuth credential all stay outside this function (the credential is never read/stored/sent)."""
    argv: list[str] = [executable]
    ws = str(workdir).strip() if workdir and str(workdir).strip() else None
    if ws:
        argv += [GROK_CWD_FLAG, ws]
    argv += [GROK_PERMISSION_MODE_FLAG, GROK_HEADLESS_PERMISSION_MODE,
             GROK_NO_MEMORY_FLAG, GROK_MINIMAL_FLAG, GROK_NO_ALT_SCREEN_FLAG,
             GROK_NO_SUBAGENTS_FLAG, GROK_DISABLE_WEB_SEARCH_FLAG]
    slug = model.strip() if model and model.strip() else None
    if slug:
        argv += [GROK_MODEL_FLAG, slug]
    # Both guards, on the whole argv — there is no prompt to append here, so the flags ARE the
    # command. Called explicitly rather than through the backend's `_guard` because this function is
    # not a backend method; the guards are the shared policy either way.
    C.assert_no_forbidden_provider_args(argv)
    C.assert_no_untrusted_instruction_args(argv)
    return argv


def MockGrokCliBackend(*, model: str | None = None) -> C.MockFrontierProviderBackend:  # noqa: N802
    """Deterministic stand-in, spawning nothing (build §2.4 substitution)."""
    return C.MockFrontierProviderBackend(GROK_ADAPTER, model=model)


mock_backend = MockGrokCliBackend


def probe_grok(*, runner: Any = None, executable: str | None = None) -> C.ProviderCliProbe:
    """Presence, version and the model inventory from `grok models` — the CLI's own listing and
    nothing else (operator directive §8). Spends no tokens and never raises.

    `grok models` doubles as this CLI's auth-reporting surface: it prints its own login line, which
    is the only auth evidence available without a live call. Silence there is UNVERIFIED, never
    AUTHENTICATED. An injected `runner` is how the deterministic suite drives this; with none, the
    caller must supply an executable it resolved itself — this function never spawns a discovery."""
    if runner is None:
        raise ValueError("probe_grok needs a runner: this module does not spawn a CLI implicitly")
    return C.probe_provider_cli(provider=GROK_ADAPTER, executable=executable, runner=runner,
                                min_version=MIN_GROK_VERSION, parse_models=C.parse_grok_models,
                                reports_auth=True)


def roster_descriptor(requested_model: str | None = None,
                      available: Sequence[str] | None = None) -> dict[str, Any]:
    """Roster/capability descriptor for a Grok node with the per-node model resolution SURFACED.

    `resolve_model_ref` decides the `-m` slug or the recorded CLI-default fallback; the decision
    AND its note are embedded in a `model_ref` block on the descriptor the roster/Inspector reads,
    so a fallback is a recorded field of the product surface rather than an assumption living in a
    helper's return value. A slug outside a known inventory is REFUSED (§8: never invented)."""
    import copy  # noqa: PLC0415

    slug, note = C.resolve_model_ref(requested_model, available)
    return {
        "adapter": GROK_ADAPTER,
        "display": GROK_DISPLAY,
        "node_class": GrokCliBackend.node_class,
        "locality": "frontier",
        "subscription_backed": True,
        "subscription_resource": GROK_SUBSCRIPTION,
        # deep copy so a caller mutating a nested `requirements` dict can never write back into
        # the module-level descriptor constants
        "capability_descriptors": copy.deepcopy(GROK_REASONING_CAPABILITY_DESCRIPTORS),
        "roles": list(GrokCliBackend.supported_roles),
        "model_ref": {
            "requested": requested_model,       # operator label as given (may be None)
            "resolved_slug": slug,              # None ⇒ CLI default (recorded fallback)
            "verified": bool(slug and available),
            "is_fallback": slug is None,
            "note": note,
        },
    }


def build_adapter(context: AdapterContext, mcp_client: Any, backend: Backend) -> ModelWorkerAdapter:
    """Configure the shared, already-governed `ModelWorkerAdapter` as a live `grok_build` frontier
    reasoning worker. `context` MUST come from the supervisor (`spawned_by_supervisor=True`) — the
    base contract refuses a naked launch (I-C1). Holds no credential (base default False)."""
    return ModelWorkerAdapter(
        context, mcp_client, backend,
        adapter_name=GROK_ADAPTER, node_class=GrokCliBackend.node_class, locality="frontier",
        offline_profile_eligible=False, requires_network=True,
        capability_descriptors=GROK_REASONING_CAPABILITY_DESCRIPTORS, subscription_backed=True)
