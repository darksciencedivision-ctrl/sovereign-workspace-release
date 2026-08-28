"""Base adapter contract (Plan sections 9.8, 12.2; invariants 2, 5, 29).

Every adapter — conductor, worker, coding, voice — satisfies this contract so the §12.2
conformance suite can exercise them uniformly. The contract encodes the non-negotiables:
  - an adapter refuses to start naked (I-C1): it must be handed a supervisor-issued
    identity + permission profile, never construct its own;
  - an adapter holds NO provider/subscription credential (invariant: credentials stay in
    host-native stores; the adapter references them, Plan §18.4) — the conductor path in
    particular holds no credential (Phase 4 exit criterion);
  - all shared context comes through MCP, never a side channel (I-M1/invariant 8);
  - the adapter can export its session state and context status for succession (I-CS1);
  - the adapter declares capability + eligibility flags the profile loader enforces.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class NakedLaunchRefused(Exception):
    """An adapter was constructed without a supervisor-issued identity (I-C1)."""


@dataclass(frozen=True)
class AdapterCapability:
    adapter: str                      # e.g. "conductor_fable5", "openai_codex_cli"
    node_class: str                   # conductor | worker_reasoning | worker_coding_specialist | voice_input_service
    locality: str                     # local | frontier
    offline_profile_eligible: bool
    requires_network: bool
    local_runtime: bool
    capabilities: tuple[str, ...] = ()   # capability descriptors (I-SC1): coding, reasoning, ...
    subscription_backed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter, "node_class": self.node_class, "locality": self.locality,
            "offline_profile_eligible": self.offline_profile_eligible, "requires_network": self.requires_network,
            "local_runtime": self.local_runtime, "capabilities": list(self.capabilities),
            "subscription_backed": self.subscription_backed,
        }


@dataclass
class AdapterContext:
    """What the supervisor hands an adapter at construction. Its presence is the proof the
    adapter was not started naked."""
    node_id: str
    role: str
    project_id: str
    permission_profile_id: str
    mcp_credential_id: str            # a REFERENCE to an MCP identity token, not a provider secret
    subscription_ref: str | None = None
    spawned_by_supervisor: bool = False


class BaseAdapter(abc.ABC):
    def __init__(self, context: AdapterContext) -> None:
        if not context.spawned_by_supervisor:
            raise NakedLaunchRefused(f"adapter {type(self).__name__} not spawned by supervisor (I-C1)")
        if not context.permission_profile_id:
            raise NakedLaunchRefused("adapter has no permission profile (I-C1)")
        self._context = context
        self._session_log: list[dict[str, Any]] = []

    @property
    def context(self) -> AdapterContext:
        return self._context

    @abc.abstractmethod
    def capability(self) -> AdapterCapability: ...

    def holds_provider_credential(self) -> bool:
        """Contract default: adapters hold NO provider/subscription secret (Plan §18.4).
        The conductor path asserts this in the conformance suite (Phase 4 exit criterion)."""
        return False

    @abc.abstractmethod
    def export_session_state(self) -> dict[str, Any]:
        """Serializable session state for succession (I-CS1). Must not contain secrets."""

    @abc.abstractmethod
    def get_context_status(self) -> dict[str, Any]:
        """Context-window / resume status surfaced to the operator (no project truth lives here)."""

    def _log(self, kind: str, **data: Any) -> None:
        self._session_log.append({"kind": kind, **data})
