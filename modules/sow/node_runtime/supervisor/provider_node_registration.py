"""A governed OP-12 provider session becomes a Sovereign node RECORD — Phase 18D `.close`.

**What this closes.** Invariant 2 says every terminal is a Sovereign node. Through 18C the two
OP-12 providers could not be one: `node@1.0`'s `adapter` enum is frozen and has no member for
`grok_build` or `google_antigravity`, so `NodeRegistry.register` refused them and the refusal was
the honest answer (U227). The operator ruled U227 on 2026-08-01 — **OP-12.1, by successor schema**
— and 18D `.amendment` shipped `schemas/node.schema@1.1.json` beside the untouched frozen file.
That opened the vocabulary and deliberately wired nothing to it: the amendment's own evidence says
"the vocabulary is open; nothing is wired to write into it." This module is the wiring.

**It is one direction only.** Registration is not a gate and must never become one — the schema
says so in `node@1.1`'s own description, and it is worth repeating where the code is: a node record
is what a session that ALREADY passed the live switch, the operator's terms determination, CLI
presence and the I-X3 lease leaves behind on the append-only log. Registering does not authorize
anything. What it does is make the session auditable after the fact: the record carries the
adapter, the subscription it was counted against, the workspace it was bound to, and — from the
registry itself — WHICH version of the canonical vocabulary admitted it, so a reader can tell a
`node@1.0` node from one the OP-12.1 amendment admitted without re-deriving enums from a log that
does not carry them.

**Three refusals, all fail-closed, all auditable:**

  1. a session whose own `supervised` field is not True is refused HERE, before anything is
     written — the registrar reads the session's claim, it never makes it on the session's behalf
     (I-C1). The registry's own `spawned_by_supervisor` guard is downstream of this one and stays;
  2. a record that does not validate against the schema version it names is refused by the real
     jsonschema validator against the real file on disk — including an `adapter` no version admits
     and a `schema` string pointing at a version that does not exist. Unreadable file ⇒ refusal,
     never a skipped check;
  3. the registry fence itself (`registry.py`) still refuses an adapter id in NO node schema
     version, with the append-only `registration_refused` event it has always written. `kimi_k3`
     is the live example and stays OWED-pending-operator.

**The log is durable operator state, not repository content.** It lives under `.sovereign_store/`
beside the terminal-lease ledger — gitignored, per-host, hash-chained, append-only (invariant 12).
A record written for a session that then exits is CLOSED on that same log (`transition` → `exit`),
because a one-shot probe that leaves a node reading SPAWNING forever is a D-LOOP-1 leak in the one
place an auditor would look for it.
"""
from __future__ import annotations

from collections.abc import Mapping

import errno
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from adapters.frontier.antigravity import (
    ANTIGRAVITY_ADAPTER,
    ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS,
    AntigravityCliBackend,
)
from adapters.frontier.grok_build import (
    GROK_ADAPTER,
    GROK_REASONING_CAPABILITY_DESCRIPTORS,
    GrokCliBackend,
)
from control_plane.nodes.event_log import AppendOnlyEventLog
from control_plane.nodes.registry import (
    NODE_SCHEMA_VERSIONS,
    NodeRecord,
    NodeRegistry,
    RegistrationRefused,
    adapter_version_map,
    node_schema_path,
)
from control_plane.nodes.states import NodeState

#: Where the durable node event log lives, relative to the repo root. Under `.sovereign_store/`
#: with the lease ledger and the CAS: gitignored, per-host, never committed. A node log inside the
#: tree would make one host's sessions another host's history.
NODE_EVENT_LOG_RELPATH = Path(".sovereign_store") / "nodes" / "node_events.jsonl"

#: The schema version a record built here declares. It is the successor OP-12.1 authorized — the
#: only version whose `adapter` enum admits these two providers. Written as a constant rather than
#: computed from the provider so a reader can see WHICH vocabulary the product path depends on.
RECORD_SCHEMA_VERSION = "node@1.1"

#: uuid5 namespace for node record ids. The schema requires `format: uuid` for `node_id` while the
#: registry's key is the human `probe-grok`; deriving the uuid from the lease key keeps the two
#: linked, makes the record reproducible for the same session, and keeps two sessions of one
#: provider distinct (the U75 lesson, in the record rather than only in the lease).
_NODE_ID_NAMESPACE = uuid.UUID("6f2a1d54-9b3e-5c07-8a41-0d18e3c2b7a9")

#: Gate ids — machine-readable, so a receipt asserts the check that refused instead of grepping
#: prose. Distinct from the probe path's gate ids for the same reason those are distinct from the
#: pane path's: "the registrar refused" must not be satisfiable by any other refusal.
GATE_UNSUPERVISED_SESSION = "node_registration_unsupervised"
GATE_RECORD_INVALID = "node_record_invalid"
GATE_UNKNOWN_NODE = "node_record_unknown"
#: A session object that is not the supervisor's own governed-session type, or one that carries no
#: terminal. Distinct from `GATE_UNSUPERVISED_SESSION` because "you marked it unsupervised" and
#: "you are not the thing that can be supervised" are different refusals (spec-audit MEDIUM-3).
GATE_UNGOVERNED_SESSION = "node_registration_ungoverned"
#: The node log is held by another process. Fail-closed, and its own id so a receipt can tell a
#: contention refusal from a vocabulary one (spec-audit MEDIUM-5).
GATE_LOG_LOCKED = "node_log_locked"
# W-66: the durable history fails AppendOnlyEventLog/verify_file - an integrity fault
# of the hash-chained log, never to be reported as the argv_builder gate.
GATE_LOG_CORRUPT = "node_log_corrupt"
#: The record could not be validated because the validator itself is absent. Fail-closed with an
#: id, so "validator missing" never reads as "record invalid" (spec-audit NIT-12).
GATE_VALIDATOR_UNAVAILABLE = "node_record_validator_unavailable"

#: The bounded wait before a contended node log is refused. Every holder is a short-lived emitter,
#: so a contended window is milliseconds; this covers a picker double-click without ever becoming a
#: pause the operator would notice as a hang.
_LOCK_WAIT_ATTEMPTS = 20
_LOCK_WAIT_SECONDS = 0.1

#: Per provider, derived from the adapter that would run — never re-declared here. A hand-copied
#: capability list is exactly the drift `adapter_version_map()` exists to prevent one level up.
#: EPC-02 / U313(A). What a LOCAL pane can be asked to do. Deliberately narrower than the
#: frontier descriptors beside it: no `tool_use` requirement, because most models at or under
#: 4B on the operator's host report `completion` only, and a descriptor that demanded tools
#: would silently exclude the very panes this wiring exists to register. `min_context` is set
#: to what an 8 GB card can actually hold (EPC-02 sized num_ctx to 20,480 from measured VRAM),
#: not to a model card's maximum.
OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    # `local_only`, not "local": the node@1.1 schema enumerates
    # ['any', 'local_only', 'frontier_ok'] and refused the record outright. Caught by the
    # end-to-end demonstration - the schema is the authority on its own vocabulary, and
    # "local" was my guess at it.
    {"capability": "reasoning", "requirements": {"structured_output": False,
                                                 "min_context": 8192,
                                                 "locality": "local_only"}},
]

