"""Governed inter-model flow driven by the LIVE-capable conductor binding — Phase 15D `.flow`.

Directive §11 track 15D: "conductor decomposes an objective → Scheduler assigns by capability to
live worker nodes → workers publish CANDIDATE artifacts over MCP → gates → conductor SYNTHESIZES
the ACCEPTED set into an acceptance packet."

This is the Phase-5 end-to-end path (`ConductorPrototype`) driven through the live-capable
conductor binding landed at 15B/15D `.selection`, and it closes the two gaps that path left open:

  1. **The decomposition drives the task graph and the routing.** `ConductorPrototype` hard-coded
     `t-1`/`t-2` and ignored the backend's `proposed_tasks`. Here the conductor's own
     decomposition becomes the task graph and its declared ordering — fail closed: an element that
     does not name a KNOWN capability with a real description is REFUSED and recorded, never
     defaulted (a guessed capability would route work by inference, and the Scheduler must route
     by descriptor — invariant 4). NOT yet consumed: each worker is still handed the OBJECTIVE
     entry as its context ref, not a per-task scoped entry carrying the subtask description, so
     the artifacts differ only by task id. Delivering per-task context is owed (U35) — the graph,
     the ordering and the routing are real; the work content is not yet task-specific.
  2. **The gates are the real gate engine.** `ConductorPrototype` promoted artifacts with a raw MCP
     `transition` (a stand-in). Here `GateEngine.evaluate` produces a `gate@1.0` verdict and
     `apply_to_task` drives the task graph, and ONLY a PASS verdict is followed by the MCP
     promotion — a failed artifact cannot advance (invariant 16), and the promoting client is the
     GATE node, never the author (invariant 18).

Honesty (directive §6 / §10.4): every run declares its LEGS. The CONDUCTOR leg may be called
`live` only when the executing checkpoint was VERIFIED — i.e. reported back by the CLI itself
(`reported_model` → `bind_conductor_selection`). `build_acceptance_packet` REFUSES to package a
mock run as live, so a substituted result cannot be presented as a real-provider result by
construction rather than by convention. No OTHER leg carries a verification record yet, so for
those `live` is refused outright rather than merely unchecked — a live worker path must arrive
together with its own evidence record. `attempt_live_flow` runs the whole flow through the
governed live-spawn gates and degrades to skip-with-record on any unmet gate, making no live
call; a run that reached the model but did not complete is reported `attempted`, never `skipped`.

The conductor SELECTION (fable-5, operator-selected) and the EXECUTING checkpoint stay separate
records throughout (directive §11 15D; `control_plane.conductor.selection`).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from adapters.base.backend import Backend, BackendAuthPause
from adapters.base.contract import AdapterContext
from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor.adapter import ConductorAdapter
from adapters.frontier.claude_code import (
    bind_calls_snapshot,
    claude_code_conductor_descriptor,
    is_live_cli_backend,
    resolve_claude_model_ref,
    verify_reported_checkpoint,
)
from adapters.local.worker import LocalWorkerAdapter
from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    ExecutingEvidence,
    bind_conductor_selection,
)
from control_plane.gates.criteria import GateContext
from control_plane.gates.engine import GateEngine, define_gate
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import ProfileLoader
from control_plane.tasks.graph import TaskGraph, TaskState
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.conductor_spawn import spawn_claude_code_conductor
from node_runtime.supervisor.frontier_spawn import spawn_claude_code_terminal
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor
from scheduler.capability_registry.registry import CapabilityRegistry
from scheduler.scheduler import Scheduler

# --------------------------------------------------------------------------------------
# 1. decomposition: the conductor's proposed tasks -> task-graph inputs (fail closed)
# --------------------------------------------------------------------------------------

#: Requirements are PINNED here per capability — they are policy, not model output. A model that
#: proposes a task can name WHICH capability it needs; it cannot widen or invent the requirements
#: its work will be routed against.
CAPABILITY_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "reasoning": {"tool_use": True, "structured_output": True, "min_context": 8000, "locality": "any"},
    "review": {"structured_output": True, "min_context": 8000},
    "coding": {"tool_use": True, "structured_output": True, "min_context": 8000},
}

#: parse modes the conductor backend may report. Anything else is unusable (fail closed).
_USABLE_PARSE_MODE = "structured"
_KNOWN_PARSE_MODES = (_USABLE_PARSE_MODE, "unstructured")


class DecompositionError(ValueError):
    """The decomposition input was not a decision payload at all (a caller/programming error).

    Malformed CONTENT inside a well-shaped payload is never raised — it is refused and recorded,
    because that is normal live-model output, not a bug.
    """


@dataclass(frozen=True)
class DecomposedTask:
    task_id: str
    description: str
    capability: str
    capability_req: dict[str, Any]
    deps: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "description": self.description,
                "capability": self.capability, "deps": list(self.deps)}


@dataclass(frozen=True)
class Decomposition:
    tasks: tuple[DecomposedTask, ...]
    refused: tuple[dict[str, Any], ...]
    parse_mode: str

    @property
    def usable(self) -> bool:
        return bool(self.tasks)

    def as_record(self) -> dict[str, Any]:
        return {"parse_mode": self.parse_mode, "accepted_count": len(self.tasks),
                "refused_count": len(self.refused), "tasks": [t.as_record() for t in self.tasks],
                "refused": [dict(r) for r in self.refused]}


def decompose_plan(decision: Any, *, task_id_prefix: str = "t") -> Decomposition:
    """Turn a conductor decision payload into task-graph inputs, FAIL CLOSED.

    Accepts the shape produced by both `MockReasoningBackend.propose_plan` and
    `ClaudeCodeConductorBackend.propose_plan`. Nothing is invented: an unparseable decomposition
    (`parse_mode` other than 'structured') yields NO tasks even if elements are present, and every
    rejected element is recorded with its index and reason so a dropped task is never silent.
    """
    if not isinstance(decision, Mapping):
        raise DecompositionError(f"decomposition input must be a mapping, got {type(decision).__name__}")

    parse_mode = decision.get("parse_mode", _USABLE_PARSE_MODE)
    if not isinstance(parse_mode, str) or parse_mode not in _KNOWN_PARSE_MODES:
        return Decomposition((), ({"index": None, "reason": f"unknown parse_mode {parse_mode!r} "
                                                            f"(fail closed)", "raw": None},), str(parse_mode))
    if parse_mode != _USABLE_PARSE_MODE:
        return Decomposition((), ({"index": None, "raw": None,
                                   "reason": "conductor reply was unstructured — no task is trusted "
                                             "from an unparsed decomposition"},), parse_mode)

    proposed = decision.get("proposed_tasks")
    if not isinstance(proposed, list):
        return Decomposition((), ({"index": None, "raw": None,
                                   "reason": f"proposed_tasks missing or not a list "
                                             f"({type(proposed).__name__})"},), parse_mode)
    if not proposed:
        return Decomposition((), ({"index": None, "raw": None,
                                   "reason": "conductor proposed no tasks"},), parse_mode)

    tasks: list[DecomposedTask] = []
    refused: list[dict[str, Any]] = []
    #: 1-based PROPOSED index -> the task id that element actually received. Ids number only
    #: accepted tasks, so a proposed index is NOT the task number and must be translated.
    assigned: dict[int, str] = {}
    for index, element in enumerate(proposed):
        ok, why = _element_fault(element)
        if not ok:
            refused.append({"index": index, "reason": why, "raw": _excerpt(element)})
            continue
        deps, why = _resolve_deps(element, position=index + 1, assigned=assigned,
                                  proposed_count=len(proposed))
        if deps is None:
            # an unresolvable dependency edge is never silently dropped: the dependent task is
            # refused, which cascades naturally to anything depending on IT (deps point backwards)
            refused.append({"index": index, "reason": why, "raw": _excerpt(element)})
            continue
        capability = element["capability"].strip()
        task_id = f"{task_id_prefix}-{len(tasks) + 1}"
        assigned[index + 1] = task_id
        tasks.append(DecomposedTask(
            task_id=task_id,
            description=str(element["desc"]).strip(),
            capability=capability,
            deps=deps,
            capability_req={"capability": capability,
                            "requirements": copy.deepcopy(CAPABILITY_REQUIREMENTS[capability])}))
    return Decomposition(tuple(tasks), tuple(refused), parse_mode)


def _resolve_deps(element: Mapping[str, Any], *, position: int, assigned: Mapping[int, str],
                  proposed_count: int) -> tuple[tuple[str, ...] | None, str]:
    """Resolve an element's declared `deps` (1-based indices over the PROPOSED list) to task ids.

    Returns `(deps, "")` on success or `(None, reason)` on refusal — never a partial edge set.
    Rules, all fail closed:

      * absent `deps` is an EMPTY dependency list, never a guessed edge;
      * an index must be a real int (`bool` is an int subclass and is refused) naming a STRICTLY
        EARLIER element — a forward or self reference is refused. Backward-only edges satisfy
        `TaskGraph.add_task`'s define-deps-first precondition and make a cycle structurally
        impossible from this path; the plan gate's `plan_acyclic` criterion still runs as an
        independent check rather than the sole guard;
      * an index naming a REFUSED element is unsatisfiable — its prerequisite never entered the
        graph, so running the dependent task would execute work out of order.
    """
    raw = element.get("deps", [])
    if not isinstance(raw, list):
        return None, f"deps must be a list of 1-based task indices, got {type(raw).__name__}"
    resolved: list[str] = []
    for dep in raw:
        if isinstance(dep, bool) or not isinstance(dep, int):
            return None, f"dep {_excerpt(dep)} is not an integer task index (fail closed)"
        if dep < 1 or dep > proposed_count:
            return None, (f"dep index {dep} is outside the proposed list "
                          f"(1..{proposed_count})")
        if dep >= position:
            return None, (f"dep index {dep} does not name a strictly earlier task "
                          f"(element {position} may only depend on 1..{position - 1})")
        if dep not in assigned:
            return None, (f"dep index {dep} names an element that was itself refused — "
                          f"its prerequisite never entered the graph")
        task_id = assigned[dep]
        if task_id not in resolved:                 # deterministic dedup, order preserved
            resolved.append(task_id)
    return tuple(resolved), ""


def _element_fault(element: Any) -> tuple[bool, str]:
    if not isinstance(element, Mapping):
        return False, f"element is not a mapping ({type(element).__name__})"
    desc = element.get("desc")
    if not isinstance(desc, str) or not desc.strip():
        return False, "element has no usable description"
    capability = element.get("capability")
    if not isinstance(capability, str) or not capability.strip():
        return False, "element names no capability (never defaulted — fail closed)"
    if capability.strip() not in CAPABILITY_REQUIREMENTS:
        return False, (f"unknown capability {capability.strip()!r}; known: "
                       f"{sorted(CAPABILITY_REQUIREMENTS)}")
    return True, ""


def _excerpt(value: Any, limit: int = 200) -> str:
    try:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = repr(value)
    return text[:limit]


# --------------------------------------------------------------------------------------
# 2. the acceptance packet the conductor synthesizes from the ACCEPTED set
# --------------------------------------------------------------------------------------

ACCEPTANCE_PACKET_SCHEMA = "acceptance_packet@1.0"
ACCEPTANCE_PACKET_KEYS: tuple[str, ...] = (
    "schema", "objective", "ts", "synthesized_by", "conductor_selection", "decomposition",
    "accepted", "accepted_count", "accepted_confirmed_in_mcp", "failed_tasks", "queued_tasks",
    "task_states", "gate_records", "legs", "operator_disposition", "promotion_conflicts",
    "node_refusals", "worker_evidence",
)

#: The gate engine can promote this packet to ACCEPTED in MCP (invariants 16/18 — a deterministic
#: verdict by a node that is not the author). That is NOT operator acceptance: the operator holds
#: final authority (invariant 1) and has not been consulted anywhere in this loop. The field is
#: pinned so an ACCEPTED `acceptance_packet@1.0` can never be mistaken for an operator decision.
OPERATOR_DISPOSITION_PENDING = "pending"
#: The run reached the backend and a call was COUNTED, but no VERIFIED executing checkpoint came
#: back — so the leg is neither a clean `skipped` (nothing was spent) nor a provable `live`.
#: Reporting such a run as `skipped` would under-report spend, the same dishonest direction the
#: `calls` counters guard; reporting it as `live` would claim a checkpoint nobody verified.
ATTEMPTED_LEG = "attempted"

#: A leg is what it can be PROVEN to be. 'live' requires a verified executing checkpoint;
#: 'attempted' is the honest middle value for a real call that returned no verifiable checkpoint.
VALID_LEGS = ("live", ATTEMPTED_LEG, "mock", "skipped")
_REQUIRED_LEGS = ("conductor", "workers")

#: Prefix of a PER-NODE worker leg, e.g. `worker:frontier-live-1`. The `workers` leg describes the
#: pool as a whole (necessarily coarse for a mixed pool); a prefixed leg names exactly one node, so
#: an operator reading the packet can see WHICH worker was live rather than only that one was.
WORKER_LEG_PREFIX = "worker:"


class AcceptancePacketError(ValueError):
    """The packet could not be built honestly — refused rather than emitted with a false claim."""


def build_acceptance_packet(
    *,
    objective: str,
    conductor_selection: Mapping[str, Any] | None,
    decomposition: Mapping[str, Any],
    accepted: Sequence[Mapping[str, Any]],
    failed_tasks: Sequence[str],
    queued_tasks: Sequence[Mapping[str, Any]],
    task_states: Mapping[str, str],
    gate_records: Sequence[Mapping[str, Any]],
    legs: Mapping[str, str],
    synthesized_by: str,
    ts: str,
    accepted_confirmed_in_mcp: int = 0,
    promotion_conflicts: Sequence[Mapping[str, Any]] = (),
    node_refusals: Sequence[Mapping[str, Any]] = (),
    worker_evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the operator-facing acceptance packet, deterministically and honestly.

    `ts` is INJECTED (no clock read here) so the packet is replayable. Counts are DERIVED from the
    accepted set — a caller cannot inflate them. The load-bearing refusal: a leg declared `live`
    must be backed by a VERIFIED executing checkpoint, so a mock or skipped leg can never be
    packaged as a real-provider result (directive §6, §10.4).
    """
    if not isinstance(objective, str) or not objective.strip():
        raise AcceptancePacketError("acceptance packet needs a real objective")
    if not isinstance(ts, str) or not ts.strip():
        raise AcceptancePacketError("acceptance packet needs an injected timestamp")
    if not isinstance(synthesized_by, str) or not synthesized_by.strip():
        raise AcceptancePacketError("acceptance packet must name its synthesizer")
    if isinstance(accepted, (str, bytes, Mapping)) or not isinstance(accepted, Sequence):
        raise AcceptancePacketError("accepted must be a sequence of accepted-entry mappings")
    accepted_rows: list[dict[str, Any]] = []
    for item in accepted:
        if not isinstance(item, Mapping) or not str(item.get("entry_id") or "").strip():
            raise AcceptancePacketError(f"accepted entry must name its MCP entry_id: {_excerpt(item)}")
        accepted_rows.append({"entry_id": item["entry_id"], "task_id": item.get("task_id"),
                              "content_hash": item.get("content_hash")})

    # a reconciliation count that can exceed the set it reconciles is worse than no count
    confirmed_count = int(accepted_confirmed_in_mcp)
    if not 0 <= confirmed_count <= len(accepted_rows):
        raise AcceptancePacketError(
            f"accepted_confirmed_in_mcp={confirmed_count} cannot exceed the accepted set "
            f"({len(accepted_rows)}) or be negative — it reconciles that set, it does not extend it")

    _assert_legs_honest(legs, conductor_selection, worker_evidence)

    return {
        "schema": ACCEPTANCE_PACKET_SCHEMA,
        "objective": objective,
        "ts": ts,
        "synthesized_by": synthesized_by,
        "conductor_selection": copy.deepcopy(dict(conductor_selection)) if conductor_selection else None,
        "decomposition": copy.deepcopy(dict(decomposition)),
        "accepted": accepted_rows,
        "accepted_count": len(accepted_rows),
        # how many of THIS run's accepted entries were read back as ACCEPTED from MCP — a
        # reconciliation, never a project-wide count
        "accepted_confirmed_in_mcp": confirmed_count,
        # gate promotion is not operator acceptance (invariant 1) — see OPERATOR_DISPOSITION_PENDING
        "operator_disposition": OPERATOR_DISPOSITION_PENDING,
        # Carried into the DURABLE artifact, not just the in-process trace: without these an
        # operator reading the published packet sees a task both DONE and failed with nothing
        # explaining why. Conflicts are explicit objects (invariant 13) and node-authored refusal
        # text stays attributed to the node, never to the gate engine.
        "promotion_conflicts": [dict(c) for c in promotion_conflicts],
        "node_refusals": [dict(r) for r in node_refusals],
        # The per-node record every worker leg above is DERIVED from (Phase 17B `.legs`): which node
        # executed, whether a vendor call was counted, and the checkpoint the CLI reported back. It
        # travels in the DURABLE artifact so an operator reading the published packet can re-derive
        # the legs rather than take them on trust.
        "worker_evidence": [dict(r) for r in _validated_worker_evidence(worker_evidence)],
        "failed_tasks": list(failed_tasks),
        "queued_tasks": [dict(q) for q in queued_tasks],
        "task_states": dict(task_states),
        "gate_records": [{"gate_id": g.get("gate_id"), "kind": g.get("kind"),
                          "verdict": g.get("verdict"), "task_id": g.get("task_id")}
                         for g in gate_records],
        "legs": dict(legs),
    }


