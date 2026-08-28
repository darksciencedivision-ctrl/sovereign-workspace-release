"""Governed CONDUCTOR dispatch feed — Phase 16C `.dispatch` (directive §15 track 16C; OP-8 §13.4 / OP-9).

The govern-born conductor pane (`.spawn`) is not just a chat surface: as it converses it DISPATCHES work
to the other model nodes over the shared Sovereign MCP memory, pulls their CANDIDATE results back through
the gates, and SYNTHESIZES them (OP-8 §13.4). This sub-step wires that dispatch into the shell so the
operator can see, on launch, that the conductor's governed dispatch path is real — it runs the whole
`control_plane.orchestration.live_flow` loop (decompose → assign BY DESCRIPTOR → CANDIDATE over MCP →
real gate engine → conductor synthesis into an acceptance packet) and folds the trace into a stable
`conductor_dispatch_feed@1.0` contract the renderer draws from.

HONESTY — this is the load-bearing constraint (directive §6 / §10.4; closes **U58 as far as evidence
allows**). U58 records that the live `.flow` proved a live CONDUCTOR but the WORKERS were still the
deterministic `LocalWorkerAdapter` (`legs.workers="mock"`). This sub-step does NOT change that: the
dispatch is run MOCK-first — `legs.conductor="mock"`, `legs.workers="mock"` — so **no live model call is
made here** (§2.2/§2.4), and `build_acceptance_packet`/`_assert_legs_honest` make a `live`/`attempted`
WORKER leg UNREPRESENTABLE without its own evidence record. The feed therefore carries an explicit
`live_workers_owed` record: the governed dispatch MACHINERY is proven end-to-end and wired into the shell,
but the actual LIVE worker CANDIDATE publication remains OWED to the operator-run assembled run (16F). We
close U58 exactly as far as the non-interactive evidence allows and no further — never dressing a mock
dispatch as a live-worker result.

Invariants surfaced on the feed so an operator/self-check can verify them: routing is BY DESCRIPTOR
(invariant 4 — `by_descriptor`), the conductor does not accept its own synthesis (invariant 18 — the
`acceptance_verdict` is the GATE node's, and the packet's `operator_disposition` stays `pending` because
gate promotion is NOT operator acceptance, invariant 1). Fail-closed (invariant 3 / invariant 20 spirit):
any fault yields the UN-DISPATCHED feed (`dispatched:false`, `reason`), never a fabricated dispatch.
D-LOOP-1 (directive §14): the MCP server + flow are torn down within `run_governed_dispatch` before it
returns (`torn_down:true`) — nothing outlives the call.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from adapters.conductor import publish_conductor_files
from control_plane.orchestration.live_flow import (
    WORKER_LEG_PREFIX,
    LiveGovernedFlow,
    WorkerHandle,
    derive_worker_legs,
)
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer

#: Pinned so the shell source validates the shape it parses (a drifted producer is refused).
CONDUCTOR_DISPATCH_FEED_SCHEMA = "conductor_dispatch_feed@1.0"

#: Smoke-scale objective (minimal work; the point is the governed dispatch path, not the content).
DEFAULT_OBJECTIVE = "Design the offline conductor roster"
DEFAULT_WORKER_IDS: tuple[str, ...] = ("worker-A", "worker-B")

#: An INJECTED, fixed synthesis timestamp so the MOCK dispatch (and the acceptance packet it
#: synthesizes) is fully REPLAYABLE — `build_acceptance_packet` requires an injected ts for exactly
#: this reason. A fixed ts is not a false claim for a mock proof of the dispatch machinery: it is
#: deterministic by design and nothing about it happened at a particular moment.
#:
#: It IS a false claim for a run that spent a real subscription call, and one was stamped with it
#: (Phase 17B `.legs`: a 2026-07-26 live dispatch published a packet dated 2026-07-24 — found
#: independently by the gate-validator and the spec-auditor). A live dispatch now takes the real
#: clock; only the mock path is replayable. Provenance must date what actually happened (inv 11).
DISPATCH_TS = "2026-07-24T00:00:00+00:00"

#: The honest U58 record carried on EVERY feed (dispatched or not): the live-worker leg is owed.
LIVE_WORKERS_OWED: dict[str, Any] = {
    "owed": True,
    "issue": "U58",
    "note": ("governed dispatch proven mock-first (legs.workers=mock); a LIVE worker leg is "
             "unrepresentable without its own evidence record (build_acceptance_packet refuses it) "
             "— the live worker CANDIDATE publication is the operator-run assembled run (16F)."),
}

#: The DISCHARGED record — emitted only when the packet's own worker evidence derives a `live`
#: aggregate, i.e. a real vendor call was counted AND the CLI reported a checkpoint back. Phase 17B
#: `.legs`. It is computed from the packet, never from a caller's flag, so a mock-first dispatch can
#: never present itself as having discharged U58.
#:
#: It says NOTHING about what the gate then did. It used to — the literal read "the real gate engine
#: accepted it" — and that sentence was emitted verbatim onto
#: `docs/evidence/live/PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.json`, a run whose artifact the
#: STAGE gate REFUSED (`stage_pass: 0/1`, `acceptance_verdict: "FAIL"`). A record that cannot observe
#: the gate must not narrate it (inv 11; spec-audit H2 at 17E `.close`). The gate's own verdict is in
#: `gate_summary` / `acceptance_verdict` / `accepted_count`, computed by the gate engine.
LIVE_WORKERS_MET: dict[str, Any] = {
    "owed": False,
    "issue": "U58",
    "note": ("a LIVE worker executed this dispatch: it published a CANDIDATE over MCP, and its leg is "
             "derived from a VERIFIED executing checkpoint dated to a call spent in this run. What the "
             "gate then did is not this record's claim — read `gate_summary`, `acceptance_verdict` and "
             "`accepted_count` for that."),
}


def live_workers_record(legs: Mapping[str, Any] | None,
                        worker_evidence: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """The U58 record, DERIVED from what the run's own evidence proves.

    `owed:false` requires BOTH the aggregate worker leg to read `live` AND at least one evidence row
    carrying a verified checkpoint — two independent reads of the same fact, so a feed whose legs
    were folded from a trace with no evidence attached cannot silently discharge the issue.
    """
    aggregate = (legs or {}).get("workers")
    verified = [r for r in (worker_evidence or [])
                if isinstance(r, Mapping) and r.get("verified") is True]
    if aggregate == "live" and verified:
        return {**LIVE_WORKERS_MET,
                "live_nodes": [{"node_id": r.get("node_id"), "model": r.get("model")}
                               for r in verified]}
    return dict(LIVE_WORKERS_OWED)


def _leg(value: Any) -> str:
    return value if isinstance(value, str) and value else "unknown"


def fold_dispatch_feed(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Fold a `LiveGovernedFlow.run(...)` trace into the stable `conductor_dispatch_feed@1.0` contract.

    PURE (no I/O) so the fold is unit-tested without a live server. Everything it reports is DERIVED
    from the trace the governed loop produced — it invents nothing. A `plan_blocked` run (the plan
    gate refused an unusable decomposition) folds to `dispatched:false` with the plan verdict as the
    reason: no plan ⇒ nothing was dispatched, reported honestly rather than as an empty success.
    """
    if not isinstance(trace, Mapping):
        raise TypeError("fold_dispatch_feed requires a flow trace mapping")

    packet = trace.get("packet") or {}
    assignments = [
        {"task": a.get("task"), "node": a.get("node"), "rationale": a.get("rationale")}
        for a in (trace.get("assignments") or [])
    ]
    # invariant 4: assignment is BY DESCRIPTOR, never by node/vendor name. True only when EVERY
    # assignment's rationale says so AND at least one task was actually routed.
    by_descriptor = bool(assignments) and all(
        isinstance(a.get("rationale"), str) and "by descriptor" in a["rationale"] for a in assignments
    )
    gate_records = trace.get("gate_records") or []
    plan_gate = trace.get("plan_gate") or {}
    stage = [g for g in gate_records if g.get("kind") == "stage"]
    stage_pass = [g for g in stage if g.get("verdict") in ("PASS", "PASS_WITH_RESERVATIONS")]
    acceptance = trace.get("acceptance_gate") or {}
    legs = trace.get("legs") or {}
    # Read from the PACKET, not the trace: the packet's rows are the ones `build_acceptance_packet`
    # validated and `_assert_legs_honest` checked the legs against, so the feed reports the same
    # evidence the durable artifact carries rather than a parallel copy that could drift.
    worker_evidence = [r for r in (packet.get("worker_evidence") or []) if isinstance(r, Mapping)]

    # A run that never built a graph (plan gate blocked) dispatched nothing — say so, fail closed.
    plan_verdict = plan_gate.get("verdict")
    plan_ok = plan_verdict in ("PASS", "PASS_WITH_RESERVATIONS")
    dispatched = bool(plan_ok and assignments)

    return {
        "schema": CONDUCTOR_DISPATCH_FEED_SCHEMA,
        "dispatched": dispatched,
        "reason": None if dispatched else (
            f"plan gate {plan_verdict!r} — no plan, nothing dispatched" if not plan_ok
            else "conductor decomposition routed no task to any worker"),
        "objective": trace.get("objective"),
        # Phase 17D `.events`: the decomposed plan AND the gate record that judged it, carried so the
        # shell can record this dispatch as a real approval-drawer event (a gate promotion the operator
        # has not yet disposed of — the packet holds `operator_disposition: pending`). Additive: it is
        # the trace's own decomposition + `gate@1.0` verdict, re-derived nowhere. `plan_blocked` is the
        # same fact `dispatched` is computed from, so the drawer and this feed cannot disagree about
        # whether the plan passed its gate.
        "plan": {
            "objective": trace.get("objective"),
            "tasks": [dict(t) for t in ((trace.get("decomposition") or {}).get("tasks") or [])],
            "refused": [dict(r) for r in ((trace.get("decomposition") or {}).get("refused") or [])],
            "plan_gate": dict(plan_gate),
            "plan_blocked": not plan_ok,
        },
        "assignments": assignments,
        "assigned_count": len(assignments),
        "by_descriptor": by_descriptor,
        "queued_count": len(trace.get("queued") or []),
        "failed_count": len(trace.get("failed_tasks") or []),
        "accepted_count": int(packet.get("accepted_count") or 0),
        "acceptance_packet": trace.get("acceptance_packet"),
        "acceptance_verdict": acceptance.get("verdict"),
        # invariant 1: gate promotion is NOT operator acceptance — surfaced so the feed can never be
        # mistaken for an operator decision (the packet holds it "pending").
        "operator_disposition": packet.get("operator_disposition"),
        "legs": {"conductor": _leg(legs.get("conductor")), "workers": _leg(legs.get("workers"))},
        # Per-NODE worker legs and the evidence rows they were derived from (Phase 17B `.legs`).
        # Additive to the 1.0 feed: existing consumers read `legs`/`live_workers_owed` unchanged,
        # and a mock-first dispatch emits an empty pair — the shape never claims what did not run.
        "worker_legs": {k: _leg(v) for k, v in legs.items() if k.startswith(WORKER_LEG_PREFIX)},
        "worker_evidence": [
            {"node_id": r.get("node_id"), "leg": r.get("leg"), "adapter": r.get("adapter"),
             "executed": r.get("executed"), "spent": r.get("spent"),
             "verified": r.get("verified"), "model": r.get("model"), "tasks": r.get("tasks") or []}
            for r in worker_evidence],
        # WHY a node declined, in the node's own words (Phase 17B `.legs`). A dispatch that assigned
        # work and accepted none is otherwise a wall of zeroes: the operator can see that a live
        # worker failed but not what it objected to, and the first `.legs` live dispatches were
        # diagnosed by reading source rather than the feed. Attributed to the node, never to a gate
        # (invariants 11/18).
        "node_refusals": [
            {"task_id": r.get("task_id"), "node_id": r.get("node_id"),
             "node_reported_reasons": [str(x) for x in (r.get("node_reported_reasons") or [])]}
            for r in (packet.get("node_refusals") or []) if isinstance(r, Mapping)],
        "gate_summary": {
            "plan": plan_verdict,
            "stage_pass": len(stage_pass),
            "stage_total": len(stage),
            "acceptance": acceptance.get("verdict"),
        },
        # invariant 18: the synthesizer named, so the operator can confirm the acceptance verdict came
        # from a GATE node, not from the synthesizer accepting its own work.
        "synthesized_by": packet.get("synthesized_by"),
        "live_workers_owed": live_workers_record(legs, worker_evidence),
        "ts": packet.get("ts") or trace.get("ts"),
        "torn_down": False,   # set True by run_governed_dispatch after teardown (D-LOOP-1)
    }