#: What an OPENCODE coding pane can be asked to do (EPC-04). Separate from the reasoning
#: descriptors above because the capability genuinely differs: this node edits files inside its own
#: git worktree, which is a different thing to ask of a model than answering a question, and a
#: conductor reading the registry must be able to tell the two apart. The `locality` and
#: `structured_output` terms are unchanged — same card, same small local models.
OPENCODE_LOCAL_CAPABILITY_DESCRIPTORS: list[dict[str, Any]] = [
    {"capability": "coding", "requirements": {"structured_output": False,
                                              "min_context": 8192,
                                              "locality": "local_only"}},
]

from adapters.local.ollama_session import OLLAMA_LOCAL_ADAPTER  # noqa: E402
from adapters.coding.opencode.session import OPENCODE_LOCAL_ADAPTER  # noqa: E402

_PROVIDER_FACTS: dict[str, tuple[str, list[dict[str, Any]]]] = {
    GROK_ADAPTER: (GrokCliBackend.node_class, GROK_REASONING_CAPABILITY_DESCRIPTORS),
    ANTIGRAVITY_ADAPTER: (AntigravityCliBackend.node_class,
                          ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS),
    # U313 said: "Invariant 2 says every terminal is a Sovereign node", and then only two
    # frontier providers were wired. A local pane held a terminal and wrote no record, so the
    # node registry stayed empty and a conductor asking who is up got nothing — measured on the
    # operator's host: 154 node events, grok_build 22, google_antigravity 20, everything else 0.
    OLLAMA_LOCAL_ADAPTER: ("worker_reasoning", OLLAMA_LOCAL_CAPABILITY_DESCRIPTORS),
    # EPC-04. A coding pane is a terminal, so invariant 2 applies to it identically: it registers
    # or it does not open. A CODING class rather than `worker_reasoning` because the node class is
    # what a conductor routes on — filing an OpenCode harness as a reasoning worker would make the
    # registry answer the wrong question correctly.
    #
    # The name is `worker_coding_specialist`, which is the one `node.schema@1.1` admits and the one
    # the frontier coding path already mints (`codex._ROLE_NODE_CLASS`, `roster.coding_node`). This
    # read `worker_coding` — a name no schema enum contains — so EVERY OpenCode pane launch was
    # refused at `node_record_invalid` AFTER passing every gate that precedes it (selection,
    # local runtime, residency). Invariant 2 makes that refusal fatal by design: the record does not
    # validate, so the terminal does not open. The class is a ROUTING key shared with the permission
    # profiles (`permission.schema.json` gates on the same enum), so the fix is to speak the
    # system's existing name, never to widen the enum to admit a second name for one concept.
    OPENCODE_LOCAL_ADAPTER: ("worker_coding_specialist", OPENCODE_LOCAL_CAPABILITY_DESCRIPTORS),
}

#: Adapters governed by VRAM RESIDENCY rather than by a subscription. Their records name a
#: ResidencyPlanner decision; they hold no lease because there is no subscription to count them
#: against, and inventing one would put a lease id on a terminal nobody counted - exactly what
#: the subscription fence exists to make unrepresentable.
RESIDENCY_GOVERNED_ADAPTERS: frozenset[str] = frozenset({OLLAMA_LOCAL_ADAPTER,
                                                         OPENCODE_LOCAL_ADAPTER})

#: The providers this module can build a record for, DERIVED from the facts table above rather than
#: re-listed. Callers that must decide "is this a session I should register?" before building
#: anything read this — a second literal elsewhere is how a provider ends up in one list and not the
#: other, which reads as "deliberately not registered" and is really a typo (the U254 shape).
REGISTRABLE_PROVIDERS: frozenset[str] = frozenset(_PROVIDER_FACTS)


GATE_UNRESERVED_RESIDENCY = "unreserved_residency"


def _require_residency(residency: Any, *, session_id: str, model: Any) -> dict[str, Any]:
    """The LOCAL analogue of the subscription fence, and it is not a weaker one.

    A frontier record names the subscription its terminal was counted against. A local pane has
    no subscription to name — `adapters/local/ollama_session` states it outright: "a local model
    involves NO subscription and NO credential... the governance that applies is VRAM residency
    (invariant 22)". So the local record names the ResidencyPlanner decision that admitted it.

    The same property is preserved: a node record names the counted resource it was admitted
    under, and a record whose count nobody can find is refused. What changes is WHICH resource,
    because for a local pane the honest answer is VRAM, not a subscription.

    A synthetic lease was considered and rejected. It would have satisfied the existing fence
    while putting a lease id onto a terminal that was never counted against any subscription —
    the precise claim that fence exists to make unrepresentable.
    """
    scheduled = None
    reserved_model = None
    if isinstance(residency, Mapping):
        scheduled = residency.get("scheduled")
        reserved_model = residency.get("model")
    elif residency is not None:
        scheduled = getattr(residency, "scheduled", None)
        reserved_model = getattr(residency, "model", None)

    if scheduled is not True:
        raise ProviderNodeRegistrationRefused(
            f"the local pane session carries no VRAM residency reservation (session "
            f"{session_id!r}, scheduled={scheduled!r}) — a local node record names the "
            f"ResidencyPlanner decision it was admitted under, and a pane the planner never "
            f"scheduled has no honest record (fail closed)",
            gate=GATE_UNRESERVED_RESIDENCY)

    if model and reserved_model and str(reserved_model).strip() != str(model).strip():
        raise ProviderNodeRegistrationRefused(
            f"the residency reservation is for {reserved_model!r} but the pane runs "
            f"{model!r} — a record must name the reservation that admitted THIS model, not "
            f"another one that happened to be scheduled (fail closed)",
            gate=GATE_UNRESERVED_RESIDENCY)

    return {"governed_by": "vram_residency",
            "model": str(reserved_model or model or ""),
            "status": (residency.get("status") if isinstance(residency, Mapping)
                       else getattr(residency, "status", None))}


class ProviderNodeRegistrationRefused(Exception):
    """This module refused, fail-closed. `gate` names the check that said no."""

    def __init__(self, message: str, *, gate: str = "provider_node_registration") -> None:
        super().__init__(message)
        self.gate = gate


def default_node_event_log_path(repo_root: str | Path) -> Path:
    """The durable node event log for `repo_root`. One spelling, one location.

    `SOW_NODE_EVENT_LOG` redirects it, exactly as `SOW_TERMINAL_LEASE_LEDGER` redirects the durable
    lease ledger and for the same reason: a check that must not append to the OPERATOR's own node
    history needs somewhere else to write. The override is deliberately visible rather than quiet —
    `ProviderNodeRegistrar.log_path` reports the path in force WITHOUT opening the file, and any
    receipt that reports a node record is expected to name it. (18D shipped a `real_switch` that
    silently followed an env var and named no path, and the validator promptly produced a receipt
    citing register row OP-12 for a file in %TEMP%. Same shape, so: same rule.)"""
    override = os.environ.get("SOW_NODE_EVENT_LOG", "").strip()
    if override:
        return Path(override)
    return Path(repo_root) / NODE_EVENT_LOG_RELPATH


