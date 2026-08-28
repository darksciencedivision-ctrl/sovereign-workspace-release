"""Phase 4 exit criteria: the conductor adapter loads conductor files FROM MCP in declared
order before acting, runs the conductor loop against the mock backend, holds no provider
credential, and honors the I-X3 governor + §12.2 conformance contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.base import AdapterContext, MockReasoningBackend, NakedLaunchRefused
from adapters.conductor import (
    CONDUCTOR_FILE_ORDER,
    ConductorAdapter,
    ConductorNotReady,
    publish_conductor_files,
)
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
)

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"


@pytest.fixture()
def wired(tmp_path):
    srv = MCPServer(tmp_path / "store")
    srv.start()
    op_tok = srv.credentials.issue("operator", "operator", "proj")
    op = McpClient("127.0.0.1", srv.port, op_tok); op.connect()
    manifest = publish_conductor_files(op, "operator", CONDUCTOR_DIR)
    cond_tok = srv.credentials.issue("conductor-fable5", "conductor", "proj")
    cond_client = McpClient("127.0.0.1", srv.port, cond_tok); cond_client.connect()
    # Fixture sweep (U530): "anthropic" is not a recorded provider under the W-65 cap table
    # (an unrecorded id caps at 0), so registration now refuses. claude_code carries the
    # recorded OP-6 cap of 2; the ref string stays free-form pre-OP-12 spelling.
    gov = SubscriptionGovernor(); gov.register_subscription("sub-anthropic-01", "claude_code")
    ctx = AdapterContext(node_id="conductor-fable5", role="conductor", project_id="proj",
                         permission_profile_id="pp-conductor", mcp_credential_id="tok-ref",
                         subscription_ref="sub-anthropic-01", spawned_by_supervisor=True)
    adapter = ConductorAdapter(ctx, cond_client, MockReasoningBackend(), gov, manifest)
    yield {"srv": srv, "op": op, "adapter": adapter, "gov": gov, "manifest": manifest, "cond_client": cond_client}
    op.close(); cond_client.close(); srv.stop()


def test_loads_all_conductor_files_from_mcp_in_declared_order(wired) -> None:
    adapter = wired["adapter"]
    adapter.start()
    assert adapter.loaded_files == CONDUCTOR_FILE_ORDER  # order preserved
    assert adapter.get_context_status()["ready"]


def test_conductor_refuses_to_act_before_loading(wired) -> None:
    # a fresh adapter that never started must not run a cycle (fail closed)
    adapter = wired["adapter"]
    with pytest.raises(ConductorNotReady):
        adapter.run_cycle("do the thing")


def test_conductor_runs_loop_and_records_candidate_decision(wired) -> None:
    adapter, op = wired["adapter"], wired["op"]
    adapter.start()
    result = adapter.run_cycle("Build the offline conductor roster")
    assert result["cycle"] == 1 and result["decision_entry"].startswith("m-")
    # the decision is a CANDIDATE proposal in MCP (conductor proposes, never self-promotes)
    decisions = op.call("read_status", status="CANDIDATE")
    assert any(d["entry_id"] == result["decision_entry"] and d["kind"] == "decision" for d in decisions)


def test_conductor_holds_no_provider_credential(wired) -> None:
    adapter = wired["adapter"]
    adapter.start()
    assert adapter.holds_provider_credential() is False
    state = adapter.export_session_state()
    # exported succession state keys are an allowlist — no credential/subscription material (F4)
    assert set(state) <= {"node_id", "cycle", "loaded_files", "backend_calls", "conductor_file_refs"}
    blob = json.dumps(state).lower()
    assert not any(s in blob for s in ("tok", "secret", "password", "sub-", "credential"))


def test_all_conductor_files_loaded_via_mcp_get_content(wired) -> None:
    """F3 strengthened: prove every file came through MCP get_content (not disk) by counting
    the actual MCP calls the adapter made."""
    calls: list = []
    real = wired["cond_client"].call

    def spy(op, **kw):
        calls.append((op, kw.get("entry_id")))
        return real(op, **kw)

    wired["cond_client"].call = spy  # type: ignore[method-assign]
    wired["adapter"].start()
    get_contents = [c for c in calls if c[0] == "get_content"]
    assert len(get_contents) == len(CONDUCTOR_FILE_ORDER)  # exactly 12 MCP reads, one per file
    assert [c[1] for c in get_contents] == [wired["manifest"][f] for f in CONDUCTOR_FILE_ORDER]  # in order


def test_conductor_context_comes_only_from_mcp(wired) -> None:
    """The adapter is constructed with an MCP client + refs but NO conductor_dir — it cannot
    read the files from disk; the only source of context is MCP (I-M1/invariant 8)."""
    adapter = wired["adapter"]
    assert not hasattr(adapter, "_conductor_dir")
    adapter.start()
    # content actually came back through the MCP client
    assert all(len(adapter._loaded[f]) > 0 for f in CONDUCTOR_FILE_ORDER)


def test_naked_conductor_refused(wired) -> None:
    bad_ctx = AdapterContext(node_id="x", role="conductor", project_id="proj",
                             permission_profile_id="pp", mcp_credential_id="ref",
                             spawned_by_supervisor=False)
    with pytest.raises(NakedLaunchRefused):
        ConductorAdapter(bad_ctx, wired["cond_client"], MockReasoningBackend(), wired["gov"], wired["manifest"])


def test_ix3_second_conductor_on_same_subscription_refused(wired) -> None:
    adapter, gov = wired["adapter"], wired["gov"]
    adapter.start()  # holds the one terminal on sub-anthropic-01
    with pytest.raises(SubscriptionLimitExceeded):
        gov.acquire("sub-anthropic-01", "conductor-successor")
    # succession: predecessor releases, successor claims
    adapter.close()
    gov.acquire("sub-anthropic-01", "conductor-successor")
    assert gov.active_count("sub-anthropic-01") == 1


def test_conductor_excluded_from_offline_profile(wired) -> None:
    cap = wired["adapter"].capability()
    with pytest.raises(ProfileViolation):
        ProfileLoader(DeploymentProfile("offline_airgapped")).check_eligible(cap)


def test_missing_conductor_file_ref_fails_closed(wired) -> None:
    incomplete = dict(wired["manifest"]); incomplete.pop("GATE_POLICY.md")
    ctx = AdapterContext(node_id="c2", role="conductor", project_id="proj",
                         permission_profile_id="pp", mcp_credential_id="ref",
                         subscription_ref=None, spawned_by_supervisor=True)
    adapter = ConductorAdapter(ctx, wired["cond_client"], MockReasoningBackend(), None, incomplete)
    with pytest.raises(ConductorNotReady, match="missing"):
        adapter.start()


def test_governor_released_when_load_fails(wired) -> None:
    """F2: a conductor-file load failure after acquiring the subscription must release the
    terminal, not wedge the subscription."""
    gov = wired["gov"]
    incomplete = dict(wired["manifest"]); incomplete.pop("ROLE.md")
    ctx = AdapterContext(node_id="conductor-fail", role="conductor", project_id="proj",
                         permission_profile_id="pp", mcp_credential_id="ref",
                         subscription_ref="sub-anthropic-01", spawned_by_supervisor=True)
    adapter = ConductorAdapter(ctx, wired["cond_client"], MockReasoningBackend(), gov, incomplete)
    with pytest.raises(ConductorNotReady):
        adapter.start()
    assert gov.active_count("sub-anthropic-01") == 0  # released; a successor can now start
    gov.acquire("sub-anthropic-01", "retry")
    assert gov.active_count("sub-anthropic-01") == 1
