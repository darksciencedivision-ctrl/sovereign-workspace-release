"""Phase 15C .adapter (integration): the live `openai_codex_cli` frontier terminal driven through
the REAL supervisor/startup entrypoint (node_runtime/supervisor/codex_spawn) and the REAL MCP
server.

Proven here (mirrors the claude_code .adapter integration):
  1. MOCK-FIRST end-to-end: an authorized live_auth + confirmed operator terms + an injected
     MockCodexCliBackend spawns a governed terminal that reads scoped context from MCP, passes the
     local gate, and publishes a CANDIDATE — the whole governance path, zero live call.
  2. REAL-ENTRYPOINT ENFORCEMENT: the same entrypoint, given a DENIED (absent) authorization,
     refuses to spawn. Enforcement is at the real spawn site, not just in a test.
  3. I-X3 under OP-6: the subscription governor admits two terminals on one subscription and
     refuses the third.
And the single live smoke: attempted through the real path -> skip-with-record (no live call), the
honest non-interactive outcome (directive §10.4) — the operator R8 §6 live-terms are unmet here.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.frontier.codex import MockCodexCliBackend
from control_plane.profiles.live_authorization import LiveAuthorization, load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.codex_spawn import (
    attempt_codex_live_smoke,
    spawn_codex_terminal,
)
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor, SubscriptionLimitExceeded

# OP-6 two-provider live scope (Phase 15A .liveauth): openai_codex_cli is authorized alongside
# claude_code.
_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True,
               "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-19T00:00:00+00:00",
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
    mcp = _client(server, "codex-node", "worker")
    gov = SubscriptionGovernor()
    adapter = spawn_codex_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="codex-sub", node_id="codex-node",
        permission_profile_id="pp-frontier", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, role="reasoning", model="5.5",
        backend=MockCodexCliBackend(model="5.5"))
    # the terminal is counted against the subscription (I-X3)
    assert gov.active_count("codex-sub") == 1
    assert adapter.capability().adapter == "openai_codex_cli"
    assert adapter.holds_provider_credential() is False
    adapter.assign("t-live", obj["entry_id"])
    result = adapter.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    # the CANDIDATE is real, content-addressed, provenance-bearing, in MCP
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "openai_codex_cli" in body and "deterministic Codex result" in body
    gov.release("codex-sub", "codex-node")
    mcp.close(); op.close()


def test_mock_first_coding_role_publishes_candidate(server: MCPServer, tmp_path: Path) -> None:
    """The coding-specialist role also rides the governed path end-to-end (worktree-scoped in
    the live backend; here the mock proves the governance)."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Add a docstring to util.py."), provenance=_prov("op"),
                  status="ACCEPTED")
    mcp = _client(server, "codex-coder", "worker")
    gov = SubscriptionGovernor()
    adapter = spawn_codex_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="codex-sub", node_id="codex-coder",
        permission_profile_id="pp", live_auth=_authorized(tmp_path),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, role="coding", model="5.5",
        workdir=str(tmp_path / "wt"), backend=MockCodexCliBackend(model="5.5", role="coding"))
    assert adapter.capability().node_class == "worker_coding_specialist"
    adapter.assign("t-code", obj["entry_id"])
    result = adapter.execute()
    assert result["published"] and result["local_gate"] == "PASS"
    gov.release("codex-sub", "codex-coder")
    mcp.close(); op.close()


# ---- (2) REAL-ENTRYPOINT ENFORCEMENT: a DENIED (absent) authorization refuses ---------------

def test_denied_authorization_refuses_live_spawn(server: MCPServer, tmp_path: Path) -> None:
    """A DENIED authorization (absent config) makes the real spawn entrypoint refuse. The enduring
    invariant is 'no authorization => no live spawn', independent of whether the real config exists."""
    absent_auth = load_live_authorization(path=tmp_path / "no_config.json")  # DENIED-by-absence
    assert absent_auth.authorized is False
    mcp = _client(server, "codex-node", "worker")
    gov = SubscriptionGovernor()
    from control_plane.profiles.loader import ProfileViolation
    with pytest.raises(ProfileViolation):
        spawn_codex_terminal(
            mcp_client=mcp, governor=gov, subscription_ref="codex-sub", node_id="codex-node",
            permission_profile_id="pp", live_auth=absent_auth,
            profile_loader=ProfileLoader(DeploymentProfile("cloud")),
            operator_terms_confirmed=True, backend=MockCodexCliBackend())
    assert gov.active_count("codex-sub") == 0  # nothing acquired on the denied path
    mcp.close()


# ---- (3) I-X3 under OP-6: TWO terminals per subscription, the THIRD refused -----------------