def node_record_uuid(lease_key: str, incarnation: int = 1) -> str:
    """The record's `node_id`, derived from the session's lease key AND its incarnation.

    Deterministic by design — the same session always yields the same record id — and unique per
    registered incarnation, which is not decoration: `register_session` numbers incarnations, so a
    uuid derived from the lease key alone would give two records on one append-only log the same
    `node_id` and make them indistinguishable to every reader downstream.
    """
    return str(uuid.uuid5(_NODE_ID_NAMESPACE, f"{lease_key}#{int(incarnation)}"))


def provider_facts(provider: str | None) -> tuple[str, list[dict[str, Any]]]:
    """`(node_class, capability descriptors)` for an OP-12 provider, or a refusal.

    Separate from `build_provider_node_record` so a caller can ask "is this an id I govern?"
    without building anything and without opening a log."""
    facts = _PROVIDER_FACTS.get(provider or "")
    if facts is None:
        raise ProviderNodeRegistrationRefused(
            f"{provider!r} is not an OP-12 provider this module builds records for — "
            f"{'/'.join(sorted(_PROVIDER_FACTS))} only (fail closed). A third provider is an "
            f"operator decision, exactly as OP-12.1 was for these two.", gate=GATE_RECORD_INVALID)
    return facts


def build_provider_node_record(session: Any, *, incarnation: int = 1) -> dict[str, Any]:
    """The canonical `node@1.1` document for a governed OP-12 provider session.

    Every field is READ from the session or from the adapter that will run — nothing is invented
    here except the derived uuid. `mcp_credential_id` is a reference to an MCP identity, never a
    provider secret (§2.2/§13, Plan §18.4): the CLIs use their own host-native auth and no
    credential ever reaches this record, this log, or MCP.
    """
    provider = getattr(session, "provider", None)
    node_class, capabilities = provider_facts(provider)
    workspace = str(getattr(session, "workspace", "") or "")
    return {
        "node_id": node_record_uuid(f"{session.node_id}#{session.session_id}", incarnation),
        "class": node_class,
        "adapter": provider,
        "harness": None,
        # A probe session selects no model — the CLI's own default answers it — so this is `null`
        # by construction rather than by lookup. It was `getattr(session, "model_ref", None)`,
        # which implied a session shape that does not exist (spec-audit NIT-11).
        "model_ref": None,
        "locality": "frontier",
        "subscription_ref": session.subscription_ref,
        "capabilities": capabilities,
        "workspace": {"type": "dir", "path": workspace} if workspace else {"type": "none"},
        "permission_profile_id": session.permission_profile_id,
        # A REFERENCE, and the same one every other supervised spawn path in this repo writes
        # (`frontier_spawn`, `codex_spawn`, `conductor_spawn`, `opencode_spawn`).
        "auth": {"mcp_credential_id": "mcp-ref"},
        "state": NodeState.SPAWNING.value,
        "offline_profile_eligible": False,
        "spawned_by_supervisor": True,
        "schema": RECORD_SCHEMA_VERSION,
    }


def build_pane_node_record(session: Any, *, session_id: str, incarnation: int = 1,
                           ) -> dict[str, Any]:
    """The canonical `node@1.1` document for a governed OP-12 provider **worker pane** session.

    The sibling of `build_provider_node_record`, and deliberately not a branch inside it: the two
    sessions differ in what they know. A one-shot probe selects no model and its record's
    `model_ref` is `null` by construction; a PANE runs the model the operator picked, and it is in
    the argv — a record that dropped it would describe a different session from the one running in
    front of them.

    Everything is READ off the authorization (`WorkerPaneSession`), never invented here: the
    adapter, model slug, subscription ref and node key come from the chrome the shell renders, the
    workspace from the launch spec the ConPTY is bound to, and the permission profile from the
    identity the supervisor minted. The record's `state` is `SPAWNING` because at the moment this
    is written the process does not exist yet — the ticket is an authorization. `READY` is written
    later, by the attestation, when a supervised pid actually exists.
    """
    chrome = getattr(session, "chrome", None)
    provider = getattr(chrome, "adapter", None)
    node_class, capabilities = provider_facts(provider)
    node_key = str(getattr(chrome, "node_id", "") or "")
    sid = str(session_id or "").strip()
    workspace = str((getattr(session, "launch", None) or {}).get("cwd") or "")
    profile_id = str(getattr(session, "permission_profile_id", "") or "")
    subscription = getattr(chrome, "subscription", None) or {}
    missing = [name for name, value in (("node_id", node_key), ("session_id", sid),
                                        ("workspace", workspace),
                                        ("permission_profile_id", profile_id))
               if not value]
    if missing:
        raise ProviderNodeRegistrationRefused(
            f"a worker-pane node record needs {', '.join(missing)} and the authorization carries "
            f"none — refuse to write a record that cannot be traced back to the session it "
            f"describes (fail closed)", gate=GATE_RECORD_INVALID)
    slug = getattr(chrome, "model_slug", None)
    return {
        "node_id": node_record_uuid(f"{node_key}#{sid}", incarnation),
        "class": node_class,
        "adapter": provider,
        "harness": None,
        # The slug in the argv, or `null` for the recorded CLI-default fallback — the same fact the
        # chrome badges, so the record and the badge cannot disagree.
        "model_ref": slug if isinstance(slug, str) and slug.strip() else None,
        # EPC-02 / U313(A). READ from the chrome, not asserted. This was the literal "frontier",
        # which was true while only grok and google_antigravity could register. A local pane
        # would have written `locality: "frontier"` and a null subscription_ref onto an
        # APPEND-ONLY log that can never be corrected - a record claiming the wrong governance
        # class, which is worse than the missing record it replaced. The schema permits
        # ["local", "frontier"] and the chrome already carries which one this pane is.
        "locality": ("local"
                     if str(getattr(chrome, "locality", "")).strip().lower() == "local"
                     else "frontier"),
        # None for a local pane, and that is the honest value: it holds no subscription, so
        # there is no reference to name. What governs it is the residency reservation the fence
        # above verified, and inventing a ref here would be the synthetic lease by another route.
        "subscription_ref": subscription.get("ref"),
        "capabilities": capabilities,
        "workspace": {"type": "dir", "path": workspace},
        "permission_profile_id": profile_id,
        "auth": {"mcp_credential_id": "mcp-ref"},
        "state": NodeState.SPAWNING.value,
        "offline_profile_eligible": False,
        "spawned_by_supervisor": True,
        "schema": RECORD_SCHEMA_VERSION,
    }