#: The shape one worker's evidence row must have before ANY worker leg may be read off it. Every
#: field is a fact the flow OBSERVED (did this node execute; was a vendor call counted; did the CLI
#: report back a checkpoint), never a caller's claim about itself.
_WORKER_EVIDENCE_BOOLS = ("executed", "spent", "verified")


def _validated_worker_evidence(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Validate + normalise worker evidence rows, FAIL CLOSED on anything unreadable.

    A malformed row is refused rather than skipped: silently dropping it would turn a row that says
    "this node spent a live call" into no row at all, which reads as "nothing was spent" — the
    under-reporting direction §6 forbids.
    """
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
        raise AcceptancePacketError("worker_evidence must be a sequence of per-node evidence rows")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise AcceptancePacketError(f"worker evidence row must be a mapping: {_excerpt(row)}")
        node_id = str(row.get("node_id") or "").strip()
        if not node_id:
            raise AcceptancePacketError(f"worker evidence row must name its node_id: {_excerpt(row)}")
        if node_id in seen:
            # two rows for one node would let a caller pick whichever backs the leg it wants
            raise AcceptancePacketError(f"duplicate worker evidence row for node {node_id!r}")
        seen.add(node_id)
        backing = row.get("leg")
        if backing not in ("live", "mock"):
            raise AcceptancePacketError(
                f"worker evidence row {node_id!r} must classify its backing as 'live' or 'mock' "
                f"(what the node is BOUND to), got {backing!r}")
        flags: dict[str, bool] = {}
        for key in _WORKER_EVIDENCE_BOOLS:
            value = row.get(key)
            if not isinstance(value, bool):
                raise AcceptancePacketError(
                    f"worker evidence row {node_id!r} must carry a boolean {key!r}, got {_excerpt(value)}")
            flags[key] = value
        model = row.get("model")
        if model is not None and not isinstance(model, str):
            raise AcceptancePacketError(
                f"worker evidence row {node_id!r} model must be the reported checkpoint string or None")
        if flags["verified"]:
            # a verification record IS a checkpoint the vendor CLI reported back; without the
            # checkpoint string (or against a mock binding) there is nothing verified to report
            if backing != "live":
                raise AcceptancePacketError(
                    f"worker evidence row {node_id!r} claims verified against a {backing!r} binding")
            if not (isinstance(model, str) and model.strip()):
                raise AcceptancePacketError(
                    f"worker evidence row {node_id!r} claims verified with no reported checkpoint")
            if not flags["spent"]:
                raise AcceptancePacketError(
                    f"worker evidence row {node_id!r} claims a verified checkpoint with no counted "
                    f"call — nothing ran, yet something reported (contradictory evidence)")
            if not flags["executed"]:
                raise AcceptancePacketError(
                    f"worker evidence row {node_id!r} claims a verified checkpoint but never "
                    f"executed a task in this run")
        tasks = row.get("tasks") or []
        if isinstance(tasks, (str, bytes, Mapping)) or not isinstance(tasks, Sequence):
            raise AcceptancePacketError(f"worker evidence row {node_id!r} tasks must be a sequence")
        out.append({"node_id": node_id, "leg": backing, "model": model.strip() if isinstance(model, str) else None,
                    "adapter": row.get("adapter"), "tasks": [str(t) for t in tasks], **flags})
    return tuple(out)


def derive_worker_legs(rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Derive the per-node worker legs AND the pool aggregate from validated evidence.

    Per node (`worker:<node_id>`): a node that executed nothing is `skipped`; a mock-bound node is
    `mock`; a live-bound node is `live` only with a verification record, `attempted` when a call was
    counted without one.

    Aggregate (`workers`), over the nodes that actually EXECUTED:
      * nothing executed                                        → `skipped`
      * every executing node is a VERIFIED live node            → `live`
      * at least one executing node spent a live call, but the  → `attempted`
        above does not hold (an unverified live node, OR a
        MIXED pool where live and mock workers both ran)
      * otherwise (only mock workers ran)                       → `mock`

    The MIXED case is deliberately `attempted`, not `mock`: a pool where a real subscription call was
    spent must not be reported as if nothing was, since under-reporting spend is the dishonest
    direction (§6). It is equally not `live`, because some of this pool's work came from a mock. The
    per-node legs carry which is which — the aggregate is coarse by nature, so it is the conservative
    reading of a set, never a claim about any single node.
    """
    legs: dict[str, str] = {}
    executed = [r for r in rows if r.get("executed")]
    for row in rows:
        node_id = row["node_id"]
        if not row.get("executed"):
            legs[f"{WORKER_LEG_PREFIX}{node_id}"] = "skipped"
        elif row["leg"] != "live":
            legs[f"{WORKER_LEG_PREFIX}{node_id}"] = "mock"
        elif row.get("verified"):
            legs[f"{WORKER_LEG_PREFIX}{node_id}"] = "live"
        elif row.get("spent"):
            legs[f"{WORKER_LEG_PREFIX}{node_id}"] = ATTEMPTED_LEG
        else:
            # A live-bound node that executed but counted no call reached no model at all. `skipped`,
            # not `mock`: `mock` asserts a mock backend produced this node's work, and nothing here
            # produced any (spec-audit MINOR-1). The row still carries `leg: "live"`, so what the
            # node was BOUND to remains readable — the leg describes what RAN.
            legs[f"{WORKER_LEG_PREFIX}{node_id}"] = "skipped"
    # The aggregate is folded from the PER-NODE legs just derived, not recomputed from the rows: two
    # independent derivations drift, and they did — a node whose per-node leg was `skipped` still
    # counted toward a `mock` aggregate, so the pool claimed a mock had produced work that nothing
    # produced. One derivation, one vocabulary.
    node_legs = [legs[f"{WORKER_LEG_PREFIX}{r['node_id']}"] for r in executed]
    if not node_legs or all(v == "skipped" for v in node_legs):
        legs["workers"] = "skipped"
    elif all(v == "live" for v in node_legs):
        legs["workers"] = "live"
    elif ATTEMPTED_LEG in node_legs or "live" in node_legs:
        # a real call was spent somewhere in this pool, but not every node's work is a verified live
        # result — neither `live` nor `mock` is honest, and under-reporting spend is the worse error
        legs["workers"] = ATTEMPTED_LEG
    else:
        legs["workers"] = "mock"
    return legs


def _assert_legs_honest(legs: Mapping[str, str], conductor_selection: Mapping[str, Any] | None,
                        worker_evidence: Sequence[Mapping[str, Any]] = ()) -> None:
    """Refuse any leg claim this packet cannot back with evidence, in BOTH directions.

    The conductor leg is backed by a VERIFIED executing checkpoint (reported by the CLI itself).
    A WORKER leg — the pool aggregate or a per-node `worker:<id>` leg — is backed by that node's own
    evidence row (Phase 17B `.legs`): a run that supplies no worker evidence cannot declare a live or
    attempted worker leg at all, and a run that DOES supply evidence must declare exactly the legs
    that evidence derives. Nothing is left to convention: an unverifiable claim is impossible to
    write, and so is an under-claim that would hide real spend (directive §6, §10.4). Every OTHER leg
    name still has no verification record, so `live` stays unrepresentable for it.
    """
    if not isinstance(legs, Mapping):
        raise AcceptancePacketError("legs must declare what actually ran")
    for name in _REQUIRED_LEGS:
        if name not in legs:
            raise AcceptancePacketError(f"leg {name!r} must be declared (mock/live/skipped)")
    rows = _validated_worker_evidence(worker_evidence)
    derived = derive_worker_legs(rows) if rows else {}
    for name, value in legs.items():
        if value not in VALID_LEGS:
            raise AcceptancePacketError(f"leg {name!r}={value!r} is not one of {VALID_LEGS}")
        if name == "conductor":
            continue
        if name == "workers" or name.startswith(WORKER_LEG_PREFIX):
            if value in ("live", ATTEMPTED_LEG) and not rows:
                raise AcceptancePacketError(
                    f"leg {name!r} cannot be declared {value!r} with no worker evidence: a live "
                    f"worker leg must land with its own evidence record — until then the claim is "
                    f"unbacked (directive §6, §10.4)")
            if rows and derived.get(name) != value:
                raise AcceptancePacketError(
                    f"leg {name!r}={value!r} contradicts the worker evidence, which derives "
                    f"{derived.get(name)!r} — legs are DERIVED from evidence, never asserted "
                    f"(directive §6, §10.4)")
            continue
        if value in ("live", ATTEMPTED_LEG):
            raise AcceptancePacketError(
                f"leg {name!r} cannot be declared {value!r}: only the conductor and worker legs "
                f"carry a verification record. A live {name!r} leg must land with its own evidence "
                f"record — until then the claim is unbacked (directive §6, §10.4)")
    for name in derived:
        if name not in legs:
            raise AcceptancePacketError(
                f"worker evidence derives leg {name!r}={derived[name]!r}, which the packet does not "
                f"declare — a node's leg is never dropped from the record")
    if legs.get("conductor") == "live" and not _executing_verified(conductor_selection):
        raise AcceptancePacketError(
            "a LIVE conductor leg requires a VERIFIED executing checkpoint reported by the CLI; "
            "an unverified run is mock/skipped (directive §6, §10.4 — never present a substituted "
            "result as the real-provider result)")


def _executing_verified(conductor_selection: Mapping[str, Any] | None) -> bool:
    if not isinstance(conductor_selection, Mapping):
        return False
    executing = conductor_selection.get("executing")
    if not isinstance(executing, Mapping):
        return False
    return executing.get("verified") is True and bool(str(executing.get("model") or "").strip())


# --------------------------------------------------------------------------------------
# 3. the governed flow
# --------------------------------------------------------------------------------------

#: stage-gate criteria (the canonical set used by the Phase-13 harness)
STAGE_CRITERIA = ["artifact_present", "structured_output_valid", "artifact_content_addressed",
                  "claims_cite_evidence", "no_placeholders", "no_unresolved_critical"]
PLAN_CRITERIA = ["plan_acyclic"]
ACCEPTANCE_CRITERIA = ["artifact_present", "structured_output_valid", "artifact_content_addressed",
                       "claims_cite_evidence", "no_placeholders"]


def _max_waves(task_count: int) -> int:
    """Structural bound on scheduling waves. Deps point strictly backwards, so the longest chain
    is `task_count`; a wave need not COMPLETE a task (its node-local gate may fail), but a wave
    that assigns nothing cannot change readiness and the loop's own no-assignment exit fires
    first. This bound is defence in depth: the governed loop terminates deterministically even if
    a future readiness change made that quiescence check wrong (Buildout §4, fail closed)."""
    return max(1, task_count) + 1


@dataclass(frozen=True)
class ConductorHandle:
    """A conductor bound for this flow, plus the honest record of what it is."""

    adapter: ConductorAdapter
    leg: str                                    # "live" | "mock"
    selection_record: dict[str, Any] | None = None
    model_resolution: dict[str, Any] | None = None
    #: recomputed after a cycle so the EXECUTING checkpoint reflects what the CLI reported
    rebind: Callable[[ConductorAdapter], dict[str, Any] | None] | None = None


def mock_conductor_handle(mcp_client: Any, conductor_manifest: dict[str, str], *,
                          project_id: str = "proj",
                          node_id: str = "conductor-fable5") -> ConductorHandle:
    """The mock-first conductor: the same ConductorAdapter contract, a deterministic backend, and
    a selection record whose EXECUTING checkpoint is honestly unverified (nothing live ran)."""
    ctx = AdapterContext(node_id=node_id, role="conductor", project_id=project_id,
                         permission_profile_id="pp-conductor", mcp_credential_id="ref",
                         subscription_ref=None, spawned_by_supervisor=True)
    backend = MockReasoningBackend()
    adapter = ConductorAdapter(ctx, mcp_client, backend, None, conductor_manifest)
    selection = bind_conductor_selection(
        OPERATOR_SELECTED_CONDUCTOR, requested_model=OPERATOR_SELECTED_CONDUCTOR.model,
        resolver=resolve_claude_model_ref).as_record()
    # The SELECTION is the operator's interface label and is preserved (invariant 3), but the
    # resolution describes what is actually BOUND. Emitting the claude_code roster descriptor here
    # would assert a frontier, subscription-backed, vendor identity for a run in which no
    # claude_code component participates — the descriptor must describe the bound backend.
    return ConductorHandle(adapter=adapter, leg="mock", selection_record=selection,
                           model_resolution=_mock_conductor_descriptor(backend))


def _mock_conductor_descriptor(backend: Any) -> dict[str, Any]:
    """A neutral resolution record for a mock-backed conductor: no vendor, no subscription, and
    nothing verified.

    This is deliberately a NARROWER field set than the vendor roster descriptor
    (`claude_code_conductor_descriptor`), which also carries `capability_descriptors`,
    `candidate_models` and `role`. Those describe a roster entry backed by a real CLI; asserting
    them for a mock would be the overclaim this function exists to remove. Consumers must treat
    the vendor-only fields as absent, not empty.
    """
    return {
        # `name` on the CLI-shaped backends, `model_name` on MockReasoningBackend — resolved in
        # that order so the descriptor actually names the bound backend rather than a literal
        "adapter": (getattr(backend, "name", None) or getattr(backend, "model_name", None)
                    or "unknown_backend"),
        "node_class": "conductor",
        "conductor_capable": True,
        "subscription_backed": False,
        "locality": "local",
        "model_ref": {"requested": OPERATOR_SELECTED_CONDUCTOR.model, "resolved_slug": None,
                      "verified": False, "is_fallback": False,
                      "note": "mock reasoning backend — no vendor CLI is bound to this conductor"},
    }


@dataclass(frozen=True)
class WorkerHandle:
    """A worker node bound for this flow, plus the honest record of what backs it.

    Injected exactly like `ConductorHandle`, so the SAME governed loop runs the deterministic
    `LocalWorkerAdapter` pool or a live, supervisor-spawned vendor terminal with no branch in the
    governed path (invariant 4: workers are interchangeable behind the adapter contract).

    `verify` is the load-bearing field: it returns this node's own verification record (the
    checkpoint the vendor CLI reported back, dated to a call spent in THIS run) or None. Without it
    `derive_worker_legs` cannot produce a `live` leg.

    STATED LIMIT (U43, inherited): `leg` and `verify` are plain injected fields, so this is
    unforgeable only for handles minted by `live_claude_worker_handle`, whose verifier is
    `verify_reported_checkpoint` against the exact vendor CLI class. A caller that writes its own
    verifier can produce a `live` leg without a vendor call — this suite does exactly that to drive
    the flow deterministically. What the design rules out is every ACCIDENTAL and every mock-SHAPED
    path: `live` is trustworthy exactly as far as the caller that mints the handle is.
    """

    node_id: str
    adapter: Any
    leg: str                                                    # "live" | "mock" — what is BOUND
    descriptors: tuple[dict[str, Any], ...]
    locality: str = "local"
    cost_class: str = "local"
    offline_profile_eligible: bool = True
    #: run one assignment; defaults to `adapter.execute()` (the LocalWorkerAdapter signature)
    execute: Callable[[], dict[str, Any]] | None = None
    #: this node's verification record, or None when nothing is verifiable
    verify: Callable[[], dict[str, Any] | None] | None = None
    #: True when a vendor call was counted since bind time. Unreadable ⇒ True (over-reporting spend
    #: is the honest direction, §6) — mirrors `_spent_calls`/`_failure_legs` on the conductor leg.
    spent: Callable[[], bool] | None = None
    #: release whatever the spawn acquired (the I-X3 terminal). Called by `LiveGovernedFlow.close`
    #: so a live worker never outlives the work unit (D-LOOP-1).
    release: Callable[[], None] | None = None

    def run_task(self) -> dict[str, Any]:
        return self.execute() if self.execute is not None else self.adapter.execute()

    def verification(self) -> dict[str, Any] | None:
        if self.leg != "live" or self.verify is None:
            return None
        try:
            record = self.verify()
        except Exception:  # noqa: BLE001 — an unreadable verifier is NOT a verification
            return None
        return record if isinstance(record, Mapping) and record.get("verified") is True else None

    def spent_a_call(self) -> bool:
        if self.leg != "live":
            return False
        if self.spent is None:
            return True                 # a live binding with no counter: fail closed to "spent"
        try:
            return bool(self.spent())
        except Exception:  # noqa: BLE001 — unreadable counter over-reports spend, never under
            return True


@dataclass
class _WorkerNode:
    node_id: str
    adapter: Any
    handle: WorkerHandle | None = None
    executed: list[str] = field(default_factory=list)

    def run_task(self) -> dict[str, Any]:
        return self.handle.run_task() if self.handle is not None else self.adapter.execute()


@dataclass
class _RunState:
    """The in-flight state of ONE governed run, held on the flow so the run can be interrupted
    between waves and resumed by a different conductor (Phase 15D `.succession`).

    It holds only scheduling/bookkeeping state. Every project fact — artifacts, provenance, gate
    verdicts, statuses — lives in MCP, which is exactly why a conductor can be replaced without
    loss (invariant 5: project state lives outside model context).
    """

    objective: str
    trace: dict[str, Any]
    objective_entry: str
    decomposition: Decomposition
    gate_records: list[dict[str, Any]]
    accepted: list[dict[str, Any]] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    all_assignments: list[Any] = field(default_factory=list)
    queued_rows: list[dict[str, Any]] = field(default_factory=list)
    queued_seen: set[str] = field(default_factory=set)
    conductor_swaps: list[dict[str, Any]] = field(default_factory=list)
    waves_run: int = 0
    plan_blocked: bool = False


class LiveGovernedFlow:
    """Objective → conductor decomposition → capability-based assignment → CANDIDATE over MCP →
    real gate engine → conductor synthesis into an acceptance packet.

    The conductor is INJECTED as a `ConductorHandle`, so the identical flow runs on the mock
    backend or on the live claude_code binding (`live_conductor_handle`) with no branch in the
    governed path itself — the conductor is an interface (invariant 3).
    """

    def __init__(self, server: MCPServer, conductor_manifest: dict[str, str], *,
                 project_id: str = "proj",
                 conductor_handle: ConductorHandle | None = None,
                 worker_ids: Sequence[str] = ("worker-A", "worker-B"),
                 worker_handles: Sequence[WorkerHandle] = (),
                 clock: Callable[[], str] | None = None) -> None:
        self._srv = server
        self._project = project_id
        self._graph = TaskGraph()
        self._registry = CapabilityRegistry()
        self._scheduler = Scheduler(self._graph, self._registry)
        self._gates = GateEngine()
        self._clients: list[McpClient] = []
        self._clock = clock or _now
        self._worker_ids = tuple(worker_ids)
        self._worker_handles = tuple(worker_handles)
        collisions = sorted(set(self._worker_ids) & {h.node_id for h in self._worker_handles})
        if collisions:
            # two nodes under one id would let a mock adapter execute work whose evidence row was
            # written from the live handle of the same name — the leg would describe the wrong node
            raise ValueError(f"worker node ids collide between the mock pool and injected "
                             f"handles: {collisions}")

        self._op = self._client("operator", "operator")
        self._gate = self._client("gate-1", "gate")
        self._handle = conductor_handle or mock_conductor_handle(
            self._client("conductor-fable5", "conductor"), conductor_manifest,
            project_id=project_id)
        self._conductor = self._handle.adapter
        self._workers: dict[str, _WorkerNode] = {}
        #: node-authored refusal explanations, kept OUT of the frozen gate@1.0 records
        self._node_refusals: list[dict[str, Any]] = []
        #: explicit CAS-conflict objects from lost promotions (invariant 13)
        self._conflicts: list[dict[str, Any]] = []
        #: the in-flight run, None until begin() — one flow runs one objective
        self._run: _RunState | None = None

    # -- plumbing ----------------------------------------------------------------
    def _client(self, node_id: str, role: str) -> McpClient:
        c = McpClient("127.0.0.1", self._srv.port,
                      self._srv.credentials.issue(node_id, role, self._project))
        c.connect()
        self._clients.append(c)
        return c

    def _spawn_worker(self, node_id: str) -> _WorkerNode:
        ctx = AdapterContext(node_id=node_id, role="worker", project_id=self._project,
                             permission_profile_id="pp-worker", mcp_credential_id="ref",
                             spawned_by_supervisor=True)
        adapter = LocalWorkerAdapter(ctx, self._client(node_id, "worker"))
        self._registry.register(node_id, adapter.capability_descriptors(), locality="local",
                                cost_class="local", offline_profile_eligible=True)
        node = _WorkerNode(node_id, adapter)
        self._workers[node_id] = node
        return node

    def _register_handle(self, handle: WorkerHandle) -> _WorkerNode:
        """Register an INJECTED worker node so the Scheduler can resolve to it BY DESCRIPTOR.

        The node was already spawned through its own governed path (a live frontier terminal comes
        from `spawn_claude_code_terminal`, gates and I-X3 included) — this only publishes the
        capability descriptors it declares, so routing stays descriptor-based (invariant 4) and a
        vendor name never enters the resolver.
        """
        self._registry.register(handle.node_id, [dict(d) for d in handle.descriptors],
                                locality=handle.locality, cost_class=handle.cost_class,
                                offline_profile_eligible=handle.offline_profile_eligible)
        node = _WorkerNode(handle.node_id, handle.adapter, handle=handle)
        self._workers[handle.node_id] = node
        return node

    # -- the run -----------------------------------------------------------------
    def run(self, objective: str, *, gate_reject_tasks: frozenset[str] = frozenset()) -> dict[str, Any]:
        """The whole governed loop in one call: begin → waves to quiescence → synthesize.

        Composed from the three phases below rather than duplicating them, so a caller that must
        interrupt the run (Phase 15D `.succession`: kill the conductor between waves) drives the
        SAME code path this method does — there is no separate "succession flow" that could drift
        from the gated one.
        """
        run_state = self.begin(objective)
        if run_state.plan_blocked:
            return self.finish()
        self.run_waves(gate_reject_tasks=gate_reject_tasks)
        return self.finish()

    def begin(self, objective: str) -> _RunState:
        """Phase 1: publish the objective, let the conductor decompose, gate the plan, build the
        graph and spawn workers. No task has executed when this returns."""
        trace: dict[str, Any] = {"objective": objective, "legs": {"conductor": self._handle.leg,
                                                                  "workers": "mock"}}

        # (a) the objective lives in MCP as scoped context — never a forwarded transcript (inv 8)
        objective_entry = self._op.call(
            "publish", kind="finding", tier="shared_project",
            content_b64=_b64(objective.encode("utf-8")),
            provenance=_prov("operator", self._clock()), status="ACCEPTED")["entry_id"]
        trace["objective_entry"] = objective_entry

        # (b) the conductor decomposes (CANDIDATE decision published through MCP)
        self._conductor.start()
        cycle = self._conductor.run_cycle(objective)
        trace["plan_decision"] = cycle["decision_entry"]
        if self._handle.rebind is not None:
            self._handle = ConductorHandle(
                adapter=self._conductor, leg=self._handle.leg,
                selection_record=self._handle.rebind(self._conductor),
                model_resolution=self._handle.model_resolution, rebind=self._handle.rebind)
        trace["conductor_selection"] = self._handle.selection_record
        trace["model_resolution"] = self._handle.model_resolution

        decomposition = decompose_plan(cycle["decision"])
        trace["decomposition"] = decomposition.as_record()

        # (c) plan gate — the REAL gate engine, before any assignment. An unusable decomposition
        #     cannot advance: no plan, no tasks, no work (fail closed, invariant 16).
        plan_tasks = [{"task_id": t.task_id, "deps": list(t.deps)} for t in decomposition.tasks]
        plan_verdict = self._gates.evaluate(define_gate("plan", PLAN_CRITERIA),
                                            GateContext(plan_tasks=plan_tasks),
                                            evidence=[cycle["decision_entry"]])
        trace["plan_gate"] = plan_verdict
        gate_records = [plan_verdict]
        self._run = _RunState(objective=objective, trace=trace, objective_entry=objective_entry,
                              decomposition=decomposition, gate_records=gate_records)
        if plan_verdict["verdict"] not in ("PASS", "PASS_WITH_RESERVATIONS"):
            # No plan ⇒ no tasks, no workers, no waves. `finish()` still synthesizes, so the
            # refusal reaches an operator-facing packet instead of vanishing.
            self._run.plan_blocked = True
            return self._run

        for t in decomposition.tasks:
            self._graph.add_task(t.task_id, t.capability_req, deps=t.deps)
        for node_id in self._worker_ids:
            self._spawn_worker(node_id)
        for handle in self._worker_handles:
            self._register_handle(handle)
        return self._run

    def swap_conductor(self, handle: ConductorHandle) -> None:
        """Replace the bound conductor mid-run (invariant 28 / I-CN1: the conductor is an
        INTERFACE, so a successor takes over the SAME governed run rather than starting a new one).

        Only the conductor changes: the task graph, the scheduler, the gate engine, the workers and
        every MCP artifact are untouched — that is precisely what makes the succession lossless, and
        what the `.succession` zero-loss comparison measures. The predecessor's leg is NOT merged
        into `trace["legs"]` here: that dict describes the conductor accompanying the packet's
        selection record (`_assert_legs_honest` binds the two), and the predecessor's own leg is
        carried by the succession report instead (see `live_succession.build_succession_report`).
        """
        if self._run is None:
            raise RuntimeError("swap_conductor requires a run in progress (call begin() first)")
        self._handle = handle
        self._conductor = handle.adapter
        self._run.trace["legs"] = {**self._run.trace["legs"], "conductor": handle.leg}
        self._run.conductor_swaps.append({"leg": handle.leg,
                                          "adapter": handle.adapter.capability().adapter,
                                          "selection": handle.selection_record})

    def run_waves(self, *, gate_reject_tasks: frozenset[str] = frozenset(),
                  max_waves: int | None = None) -> bool:
        """Phase 2: schedule and execute waves. Returns True when the graph has QUIESCED (a wave
        assigned nothing), False when it stopped early because `max_waves` was reached.

        `max_waves` is what lets a caller interrupt a run at a real, governed boundary — between
        waves, with the completed waves' artifacts already gated and promoted in MCP — rather than
        by tearing down mid-artifact. The structural `_max_waves` bound still applies on top.
        """
        # (d) Scheduler resolves each READY task to a node BY DESCRIPTOR (invariant 4). A task no
        #     node can serve is QUEUED with its reason — surfaced, never silently dropped.
        #
        #     Scheduling runs in WAVES until the graph quiesces: a task with declared deps starts
        #     PENDING and only becomes READY once its prerequisites reach DONE, so a single pass
        #     would leave every dependent task unexecuted, ungated, and absent from both the
        #     accepted and failed sets — a silent drop. (A dependent of a QUEUED, unroutable task
        #     still reaches neither set; it stays PENDING and is surfaced via `task_states` and the
        #     queued reason.) A wave that assigns nothing cannot change readiness, so it terminates
        #     the loop; `_max_waves` bounds it structurally regardless.
        st = self._require_run()
        if st.plan_blocked:
            return True                     # no plan ⇒ nothing schedulable ⇒ already quiesced
        # the structural bound is on the WHOLE run, so an interrupted-and-resumed run gets the same
        # total budget an uninterrupted one does — resuming cannot buy extra waves
        budget = _max_waves(len(st.decomposition.tasks)) - st.waves_run
        if max_waves is not None:
            budget = min(budget, max(0, int(max_waves)))

        for _wave in range(budget):
            assignments, queued = self._scheduler.schedule_ready()
            for q in queued:
                # a queued task stays READY, so it re-reports every wave — record it once
                if q.task_id not in st.queued_seen:
                    st.queued_seen.add(q.task_id)
                    st.queued_rows.append({"task": q.task_id, "reason": q.reason})
            if not assignments:
                return True                 # nothing ran ⇒ no readiness can change ⇒ quiesced
            st.waves_run += 1
            st.all_assignments.extend(assignments)
            self._run_wave(assignments, st.objective, st.objective_entry, gate_reject_tasks,
                           st.accepted, st.failed, st.gate_records)
        # exhausted the budget without an empty wave: quiesced only if the whole structural bound
        # was consumed (the `run()` contract), not merely this call's `max_waves` slice
        return st.waves_run >= _max_waves(len(st.decomposition.tasks))

    def finish(self) -> dict[str, Any]:
        """Phase 3: the (possibly successor) conductor synthesizes the ACCEPTED set into the
        acceptance packet and the acceptance gate decides."""
        st = self._require_run()
        if not st.plan_blocked:
            # Deliberately ABSENT (not an empty list) when the plan gate blocked the run: the graph
            # was never built and the scheduler was never consulted, so an `assignments: []` key
            # would report an empty scheduling result where no scheduling was attempted.
            st.trace["assignments"] = [{"task": a.task_id, "node": a.node_id, "rationale": a.rationale}
                                       for a in st.all_assignments]
            st.trace["queued"] = st.queued_rows
        if st.conductor_swaps:
            st.trace["conductor_swaps"] = list(st.conductor_swaps)
        return self._synthesize(st.objective, st.trace, st.decomposition, st.accepted, st.failed,
                                st.queued_rows, st.gate_records)

    def _require_run(self) -> _RunState:
        if self._run is None:
            raise RuntimeError("no run in progress — call begin() first")
        return self._run

    def _run_wave(self, assignments: Sequence[Any], objective: str, objective_entry: str,
                  gate_reject_tasks: frozenset[str], accepted: list[dict[str, Any]],
                  failed: list[str], gate_records: list[dict[str, Any]]) -> None:
        """Execute one scheduling wave: assigned task → worker → CANDIDATE → real stage gate."""
        for a in assignments:
            worker = self._workers[a.node_id]
            try:
                self._graph.transition(a.task_id, TaskState.IN_PROGRESS, reason="worker started", by=a.node_id)
                worker.adapter.assign(a.task_id, objective_entry)   # context is an MCP ref
                # Recorded BEFORE the call, not after: a worker that reached the model and then threw
                # (or paused) still spent what it spent, and an evidence row written only on success
                # would report that spend as if it never happened (§6, the under-reporting direction).
                worker.executed.append(a.task_id)
                result = worker.run_task()                          # node-local gate, then CANDIDATE
            finally:
                # W-72: the scheduler acquired this slot BEFORE the wave; a worker that
                # raised used to keep it forever - release lands on EVERY exit path.
                self._registry.release_load(a.node_id)

            # A node that reports a publication but no structured output leaves the STAGE gate with
            # nothing to evaluate. Treated exactly like a node-local refusal — recorded, failed,
            # NOT advanced — rather than crashing the wave or gating the bytes alone: an artifact
            # the gate cannot judge must not advance (invariant 16, fail closed on ambiguity).
            if result.get("published") and not isinstance(result.get("structured"), Mapping):
                # The entry HAS already left the node here (a publish precedes the return), so unlike
                # a node-local gate failure it cannot simply be dropped: leaving it would strand an
                # unreviewable CANDIDATE in shared memory with no gate record pointing at it
                # (validator R5). Reject it in MCP first, then fall into the refusal path.
                orphan = result.get("entry_id")
                if orphan:
                    try:
                        self._gate.call("transition", entry_id=orphan, requested_status="REJECTED",
                                        reviewer_note=("published with no structured output — the "
                                                       "stage gate has nothing to evaluate"))
                    except Exception:  # noqa: BLE001 — a failed cleanup never masks the refusal
                        pass
                result = {"published": False, "local_gate": "FAIL",
                          "reasons": ["node reported a publication with no structured output — the "
                                      "stage gate has nothing to evaluate (fail closed)"]}

            if not result.get("published"):
                # Nothing of this node's is advancing (invariant 16): either its local gate refused
                # and nothing left the node at all, or it published something unreviewable that the
                # branch above has just REJECTED in MCP. Record a local-kind verdict so the refusal
                # carries EVIDENCE into the packet — a failed task with no verdict explaining it is
                # not observable (Buildout §4).
                local_verdict = self._gates.evaluate(
                    define_gate("local", ["artifact_present"]),
                    GateContext(artifact_content=None, structured_output=None),
                    task_id=a.task_id)
                # The gate record is left EXACTLY as the engine validated it: `gate@1.0` is frozen
                # with additionalProperties=false, so grafting a field on would make it
                # schema-invalid, and overwriting `reasons` would attribute node-authored text to
                # `decided_by: gate_engine` (authorship blur, invariants 11/18). The worker's own
                # explanation is recorded ALONGSIDE it, clearly attributed to the node.
                gate_records.append(local_verdict)
                # BOTH refusal vocabularies, because a node has two ways to decline: its local GATE
                # failed (`reasons`), or its BACKEND faulted before there was anything to gate
                # (`backend_error` — the live path: a CLI non-zero exit, timeout, or unparseable
                # response). Reading only `reasons` recorded the live case as a failed task with an
                # empty explanation, which is not observable (Buildout §4) — the fault the operator
                # most needs to see is the one a live vendor call reports back.
                reported = [str(r) for r in (result.get("reasons") or [])]
                backend_error = result.get("backend_error")
                if backend_error:
                    reported.append(str(backend_error))
                self._node_refusals.append({
                    "task_id": a.task_id, "node_id": a.node_id,
                    "gate_id": local_verdict["gate_id"],
                    "node_reported_reasons": reported})
                self._graph.transition(a.task_id, TaskState.BLOCKED,
                                       reason="node-local gate FAIL", by=a.node_id)
                failed.append(a.task_id)
                continue

            entry_id = result["entry_id"]
            self._graph.attach_artifact(a.task_id, entry_id)
            self._graph.transition(a.task_id, TaskState.AWAITING_GATE,
                                   reason="artifact published", by=a.node_id)
            self._gate.call("transition", entry_id=entry_id, requested_status="UNDER_REVIEW")

            # (e) the REAL stage gate decides. The gate node reads the published bytes back FROM
            #     MCP — it does not trust the worker's own report of what it produced (I-M1).
            #     `gate_reject_tasks` seeds a genuine content-addressing defect (a claimed hash
            #     that does not match the stored bytes); the FAIL is COMPUTED, never asserted.
            content = base64.b64decode(self._gate.call("get_content", entry_id=entry_id)["content_b64"])
            structured = result["structured"]
            if a.task_id in gate_reject_tasks:
                structured = copy.deepcopy(structured)
                structured["artifact"]["artifact_id"] = "sha256:" + "0" * 64
            ctx = GateContext(artifact_content=content, structured_output=structured,
                              evidence_refs=[objective_entry, entry_id])
            verdict = self._gates.evaluate(define_gate("stage", STAGE_CRITERIA), ctx,
                                           task_id=a.task_id)
            gate_records.append(verdict)
            self._gates.apply_to_task(self._graph, a.task_id, verdict)

            if verdict["verdict"] not in ("PASS", "PASS_WITH_RESERVATIONS"):
                # a failed artifact is never promoted in MCP either (invariant 16)
                self._gate.call("transition", entry_id=entry_id, requested_status="REJECTED",
                                reviewer_note=f"stage gate {verdict['verdict']} for {a.task_id}")
                failed.append(a.task_id)
                continue

            # promotion is the GATE node's act, never the author's (invariant 18)
            promotion = self._gate.call("transition", entry_id=entry_id, requested_status="ACCEPTED",
                                        reviewer_note=f"stage gate {verdict['verdict']} for {a.task_id}")
            # A lost CAS is an EXPLICIT conflict object, never a silent last-write-wins
            # (invariant 13). MemoryService reports `applied: False` with the parked fork ref;
            # discarding that report would let an entry whose MCP status never changed be counted
            # as accepted. The conflict is surfaced and the entry is NOT accepted.
            if promotion.get("applied") is False:
                # The task graph is NOT forced backwards: the gate verdict genuinely PASSED and
                # the state machine rightly forbids DONE -> BLOCKED (there is no override path,
                # invariant 16). What failed is the MCP promotion, so the task keeps its honest
                # gate outcome while the entry is excluded from the accepted set and the conflict
                # is carried explicitly.
                self._conflicts.append({"task_id": a.task_id, "entry_id": entry_id,
                                        "conflict": promotion.get("conflict"),
                                        "status": promotion.get("status")})
                failed.append(a.task_id)
                continue
            accepted.append({"entry_id": entry_id, "task_id": a.task_id,
                             "content_hash": result.get("content_hash")})

    def _synthesize(self, objective: str, trace: dict[str, Any], decomposition: Decomposition,
                    accepted: list[dict[str, Any]], failed: list[str],
                    queued: list[dict[str, Any]], gate_records: list[dict[str, Any]]) -> dict[str, Any]:
        """The conductor reads the ACCEPTED set back from MCP and synthesizes the packet, which is
        itself published CANDIDATE and gated — the conductor does not accept its own synthesis
        (invariant 18: no node solely judges its own work)."""
        # CONFIRMED, not "visible": `read_accepted` returns every ACCEPTED entry in the project
        # (the 12 conductor files, the objective, any prior run's packet), so a raw count reads as
        # a reconciliation it does not perform. Intersect with THIS run's ids so the number means
        # what its name says.
        visible_ids = {e.get("entry_id") for e in self._conductor.read_accepted()}
        confirmed = [r["entry_id"] for r in accepted if r["entry_id"] in visible_ids]

        # A live run whose CLI returned no verifiable checkpoint must DEGRADE its leg, not abort:
        # the workers' artifacts are already gated and promoted in MCP, so refusing to synthesize
        # would discard the whole governed record over an unprovable label. Report less than was
        # claimed (§6); never destroy the evidence (Buildout §4 observability).
        legs = dict(trace["legs"])
        if legs.get("conductor") == "live" and not _executing_verified(self._handle.selection_record):
            legs["conductor"] = ATTEMPTED_LEG
            trace["leg_degraded"] = ("conductor leg degraded live -> attempted: the CLI reported no "
                                     "verifiable executing checkpoint")
        # The WORKER legs are DERIVED from what each node's own evidence proves, never carried over
        # from the optimistic value `begin()` seeded — an injected handle that turned out to spend
        # nothing degrades exactly like the conductor leg does (Phase 17B `.legs`).
        worker_evidence = self._worker_evidence()
        if worker_evidence:
            legs.update(derive_worker_legs(worker_evidence))
        trace["legs"] = legs
        trace["worker_evidence"] = [dict(r) for r in worker_evidence]

        ts = self._clock()          # read ONCE — two reads make the packet non-reproducible
        packet = build_acceptance_packet(
            objective=objective, conductor_selection=self._handle.selection_record,
            decomposition=decomposition.as_record(), accepted=accepted, failed_tasks=failed,
            queued_tasks=queued, task_states={t.task_id: t.state.value for t in self._graph.all_tasks()},
            gate_records=gate_records, legs=legs,
            synthesized_by=self._conductor.capability().adapter, ts=ts,
            accepted_confirmed_in_mcp=len(confirmed),
            promotion_conflicts=self._conflicts, node_refusals=self._node_refusals,
            worker_evidence=worker_evidence)

        packet_entry = self._conductor.publish_acceptance_packet(packet)
        # Gate the bytes MCP ACTUALLY STORED, read back through the gate node — the same rule the
        # worker path applies (I-M1). The conductor's own artifact is not exempt from it.
        content = base64.b64decode(
            self._gate.call("get_content", entry_id=packet_entry)["content_b64"])
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        # An empty accepted set has nothing to cite. Citing the packet's own id would make it its
        # own evidence for a vacuous claim, which `claims_cite_evidence` would then pass — so the
        # claim is DROPPED instead of self-referentially satisfied (§6 honesty).
        claims = ([{"text": "every accepted artifact passed a stage gate",
                    "evidence_refs": [r["entry_id"] for r in accepted]}] if accepted else [])
        structured = {
            "summary": f"acceptance packet for: {objective}",
            "claims": claims,
            "artifact": {"artifact_id": digest, "media_type": "application/json",
                         "size_bytes": len(content), "created_by_node": self._conductor.capability().adapter,
                         "task_id": None, "ts": ts, "schema": "artifact@1.0"},
        }
        # No `or [packet_entry]` fallback: an empty accepted set has no evidence, and handing the
        # packet its own id would make it self-evidencing — the same defect as the dropped claim.
        acceptance_verdict = self._gates.evaluate(
            define_gate("acceptance", ACCEPTANCE_CRITERIA),
            GateContext(artifact_content=content, structured_output=structured,
                        evidence_refs=[r["entry_id"] for r in accepted]),
            evidence=[r["entry_id"] for r in accepted])
        gate_records.append(acceptance_verdict)
        self._gate.call("transition", entry_id=packet_entry, requested_status="UNDER_REVIEW")
        if acceptance_verdict["verdict"] in ("PASS", "PASS_WITH_RESERVATIONS"):
            self._gate.call("transition", entry_id=packet_entry, requested_status="ACCEPTED",
                            reviewer_note="acceptance gate PASS")
        else:
            self._gate.call("transition", entry_id=packet_entry, requested_status="REJECTED",
                            reviewer_note=f"acceptance gate {acceptance_verdict['verdict']}")

        trace["acceptance_packet"] = packet_entry
        trace["acceptance_artifact_id"] = digest      # the id the acceptance gate content-addressed
        trace["acceptance_gate"] = acceptance_verdict
        trace["packet"] = packet
        trace["accepted_entries"] = [r["entry_id"] for r in accepted]
        trace["failed_tasks"] = failed
        trace["gate_records"] = gate_records
        trace["node_refusals"] = list(self._node_refusals)
        trace["promotion_conflicts"] = list(self._conflicts)
        trace["task_events"] = self._graph.events()
        return trace

    def _worker_evidence(self) -> tuple[dict[str, Any], ...]:
        """One evidence row per INJECTED worker handle — the facts the legs are derived from.

        The deterministic `LocalWorkerAdapter` pool produces no rows: it is the historical default
        and has nothing to verify, and emitting `mock` rows for it would flip the aggregate of every
        pre-existing run from `mock` to a derivation of an empty-ish set. A run with NO handles keeps
        the leg its caller declared (`workers: mock`), unchanged (Phase 17B `.legs` is additive).

        The row is written for every handle, executed or not: a spawned-but-unused live terminal is
        a fact the operator should see (it held an I-X3 slot), and `executed:false` is exactly what
        makes its per-node leg `skipped` rather than a claim.
        """
        rows: list[dict[str, Any]] = []
        for handle in self._worker_handles:
            node = self._workers.get(handle.node_id)
            executed = list(node.executed) if node is not None else []
            record = handle.verification() if executed else None
            rows.append({
                "node_id": handle.node_id,
                "leg": handle.leg,
                "adapter": _adapter_name(handle.adapter),
                "executed": bool(executed),
                # Spend is only asked of a node that actually ran: a handle that never executed
                # cannot have spent anything in THIS flow, and the counter is lifetime-scoped. A
                # verification record is ITSELF proof a call was counted (it is datable to one), so
                # it settles `spent` without a second, independently-failable read.
                "spent": bool(executed) and (record is not None or handle.spent_a_call()),
                "verified": record is not None,
                "model": (record or {}).get("model"),
                "tasks": executed,
            })
        return _validated_worker_evidence(rows)

    def worker_evidence_rows(self) -> tuple[dict[str, Any], ...]:
        """The worker evidence as it stands RIGHT NOW, readable after a fault mid-run.

        `run()` folds these into the packet on the happy path. A caller whose run raised has no
        packet at all, and the spend still happened — so it reads them here and reports it rather
        than emitting a feed that says nothing ran (§6, the under-reporting direction).
        """
        return self._worker_evidence()

    # -- introspection used by tests/inspector -----------------------------------
    @property
    def graph(self) -> TaskGraph:
        return self._graph

    @property
    def conductor_handle(self) -> ConductorHandle:
        """The conductor handle CURRENTLY bound to the flow.

        After `begin()`, this is the REBOUND handle when the conductor carries a `rebind` (the live
        binding recomputes the EXECUTING checkpoint from what the CLI reported), not the pre-call
        handle the caller passed in. A caller that captured the handle before `begin()` and later
        reports the conductor from it would echo a stale `selection.executing` mirror beside a
        freshly-correct verification — the U62 composition artifact. Reading the handle back here
        lets `live_succession` report the predecessor from the same rebound record the packet uses.
        """
        return self._handle

    def close(self) -> None:
        try:
            self._conductor.close()
        except Exception:  # noqa: BLE001 — teardown must not mask a run's result
            pass
        # D-LOOP-1: an injected live worker holds a real I-X3 terminal. Release EVERY handle even if
        # one raises, before the MCP clients go — a wedged subscription count outlives the process
        # that wedged it, so this is the one teardown step that must not be skipped.
        for handle in self._worker_handles:
            if handle.release is None:
                continue
            try:
                handle.release()
            except Exception:  # noqa: BLE001 — one node's failed release never strands the others
                pass
        for c in self._clients:
            c.close()


# --------------------------------------------------------------------------------------
# 4. the live leg: the same flow, through the governed live-spawn gates
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class FlowOutcome:
    """Result of one governed flow attempt. `ran=False, skipped_with_record=True` is the honest
    non-interactive outcome (directive §10.4): the live path is built and gated, but a gate was
    unmet so NO live call was made."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    acceptance_packet: str | None = None
    trace: dict[str, Any] | None = None
    model_resolution: dict[str, Any] | None = None
    conductor_selection: dict[str, Any] | None = None
    legs: dict[str, str] = field(default_factory=lambda: {"conductor": "skipped", "workers": "skipped"})


def live_conductor_handle(
    *,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    conductor_file_refs: dict[str, str],
    model: str | None = None,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
) -> ConductorHandle:
    """Bind the LIVE claude_code conductor for this flow through the governed spawn gates.

    Raises through `spawn_claude_code_conductor` if any gate is unmet — the caller
    (`attempt_live_flow`) turns that into skip-with-record. The leg is `live` only when a REAL
    backend is used; an injected mock backend runs the identical governed path but is recorded as
    `mock`, so a mock-first proof can never be packaged as a live result.
    """
    requested_model = model if model is not None else selection.model
    adapter = spawn_claude_code_conductor(
        mcp_client=mcp_client, governor=governor, subscription_ref=subscription_ref,
        node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
        profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
        conductor_file_refs=conductor_file_refs, model=model, selection=selection,
        project_id=project_id, cli_present=cli_present, backend=backend)

    # The call count of the CLI backend BEFORE this flow's conductor does anything, so a checkpoint
    # can be dated to a call made by THIS run (U45). `None` when there is no vendor backend behind
    # the adapter at all, which can never verify — fail closed.
    calls_before = bind_calls_snapshot(adapter.backend)

    def _rebind(a: ConductorAdapter) -> dict[str, Any]:
        # Evidence, not a bare string: `a.reported_model` is lifetime-scoped and carries no proof a
        # call was spent HERE (U45 site 2). An unverified checkpoint is recorded as an unbacked
        # claim, never as `executing.model`.
        evidence = verify_reported_checkpoint(a.backend, calls_before=calls_before)
        return bind_conductor_selection(
            selection, requested_model=requested_model,
            executing_evidence=ExecutingEvidence(evidence["model"]) if evidence else None,
            reported_model=None if evidence else a.reported_model,
            resolver=resolve_claude_model_ref).as_record()

    return ConductorHandle(
        adapter=adapter,
        # Classified from the backend TYPE that is actually bound, not from "was an override
        # passed": a real `ClaudeCliBackend` handed in explicitly spends the subscription and must
        # be recorded live. Type-based, so a mock cannot spoof it with a `claude_code:cli:` name.
        leg=_leg_for_backend(backend),
        selection_record=bind_conductor_selection(
            selection, requested_model=requested_model, resolver=resolve_claude_model_ref).as_record(),
        model_resolution=claude_code_conductor_descriptor(requested_model),
        rebind=_rebind)


def live_claude_worker_handle(
    *,
    mcp_client: Any,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    node_id: str,
    permission_profile_id: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    model: str | None = None,
    project_id: str = "proj",
    cli_present: bool | None = None,
    backend: Backend | None = None,
    max_tokens: int = 256,
) -> WorkerHandle:
    """Bind a LIVE `claude_code` WORKER node for this flow through the governed live-spawn gates.

    Phase 17B `.legs` (directive §16, closing the worker half of U58). This is the worker mirror of
    `live_conductor_handle`: the node is born from `spawn_claude_code_terminal` — the ONE governed
    live-frontier spawn site — so every gate applies before any live call (roster profile +
    LIVE_OPERATION_AUTHORIZED, provider-live, R8 §6 operator terms, CLI presence, I-X3 acquire), and
    it raises through to the caller when a gate is unmet rather than degrading silently.

    The handle carries its own verification closure: `calls_before` is snapshotted at BIND time, so
    the checkpoint the CLI reports back is datable to a call this flow spent (U45's rule, applied to
    the worker path). Without that record `derive_worker_legs` cannot produce a `live` worker leg —
    the claim is unrepresentable, not merely unchecked.

    `release` gives the I-X3 terminal back; `LiveGovernedFlow.close` calls it (D-LOOP-1).
    """
    adapter = spawn_claude_code_terminal(
        mcp_client=mcp_client, governor=governor, subscription_ref=subscription_ref,
        node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
        profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
        model=model, project_id=project_id, cli_present=cli_present, backend=backend)

    calls_before = bind_calls_snapshot(adapter.backend)

    def _verify() -> dict[str, Any] | None:
        return verify_reported_checkpoint(adapter.backend, calls_before=calls_before)

    def _spent() -> bool:
        # Unreadable (None) fails closed to "spent": under-reporting spend is the dishonest
        # direction (§6). `calls_before is None` means there is no vendor backend to spend at all.
        if calls_before is None:
            return False
        now = bind_calls_snapshot(adapter.backend)
        return True if now is None else now > calls_before

    def _release() -> None:
        governor.release(subscription_ref, node_id)

    cap = adapter.capability()
    return WorkerHandle(
        node_id=node_id,
        adapter=adapter,
        # classified from the backend TYPE actually bound, exactly as the conductor leg is: an
        # injected mock runs the identical governed path but can never be recorded live
        leg=_leg_for_backend(backend),
        descriptors=tuple(copy.deepcopy(d) for d in adapter.capability_descriptors()),
        locality=cap.locality,
        cost_class="subscription" if cap.subscription_backed else "local",
        offline_profile_eligible=cap.offline_profile_eligible,
        execute=lambda: adapter.execute(max_tokens=max_tokens),
        verify=_verify,
        spent=_spent,
        release=_release)


def _adapter_name(adapter: Any) -> str | None:
    try:
        return str(adapter.capability().adapter)
    except Exception:  # noqa: BLE001 — an unnameable adapter is recorded as unknown, never guessed
        return None


def _leg_for_backend(backend: Backend | None) -> str:
    """`live` only for a backend that actually spawns the vendor CLI.

    `backend is None` means `spawn_claude_code_conductor` constructs the REAL `ClaudeCliBackend`,
    so that is a live leg. An explicitly-passed real backend is ALSO live — classifying on "was an
    override supplied" would record a subscription-spending run as `mock`.

    EXACT TYPE (U45 site 1, discharged at `phase-15d.gate`). This was `isinstance`, which accepts a
    SUBCLASS that overrides `generate`, spawns nothing, and sets the instrumentation itself — a mock
    classified `live` (§6/§10.4). The check is never on the backend's `name`, which a mock may set
    freely. This is a BIND-TIME classification and therefore cannot carry spend evidence; the
    evidence requirement is enforced at publish time by `_assert_legs_honest`, which refuses a
    `live` conductor leg without a VERIFIED executing checkpoint.
    """
    return "live" if backend is None or is_live_cli_backend(backend) else "mock"


def _spent_calls(adapter: ConductorAdapter | None) -> int | None:
    """Backend calls counted so far — the evidence that a run reached the model.

    Returns None when the counter is UNREADABLE, which is not the same as zero: reporting an
    unreadable counter as "nothing was spent" is the exact under-reporting `_failure_legs` exists
    to prevent, so the caller fails closed on None instead.
    """
    if adapter is None:
        return 0
    try:
        return int(adapter.export_session_state().get("backend_calls") or 0)
    except Exception:  # noqa: BLE001 — unreadable, NOT zero
        return None


def _failure_legs(handle: ConductorHandle | None, adapter: ConductorAdapter | None) -> dict[str, str]:
    """Legs for a run that did not complete. A live-classified leg whose backend already counted a
    call — or whose counter cannot be read at all — is `attempted`, never `skipped`;
    under-reporting spend is the dishonest direction (§6)."""
    if handle is not None and handle.leg == "live":
        spent = _spent_calls(adapter)
        if spent is None or spent > 0:
            return {"conductor": ATTEMPTED_LEG, "workers": "skipped"}
    return {"conductor": "skipped", "workers": "skipped"}


def attempt_live_flow(
    *,
    objective: str,
    server: MCPServer,
    conductor_file_refs: dict[str, str],
    governor: SubscriptionGovernor,
    subscription_ref: str,
    live_auth: LiveAuthorization,
    profile_loader: ProfileLoader,
    operator_terms_confirmed: bool,
    node_id: str = "conductor-fable5",
    permission_profile_id: str = "pp-conductor",
    model: str | None = None,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    project_id: str = "proj",
    worker_ids: Sequence[str] = ("worker-A", "worker-B"),
    cli_present: bool | None = None,
    backend: Backend | None = None,
    clock: Callable[[], str] | None = None,
) -> FlowOutcome:
    """Run EXACTLY ONE governed flow on the live-capable conductor binding, spawning and tearing
    down within this call (no live process outlives the unit — loop constraint D-LOOP-1).

    Any unmet gate (unauthorized live_auth, unconfirmed R8 §6 operator terms, absent CLI) yields
    skip-with-record and makes NO live call. A `BackendAuthPause` mid-run is a fail-closed pause
    (Plan §18.4). The model resolution and the conductor selection are surfaced on EVERY outcome
    (directive §11 15B/15D — never silent).
    """
    requested_model = model if model is not None else selection.model
    model_resolution = claude_code_conductor_descriptor(requested_model)
    selection_record = bind_conductor_selection(
        selection, requested_model=requested_model, resolver=resolve_claude_model_ref).as_record()
    skipped = {"conductor": "skipped", "workers": "skipped"}

    flow: LiveGovernedFlow | None = None
    try:
        conductor_client = McpClient("127.0.0.1", server.port,
                                     server.credentials.issue(node_id, "conductor", project_id))
        conductor_client.connect()
    except Exception as exc:  # noqa: BLE001
        return FlowOutcome(ran=False, published=False, skipped_with_record=True,
                           reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution,
                           conductor_selection=selection_record, legs=skipped)
    try:
        handle = live_conductor_handle(
            mcp_client=conductor_client, governor=governor, subscription_ref=subscription_ref,
            node_id=node_id, permission_profile_id=permission_profile_id, live_auth=live_auth,
            profile_loader=profile_loader, operator_terms_confirmed=operator_terms_confirmed,
            conductor_file_refs=conductor_file_refs, model=model, selection=selection,
            project_id=project_id, cli_present=cli_present, backend=backend)
    except Exception as exc:  # noqa: BLE001 — every gate failure is skip-with-record
        conductor_client.close()
        return FlowOutcome(ran=False, published=False, skipped_with_record=True,
                           reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution,
                           conductor_selection=selection_record, legs=skipped)
    try:
        flow = LiveGovernedFlow(server, conductor_file_refs, project_id=project_id,
                                conductor_handle=handle, worker_ids=worker_ids, clock=clock)
        trace = flow.run(objective)
    except BackendAuthPause as exc:
        # The real backend raises this only AFTER invoking the CLI, but `ran` is derived from the
        # counted-call evidence rather than assumed — an injected test double can pause without
        # ever reaching a model, and claiming otherwise would be the mirror-image overclaim.
        legs = _failure_legs(handle, handle.adapter)
        _teardown(flow, conductor_client)
        return FlowOutcome(ran=legs["conductor"] == ATTEMPTED_LEG, published=False,
                           skipped_with_record=True,
                           reason=f"auth pause (Plan §18.4): {exc}", model_resolution=model_resolution,
                           conductor_selection=selection_record, legs=legs)
    except Exception as exc:  # noqa: BLE001 — never a false PASS
        legs = _failure_legs(handle, handle.adapter)
        # `ran` reflects whether the conductor actually reached the model, not which branch we exited
        spent = legs["conductor"] == ATTEMPTED_LEG
        _teardown(flow, conductor_client)
        return FlowOutcome(ran=spent, published=False, skipped_with_record=True,
                           reason=f"{type(exc).__name__}: {exc}", model_resolution=model_resolution,
                           conductor_selection=selection_record, legs=legs)

    _teardown(flow, conductor_client)   # spawn -> exercise -> TEAR DOWN inside the unit
    # the prose reason reports the leg AS RECORDED (post-degradation), not the leg we hoped for:
    # a run degraded to `attempted` must not be described as `live` in an operator-facing string
    recorded_leg = trace["legs"]["conductor"]
    return FlowOutcome(
        ran=True, published=True, skipped_with_record=False,
        reason=f"governed flow ran on a {recorded_leg} conductor; acceptance packet published",
        acceptance_packet=trace.get("acceptance_packet"), trace=trace,
        model_resolution=model_resolution,
        conductor_selection=trace.get("conductor_selection") or selection_record,
        legs=dict(trace["legs"]))


def _teardown(flow: LiveGovernedFlow | None, client: McpClient) -> None:
    if flow is not None:
        flow.close()
    try:
        client.close()
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------------------

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prov(author: str, ts: str) -> dict[str, Any]:
    return {"author_node": author, "task_id": None, "ts": ts,
            "directive_version": "v2.4", "confidence": "high"}
