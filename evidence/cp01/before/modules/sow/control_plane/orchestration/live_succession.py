"""Phase 15D `.succession` — LIVE conductor succession over a governed run.

Directive §11 track 15D, the fourth sub-step: **kill the conductor mid-run, resume on a DIFFERENT
backend, prove ZERO LOSS, then restore the operator selection.** Invariant 28 ("conductor
succession works: serialize to MCP, Resume→Select") is the claim under test; invariant 5 ("project
state lives outside model context") is *why* it can hold at all.

WHAT THIS MODULE DOES NOT DO: it does not reimplement succession. `SuccessionManager`
(`control_plane/recovery/succession.py`, gated at Phase 11) owns serialization, the §19.1 staleness
checklist and the I-X3 handoff; `LiveGovernedFlow` (gated at `.flow`) owns the governed loop;
`control_plane/conductor/selection.py` (gated at `.selection`) owns the selection records. This
module composes those three across one interrupted run and decides — fail closed — whether the
resulting evidence supports the claim "the conductor was replaced and nothing was lost".

THE KILL IS AT A GOVERNED BOUNDARY, AND WHAT IT REPLACES IS THE CONDUCTOR — NOT THE RUN. The
predecessor is interrupted BETWEEN scheduling waves, with the completed waves' artifacts already
gated and promoted in MCP: its adapter is closed (releasing its subscription terminal), its MCP
client is closed, and the successor is a separately-constructed adapter, on its own MCP session and
node_id, that reloads all 12 conductor files FROM MCP.

Be precise about the scope of that claim, because an earlier draft of this module overstated it.
What is replaced is the CONDUCTOR (adapter + backend + MCP session). What deliberately SURVIVES
in-process is the orchestration harness: the `LiveGovernedFlow`, its `TaskGraph`, `Scheduler`,
`CapabilityRegistry`, the worker adapters and the `_RunState`. That is the design — a successor
takes over the SAME governed run (invariant 28 / I-CN1) rather than starting a new one — but it
means this unit does NOT demonstrate that conductor-side orchestration state is MCP-resident and
rebuildable. See U48.

HONESTY RULES (directive §6/§10.4), each pinned by a test:
  - `zero_loss.ok` is UNREACHABLE with an empty pre-kill accepted set, AND the durable claim
    additionally requires the accepted set to have GROWN across the succession (`work_advanced`) —
    otherwise a "succession" that resumed nothing would earn the claim by preserving the 12
    read-only conductor files that bootstrap publishes as ACCEPTED. See U49.
  - artifacts are compared by CONTENT HASH read back from MCP, not by entry id: an id that
    survives while its bytes changed is loss, not preservation. This is the LOAD-BEARING half of
    the comparison. The `task_states` half is weaker by construction and is labelled as such
    (U48): both sides read the surviving in-process graph, so it cannot detect graph loss.
  - "resume on a DIFFERENT backend" is a LABEL-DIFFERENCE REFUSAL, not structural proof. It
    catches the degenerate identical-configuration case and nothing more. `capability().adapter`
    is hard-coded to `"conductor_fable5"` for every `ConductorAdapter`, so it never discriminates;
    the discrimination rests entirely on `model_name`, which this module ASSIGNS onto the backend
    object. Two identical `MockReasoningBackend` instances can satisfy it. See U50.
  - the kill is REFUSED, not merely recorded: if the predecessor is still `is_active` after
    `close()`, the succession is abandoned rather than reported. A recorded-but-unchecked death
    field is not a guard.
  - the §19.1 staleness checklist GATES the successor: a failed checklist stops the run before the
    successor assigns any work.
  - leg vocabulary is IMPORTED from `live_flow`/`live_debate`, never redeclared, and a `live` leg
    with no verification record is unrepresentable. The classifier used here is the HARDENED one
    from `live_debate` (exact type + freshness against a bind-time call snapshot); `live_flow`'s
    weaker `_leg_for_backend` is U45, unified at `.gate`.
  - the run-level spend leg merges UPWARD across both conductors: a succession must not let the
    predecessor's spend disappear from the record.

MOCK-FIRST, AND THIS UNIT HAS NO LIVE PATH AT ALL. Nothing here spawns a provider CLI, and unlike
`live_flow.attempt_live_flow` / `live_debate.attempt_live_debate` there is no `attempt_live_*`
entry point, no `LiveAuthorization` check and no supervised live spawn. A live succession is OWED
(U51); it is not merely un-run. The public `mock_*_handle` helpers hard-code `leg="mock"`, so they
must NOT be handed a real vendor backend — that would under-report a real subscription spend.

STATED LIMITS, recorded in docs/registers/UNRESOLVED_ISSUE_REGISTER.md (U46–U53).
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

from adapters.base.contract import AdapterContext
from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor.adapter import ConductorAdapter
from adapters.frontier.claude_code import bind_calls_snapshot, calls_or_none
from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    ConductorSelectionError,
    restore_operator_selection,
    succession_selection,
)
from control_plane.gates.criteria import GateContext
from control_plane.gates.engine import GateEngine, define_gate
from control_plane.orchestration.live_flow import (
    ATTEMPTED_LEG,
    VALID_LEGS,
    ConductorHandle,
    LiveGovernedFlow,
    mock_conductor_handle,
)
# The HARDENED leg classifier (exact type + freshness against a bind-time call snapshot). Imported
# rather than re-implemented so this unit cannot introduce a third, weaker leg vocabulary; see the
# module header on U45.
from control_plane.orchestration.live_debate import debater_leg as backend_leg
from control_plane.orchestration.live_debate import verification_for
from control_plane.recovery.succession import ConductorState, SuccessionManager
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer

SUCCESSION_REPORT_SCHEMA = "succession_report@1.0"

#: `succession_report@1.0` has no file in `schemas/` (frozen @1.0 at 12 files) — the same standing
#: gap `acceptance_packet@1.0` and `debate_report@1.0` carry. U40 enumerated exactly those two, so
#: adding a third envelope required AMENDING it (see the U40 amendment, 2026-07-20) rather than
#: assuming coverage. The key set is pinned HERE and asserted by test, so the artifact's shape is
#: still a checked contract.
SUCCESSION_REPORT_KEYS: tuple[str, ...] = (
    "schema", "ts", "objective", "predecessor", "successor", "restored_selection",
    "restored_selection_note", "staleness", "zero_loss", "handoff_order", "handoff_note",
    "run_spend_leg", "acceptance_packet", "operator_disposition",
)

#: `restored_selection` is the operator's SELECTION RECORD, restored — it is NOT a statement that a
#: conductor on that model is now running. Nothing is re-bound: the conductor executing at the end
#: of a succession is the SUCCESSOR. Without this note an operator reading the report sees
#: `{model: fable-5, adapter: claude_code}` and reasonably concludes a claude_code conductor
#: finished the run, in a run that may have spawned no vendor CLI at all (invariant 3, §6). See U52.
RESTORED_SELECTION_NOTE = (
    "the operator's SELECTION RECORD was restored; no conductor was re-bound to it. The conductor "
    "that executed the remainder of this run is the successor recorded above."
)

#: Gate promotion is not operator acceptance (invariant 1) — identical rule to the acceptance
#: packet's, and pinned for the same reason: an ACCEPTED succession report is a deterministic gate
#: verdict, never an operator sign-off on the succession.
OPERATOR_DISPOSITION_PENDING = "pending"

#: Spend rank. Higher = a stronger claim about having reached a real provider. Merging across the
#: two conductors takes the MAXIMUM: under-reporting spend is the dishonest direction (§6).
_LEG_RANK: dict[str, int] = {"skipped": 0, "mock": 1, ATTEMPTED_LEG: 2, "live": 3}

#: The succession report is gated as an `acceptance`-kind artifact. `gate@1.0` freezes `kind` to
#: {local, stage, plan, acceptance} and `VALID_KINDS` enforces it, so a new "succession" kind is
#: NOT invented for this unit — that would mean editing a frozen schema for convenience, and
#: "minimal necessary control, no invented governance layers" (invariant 30) points the same way.
#: The report is an operator-facing synthesized record, which is exactly what `acceptance` covers.
SUCCESSION_GATE_KIND = "acceptance"
SUCCESSION_GATE_CRITERIA = ["artifact_present", "structured_output_valid",
                            "artifact_content_addressed", "claims_cite_evidence",
                            "no_placeholders"]


#: Backend class names that spend a real subscription. Matched by NAME (not import) so this guard
#: costs no vendor import in a control-plane module (the U36 shape), and so it also catches a
#: renamed re-export. It is a guard against ACCIDENTAL misuse of the mock helpers, not a security
#: boundary — the U43 falsification limit applies here exactly as it does in `live_debate`.
_VENDOR_BACKEND_NAMES = frozenset({"ClaudeCliBackend", "CodexCliBackend",
                                   "ClaudeCodeConductorBackend"})


class SuccessionError(RuntimeError):
    """A succession claim that cannot be backed by the evidence — refused, never emitted."""


# --------------------------------------------------------------------------------------
# 1. zero loss
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ZeroLossReport:
    ok: bool
    checks: dict[str, Any]

    def reasons(self) -> list[str]:
        """The named checks that FAILED. `False` only — the numeric/list diagnostics alongside them
        are evidence, not verdicts."""
        return [k for k, v in self.checks.items() if v is False]


def compare_zero_loss(before: Mapping[str, Any], after: Mapping[str, Any]) -> ZeroLossReport:
    """Compare the project as it stood at the KILL against the project after the successor
    finished. Both sides are read back from MCP (see `capture_project_snapshot`), never taken from
    a node's own report of what it produced (I-M1).

    `before`/`after` are `{"accepted": {entry_id: content_hash}, "task_states": {task_id: state}}`.

    A verdict of `ok=True` requires that the pre-kill accepted set was NON-EMPTY. This is the
    anti-vacuity rule: every preservation check below is a universally-quantified statement over
    that set, and all of them hold trivially when it is empty. A succession that happened before
    any artifact existed put nothing at risk and therefore proves nothing about loss.

    That rule alone is WEAK in practice, and saying so is the point of `work_advanced`: bootstrap
    publishes the 12 conductor files as ACCEPTED, so a real run's pre-kill set is never empty and
    the emptiness guard can only fire against a project this runner cannot construct. `ok` on its
    own is therefore satisfiable by preserving 12 read-only files. `work_advanced` records whether
    the accepted set actually GREW across the succession — i.e. whether the successor completed
    work the predecessor never saw — and the durable claim in `_publish_and_gate_report` requires
    BOTH. `ok` keeps its literal meaning (nothing was lost); `work_advanced` supplies the
    non-vacuity the emptiness guard cannot. See U49.

    NOTE on `task_states` (U48): both sides are read from the surviving in-process `TaskGraph`, so
    `tasks_preserved`/`done_tasks_preserved` compare that object against itself and cannot detect
    graph loss. They are retained as regression detectors for the successor's own wave execution,
    NOT as evidence of MCP-resident state. The load-bearing evidence is the content-hash half.
    """
    before_accepted = dict(before.get("accepted") or {})
    after_accepted = dict(after.get("accepted") or {})
    before_tasks = dict(before.get("task_states") or {})
    after_tasks = dict(after.get("task_states") or {})

    missing = sorted(e for e in before_accepted if e not in after_accepted)
    # same id, different bytes: an id-only comparison would call this "preserved"
    drifted = sorted(e for e, h in before_accepted.items()
                     if e in after_accepted and after_accepted[e] != h)
    missing_tasks = sorted(t for t in before_tasks if t not in after_tasks)
    # DONE is terminal in the state machine; a task leaving it after a succession would mean the
    # successor un-did completed, gated work
    regressed = sorted(t for t, s in before_tasks.items()
                       if s == "DONE" and after_tasks.get(t) != "DONE")

    at_risk = len(before_accepted) > 0
    checks: dict[str, Any] = {
        "pre_kill_accepted_count": len(before_accepted),
        "accepted_preserved": not missing,
        "missing_entries": missing,
        "no_content_drift": not drifted,
        "drifted_entries": drifted,
        # weaker by construction — see the U48 note in the docstring
        "tasks_preserved": not missing_tasks,
        "missing_tasks": missing_tasks,
        "done_tasks_preserved": not regressed,
        "regressed_tasks": regressed,
        "post_succession_accepted_count": len(after_accepted),
        # did the successor actually finish work the predecessor never saw? (U49)
        "work_advanced": len(after_accepted) > len(before_accepted),
    }
    if not at_risk:
        # A FAILURE marker only — present exactly when the comparison is vacuous, absent otherwise,
        # so it can never be read as an assertion that the run was risk-free.
        checks["nothing_at_risk"] = False

    ok = bool(at_risk and not missing and not drifted and not missing_tasks and not regressed)
    return ZeroLossReport(ok=ok, checks=checks)


def capture_project_snapshot(client: Any, task_states: Mapping[str, str]) -> dict[str, Any]:
    """Read every ACCEPTED entry back from MCP and hash its STORED BYTES.

    The hash is computed here from what MCP actually returns, not copied from the publishing
    node's `content_hash` claim — the whole point of the comparison is that it does not trust the
    author (I-M1).
    """
    accepted: dict[str, str] = {}
    for entry in client.call("read_status", status="ACCEPTED"):
        entry_id = entry.get("entry_id")
        if not entry_id:
            continue
        raw = client.call("get_content", entry_id=entry_id)
        content = base64.b64decode(raw["content_b64"])
        accepted[entry_id] = "sha256:" + hashlib.sha256(content).hexdigest()
    return {"accepted": accepted, "task_states": dict(task_states)}


# --------------------------------------------------------------------------------------
# 2. the report
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ConductorParty:
    """One side of the succession, as it can be PROVEN — not as it was configured."""

    role: str                                   # "predecessor" | "successor"
    node_id: str
    adapter: str                                # the adapter/capability label
    model_name: str                             # the bound backend's own model name
    leg: str                                    # live | attempted | mock | skipped
    selection_record: Mapping[str, Any] | None
    verification: Mapping[str, Any] | None = None   # only a real CLI checkpoint fills this
    calls_spent: int = 0

    def as_record(self) -> dict[str, Any]:
        return {"role": self.role, "node_id": self.node_id, "adapter": self.adapter,
                "model_name": self.model_name, "leg": self.leg,
                "selection": copy.deepcopy(dict(self.selection_record)) if self.selection_record else None,
                "verification": copy.deepcopy(dict(self.verification)) if self.verification else None,
                "calls_spent": int(self.calls_spent)}


def merge_spend_leg(*legs: str) -> str:
    """The run-level answer to "did this run reach a real provider", across BOTH conductors.

    Takes the STRONGEST claim, because the question is about the run as a whole: if the
    predecessor spent a live call before it was killed, that spend happened, and a successor's
    mock leg must not erase it. (The acceptance packet's own `legs` field stays bound to the
    conductor accompanying its selection record — see `LiveGovernedFlow.swap_conductor` — so this
    merged value is the field that reconciles the two.)
    """
    for leg in legs:
        if leg not in _LEG_RANK:
            raise SuccessionError(f"leg {leg!r} is not one of {VALID_LEGS}")
    if not legs:
        return "skipped"
    return max(legs, key=lambda leg: _LEG_RANK[leg])


def earns_zero_loss_claim(report: Mapping[str, Any]) -> bool:
    """Whether a succession report has EARNED the durable claim "the conductor was replaced mid-run
    with no loss of gated project state".

    A CONFIRMED zero-loss verdict is necessary but NOT sufficient. `ok` alone is satisfiable by a
    "succession" that resumed nothing, because bootstrap publishes the 12 read-only conductor files
    as ACCEPTED and preserving those is not an achievement (U49). The claim therefore also requires
    `work_advanced` — the successor finished work the predecessor never saw.

    A pure function, and public, so the rule can be pinned by test rather than only exercised
    through a full governed run (it was a surviving mutant when it lived inline).
    """
    zero_loss = report.get("zero_loss") or {}
    checks = zero_loss.get("checks") or {}
    return zero_loss.get("ok") is True and checks.get("work_advanced") is True


def build_succession_report(
    *,
    objective: str,
    predecessor: ConductorParty,
    successor: ConductorParty,
    restored_selection: Mapping[str, Any] | None,
    staleness: Mapping[str, Any],
    zero_loss: ZeroLossReport,
    handoff_order: Sequence[str],
    packet_entry: str | None,
    ts: str,
) -> dict[str, Any]:
    """Build the operator-facing succession record, deterministically and honestly.

    `ts` is INJECTED (no clock read) so the report is replayable. Every refusal below exists
    because the corresponding claim would otherwise be storable without evidence.
    """
    if not isinstance(objective, str) or not objective.strip():
        raise SuccessionError("succession report needs a real objective")
    if not isinstance(ts, str) or not ts.strip():
        raise SuccessionError("succession report needs an injected timestamp")
    if not isinstance(zero_loss, ZeroLossReport):
        raise SuccessionError("zero_loss must be a computed ZeroLossReport, not a supplied verdict")

    for party in (predecessor, successor):
        if party.leg not in VALID_LEGS:
            raise SuccessionError(f"leg {party.leg!r} is not one of {VALID_LEGS}")
        if party.leg == "live" and not party.verification:
            raise SuccessionError(
                f"the {party.role} leg is declared 'live' with no verification record; a live leg "
                "requires a VERIFIED executing checkpoint reported by the CLI (directive §6, §10.4)")

    # A LABEL-DIFFERENCE REFUSAL, and no more than that. It catches the degenerate case where the
    # succession was configured onto an identical conductor. It does NOT prove the backends differ:
    # `ConductorAdapter.capability().adapter` is the hard-coded literal "conductor_fable5" for every
    # instance, so that half never discriminates, and `model_name` is an attribute this module
    # assigns onto the backend object — two identical MockReasoningBackend instances satisfy it.
    # Recorded as U50; do not read a pass here as evidence of interchangeability.
    if (predecessor.adapter == successor.adapter
            and predecessor.model_name == successor.model_name):
        raise SuccessionError(
            f"successor is not a different backend: both conductors are "
            f"{successor.adapter!r}/{successor.model_name!r} — 15D requires resuming on a DIFFERENT "
            "backend, and a succession onto the same one proves no interchangeability")

    order = [str(step) for step in handoff_order]
    if order and order[:2] != ["release", "acquire"]:
        raise SuccessionError(
            f"I-X3 handoff must release the predecessor's terminal BEFORE the successor acquires "
            f"it; observed {order}")
    handoff_note = ("release-before-acquire observed on the subscription governor (I-X3)" if order
                    else "no subscription governor bound — handoff order not observed "
                         "(recorded as absent, not as correct)")

    if restored_selection is not None:
        reason = dict(restored_selection).get("reason")
        if reason != "operator_selected":
            raise SuccessionError(
                f"a RESTORED selection must carry reason 'operator_selected'; got {reason!r}. "
                "Recording a still-succeeded state as restored would claim a restore that did not "
                "happen (directive §11 15D 'then restore selection')")

    return {
        "schema": SUCCESSION_REPORT_SCHEMA,
        "ts": ts,
        "objective": objective,
        "predecessor": predecessor.as_record(),
        "successor": successor.as_record(),
        "restored_selection": copy.deepcopy(dict(restored_selection)) if restored_selection else None,
        "restored_selection_note": RESTORED_SELECTION_NOTE if restored_selection else None,
        "staleness": copy.deepcopy(dict(staleness)),
        "zero_loss": {"ok": zero_loss.ok, "checks": copy.deepcopy(zero_loss.checks),
                      "failed_checks": zero_loss.reasons()},
        "handoff_order": order,
        "handoff_note": handoff_note,
        # the ONE field that answers "did this run reach a real provider", spanning both conductors
        "run_spend_leg": merge_spend_leg(predecessor.leg, successor.leg),
        "acceptance_packet": packet_entry,
        "operator_disposition": OPERATOR_DISPOSITION_PENDING,
    }


# --------------------------------------------------------------------------------------
# 3. driving one interrupted governed run
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SuccessionOutcome:
    """Result of ONE succession attempt. `ran=False, skipped_with_record=True` is the honest
    non-interactive outcome (§10.4)."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    #: the succession gate's verdict on the report. `published` says the record reached MCP; it does
    #: NOT say the gate accepted it, and a caller checking `ran and published` would otherwise read
    #: a REJECTED report as success (invariant 16).
    report_verdict: str | None = None
    #: True when this non-result is a GOVERNANCE REFUSAL (the kill was ineffective, §19.1 staleness
    #: refused the successor, the I-X3 order was wrong, a promotion lost its CAS) rather than an
    #: environmental skip. Both are honest non-results; only this one is a defect.
    governance_refusal: bool = False
    report: dict[str, Any] | None = None
    report_entry: str | None = None
    acceptance_packet: str | None = None
    trace: dict[str, Any] | None = None
    zero_loss: ZeroLossReport | None = None
    legs: dict[str, str] = field(default_factory=lambda: {"conductor_predecessor": "skipped",
                                                          "conductor_successor": "skipped",
                                                          "workers": "skipped"})


