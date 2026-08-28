"""Phase 18D `.close` — the wiring OP-12.1 authorized: a governed OP-12 provider session becomes a
Sovereign node RECORD.

18D `.amendment` opened the vocabulary (`schemas/node.schema@1.1.json`, OP-12.1) and deliberately
wired nothing to it — the amendment's own commit says so, and `provider_probe_session` still
reported `node_registered: False`. These tests are the other half: the registrar that turns a
`GovernedProbeSession` into a schema-valid `node@1.1` record on the append-only log, and the
refusals that make it a fence rather than a formality.

Every test here asserts on a MEASURED value from the real modules — the real `NodeRegistry`, the
real hash-chained `AppendOnlyEventLog`, the real schema files on disk, the real jsonschema
validator. Nothing is stubbed except the filesystem location (tmp_path) and, in the session tests,
the CLI binary that is never executed.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER
from control_plane.nodes.event_log import AppendOnlyEventLog, verify_file
from control_plane.nodes.registry import RegistrationRefused
from control_plane.nodes.states import NodeState
from node_runtime.supervisor.provider_node_registration import (
    GATE_LOG_LOCKED,
    GATE_RECORD_INVALID,
    GATE_UNGOVERNED_SESSION,
    GATE_UNKNOWN_NODE,
    GATE_UNSUPERVISED_SESSION,
    NODE_EVENT_LOG_RELPATH,
    ProviderNodeRegistrar,
    ProviderNodeRegistrationRefused,
    build_provider_node_record,
    default_node_event_log_path,
    node_record_uuid,
    validate_node_record,
)
from node_runtime.supervisor.provider_probe_session import GovernedProbeSession

REPO_ROOT = Path(__file__).resolve().parents[2]


def _session(provider: str = GROK_ADAPTER, **kw) -> GovernedProbeSession:
    """A session document shaped exactly as `governed_probe_session` yields one. Built directly
    (rather than by entering the context manager) so these tests measure the REGISTRAR; the wiring
    itself is measured in `TestTheProbeSessionRegistersItsNode` against the real context manager."""
    params = {
        "provider": provider, "display": "Grok Build", "node_id": "probe-grok",
        "session_id": "s1", "permission_profile_id": "pp-probe-reasoning", "role": "reasoning",
        "subscription_ref": f"{provider}_subscription", "allowance": 1, "in_use": 1,
        "lease_id": "lease-abc", "executable": "C:/fake/grok.CMD", "workspace": "C:/ws",
        "env_scrub_names": ("XAI_API_KEY",),
    }
    params.update(kw)
    return GovernedProbeSession(**params)


def _registrar(tmp_path: Path) -> ProviderNodeRegistrar:
    return ProviderNodeRegistrar(tmp_path / "nodes" / "node_events.jsonl")


# ---- the record document -------------------------------------------------------------------

class TestTheRecordIsSchemaValidAndDerived:
    def test_both_op12_providers_produce_a_record_that_validates_against_node_1_1(self) -> None:
        for provider in (GROK_ADAPTER, ANTIGRAVITY_ADAPTER):
            record = build_provider_node_record(_session(provider))
            assert record["adapter"] == provider
            assert record["schema"] == "node@1.1"
            # the real validator against the real file — not a shape assertion
            assert validate_node_record(record) == "node@1.1"

    def test_the_node_id_is_a_uuid_derived_from_the_lease_key_not_a_random_one(self) -> None:
        """`node_id` is `format: uuid` in the schema while the registry's key is the human
        `probe-grok`. The record's uuid is therefore DERIVED (uuid5) from the lease key, so the
        same governed session always yields the same record id and two sessions never collide."""
        s = _session()
        first = build_provider_node_record(s)["node_id"]
        assert first == build_provider_node_record(s)["node_id"]
        assert uuid.UUID(first).version == 5
        assert first != build_provider_node_record(_session(session_id="s2"))["node_id"]
        assert first == node_record_uuid("probe-grok#s1")
        # …and the incarnation is part of the derivation (see the registrar test that pairs here)
        assert first != build_provider_node_record(s, incarnation=2)["node_id"]

    def test_the_capability_list_is_the_adapters_own_never_re_declared(self) -> None:
        from adapters.frontier.antigravity import ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS
        from adapters.frontier.grok_build import GROK_REASONING_CAPABILITY_DESCRIPTORS

        assert (build_provider_node_record(_session(GROK_ADAPTER))["capabilities"]
                == GROK_REASONING_CAPABILITY_DESCRIPTORS)
        assert (build_provider_node_record(_session(ANTIGRAVITY_ADAPTER))["capabilities"]
                == ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS)

    def test_a_frontier_record_is_never_offline_eligible_and_names_its_subscription(self) -> None:
        record = build_provider_node_record(_session())
        assert record["locality"] == "frontier"
        assert record["offline_profile_eligible"] is False
        assert record["subscription_ref"] == "grok_build_subscription"
        assert record["spawned_by_supervisor"] is True
        assert record["state"] == NodeState.SPAWNING.value

    def test_the_auth_block_carries_a_reference_and_no_credential_material(self) -> None:
        """§2.2/§13: `mcp_credential_id` is a REFERENCE to an MCP identity, never a provider
        secret, and the record must not carry a scrubbed environment NAME's value either."""
        record = build_provider_node_record(_session())
        assert set(record["auth"]) == {"mcp_credential_id"}
        assert record["auth"]["mcp_credential_id"] == "mcp-ref"
        blob = json.dumps(record)
        for banned in ("XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "api_key", "token"):
            assert banned not in blob

    def test_a_record_the_vocabulary_does_not_admit_is_refused_by_the_validator(self) -> None:
        record = build_provider_node_record(_session())
        record["adapter"] = "kimi_k3"
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            validate_node_record(record)
        assert exc.value.gate == GATE_RECORD_INVALID

    def test_an_unknown_schema_version_is_refused_rather_than_skipped(self) -> None:
        record = build_provider_node_record(_session())
        record["schema"] = "node@9.9"
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            validate_node_record(record)
        assert exc.value.gate == GATE_RECORD_INVALID
        assert "node@9.9" in str(exc.value)


# ---- the registrar -------------------------------------------------------------------------

class TestRegistrationIsRealAndAuditable:
    def test_registering_a_governed_session_writes_a_verifiable_append_only_record(
            self, tmp_path: Path) -> None:
        reg = _registrar(tmp_path)
        result = reg.register_session(_session())
        assert result.adapter == GROK_ADAPTER
        assert result.adapter_schema_version == "node@1.1"   # the amendment, not the frozen file
        assert result.validated_against == "node@1.1"
        assert result.node_key == "probe-grok"
        assert result.record["node_id"] == node_record_uuid("probe-grok#s1")
        # the log is the record — read it back rather than trusting the return value
        chain = verify_file(reg.log_path)
        assert chain.ok and chain.rows == 1
        row = json.loads(reg.log_path.read_text(encoding="utf-8").splitlines()[0])
        assert row["kind"] == "spawn" and row["node_id"] == "probe-grok"
        assert row["data"]["adapter"] == GROK_ADAPTER
        assert row["data"]["adapter_schema_version"] == "node@1.1"
        assert row["data"]["node_record"]["schema"] == "node@1.1"
        assert row["data"]["lease_id"] == "lease-abc"           # the terminal it was counted under

    def test_both_providers_register_and_are_counted_as_live_nodes(self, tmp_path: Path) -> None:
        reg = _registrar(tmp_path)
        reg.register_session(_session(GROK_ADAPTER))
        reg.register_session(_session(ANTIGRAVITY_ADAPTER, node_id="probe-agy",
                                      display="Gemini · Antigravity",
                                      subscription_ref="google_antigravity_subscription"))
        adapters = sorted(r.adapter for r in reg.registry.alive())
        assert adapters == [ANTIGRAVITY_ADAPTER, GROK_ADAPTER]

    def test_a_session_that_is_not_supervised_is_refused_before_anything_is_written(
            self, tmp_path: Path) -> None:
        """I-C1 / invariant 2. The registry's own `spawned_by_supervisor` guard is downstream of
        this one; what this asserts is that the registrar never ASSERTS supervision on the
        session's behalf — it reads the session's own field."""
        reg = _registrar(tmp_path)
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            reg.register_session(_session(supervised=False))
        assert exc.value.gate == GATE_UNSUPERVISED_SESSION
        assert not reg.log_path.exists() or verify_file(reg.log_path).rows == 0

    def test_an_id_no_schema_version_admits_is_refused_twice_over(self, tmp_path: Path) -> None:
        """The fence moved at `.amendment`; it did not open. `kimi_k3` is the live example and is
        OWED-pending-operator. It is refused by the record builder (this module governs two
        providers and knows nothing about a third) AND, independently, by the registry fence with
        its auditable append-only event — which is the one that would matter if this module ever
        acquired a third provider without the operator ruling for it."""
        reg = _registrar(tmp_path)
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            reg.register_session(_session("kimi_k3"))
        assert exc.value.gate == GATE_RECORD_INVALID
        assert not reg.log_path.exists() or verify_file(reg.log_path).rows == 0

        with pytest.raises(RegistrationRefused):
            reg.registry.register("n1", "worker_reasoning", "kimi_k3", spawned_by_supervisor=True)
        rows = [json.loads(ln) for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        assert [r["kind"] for r in rows] == ["registration_refused"]
        assert "kimi_k3" in rows[0]["data"]["reason"]

    def test_supervision_must_be_exactly_True_not_merely_truthy(self, tmp_path: Path) -> None:
        """`is not True` rather than `not …`, and the strictness is PINNED: the validator's own
        mutation loosening it stayed green against the whole suite (MINOR-1). A truthy `1` or a
        non-empty string is a value nothing in this repo sets deliberately — it is what a partial
        deserialization or a hand-built object produces, and it must not attest I-C1."""
        reg = _registrar(tmp_path)
        for truthy in (1, "yes", [1]):
            with pytest.raises(ProviderNodeRegistrationRefused) as exc:
                reg.register_session(_session(supervised=truthy))
            assert exc.value.gate == GATE_UNSUPERVISED_SESSION

    def test_the_provenance_follows_the_vocabulary_it_reads(
            self, tmp_path: Path, monkeypatch) -> None:
        """"Derived, never re-declared" was unpinned: hardcoding `'node@1.1'` in place of the
        `adapter_version_map()` lookup stayed green on the whole suite (validator MINOR-2), because
        on this tree the two agree. Move the vocabulary and the report must move with it."""
        import node_runtime.supervisor.provider_node_registration as M

        monkeypatch.setattr(M, "adapter_version_map", lambda: {GROK_ADAPTER: "node@1.0"})
        reg = _registrar(tmp_path)
        assert reg.register_session(_session()).adapter_schema_version == "node@1.0"

    def test_a_record_that_would_not_validate_is_refused_at_registration(
            self, tmp_path: Path) -> None:
        """The validation on the registration path is REAL — not the builder agreeing with itself.

        Without this the schema check could be deleted and every suite would stay green, because
        every record these tests build happens to be valid (mutation C2 was GREEN when first run).
        A permission profile that is not a string is the cheapest way to make a well-built record
        schema-invalid, and it is not academic: `permission_profile_id` is the broker's key."""
        reg = _registrar(tmp_path)
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            reg.register_session(_session(permission_profile_id=123))
        assert exc.value.gate == GATE_RECORD_INVALID
        assert "permission_profile_id" in str(exc.value)
        assert not reg.registry.alive()          # nothing was registered on the way to refusing

    def test_the_registry_refuses_a_node_record_payload_that_disagrees_with_it(
            self, tmp_path: Path) -> None:
        """`node_record` is a CANONICAL DOCUMENT landing on an append-only log, and the registry's
        own argument for the adapter enum applies to it: the guarantee must be a property of the
        code, not of the one caller that writes it correctly today. The validator wrote a non-node
        document naming `kimi_k3` onto a verified chain through this API (MEDIUM-1)."""
        reg = _registrar(tmp_path)
        reg.register_session(_session())          # open the log honestly first
        for bad in ({"adapter": "kimi_k3", "this": "is not a node document"},
                    {"adapter": GROK_ADAPTER, "schema": "node@9.9", "node_id": "x"},
                    {"adapter": GROK_ADAPTER, "schema": "node@1.1"},           # no node_id
                    "not even an object"):
            with pytest.raises(RegistrationRefused) as exc:
                reg.registry.register("n-bad", "worker_reasoning", GROK_ADAPTER,
                                      spawned_by_supervisor=True, node_record=bad)
            assert "node_record" in str(exc.value)
        kinds = [json.loads(ln)["kind"]
                 for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        assert kinds.count("registration_refused") == 4      # every refusal auditable

    def test_the_reported_provenance_is_the_one_on_the_log(self, tmp_path: Path) -> None:
        """`register_session` derives `adapter_schema_version` and `NodeRegistry.register` writes
        its own onto the append-only event. Two derivations that nothing compares are two
        derivations that drift, so this compares them."""
        reg = _registrar(tmp_path)
        result = reg.register_session(_session())
        row = json.loads(reg.log_path.read_text(encoding="utf-8").splitlines()[0])
        assert result.adapter_schema_version == row["data"]["adapter_schema_version"] == "node@1.1"

    def test_there_is_no_way_to_register_without_a_validated_record(self) -> None:
        """No `validate=False`, no `force`, no `allow_*`: a vocabulary with an override is two
        vocabularies (the 18B fence's own MINOR-5 lesson, applied before it can recur)."""
        import inspect

        params = inspect.signature(ProviderNodeRegistrar.register_session).parameters
        assert list(params) == ["self", "session"]

    def test_the_exit_is_recorded_so_the_record_does_not_outlive_the_session(
            self, tmp_path: Path) -> None:
        """D-LOOP-1 in the node log: a one-shot probe's record must end TERMINATED, and the exit
        must be on the append-only log, or an auditor reading it sees a node still alive."""
        reg = _registrar(tmp_path)
        result = reg.register_session(_session())
        reg.record_exit(result, exit_code=0, expected=True)
        record = reg.registry.get(result.node_key)
        assert record.state is NodeState.TERMINATED
        kinds = [json.loads(ln)["kind"]
                 for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        assert kinds == ["spawn", "transition", "exit"]
        assert verify_file(reg.log_path).ok

    def test_recording_an_exit_for_a_node_that_was_never_registered_is_refused(
            self, tmp_path: Path) -> None:
        import dataclasses

        reg = _registrar(tmp_path)
        result = reg.register_session(_session())
        other = dataclasses.replace(result, node_key="probe-never")
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            reg.record_exit(other, exit_code=0, expected=True)
        assert exc.value.gate == GATE_UNKNOWN_NODE

    def test_a_duplicate_incarnation_is_refused_by_the_registry(self, tmp_path: Path) -> None:
        """`register_session` numbers incarnations itself, so it never asks for a duplicate — but
        the guard beneath it is what makes that safe, and it is asserted rather than assumed."""
        reg = _registrar(tmp_path)
        result = reg.register_session(_session())
        with pytest.raises(RegistrationRefused):
            reg.registry.register(result.node_key, "worker_reasoning", GROK_ADAPTER,
                                  spawned_by_supervisor=True, incarnation=result.incarnation)

    @pytest.mark.parametrize("second_session_id", ["s2", "s1"])
    def test_two_sessions_of_one_provider_are_two_incarnations_not_one_node(
            self, tmp_path: Path, second_session_id: str) -> None:
        """Same node id (derived from the provider's command), a second session — the U75 lesson
        the lease key already carries, now in the record: the second is incarnation 2 with its own
        uuid, never an idempotent re-registration of the first. Parametrised over a DIFFERENT and
        an IDENTICAL session id because the record uuid is derived, and a derivation that ignored
        the incarnation would give two rows of one append-only log the same `node_id`."""
        reg = _registrar(tmp_path)
        first = reg.register_session(_session(session_id="s1"))
        second = reg.register_session(_session(session_id=second_session_id))
        assert (first.incarnation, second.incarnation) == (1, 2)
        assert first.record["node_id"] != second.record["node_id"]

    def test_the_default_log_lives_in_the_gitignored_store_not_in_the_tree(self) -> None:
        """The node event log is durable operator state, like the lease ledger — never committed."""
        assert NODE_EVENT_LOG_RELPATH.parts[0] == ".sovereign_store"
        assert default_node_event_log_path(REPO_ROOT) == REPO_ROOT / NODE_EVENT_LOG_RELPATH
        assert ".sovereign_store/" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_constructing_a_registrar_writes_nothing(self, tmp_path: Path) -> None:
        """The log is opened when a node is REGISTERED, never when one is prepared for.
        `AppendOnlyEventLog.__init__` creates its directory and file, so an eager registrar wrote
        an empty `node_events.jsonl` into the operator's durable store for every probe refused at
        gate 1 — and for every test that merely walked the product call site (found by running the
        suite and looking at `.sovereign_store/`, not by a test)."""
        reg = ProviderNodeRegistrar(tmp_path / "nodes" / "node_events.jsonl")
        assert reg.log_path == tmp_path / "nodes" / "node_events.jsonl"   # readable without opening
        assert not (tmp_path / "nodes").exists()
        reg.register_session(_session())
        assert reg.log_path.exists()

    def test_a_refusal_for_an_ungoverned_id_leaves_no_log_behind(self, tmp_path: Path) -> None:
        reg = ProviderNodeRegistrar(tmp_path / "nodes" / "node_events.jsonl")
        with pytest.raises(ProviderNodeRegistrationRefused):
            reg.register_session(_session("kimi_k3"))
        with pytest.raises(ProviderNodeRegistrationRefused):
            reg.register_session(_session(supervised=False))
        assert not (tmp_path / "nodes").exists()

    def test_a_duck_typed_session_cannot_assert_i_c1_on_the_supervisors_behalf(
            self, tmp_path: Path) -> None:
        """The record carries `spawned_by_supervisor: true`. If any object with the right attribute
        names could get one written, that attestation would be the CALLER's claim published as the
        supervisor's — a namespace with `supervised=True` is one line (spec-audit MEDIUM-3)."""
        from types import SimpleNamespace

        reg = _registrar(tmp_path)
        impostor = SimpleNamespace(
            provider=GROK_ADAPTER, node_id="probe-fake", session_id="s", supervised=True,
            permission_profile_id="pp-probe-reasoning", subscription_ref="grok_build_subscription",
            lease_id="lease-x", workspace=str(tmp_path))
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            reg.register_session(impostor)
        assert exc.value.gate == GATE_UNGOVERNED_SESSION
        assert not (tmp_path / "nodes").exists()

    def test_a_session_holding_no_terminal_is_refused(self, tmp_path: Path) -> None:
        """A frontier node record names the subscription it was counted against. A governed
        session without a lease is not one this registrar can vouch for."""
        reg = _registrar(tmp_path)
        for kw in ({"lease_id": ""}, {"subscription_ref": "  "}):
            with pytest.raises(ProviderNodeRegistrationRefused) as exc:
                reg.register_session(_session(**kw))
            assert exc.value.gate == GATE_UNGOVERNED_SESSION

    def test_the_incarnation_comes_from_the_log_not_from_this_process(self, tmp_path: Path) -> None:
        """`NodeRegistry` never replays its log, so a fresh process computed incarnation 1 forever
        — and the node key is stable, so every probe run on the operator's host appended another
        incarnation-1 spawn row to an append-only file (spec-audit MEDIUM-2). A second registrar
        over the SAME file is the test, because that is what a second process is."""
        log = tmp_path / "nodes" / "node_events.jsonl"
        first = ProviderNodeRegistrar(log)
        a = first.register_session(_session())
        first.close()
        second = ProviderNodeRegistrar(log)
        b = second.register_session(_session())
        second.close()
        assert (a.incarnation, b.incarnation) == (1, 2)
        assert a.record["node_id"] != b.record["node_id"]

    def test_the_log_is_held_exclusively_while_a_registrar_owns_it(self, tmp_path: Path) -> None:
        """Two `AppendOnlyEventLog` objects over one file each cache `prev_hash` at open time, so
        two processes appending would write duplicate `seq` and break the chain — and a corrupt log
        cannot be opened again, which would wedge the governed-probe path with no repair an
        append-only log permits (spec-audit MEDIUM-5)."""
        log = tmp_path / "nodes" / "node_events.jsonl"
        holder = ProviderNodeRegistrar(log)
        holder.register_session(_session())
        contender = ProviderNodeRegistrar(log)
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            contender.registry
        assert exc.value.gate == GATE_LOG_LOCKED
        holder.close()
        # …and the lock is handed back, so the next one gets it
        assert ProviderNodeRegistrar(log).register_session(_session()).incarnation == 2

    def test_a_lock_whose_holder_is_gone_is_reclaimed_and_one_that_lives_is_not(
            self, tmp_path: Path) -> None:
        """A crash must not wedge the path forever — the durable lease ledger reaps a lease whose
        process is gone and this does the same. An unreadable stamp is treated as LIVE."""
        log = tmp_path / "nodes" / "node_events.jsonl"
        lock = Path(str(log) + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999999999", encoding="ascii")      # a pid that cannot be alive
        reg = ProviderNodeRegistrar(log)
        assert reg.register_session(_session()).incarnation == 1
        reg.close()
        lock.write_text("not-a-pid", encoding="ascii")
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            ProviderNodeRegistrar(log).registry
        assert exc.value.gate == GATE_LOG_LOCKED
        lock.unlink()

    def test_the_registrar_shares_one_registry_with_one_log(self, tmp_path: Path) -> None:
        """A registrar that opened a second `NodeRegistry` over the same file would keep two
        in-memory views of one append-only log — the duplicate check would pass twice."""
        log = AppendOnlyEventLog(tmp_path / "n.jsonl")
        reg = ProviderNodeRegistrar(log.path, log=log)
        reg.register_session(_session())
        assert reg.registry.alive()[0].adapter == GROK_ADAPTER
        assert verify_file(log.path).rows == 1


# ---- the wiring ------------------------------------------------------------------------------

class TestTheProbeSessionRegistersItsNode:
    """The measurement `provider_probe_session.node_registered` now reports, driven through the
    REAL context manager with all its gates satisfied by injected fixtures (no CLI is executed)."""

    def _open(self, tmp_path: Path, registrar, provider: str = GROK_ADAPTER, ledger=None):
        import json as _json

        from control_plane.profiles.live_authorization import load_live_authorization
        from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
        from node_runtime.supervisor.provider_probe_session import governed_probe_session
        from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger

        cfg = tmp_path / "live_operation.json"
        cfg.write_text(_json.dumps({
            "config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-12",
            "scope": {"providers": ["claude_code", "openai_codex_cli", GROK_ADAPTER,
                                    ANTIGRAVITY_ADAPTER],
                      "terminals_per_subscription": 2}}), encoding="utf-8")
        return governed_probe_session(
            provider, probe_id="grok", workspace=str(tmp_path),
            live_auth=load_live_authorization(path=cfg),
            ledger=ledger if ledger is not None else TerminalLeaseLedger(
                tmp_path / "leases.json", pid_alive=lambda _p: True),
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=True, cli_present=True,
            executable=str(tmp_path / "fake-cli"), holder_pid=4242, session_id="s1",
            registrar=registrar)

    def test_an_opened_session_is_a_registered_node_and_says_so(self, tmp_path: Path) -> None:
        reg = _registrar(tmp_path)
        with self._open(tmp_path, reg) as session:
            assert session.node_registered is True
            assert session.as_dict()["node_record"]["adapter_schema_version"] == "node@1.1"
            assert reg.registry.get("probe-grok").state is NodeState.SPAWNING
        # …and the record does not outlive the session (D-LOOP-1). Read from the LOG, because the
        # session hands the registry and the log's lock back on exit — asking the registrar again
        # would silently re-open and re-lock the file, which is the leak the close exists to stop.
        rows = [json.loads(ln) for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        assert [r["kind"] for r in rows] == ["spawn", "transition", "exit"]
        assert rows[1]["data"]["to"] == NodeState.TERMINATED.value
        assert session.teardown_record["node_exit_recorded"] is True
        assert session.teardown_record["node_exit_expected"] is True

    def test_registration_is_not_optional_and_cannot_be_defaulted_away(
            self, tmp_path: Path) -> None:
        """`registrar` is a REQUIRED keyword for the same reason `profile_loader` and
        `operator_terms_confirmed` are: a default here would be this module deciding whether the
        session it opens becomes a Sovereign node (invariant 2)."""
        from node_runtime.supervisor.provider_probe_session import governed_probe_session

        with pytest.raises(TypeError):
            governed_probe_session(GROK_ADAPTER, probe_id="grok", workspace=str(tmp_path),
                                   profile_loader=None, operator_terms_confirmed=True)

    def test_an_explicit_none_registrar_yields_an_honest_unregistered_session(
            self, tmp_path: Path) -> None:
        """`None` is permitted and means exactly one thing: no record was created, and the session
        says so. It is not a silent default — the caller had to write it."""
        with self._open(tmp_path, None) as session:
            assert session.node_registered is False
            assert session.as_dict()["node_record"] is None
        assert session.teardown_record["node_exit_recorded"] is False

    def test_a_session_that_ends_badly_is_recorded_as_an_UNEXPECTED_exit(
            self, tmp_path: Path) -> None:
        """The lease half of teardown was measured while the node half was asserted: every exit
        went onto the append-only log as `expected`, code `None`, including a session that raised
        (spec-audit MEDIUM-4). An auditor reading the operator's node history would see every
        crashed session as a clean one."""
        reg = _registrar(tmp_path)
        with pytest.raises(RuntimeError):
            with self._open(tmp_path, reg):
                raise RuntimeError("the body blew up")
        rows = [json.loads(ln) for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        exits = [r for r in rows if r["kind"] == "exit"]
        assert exits and exits[-1]["data"]["expected"] is False
        transitions = [r for r in rows if r["kind"] == "transition"]
        assert "unexpected" in transitions[-1]["data"]["reason"]

    def test_the_childs_own_exit_code_reaches_the_record(self, tmp_path: Path) -> None:
        """`None` reads the same for "ran and returned 0" and "never ran"; the runner knows which."""
        reg = _registrar(tmp_path)
        with self._open(tmp_path, reg) as session:
            session.child_exit_code = 0        # what `supervised_probe_runner` sets after a run
        rows = [json.loads(ln) for ln in reg.log_path.read_text(encoding="utf-8").splitlines()]
        assert [r for r in rows if r["kind"] == "exit"][-1]["data"]["exit_code"] == 0

    def test_the_session_hands_the_log_and_its_lock_back(self, tmp_path: Path) -> None:
        """D-LOOP-1 for the node log: a long-lived process must not leak a handle per probe, nor
        hold the log against the next probe."""
        reg = _registrar(tmp_path)
        with self._open(tmp_path, reg):
            assert Path(str(reg.log_path) + ".lock").exists()
        assert not Path(str(reg.log_path) + ".lock").exists()

    def test_a_refused_registration_refuses_the_session_and_releases_the_lease(
            self, tmp_path: Path) -> None:
        """Fail closed: if the node record cannot be written, the session must not proceed — and
        the I-X3 terminal it had already taken must come back."""
        from node_runtime.supervisor.terminal_lease import TerminalLeaseLedger

        class Refusing(ProviderNodeRegistrar):
            def register_session(self, session):
                raise ProviderNodeRegistrationRefused("no record for you",
                                                      gate=GATE_RECORD_INVALID)

        ledger = TerminalLeaseLedger(tmp_path / "leases.json", pid_alive=lambda _p: True)
        reg = Refusing(tmp_path / "nodes" / "n.jsonl")
        with pytest.raises(ProviderNodeRegistrationRefused):
            with self._open(tmp_path, reg, ledger=ledger):
                pass
        assert ledger.in_use("grok_build_subscription") == 0



class TestACorruptLogIsAnIntegrityRefusalNotAnArgvFault:
    """W-66. AppendOnlyEventLog refuses a corrupt log with a bare ValueError, and the
    emitter's routing table maps every ValueError to gate argv_builder - so corruption of
    the DURABLE HASH-CHAINED HISTORY reported as an argv-builder refusal. The registrar
    owns this boundary and converts the fault to its own refused class at source."""

    def _corrupt(self, log: Path) -> None:
        import json as _json
        lines = log.read_text(encoding="utf-8").splitlines()
        row = _json.loads(lines[0])
        row["seq"] = 99          # breaks the seq/hash linkage verify_file checks
        lines[0] = _json.dumps(row)
        log.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    def test_opening_the_registry_over_a_corrupt_log_refuses_with_an_integrity_gate(
            self, tmp_path: Path) -> None:

        log = tmp_path / "nodes" / "node_events.jsonl"
        first = ProviderNodeRegistrar(log)
        first.register_session(_session())
        first.close()
        self._corrupt(log)

        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            ProviderNodeRegistrar(log).registry

        assert exc.value.gate == "node_log_corrupt"
        assert "corrupt" in str(exc.value).lower()

    def test_registering_on_a_corrupt_log_is_refused_the_same_way(
            self, tmp_path: Path) -> None:

        log = tmp_path / "nodes" / "node_events.jsonl"
        first = ProviderNodeRegistrar(log)
        first.register_session(_session())
        first.close()
        self._corrupt(log)

        second = ProviderNodeRegistrar(log)
        with pytest.raises(ProviderNodeRegistrationRefused) as exc:
            second.register_session(_session())
        second.close()

        assert exc.value.gate == "node_log_corrupt"

    def test_the_emitter_routes_this_class_by_its_own_gate_not_argv_builder(self) -> None:
        """CONTROL/INHERITED: this refusal is a governance refusal whose gate id comes from
        the exception itself - never from the ValueError fallback that mislabelled
        durable-history corruption as an argv fault."""
        from tools.live.emit_worker_launch import _EXCEPTION_GATE, _GOVERNANCE_REFUSALS

        assert ProviderNodeRegistrationRefused in _GOVERNANCE_REFUSALS
        assert _EXCEPTION_GATE.get("ProviderNodeRegistrationRefused") != "argv_builder"
