"""Which worker panes are actually up, for a conductor that has been guessing.

EPC-02, operator-directed. Measured against the operator's running system: he had four Electron
processes and a screenful of ConPTY consoles open, and the conductor dispatched to `worker-A`
and `worker-B` — synthetic ids from a hardcoded tuple in `conductor_dispatch.py`:

    DEFAULT_WORKER_IDS: tuple[str, ...] = ("worker-A", "worker-B")

His panes appeared nowhere. The conductor was not unaware because presence was missing; it was
unaware because nothing looked. `provider_node_registration.register_pane_session` already
registers a governed pane as a Sovereign node, behind three fences, and `attest_spawned`
already records a live pid as a separate act with a separate fact behind it. `NodeRegistry`
already tracks states and incarnations.

This module reads that registry. It adds no authority and no fences of its own.

WHAT PRESENCE IS, AND WHAT IT IS NOT. Knowing a pane is up is not knowing it did anything.
`_assert_legs_honest` makes a `live` worker leg unrepresentable without its own evidence
record, and `build_acceptance_packet` refuses one — those guards are untouched here and this
module never asserts a leg. A conductor that can NAME the panes that exist is still dispatching
mock-first until a pane actually publishes a CANDIDATE (U58, owner gate 16F).

The distinction matters because it is exactly the failure this codebase keeps guarding against:
a record that narrates something it cannot observe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: States in which a pane is a plausible delegate. SPAWNING is deliberately EXCLUDED: at ticket
#: time the ConPTY has not been spawned, which is why `attest_spawned` exists as a separate act.
#: Offering a conductor a pane that may never come up would be presence asserting more than the
#: registry knows.
LIVE_PANE_STATES: frozenset[str] = frozenset({"READY", "RUNNING", "IDLE", "ACTIVE"})


@dataclass(frozen=True)
class PanePresence:
    """One pane the registry knows about. A description, never a capability claim."""

    node_id: str
    model: str | None
    state: str
    pid: int | None
    incarnation: int | None = None

    @property
    def is_live(self) -> bool:
        """Up by the registry's own account, with a pid behind it.

        Both halves are required. A record in a live state with no pid has not been attested
        spawned; a pid with no live state is a process the registry no longer vouches for.
        """
        return self.state.upper() in LIVE_PANE_STATES and bool(self.pid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "model": self.model,
            "state": self.state,
            "pid": self.pid,
            "incarnation": self.incarnation,
            "live": self.is_live,
        }


def _read(record: Any, *names: str) -> Any:
    for name in names:
        value = getattr(record, name, None)
        if value not in (None, ""):
            return value
    return None


def presence_from_records(records: Iterable[Any]) -> list[PanePresence]:
    """Fold whatever the registry hands back into presence rows.

    Tolerant by design: this runs on the operator's display path, and a registry row with an
    unexpected shape must not take the conductor's surface down. A row that cannot be read is
    skipped rather than guessed at — an invented node id would be worse than a missing one.
    """
    presence: list[PanePresence] = []
    for record in records or ():
        node_id = _read(record, "node_id", "id", "name")
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        state = _read(record, "state", "status") or "UNKNOWN"
        pid = _read(record, "pid", "process_id")
        presence.append(PanePresence(
            node_id=node_id.strip(),
            model=_read(record, "model", "model_id", "model_tag"),
            state=str(getattr(state, "name", state)),
            pid=int(pid) if isinstance(pid, int) else None,
            incarnation=_read(record, "incarnation"),
        ))
    return sorted(presence, key=lambda p: p.node_id)


def live_pane_ids(presence: Sequence[PanePresence]) -> tuple[str, ...]:
    """The ids a conductor could plausibly address, in stable order."""
    return tuple(p.node_id for p in presence if p.is_live)


def presence_feed(presence: Sequence[PanePresence],
                  dispatched_to: Sequence[str] = ()) -> dict[str, Any]:
    """The record the conductor surface renders.

    `dispatched_to` is carried so the two can be COMPARED rather than conflated. When the
    conductor dispatches to ids that are not present panes, that is the honest and currently
    expected state — a mock-first dispatch — and the feed says so in a field an operator can
    read, instead of leaving him to infer it from ids that merely look plausible.
    """
    present = [p.as_dict() for p in presence]
    live = list(live_pane_ids(presence))
    addressed = [str(x) for x in dispatched_to]
    return {
        "panes_present": present,
        "panes_live": live,
        "dispatched_to": addressed,
        "dispatched_to_live_panes": bool(addressed) and all(x in live for x in addressed),
        "note": (
            "Presence is what the node registry knows: which panes were registered and attested "
            "spawned. It is NOT a claim that any pane executed work. A dispatch to ids outside "
            "`panes_live` is a mock-first dispatch (U58, owner gate 16F)."
        ),
    }
