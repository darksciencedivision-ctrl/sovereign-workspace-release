"""Node registry: single state authority for node incarnations (Plan sections 7-P2, 9.1).

Every mutation validates the state machine and lands in the append-only event log before
the in-memory view changes — the log is the record, the dict is a cache of it. I-C1 is
enforced at registration: a process not spawned by the supervisor is refused. PAUSED
resumes only to the state it interrupted. TERMINATED is absorbing; a restart registers
the next incarnation under the same node_id.

**Adapter vocabulary (18B `.scope` → 18D, U227).** `adapter` is a node schema field with a frozen
enum, and until 18B nothing checked it: `register()` took any string. That was tolerable while the
only out-of-enum id was `ollama_local` (a local, un-counted node), and it stopped being
tolerable the moment Phase 18 asked to register subscription-backed frontier providers whose
ids the canonical vocabulary does not contain. The claim "no schema-valid node record can name
these providers" needs to be a property of the code, not a sentence in a docstring — because the
event log is APPEND-ONLY (invariant 12), so a node record written under an unrecognised adapter
cannot be un-written later.

So registration refuses an `adapter` that no version of the node schema admits. **The operator
ruled U227 on 2026-08-01 (OP-12.1, directive §17.1): by SUCCESSOR SCHEMA, not by editing the
freeze.** `schemas/node.schema@1.1.json` exists beside the untouched `@1.0` and adds exactly three
members — `grok_build`, `google_antigravity`, and `ollama_local` (the U254 drift, admitted by the
same ruling). This module's vocabulary is therefore the UNION over every node schema version
present, read from the files; `grok_build` and `google_antigravity` now register, and an id in
NEITHER version is still refused with an auditable `registration_refused` event naming the versions
that were consulted.

Two properties of that union are deliberate. It is derived, never re-declared — a hand-written copy
of an enum is the drift this guard exists to catch. And it is fail-closed in both directions: an
unreadable or malformed schema file contributes NOTHING (so a corrupted `@1.1` refuses the new
providers rather than defaulting them open), and a version whose enum is unreadable cannot widen
anything. `register()` records WHICH version admitted the adapter on the append-only spawn event,
so an auditor reading the log can tell a `@1.0` node from one admitted by the amendment.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event_log import AppendOnlyEventLog
from .states import RESUMABLE, IllegalTransition, NodeState, validate_transition

#: The schema directory, monkeypatchable in tests so the fail-closed branches can be MEASURED
#: against a corrupt/missing file rather than argued for. `_SCHEMA_PATH` (the single-file constant
#: this replaced) is gone rather than kept "for compatibility": it had no reader left, and a stale
#: pointer at the frozen file is precisely how a second, narrower vocabulary source comes back.
_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

#: The node schema versions this registry consults, in precedence order: the frozen Phase-0 file
#: first, then every recorded successor. A successor is a FILE, not a literal — adding a version
#: means writing the schema, extending the freeze manifest's amendment block with its authorizing
#: operator ruling (OP-12.1 / U222), AND adding a row to this tuple. The third act is the one that
#: actually changes runtime behaviour, and it is named last here on purpose: the first two are the
#: reviewable record, this is the switch. A named file that is absent is skipped, not fatal: the
#: union simply stays narrower, which is the safe direction.
NODE_SCHEMA_VERSIONS: tuple[tuple[str, str], ...] = (
    ("node@1.0", "node.schema.json"),
    ("node@1.1", "node.schema@1.1.json"),
)

#: Adapter ids allowed to register while being members of NO node schema version. **Empty since
#: 18D, and that is the point of the amendment.** It held exactly one id — `ollama_local`, the
#: local Ollama adapter every product path has used since Phase 15E while the frozen enum spells
#: the same thing `ollama_direct` (U254) — grandfathered here rather than tolerated silently.
#: OP-12.1 admitted that id into `node@1.1` itself, so the grandfather clause has nothing left to
#: cover and the vocabulary is now schema-derived with no exceptions at all.
#:
#: The mechanism is kept (not deleted) because it is the recorded, reviewable place for a future
#: id that genuinely cannot wait for a schema version — but note that an EMPTY set is strictly
#: stronger than a populated one, and the honest bar for adding a row is now higher, not lower:
#: OP-12.1 shows the schema route is available. There is no bypass parameter; the
#: `allow_unlisted_adapter=True` opt-out the guard first shipped with had no caller anywhere
#: (spec-audit MINOR-5, 18B close) and is gone.
ADAPTER_EXEMPTIONS: frozenset[str] = frozenset()


def node_schema_path(filename: str) -> Path:
    """The on-disk location of one node schema version's file.

    The ONE public spelling of "where the node schemas live" — `_SCHEMA_DIR` is read at CALL time,
    so the monkeypatch seam the fail-closed tests use covers every reader. It exists because the
    18D record validator needs the same file this module derives the vocabulary from, and a second
    module computing its own path is how a record comes to be valid against a schema the fence
    never consulted."""
    return _SCHEMA_DIR / filename


def _enum_of(filename: str) -> frozenset[str]:
    """One schema file's `adapter` enum, read from disk. Unreadable / malformed / missing the
    property ⇒ empty ⇒ that version widens nothing (fail closed)."""
    try:
        schema = json.loads(node_schema_path(filename).read_text(encoding="utf-8"))
        enum = schema["properties"]["adapter"]["enum"]
    except (OSError, ValueError, KeyError, TypeError):
        return frozenset()
    if not isinstance(enum, list) or not all(isinstance(m, str) for m in enum):
        return frozenset()
    return frozenset(enum)


def adapter_version_map() -> dict[str, str]:
    """`adapter id -> the FIRST node schema version that admits it`, over every version present.

    The provenance half of the fence: `register()` writes the version that admitted an adapter onto
    the append-only spawn event, so a later auditor can distinguish a `node@1.0` node from one the
    OP-12.1 amendment admitted, without re-deriving the enums from a log that does not carry them.
    First-wins because `@1.0` is listed first: an id both versions carry is reported as the frozen
    one, which is the stronger provenance claim.

    This is the ONLY vocabulary source — `register()` calls it directly, and the tests assert on it
    for the same reason. A convenience `_schema_adapter_enum()` wrapper stood here for one commit
    and was deleted at the 18D gate (validator MINOR-2): every test asserted on the wrapper while
    the fence read the map, so widening the wrapper alone left the fence untouched and the suite
    red for the wrong reason. A second accessor onto a vocabulary is how a second vocabulary
    starts."""
    admitted: dict[str, str] = {}
    for version, filename in NODE_SCHEMA_VERSIONS:
        for member in sorted(_enum_of(filename)):
            admitted.setdefault(member, version)
    return admitted


class RegistrationRefused(Exception):
    pass


@dataclass
class NodeRecord:
    node_id: str
    incarnation: int
    node_class: str
    adapter: str
    pid: int | None = None
    state: NodeState = NodeState.SPAWNING
    paused_from: NodeState | None = None
    last_heartbeat: float | None = None
    exit_code: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, int]:
        return (self.node_id, self.incarnation)


class NodeRegistry:
    def __init__(self, log: AppendOnlyEventLog) -> None:
        self._log = log
        self._lock = threading.RLock()
        self._nodes: dict[tuple[str, int], NodeRecord] = {}

    def register(
        self,
        node_id: str,
        node_class: str,
        adapter: str,
        *,
        spawned_by_supervisor: bool,
        pid: int | None = None,
        incarnation: int = 1,
        **meta: Any,
    ) -> NodeRecord:
        if not spawned_by_supervisor:
            # I-C1 / invariant 2: no naked sessions. Refusal is itself an auditable event.
            self._log.append("registration_refused", node_id=node_id, incarnation=incarnation, reason="not spawned by supervisor (I-C1)")
            raise RegistrationRefused(f"node {node_id}: not spawned by supervisor (I-C1)")
        admitted_by = adapter_version_map().get(adapter)
        if admitted_by is None and adapter not in ADAPTER_EXEMPTIONS:
            # U227: the node vocabulary lives in versioned schema files and the event log is
            # append-only, so an unrecognised adapter is refused BEFORE it can be written down. No
            # caller may opt out — see ADAPTER_EXEMPTIONS for why the bypass parameter this guard
            # shipped with is gone. The versions CONSULTED are named, so a refusal caused by an
            # unreadable schema file reads differently from one caused by a genuinely unknown id.
            versions = ", ".join(v for v, _ in NODE_SCHEMA_VERSIONS)
            reason = (f"adapter {adapter!r} is not an enum member of any node schema version "
                      f"({versions}) and is not a recorded exemption "
                      f"{sorted(ADAPTER_EXEMPTIONS)} — refuse to append a node record the "
                      f"canonical vocabulary does not admit (U227, invariant 12: the event log "
                      f"cannot be un-written). Admitting a new provider is an operator decision "
                      f"(OP-12.1 admitted grok_build/google_antigravity by successor schema).")
            self._log.append("registration_refused", node_id=node_id, incarnation=incarnation,
                             reason=reason)
            raise RegistrationRefused(f"node {node_id}: {reason}")
        # A `node_record` in the metadata is a CANONICAL DOCUMENT about to land on an append-only
        # log, so the same argument this module makes for the adapter enum applies to it: the
        # guarantee must be a property of the code, not of the single caller that happens to write
        # it correctly today (gate-validator MEDIUM-1, 18D `.close` — a non-node document naming an
        # unadmitted adapter was written onto a verified chain through this API). This is a
        # STRUCTURAL agreement check, not schema validation: the registry must not grow a
        # dependency on the validator, and the record's own schema check belongs to the module that
        # builds it. What it refuses is a record that disagrees with the registration it rides on.
        record = meta.get("node_record")
        if record is not None:
            declared = record.get("schema") if isinstance(record, dict) else None
            known = {v for v, _ in NODE_SCHEMA_VERSIONS}
            problem = (
                "is not an object" if not isinstance(record, dict)
                else f"declares schema {declared!r}, which is no node schema version {sorted(known)}"
                if declared not in known
                else f"names adapter {record.get('adapter')!r}, not {adapter!r}"
                if record.get("adapter") != adapter
                else "carries no node_id" if not record.get("node_id") else None)
            if problem is not None:
                reason = (f"the node_record metadata {problem} — refuse to append a canonical "
                          f"document that disagrees with the registration carrying it (invariant "
                          f"12: the event log cannot be un-written)")
                self._log.append("registration_refused", node_id=node_id, incarnation=incarnation,
                                 reason=reason)
                raise RegistrationRefused(f"node {node_id}: {reason}")
        with self._lock:
            key = (node_id, incarnation)
            if key in self._nodes:
                # every refusal is auditable, same as the I-C1 path
                self._log.append("registration_refused", node_id=node_id, incarnation=incarnation, reason="duplicate registration")
                raise RegistrationRefused(f"duplicate registration {node_id}#{incarnation}")
            record = NodeRecord(node_id=node_id, incarnation=incarnation, node_class=node_class, adapter=adapter, pid=pid, meta=meta)
            # `adapter_schema_version` is provenance on an append-only record: which version of the
            # canonical vocabulary admitted this node. `None` means the exemption list did, which is
            # a different and weaker claim, so it is never reported as a version. Built as a dict
            # rather than passed as a kwarg beside `**meta` so caller metadata cannot collide with
            # (or overwrite) the field — the registry's own provenance wins, deterministically.
            event = {**meta, "adapter_schema_version": admitted_by}
            self._log.append("spawn", node_id=node_id, incarnation=incarnation, pid=pid, node_class=node_class, adapter=adapter, **event)
            self._nodes[key] = record
            return record

    def get(self, node_id: str, incarnation: int | None = None) -> NodeRecord:
        with self._lock:
            if incarnation is not None:
                return self._nodes[(node_id, incarnation)]
            latest = max((k for k in self._nodes if k[0] == node_id), key=lambda k: k[1], default=None)
            if latest is None:
                raise KeyError(node_id)
            return self._nodes[latest]

    def rehydrate(self, record: NodeRecord) -> NodeRecord:
        """Restore ONE record into the in-memory view **from the durable log**, writing nothing.

        The module docstring says it plainly — "the log is the record, the dict is a cache of it" —
        and until 18E nothing could act on that: `NodeRegistry` starts empty and never replays, so
        a SECOND PROCESS reading a durable log could see every event and still not `get()` a node.
        That is exactly the world the worker-pane lifecycle lives in: the ticket is one `py -3.12`
        invocation, the spawn attestation another, the release a third. Without this, closing a
        record written by an earlier process was impossible and the only reachable behaviour was to
        register the same pane again as a fresh incarnation on every step.

        It is a CACHE restore and nothing more, so it is deliberately the weakest method here:
        it appends no event (there is nothing new to record — the caller is reading back what the
        log already says) and it grants no authority. THREE fences, because dropping any would make
        it a bypass of the ones `register()` exists to be:

          * the vocabulary check — an adapter no node schema version admits is refused, since a
            record that could not be WRITTEN must not become readable by another door;
          * the duplicate guard — rehydrating over a live key would silently discard the in-memory
            state of a running node;
          * **the log must actually carry a `spawn` row for this exact `(node_id, incarnation)`.**
            The first cut asserted this in prose ("the caller has to have read the record out of
            the log to pass one in") and enforced nothing, so any in-process caller could hand in a
            fabricated `NodeRecord` and then drive it through `transition`/`record_exit` — which DO
            append — producing `transition`+`exit` rows for a node with no `spawn` row, defeating
            the spawn/exit pairing `event_log` names as the compensating control for the chain's
            tail-truncation blind spot (spec-audit MINOR-8). The claim is now the check.

        Unlike `register()`, a refusal here appends NO `registration_refused` event: nothing was
        being written, and an append-only log is not the place to record that a reader asked a bad
        question.
        """
        admitted = adapter_version_map().get(record.adapter)
        if admitted is None and record.adapter not in ADAPTER_EXEMPTIONS:
            versions = ", ".join(v for v, _ in NODE_SCHEMA_VERSIONS)
            raise RegistrationRefused(
                f"node {record.node_id}: adapter {record.adapter!r} is not an enum member of any "
                f"node schema version ({versions}) — refuse to restore into the live view a record "
                f"the vocabulary does not admit (U227; rehydrate is not a second door)")
        if not self._log_carries_spawn(record.node_id, record.incarnation):
            raise RegistrationRefused(
                f"node {record.node_id}#{record.incarnation}: this log carries no `spawn` row for "
                f"it — refuse to restore a record the log does not have, because a restored record "
                f"can be transitioned and closed, and those DO append (invariant 12)")
        with self._lock:
            key = (record.node_id, record.incarnation)
            if key in self._nodes:
                raise RegistrationRefused(
                    f"node {record.node_id}#{record.incarnation} is already in this registry's "
                    f"view — refuse to overwrite the live state of a node with a replayed copy")
            self._nodes[key] = record
            return record

    def _log_carries_spawn(self, node_id: str, incarnation: int) -> bool:
        """Does this registry's own log carry a `spawn` row for exactly `(node_id, incarnation)`?

        Read from the file rather than from `self._nodes`, because the whole point of `rehydrate`
        is that the in-memory view is empty. Fail-closed in every direction: an unreadable or
        unparseable log answers False, so a rehydrate refuses instead of proceeding on a log nobody
        could check."""
        try:
            with Path(self._log.path).open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        return False
                    if (row.get("kind") == "spawn" and row.get("node_id") == node_id
                            and row.get("incarnation") == incarnation):
                        return True
        except OSError:
            return False
        return False

    def transition(self, node_id: str, requested: NodeState, *, incarnation: int | None = None, reason: str = "", pid: int | None = None) -> NodeRecord:
        with self._lock:
            record = self.get(node_id, incarnation)
            current = record.state
            if requested is NodeState.PAUSED and current in RESUMABLE:
                record.paused_from = current
            if current is NodeState.PAUSED and requested is not NodeState.TERMINATED and requested is not NodeState.DISCONNECTED:
                if record.paused_from is not None and requested is not record.paused_from:
                    raise IllegalTransition(current, requested)
            validate_transition(current, requested)
            # `pid` and nothing else. The first cut took `**data`, which widened the append-only
            # log's write surface to arbitrary unvalidated caller keys on the one store §2.2
            # content must never reach — a surface wider than its single use (spec-audit NIT-13).
            extra = {} if pid is None else {"pid": int(pid)}
            self._log.append(
                "transition", node_id=record.node_id, incarnation=record.incarnation,
                frm=current.value, to=requested.value, reason=reason, **extra,
            )
            record.state = requested
            if requested is not NodeState.PAUSED and record.paused_from is not None and current is NodeState.PAUSED:
                record.paused_from = None
            return record

    def heartbeat(self, node_id: str, *, incarnation: int | None = None) -> None:
        with self._lock:
            record = self.get(node_id, incarnation)
            record.last_heartbeat = time.monotonic()
            if record.state is NodeState.SPAWNING:
                self.transition(node_id, NodeState.READY, incarnation=record.incarnation, reason="first heartbeat")
            elif record.state is NodeState.DISCONNECTED:
                self.transition(node_id, NodeState.READY, incarnation=record.incarnation, reason="heartbeat resumed")

    def record_exit(self, node_id: str, incarnation: int, exit_code: int | None, *, expected: bool) -> NodeRecord:
        with self._lock:
            record = self._nodes[(node_id, incarnation)]
            record.exit_code = exit_code
            if record.state is not NodeState.TERMINATED:
                validate_transition(record.state, NodeState.TERMINATED)  # enforced even here: no bypass path
                self._log.append(
                    "transition", node_id=node_id, incarnation=incarnation,
                    frm=record.state.value, to=NodeState.TERMINATED.value,
                    reason=f"{'expected' if expected else 'unexpected'} exit code={exit_code}",
                )
                record.state = NodeState.TERMINATED
            self._log.append("exit", node_id=node_id, incarnation=incarnation, exit_code=exit_code, expected=expected)
            return record

    def alive(self) -> list[NodeRecord]:
        with self._lock:
            return [r for r in self._nodes.values() if r.state is not NodeState.TERMINATED]

    def all_records(self) -> list[NodeRecord]:
        with self._lock:
            return list(self._nodes.values())
