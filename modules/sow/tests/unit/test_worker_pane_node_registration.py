"""Phase 18E `.live.electron.wiring` — a supervised worker PANE becomes a Sovereign node RECORD.

Directive §17.2(1) asks the live acceptance leg for "a supervised ConPTY pane **as a registered
Sovereign node**". 18D wired that for the one-shot `GovernedProbeSession` and for nothing else: a
picker selection that opens a real `grok`/`agy` pane on the operator's host produced a durable I-X3
lease, an argv and a chrome — and no node record at all. Invariant 2 says every terminal is a
Sovereign node; the pane path was the terminal with no node.

These tests pin the wiring that closes it, end to end and on the REAL modules (real `NodeRegistry`,
real hash-chained `AppendOnlyEventLog`, real schema files, real jsonschema validator, real ticket
emitter). Only the filesystem location (tmp_path), the host detections the emitter already injects,
and the CLI binary that is never executed are stood in for.

The lifecycle is THREE facts written at the three moments they become true, never one moment
asserting all three:

  1. **ticket time** — the governed chain passed and a terminal was counted, so a record is written
     in `SPAWNING`. That is the honest state: authorized, not yet born. If the registrar refuses,
     the SESSION is refused and the durable terminal is handed back (18D's rule — a leased terminal
     with no record is the naked-but-leased session the chain exists to prevent);
  2. **spawn time** — the shell has a supervised ConPTY with a live pid, and only then does the
     record move to `READY` carrying that pid. Nothing before this claims the process exists;
  3. **release time** — the session ended, so the record is CLOSED on the same append-only log
     (`transition` → `exit`, D-LOOP-1 in the one place an auditor would look).

Steps 2 and 3 happen in a DIFFERENT PROCESS from step 1 (each emitter invocation is its own
`py -3.12`), so they rest on reading the durable log back — which is why `NodeRegistry.rehydrate`
and `ProviderNodeRegistrar.adopt_from_log` exist and are tested here as the fail-closed things they
are, not as conveniences.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER
from control_plane.nodes.event_log import AppendOnlyEventLog, verify_file
from control_plane.nodes.registry import NodeRecord, NodeRegistry, RegistrationRefused
from control_plane.nodes.states import NodeState
from control_plane.profiles.live_authorization import LiveAuthorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from node_runtime.supervisor.provider_node_registration import (
    GATE_RECORD_INVALID,
    GATE_UNGOVERNED_SESSION,
    GATE_UNKNOWN_NODE,
    GATE_UNSUPERVISED_SESSION,
    ProviderNodeRegistrar,
    ProviderNodeRegistrationRefused,
    build_pane_node_record,
    node_record_uuid,
)
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger
from node_runtime.supervisor.worker_pane_spawn import (
    PaneSelection,
    WorkerPaneChrome,
    authorize_worker_pane,
)
from tools.live.emit_worker_launch import (
    build_worker_lease_release_session,
    build_worker_launch_ticket,
    build_worker_pane_spawn_attestation,
    main,
)

HOLDER = 6120
SESSION = "pane-7#6120.1"
PANE = "pane-7"
WORKSPACE = "D:/repo"


# ---- fixtures: the real product objects, with the host's answers injected ----------------------

def _authorized(*providers: str) -> LiveAuthorization:
    return LiveAuthorization(
        authorized=True, providers=frozenset(providers or (GROK_ADAPTER, ANTIGRAVITY_ADAPTER)),
        terminals_per_subscription=1, register_row="OP-12", source="(test)",
        reason="test authorization")


def _ledger(tmp_path: Path, *, alive=(HOLDER,)) -> TerminalLeaseLedger:
    live = set(alive)
    return TerminalLeaseLedger(path=tmp_path / "leases.json", pid_alive=lambda p: p in live)


def _registrar(tmp_path: Path) -> ProviderNodeRegistrar:
    return ProviderNodeRegistrar(tmp_path / "nodes" / "node_events.jsonl")


def _option(adapter: str = GROK_ADAPTER, *, slug: str | None = "grok-4-fast",
            available: bool = True, locality: str = "frontier") -> dict:
    return {"provider": adapter, "adapter": adapter, "locality": locality,
            "subscription_backed": True, "label": slug or "CLI default", "model_slug": slug,
            "verified": True, "is_fallback": False, "roles": ["reasoning", "coding"],
            "residency": None, "available": available, "unavailable_reason": None}


def _selection(adapter: str = GROK_ADAPTER, **kw) -> dict:
    return {"option": _option(adapter, **kw), "role": "reasoning", "mode": "autonomous"}


def _offered(*selections: dict) -> list[dict]:
    return [dict(s["option"], roles=list(s["option"].get("roles") or [])) for s in selections]


def _pane_session(adapter: str = GROK_ADAPTER, **kw):
    """A REAL `WorkerPaneSession` from the REAL authorizer — never a hand-built stand-in.

    The gates are all injected (`cli_present`, an authorized `LiveAuthorization`, a cloud profile),
    which is what every other pane test does; what is NOT stood in for is the object under test.
    """
    option = _option(adapter, **kw)
    sel = PaneSelection(option=option, role="reasoning", mode="autonomous",
                        node_id=f"worker-{PANE}", permission_profile_id="pp-worker-reasoning",
                        subscription_ref=canonical_subscription_ref(adapter))
    gov = SubscriptionGovernor()
    return authorize_worker_pane(
        sel, live_auth=_authorized(), governor=gov,
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        workspace=WORKSPACE, cli_present=True,
        executable="C:/fake/grok.CMD" if adapter == GROK_ADAPTER else "C:/fake/agy.CMD")


def _ticket(tmp_path: Path, selection: dict | None = None, **kw) -> dict:
    sel = selection if selection is not None else _selection()
    call = dict(
        holder_pid=HOLDER, session_id=SESSION, pane_id=PANE, selection=sel,
        offered_options=_offered(sel), ledger=_ledger(tmp_path), live_auth=_authorized(),
        governor=SubscriptionGovernor(),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        registrar=_registrar(tmp_path), workspace=WORKSPACE, cli_present=True)
    call.update(kw)
    return build_worker_launch_ticket(**call)


def _raise_later(self) -> dict:
    """Stand-in for the first step AFTER the node record is written, forced to refuse."""
    raise ValueError("a later gate refused, after the record was written")


def _rows(tmp_path: Path) -> list[dict]:
    path = tmp_path / "nodes" / "node_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- 1. the record document ---------------------------------------------------------------------

class TestThePaneRecordIsSchemaValidAndDerived:
    def test_both_op12_providers_yield_a_record_that_validates_against_node_1_1(self) -> None:
        for adapter in (GROK_ADAPTER, ANTIGRAVITY_ADAPTER):
            record = build_pane_node_record(_pane_session(adapter), session_id=SESSION)
            assert record["adapter"] == adapter
            assert record["schema"] == "node@1.1"
            assert record["state"] == NodeState.SPAWNING.value
            assert record["locality"] == "frontier"
            assert record["spawned_by_supervisor"] is True

    def test_the_record_names_the_model_the_pane_will_actually_run(self) -> None:
        """The probe record's `model_ref` is `null` by construction — a probe selects no model. A
        PANE does: the operator picked it and it is in the argv. A record that dropped it would
        describe a different session from the one that runs."""
        record = build_pane_node_record(_pane_session(slug="grok-4-fast"), session_id=SESSION)
        assert record["model_ref"] == "grok-4-fast"

    def test_a_cli_default_pane_records_a_null_model_ref_rather_than_a_label(self) -> None:
        record = build_pane_node_record(_pane_session(slug=None), session_id=SESSION)
        assert record["model_ref"] is None

    def test_the_record_names_the_workspace_the_conpty_is_bound_to(self) -> None:
        record = build_pane_node_record(_pane_session(), session_id=SESSION)
        assert record["workspace"] == {"type": "dir", "path": WORKSPACE}

    def test_the_uuid_is_derived_from_the_node_and_the_session_not_the_pane_alone(self) -> None:
        """Two sessions of ONE pane are two nodes. Deriving from the pane alone would give them one
        record id on an append-only log (the U75 lesson, in the record)."""
        a = build_pane_node_record(_pane_session(), session_id="pane-7#1.1")
        b = build_pane_node_record(_pane_session(), session_id="pane-7#1.2")
        assert a["node_id"] != b["node_id"]
        assert a["node_id"] == node_record_uuid(f"worker-{PANE}#pane-7#1.1", 1)

    def test_no_credential_bearing_field_exists_on_the_record(self) -> None:
        record = build_pane_node_record(_pane_session(), session_id=SESSION)
        assert record["auth"] == {"mcp_credential_id": "mcp-ref"}
        blob = json.dumps(record).lower()
        for token in ("api_key", "apikey", "token", "secret", "oauth"):
            assert token not in blob


# ---- 2. the registrar's fences -------------------------------------------------------------------

class TestTheRegistrarRefusesWhatItCannotVouchFor:
    def test_a_duck_typed_session_is_refused(self, tmp_path: Path) -> None:
        """The I-C1 attestation this record carries is the supervisor's, not the caller's. A
        namespace with the right attribute names must not be able to assert it (18D MEDIUM-3, the
        same fence on the pane surface)."""
        import types

        fake = types.SimpleNamespace(
            chrome=_pane_session().chrome, launch={"cwd": WORKSPACE},
            subscription_governed=True, permission_profile_id="pp-worker-reasoning")
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            _registrar(tmp_path).register_pane_session(fake, session_id=SESSION, lease_id="lease-1")
        assert exc.value.gate == GATE_UNGOVERNED_SESSION

    def test_a_pane_session_holding_no_terminal_is_refused(self, tmp_path: Path) -> None:
        session = _pane_session()
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            _registrar(tmp_path).register_pane_session(session, session_id=SESSION, lease_id="")
        assert exc.value.gate == GATE_UNGOVERNED_SESSION

    def test_a_pane_session_that_does_not_claim_governance_is_refused(self, tmp_path: Path) -> None:
        session = _pane_session()
        session.chrome.governed = False
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            _registrar(tmp_path).register_pane_session(session, session_id=SESSION, lease_id="l1")
        assert exc.value.gate == GATE_UNSUPERVISED_SESSION

    def test_a_non_op12_provider_is_refused_without_creating_a_log(self, tmp_path: Path) -> None:
        """`claude_code` panes are OUT OF SCOPE for this wiring and are refused by NAME rather than
        registered under a borrowed vocabulary. The refusal must leave no file behind in the
        operator's store — the 18D lesson about an eagerly-created empty log."""
        session = _pane_session()
        session.chrome.adapter = CLAUDE_CODE_ADAPTER
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            _registrar(tmp_path).register_pane_session(session, session_id=SESSION, lease_id="l1")
        assert exc.value.gate == GATE_RECORD_INVALID
        assert not (tmp_path / "nodes" / "node_events.jsonl").exists()

    def test_a_pane_with_no_session_id_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            _registrar(tmp_path).register_pane_session(_pane_session(), session_id="  ",
                                                       lease_id="l1")
        assert exc.value.gate == GATE_RECORD_INVALID