def validate_node_record(record: dict[str, Any]) -> str:
    """Validate `record` against the node schema version it declares, and return that version.

    Fail closed in every direction: an undeclared or unknown `schema`, a file that cannot be read
    or parsed, and any validation error are all refusals. The check is the REAL validator against
    the REAL file — the same document `adapter_version_map()` derives the vocabulary from — so a
    record cannot be valid here and invalid to the fence.
    """
    try:
        import jsonschema  # noqa: PLC0415 — local, matching this package's convention
    except ImportError as exc:      # pragma: no cover — the validator is a hard dependency here
        raise ProviderNodeRegistrationRefused(
            f"the node-record validator is unavailable ({exc}) — refuse to write a record nothing "
            f"validated, and say WHICH thing was missing (fail closed)",
            gate=GATE_VALIDATOR_UNAVAILABLE) from exc

    declared = record.get("schema")
    filename = dict((v, f) for v, f in NODE_SCHEMA_VERSIONS).get(declared)
    if filename is None:
        raise ProviderNodeRegistrationRefused(
            f"node record declares schema {declared!r}, which is not one of the node schema "
            f"versions this build consults ({', '.join(v for v, _ in NODE_SCHEMA_VERSIONS)}) — "
            f"refuse to write a record no version validates (fail closed)", gate=GATE_RECORD_INVALID)
    try:
        schema = json.loads(node_schema_path(filename).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderNodeRegistrationRefused(
            f"node schema {declared} could not be read ({type(exc).__name__}) — an unreadable "
            f"schema refuses the record rather than skipping the check (fail closed)",
            gate=GATE_RECORD_INVALID) from exc
    validator = jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ProviderNodeRegistrationRefused(
            f"node record is not valid against {declared}: "
            f"{'/'.join(str(p) for p in first.path) or '<root>'}: {first.message}",
            gate=GATE_RECORD_INVALID)
    return str(declared)


@dataclass(frozen=True)
class ProviderNodeRegistration:
    """What a successful registration leaves behind — the auditable facts, measured."""

    node_key: str               # the registry's key (`probe-grok`), NOT the record's uuid
    incarnation: int
    adapter: str
    adapter_schema_version: str | None   # which version ADMITTED the adapter (registry provenance)
    validated_against: str               # which version the record VALIDATED against
    record: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"node_key": self.node_key, "incarnation": self.incarnation,
                "adapter": self.adapter, "adapter_schema_version": self.adapter_schema_version,
                "validated_against": self.validated_against, "node_id": self.record.get("node_id"),
                "schema": self.record.get("schema")}


