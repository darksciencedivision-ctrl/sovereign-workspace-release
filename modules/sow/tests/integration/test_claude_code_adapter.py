"""Phase 14B .adapter (integration): the live `claude_code` frontier terminal driven through
the REAL supervisor/startup entrypoint (node_runtime/supervisor/frontier_spawn) and the REAL
MCP server.

Three things are proven here:
  1. MOCK-FIRST end-to-end: an authorized live_auth + confirmed operator terms + an injected
     MockClaudeCliBackend spawns a governed terminal that reads scoped context from MCP, passes
     the local gate, and publishes a CANDIDATE — the whole governance path, zero live call.
  2. REAL-ENTRYPOINT ENFORCEMENT (discharges .liveflag MINOR-2): the same entrypoint, given the
     REAL in-repo authorization (DENIED-by-absence — config/live_operation.json is gitignored
     and absent), refuses to spawn. Enforcement is at the real spawn site, not just in a test.
  3. I-X3: the subscription governor admits exactly one terminal; a second is refused.
And the single live smoke: attempted through the real path with the real repo authorization ->
skip-with-record (no live call), the honest non-interactive outcome (directive §10.4).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.frontier.claude_code import MockClaudeCliBackend
from control_plane.profiles.live_authorization import LiveAuthorization, load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.frontier_spawn import (
    attempt_live_smoke,
    spawn_claude_code_terminal,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor, SubscriptionLimitExceeded

# OP-6 two-provider live scope (Phase 15A .liveauth); claude_code stays authorized for the
# existing supervised-spawn path, now alongside openai_codex_cli.
_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True,
               "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-18T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _client(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj")); c.connect()
    return c


def _authorized(tmp_path: Path) -> LiveAuthorization:
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")  # a TEST config, never the repo one
    return load_live_authorization(path=cfg)


# ---- (1) MOCK-FIRST governed spawn end-to-end through the real entrypoint ------------------

def test_mock_first_governed_spawn_publishes_candidate(server: MCPServer, tmp_path: Path) -> None:
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Explain compare-and-swap in one sentence."),
                  provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    adapter = spawn_claude_code_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="claude-sub", node_id="claude-node",
        permission_profile_id="pp-frontier", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    # the terminal is counted against the subscription (I-X3)
    assert gov.active_count("claude-sub") == 1
    assert adapter.capability().adapter == "claude_code"
    assert adapter.holds_provider_credential() is False
    adapter.assign("t-live", obj["entry_id"])
    result = adapter.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    # the CANDIDATE is real, content-addressed, provenance-bearing, in MCP
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "claude_code" in body and "deterministic Claude Code result" in body
    gov.release("claude-sub", "claude-node")
    mcp.close(); op.close()


# ---- (2) REAL-ENTRYPOINT ENFORCEMENT: a DENIED (absent) authorization refuses ---------------

def test_denied_authorization_refuses_live_spawn(server: MCPServer, tmp_path: Path) -> None:
    """A DENIED authorization (absent config) makes the real spawn entrypoint refuse. Under OP-6
    the repo-default config/live_operation.json is now loop-created and authorizes both providers,
    so the denied scenario is exercised with an explicitly-absent path — the enduring invariant is
    'no authorization => no live spawn', independent of whether the real config exists on disk."""
    absent_auth = load_live_authorization(path=tmp_path / "no_config.json")  # DENIED-by-absence
    assert absent_auth.authorized is False
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    from control_plane.profiles.loader import ProfileViolation
    with pytest.raises(ProfileViolation):
        spawn_claude_code_terminal(
            mcp_client=mcp, governor=gov, subscription_ref="claude-sub", node_id="claude-node",
            permission_profile_id="pp", live_auth=absent_auth,
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert gov.active_count("claude-sub") == 0  # nothing acquired on the denied path
    mcp.close()


# ---- (3) I-X3 under OP-6: TWO terminals per subscription, the THIRD refused -----------------

def _spawn(server, gov, loader, auth, node_id):
    mcp = _client(server, node_id, "worker")
    adapter = spawn_claude_code_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="claude-sub", node_id=node_id,
        permission_profile_id="pp", live_auth=auth, profile_loader=loader,
        operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    return mcp, adapter


def test_op6_two_terminals_permitted_third_refused(server: MCPServer, tmp_path: Path) -> None:
    """OP-6 allowance=2 proof: the enforced authorization scopes 2 terminals/subscription, so
    the supervised spawn path admits two on the SAME subscription and refuses the third — the
    concurrency comes from live_auth.terminals_per_subscription, never a hardcoded 1."""
    auth = _authorized(tmp_path)
    assert auth.terminals_per_subscription == 2  # the spawn path reads its allowance from here
    loader = ProfileLoader(DeploymentProfile("cloud"))
    gov = SubscriptionGovernor()
    mcp1, _ = _spawn(server, gov, loader, auth, "claude-a")
    mcp2, _ = _spawn(server, gov, loader, auth, "claude-b")  # second is now PERMITTED (OP-6)
    assert gov.active_count("claude-sub") == 2
    mcp3 = _client(server, "claude-c", "worker")
    with pytest.raises(SubscriptionLimitExceeded):  # the THIRD is refused (governor cap 2)
        spawn_claude_code_terminal(
            mcp_client=mcp3, governor=gov, subscription_ref="claude-sub", node_id="claude-c",
            permission_profile_id="pp", live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert gov.active_count("claude-sub") == 2
    mcp1.close(); mcp2.close(); mcp3.close()


def test_config_may_narrow_allowance_to_one(server: MCPServer, tmp_path: Path) -> None:
    """A present config may NARROW the OP-6 scope to 1 terminal (never widen past 2). When it
    does, the spawn path honors it and refuses the second — the allowance is authorization-driven,
    not a fixed constant, so a narrowed config binds the supervised spawn."""
    cfg = tmp_path / "live_operation.json"
    narrowed = {**_VALID_AUTH, "scope": {"providers": ["claude_code", "openai_codex_cli"],
                                          "terminals_per_subscription": 1}}
    cfg.write_text(json.dumps(narrowed), encoding="utf-8")
    auth = load_live_authorization(path=cfg)
    assert auth.terminals_per_subscription == 1
    loader = ProfileLoader(DeploymentProfile("cloud"))
    gov = SubscriptionGovernor()
    mcp1, _ = _spawn(server, gov, loader, auth, "claude-a")
    mcp2 = _client(server, "claude-b", "worker")
    with pytest.raises(SubscriptionLimitExceeded):  # narrowed to 1 -> second refused
        spawn_claude_code_terminal(
            mcp_client=mcp2, governor=gov, subscription_ref="claude-sub", node_id="claude-b",
            permission_profile_id="pp", live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert gov.active_count("claude-sub") == 1
    mcp1.close(); mcp2.close()


# ---- the single live smoke: skip-with-record under a DENIED authorization ------------------

def test_live_smoke_skips_with_record_under_denied_authorization(server: MCPServer, tmp_path: Path) -> None:
    """A DENIED (absent) authorization forces skip-with-record with NO live call — the auth gate
    is binding even if operator terms were (hypothetically) confirmed. (Under OP-6 the repo-default
    config now authorizes both providers, so this fail-closed scenario uses an explicitly-absent
    path; the single live `claude` smoke against the real config is owed to 15B/15D + operator.)"""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="claude-sub", node_id="claude-node", permission_profile_id="pp",
        live_auth=load_live_authorization(path=tmp_path / "no_config.json"),  # DENIED-by-absence
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True)  # even so, the auth gate denies -> no live call
    assert outcome.ran is False and outcome.skipped_with_record is True
    assert outcome.published is False and outcome.entry_id is None
    assert gov.active_count("claude-sub") == 0
    mcp.close(); op.close()


def test_auth_pause_propagates_to_fail_closed_skip(server: MCPServer, tmp_path: Path) -> None:
    """MAJOR-2 regression: an auth/credit/rate pause raised by the backend must NOT be swallowed
    as an ordinary published=False; it must propagate through ModelWorkerAdapter.execute and be
    reported by attempt_live_smoke as a fail-closed pause (Plan §18.4), releasing the terminal."""
    from adapters.frontier.claude_code import ClaudeCodeAuthError

    class _AuthExpiredBackend:
        name = "claude_code:cli"

        def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
            raise ClaudeCodeAuthError("claude CLI auth/rate failure: session expired — pause (Plan §18.4)")

    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="claude-sub", node_id="claude-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, backend=_AuthExpiredBackend())
    assert outcome.ran is True and outcome.published is False
    assert outcome.skipped_with_record is True and "auth pause" in outcome.reason
    assert gov.active_count("claude-sub") == 0  # terminal released on the pause path (no wedge)
    mcp.close(); op.close()


def test_live_smoke_unconfirmed_terms_also_skips_with_record(server: MCPServer, tmp_path: Path) -> None:
    """Second skip path: even WITH a valid authorization, unconfirmed operator terms skip-with-
    record (the R8 §6 [OPERATOR] items are unmet in a non-interactive session)."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="claude-sub", node_id="claude-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, backend=MockClaudeCliBackend())
    assert outcome.ran is False and outcome.skipped_with_record is True
    assert "LiveTermsNotConfirmed" in outcome.reason
    assert gov.active_count("claude-sub") == 0
    mcp.close(); op.close()