def _mock_handle(mcp_client: Any, conductor_manifest: dict[str, str], *, node_id: str, model: str,
                 selection: ConductorSelection, project_id: str, governor: Any,
                 subscription_ref: str | None, backend: Any = None) -> ConductorHandle:
    """A mock-backed conductor bound to the real `ConductorAdapter` contract, optionally under the
    subscription governor so the I-X3 handoff is OBSERVABLE rather than assumed.

    The selection record deliberately mirrors `ConductorBinding.as_record()`'s shape while stating
    the mock truth: nothing executed, so `executing.model` is None and `verified` is False. It is
    never the vendor roster descriptor — asserting a frontier, subscription-backed vendor identity
    for a run in which no vendor CLI participates is the overclaim `.flow` removed.

    MOCK ONLY — do not hand this a real vendor backend. It hard-codes `leg="mock"` and MUTATES the
    backend's `model_name`, so a real `ClaudeCliBackend` passed here would have a genuine
    subscription spend recorded as mock and its model relabelled (§6, U51).
    """
    if type(backend).__name__ in _VENDOR_BACKEND_NAMES:
        raise SuccessionError(
            f"{type(backend).__name__} is a live vendor backend; this helper hard-codes leg='mock' "
            "and would under-report a real subscription spend. A live succession needs a supervised "
            "spawn path, which this unit does not have (U51).")
    ctx = AdapterContext(node_id=node_id, role="conductor", project_id=project_id,
                         permission_profile_id="pp-conductor", mcp_credential_id="ref",
                         subscription_ref=subscription_ref, spawned_by_supervisor=True)
    backend = backend if backend is not None else MockReasoningBackend()
    # A distinct model name is what makes "a DIFFERENT backend" CHECKABLE in the report; the mock
    # reasoner is otherwise the same class, and reporting two indistinguishable objects as
    # different backends is exactly what `build_succession_report` refuses.
    backend.model_name = model
    adapter = ConductorAdapter(ctx, mcp_client, backend, governor, conductor_manifest)
    return ConductorHandle(
        adapter=adapter, leg="mock",
        # Hand-built rather than produced by `bind_conductor_selection` because no vendor slug is
        # resolved here at all. It MUST stay key-identical to `ConductorBinding.as_record()`, or a
        # consumer reading both shapes sees fields appear and vanish by code path — that drift
        # already happened once (`.gate` added `reported_unverified`/`verified_by` and this copy
        # did not follow), so `test_mock_handle_record_matches_the_binding_shape` now pins it.
        selection_record={"selection": selection.as_current_conductor(),
                          "executing": {"model": None, "requested": model, "resolved_slug": None,
                                        "verified": False, "is_fallback": False,
                                        "note": f"mock backend {model!r} — no vendor CLI is bound",
                                        "reported_unverified": None, "verified_by": None},
                          "label_mismatch": False},
        model_resolution={"adapter": model, "node_class": "conductor", "conductor_capable": True,
                          "subscription_backed": False, "locality": "local"})


