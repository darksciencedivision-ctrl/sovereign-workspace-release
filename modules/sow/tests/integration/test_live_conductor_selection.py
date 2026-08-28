"""Phase 15D `.selection`: the operator's conductor SELECTION (fable-5, OP-6) is carried through the
REAL governed live-conductor spawn path, surfaced on EVERY outcome, and never conflated with the
executing checkpoint (directive §11 15D).

Proven here, through the real entrypoint + a REAL MCP server (mock backend only — no live call):
  1. The governed spawn requests the SELECTION's model by default (fable-5), not the CLI default.
  2. `conductor_selection` is surfaced on every smoke outcome — success AND skip-with-record — so
     which conductor was selected is never silent, exactly like `model_resolution` (§11 15B).
  3. The published CANDIDATE decision records the SELECTION and the executing model separately.
  4. An executing checkpoint differing from the selection LABEL is surfaced as a label mismatch
     (no label->checkpoint mapping exists yet); the selection is not rewritten.
  5. Succession + restore round-trips the record through the REAL SuccessionManager: the successor
     is `reason: succession`, and restoring returns the pinned operator selection with a new `since`.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.conductor import publish_conductor_files
from adapters.conductor.adapter import CONDUCTOR_FILE_ORDER
from adapters.frontier.claude_code import ClaudeCliBackend
from control_plane.conductor.selection import (
    OPERATOR_SELECTED_CONDUCTOR,
    bind_conductor_selection,
    restore_operator_selection,
    selection_from_record,
    succession_selection,
)
from control_plane.profiles.live_authorization import LiveAuthorization, load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from control_plane.recovery.succession import ConductorState, SuccessionManager
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.conductor_spawn import attempt_live_conductor_smoke
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"

_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


_JSON_DECOMPOSITION = json.dumps(
    {"proposed_tasks": [{"desc": "sub-task", "capability": "reasoning"}],
     "rationale": "one subtask"})


class _JsonConductorBackend:
    """Worker `Backend` returning a JSON decomposition. A MOCK, and named one.

    `reported_model` sets the raw attribute a live CLI would set. Until `phase-15d.gate` that alone
    produced a VERIFIED executing checkpoint from this mock (U45 site 2) — it no longer can, and
    the tests below pin the refusal."""

    name = "claude_code:mock:json"

    def __init__(self, reported_model: str | None = None) -> None:
        self.calls = 0
        self.reported_model = reported_model
        self.reported_model_at_call = 1 if reported_model else None

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        return _JSON_DECOMPOSITION


def _genuine_conductor_backend(reported_model: str | None) -> ClaudeCliBackend:
    """A REAL `ClaudeCliBackend` whose `generate` is replaced so no process spawns, stamping the
    checkpoint exactly as the live one does. The only way to exercise the VERIFIED path in a
    mock-first suite, since verification requires the exact vendor class (U43: exact type
    constrains the class, not the behaviour)."""
    backend = ClaudeCliBackend(model="fable-5")

    def _generate(prompt: str, *, max_tokens: int = 256) -> str:
        backend.calls += 1
        backend.reported_model = reported_model
        backend.reported_model_at_call = backend.calls if reported_model else None
        return _JSON_DECOMPOSITION

    backend.generate = _generate  # type: ignore[method-assign]
    return backend


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _mcp(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj")); c.connect()
    return c


def _manifest(server: MCPServer) -> dict[str, str]:
    op = _mcp(server, "operator", "operator")
    try:
        return publish_conductor_files(op, "operator", CONDUCTOR_DIR)
    finally:
        op.close()


def _authorized(tmp_path: Path) -> LiveAuthorization:
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")  # a TEST config, never the repo one
    return load_live_authorization(path=cfg)


def _smoke(server, tmp_path, *, backend, live_auth=None, terms=True, model=None):
    cond = _mcp(server, "conductor-fable5", "conductor")
    try:
        return cond, attempt_live_conductor_smoke(
            objective="decompose the objective", mcp_client=cond, governor=SubscriptionGovernor(),
            subscription_ref="claude-sub", node_id="conductor-fable5", permission_profile_id="pp",
            live_auth=live_auth or _authorized(tmp_path),
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=terms, conductor_file_refs=_manifest(server),
            model=model, backend=backend)
    finally:
        pass


# ---- (1)+(2) the selection drives the request and is surfaced on every outcome ----------------

def test_smoke_requests_the_selection_model_by_default(server: MCPServer, tmp_path: Path) -> None:
    cond, outcome = _smoke(server, tmp_path, backend=_JsonConductorBackend())
    assert outcome.ran and outcome.published
    # 15D: model_ref = fable-5 (the selection), NOT a silent CLI default
    assert outcome.model_resolution["model_ref"]["resolved_slug"] == "fable-5"
    assert outcome.conductor_selection["selection"]["model"] == "fable-5"
    assert outcome.conductor_selection["selection"]["reason"] == "operator_selected"
    cond.close()


def test_selection_surfaced_on_skip_with_record(server: MCPServer, tmp_path: Path) -> None:
    """A refused live conductor must still say WHICH conductor was selected — never silent."""
    cond, outcome = _smoke(server, tmp_path, backend=_JsonConductorBackend(), terms=False)
    assert not outcome.ran and outcome.skipped_with_record
    assert outcome.conductor_selection["selection"]["model"] == "fable-5"
    # refused before a backend existed: nothing executed, and the record says so
    assert outcome.conductor_selection["executing"]["verified"] is False
    assert outcome.conductor_selection["executing"]["model"] is None
    cond.close()


def test_selection_surfaced_when_authorization_denied(server: MCPServer, tmp_path: Path) -> None:
    cond, outcome = _smoke(server, tmp_path, backend=_JsonConductorBackend(),
                           live_auth=load_live_authorization(path=tmp_path / "absent.json"))
    assert not outcome.ran and outcome.skipped_with_record
    assert outcome.conductor_selection["selection"]["model"] == "fable-5"
    cond.close()


# ---- (3)+(4) the published decision records BOTH; a label mismatch is surfaced ----------------

def test_published_decision_records_selection_and_executing_separately(
        server: MCPServer, tmp_path: Path) -> None:
    reported = "claude-fable-5-20260101"
    cond, outcome = _smoke(server, tmp_path, backend=_genuine_conductor_backend(reported))
    row = next(d for d in cond.call("read_status", status="CANDIDATE")
               if d["entry_id"] == outcome.decision_entry)
    body = json.loads(base64.b64decode(cond.call("get_content", entry_id=row["entry_id"])["content_b64"]))
    assert body["model"] == reported and body["model_verified"] is True   # what RAN
    assert "fable-5" in body["model_selection"]                            # what was SELECTED
    # and the outcome's selection record agrees, through the REAL entrypoint
    assert outcome.conductor_selection["executing"]["model"] == reported
    assert outcome.conductor_selection["executing"]["verified"] is True
    cond.close()


def test_a_mock_reporting_a_checkpoint_cannot_publish_a_verified_one(
        server: MCPServer, tmp_path: Path) -> None:
    """U45 site 2, through the REAL entrypoint. The backend is a mock that merely SETS the
    attribute a live CLI would set. Pre-fix this published `model_verified: true` and a verified
    executing checkpoint — a mock presented as a real-provider result (§6/§10.4)."""
    cond, outcome = _smoke(server, tmp_path,
                           backend=_JsonConductorBackend(reported_model="claude-fable-5-20260101"))
    assert outcome.ran and outcome.published
    sel = outcome.conductor_selection
    assert sel["executing"]["verified"] is False
    assert sel["executing"]["model"] is None
    # the claim is recorded, not silently dropped — the operator can see it was made and unbacked
    assert sel["executing"]["reported_unverified"] == "claude-fable-5-20260101"
    row = next(d for d in cond.call("read_status", status="CANDIDATE")
               if d["entry_id"] == outcome.decision_entry)
    body = json.loads(base64.b64decode(cond.call("get_content", entry_id=row["entry_id"])["content_b64"]))
    assert body["model_verified"] is False
    assert body["model"] != "claude-fable-5-20260101"
    cond.close()


def test_checkpoint_differing_from_label_surfaced_not_masked(server: MCPServer, tmp_path: Path) -> None:
    cond, outcome = _smoke(server, tmp_path,
                           backend=_genuine_conductor_backend("claude-opus-4-8"))
    sel = outcome.conductor_selection
    assert sel["selection"]["model"] == "fable-5"        # selection preserved (invariant 3)
    assert sel["executing"]["model"] == "claude-opus-4-8"
    assert sel["label_mismatch"] is True
    cond.close()


def test_mock_path_never_claims_a_verified_checkpoint(server: MCPServer, tmp_path: Path) -> None:
    cond, outcome = _smoke(server, tmp_path, backend=_JsonConductorBackend())  # reports nothing
    executing = outcome.conductor_selection["executing"]
    assert executing["verified"] is False
    assert executing["model"] is None                    # a mock run executed no live checkpoint
    assert executing["resolved_slug"] == "fable-5"       # what was requested, verbatim
    assert outcome.conductor_selection["label_mismatch"] is False
    cond.close()


# ---- (5) succession + restore through the REAL SuccessionManager ------------------------------

def test_succession_then_restore_round_trips_through_mcp(server: MCPServer) -> None:
    cond = _mcp(server, "conductor-fable5", "conductor")
    mgr = SuccessionManager(cond)
    state = ConductorState(nodes=[{"node_id": "w1"}], directive_version="v2.4",
                           current_conductor={**OPERATOR_SELECTED_CONDUCTOR.as_current_conductor(),
                                              "node_id": "conductor-fable5"})
    mgr.serialize(state, trigger="major_event")
    successor = succession_selection("opus-4.8", since="2026-07-19T14:00:00+00:00",
                                     adapter="claude_code")
    reconstructed, report = mgr.reconstruct(
        expected_directive_version="v2.4",
        new_selection={"model": successor.model, "adapter": successor.adapter})
    assert reconstructed.current_conductor["reason"] == "succession"      # not an operator choice
    assert reconstructed.current_conductor["model"] == "opus-4.8"
    assert report.checks["integrity_ok"] is True

    restored = restore_operator_selection(
        selection_from_record({k: v for k, v in reconstructed.current_conductor.items()
                               if k in OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()}),
        since="2026-07-19T15:00:00+00:00")
    assert restored.model == "fable-5" and restored.reason == "operator_selected"
    assert restored.since == "2026-07-19T15:00:00+00:00"
    cond.close()


def test_chained_succession_reserializes_a_reconstructed_record(server: MCPServer) -> None:
    """B reconstructs, is snapshotted, C reconstructs: the reconstructed `current_conductor` now
    carries every schema key (including explicit nulls), so it must survive re-entering
    `jsonschema.validate` on the next serialize — the property the shared key set relies on."""
    # each successor is its own node (MCP enforces author_node == publishing node)
    a, b_client, c_client = (_mcp(server, n, "conductor")
                             for n in ("conductor-A", "conductor-B", "conductor-C"))
    state = ConductorState(nodes=[{"node_id": "w1"}], directive_version="v2.4",
                           current_conductor={**OPERATOR_SELECTED_CONDUCTOR.as_current_conductor(),
                                              "node_id": "conductor-A"})
    SuccessionManager(a).serialize(state, trigger="major_event")
    mgr_b = SuccessionManager(b_client)
    b, _ = mgr_b.reconstruct(expected_directive_version="v2.4",
                             new_selection={"node_id": "conductor-B", "model": "opus-4.8"})
    mgr_b.serialize(b, trigger="major_event")        # would raise if the record were schema-invalid
    c, _ = SuccessionManager(c_client).reconstruct(
        expected_directive_version="v2.4",
        new_selection={"node_id": "conductor-C", "model": "fable-5"})
    assert c.current_conductor["model"] == "fable-5"
    assert c.current_conductor["reason"] == "succession"
    assert c.current_conductor["node_id"] == "conductor-C"   # non-schema key preserved in state
    for client in (a, b_client, c_client):
        client.close()


def test_succession_refuses_a_selection_that_smuggles_owned_fields(server: MCPServer) -> None:
    """`reason`/`since` are owned by the succession path — a caller supplying them (which would
    let an operator re-selection be recorded as a system recovery) is refused, not ignored."""
    from control_plane.conductor.selection import ConductorSelectionError

    cond = _mcp(server, "conductor-fable5", "conductor")
    mgr = SuccessionManager(cond)
    mgr.serialize(ConductorState(nodes=[{"node_id": "w1"}], directive_version="v2.4",
                                 current_conductor={**OPERATOR_SELECTED_CONDUCTOR.as_current_conductor(),
                                                    "node_id": "conductor-fable5"}),
                  trigger="major_event")
    for smuggled in ({"model": "opus-4.8", "reason": "operator_selected"},
                     {"model": "opus-4.8", "since": "2020-01-01T00:00:00+00:00"}):
        with pytest.raises(ConductorSelectionError):
            mgr.reconstruct(expected_directive_version="v2.4", new_selection=smuggled)
    with pytest.raises(ConductorSelectionError):   # missing model: module error, not bare KeyError
        mgr.reconstruct(expected_directive_version="v2.4", new_selection={"node_id": "conductor-B"})
    cond.close()


def test_binding_record_is_checkpoint_compatible() -> None:
    """The binding's selection half must be exactly what a checkpoint carries — one record shape."""
    binding = bind_conductor_selection(reported_model="claude-fable-5-20260101")
    assert binding.as_record()["selection"] == OPERATOR_SELECTED_CONDUCTOR.as_current_conductor()
