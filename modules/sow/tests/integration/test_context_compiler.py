"""Phase 9 exit criteria: scoped context assembly from MCP by role+task+need-to-know; a
worker receives ONLY scoped context; MEASURED token reduction vs a naive full-transcript
baseline on a reference project."""
from __future__ import annotations

import base64

import pytest

from control_plane.routing import ContextCompiler, measure_reduction, tokenizer_method
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _prov(author: str, task_id: str | None = None) -> dict:
    return {"author_node": author, "task_id": task_id, "ts": "2026-07-17T00:00:00+00:00",
            "directive_version": "v2.4", "confidence": "high"}


@pytest.fixture()
def reference(tmp_path):
    """A reference project: an objective + 8 accepted findings (one per task t-1..t-8), each a
    chunky document. The target task depends on only t-2 and t-5."""
    srv = MCPServer(tmp_path / "store"); srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("operator", "operator", "proj")); op.connect()
    objective = op.call("publish", kind="finding", tier="shared_project",
                        content_b64=_b64(b"Objective: design the offline conductor roster and its fallbacks."),
                        provenance=_prov("operator"), status="ACCEPTED")
    findings = {}
    for i in range(1, 9):
        body = (f"# Finding for task t-{i}\n" + f"Detailed analysis section for task {i}. " * 60).encode("utf-8")
        pub = op.call("publish", kind="finding", tier="shared_project", content_b64=_b64(body),
                      provenance=_prov("operator", task_id=f"t-{i}"), status="ACCEPTED")
        findings[f"t-{i}"] = pub["entry_id"]
    yield {"srv": srv, "op": op, "objective": objective["entry_id"], "findings": findings}
    op.close(); srv.stop()


def test_scoped_context_includes_only_need_to_know(reference) -> None:
    worker = McpClient("127.0.0.1", reference["srv"].port,
                       reference["srv"].credentials.issue("worker-x", "worker", "proj")); worker.connect()
    compiler = ContextCompiler(worker)
    ctx = compiler.compile(task_id="t-target", deps=["t-2", "t-5"], role="worker_reasoning",
                           objective_entry=reference["objective"], role_scope="You analyze and cite evidence.",
                           project_id="proj")
    # only the objective + the two dependency outputs are included — not the other six
    assert set(ctx.included_entry_ids) == {reference["objective"], reference["findings"]["t-2"],
                                           reference["findings"]["t-5"]}
    assert {d["task_id"] for d in ctx.dependency_outputs} == {"t-2", "t-5"}
    rendered = ctx.render()
    assert "task t-2" in rendered and "task t-5" in rendered
    for other in ("t-1", "t-3", "t-4", "t-6", "t-7", "t-8"):  # sibling work is NOT forwarded
        assert f"Finding for task {other}\n" not in rendered
    worker.close()


def test_measured_token_reduction_beats_naive(reference) -> None:
    worker = McpClient("127.0.0.1", reference["srv"].port,
                       reference["srv"].credentials.issue("worker-y", "worker", "proj")); worker.connect()
    compiler = ContextCompiler(worker)
    ctx = compiler.compile(task_id="t-target", deps=["t-2", "t-5"], role="worker_reasoning",
                           objective_entry=reference["objective"], role_scope="role scope text",
                           project_id="proj")
    naive = compiler.measurement_baseline_naive(project_id="proj")
    result = measure_reduction(ctx.render(), naive)
    # scoped (objective + 2 deps) should be far smaller than naive (objective + 8 findings)
    assert result.scoped_tokens < result.naive_tokens
    assert result.reduction_pct >= 50.0, f"expected >=50% reduction, got {result.reduction_pct}%"
    assert "tiktoken" in result.tokenizer or result.tokenizer == "word-proxy"
    print(f"[phase9] tokenizer={result.tokenizer} scoped={result.scoped_tokens} "
          f"naive={result.naive_tokens} reduction={result.reduction_pct}%")
    worker.close()


def test_no_deps_still_scopes_to_objective_and_role(reference) -> None:
    worker = McpClient("127.0.0.1", reference["srv"].port,
                       reference["srv"].credentials.issue("worker-z", "worker", "proj")); worker.connect()
    ctx = ContextCompiler(worker).compile(task_id="t-1", deps=[], role="worker_reasoning",
                                          objective_entry=reference["objective"], role_scope="scope",
                                          project_id="proj")
    assert ctx.included_entry_ids == [reference["objective"]]  # no dependency dump
    assert not ctx.dependency_outputs
    worker.close()


def test_tokenizer_method_is_recorded() -> None:
    assert tokenizer_method() in ("tiktoken:cl100k_base", "word-proxy")