def mock_predecessor_handle(mcp_client: Any, conductor_manifest: dict[str, str], *,
                            model: str = "mock-fable5", project_id: str = "proj",
                            node_id: str = "conductor-fable5", governor: Any = None,
                            subscription_ref: str | None = None,
                            backend: Any = None) -> ConductorHandle:
    """The conductor that gets killed: the OPERATOR's selection (fable-5, `operator_selected`)."""
    return _mock_handle(mcp_client, conductor_manifest, node_id=node_id, model=model,
                        selection=OPERATOR_SELECTED_CONDUCTOR, project_id=project_id,
                        governor=governor, subscription_ref=subscription_ref, backend=backend)


def mock_successor_handle(mcp_client: Any, conductor_manifest: dict[str, str], *,
                          model: str = "mock-successor", project_id: str = "proj",
                          node_id: str = "conductor-successor", governor: Any = None,
                          subscription_ref: str | None = None, backend: Any = None,
                          since: str = "2026-07-20T00:00:00+00:00") -> ConductorHandle:
    """A successor conductor on a DIFFERENT mock backend, carrying a `reason: succession` selection.

    Built through `succession_selection` (the ONE validated constructor), so the successor stays
    distinguishable forever after from an operator choice — "the operator picked this" and "the
    system recovered onto this" are different facts (invariant 28 / `.selection`).
    """
    return _mock_handle(mcp_client, conductor_manifest, node_id=node_id, model=model,
                        selection=succession_selection(model, since=since, adapter="mock_reasoning"),
                        project_id=project_id, governor=governor, subscription_ref=subscription_ref,
                        backend=backend)