# ---- 3. the lifecycle, across processes ----------------------------------------------------------

class TestTheLifecycleIsWrittenAtTheThreeMomentsItBecomesTrue:
    def test_registration_writes_a_spawning_record_on_a_verified_chain(self, tmp_path: Path) -> None:
        reg = _registrar(tmp_path)
        try:
            out = reg.register_pane_session(_pane_session(), session_id=SESSION, lease_id="lease-1")
        finally:
            reg.close()
        assert out.adapter == GROK_ADAPTER
        assert out.validated_against == "node@1.1"
        assert out.adapter_schema_version == "node@1.1"
        rows = _rows(tmp_path)
        assert [r["kind"] for r in rows] == ["spawn"]
        assert rows[0]["node_id"] == f"worker-{PANE}"
        assert verify_file(tmp_path / "nodes" / "node_events.jsonl").ok is True

    def test_a_fresh_process_adopts_the_record_from_the_log_and_attests_the_spawn(
            self, tmp_path: Path) -> None:
        """Steps 1 and 2 are two `py -3.12` invocations. The second one has an EMPTY registry and
        must recover the record from the durable log, or the pane's node would be re-registered as
        a second incarnation on every spawn."""
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id=SESSION, lease_id="lease-1")
        finally:
            first.close()

        second = _registrar(tmp_path)          # a NEW registrar: nothing in memory
        try:
            out = second.attest_spawned(f"worker-{PANE}", session_id=SESSION, pid=os.getpid())
        finally:
            second.close()
        assert out["attested"] is True and out["pid"] == os.getpid() and out["incarnation"] == 1
        kinds = [r["kind"] for r in _rows(tmp_path)]
        assert kinds == ["spawn", "transition"]
        transition = _rows(tmp_path)[-1]["data"]
        assert transition["to"] == NodeState.READY.value
        # the pid is a STRUCTURED field on the log, not a phrase inside a reason string
        assert transition["pid"] == os.getpid()
        assert verify_file(tmp_path / "nodes" / "node_events.jsonl").ok is True

    def test_the_release_closes_the_record_on_the_same_log(self, tmp_path: Path) -> None:
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id=SESSION, lease_id="lease-1")
        finally:
            first.close()
        mid = _registrar(tmp_path)
        try:
            mid.attest_spawned(f"worker-{PANE}", session_id=SESSION, pid=os.getpid())
        finally:
            mid.close()

        last = _registrar(tmp_path)
        try:
            out = last.close_session_record(f"worker-{PANE}", session_id=SESSION, exit_code=0,
                                            expected=True)
        finally:
            last.close()
        assert out["closed"] is True and out["state"] == NodeState.TERMINATED.value
        kinds = [r["kind"] for r in _rows(tmp_path)]
        assert kinds == ["spawn", "transition", "transition", "exit"]
        assert verify_file(tmp_path / "nodes" / "node_events.jsonl").ok is True

    def test_a_session_that_never_spawned_still_closes_from_spawning(self, tmp_path: Path) -> None:
        """The ticket was authorized and the shell then failed to spawn. The record must not be left
        reading SPAWNING forever — that is the D-LOOP-1 leak in the auditor's own file."""
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id=SESSION, lease_id="lease-1")
        finally:
            first.close()
        last = _registrar(tmp_path)
        try:
            out = last.close_session_record(f"worker-{PANE}", session_id=SESSION, exit_code=None,
                                            expected=False)
        finally:
            last.close()
        assert out["closed"] is True
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn", "transition", "exit"]

    def test_closing_twice_is_reported_not_re_written(self, tmp_path: Path) -> None:
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id=SESSION, lease_id="lease-1")
        finally:
            first.close()
        for _ in range(2):
            reg = _registrar(tmp_path)
            try:
                out = reg.close_session_record(f"worker-{PANE}", session_id=SESSION, exit_code=0,
                                           expected=True)
            finally:
                reg.close()
        assert out["closed"] is False and "already" in out["reason"].lower()
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn", "transition", "exit"]

    def test_attesting_a_node_that_was_never_registered_is_refused(self, tmp_path: Path) -> None:
        reg = _registrar(tmp_path)
        try:
            with pytest.raises(ProviderNodeRegistrationRefused) as exc:
                reg.attest_spawned("worker-pane-never", session_id=SESSION, pid=os.getpid())
        finally:
            reg.close()
        assert exc.value.gate == GATE_UNKNOWN_NODE

    def test_a_relaunch_of_the_same_pane_is_the_next_incarnation(self, tmp_path: Path) -> None:
        for session_id in ("pane-7#1.1", "pane-7#1.2"):
            reg = _registrar(tmp_path)
            try:
                if session_id != "pane-7#1.1":
                    reg.close_session_record(f"worker-{PANE}", session_id=SESSION, exit_code=0,
                                           expected=True)
                out = reg.register_pane_session(_pane_session(), session_id=session_id,
                                                lease_id="lease-1")
            finally:
                reg.close()
        assert out.incarnation == 2
        spawns = [r for r in _rows(tmp_path) if r["kind"] == "spawn"]
        assert [r["incarnation"] for r in spawns] == [1, 2]


