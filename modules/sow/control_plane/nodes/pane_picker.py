"""Per-pane model picker data model (OP-7 §12.2 — Phase 15E `.picker`).

OP-7 §12.2: *every pane gets a model selector offering both live provider adapters with their
probed model IDs (Anthropic: Opus 4.8 / Fable 5 / CLI default; OpenAI: the GPT-5.5 line incl.
Sol as probed), **and** the operator's entire local model list enumerated live from
`ollama list`. Selecting spawns a governed node through supervisor + governor (naked sessions
still refused). Local models route through the VRAM residency planner; the picker shows
residency state (resident / loading / awaiting-eviction).*

This module is the **pure, deterministic, fail-closed** data layer that produces that option
list. The rendered selector is an operator-run surface (Phase-1 substitution pattern); this is
the JSON it consumes, built here so the picker can never fabricate an option or hide an
unavailable one. Spawning is a LATER sub-step (`.spawn`); this only *offers* — every option
carries an `available` flag with a recorded reason so the picker greys-out (never hides) a
provider that live authorization does not cover.

Honesty rules enforced here:
  * a frontier provider is `available` ONLY if `LiveAuthorization` covers it (fail-closed to
    unavailable-with-reason otherwise — never hidden, per invariant 20 air-gap honesty spirit);
  * the Codex option also requires the CLI to be present AND authenticated on the host (the
    caller passes those facts from a real `probe_codex`) — each missing condition is named;
  * frontier model slugs are never fabricated. For the OP-6 pair they are UNVERIFIED operator
    labels until a live smoke (`verified` carried straight from the roster descriptor). For the
    OP-12 pair the slug IS the CLI's own `models` listing, so it ships `verified=True` on a
    stronger basis than an operator label — the CLI said it (see `_op12_options` and U272). Two
    different bases, one rule: the flag reports where the slug came from and is never upgraded
    downstream (`worker_pane_spawn` carries it verbatim);
  * local Ollama models need no credential (§2.4) so they are always offered when enumerated,
    each annotated with its live residency state from the ResidencyPlanner; an empty
    enumeration yields zero local options RECORDED (never a fabricated model).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters.frontier.claude_code import (
    CLAUDE_CANDIDATE_MODEL_REFS,
    CLAUDE_CODE_ADAPTER,
    resolve_claude_model_ref,
)
from adapters.frontier.antigravity import (
    ANTIGRAVITY_ADAPTER,
    ANTIGRAVITY_DISPLAY,
    AntigravityCliBackend,
)
from adapters.frontier.codex import (
    CODEX_ADAPTER,
    CODEX_CANDIDATE_MODEL_REFS,
    resolve_codex_model_ref,
)
from adapters.frontier.grok_build import GROK_ADAPTER, GROK_DISPLAY, GrokCliBackend
from control_plane.profiles.live_authorization import LiveAuthorization
from scheduler.residency_planner.residency_planner import NOT_LOADED, UNKNOWN

# Frontier provider identities. For these two the id IS the frozen node.schema.json adapter enum
# member. The picker's vocabulary as a whole is still a PRODUCT-layer namespace, but it is no
# longer WIDER than the canonical one: OP-12.1 (2026-08-01) resolved U227 by successor schema, so
# `node@1.1` admits `ollama_local` (U254) and both OP-12 providers, and every id this picker emits
# is now an enum member of some node schema version. Saying so here rather than repeating a
# "single source of truth" line the next declaration contradicts — the versions differ, and
# `control_plane/nodes/registry.adapter_version_map()` is where which-version-admits-what lives.
_ANTHROPIC = CLAUDE_CODE_ADAPTER      # "claude_code"
_OPENAI = CODEX_ADAPTER               # "openai_codex_cli"

# Role eligibility the picker offers per provider (honest, coarse; the Scheduler still resolves
# by capability descriptor at spawn — this is only what the selector lists). These are ADAPTER
# capability facts, not name inference: claude_code is the conductor-capable adapter (D-COND-01);
# both frontier CLIs do reasoning + coding. Local models advertise the coarse worker-role menu
# uniformly — a local model's actual fit for a role is resolved by its capability descriptor at
# `.spawn` (I-SC1: capability from a descriptor, NEVER inferred from the model's name).
_ANTHROPIC_ROLES = ("conductor", "reasoning", "coding")
_OPENAI_ROLES = ("reasoning", "coding")
_LOCAL_ROLES = ("reasoning", "coding")
# The OP-12 providers offer REASONING ONLY, and that is a decision with a warrant rather than an
# omission (U260, taken at `.adapter` and honoured here so the selector cannot offer a role the
# adapter refuses to construct): a coding role needs either an auto-approving permission mode
# (operator directive §11 forbids emitting one) or a sandbox profile neither CLI documents.
# Each backend's own `supported_roles` is the authority — read PER PROVIDER, not re-spelled and not
# read from one of them for both, so the picker cannot offer a role the adapter would refuse to
# construct (and so a later divergence between the two backends surfaces here instead of at spawn).
_OP12_ROLES: dict[str, tuple[str, ...]] = {
    GROK_ADAPTER: tuple(GrokCliBackend.supported_roles),
    ANTIGRAVITY_ADAPTER: tuple(AntigravityCliBackend.supported_roles),
}
# The CLI command each OP-12 provider is invoked as, read from the backend's own candidate list
# (its FIRST entry is the plain command name; the rest are Windows shim spellings). Used only for
# operator-facing text, and taken from the adapter so a message can never name a command this build
# would not actually run.
_OP12_COMMAND: dict[str, str] = {
    GROK_ADAPTER: GrokCliBackend.executable_candidates[0],
    ANTIGRAVITY_ADAPTER: AntigravityCliBackend.executable_candidates[0],
}

# The id prefix each provider's OWN model line uses. Not a filter and not a judgement: an id that
# does not start with it is still offered under this provider (the CLI listed it, and §8 says the
# listing IS the option set) — it only gains a note saying which subscription pays for it. `agy
# models` on this host offers `claude-sonnet-4-6`, `claude-opus-4-6-thinking` and `gpt-oss-120b-medium`
# beside the `gemini-*` line, which is the U246 fact this discloses.
_OP12_NATIVE_MODEL_PREFIX: dict[str, str] = {
    GROK_ADAPTER: "grok",
    ANTIGRAVITY_ADAPTER: "gemini",
}

# The local provider id this picker emits. Still NOT a node@1.0 `adapter` enum member — the frozen
# enum spells the local adapter `ollama_direct` and is untouched — but no longer un-admitted:
# recorded as U254, and admitted into `node@1.1` by the same operator ruling that admitted the two
# OP-12 providers (OP-12.1). The two spellings still coexist, which is why U254 is closed as
# ADMITTED rather than as fixed; a rename remains the tidier end state and is not this unit's call.
_LOCAL_PROVIDER = "ollama_local"


# THE picker's provider table: (provider id, display, locality). One declaration, from which the
# rendered group list AND both registration accessors are derived. Two hand-maintained enumerations
# would let the next sub-step add a provider to one and not the other — and the failure mode that
# hides is the bad one: a live, money-spending frontier terminal with no n/allowance counter in the
# status bar (invariant 27). Adding a provider here is the ONE edit that wires it everywhere.
_PROVIDER_TABLE: tuple[tuple[str, str, str], ...] = (
    (_ANTHROPIC, "Anthropic (claude CLI)", "frontier"),
    (_OPENAI, "OpenAI (codex CLI)", "frontier"),
    # OP-12. The display strings are the operator directive's §14 SELECTABLE LABELS verbatim, taken
    # from the adapter modules that publish them rather than re-typed here — §14 also forbids showing
    # "Gemini CLI" for this path, and a second spelling is how that creeps back in.
    (GROK_ADAPTER, GROK_DISPLAY, "frontier"),
    (ANTIGRAVITY_ADAPTER, ANTIGRAVITY_DISPLAY, "frontier"),
    (_LOCAL_PROVIDER, "Local (Ollama)", "local"),
)


def registered_providers() -> frozenset[str]:
    """The provider ids this picker can actually OFFER today — the application's product-layer
    registration surface, published so a diagnostic does not have to infer it (U230 closed the
    equivalent private read against `live_authorization`).

    This is a REGISTRATION fact, not an availability one: a provider listed here may still be
    greyed out with a reason (no live authorization, CLI absent, not signed in). A provider ABSENT
    here cannot be selected at all.

    **U256, closed here.** `.scope` re-based the recon engine's registration verdict onto this
    accessor and recorded that the replacement was weaker evidence: adding an id to the table made
    the diagnostic answer REGISTERED whether or not anything could be spawned. It is now the
    INTERSECTION of what the picker renders and what the pane authorizer will actually dispatch
    (`worker_pane_spawn.FRONTIER_PANE_ADAPTERS` + the local adapter), so "registered" means a
    selection can reach a governed launch path rather than merely appear in a list. The local id is
    named from the authorizer's own constant for the same reason. An id in the table but not in the
    dispatch set is silently unspawnable, and this is the accessor that would have called it
    registered."""
    from node_runtime.supervisor.worker_pane_spawn import (  # noqa: PLC0415 — import cycle
        FRONTIER_PANE_ADAPTERS,
        OLLAMA_LOCAL_ADAPTER,
    )

    dispatchable = frozenset(FRONTIER_PANE_ADAPTERS) | {OLLAMA_LOCAL_ADAPTER}
    return frozenset(p for p, _display, _locality in _PROVIDER_TABLE) & dispatchable


def registered_frontier_providers() -> frozenset[str]:
    """The subscription-backed subset of `registered_providers()` — i.e. exactly the providers the
    shell can hold an I-X3 terminal for, and therefore the set whose n/allowance counters the
    status bar renders. Distinct from `live_authorization.authorized_providers()`, which answers
    the broader "some operator ruling covers this id": after OP-12 those two sets differ, and the
    status bar must mirror the narrower one or it would advertise a counter for a provider no pane
    can select. Derived from `registered_providers()` so the U256 spawnability intersection applies
    here too — this is the set the shell renders n/allowance counters for, and a counter for an
    unspawnable provider is precisely the advertisement this accessor exists to prevent."""
    registered = registered_providers()
    return frozenset(p for p, _display, locality in _PROVIDER_TABLE
                     if locality == "frontier" and p in registered)


def _frontier_option(*, provider: str, label: str, resolved_slug: str | None, verified: bool,
                     is_fallback: bool, roles: tuple[str, ...], available: bool,
                     unavailable_reason: str | None, note: str, registered: bool = True,
                     conductor_capable: bool = False,
                     authentication_status: str = "unknown") -> dict[str, Any]:
    return {
        "provider": provider,
        "adapter": provider,
        "locality": "frontier",
        "subscription_backed": True,
        "label": label,
        "model_slug": resolved_slug,        # None ⇒ CLI default (recorded fallback)
        "verified": verified,               # operator label unverified until a live smoke
        "registered": registered,
        "conductor_capable": conductor_capable,
        "authentication_status": authentication_status,
        "is_fallback": is_fallback,
        "roles": list(roles),
        "residency": None,                  # frontier models are not VRAM-resident locally
        "available": available,
        "unavailable_reason": None if available else unavailable_reason,
        "note": note,
    }


def _anthropic_options(live: LiveAuthorization, *, claude_available: bool) -> list[dict[str, Any]]:
    # Symmetric with the codex path: authorization is necessary but not sufficient — the host
    # `claude` CLI must also be present. (Unlike codex, the claude CLI exposes no cheap
    # non-interactive auth-status probe, so CLI-auth is confirmed only by the live smoke; the
    # option carries `verified=False` and the note states this — never a fabricated auth claim.)
    missing: list[str] = []
    if not live.is_provider_live(_ANTHROPIC):
        missing.append(f"live operation not authorized for {_ANTHROPIC!r}: {live.reason}")
    if not claude_available:
        missing.append("`claude` CLI not detected on host")
    provider_live = not missing
    reason = None if provider_live else "; ".join(missing)
    options: list[dict[str, Any]] = []
    for cand in CLAUDE_CANDIDATE_MODEL_REFS:
        slug, note = resolve_claude_model_ref(cand.provisional_slug)
        options.append(_frontier_option(
            provider=_ANTHROPIC, label=cand.operator_name, resolved_slug=slug,
            verified=cand.verified, is_fallback=slug is None, roles=_ANTHROPIC_ROLES,
            available=provider_live, unavailable_reason=reason, note=note,
            registered=cand.registered, conductor_capable=cand.conductor_capable,
            authentication_status="unverified" if provider_live else "unavailable"))
    # The CLI-default option (no --model): an explicit, recorded fallback (directive §11 15B).
    default_slug, default_note = resolve_claude_model_ref(None)
    options.append(_frontier_option(
        provider=_ANTHROPIC, label="CLI default", resolved_slug=default_slug, verified=False,
        is_fallback=True, roles=("reasoning", "coding"), available=provider_live,
        unavailable_reason=reason, note=default_note))
    return options


def _openai_options(live: LiveAuthorization, *, codex_available: bool,
                    codex_authenticated: bool) -> list[dict[str, Any]]:
    provider_live = live.is_provider_live(_OPENAI)
    # Fail closed AND specific: name every unmet condition so the picker's tooltip is truthful.
    missing: list[str] = []
    if not provider_live:
        missing.append(f"live operation not authorized for {_OPENAI!r}: {live.reason}")
    if not codex_available:
        missing.append("`codex` CLI not detected on host (install: npm install -g @openai/codex)")
    if not codex_authenticated:
        missing.append("`codex` CLI not authenticated on host (run: codex login)")
    available = not missing
    reason = None if available else "; ".join(missing)
    options: list[dict[str, Any]] = []
    for cand in CODEX_CANDIDATE_MODEL_REFS:
        slug, note = resolve_codex_model_ref(cand.provisional_slug)
        options.append(_frontier_option(
            provider=_OPENAI, label=cand.operator_name, resolved_slug=slug,
            verified=cand.verified, is_fallback=slug is None,
            roles=(("conductor",) + _OPENAI_ROLES if cand.conductor_capable else _OPENAI_ROLES),
            available=available, unavailable_reason=reason, note=note,
            registered=cand.registered, conductor_capable=cand.conductor_capable,
            authentication_status="authenticated" if codex_authenticated else "unauthenticated"))
    default_slug, default_note = resolve_codex_model_ref(None)
    options.append(_frontier_option(
        provider=_OPENAI, label="CLI default", resolved_slug=default_slug, verified=False,
        is_fallback=True, roles=_OPENAI_ROLES, available=available,
        unavailable_reason=reason, note=default_note))
    return options


@dataclass(frozen=True)
class ProviderCliInventory:
    """What a live host probe established about ONE OP-12 provider CLI, and nothing more.

    The picker will not guess any of these. It is built by the host enumerator from a real
    `probe_grok` / `probe_antigravity` (`tools/live/enumerate_pane_picker`); the deterministic suite
    constructs it directly. Absent ⇒ the provider is offered with ZERO options and the honest reason
    "not enumerated on this host", never a fabricated model (operator directive §8).

    `present`       — the CLI resolved on PATH. Presence is NEVER an auth claim (§6).
    `authenticated` — `True`/`False` only where the CLI has an offline auth surface that SAID so;
                      `None` where it has none. `agy` has none at all, so `None` is its permanent
                      honest answer and must not read as "signed in" or as "login required".
    `models`        — the CLI's OWN listing (`grok models` / `agy models`), verbatim and in order.
    `blocked_reason`— any OTHER condition the probe established that makes the provider
                      unselectable (unsupported version, an unparseable or timed-out metadata call).
                      Kept separate from `present` because "the CLI is not here" and "the CLI is
                      here and did not answer" are different facts and lead the operator to
                      different actions; collapsing them would print an install command to someone
                      whose CLI is installed.
    `note`          — provenance carried onto every option built from this inventory.
    """

    present: bool = False
    authenticated: bool | None = None
    models: tuple[str, ...] = ()
    blocked_reason: str | None = None
    note: str = ""


#: Per-provider install hint for the greyed-out reason (operator directive §4 / §14: the failure
#: text must identify the ACTUAL provider — never one provider's message under another's label).
_OP12_INSTALL_HINT: dict[str, str] = {
    GROK_ADAPTER: "install: npm install -g @xai-official/grok",
    ANTIGRAVITY_ADAPTER: "install: irm https://antigravity.google/cli/install.ps1 | iex",
}
#: Per-provider sign-in hint, used ONLY where a provider's own offline surface reported "not signed
#: in". `agy` has no such surface, so it can never reach this text.
_OP12_LOGIN_HINT: dict[str, str] = {
    GROK_ADAPTER: "sign in: grok login",
    ANTIGRAVITY_ADAPTER: "sign in: run `agy` once and complete the Google sign-in",
}


def _op12_options(provider: str, live: LiveAuthorization, inventory: ProviderCliInventory | None
                  ) -> tuple[list[dict[str, Any]], str | None]:
    """Options for one OP-12 provider — one per model the CLI ITSELF enumerated, never more —
    together with the group-level reason (None when the provider is fully available).

    Three differences from the claude/codex builders above, each forced by what these CLIs are:

    1. **There is no candidate-label list and no "CLI default" option.** `claude`/`codex` publish no
       offline model list, so the picker offers operator LABELS resolved at launch. These two DO
       publish one (`grok models`, `agy models`), so the option set IS that listing — an id this
       build never composed. A provider with an empty listing therefore yields ZERO options: the
       directive says model identifiers are never invented, and "CLI default" for a provider whose
       real default we could not read would be exactly that invention.
    2. **`verified=True`.** In this codebase the flag means "the CLI confirmed it accepts this id",
       which is precisely what an entry in the CLI's own listing is (the same basis on which
       `roster_descriptor` sets it, and on which a local Ollama tag is verified). It does NOT mean a
       live session has answered — nothing offline can establish that, and the note says so.
    3. **Authentication is per-provider and asymmetric**, because the hosts' surfaces are: `grok
       models` prints its own login line, so `authenticated=False` is a real refusal condition;
       `agy` prints nothing about auth ever, so `None` blocks nothing and is disclosed in the note
       instead. Blocking on it would make the provider permanently unselectable on a signed-in host;
       claiming it is fine would be an auth claim nothing observed (§6).
    """
    missing: list[str] = []
    if not live.is_provider_live(provider):
        missing.append(f"live operation not authorized for {provider!r}: {live.reason}")
    inv = inventory or ProviderCliInventory()
    if not inv.present:
        missing.append(f"`{_OP12_COMMAND[provider]}` CLI not detected on host "
                       f"({_OP12_INSTALL_HINT[provider]})")
    if inv.authenticated is False:
        missing.append(f"`{_OP12_COMMAND[provider]}` CLI reports no signed-in session "
                       f"({_OP12_LOGIN_HINT[provider]})")
    if inv.present and inv.blocked_reason:
        # Only meaningful when the CLI IS present: an absent CLI has already said the useful thing,
        # and appending "its metadata call did not answer" to that would describe a call nothing made.
        missing.append(inv.blocked_reason)
    available = not missing
    reason = None if available else "; ".join(missing)

    note_bits = [f"model id enumerated live from `{_OP12_COMMAND[provider]} models` — the CLI's own "
                 f"listing; accepted-id verified, a live REPLY is still unproven"]
    if inv.authenticated is None:
        note_bits.append("this CLI has no offline auth surface: whether the operator is signed in "
                         "is UNVERIFIED here and only a live call can answer it")
    if inv.note:
        note_bits.append(inv.note)
    # Not joined here: the U246 disclosure below is per-OPTION, so each option composes its own note
    # from these shared bits plus, where it applies, the sentence saying which subscription pays.

    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    for slug in inv.models:
        if not isinstance(slug, str) or not slug.strip() or slug in seen:
            continue
        seen.add(slug)
        # U246, decided at `.picker` review round 1: this subscription's listing contains models
        # served by OTHER vendors (`agy models` offers claude-* and gpt-* beside the gemini-* line).
        # The id stays exactly as the CLI published it — renaming it to conceal who serves it would
        # be §14's defect pointing the other way — and the note DISCLOSES the accounting instead,
        # because "a claude model under the Gemini label" is otherwise an operator reading a
        # subscription wrong. Never a claim about who trained it: only which subscription pays.
        bits = list(note_bits)
        if not slug.startswith(_OP12_NATIVE_MODEL_PREFIX[provider]):
            bits.append(f"served THROUGH the {_OP12_COMMAND[provider]} subscription and counted "
                        f"against it, though the id is not this provider's own model line (U246)")
        options.append(_frontier_option(
            provider=provider, label=slug, resolved_slug=slug, verified=True, is_fallback=False,
            roles=_OP12_ROLES[provider], available=available, unavailable_reason=reason,
            note="; ".join(bits)))
    if reason is None and not options:
        # Every gate said yes and the CLI still listed nothing. Not an availability refusal and not
        # a fabricated option: an empty inventory from a present, authorized, signed-in CLI is its
        # own fact, and saying so is the only honest thing left (operator directive §8).
        reason = (f"`{_OP12_COMMAND[provider]} models` enumerated no models on this host — nothing "
                  f"to offer; no model id is ever invented (operator directive §8)")
    return options, reason


def _group_status(options: list[dict[str, Any]], group_reason: str | None) -> dict[str, Any]:
    """The provider GROUP's own availability line — what the selector shows next to a provider's
    title, and the ONLY place a reason can live when a provider has zero options.

    `group_reason` is supplied by builders whose option list can legitimately be empty (the OP-12
    pair, whose options come from a live enumeration). For the others it is derived from the options
    themselves, so one rule renders every group: a group is available iff at least one of its
    options is, and an unavailable group reports the first recorded reason rather than a generic
    one. Derived — never a second hand-maintained availability judgement that could disagree with
    the options directly beneath it."""
    available = any(o.get("available") for o in options)
    reason: str | None = None
    if not available:
        reason = group_reason or next(
            (o.get("unavailable_reason") for o in options if o.get("unavailable_reason")), None)
        if reason is None:
            reason = "no options enumerated for this provider"
    return {"available": available, "reason": reason, "option_count": len(options)}


def _local_group_reason(ollama_models: list[str],
                        local_unavailable_reason: str | None) -> str | None:
    """The LOCAL group's own availability line.

    N-25/F-5. `_group_status` falls back to "no options enumerated for this provider" when a
    group has neither options nor a reason, and the local group was passed no reason at all — so
    with Ollama down the operator was told, about the one provider that costs nothing to run,
    only that nothing was enumerated. That names neither Ollama nor anything the operator could
    act on. It is the N-22 lesson in a second place: an absent thing must say what is absent.

    `local_admission_reason` already computes the actionable text (daemon unreachable, runtime not
    on PATH, no VRAM budget) and it was reaching the individual options but not the group heading
    that is the only thing visible when there are zero options.
    """
    if local_unavailable_reason:
        return local_unavailable_reason
    if not ollama_models:
        # Admission is fine and the daemon answered: it simply has nothing pulled. Distinct from
        # a daemon that is not running, and the distinction is the whole point.
        return ("the local ollama runtime is available but `ollama list` returned no models - "
                "pull a model to offer it here")
    return None


def _local_options(ollama_models: list[str], residency: dict[str, str] | None,
                   unavailable_reason: str | None = None) -> list[dict[str, Any]]:
    """One option per live-enumerated Ollama model, annotated with its residency state. Local
    models carry no credential (§2.4) so they are always OFFERED; an empty enumeration yields an
    empty list (recorded as count 0 — never a fabricated model).

    `unavailable_reason` greys them out. Local availability is not a credential question (there is
    no credential), but 17B promoted the residency planner from a display chip into an
    AUTHORIZATION gate: when this host's VRAM budget cannot be established, `worker_pane_spawn`
    refuses every local pane, and rendering all of them `available:true` shows the operator
    something the gate will not honour (spec-audit MAJOR-2, 2026-07-26). Greyed-with-reason is
    this module's own stated contract — it was simply never extended to the condition 17B
    introduced."""
    options: list[dict[str, Any]] = []
    # Deterministic order, de-duplicated while preserving first-seen — the enumeration is the
    # operator's real `ollama list`, but a duplicate name must not double an option.
    seen: set[str] = set()
    for name in ollama_models:
        if not isinstance(name, str) or not name.strip() or name in seen:
            continue
        seen.add(name)
        options.append({
            "provider": _LOCAL_PROVIDER,
            "adapter": _LOCAL_PROVIDER,
            "locality": "local",
            "subscription_backed": False,
            "label": name,
            "model_slug": name,             # local model tag is the real, verified id
            "verified": True,
            "is_fallback": False,
            # coarse worker-role menu, uniform for every local model — the model's real fit for a
            # role is resolved by its capability descriptor at `.spawn`, NEVER inferred from its
            # name (I-SC1; spec-audit MINOR-1).
            "roles": list(_LOCAL_ROLES),
            # `residency is None` means there is NO residency view (no planner was built): every
            # model reads UNKNOWN. Only when a planner DID report is an absent name honestly
            # not_loaded — the planner enumerates everything it knows, so absent means absent from
            # VRAM. Collapsing the two states told the operator that a model the daemon is
            # actively serving was not loaded (gate-validator FAIL-1).
            "residency": UNKNOWN if residency is None else residency.get(name, NOT_LOADED),
            # No CREDENTIAL gate for a detected local model — but the VRAM admission gate can still
            # cover none of them (see the docstring). Fail closed to greyed-with-reason.
            "available": unavailable_reason is None,
            "unavailable_reason": unavailable_reason,
            "note": "local model enumerated live from the Ollama daemon (§2.4, no credential)",
        })
    return sorted(options, key=lambda o: o["label"])


def build_pane_picker(
    live: LiveAuthorization,
    *,
    ollama_models: list[str] | None = None,
    residency: dict[str, str] | None = None,
    claude_available: bool = False,
    codex_available: bool = False,
    codex_authenticated: bool = False,
    local_unavailable_reason: str | None = None,
    grok: ProviderCliInventory | None = None,
    antigravity: ProviderCliInventory | None = None,
) -> dict[str, Any]:
    """Assemble the per-pane model-picker option set (OP-7 §12.2), provider-neutral and
    fail-closed.

    `live`               — resolved LiveAuthorization (frontier availability gate).
    `ollama_models`      — the operator's live `ollama list` result (host-enumerated by the
                           driver; None/[] ⇒ no local options, recorded honestly).
    `residency`          — ResidencyPlanner.residency_map(): local model → residency state.
                           `None` means there is NO residency view (the daemon is unreachable, or
                           the VRAM budget could not be established so no planner exists) and every
                           local model renders UNKNOWN — never NOT_LOADED, which would assert a
                           fact about a model the daemon may be serving right now.
    `claude_available`   — real `detect.claude_code_available()`: is the `claude` CLI on PATH?
    `codex_available`    — real `probe_codex` result: is the `codex` CLI on PATH?
    `codex_authenticated`— real `probe_codex` result: is it logged in?
    `local_unavailable_reason` — when the VRAM budget this host's local admission gate needs could
                           not be established, every local option is greyed with THIS reason (the
                           authorization would refuse it — spec-audit MAJOR-2). None ⇒ offered.
    `grok` / `antigravity` — the OP-12 provider inventories from a real host probe
                           (`ProviderCliInventory`). None ⇒ that provider is offered with ZERO
                           options and the reason says the CLI was not detected — never a
                           fabricated model, and never a silently absent provider.

    Returns a dict with `providers` (grouped) and a flat `options` list (the UI can render
    either), plus `authorization` provenance and honest counts. Nothing is hidden: an
    unavailable provider's options appear with `available=False` and a specific reason — and a
    provider with NO options at all carries that reason on its GROUP (`status`), which is the only
    place it can live for the OP-12 pair: their option sets come from a live enumeration, so an
    absent or signed-out CLI legitimately produces an empty list, and an empty list with no reason
    would render as a silent gap exactly where the honesty matters most.
    """
    ollama_models = ollama_models or []
    # NOT `residency or {}`: `None` (no residency view) and `{}` (a planner that reports nothing
    # resident) are different facts and must render differently.

    anthropic = _anthropic_options(live, claude_available=claude_available)
    openai = _openai_options(live, codex_available=codex_available,
                             codex_authenticated=codex_authenticated)
    grok_options, grok_reason = _op12_options(GROK_ADAPTER, live, grok)
    antigravity_options, antigravity_reason = _op12_options(ANTIGRAVITY_ADAPTER, live, antigravity)
    local = _local_options(ollama_models, residency, local_unavailable_reason)

    # Groups come from the ONE provider table, so `registered_providers()` cannot claim a provider
    # this list does not render (or vice versa).
    by_provider = {_ANTHROPIC: anthropic, _OPENAI: openai, GROK_ADAPTER: grok_options,
                   ANTIGRAVITY_ADAPTER: antigravity_options, _LOCAL_PROVIDER: local}
    reasons = {GROK_ADAPTER: grok_reason, ANTIGRAVITY_ADAPTER: antigravity_reason,
               _LOCAL_PROVIDER: _local_group_reason(ollama_models, local_unavailable_reason)}
    providers = [{"provider": p, "display": display, "options": by_provider[p],
                  "status": _group_status(by_provider[p], reasons.get(p))}
                 for p, display, _locality in _PROVIDER_TABLE]
    flat = anthropic + openai + grok_options + antigravity_options + local
    # Locality comes from the ONE provider table, so a provider added there is counted correctly
    # without a second edit here. The previous form named the two frontier lists literally, which
    # would have left `counts.frontier` reporting a number that excluded the two providers this
    # sub-step added while `counts.total` included them — the status bar's own class of defect
    # (U255/U258) reproduced in the picker's counters.
    _locality_of = {p: locality for p, _display, locality in _PROVIDER_TABLE}
    return {
        "providers": providers,
        "options": flat,
        "authorization": live.as_dict(),
        "counts": {
            "total": len(flat),
            "available": sum(1 for o in flat if o["available"]),
            "frontier": sum(1 for o in flat if _locality_of.get(o["provider"]) == "frontier"),
            "local": sum(1 for o in flat if _locality_of.get(o["provider"]) == "local"),
        },
    }