class LiveConductorSuccession:
    """One governed run, interrupted mid-flight, resumed by a different conductor.

    The conductors are INJECTED (a handle and a successor factory), so the identical sequence runs
    on mock backends or on the live claude_code binding with no branch in the governed path —
    the conductor is an interface (invariant 3).
    """

    def __init__(self, server: MCPServer, conductor_manifest: dict[str, str], *,
                 predecessor_factory: Callable[[Any], ConductorHandle] | None = None,
                 successor_factory: Callable[[Any], ConductorHandle] | None = None,
                 project_id: str = "proj",
                 worker_ids: Sequence[str] = ("worker-A", "worker-B"),
                 governor: Any = None, subscription_ref: str | None = None,
                 directive_version: str = "v2.4",
                 clock: Callable[[], str] | None = None) -> None:
        self._srv = server
        self._manifest = dict(conductor_manifest)
        self._project = project_id
        self._worker_ids = tuple(worker_ids)
        self._governor = governor
        self._subscription_ref = subscription_ref
        self._directive_version = directive_version
        self._clock = clock or _now
        self._clients: list[McpClient] = []
        # Both conductors are built by the runner from a client IT owns. That ownership is what
        # makes the kill real: a caller-supplied handle would carry an MCP session this runner
        # could not close, and "the predecessor is dead" would be an assumption rather than an act.
        self._predecessor_factory = predecessor_factory or (
            lambda client: mock_predecessor_handle(
                client, self._manifest, project_id=self._project, governor=self._governor,
                subscription_ref=self._subscription_ref))
        self._successor_factory = successor_factory or (
            lambda client: mock_successor_handle(client, self._manifest, project_id=self._project,
                                                 governor=self._governor,
                                                 subscription_ref=self._subscription_ref))
        self._gates = GateEngine()
        #: the handles actually built, exposed so a caller can inspect the real objects
        self.predecessor_handle: ConductorHandle | None = None
        self.successor_handle: ConductorHandle | None = None

    def _client(self, node_id: str, role: str) -> McpClient:
        c = McpClient("127.0.0.1", self._srv.port,
                      self._srv.credentials.issue(node_id, role, self._project))
        c.connect()
        self._clients.append(c)
        return c

    # -- the run -----------------------------------------------------------------
    def run(self, objective: str, *, kill_after_waves: int = 1) -> SuccessionOutcome:
        """Run the governed flow, kill the conductor after `kill_after_waves` waves, resume on a
        DIFFERENT backend, compare, restore the operator selection, and publish the record.

        Everything this creates is torn down before the method returns (loop constraint D-LOOP-1).
        Any outcome short of a completed, compared succession is skip-with-record: the honest
        non-result, never a softened pass (§10.4).
        """
        # Construction runs INSIDE the teardown guarantee. Previously the predecessor factory, the
        # audit client and the flow were built before the `try`, so a failure there escaped `run()`
        # raw and leaked MCP sessions (and, with a governor bound, a possibly-acquired terminal) —
        # contradicting both this docstring's teardown promise and its skip-with-record promise.
        handle: ConductorHandle | None = None
        pred_backend: Any = None
        pred_calls_before = 0
        flow: LiveGovernedFlow | None = None
        succ_client: McpClient | None = None
        try:
            pred_client = self._client("conductor-fable5", "conductor")
            handle = self._predecessor_factory(pred_client)
            self.predecessor_handle = handle
            pred_backend = handle.adapter.backend
            # Bind-time snapshot: every leg/verification judgement below is about THIS run, not the
            # backend object's lifetime (`calls` is a lifetime counter — `.debate`'s freshness rule).
            pred_calls_before = bind_calls_snapshot(pred_backend) or 0

            audit = self._client("succession-audit", "operator")
            flow = LiveGovernedFlow(self._srv, self._manifest, project_id=self._project,
                                    conductor_handle=handle, worker_ids=self._worker_ids,
                                    clock=self._clock)
            run_state = flow.begin(objective)
            # U62: begin() may have REBOUND the conductor handle with a post-CLI selection record
            # (the live binding's `_rebind` computes `verify_reported_checkpoint` AFTER the decompose
            # call). The pre-rebind `handle` still on `self.predecessor_handle` carries a stale
            # `selection.executing` mirror, so `_party` would echo `executing.model=null` beside a
            # freshly-correct `verification` record. Read the rebound handle back so the predecessor
            # party reports the SAME selection record the acceptance packet does. The adapter and
            # backend are unchanged by a rebind (identical for the mock path, where rebind is None),
            # so the kill/death-evidence/teardown uses of `handle` are unaffected.
            handle = flow.conductor_handle
            self.predecessor_handle = handle
            if run_state.plan_blocked:
                flow.finish()
                return self._skip("the plan gate blocked the run — no governed work existed to "
                                  "survive a succession", handle, pred_backend, pred_calls_before)

            # --- run to the KILL point, at a governed boundary between waves -------------
            if flow.run_waves(max_waves=max(1, int(kill_after_waves))):
                # The graph quiesced inside the pre-kill slice: there is no remaining work for a
                # successor to resume, so killing here would demonstrate no MID-RUN succession.
                # Reported as a non-result rather than dressed up as one.
                flow.finish()
                return self._skip("the run quiesced before the kill point — nothing remained for a "
                                  "successor to resume, so this is not a mid-run succession",
                                  handle, pred_backend, pred_calls_before)

            before = capture_project_snapshot(audit, self._task_states(flow))
            state = self._conductor_state(flow, audit, handle)
            # `major_event` is the frozen checkpoint@1.0 trigger for this: a conductor handover is
            # the major event par excellence. The enum is frozen at four values and is NOT widened
            # for this unit's convenience (canonical set frozen; §2.5).
            snapshot = SuccessionManager(pred_client).serialize(state, trigger="major_event")

            predecessor = self._party("predecessor", handle, pred_backend, pred_calls_before)

            # --- KILL --------------------------------------------------------------------
            # close() releases the subscription terminal (I-X3 release); closing the MCP client
            # ends the session. Nothing of the predecessor survives into the successor except what
            # is durably in MCP — which is the whole claim.
            handle.adapter.close()
            # REFUSE, don't just record. A gate-validator produced a full `ran=True, published=True,
            # zero loss CONFIRMED` succession from a predecessor whose close() was a no-op, because
            # `_death_evidence` only reported liveness and nothing ever checked it. Every other
            # honesty rule in this module raises; this one now does too.
            if handle.adapter.is_active:
                raise SuccessionError(
                    "the predecessor is still active after close() — the kill did not happen, so "
                    "nothing that follows can be reported as a succession")
            released = self._governor_active()
            pred_client.close()

            # --- Resume → Select: a separately-constructed conductor on a DIFFERENT backend ---
            succ_client = self._client("conductor-successor", "conductor")
            succ_handle = self._successor_factory(succ_client)
            self.successor_handle = succ_handle
            succ_backend = succ_handle.adapter.backend
            succ_calls_before = bind_calls_snapshot(succ_backend) or 0
            # start() acquires the successor's terminal (I-X3 acquire, strictly after the release
            # above) and RELOADS all 12 conductor files from MCP — the successor rebuilds its
            # operating context from shared memory, never from the predecessor's session.
            succ_handle.adapter.start()
            acquired = self._governor_active()
            handoff = self._handoff_order(released, acquired)

            # The §19.1 staleness checklist decides whether the successor may assign work at all.
            # The adapter label is taken from the successor's OWN capability, never hard-coded:
            # `run()` is backend-agnostic, and stamping a literal here would write a false adapter
            # label onto any non-mock successor injected through `successor_factory` (I-SC1).
            recon_state, staleness = SuccessionManager(succ_client).reconstruct(
                expected_directive_version=self._directive_version,
                new_selection={"model": _model_name(succ_backend),
                               "adapter": succ_handle.adapter.capability().adapter})
            if not staleness.ok:
                # Fail closed (Buildout §4, invariant 16). Previously this verdict was computed,
                # stored in the report and then ignored while the successor ran anyway.
                return self._skip(
                    f"the §19.1 staleness checklist REFUSED the successor "
                    f"({staleness.reasons()}) — it may not assign work, so no succession occurred",
                    handle, pred_backend, pred_calls_before, governance_refusal=True)

            # --- resume the SAME governed run under the successor ------------------------
            flow.swap_conductor(succ_handle)
            flow.run_waves()
            trace = flow.finish()

            after = capture_project_snapshot(audit, self._task_states(flow))
            zero_loss = compare_zero_loss(before, after)

            # --- restore the operator's selection (15D: "then restore selection") --------
            ts = self._clock()
            restored = restore_operator_selection(recon_state.current_conductor, since=ts)

            successor = self._party("successor", succ_handle, succ_backend, succ_calls_before)
            report = build_succession_report(
                objective=objective, predecessor=predecessor, successor=successor,
                restored_selection=restored.as_current_conductor(),
                staleness={"ok": staleness.ok, "checks": staleness.checks,
                           "failed_checks": staleness.reasons(), "snapshot_entry": snapshot["entry_id"]},
                zero_loss=zero_loss, handoff_order=handoff,
                packet_entry=trace.get("acceptance_packet"), ts=ts)

            report_entry, verdict = self._publish_and_gate_report(
                report, succ_client, succ_handle.adapter, ts,
                evidence=[snapshot["entry_id"]] + ([trace["acceptance_packet"]]
                                                   if trace.get("acceptance_packet") else []))
            trace["succession"] = {
                "report_entry": report_entry, "report_gate": verdict,
                "snapshot_entry": snapshot["entry_id"],
                "predecessor_dead": self._death_evidence(handle.adapter),
                "handoff_order": handoff,
            }
            legs = {"conductor_predecessor": predecessor.leg,
                    "conductor_successor": successor.leg, "workers": "mock"}
            advanced = zero_loss.checks.get("work_advanced") is True
            return SuccessionOutcome(
                ran=True, published=True, skipped_with_record=False,
                report_verdict=verdict["verdict"],
                reason=(f"conductor succeeded mid-run onto a differently-LABELLED backend "
                        f"({predecessor.model_name} -> {successor.model_name}); zero loss "
                        f"{'CONFIRMED' if zero_loss.ok and advanced else 'NOT confirmed'}"
                        f"; succession gate {verdict['verdict']}"),
                report=report, report_entry=report_entry,
                acceptance_packet=trace.get("acceptance_packet"), trace=trace,
                zero_loss=zero_loss, legs=legs)
        except SuccessionError as exc:
            # A GOVERNANCE REFUSAL (kill not effective, staleness refused, I-X3 order wrong, lost
            # CAS) is not the same fact as "the environment could not run this". Both are non-
            # results, but only one is a defect, and flattening them would hide it (§6).
            return self._skip(f"REFUSED: {exc}", handle, pred_backend, pred_calls_before,
                              governance_refusal=True)
        except Exception as exc:  # noqa: BLE001 — never a false PASS
            return self._skip(f"{type(exc).__name__}: {exc}", handle, pred_backend,
                              pred_calls_before)
        finally:
            # spawn -> exercise -> TEAR DOWN inside the unit (D-LOOP-1)
            if flow is not None:
                try:
                    flow.close()
                except Exception:  # noqa: BLE001
                    pass
            if handle is not None:
                # `flow.close()` only closes the CURRENT conductor, so after a swap the predecessor
                # would leak its subscription terminal. Closing twice is idempotent.
                try:
                    handle.adapter.close()
                except Exception:  # noqa: BLE001
                    pass
            self.close()

    # -- pieces ------------------------------------------------------------------
    def _skip(self, reason: str, handle: ConductorHandle | None, backend: Any,
              calls_before: int, *, governance_refusal: bool = False) -> SuccessionOutcome:
        """The honest non-result. The predecessor's leg is still classified from COUNTED-CALL
        evidence, so a run that reached the model before failing is never reported as `skipped`."""
        leg = backend_leg(backend, calls_before=calls_before) if handle is not None else "skipped"
        return SuccessionOutcome(
            ran=False, published=False, skipped_with_record=True, reason=reason,
            governance_refusal=governance_refusal,
            legs={"conductor_predecessor": leg, "conductor_successor": "skipped",
                  "workers": "skipped"})

    def _party(self, role: str, handle: ConductorHandle, backend: Any,
               calls_before: int) -> ConductorParty:
        """Classify one conductor from evidence: the HARDENED classifier (exact vendor type +
        a checkpoint datable to a call made after the bind-time snapshot), never from configuration.
        """
        return ConductorParty(
            role=role, node_id=handle.adapter.context.node_id,
            adapter=handle.adapter.capability().adapter, model_name=_model_name(backend),
            leg=backend_leg(backend, calls_before=calls_before),
            selection_record=handle.selection_record,
            verification=verification_for(backend, calls_before=calls_before),
            calls_spent=max(0, _calls_or_zero(backend) - calls_before))

    @staticmethod
    def _task_states(flow: LiveGovernedFlow) -> dict[str, str]:
        return {t.task_id: t.state.value for t in flow.graph.all_tasks()}

    def _conductor_state(self, flow: LiveGovernedFlow, reader: Any,
                         handle: ConductorHandle) -> ConductorState:
        """The predecessor's full operating state, with `memory_heads` pinned to the CURRENT head
        version of every ACCEPTED entry.

        Pinning every accepted entry (not a curated subset) is what gives the §19.1 checklist teeth:
        `reconstruct` flags any ACCEPTED entry absent from these heads as post-snapshot work, so an
        incomplete snapshot surfaces as a staleness failure instead of a silent gap.
        """
        heads: dict[str, str] = {}
        for entry in reader.call("read_status", status="ACCEPTED"):
            entry_id = entry.get("entry_id")
            if not entry_id:
                continue
            head = reader.call("get_head", entry_id=entry_id)
            if head is not None:
                heads[entry_id] = f"{entry_id}@{head['version']}"
        graph = flow.graph
        return ConductorState(
            tasks=[{"task_id": t.task_id, "state": t.state.value} for t in graph.all_tasks()],
            nodes=[{"node_id": n, "state": "READY"} for n in self._worker_ids],
            open_debates=[], pending_gates=[], memory_heads=heads,
            routing={}, outstanding_issues=[], directive_version=self._directive_version,
            task_graph_version=len(graph.events()),
            # `node_id` rides alongside the schema keys because `SuccessionManager` publishes the
            # snapshot AS that node, and MCP enforces provenance.author_node == the publishing node
            # (invariant 11). It is filtered back out for the checkpoint's `current_conductor`
            # (checkpoint@1.0 is additionalProperties:false) and again by `reconstruct`, so it never
            # contaminates the selection record itself.
            current_conductor={**((handle.selection_record or {}).get("selection") or {}),
                               "node_id": handle.adapter.context.node_id})

    def _governor_active(self) -> int | None:
        if self._governor is None or not self._subscription_ref:
            return None
        try:
            return int(self._governor.active_count(self._subscription_ref))
        except Exception:  # noqa: BLE001 — unobservable, NOT zero
            return None

    @staticmethod
    def _handoff_order(released: int | None, acquired: int | None) -> tuple[str, ...]:
        """The I-X3 order as OBSERVED on the governor, or empty when no governor was bound.

        `release` is recorded only when the count actually dropped to zero after the predecessor
        closed, and `acquire` only when it came back up: an unobserved handoff is reported as
        absent, never as correct.
        """
        if released is None or acquired is None:
            return ()
        if released == 0 and acquired >= 1:
            return ("release", "acquire")
        # Observed something OTHER than a clean handoff. Do not fabricate an ordering: all that was
        # actually observed is that the count did not drop to zero, which is not an observation of
        # acquire-before-release. Report the anomaly as itself so the report's refusal fires on a
        # true statement rather than an invented one.
        return ("no-release-observed",)

    @staticmethod
    def _death_evidence(adapter: ConductorAdapter) -> dict[str, Any]:
        """Evidence that the predecessor is actually gone, read from the adapter after close().

        `is_active` is the liveness fact; `files_loaded` deliberately stays True, because a closed
        conductor keeps its loaded files in memory. Reporting `ready` as death evidence would be
        reading file-load completeness and calling it liveness.
        """
        status = adapter.get_context_status()
        return {"is_active": adapter.is_active, "files_loaded": status["ready"],
                "cycles_run": status["cycles_run"]}

    def _publish_and_gate_report(self, report: Mapping[str, Any], author_client: Any,
                                 author: ConductorAdapter, ts: str,
                                 evidence: Sequence[str]) -> tuple[str, dict[str, Any]]:
        """Publish the succession report CANDIDATE and let a GATE node decide it.

        The successor authored the report, so the successor does not promote it: promotion is the
        gate node's act (invariant 18 — no node solely judges its own work), and the gate reads the
        bytes back FROM MCP rather than trusting the author's copy (I-M1).
        """
        content = _json_bytes(report)
        prov = {"author_node": author.context.node_id, "task_id": None, "ts": ts,
                "directive_version": self._directive_version, "confidence": "high"}
        entry_id = author_client.call(
            "publish", kind="decision", tier="shared_project",
            content_b64=base64.b64encode(content).decode("ascii"),
            provenance=prov, status="CANDIDATE")["entry_id"]

        gate_client = self._client("gate-succession", "gate")
        gate_client.call("transition", entry_id=entry_id, requested_status="UNDER_REVIEW")
        stored = base64.b64decode(gate_client.call("get_content", entry_id=entry_id)["content_b64"])
        digest = "sha256:" + hashlib.sha256(stored).hexdigest()
        claims = ([{"text": "the conductor was replaced mid-run with no loss of gated project state",
                    "evidence_refs": list(evidence)}]
                  if earns_zero_loss_claim(report) and evidence else [])
        structured = {
            "summary": f"conductor succession for: {report['objective']}",
            "claims": claims,
            "artifact": {"artifact_id": digest, "media_type": "application/json",
                         "size_bytes": len(stored), "created_by_node": author.context.node_id,
                         "task_id": None, "ts": ts, "schema": "artifact@1.0"},
        }
        verdict = self._gates.evaluate(
            define_gate(SUCCESSION_GATE_KIND, SUCCESSION_GATE_CRITERIA),
            GateContext(artifact_content=stored, structured_output=structured,
                        evidence_refs=list(evidence)),
            evidence=list(evidence))
        passed = verdict["verdict"] in ("PASS", "PASS_WITH_RESERVATIONS")
        promotion = gate_client.call("transition", entry_id=entry_id,
                                     requested_status="ACCEPTED" if passed else "REJECTED",
                                     reviewer_note=f"succession gate {verdict['verdict']}")
        # Invariant 13: a lost CAS is an EXPLICIT conflict object, never a silent last-write-wins.
        # `live_flow` already does this for promotions thirty lines away; discarding the result
        # here would let a report whose status never changed still be reported as published.
        if isinstance(promotion, Mapping) and promotion.get("applied") is False:
            raise SuccessionError(
                f"the succession report's promotion to "
                f"{'ACCEPTED' if passed else 'REJECTED'} was NOT applied (CAS conflict: "
                f"{promotion.get('conflict')}) — its MCP status is unchanged, so it cannot be "
                "reported as published")
        return entry_id, verdict

    def close(self) -> None:
        for c in self._clients:
            try:
                c.close()
            except Exception:  # noqa: BLE001 — teardown must not mask a result
                pass


def _calls_or_zero(backend: Any) -> int:
    """Counted calls for the SPENT-HERE ARITHMETIC only, 0 when unreadable.

    NOT a bind-time snapshot. Snapshots go through `bind_calls_snapshot`, which resolves the same
    object `verify_reported_checkpoint` will read; this function reads whatever it is handed. An
    earlier version of this module used it for both, and for a conductor WRAPPER the two are
    different counters (the wrapper tallies `propose_plan` calls, the inner backend tallies CLI
    calls) — so freshness compared two unrelated numbers and a stale checkpoint could verify. That
    is the U45 defect shape, and `phase-15d.gate` removed it from this module too.
    """
    return calls_or_none(backend) or 0


def _model_name(backend: Any) -> str:
    name = getattr(backend, "model_name", None) or getattr(backend, "name", None)
    return str(name) if name else "unknown_backend"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True).encode("utf-8")