# ---- 4. rehydrate is a fence, not a convenience ---------------------------------------------------

class TestRehydrateRestoresTheCacheWithoutWritingAnything:
    def test_rehydrating_writes_no_event(self, tmp_path: Path) -> None:
        log = AppendOnlyEventLog(tmp_path / "n.jsonl")
        try:
            NodeRegistry(log).register("worker-pane-7", "worker_reasoning", GROK_ADAPTER,
                                       spawned_by_supervisor=True)
            before = (tmp_path / "n.jsonl").read_text(encoding="utf-8")
            fresh = NodeRegistry(log)          # a new view over the SAME log: nothing in memory
            fresh.rehydrate(NodeRecord(node_id="worker-pane-7", incarnation=1,
                                       node_class="worker_reasoning", adapter=GROK_ADAPTER))
            assert fresh.get("worker-pane-7").incarnation == 1
        finally:
            log.close()
        assert (tmp_path / "n.jsonl").read_text(encoding="utf-8") == before

    def test_rehydrating_a_record_the_log_does_not_carry_is_refused(self, tmp_path: Path) -> None:
        """The fence that makes "it cannot conjure a node the log does not carry" a property of the
        code instead of a sentence about callers: a restored record can be transitioned and closed,
        and THOSE append — so a fabricated one would put `transition`+`exit` rows on the chain for
        a node with no `spawn` row."""
        log = AppendOnlyEventLog(tmp_path / "n.jsonl")
        try:
            registry = NodeRegistry(log)
            with pytest.raises(RegistrationRefused, match="no `spawn` row"):
                registry.rehydrate(NodeRecord(node_id="worker-pane-never", incarnation=1,
                                              node_class="worker_reasoning", adapter=GROK_ADAPTER))
            # …and a real node at the WRONG incarnation is refused by the same fence.
            registry.register("worker-pane-7", "worker_reasoning", GROK_ADAPTER,
                              spawned_by_supervisor=True)
            with pytest.raises(RegistrationRefused, match="no `spawn` row"):
                NodeRegistry(log).rehydrate(NodeRecord(
                    node_id="worker-pane-7", incarnation=7, node_class="worker_reasoning",
                    adapter=GROK_ADAPTER))
        finally:
            log.close()

    def test_rehydrating_an_adapter_no_schema_version_admits_is_refused(self, tmp_path: Path) -> None:
        """The VOCABULARY fence specifically — so the spawn-row fence added later cannot stand in
        for it: the log genuinely carries this node's spawn row, and only the adapter is wrong."""
        log = AppendOnlyEventLog(tmp_path / "n.jsonl")
        try:
            NodeRegistry(log).register("n", "worker_reasoning", GROK_ADAPTER,
                                       spawned_by_supervisor=True)
            with pytest.raises(RegistrationRefused, match="not an enum member"):
                NodeRegistry(log).rehydrate(NodeRecord(node_id="n", incarnation=1,
                                                       node_class="worker_reasoning",
                                                       adapter="kimi_k3"))
        finally:
            log.close()

    def test_rehydrating_over_a_live_key_is_refused(self, tmp_path: Path) -> None:
        log = AppendOnlyEventLog(tmp_path / "n.jsonl")
        try:
            registry = NodeRegistry(log)
            registry.register("worker-pane-7", "worker_reasoning", GROK_ADAPTER,
                              spawned_by_supervisor=True)
            with pytest.raises(RegistrationRefused):
                registry.rehydrate(NodeRecord(node_id="worker-pane-7", incarnation=1,
                                              node_class="worker_reasoning", adapter=GROK_ADAPTER))
        finally:
            log.close()