def _spawn(server, gov, loader, auth, node_id):
    mcp = _client(server, node_id, "worker")
    adapter = spawn_codex_terminal(
        mcp_client=mcp, governor=gov, subscription_ref="codex-sub", node_id=node_id,
        permission_profile_id="pp", live_auth=auth, profile_loader=loader,
        operator_terms_confirmed=True, backend=MockCodexCliBackend())
    return mcp, adapter


def test_op6_two_terminals_permitted_third_refused(server: MCPServer, tmp_path: Path) -> None:
    """OP-6 allowance=2 proof for the second live provider: the supervised codex spawn path admits
    two terminals on the SAME subscription and refuses the third — concurrency comes from
    live_auth.terminals_per_subscription, never a hardcoded 1."""
    auth = _authorized(tmp_path)
    assert auth.terminals_per_subscription == 2
    loader = ProfileLoader(DeploymentProfile("cloud"))
    gov = SubscriptionGovernor()
    mcp1, _ = _spawn(server, gov, loader, auth, "codex-a")
    mcp2, _ = _spawn(server, gov, loader, auth, "codex-b")  # second is PERMITTED (OP-6)
    assert gov.active_count("codex-sub") == 2
    mcp3 = _client(server, "codex-c", "worker")
    with pytest.raises(SubscriptionLimitExceeded):  # the THIRD is refused (governor cap 2)
        spawn_codex_terminal(
            mcp_client=mcp3, governor=gov, subscription_ref="codex-sub", node_id="codex-c",
            permission_profile_id="pp", live_auth=auth, profile_loader=loader,
            operator_terms_confirmed=True, backend=MockCodexCliBackend())
    assert gov.active_count("codex-sub") == 2
    mcp1.close(); mcp2.close(); mcp3.close()


# ---- the single live smoke: skip-with-record (no live call) --------------------------------

def test_live_smoke_skips_with_record_under_denied_authorization(server: MCPServer, tmp_path: Path) -> None:
    """A DENIED (absent) authorization forces skip-with-record with NO live call — the auth gate is
    binding even if operator terms were (hypothetically) confirmed."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "codex-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_codex_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="codex-sub", node_id="codex-node", permission_profile_id="pp",
        live_auth=load_live_authorization(path=tmp_path / "no_config.json"),  # DENIED-by-absence
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True)  # even so, the auth gate denies -> no live call
    assert outcome.ran is False and outcome.skipped_with_record is True
    assert outcome.published is False and outcome.entry_id is None
    assert gov.active_count("codex-sub") == 0
    mcp.close(); op.close()


def test_live_smoke_unconfirmed_terms_also_skips_with_record(server: MCPServer, tmp_path: Path) -> None:
    """Second skip path: even WITH a valid authorization, unconfirmed operator terms skip-with-
    record (the R8 §6 [OPERATOR] items are unmet in a non-interactive session) — this is the honest
    outcome of THIS session's smoke attempt for openai_codex_cli."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "codex-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_codex_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="codex-sub", node_id="codex-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, backend=MockCodexCliBackend())
    assert outcome.ran is False and outcome.skipped_with_record is True
    assert "LiveTermsNotConfirmed" in outcome.reason
    assert gov.active_count("codex-sub") == 0
    mcp.close(); op.close()


def test_auth_pause_propagates_to_fail_closed_skip(server: MCPServer, tmp_path: Path) -> None:
    """An auth/credit/rate pause raised by the backend must NOT be swallowed as an ordinary
    published=False; it must propagate through ModelWorkerAdapter.execute and be reported by
    attempt_codex_live_smoke as a fail-closed pause (Plan §18.4), releasing the terminal."""
    from adapters.frontier.codex import CodexAuthError

    class _AuthExpiredBackend:
        name = "codex:cli:5.5"

        def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
            raise CodexAuthError("codex CLI auth/rate failure: session expired — pause (Plan §18.4)")

    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"objective"), provenance=_prov("op"), status="ACCEPTED")
    mcp = _client(server, "codex-node", "worker")
    gov = SubscriptionGovernor()
    outcome = attempt_codex_live_smoke(
        objective_entry_id=obj["entry_id"], task_id="t-smoke", mcp_client=mcp, governor=gov,
        subscription_ref="codex-sub", node_id="codex-node", permission_profile_id="pp",
        live_auth=_authorized(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, backend=_AuthExpiredBackend())
    assert outcome.ran is True and outcome.published is False
    assert outcome.skipped_with_record is True and "auth pause" in outcome.reason
    assert gov.active_count("codex-sub") == 0  # terminal released on the pause path (no wedge)
    mcp.close(); op.close()