def undispatched_feed(reason: str, *, objective: str | None = None,
                      worker_evidence: Sequence[Mapping[str, Any]] = (),
                      ts: str | None = None) -> dict[str, Any]:
    """The fail-closed feed: a fault (or a blocked plan) means nothing was dispatched. NEVER a
    fabricated dispatch (invariant 3 / invariant 20 spirit) — the shell renders an honest
    "dispatch unavailable" with the reason.

    `worker_evidence` is what a LIVE worker had already spent when the fault hit (Phase 17B
    `.legs`, spec-audit MAJOR-1). Without it this feed reported `workers: skipped` and
    `live_workers_owed: true` for a run that had ALREADY consumed a subscription call — an
    auth pause, or a second transport failure, arrives after `generate()` has counted one. Faults
    are the paths under-reporting hides in, so the legs here are derived from the same evidence the
    dispatched feed uses, never hard-coded to `skipped`.
    """
    rows = [dict(r) for r in worker_evidence]
    derived = derive_worker_legs(rows) if rows else {}
    legs = {"conductor": "skipped", "workers": derived.get("workers", "skipped")}
    return {
        "schema": CONDUCTOR_DISPATCH_FEED_SCHEMA,
        "dispatched": False,
        "reason": reason,
        "objective": objective,
        "assignments": [],
        "assigned_count": 0,
        "by_descriptor": False,
        "queued_count": 0,
        "failed_count": 0,
        "accepted_count": 0,
        "acceptance_packet": None,
        "acceptance_verdict": None,
        "operator_disposition": None,
        "legs": legs,
        "worker_legs": {k: v for k, v in derived.items() if k.startswith(WORKER_LEG_PREFIX)},
        "worker_evidence": [
            {"node_id": r.get("node_id"), "leg": r.get("leg"), "adapter": r.get("adapter"),
             "executed": r.get("executed"), "spent": r.get("spent"),
             "verified": r.get("verified"), "model": r.get("model"), "tasks": r.get("tasks") or []}
            for r in rows],
        "node_refusals": [],
        "gate_summary": None,
        "synthesized_by": None,
        "live_workers_owed": live_workers_record(legs, rows),
        "ts": ts,
        "torn_down": True,   # nothing was left running to tear down
    }