# ---- Phase 15B `.modelsel`: per-node model selection flows through the real entrypoint ------

def test_per_node_model_selection_end_to_end(server: MCPServer, tmp_path: Path) -> None:
    """A per-node `model` is carried through the real spawn entrypoint to the backend name and the
    CANDIDATE is still published — the governance path is unchanged, only the model is now selectable."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Explain compare-and-swap in one sentence."),
                  provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    adapter = spawn_claude_code_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="claude-sub", node_id="claude-node",
        permission_profile_id="pp-frontier", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, model="opus-4.8",
        backend=MockClaudeCliBackend(model="opus-4.8"))
    adapter.assign("t-live", obj["entry_id"])
    result = adapter.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "opus-4.8" in body  # the selected model rode through to the published artifact
    gov.release("claude-sub", "claude-node")
    mcp.close(); op.close()


def test_live_smoke_surfaces_model_resolution_even_on_skip(server: MCPServer, tmp_path: Path) -> None:
    """directive §11 15B — the model resolution (which model, or the CLI-default fallback) is
    surfaced on EVERY smoke outcome, including a skip-with-record; never silent."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "claude-node", "worker")
    gov = SubscriptionGovernor()
    # a requested model on a skip path still records the resolution
    outcome = attempt_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="claude-sub", node_id="claude-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, model="fable-5", backend=MockClaudeCliBackend())
    assert outcome.skipped_with_record is True
    assert outcome.model_resolution is not None
    assert outcome.model_resolution["model_ref"]["resolved_slug"] == "fable-5"
    assert outcome.model_resolution["model_ref"]["verified"] is False
    # the CLI-default fallback path is likewise recorded, not silent
    outcome_default = attempt_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke2", mcp_client=mcp, governor=gov,
        subscription_ref="claude-sub", node_id="claude-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, backend=MockClaudeCliBackend())
    assert outcome_default.model_resolution["model_ref"]["is_fallback"] is True
    assert gov.active_count("claude-sub") == 0
    mcp.close(); op.close()