# ---- 5. the emitter: the product path ------------------------------------------------------------

class TestTheTicketRegistersThePanesNode:
    def test_an_op12_frontier_ticket_carries_a_measured_registration(self, tmp_path: Path) -> None:
        t = _ticket(tmp_path)
        assert t["authorized"] is True
        reg = t["node_registration"]
        assert reg["registered"] is True
        assert reg["schema_version"] == "node@1.1"
        assert reg["node_key"] == f"worker-{PANE}"
        assert reg["incarnation"] == 1
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]

    def test_a_registration_refusal_refuses_the_session_and_hands_the_terminal_back(
            self, tmp_path: Path) -> None:
        """18D's rule, on the pane path: a leased supervised terminal with no record is the
        naked-but-leased session the chain exists to prevent."""
        led = _ledger(tmp_path)
        registrar = _registrar(tmp_path)

        def _boom(*_a, **_k):
            raise ProviderNodeRegistrationRefused("registrar says no", gate=GATE_RECORD_INVALID)

        registrar.register_pane_session = _boom          # type: ignore[method-assign]
        t = _ticket(tmp_path, ledger=led, registrar=registrar)
        assert t["authorized"] is False
        assert t["refused_by"] == GATE_RECORD_INVALID
        assert t["lease"] is None
        assert led.in_use(canonical_subscription_ref(GROK_ADAPTER)) == 0

    def test_a_registrar_of_none_means_exactly_no_record_and_says_so(self, tmp_path: Path) -> None:
        """`None` is legitimate and is not a silent skip: the ticket reports `registered:false`
        with the reason, so a receipt can tell "no record" from "a record nobody looked for"."""
        t = _ticket(tmp_path, registrar=None)
        assert t["authorized"] is True
        assert t["node_registration"]["registered"] is False
        assert t["node_registration"]["reason"]
        assert not (tmp_path / "nodes" / "node_events.jsonl").exists()

    def test_a_non_op12_frontier_pane_is_reported_as_out_of_scope_not_as_registered(
            self, tmp_path: Path) -> None:
        sel = _selection(CLAUDE_CODE_ADAPTER, slug=None)
        t = _ticket(tmp_path, selection=sel, offered_options=_offered(sel),
                    live_auth=LiveAuthorization(
                        authorized=True, providers=frozenset((CLAUDE_CODE_ADAPTER,)),
                        terminals_per_subscription=2, register_row="OP-6", source="(test)",
                        reason="test"))
        assert t["authorized"] is True
        assert t["node_registration"]["registered"] is False
        assert "OP-12" in t["node_registration"]["reason"]

    def test_a_registration_refusal_after_the_record_was_written_closes_it(
            self, tmp_path: Path, monkeypatch) -> None:
        """A governance refusal raised AFTER `_register_pane_node` succeeded left a SPAWNING record
        on an append-only log while the refusal ticket asserted none existed. The record cannot be
        un-written, so it is CLOSED and the outcome is reported (validator MINOR-3)."""
        registrar = _registrar(tmp_path)
        # The refusal is forced at the FIRST step after registration returns — building the chrome
        # for the ticket payload. `ValueError` is a governance refusal in this emitter, so this is
        # the real branch, reached the real way.
        monkeypatch.setattr(WorkerPaneChrome, "as_dict", _raise_later)
        led = _ledger(tmp_path)
        t = _ticket(tmp_path, ledger=led, registrar=registrar)
        assert t["authorized"] is False
        assert t["node_registration"]["registered"] is True     # measured, not the old declaration
        assert t["node_registration"]["closed_on_refusal"]["closed"] is True
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn", "transition", "exit"]
        assert led.in_use(canonical_subscription_ref(GROK_ADAPTER)) == 0

    def test_the_registrar_is_a_required_keyword(self) -> None:
        """Whether a session becomes a Sovereign node is the CALLER's fact, exactly as the profile
        and the operator's terms determination are (U283/U292(a)). A default would let this module
        answer it for everyone."""
        import inspect

        param = inspect.signature(build_worker_launch_ticket).parameters["registrar"]
        assert param.default is inspect.Parameter.empty