class ProviderNodeRegistrar:
    """One `NodeRegistry` over one append-only log — the durable node history for this host."""

    def __init__(self, log_path: str | Path, *, log: AppendOnlyEventLog | None = None) -> None:
        # LAZY on purpose. `AppendOnlyEventLog.__init__` creates its directory and opens the file,
        # so constructing a registrar eagerly wrote an empty `node_events.jsonl` into the
        # OPERATOR's durable store for every probe that was refused at gate 1 — and for every test
        # that merely walked the product call site. A log file is created when a node is actually
        # registered, and never as a side effect of preparing to ask.
        self._log_path = Path(log_path) if log is None else log.path
        self._log = log
        self._registry: NodeRegistry | None = None if log is None else NodeRegistry(log)
        self._lock_fd: int | None = None
        self._closed = False
        #: An injected log is the caller's to own (the tests', and only the tests'): this registrar
        #: neither locks nor closes what it did not open.
        self._owns_log = log is None

    @property
    def registry(self) -> NodeRegistry:
        # ONE log object behind ONE registry, opened once and held EXCLUSIVELY. Two registries over
        # one file would each hold their own in-memory view — the duplicate check would pass twice
        # — and, worse, each caches `prev_hash` at open time, so two PROCESSES appending would
        # write duplicate `seq` values and break the chain permanently. Since `AppendOnlyEventLog`
        # refuses to open a corrupt log and a failed registration refuses the session, that would
        # wedge the whole governed-probe path with no repair an append-only log permits
        # (spec-audit MEDIUM-5). So the log is locked across this registrar's life.
        if self._closed:
            raise ProviderNodeRegistrationRefused(
                f"this registrar over {self._log_path} has been closed — refuse to reopen the log "
                f"on a closed object. With an INJECTED log the reopen took no lock, so two "
                f"AppendOnlyEventLog objects would each cache `prev_hash` over one file: duplicate "
                f"`seq` values and a permanently broken chain, which is the exact failure the lock "
                f"exists to prevent (spec-audit MINOR-10)", gate=GATE_LOG_LOCKED)
        if self._registry is None:
            self._acquire_lock()
            try:
                self._log = AppendOnlyEventLog(self._log_path)
            except ValueError as exc:
                # W-66: a corrupt durable history escaped as a bare ValueError, which the
                # emitter's routing table reports as gate `argv_builder`. Corruption of the
                # append-only log is an INTEGRITY fault; refuse under this registrar's own
                # vocabulary so the ticket names the true gate.
                self._release_lock()
                raise ProviderNodeRegistrationRefused(
                    f"the durable node event log at {self._log_path} is corrupt and refuses to "
                    f"open - an integrity fault of the hash-chained history, not an argv fault "
                    f"({exc})", gate=GATE_LOG_CORRUPT) from exc
            except BaseException:
                self._release_lock()
                raise
            self._registry = NodeRegistry(self._log)
        return self._registry

    def _acquire_lock(self) -> None:
        """Take the node log's cross-process lock, reclaiming one whose holder is gone.

        Same shape as the durable lease ledger's (`terminal_lease`), and for the same reason: a
        crash must not wedge the path forever, but a LIVE second holder must be refused rather than
        allowed to interleave appends."""
        if not self._owns_log or self._lock_fd is not None:
            return
        lock = self._log_path.with_suffix(self._log_path.suffix + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        # BOUNDED WAIT before refusing. Every one of these holders is a short-lived emitter (a
        # ticket, an attestation, a release), so the contended window is milliseconds — but with no
        # wait at all, two picker clicks in quick succession refused one fully-authorized pane with
        # "another process holds the node event log" (validator MEDIUM-3 / spec-audit MEDIUM-6).
        # Fail-closed is still where this ends: the wait is short and the refusal is unchanged.
        for attempt in (1, 2, *([3] * _LOCK_WAIT_ATTEMPTS)):
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise ProviderNodeRegistrationRefused(
                        f"the node event log's lock could not be taken ({type(exc).__name__}: "
                        f"{exc}) — fail closed", gate=GATE_LOG_LOCKED) from exc
                if attempt == 3:
                    time.sleep(_LOCK_WAIT_SECONDS)
                    continue
                if attempt == 1 and self._holder_is_gone(lock):
                    # A dead holder's lock is reclaimed, exactly as the lease ledger reaps a lease
                    # whose process no longer exists. A LIVE holder is refused below.
                    try:
                        lock.unlink()
                    except OSError:
                        pass
                    continue
                raise ProviderNodeRegistrationRefused(
                    f"another process holds the node event log {self._log_path} after waiting "
                    f"{_LOCK_WAIT_ATTEMPTS * _LOCK_WAIT_SECONDS:.1f}s — refuse to interleave "
                    f"appends on a hash-chained log (fail closed; the holder is "
                    f"{self._read_holder(lock) or 'unknown'}. If that pid is gone and this "
                    f"persists, the stale lock file beside the log is the thing to remove)",
                    gate=GATE_LOG_LOCKED) from exc
            os.write(fd, str(os.getpid()).encode("ascii"))
            self._lock_fd = fd
            return

    @staticmethod
    def _read_holder(lock: Path) -> str | None:
        try:
            return lock.read_text(encoding="ascii").strip() or None
        except OSError:
            return None

    @classmethod
    def _holder_is_gone(cls, lock: Path) -> bool:
        """True when the recorded holder pid is not a live process. An unreadable or malformed
        stamp is treated as LIVE (fail closed): an unknown holder is never assumed dead.

        Liveness comes from `terminal_lease.pid_is_alive` — the repo's one implementation of the
        question, which already carries the Windows rule (`os.kill(pid, 0)` there raises EINVAL,
        not ESRCH, for a pid that never existed) and the POSIX one. A second, home-grown copy is
        how the durable ledger's dead-holder reaping and this one come to disagree."""
        from node_runtime.supervisor.terminal_lease import pid_is_alive  # noqa: PLC0415

        raw = cls._read_holder(lock)
        if raw is None or not raw.isdigit():
            return False
        try:
            return not pid_is_alive(int(raw))
        except (ValueError, OverflowError, OSError):
            return False

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            os.close(self._lock_fd)
        finally:
            self._lock_fd = None
            try:
                self._log_path.with_suffix(self._log_path.suffix + ".lock").unlink()
            except OSError:
                pass

    def close(self) -> None:
        """Release the log and its lock. Called on every exit path of a governed session, so a
        long-lived process (the shell) neither leaks a file handle per probe nor holds the node log
        against the next one."""
        if self._log is not None and self._owns_log:
            try:
                self._log.close()
            except Exception:      # noqa: BLE001 — a close that fails must still free the lock
                pass
        self._registry = None
        self._log = None
        self._closed = True
        self._release_lock()

    @property
    def log_path(self) -> Path:
        """The log's path, readable WITHOUT opening it — so a caller can report where a record
        would go without creating the file by asking."""
        return self._log_path

    def register_session(self, session: Any) -> ProviderNodeRegistration:
        """Register `session` as a Sovereign node. Raises rather than returning a failure — an
        unregistered session must not proceed as if it were governed.

        There is no `validate=False`, no `force`, and no opt-out: every path through this method
        builds the record and validates it against the real schema before the registry is asked.
        The bypass parameter the 18B fence first shipped with had no caller and was deleted for
        exactly this reason (spec-audit MINOR-5) — a vocabulary with an override is a vocabulary
        with two vocabularies.

        `session` must be the supervisor's own `GovernedProbeSession`. The first cut took any
        object with the right attribute names, which made the I-C1 attestation this record carries
        (`spawned_by_supervisor: true`) something any in-process caller could assert by writing a
        namespace with `supervised=True` — the claim was the caller's, published as the
        supervisor's (spec-audit MEDIUM-3). It must also carry the terminal it was counted under:
        a governed session without a lease id is not one this registrar can vouch for."""
        from node_runtime.supervisor.provider_probe_session import (  # noqa: PLC0415 — cycle-safe
            GovernedProbeSession,
        )

        if not isinstance(session, GovernedProbeSession):
            raise ProviderNodeRegistrationRefused(
                f"{type(session).__name__} is not a GovernedProbeSession — a node record attests "
                f"I-C1 for a session the supervisor itself opened, and that attestation is not "
                f"something a caller may assert by duck-typing (fail closed)",
                gate=GATE_UNGOVERNED_SESSION)
        if not (str(getattr(session, "lease_id", "") or "").strip()
                and str(getattr(session, "subscription_ref", "") or "").strip()):
            raise ProviderNodeRegistrationRefused(
                f"the session for {session.provider!r} carries no I-X3 terminal (lease "
                f"{session.lease_id!r} on {session.subscription_ref!r}) — a frontier node record "
                f"names the subscription it was counted against (fail closed)",
                gate=GATE_UNGOVERNED_SESSION)
        if getattr(session, "supervised", False) is not True:
            raise ProviderNodeRegistrationRefused(
                f"session for {getattr(session, 'provider', None)!r} does not claim supervision — "
                f"a node record asserts the process was spawned by the Node Runtime supervisor "
                f"(I-C1, invariant 2), and this registrar reads that claim rather than making it",
                gate=GATE_UNSUPERVISED_SESSION)
        # The provider check runs BEFORE the registry is opened, so a refusal for an id this module
        # does not govern leaves no file behind in the operator's store. The schema validation
        # below cannot: the record's uuid is derived from the incarnation, and the incarnation is a
        # question only the log can answer — so a record that is well-formed here and invalid there
        # would leave an empty log. Recorded rather than hidden; the two refusals that matter
        # (unknown adapter, unsupervised session) both land above this line.
        provider_facts(session.provider)
        node_key = str(session.node_id)
        incarnation = self._next_incarnation(node_key)
        record = build_provider_node_record(session, incarnation=incarnation)
        validated = validate_node_record(record)
        self.registry.register(
            node_key, record["class"], session.provider, spawned_by_supervisor=True,
            incarnation=incarnation,
            session_id=getattr(session, "session_id", None),
            subscription_ref=getattr(session, "subscription_ref", None),
            lease_id=getattr(session, "lease_id", None),
            permission_profile_id=getattr(session, "permission_profile_id", None),
            workspace=str(getattr(session, "workspace", "") or ""),
            node_record=record,
        )
        # WHICH version admitted the adapter. `register()` writes the same value onto the
        # append-only spawn event; `test_the_reported_provenance_is_the_one_on_the_log` asserts the
        # two agree, because a second derivation that nothing compares is a second derivation that
        # drifts. It is read here (rather than off the log) so a caller gets the fact without
        # re-reading a file that will only grow.
        admitted = adapter_version_map().get(session.provider)
        return ProviderNodeRegistration(
            node_key=node_key, incarnation=incarnation, adapter=session.provider,
            adapter_schema_version=admitted, validated_against=validated, record=record)

    def register_pane_session(self, session: Any, *, session_id: str,
                              lease_id: str = "",
                              residency: Any = None) -> ProviderNodeRegistration:
        """Register a governed OP-12 worker PANE as a Sovereign node. Raises rather than returning
        a failure — an unregistered session must not proceed as if it were governed.

        The same three fences as `register_session`, read against the pane's own shape:

          1. `session` must be the supervisor's own `WorkerPaneSession` — the type the authorizer
             returns and nothing else. The I-C1 attestation this record carries is the supervisor's;
             a caller must not be able to assert it by writing a namespace with the right attribute
             names (18D spec-audit MEDIUM-3, the same fence one path over);
          2. it must carry the terminal it was counted under — `subscription_governed` AND a lease
             id AND a session key. A frontier node record NAMES the subscription it was counted
             against, and there is no honest record for a pane whose count nobody can find;
          3. its chrome must claim governance. `governed` is the authorizer's own statement about
             the session; this registrar reads that claim, it never makes it.

        Note what is NOT checked here and cannot be: whether the ConPTY has actually been spawned.
        At ticket time it has not been — which is why the record is written in `SPAWNING` and why
        `attest_spawned` exists as a separate act with a separate fact (a live pid) behind it.
        """
        from node_runtime.supervisor.worker_pane_spawn import (  # noqa: PLC0415 — cycle-safe
            WorkerPaneSession,
        )

        if not isinstance(session, WorkerPaneSession):
            raise ProviderNodeRegistrationRefused(
                f"{type(session).__name__} is not a WorkerPaneSession — a node record attests I-C1 "
                f"for a pane the supervisor's own authorizer opened, and that attestation is not "
                f"something a caller may assert by duck-typing (fail closed)",
                gate=GATE_UNGOVERNED_SESSION)
        # The session KEY is not checked here: an absent one is a record-shape fault and is refused
        # by `build_pane_node_record` with `GATE_RECORD_INVALID`, so the two refusals stay
        # distinguishable ("you hold no terminal" and "this record cannot be traced" are different
        # facts, and a receipt asserting one must not be satisfiable by the other).
        # EPC-02 / U313(A). Fence 2 asks the same question of every pane - "name the counted
        # resource you were admitted under" - and takes the honest answer for the pane's kind.
        # A local pane has no subscription to name, so it names its VRAM residency reservation
        # instead. Frontier panes are untouched: same fence, same wording, same gate.
        residency_record = None
        if getattr(getattr(session, "chrome", None), "adapter", None) in RESIDENCY_GOVERNED_ADAPTERS:
            # The AUTHORIZATION already carries it. `WorkerPaneSession.residency_decision` is
            # documented as "the residency decision for a local model (None for frontier)", so
            # the fence reads the authorizer's own record rather than a caller's copy - the
            # same reason `permission_profile_id` lives on the session and not the selection.
            # An explicit argument still wins, for a caller that has a fresher decision.
            residency_record = _require_residency(
                residency if residency is not None else getattr(session, "residency_decision", None),
                session_id=session_id,
                # `model_slug` is the chrome's field name - the argv slug the pane actually
                # runs. Reading a non-existent `model` returned None, which silently
                # disabled the model-match check: a reservation for ANOTHER model would
                # have passed. Caught by the end-to-end demonstration, not by the units.
                model=getattr(getattr(session, "chrome", None), "model_slug", None))
        elif not (getattr(session, "subscription_governed", False) is True
                  and str(lease_id or "").strip()):
            raise ProviderNodeRegistrationRefused(
                f"the worker pane session carries no I-X3 terminal (lease {lease_id!r}, session "
                f"{session_id!r}, subscription_governed="
                f"{getattr(session, 'subscription_governed', None)!r}) — a frontier node record "
                f"names the subscription it was counted against (fail closed)",
                gate=GATE_UNGOVERNED_SESSION)
        if getattr(session.chrome, "governed", False) is not True:
            raise ProviderNodeRegistrationRefused(
                f"the pane authorization for {getattr(session.chrome, 'adapter', None)!r} does not "
                f"claim governance — a node record asserts the process is born through the Node "
                f"Runtime's supervised spawn (I-C1, invariant 2), and this registrar reads that "
                f"claim rather than making it", gate=GATE_UNSUPERVISED_SESSION)
        # BEFORE the log is opened, so a refusal for an id this module does not govern (every
        # non-OP-12 pane) — or an authorization whose record could not be traced back to its
        # session — leaves no file behind in the operator's store. The shape check used to run
        # AFTER `_next_incarnation`, which opens (and therefore creates) the log, so a malformed
        # authorization wrote an empty `node_events.jsonl` into the durable store on its way to
        # being refused (validator MINOR-5 — the same eager-creation defect 18D `.close` fixed one
        # layer up). `incarnation=1` here is a shape probe: the uuid it derives is discarded and
        # the real record is built with the real incarnation below.
        provider = session.chrome.adapter
        provider_facts(provider)
        build_pane_node_record(session, session_id=session_id, incarnation=1)
        node_key = str(session.chrome.node_id)
        incarnation = self._next_incarnation(node_key)
        self._reap_stale_incarnation(node_key, incarnation)
        record = build_pane_node_record(session, session_id=session_id, incarnation=incarnation)
        validated = validate_node_record(record)
        self.registry.register(
            node_key, record["class"], provider, spawned_by_supervisor=True,
            incarnation=incarnation, session_id=str(session_id), subscription_ref=(
                (session.chrome.subscription or {}).get("ref")),
            lease_id=str(lease_id),
            permission_profile_id=session.permission_profile_id,
            workspace=str((session.launch or {}).get("cwd") or ""),
            node_record=record,
        )
        return ProviderNodeRegistration(
            node_key=node_key, incarnation=incarnation, adapter=provider,
            adapter_schema_version=adapter_version_map().get(provider),
            validated_against=validated, record=record)

    def adopt_from_log(self, node_key: str,
                       incarnation: int | None = None) -> ProviderNodeRegistration | None:
        """Recover ONE incarnation of `node_key` from the durable log into this registrar's view
        (the latest by default), or `None` when the log carries no spawn for it.

        The pane lifecycle spans three separate `py -3.12` processes (ticket, spawn attestation,
        release), so every step after the first starts with an empty registry over a log that
        already knows everything. This replays exactly the rows for one node — the `spawn` that
        created it and every `transition`/`exit` after it — and hands the reconstructed record to
        `NodeRegistry.rehydrate`, which restores the cache without writing anything.

        Fail-closed in every direction, not by omission: a log that cannot be read, a LINE that
        cannot be parsed, a state string no `NodeState` admits, a spawn row that carries no
        `node_record`, or a record whose adapter no schema version admits all yield `None` (or a
        refusal from `rehydrate`) — never a fabricated node and never a state reconstructed by
        skipping the rows that could not be read (spec-audit MINOR-9). An unparseable line is a
        refusal rather than a skip because the decision made downstream — attest, or close — is
        made against the state this replay produces.

        Already adopted in THIS registrar's view ⇒ that view is returned as-is: `rehydrate` refuses
        a duplicate key by design, and re-reading is not a second act.
        """
        latest: dict[str, Any] | None = None
        state = NodeState.SPAWNING
        exited = False
        try:
            with self._log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        return None
                    if row.get("node_id") != node_key:
                        continue
                    if incarnation is not None and row.get("incarnation") != incarnation:
                        continue
                    kind = row.get("kind")
                    # `AppendOnlyEventLog.append` nests everything but seq/ts/kind/node_id/
                    # incarnation/hashes under `data` — read from there, never from the row root
                    # (a `row.get("node_record")` that is always None reads as "no record on the
                    # log" and would silently re-register every pane as a new incarnation).
                    data = row.get("data") if isinstance(row.get("data"), dict) else {}
                    if kind == "spawn":
                        latest = dict(data, incarnation=row.get("incarnation"))
                        state, exited = NodeState.SPAWNING, False
                    elif latest is not None and row.get("incarnation") == latest.get("incarnation"):
                        if kind == "transition":
                            try:
                                state = NodeState(str(data.get("to")))
                            except ValueError:
                                return None
                        elif kind == "exit":
                            exited = True
        except OSError:
            return None
        if latest is None:
            return None
        record = latest.get("node_record")
        if not isinstance(record, dict):
            return None
        found = int(latest.get("incarnation") or 1)
        node = NodeRecord(node_id=node_key, incarnation=found,
                          node_class=str(latest.get("node_class") or record.get("class") or ""),
                          adapter=str(latest.get("adapter") or record.get("adapter") or ""),
                          state=state, meta={"node_record": record, "exited": exited})
        registration = ProviderNodeRegistration(
            node_key=node_key, incarnation=found, adapter=node.adapter,
            adapter_schema_version=adapter_version_map().get(node.adapter),
            validated_against=str(record.get("schema") or ""), record=record)
        try:
            self.registry.rehydrate(node)
        except RegistrationRefused:
            # Already in this registrar's view (a second adopt in one process) — `rehydrate`
            # refuses a duplicate key by design, and re-reading the same record is not a second
            # act. Any OTHER refusal (an adapter no version admits, a log with no spawn row) is a
            # fence firing and must not be swallowed: re-raise unless the key is genuinely ours.
            try:
                self.registry.get(node_key, found)
            except KeyError:
                raise
        return registration

    def _adopt_for_session(self, node_key: str, session_id: str) -> ProviderNodeRegistration:
        """The record for `node_key` that belongs to `session_id`, or a refusal.

        THE fence both post-ticket acts rest on. The first cut of `attest_spawned` and
        `close_session_record` took only the node KEY (`worker-<paneId>`) and acted on "the latest
        spawn row for it" — and BOTH reviewers found the same consequence independently: a pane id
        is reused across sessions, so a stale record left open by a crashed shell could be attested
        READY with an unrelated process's pid, and a late release for session A could write
        `TERMINATED` against session B's still-live record. On an append-only log neither row can
        ever be corrected (invariant 12).

        The binding already existed and was never checked: the record's `node_id` uuid is derived
        from `f"{node_key}#{session_id}"` and the incarnation, so recomputing it is an exact,
        cheap identity test. A record that is not this session's is refused rather than acted on.
        """
        sid = str(session_id or "").strip()
        if not sid:
            raise ProviderNodeRegistrationRefused(
                f"a post-ticket act on node {node_key!r} needs the SESSION it belongs to — a pane "
                f"id is reused across sessions, and acting on 'the latest record for this pane' is "
                f"how a stale record gets a live session's pid (fail closed)",
                gate=GATE_RECORD_INVALID)
        registration = self.adopt_from_log(node_key)
        if registration is None:
            raise ProviderNodeRegistrationRefused(
                f"no registered node {node_key} on {self._log_path} — refuse to act on a record "
                f"that was never written", gate=GATE_UNKNOWN_NODE)
        expected = node_record_uuid(f"{node_key}#{sid}", registration.incarnation)
        if registration.record.get("node_id") != expected:
            raise ProviderNodeRegistrationRefused(
                f"the latest record for {node_key} (#{registration.incarnation}) does not belong "
                f"to session {sid!r} — refuse to write onto another session's record on an "
                f"append-only log (invariant 12)", gate=GATE_UNKNOWN_NODE)
        return registration

    def attest_spawned(self, node_key: str, *, session_id: str, pid: int) -> dict[str, Any]:
        """The pane's ConPTY is alive under a supervised pid: move its record `SPAWNING` → `READY`.

        This is a SEPARATE act from registration on purpose. The ticket cannot know whether the
        shell managed to spawn anything, so a record that claimed `READY` at ticket time would be
        asserting the existence of a process nobody had seen.

        The pid is what makes this step different from the last one, so it is CHECKED rather than
        recorded: it must be a positive integer AND a live process on this host, through
        `terminal_lease.pid_is_alive` — the repo's one implementation of that question. The first
        cut checked only `pid > 0` while its own docstring said "refuse to record READY for a
        process nobody observed", i.e. the stronger claim had the weaker fence (spec-audit
        MAJOR-1), and the same module's `register_pane_session` refuses a duck-typed session two
        methods up for exactly that reason.

        HONEST LIMIT, recorded rather than implied: liveness is all this can check. Nothing here
        proves the pid is the pane's own child, or a descendant of the shell — that would need the
        job-object handoff U25 still owes. What is excluded is a fabricated or already-dead pid,
        not a live-but-wrong one.
        """
        from node_runtime.supervisor.terminal_lease import pid_is_alive  # noqa: PLC0415

        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise ProviderNodeRegistrationRefused(
                f"a spawn attestation needs the supervised session's live pid; got {pid!r} — "
                f"refuse to record READY for a process nobody observed (fail closed)",
                gate=GATE_RECORD_INVALID)
        try:
            alive = pid_is_alive(pid)
        except (ValueError, OverflowError, OSError):
            alive = False
        if not alive:
            raise ProviderNodeRegistrationRefused(
                f"pid {pid} is not a live process on this host — refuse to record READY for a "
                f"process nobody observed (fail closed)", gate=GATE_RECORD_INVALID)
        registration = self._adopt_for_session(node_key, session_id)
        record = self.registry.get(node_key, registration.incarnation)
        if record.state is not NodeState.SPAWNING:
            raise ProviderNodeRegistrationRefused(
                f"node {node_key}#{registration.incarnation} is {record.state.value}, not SPAWNING "
                f"— a spawn is attested once, at the moment the process appears",
                gate=GATE_RECORD_INVALID)
        self.registry.transition(
            node_key, NodeState.READY, incarnation=registration.incarnation,
            reason="supervised ConPTY spawn observed by the shell", pid=pid)
        record.pid = pid
        return {"attested": True, "node_key": node_key, "incarnation": registration.incarnation,
                "pid": pid, "state": NodeState.READY.value, "log_path": str(self._log_path),
                "adapter": registration.adapter, "node_id": registration.record.get("node_id")}

    def close_session_record(self, node_key: str, *, session_id: str, exit_code: int | None,
                             expected: bool) -> dict[str, Any]:
        """Close ONE session's node record on the same append-only log (D-LOOP-1).

        Bound to the session through `_adopt_for_session` — see there for why "the latest record
        for this pane" is not good enough.

        Idempotent by REPORT, not by silence: a record already TERMINATED yields `closed:false`
        with the reason rather than a second exit row, because an append-only log cannot un-write a
        duplicate. A node this log never carried, and a record belonging to a different session,
        both yield `closed:false` too — the release path runs for every pane, including local ones
        and the OP-6 providers' panes, which have no record by design.
        """
        try:
            registration = self._adopt_for_session(node_key, session_id)
        except ProviderNodeRegistrationRefused as exc:
            return {"closed": False, "node_key": node_key, "incarnation": None, "state": None,
                    "log_path": str(self._log_path), "gate": exc.gate, "reason": str(exc)}
        record = self.registry.get(node_key, registration.incarnation)
        if record.state is NodeState.TERMINATED or record.meta.get("exited") is True:
            return {"closed": False, "node_key": node_key, "incarnation": registration.incarnation,
                    "state": NodeState.TERMINATED.value, "log_path": str(self._log_path),
                    "reason": f"node {node_key}#{registration.incarnation} is already closed"}
        self.registry.record_exit(node_key, registration.incarnation, exit_code, expected=expected)
        return {"closed": True, "node_key": node_key, "incarnation": registration.incarnation,
                "state": NodeState.TERMINATED.value, "exit_code": exit_code, "expected": expected,
                "log_path": str(self._log_path),
                "adapter": registration.adapter, "reason": None}

    def record_exit(self, registration: ProviderNodeRegistration, *, exit_code: int | None,
                    expected: bool) -> None:
        """Close the record on the same append-only log (D-LOOP-1). A node the registrar never
        registered is refused rather than silently created by a KeyError somewhere downstream."""
        try:
            self.registry.get(registration.node_key, registration.incarnation)
        except KeyError as exc:
            raise ProviderNodeRegistrationRefused(
                f"no registered node {registration.node_key}#{registration.incarnation} to close "
                f"— refuse to write an exit for a record that was never written",
                gate=GATE_UNKNOWN_NODE) from exc
        self.registry.record_exit(registration.node_key, registration.incarnation, exit_code,
                                   expected=expected)

    def _reap_stale_incarnation(self, node_key: str, next_incarnation: int) -> None:
        """Close the PREVIOUS incarnation of this pane node if it was left open by a dead process.

        The durable lease ledger reaps a lease whose holder is gone; the node log had no equivalent,
        so a shell that died between spawn and release left a record READY forever with a dead pid,
        and `_next_incarnation` simply counted past it (validator MEDIUM-2 / spec-audit MEDIUM-4 —
        the D-LOOP-1 leak this module's own docstring says it closes, arriving by a crash).

        The rule is the ledger's rule and no wider: reap only when the recorded pid is NOT a live
        process. A prior incarnation whose pid IS alive REFUSES the new registration — two live
        sessions under one pane node is a state nobody should be able to write, and refusing is the
        fail-closed direction. A record with no pid at all (never attested — the shell died before
        the spawn) is closed too: nothing was ever running under it.
        """
        from node_runtime.supervisor.terminal_lease import pid_is_alive  # noqa: PLC0415

        prior = next_incarnation - 1
        if prior < 1:
            return
        state, exited, pid = self._replay_state(node_key, prior)
        if state is None or exited or state is NodeState.TERMINATED:
            return
        if pid is not None:
            try:
                if pid_is_alive(pid):
                    raise ProviderNodeRegistrationRefused(
                        f"node {node_key}#{prior} is still {state.value} under LIVE pid {pid} — "
                        f"refuse to register a second live incarnation of one pane node "
                        f"(fail closed; close that session first)", gate=GATE_UNGOVERNED_SESSION)
            except (ValueError, OverflowError, OSError):
                return          # cannot answer ⇒ do not reap and do not refuse (fail quiet, U25)
        if self.adopt_from_log(node_key, incarnation=prior) is None:
            return              # the log cannot produce the record ⇒ nothing to close, honestly
        self.registry.record_exit(node_key, prior, None, expected=False)

    def _replay_state(self, node_key: str, incarnation: int,
                      ) -> tuple[NodeState | None, bool, int | None]:
        """`(state, exited, pid)` for one incarnation, read from the log. `(None, …)` ⇒ no such row."""
        state: NodeState | None = None
        exited = False
        pid: int | None = None
        try:
            with self._log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        return (None, False, None)
                    if row.get("node_id") != node_key or row.get("incarnation") != incarnation:
                        continue
                    data = row.get("data") if isinstance(row.get("data"), dict) else {}
                    if row.get("kind") == "spawn":
                        state, exited, pid = NodeState.SPAWNING, False, None
                    elif row.get("kind") == "transition" and state is not None:
                        try:
                            state = NodeState(str(data.get("to")))
                        except ValueError:
                            return (None, False, None)
                        if isinstance(data.get("pid"), int):
                            pid = data["pid"]
                    elif row.get("kind") == "exit" and state is not None:
                        exited = True
        except OSError:
            return (None, False, None)
        return (state, exited, pid)

    def _next_incarnation(self, node_key: str) -> int:
        """The next incarnation for `node_key`, read from the LOG and not only from memory.

        `NodeRegistry` starts with an empty dict and never replays its log, so a fresh process
        opening the DURABLE log computed 1 every time — and the node key is stable (`probe-grok`),
        so every probe run on the operator's host appended another incarnation-1 `spawn` row to an
        append-only file, with the in-memory duplicate guard unable to see it. The registry's own
        convention is the opposite ("a restart registers the next incarnation under the same
        node_id"), and this comment used to claim "the incarnation is a question only the log can
        answer" while asking memory (spec-audit MEDIUM-2). Now it asks the log.
        """
        highest = 0
        for record in self.registry.all_records():
            if record.node_id == node_key:
                highest = max(highest, record.incarnation)
        try:
            with self._log_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("kind") == "spawn" and row.get("node_id") == node_key:
                        highest = max(highest, int(row.get("incarnation") or 0))
        except (OSError, ValueError, TypeError):
            # An unreadable log cannot LOWER the number: the in-memory maximum still stands, and
            # the registry's own duplicate guard is the backstop. (A log that cannot be parsed at
            # all never got this far — `AppendOnlyEventLog` refuses to open a corrupt one.)
            pass
        return highest + 1


def default_provider_node_registrar(repo_root: str | Path) -> ProviderNodeRegistrar:
    """The registrar the PRODUCT path uses: the durable per-host log under `.sovereign_store/`."""
    return ProviderNodeRegistrar(default_node_event_log_path(repo_root))


__all__ = [
    "GATE_LOG_LOCKED", "GATE_RECORD_INVALID", "GATE_UNGOVERNED_SESSION", "GATE_UNKNOWN_NODE",
    "GATE_UNSUPERVISED_SESSION", "GATE_VALIDATOR_UNAVAILABLE", "GATE_LOG_CORRUPT",
    "NODE_EVENT_LOG_RELPATH", "RECORD_SCHEMA_VERSION", "ProviderNodeRegistrar",
    "ProviderNodeRegistration", "ProviderNodeRegistrationRefused", "build_pane_node_record",
    "build_provider_node_record",
    "default_node_event_log_path", "default_provider_node_registrar", "node_record_uuid",
    "provider_facts", "validate_node_record",
]