def run_governed_dispatch(
    *,
    conductor_dir: Path,
    store_root: Path,
    objective: str = DEFAULT_OBJECTIVE,
    worker_ids: Sequence[str] = DEFAULT_WORKER_IDS,
    clock: Callable[[], str] | None = None,
    project_id: str = "proj",
    worker_handles: Callable[[MCPServer, str], Sequence[WorkerHandle]] | None = None,
) -> dict[str, Any]:
    """Run ONE governed dispatch over a REAL loopback MCP server and return the folded feed, tearing
    the server + flow down before returning (D-LOOP-1).

    DEFAULT: mock-first — no `worker_handles`, so NO live model call is made and the feed carries the
    honest U58-owed record. This is what the shell invokes on launch, and it must stay that way: an
    app launch may never spend the operator's subscription.

    `worker_handles` (Phase 17B `.legs`) is a factory called with `(server, project_id)` AFTER the
    server is up, returning already-spawned `WorkerHandle`s — a live one comes from
    `live_flow.live_claude_worker_handle`, i.e. through the governed live-spawn gates. The factory is
    injected rather than parameterised so this module never imports a live-spawn path (nothing here
    can spawn a vendor CLI by accident), and the flow releases each handle's I-X3 terminal on close
    (D-LOOP-1). A factory that raises propagates to the fail-closed wrapper — an un-dispatched feed,
    never a fabricated one.

    `store_root` is a caller-owned directory (a tempdir in the emitter/tests) — this function never
    touches anything outside it. `clock` defaults to the fixed replayable `DISPATCH_TS`.
    """
    ts = clock or (lambda: DISPATCH_TS)
    srv = MCPServer(store_root / "store")
    srv.start()
    op: McpClient | None = None
    flow: LiveGovernedFlow | None = None
    try:
        op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", project_id))
        op.connect()
        manifest = publish_conductor_files(op, "op-boot", conductor_dir)
        op.close()
        op = None   # closed cleanly on the happy path — don't double-close it in the finally

        # The factory owns releasing anything it acquired before it raises (it is the only code that
        # knows what it got that far). Once it RETURNS, ownership passes here: a flow that fails to
        # construct must still give every I-X3 terminal back, or a refused dispatch would wedge the
        # operator's subscription count for the life of the process (D-LOOP-1).
        handles = tuple(worker_handles(srv, project_id)) if worker_handles is not None else ()
        try:
            flow = LiveGovernedFlow(srv, manifest, project_id=project_id, worker_ids=tuple(worker_ids),
                                    worker_handles=handles, clock=ts)
        except Exception:
            for handle in handles:
                if handle.release is not None:
                    try:
                        handle.release()
                    except Exception:  # noqa: BLE001 — one failed release never strands the others
                        pass
            raise
        try:
            trace = flow.run(objective)
            feed = fold_dispatch_feed(trace)
        except Exception as exc:  # noqa: BLE001 — reported as un-dispatched, WITH what was spent
            # An auth pause or a second transport failure lands here AFTER `generate()` counted a
            # real call. Reading the flow's evidence keeps that spend on the record instead of
            # emitting a feed that says nothing ran (spec-audit MAJOR-1).
            feed = undispatched_feed(f"{type(exc).__name__}: {exc}", objective=objective,
                                     worker_evidence=flow.worker_evidence_rows(), ts=ts())
    finally:
        # Close the operator client on EVERY path (a connect()/publish failure must not leak a socket
        # for an in-process caller), then the flow, then the server — nothing governed outlives the call.
        if op is not None:
            try:
                op.close()
            except Exception:  # noqa: BLE001 — teardown must not mask the original error
                pass
        if flow is not None:
            flow.close()
        srv.stop()
    feed["torn_down"] = True     # server + flow are down; nothing outlives this call (D-LOOP-1)
    return feed


def build_conductor_dispatch_feed(
    *,
    conductor_dir: Path,
    store_root: Path,
    objective: str = DEFAULT_OBJECTIVE,
    worker_ids: Sequence[str] = DEFAULT_WORKER_IDS,
    clock: Callable[[], str] | None = None,
    worker_handles: Callable[[MCPServer, str], Sequence[WorkerHandle]] | None = None,
) -> dict[str, Any]:
    """Top-level fail-closed wrapper: run the governed dispatch, or return the un-dispatched feed on
    ANY fault (invariant 3). The shell renders whatever this returns without fabricating a dispatch."""
    try:
        return run_governed_dispatch(conductor_dir=conductor_dir, store_root=store_root,
                                     objective=objective, worker_ids=worker_ids, clock=clock,
                                     worker_handles=worker_handles)
    except Exception as exc:  # noqa: BLE001 — a fault is reported as un-dispatched, never faked
        return undispatched_feed(f"{type(exc).__name__}: {exc}", objective=objective)