class TestTheAttestationAndReleaseModes:
    def test_the_attestation_moves_the_record_to_ready_with_the_pid(self, tmp_path: Path) -> None:
        _ticket(tmp_path)
        out = build_worker_pane_spawn_attestation(
            f"worker-{PANE}", session_id=SESSION, pid=os.getpid(),
            registrar=_registrar(tmp_path))
        assert out["attested"] is True and out["pid"] == os.getpid()
        assert out["error"] is None
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn", "transition"]

    def test_the_attestation_never_raises_and_reports_its_refusal(self, tmp_path: Path) -> None:
        out = build_worker_pane_spawn_attestation(
            "worker-pane-never", session_id=SESSION, pid=os.getpid(),
            registrar=_registrar(tmp_path))
        assert out["attested"] is False and out["error"]

    def test_a_non_positive_pid_is_refused(self, tmp_path: Path) -> None:
        """By the SHAPE check, named. The liveness check would also refuse 0, so asserting only
        "refused" would let this row stand in for the other fence — and then deleting the shape
        check would leave the suite green while `attest_spawned(pid=0)` reached `pid_is_alive`."""
        _ticket(tmp_path)
        for bad in (0, -7, True):
            out = build_worker_pane_spawn_attestation(
                f"worker-{PANE}", session_id=SESSION, pid=bad, registrar=_registrar(tmp_path))
            assert out["attested"] is False
            assert "needs the supervised session's live pid" in out["error"], (
                f"pid={bad!r} must be refused by the SHAPE check, not by liveness: {out['error']}")
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]

    def test_releasing_the_session_closes_its_node_record(self, tmp_path: Path) -> None:
        led = _ledger(tmp_path)
        t = _ticket(tmp_path, ledger=led)
        assert t["authorized"] is True
        out = build_worker_lease_release_session(SESSION, ledger=led,
                                                 registrar=_registrar(tmp_path))
        assert out["released"] is True
        assert out["node_record"]["closed"] is True
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn", "transition", "exit"]

    def test_the_release_closes_the_record_even_when_no_lease_remains(self, tmp_path: Path) -> None:
        """The lease may already have been reaped (a dead holder) while the record is still open.
        A release that only reported the lease would leave the node reading SPAWNING forever."""
        led = _ledger(tmp_path)
        _ticket(tmp_path, ledger=led)
        led.release_session(canonical_subscription_ref(GROK_ADAPTER), SESSION)
        out = build_worker_lease_release_session(SESSION, ledger=led,
                                                 registrar=_registrar(tmp_path))
        assert out["released"] is False
        assert out["node_record"]["closed"] is True

    def test_the_release_reports_a_session_it_has_no_record_for(self, tmp_path: Path) -> None:
        out = build_worker_lease_release_session("pane-9#1.1", ledger=_ledger(tmp_path),
                                                 registrar=_registrar(tmp_path))
        assert out["node_record"]["closed"] is False
        assert out["error"] is None            # nothing to close is not an error


