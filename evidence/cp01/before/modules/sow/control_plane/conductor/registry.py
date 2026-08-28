"""Registered, provider-neutral conductor model descriptors.

The conductor is a role.  Provider differences stop at the command-adapter boundary; the
desktop lifecycle consumes the same :class:`ConductorDescriptor` for every provider.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.codex import CODEX_ADAPTER
from node_runtime.supervisor.subscription_governor import canonical_subscription_ref

CONDUCTOR_PERMISSION_PROFILE = "pp-conductor-pane"
DEFAULT_WORKSPACE = str(Path(__file__).resolve().parents[2])
_LIVE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "live_operation.json"


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


def registered_conductor_models() -> tuple[ConductorModelRegistration, ...]:
    return tuple(m for m in CONDUCTOR_MODEL_REGISTRY if m.conductor_capable)


def resolve_conductor_descriptor(
    provider_id: str,
    model_id: str,
    *,
    workspace: str = DEFAULT_WORKSPACE,
    permission_profile_id: str = CONDUCTOR_PERMISSION_PROFILE,
    selection_source: str = "unstated",
) -> ConductorDescriptor:
    match = next(
        (m for m in CONDUCTOR_MODEL_REGISTRY
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
        subscription_ref=canonical_subscription_ref(match.adapter_id),
        readiness_turns=match.readiness_turns,
        locality=match.locality,
        selection_source=selection_source,
    )


def descriptor_from_mapping(raw: Mapping[str, Any], *, workspace: str = DEFAULT_WORKSPACE,
                            selection_source: str = "unstated") -> ConductorDescriptor:
    if not isinstance(raw, Mapping):
        raise ConductorRegistryError("conductor selection must be an object")
    return resolve_conductor_descriptor(
        str(raw.get("provider_id") or raw.get("provider") or raw.get("adapter_id") or ""),
        str(raw.get("model_id") or raw.get("model_slug") or raw.get("model") or ""),
        workspace=str(raw.get("workspace") or workspace),
        permission_profile_id=str(
            raw.get("permission_profile_id") or CONDUCTOR_PERMISSION_PROFILE),
        selection_source=selection_source,
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
    resolved = Path(path) if path is not None else _LIVE_CONFIG
    if not resolved.exists():
        return resolve_conductor_descriptor(CLAUDE_CODE_ADAPTER, "fable-5",
                                            selection_source="recorded_default_selection")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConductorRegistryError(f"cannot read conductor preference from {resolved}: {exc}") from exc
    pref = raw.get("conductor") if isinstance(raw, dict) else None
    if pref is None:
        return resolve_conductor_descriptor(CLAUDE_CODE_ADAPTER, "fable-5",
                                            selection_source="recorded_default_selection")
    return descriptor_from_mapping(pref, selection_source="live_operation_preference")
