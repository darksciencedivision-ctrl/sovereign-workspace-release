"""Registered, provider-neutral conductor model descriptors.

The conductor is a role.  Provider differences stop at the command-adapter boundary; the
desktop lifecycle consumes the same :class:`ConductorDescriptor` for every provider.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.codex import CODEX_ADAPTER
from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER
from adapters.local.llamacpp import LLAMACPP_LOCAL_ADAPTER
from control_plane.local_only import LOCAL_ONLY_MODE, LOCAL_ONLY_REASON, frontier_disabled
from node_runtime.supervisor.subscription_governor import canonical_subscription_ref

CONDUCTOR_PERMISSION_PROFILE = "pp-conductor-pane"
DEFAULT_WORKSPACE = str(Path(__file__).resolve().parents[2])
_LIVE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "live_operation.json"

#: Where a LOCAL conductor selection is remembered. The gitignored runtime lane, NOT
#: `live_operation.json`: a local model authorizes no spend, and that file stays absent under
#: OD-31 (S-18). This is the N-16 remedy applied to a new piece of host state - the operator's
#: choice is remembered across restarts without ever entering the release candidate.
LOCAL_CONDUCTOR_SELECTION_PATH = (
    Path(__file__).resolve().parents[2] / ".runtime" / "conductor-selection.json")


def _within_install(candidate: str, root: str) -> bool:
    """Is `candidate` the install root or a path inside it?

    Compared as canonical path COMPONENTS, never as a string prefix. SW-ORCH-001 §3.1a records
    why on this operator's disk: `D:\\producttion` is a character-prefix of
    `D:\\producttion software 2`, so a `startswith` test places an entire product tree "inside" an
    unrelated Crashpad dump directory. `Path.parts` cannot make that mistake — a component either
    equals the next one or it does not.

    `resolve()` is what handles junctions and reparse points: both sides are canonicalised before
    the comparison, so a stored path that reaches the root through a junction is admitted and one
    that escapes through it is not. A path that cannot be resolved is NOT contained (fail closed) —
    an unreadable location is not evidence of containment.
    """
    try:
        cand = Path(candidate).resolve()
        base = Path(root).resolve()
    except (OSError, ValueError):
        return False
    return cand == base or base.parts == cand.parts[:len(base.parts)]


def _admissible_workspace(raw_workspace: Any, *, install_root: str) -> tuple[str, str | None]:
    """The workspace a descriptor may actually use, and the refusal if a stored one was rejected.

    F-13/U78(a) established that a conductor session inheriting whatever directory the shell
    happened to start in is bound to nothing. SW-ORCH-001 F-22 is the other half of that: a
    workspace read back from HOST-LOCAL STATE was trusted verbatim, so a selection file copied
    between installs silently rebound the conductor's ConPTY into a tree the running install does
    not own. Measured 2026-09-05 — one session had its workers in `production software 3` and its
    conductor in `producttion software 2`, from one stale absolute literal in
    `.runtime/conductor-selection.json`.

    The stored value is therefore ADVISORY. It is honoured when it names this install, and refused
    — not substituted across installs — when it does not. The install root wins, because the
    workspace is a property of the install that reads the file, not of the file.

    Returns `(workspace, refusal)`. `refusal` is None when nothing was rejected; otherwise it names
    BOTH paths, because an operator told only "refused" cannot tell which install they are in.
    """
    stored = str(raw_workspace or "").strip()
    if not stored:
        return install_root, None
    if _within_install(stored, install_root):
        return stored, None
    # Quoted, NOT `!r`. A Windows path through `repr()` comes back with every separator doubled
    # (`D:\\producttion software 2\\...`), and this string is read by an operator deciding which
    # install they are looking at. The one place a path must be legible is the message that names
    # two of them.
    return install_root, (
        f'the stored conductor workspace "{stored}" is not inside this install '
        f'("{install_root}"), so it was refused and this install\'s own root is used instead. '
        f"A workspace is a property of the install that reads the selection, not of the "
        f"selection file (SW-ORCH-001 F-22)")


def _load_local_conductor_selection() -> dict[str, Any] | None:
    """The operator's stored LOCAL conductor choice, or None. Never raises: a corrupt or
    half-written preference must degrade to "no local preference" rather than take the shell's
    conductor resolution down with it (fail closed, invariant 3)."""
    try:
        raw = json.loads(LOCAL_CONDUCTOR_SELECTION_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    pref = raw.get('conductor') if isinstance(raw, dict) else None
    return pref if isinstance(pref, Mapping) else None


class ConductorRegistryError(ValueError):
    """A requested conductor/provider/model combination is not registered."""


@dataclass(frozen=True)
class ConductorModelRegistration:
    provider_id: str
    adapter_id: str
    model_id: str
    display_name: str
    conductor_capable: bool
    worker_capable: bool
    readiness_turns: int = 1
    locality: str = "frontier"

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "adapter_id": self.adapter_id,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "registered": True,
            "conductor_capable": self.conductor_capable,
            "worker_capable": self.worker_capable,
            "readiness_turns": self.readiness_turns,
            "locality": self.locality,
        }


@dataclass(frozen=True)
class ConductorDescriptor:
    role: str
    provider_id: str
    adapter_id: str
    model_id: str
    display_name: str
    permission_profile_id: str
    workspace: str
    subscription_ref: str
    readiness_turns: int = 1
    locality: str = "frontier"
    registered: bool = True
    conductor_capable: bool = True
    #: Where this selection came from (U331, unit 19.6).  ``live_operation_preference`` = the
    #: operator's host switch named it; ``recorded_default_selection`` = the switch was absent or
    #: silent and the registry resolved the RECORDED selection (D-COND-03, fable-5) — which is a
    #: recorded operator choice, not a vendor default (invariant 3); ``unstated`` = resolved
    #: directly, by a caller that knows something this field does not.  It is reported, never
    #: enforced: no code path may refuse a conductor because of what is written here.
    selection_source: str = "unstated"
    #: SW-ORCH-001 F-22.  Set when a workspace stored in host-local state named a path outside this
    #: install and was refused in favour of the install's own root; None when nothing was rejected.
    #: It names BOTH paths.  Like ``selection_source`` it is REPORTED, never enforced — the refusal
    #: has already been applied to ``workspace`` by the time this is read, and no code path may
    #: refuse a conductor because this field is set.  It exists so the operator surface can say
    #: which stored path was ignored instead of silently running somewhere else.
    workspace_refusal: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# Exact provider identifiers and model slugs already represented by the provider adapters.  The
# OpenAI registration is the host-supported slug authorized by the operator amendment.  Claude's
# existing entries remain registered and selectable whenever that provider is actually available.
CONDUCTOR_MODEL_REGISTRY: tuple[ConductorModelRegistration, ...] = (
    ConductorModelRegistration(
        provider_id=CODEX_ADAPTER,
        adapter_id=CODEX_ADAPTER,
        model_id="gpt-5.6-sol",
        display_name="ChatGPT 5.6 Sol",
        conductor_capable=True,
        worker_capable=True,
    ),
    ConductorModelRegistration(
        provider_id=CLAUDE_CODE_ADAPTER,
        adapter_id=CLAUDE_CODE_ADAPTER,
        model_id="fable-5",
        display_name="Claude Fable 5",
        conductor_capable=True,
        worker_capable=True,
    ),
    ConductorModelRegistration(
        provider_id=CLAUDE_CODE_ADAPTER,
        adapter_id=CLAUDE_CODE_ADAPTER,
        model_id="opus-4.8",
        display_name="Claude Opus 4.8",
        conductor_capable=True,
        worker_capable=True,
    ),
)


#: Local conductor seats are enumerated from the HOST, not written down here. A frontier model is a
#: fixed product fact — `fable-5` exists whether or not this machine can reach it — but which local
#: models exist is a property of the operator's disk, so a static tuple would either fabricate models
#: he has not got or hide ones he has. The registry therefore CARRIES the frontier rows and DERIVES
#: the local ones, through the same `adapters.local.model_ceiling` verdicts the picker uses (S-20:
#: "every local model within the ceiling" must mean the same set in every surface).
LOCAL_CONDUCTOR_ROLES_NOTE = (
    "local conductor seat enumerated live from the Ollama daemon and admitted by the operator's "
    "8B ceiling (ENTRY 017); it holds no subscription and no credential")


def _local_conductor_registrations(
    verdicts: Iterable[Any] | None = None,
) -> tuple[ConductorModelRegistration, ...]:
    """One conductor-capable registration per ADMITTED local model.

    `verdicts` is injected by callers that already classified the host (the picker path, the tests);
    `None` means enumerate now. Enumeration never raises and yields an empty tuple when the daemon is
    unreachable — an absent daemon means no local conductor seats, which is a fact to report, not an
    error to throw at a selector.
    """
    if verdicts is None:
        from adapters import detect  # noqa: PLC0415  (host detection stays out of the import graph)
        from adapters.local.model_ceiling import classify_local_models  # noqa: PLC0415
        try:
            verdicts = classify_local_models(detect.ollama_model_records())
        except Exception:
            verdicts = ()
    ollama_rows = tuple(
        ConductorModelRegistration(
            provider_id=OLLAMA_LOCAL_ADAPTER,
            adapter_id=OLLAMA_LOCAL_ADAPTER,
            model_id=v.name,
            display_name=v.name,          # the operator's own `ollama list` tag, never a prettified one
            conductor_capable=True,
            worker_capable=True,
            locality="local",
        )
        for v in verdicts if getattr(v, "admitted", False)
    )
    # llama.cpp exposes ids through its local OpenAI-compatible endpoint.  Its model metadata is
    # runtime-owned, so it is admitted as a local conductor seat when the endpoint is reachable;
    # the spawn path still requires a real llama-cli binary and VRAM admission.
    try:
        from adapters import detect  # noqa: PLC0415
        llama_rows = tuple(ConductorModelRegistration(
            provider_id=LLAMACPP_LOCAL_ADAPTER, adapter_id=LLAMACPP_LOCAL_ADAPTER,
            model_id=name, display_name=name, conductor_capable=True, worker_capable=True,
            locality="local") for name in detect.llamacpp_models())
    except Exception:
        llama_rows = ()
    return ollama_rows + llama_rows


def registered_conductor_models(
    local_verdicts: Iterable[Any] | None = None,
) -> tuple[ConductorModelRegistration, ...]:
    """Every conductor-capable seat this host can offer — frontier AND local (S-20).

    ENTRY 018, the operator: *"the conductor seat is agnostic. It needs to have the local library
    anyways. It's not frontier only. That would defeat the whole purpose of the system."* Before
    LOCAL-01 this returned three rows, all frontier, so no local model could ever be a registered
    conductor-capable combination and `resolve_conductor_descriptor` failed closed on every one.
    """
    frontier = () if LOCAL_ONLY_MODE else tuple(m for m in CONDUCTOR_MODEL_REGISTRY if m.conductor_capable)
    return frontier + _local_conductor_registrations(local_verdicts)


def resolve_conductor_descriptor(
    provider_id: str,
    model_id: str,
    *,
    workspace: str = DEFAULT_WORKSPACE,
    permission_profile_id: str = CONDUCTOR_PERMISSION_PROFILE,
    selection_source: str = "unstated",
    workspace_refusal: str | None = None,
    local_verdicts: Iterable[Any] | None = None,
) -> ConductorDescriptor:
    if frontier_disabled(provider_id):
        raise ConductorRegistryError(f"{LOCAL_ONLY_REASON}: {provider_id!r} cannot be selected as conductor")
    match = next(
        (m for m in registered_conductor_models(local_verdicts)
         if m.provider_id == provider_id and m.model_id == model_id),
        None,
    )
    if match is None or not match.conductor_capable:
        raise ConductorRegistryError(
            f"provider/model {provider_id!r}/{model_id!r} is not a registered conductor-capable "
            "combination (fail closed)"
        )
    if not workspace or not permission_profile_id:
        raise ConductorRegistryError("conductor workspace and permission profile must be non-empty")
    return ConductorDescriptor(
        role="conductor",
        provider_id=match.provider_id,
        adapter_id=match.adapter_id,
        model_id=match.model_id,
        display_name=match.display_name,
        permission_profile_id=permission_profile_id,
        workspace=str(workspace),
        # A LOCAL conductor holds NO subscription. Minting `sub-ollama_local` would create an I-X3
        # bucket for a resource that has no allowance to spend and would make the always-visible n/2
        # bar count a terminal nobody is paying for. Empty is the honest ref, and the local branch of
        # `spawn_conductor_pane` is what declines to require one (invariant 19: locality is per-node).
        subscription_ref=("" if match.locality == "local"
                          else canonical_subscription_ref(match.adapter_id)),
        readiness_turns=match.readiness_turns,
        locality=match.locality,
        selection_source=selection_source,
        workspace_refusal=workspace_refusal,
    )


def descriptor_from_mapping(raw: Mapping[str, Any], *, workspace: str = DEFAULT_WORKSPACE,
                            selection_source: str = "unstated") -> ConductorDescriptor:
    """Build a descriptor from a stored/host-supplied mapping.

    SW-ORCH-001 F-22: the mapping's `workspace` is host-local state, so it is VALIDATED against
    this install before use rather than passed through. `workspace` (the keyword) remains the
    fallback for a mapping that carries none, and is itself the containment authority — a caller
    resolving a descriptor for a particular install passes that install's root here.
    """
    if not isinstance(raw, Mapping):
        raise ConductorRegistryError("conductor selection must be an object")
    admitted, refusal = _admissible_workspace(raw.get("workspace"), install_root=str(workspace))
    return resolve_conductor_descriptor(
        str(raw.get("provider_id") or raw.get("provider") or raw.get("adapter_id") or ""),
        str(raw.get("model_id") or raw.get("model_slug") or raw.get("model") or ""),
        workspace=admitted,
        permission_profile_id=str(
            raw.get("permission_profile_id") or CONDUCTOR_PERMISSION_PROFILE),
        selection_source=(f"{selection_source}+workspace_refused" if refusal else selection_source),
        workspace_refusal=refusal,
    )


def load_runtime_conductor_descriptor(path: Path | str | None = None) -> ConductorDescriptor:
    """Load the host-local preference from the existing gitignored live-operation file.

    Absence of a preference resolves the RECORDED selection — Claude/fable-5, D-COND-03, chosen by
    the operator on 2026-07-16 — and a present but invalid preference fails closed and is never
    substituted across providers.

    U331 (unit 19.6): both outcomes now say which one they are, in ``selection_source``. The file
    is gitignored, so its absence is the ordinary case on any clone, and the audited shell answered
    that ordinary case by failing conductor readiness forever with a message that read like a
    configuration error. That pin is gone; this field is the other half of the repair — the shell
    can report "the recorded default selection, no host preference present" rather than leaving the
    operator to infer it. It labels, and nothing reads it to decide whether a conductor may run.
    """
    # A LOCAL selection is consulted FIRST, and deliberately (LOCAL-01 F-3, ENTRY 018).
    # `live_operation.json` is permanently absent under OD-31, so the branch below always resolved
    # the recorded frontier default — which meant the Conductor was frontier-backed no matter what
    # the operator chose, with no configuration present at all. The local store is the operator's
    # own most recent choice, it authorizes nothing, and it is gitignored host state.
    #
    # ONLY on the default resolution. An explicit `path` means "resolve THIS preference file" — it
    # is how the suite pins each branch of the frontier behaviour — and letting a host-local store
    # override an argument the caller passed would make the function answer a question it was not
    # asked, and make those tests depend on whatever this machine last selected.
    local = _load_local_conductor_selection() if path is None else None
    if local is not None:
        try:
            return descriptor_from_mapping(local, selection_source="local_operator_selection")
        except ConductorRegistryError:
            # The stored model is gone from the host, or now falls outside the operator's ceiling.
            # Fall through to the recorded default rather than fail the whole conductor: a stale
            # preference must not make the shell unable to resolve any conductor at all.
            pass

    resolved = Path(path) if path is not None else _LIVE_CONFIG
    if not resolved.exists():
        if LOCAL_ONLY_MODE:
            raise ConductorRegistryError(f"{LOCAL_ONLY_REASON}; select an enumerated local model")
        return resolve_conductor_descriptor(CLAUDE_CODE_ADAPTER, "fable-5",
                                            selection_source="recorded_default_selection")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConductorRegistryError(f"cannot read conductor preference from {resolved}: {exc}") from exc
    pref = raw.get("conductor") if isinstance(raw, dict) else None
    if pref is None:
        if LOCAL_ONLY_MODE:
            raise ConductorRegistryError(f"{LOCAL_ONLY_REASON}; select an enumerated local model")
        return resolve_conductor_descriptor(CLAUDE_CODE_ADAPTER, "fable-5",
                                            selection_source="recorded_default_selection")
    return descriptor_from_mapping(pref, selection_source="live_operation_preference")
