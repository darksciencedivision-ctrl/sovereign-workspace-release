"""Phase 6: the same adapter contract drives all 3 backends end-to-end through MCP, and an
opt-in live smoke proves the REAL Ollama backend works. Deterministic tests use mock backends;
the live smoke is skipped unless the Ollama daemon is detected."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from adapters import detect
from adapters.base.backend import MockBackend, OllamaBackend
from adapters.base.contract import AdapterContext
from adapters.model_adapter import ModelWorkerAdapter
from adapters.roster import build_roster
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(author: str) -> dict:
    return {"author_node": author, "task_id": None, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _client(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj")); c.connect()
    return c


def _make_adapter(server, entry, mcp, backend) -> ModelWorkerAdapter:
    ctx = AdapterContext(node_id=entry.name, role="worker", project_id="proj",
                         permission_profile_id="pp", mcp_credential_id="ref", spawned_by_supervisor=True)
    return ModelWorkerAdapter(ctx, mcp, backend, adapter_name=entry.name, node_class=entry.node_class,
                              locality=entry.locality, offline_profile_eligible=entry.offline_profile_eligible,
                              requires_network=entry.requires_network,
                              capability_descriptors=entry.capability_descriptors,
                              subscription_backed=entry.subscription_backed, harness=entry.harness)


def test_all_three_backends_share_one_contract(server: MCPServer) -> None:
    """Each roster backend, behind the identical adapter contract, reads context from MCP and
    publishes a CANDIDATE finding — proving the contract is backend-agnostic (I-CH1)."""
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"multi-model objective"), provenance=_prov("op"), status="ACCEPTED")
    published = {}
    for entry in build_roster(allow_live=False):  # deterministic: mock backends
        mcp = _client(server, entry.name, "worker")
        adapter = _make_adapter(server, entry, mcp, MockBackend(name=f"mock:{entry.name}"))
        # each adapter's declared capability matches its roster class (descriptor, not name)
        assert adapter.capability().node_class == entry.node_class
        adapter.assign(f"t-{entry.name}", obj["entry_id"])
        result = adapter.execute()
        assert result["published"] and result["entry_id"].startswith("m-")
        published[entry.name] = result["entry_id"]
        mcp.close()
    assert len(published) == 3  # all three backends produced a governed artifact
    op.close()


def test_backend_failure_is_structured_not_a_crash(server: MCPServer) -> None:
    """F3: a backend that raises must yield a structured failure (published=False), not crash
    the adapter/scheduling loop — symmetric with a local-gate failure."""
    class _BrokenBackend:
        name = "broken"

        def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
            raise ConnectionError("daemon down mid-run")

    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"obj"), provenance=_prov("op"), status="ACCEPTED")
    entry = build_roster(allow_live=False)[0]
    mcp = _client(server, entry.name, "worker")
    adapter = _make_adapter(server, entry, mcp, _BrokenBackend())
    adapter.assign("t-x", obj["entry_id"])
    result = adapter.execute()
    assert result["published"] is False and "backend_error" in result  # fail closed, no crash
    mcp.close(); op.close()


@pytest.mark.skipif(not detect.ollama_available(), reason="Ollama daemon not detected on host")
def test_live_ollama_backend_smoke(server: MCPServer) -> None:
    """Opt-in LIVE smoke: a real local model produces a real artifact through the full MCP
    path. Skipped when the daemon is absent. Not part of the deterministic suite."""
    models = detect.ollama_models()
    # prefer direct instruct models: thinking models (qwen3/deepseek-r1) spend a short
    # num_predict budget on reasoning tokens and can return an empty visible response
    model = detect.pick_model(models, ("qwen2.5:7b-instruct", "qwen2.5:14b-instruct",
                                       "llama3.1:8b", "mistral-small3.2:latest"))
    if not model:
        pytest.skip(f"no direct-output instruct model among {models[:5]}...")
    op = _client(server, "op", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"In one sentence, what is a compare-and-swap operation?"),
                  provenance=_prov("op"), status="ACCEPTED")
    entry = next(e for e in build_roster() if e.name == "local_reasoning")
    mcp = _client(server, entry.name, "worker")  # client identity must match the adapter's node_id
    adapter = _make_adapter(server, entry, mcp, OllamaBackend(model))
    adapter.assign("t-live", obj["entry_id"])
    result = adapter.execute(max_tokens=128)
    assert result["published"] and result["generated_chars"] > 0  # real model produced text
    # the real content is retrievable from MCP, content-addressed
    body = base64.b64decode(mcp.call("get_content", entry_id=result["entry_id"])["content_b64"]).decode("utf-8")
    assert "multi-model" not in body and len(body) > 50
    mcp.close(); op.close()