class TestTheSessionBindingBothReviewersFound:
    """A pane id is REUSED across sessions. Both reviewers independently found the same class of
    defect in the first cut: `attest_spawned` and `close_session_record` took only the node KEY and
    acted on "the latest record for this pane", so a stale record left open by a crashed shell
    could be attested READY with an unrelated process's pid, and a late release for session A could
    write TERMINATED against session B's still-live record — on an append-only log, permanently.
    """

    def _registered(self, tmp_path: Path, session_id: str) -> None:
        reg = _registrar(tmp_path)
        try:
            reg.register_pane_session(_pane_session(), session_id=session_id, lease_id="lease-1")
        finally:
            reg.close()

    def test_another_sessions_record_is_never_attested(self, tmp_path: Path) -> None:
        self._registered(tmp_path, "pane-7#OLD.1")
        reg = _registrar(tmp_path)
        try:
            with pytest.raises(ProviderNodeRegistrationRefused) as exc:
                reg.attest_spawned(f"worker-{PANE}", session_id="pane-7#NEW.2", pid=os.getpid())
        finally:
            reg.close()
        assert exc.value.gate == GATE_UNKNOWN_NODE
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]

    def test_another_sessions_record_is_never_closed(self, tmp_path: Path) -> None:
        self._registered(tmp_path, "pane-7#OLD.1")
        reg = _registrar(tmp_path)
        try:
            out = reg.close_session_record(f"worker-{PANE}", session_id="pane-7#NEW.2",
                                           exit_code=0, expected=True)
        finally:
            reg.close()
        assert out["closed"] is False and out["gate"] == GATE_UNKNOWN_NODE
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]

    def test_a_release_for_a_different_session_leaves_the_live_record_open(
            self, tmp_path: Path) -> None:
        """The whole failure scenario, through the product path: a live session's record must
        survive a late release carrying someone else's key."""
        led = _ledger(tmp_path)
        _ticket(tmp_path, ledger=led)                       # SESSION is registered and live
        out = build_worker_lease_release_session("pane-7#STALE.9", ledger=led,
                                                 registrar=_registrar(tmp_path))
        assert out["node_record"]["closed"] is False
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]

    def test_a_dead_pid_is_refused_rather_than_recorded_as_ready(self, tmp_path: Path) -> None:
        """`pid > 0` was the whole check while the docstring said "refuse to record READY for a
        process nobody observed". Liveness is what makes the attestation an observation."""
        self._registered(tmp_path, SESSION)
        reg = _registrar(tmp_path)
        try:
            with pytest.raises(ProviderNodeRegistrationRefused, match="not a live process"):
                # 2**31-2: a pid no live process on this host can hold.
                reg.attest_spawned(f"worker-{PANE}", session_id=SESSION, pid=2147483646)
        finally:
            reg.close()
        assert [r["kind"] for r in _rows(tmp_path)] == ["spawn"]


class TestTheStaleIncarnationReap:
    def test_a_prior_incarnation_left_open_by_a_dead_process_is_closed_not_stranded(
            self, tmp_path: Path) -> None:
        """A shell that dies between spawn and release leaves a record open forever, and
        `_next_incarnation` simply counts past it. The durable lease ledger reaps a dead holder's
        lease; the node log now does the same, on the same rule."""
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id="pane-7#1.1",
                                        lease_id="lease-1")
        finally:
            first.close()                                    # …and nothing ever closes it
        second = _registrar(tmp_path)
        try:
            out = second.register_pane_session(_pane_session(), session_id="pane-7#2.1",
                                               lease_id="lease-2")
        finally:
            second.close()
        assert out.incarnation == 2
        kinds = [r["kind"] for r in _rows(tmp_path)]
        # spawn#1, then the REAP of #1 (transition + exit), then spawn#2
        assert kinds == ["spawn", "transition", "exit", "spawn"]
        assert verify_file(tmp_path / "nodes" / "node_events.jsonl").ok is True

    def test_a_prior_incarnation_under_a_LIVE_pid_refuses_the_new_one(self, tmp_path: Path) -> None:
        first = _registrar(tmp_path)
        try:
            first.register_pane_session(_pane_session(), session_id="pane-7#1.1",
                                        lease_id="lease-1")
            first.attest_spawned(f"worker-{PANE}", session_id="pane-7#1.1", pid=os.getpid())
        finally:
            first.close()
        second = _registrar(tmp_path)
        try:
            with pytest.raises(ProviderNodeRegistrationRefused) as exc:
                second.register_pane_session(_pane_session(), session_id="pane-7#2.1",
                                             lease_id="lease-2")
        finally:
            second.close()
        assert exc.value.gate == GATE_UNGOVERNED_SESSION
        assert "LIVE pid" in str(exc.value)


class TestEveryPayloadNamesTheLogItIsAbout:
    """`SOW_NODE_EVENT_LOG` can redirect the durable node log, so `registered:true` without a path
    is a claim that could be about a scratch file — the 18D `real_switch` defect one layer out."""

    def test_the_ticket_the_attestation_and_the_release_all_name_the_path(
            self, tmp_path: Path) -> None:
        expected = str(tmp_path / "nodes" / "node_events.jsonl")
        led = _ledger(tmp_path)
        t = _ticket(tmp_path, ledger=led)
        assert t["node_registration"]["log_path"] == expected
        att = build_worker_pane_spawn_attestation(f"worker-{PANE}", session_id=SESSION,
                                                  pid=os.getpid(), registrar=_registrar(tmp_path))
        assert att["log_path"] == expected
        rel = build_worker_lease_release_session(SESSION, ledger=led,
                                                 registrar=_registrar(tmp_path))
        assert rel["node_record"]["log_path"] == expected

    def test_a_no_record_answer_names_it_too(self, tmp_path: Path) -> None:
        sel = _selection(CLAUDE_CODE_ADAPTER, slug=None)
        t = _ticket(tmp_path, selection=sel, offered_options=_offered(sel),
                    live_auth=LiveAuthorization(
                        authorized=True, providers=frozenset((CLAUDE_CODE_ADAPTER,)),
                        terminals_per_subscription=2, register_row="OP-6", source="(test)",
                        reason="test"))
        assert t["node_registration"]["registered"] is False
        assert t["node_registration"]["log_path"] == str(tmp_path / "nodes" / "node_events.jsonl")


class TestTheLocalPaneBranch:
    """MEDIUM-5 both reviewers found: the test named for this rule exercised the FRONTIER path, and
    the local branch's own no-record reason had no coverage anywhere.

    EPC-03 D-1: that no-record reason is gone. The local branch now calls the registrar, so
    this class asserts the CURRENT contract - a local pane is a Sovereign node named by its
    residency reservation. The claude_code / codex siblings above still assert no-record,
    because those adapters remain genuinely unwired (U313's other owed leg)."""

    def test_a_local_pane_holds_no_terminal_and_gets_no_node_record(self, tmp_path: Path) -> None:
        from scheduler.residency_planner.residency_planner import ResidencyPlanner

        planner = ResidencyPlanner(12288)
        planner.register_model("qwen3:8b", 5200)
        sel = {"option": {"provider": "ollama_local", "adapter": "ollama_local",
                          "locality": "local", "subscription_backed": False, "label": "qwen3:8b",
                          "model_slug": "qwen3:8b", "verified": True, "is_fallback": False,
                          "roles": ["reasoning", "coding"], "residency": "not_loaded",
                          "available": True, "unavailable_reason": None},
               "role": "reasoning", "mode": "attended"}
        t = _ticket(tmp_path, selection=sel, offered_options=_offered(sel),
                    residency_planner=planner, ollama_present=True,
                    residency_budget={"vram_budget_mb": 12288, "budget_source": "(test)",
                                      "estimate": True, "established": True})
        # EPC-03 D-1. This asserted the OPPOSITE contract - that a local pane gets no node
        # record - and it was right about the code while the code was wrong about the design.
        # Invariant 2: "every terminal is a Sovereign node". U313 records the two-provider
        # wiring as the GAP, not the intent. So a local pane now registers, and what it names
        # is its ResidencyPlanner reservation rather than a subscription it does not hold.
        #
        # Inverted under an explicit operator decision (ENTRY 036), not because the code
        # started failing it. The distinction matters: a test changed to match broken code is
        # how a guard is disarmed, and this file is where that would show.
        assert t["authorized"] is True
        assert t["subscription_governed"] is False
        assert t["lease"] is None, "a local pane still holds NO subscription terminal"
        assert t["node_registration"]["registered"] is True
        assert t["node_registration"]["node_key"]
        assert t["node_registration"]["schema_version"] == "node@1.1"
        # The row is real and on disk, and it describes a LOCAL node.
        log = tmp_path / "nodes" / "node_events.jsonl"
        assert log.exists(), "a registered local pane must leave a durable row"
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        assert len(rows) == 1
        record = rows[0]["data"]["node_record"]
        assert record["class"] == "worker_reasoning", "node class must never be null"
        assert record["locality"] == "local", "a local pane must not be recorded as frontier"
        assert record["subscription_ref"] is None, "it holds no subscription to name"
        assert rows[0]["data"]["lease_id"] == "", "no synthetic lease"


class TestTheCliContract:
    """The three shell-facing modes, exercised through `main()` — the surface the shell actually
    invokes. A mode that only works when called as a function is a mode the shell cannot use."""

    def test_the_attestation_mode_prints_one_json_line_and_exits_zero(
            self, tmp_path: Path, monkeypatch, capsys) -> None:
        monkeypatch.setenv("SOW_NODE_EVENT_LOG", str(tmp_path / "n.jsonl"))
        code = main(["--record-pane-spawned", "worker-pane-7", "--session-id", SESSION,
                     "--pid", str(os.getpid())])
        out = json.loads(capsys.readouterr().out.strip())
        assert code == 0
        assert out["schema"] == "worker_pane_spawn_attestation@1.0"
        # No record exists on this scratch log, so the honest answer is a REFUSAL reported in a
        # well-formed payload — never a crash, and never `attested:true`.
        assert out["attested"] is False and out["error"]

    def test_the_attestation_mode_refuses_a_missing_pid_with_no_json(self, capsys) -> None:
        assert main(["--record-pane-spawned", "worker-pane-7", "--session-id", SESSION]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "--pid" in captured.err

    def test_the_attestation_mode_refuses_a_missing_node_key_with_no_json(self, capsys) -> None:
        assert main(["--record-pane-spawned", "--session-id", SESSION, "--pid", "10"]) == 2
        assert capsys.readouterr().out == ""

    def test_the_usage_text_names_the_new_mode(self, capsys) -> None:
        assert main([]) == 2
        assert "--record-pane-spawned" in capsys.readouterr().err
