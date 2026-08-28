from __future__ import annotations

from pathlib import Path
from typing import Any

from control_plane.policy import SovereignPolicy
from mcp_server.sovereign_tools import SovereignToolRuntime, TOOLS, handle_request

#: W-04 spawns the MCP module as a real process; its cwd must be the repo root so the package
#: imports resolve the same way the shell's own launch does.
REPO_ROOT_FOR_MCP = Path(__file__).resolve().parents[2]


class FakeApplicationControl:
    """The Electron seam only; persistence, policy and every tool handler remain real."""

    def __init__(self, node_id: str, role: str, provider: str, model: str) -> None:
        self.details = {
            "node_id": node_id,
            "role": role,
            "project_id": "proj",
            "provider_id": provider,
            "model_id": model,
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def identity_details(self) -> dict[str, Any]:
        return dict(self.details)

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        self.calls.append((operation, args))
        if operation == "list_models":
            return [{"provider_id": "grok_build", "model_id": "grok-4.5"}]
        if operation == "spawn_worker":
            return {"ready": True, "node_id": "worker-spawned"}
        if operation == "stop_worker":
            return {"stopped": True, "node_id": args.get("node_id")}
        if operation == "get_worker_status":
            return [{"node_id": "worker-1", "ready": True}]
        if operation == "assign_task":
            return {"delivered": True, "owners": args["task"]["owner_node_ids"]}
        if operation == "preflight_assignment":
            return {"admitted": list(args["worker_node_ids"])}
        if operation.startswith("notify_"):
            return {"delivered": True, "operation": operation}
        raise AssertionError(f"unexpected application-control operation: {operation}")


def _runtime(root: Path, app: FakeApplicationControl) -> SovereignToolRuntime:
    return SovereignToolRuntime(app, root, policy=SovereignPolicy())


def _call(runtime: SovereignToolRuntime, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = handle_request(runtime, {
        "jsonrpc": "2.0",
        "id": name,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _ok(runtime: SovereignToolRuntime, called: set[str], name: str,
        arguments: dict[str, Any]) -> Any:
    payload = _call(runtime, name, arguments)
    assert payload["isError"] is False, payload["content"]
    assert "structuredContent" in payload
    called.add(name)
    return payload["structuredContent"]


def _candidate_args(task_id: str, evidence: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "summary": "protocol candidate",
        "claims": ["the real handler completed"],
        "evidence_refs": [evidence],
        "peer_messages_considered": [],
        "debates_considered": [],
        "limitations": [],
    }


def test_every_declared_handler_executes_through_real_tools_call_protocol(tmp_path: Path) -> None:
    apps = {
        "cond": FakeApplicationControl("cond-1", "conductor", "openai", "codex"),
        "w1": FakeApplicationControl("worker-1", "worker", "grok_build", "grok-4.5"),
        "w2": FakeApplicationControl("worker-2", "worker", "google_antigravity", "gemini"),
    }
    runtimes = {name: _runtime(tmp_path, app) for name, app in apps.items()}
    called: set[str] = set()
    cond, w1, w2 = runtimes["cond"], runtimes["w1"], runtimes["w2"]
    try:
        assert _ok(cond, called, "list_models", {})[0]["provider_id"] == "grok_build"
        # `model_id` added at W-33. This call omitted it and passed, because nothing enforced the
        # declared inputSchema — which lists provider/model_id/role as REQUIRED and whose
        # description states that "the runtime has no hidden vendor aliases or model defaults". The
        # fixture was exercising a call the published contract forbids, and relying on exactly the
        # default the description denies. A SUITE defect, repaired per the U451 precedent; no
        # product code constructs these arguments (they arrive from the MCP client).
        assert _ok(cond, called, "spawn_worker", {
            "provider": "grok_build", "model_id": "grok-4.5", "role": "reasoning",
        })["ready"] is True
        assert _ok(cond, called, "stop_worker", {"node_id": "worker-spawned"})["stopped"] is True

        assigned = _ok(cond, called, "assign_task", {
            "objective": "exercise every real Sovereign handler",
            "worker_node_ids": ["worker-1", "worker-2"],
            "peer_nodes": ["worker-1", "worker-2"],
            "acceptance_criteria": ["publish both candidates", "publish synthesis"],
        })
        task = assigned["task"]
        task_id, thread_id = task["task_id"], task["thread_id"]
        assert assigned["delivery"]["delivered"] is True

        status = _ok(cond, called, "get_worker_status", {})
        assert status["nodes"][0]["ready"] is True
        assert status["tasks"][0]["task_id"] == task_id

        initial = _ok(w1, called, "read_messages", {"task_id": task_id})
        assert initial["count"] >= 1
        sent = _ok(w1, called, "send_message", {
            "task_id": task_id,
            "thread_id": thread_id,
            "recipient_node_ids": ["worker-2"],
            "message_kind": "question",
            "body": "Did the protocol reach your node?",
        })
        assert sent["notification"]["delivered"] is True
        assert any(message["message_id"] == sent["message"]["message_id"]
                   for message in _ok(w2, called, "read_messages", {"task_id": task_id})["messages"])

        progress = _ok(w1, called, "publish_progress", {
            "task_id": task_id,
            "status": "IN_PROGRESS",
            "working_on": "protocol boundary",
            "what_remains": "candidate",
        })
        assert progress["task"]["status"] == "IN_PROGRESS"

        debate = _ok(cond, called, "open_debate", {
            "task_id": task_id,
            "proposition": "both handlers are reachable",
            "participant_node_ids": ["worker-1", "worker-2"],
            "max_rounds": 1,
        })
        debate_id = debate["debate_id"]
        first_turn = _ok(w1, called, "post_debate_turn", {
            "debate_id": debate_id, "body": "worker one reached the real service",
        })
        _ok(w2, called, "post_debate_turn", {
            "debate_id": debate_id,
            "body": "worker two independently agrees",
            "reply_to": first_turn["turn_id"],
        })
        closed = _ok(cond, called, "close_debate", {
            "debate_id": debate_id,
            "decision": "both protocol paths completed",
            "agreements": ["both workers posted"],
            "disagreements": [],
            "unresolved_points": [],
            "closure_reason": "bounded acceptance complete",
        })
        assert closed["state"] == "CLOSED"

        abandoned = _ok(cond, called, "open_debate", {
            "task_id": task_id,
            "proposition": "aborted debate remains visible",
            "participant_node_ids": ["worker-1", "worker-2"],
            "max_rounds": 1,
        })
        aborted = _ok(cond, called, "abort_debate", {
            "debate_id": abandoned["debate_id"], "reason": "bounded test abort",
        })
        assert aborted["state"] == "ABORTED"

        artifact = _ok(w1, called, "publish_artifact", {
            "task_id": task_id, "content": "real protocol artifact", "media_type": "text/plain",
        })
        read_back = _ok(w2, called, "read_artifact", {"artifact_id": artifact["artifact_id"]})
        assert read_back["content"] == "real protocol artifact"

        first_candidate = _ok(w1, called, "publish_candidate",
                              _candidate_args(task_id, artifact["artifact_id"]))
        second_candidate = _ok(w2, called, "publish_candidate",
                               _candidate_args(task_id, artifact["artifact_id"]))
        assert first_candidate["candidate"]["worker_node_id"] == "worker-1"
        assert second_candidate["candidate"]["worker_node_id"] == "worker-2"

        synthesis = _ok(cond, called, "publish_synthesis", {
            "task_id": task_id,
            "contributions": [
                {"node_id": "worker-1", "contribution": "first protocol proof"},
                {"node_id": "worker-2", "contribution": "second protocol proof"},
            ],
            "points_of_agreement": ["all real handlers were invoked"],
            "points_of_disagreement": [],
            "debate_outcome": "the bounded debate closed",
            "evidence_used": [artifact["artifact_id"]],
            "limitations": ["Electron seam is a deterministic fake"],
            "conductor_judgment": "the JSON-RPC boundary and real persistence agree",
            "recommended_next_action": "retain this acceptance test",
            "debate_ids": [debate_id],
        })
        assert synthesis["synthesis"]["status"] == "SYNTHESIS"
        assert synthesis["synthesis"]["aborted_debate_ids"] == [abandoned["debate_id"]]

        declared = {tool["name"] for tool in TOOLS}
        assert called == declared
    finally:
        for runtime in runtimes.values():
            runtime.close()


def test_publish_role_gates_fail_at_protocol_boundary_before_cas_write(tmp_path: Path) -> None:
    cond = _runtime(tmp_path, FakeApplicationControl("cond", "conductor", "p", "m"))
    try:
        task = _ok(cond, set(), "assign_task", {
            "objective": "gate candidate and synthesis writes",
            "worker_node_ids": ["worker"],
            "peer_nodes": ["worker"],
        })["task"]
    finally:
        cond.close()

    cas = tmp_path / "cas"
    before = sorted(path.relative_to(cas) for path in cas.rglob("*") if path.is_file()) if cas.exists() else []

    conductor = _runtime(tmp_path, FakeApplicationControl("cond", "conductor", "p", "m"))
    worker = _runtime(tmp_path, FakeApplicationControl("worker", "worker", "p", "m"))
    try:
        candidate = _call(conductor, "publish_candidate", _candidate_args(task["task_id"], "e"))
        assert candidate["isError"] is True
        assert "only an assigned worker may publish a candidate" in candidate["content"][0]["text"]

        synthesis = _call(worker, "publish_synthesis", {
            "task_id": task["task_id"],
            "contributions": [{"node_id": "worker", "contribution": "complete"}],
            "points_of_agreement": ["complete"],
            "points_of_disagreement": [],
            "debate_outcome": "none",
            "evidence_used": ["e"],
            "limitations": [],
            "conductor_judgment": "complete",
            "recommended_next_action": "none",
            "debate_ids": [],
        })
        assert synthesis["isError"] is True
        assert "only conductor/operator may publish synthesis" in synthesis["content"][0]["text"]
    finally:
        conductor.close()
        worker.close()

    after = sorted(path.relative_to(cas) for path in cas.rglob("*") if path.is_file()) if cas.exists() else []
    assert after == before


def test_assignment_refusal_preflights_before_append_only_task_creation(tmp_path: Path) -> None:
    class RefusingApplication(FakeApplicationControl):
        def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
            if operation == "preflight_assignment":
                raise RuntimeError("worker stale before task creation")
            return super().call(operation, arguments)

    runtime = _runtime(tmp_path, RefusingApplication("cond", "conductor", "p", "m"))
    try:
        result = _call(runtime, "assign_task", {
            "objective": "must not create a blocked row",
            "worker_node_ids": ["worker"],
        })
        assert result["isError"] is True
        assert "worker stale before task creation" in result["content"][0]["text"]
        assert runtime.collaboration.list_tasks(runtime.identity) == []
    finally:
        runtime.close()


# ---- W-04 / A-5: the stdio transport, in both directions ----------------------------------------
# Inbound, `for line in sys.stdin` decoded with the host ANSI codepage, so non-ASCII task/message/
# artifact content was persisted as mojibake WITH CONTENT HASHES COMPUTED OVER THE MOJIBAKE.
# Outbound, `json.dumps(..., ensure_ascii=False)` was written to a locale-encoded stdout, which
# raises UnicodeEncodeError on the first non-ASCII response character -- a hard failure that can
# kill the server mid-session, not a corruption.
#
# These drive `main()` itself. Its streams are opened with cp1252 on purpose: that reproduces the
# Windows ANSI default on ANY host, so a transport that merely inherits its codec fails here even
# where the locale happens to be right. Spawning the module instead would test nothing -- it
# refuses to start without a live app-control gateway, which is a STARTUP path, not this one.

def _drive_main(monkeypatch, tmp_path: Path, payload: bytes) -> bytes:
    import io
    import sys

    from mcp_server import sovereign_tools as mod

    app = FakeApplicationControl("w-1", "worker", "grok_build", "grok-4.5")
    monkeypatch.setattr(mod, "AppControlClient", lambda *a, **k: app)
    monkeypatch.setenv("SOVEREIGN_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_CONTROL_PORT", "0")
    monkeypatch.setenv("SOVEREIGN_CONTROL_TOKEN", "")

    sink = io.BytesIO()
    stdin = io.TextIOWrapper(io.BytesIO(payload), encoding="cp1252", errors="strict")
    stdout = io.TextIOWrapper(sink, encoding="cp1252", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    assert mod.main() == 0
    stdout.flush()
    return sink.getvalue()


def test_the_stdio_transport_is_utf8_in_both_directions(tmp_path: Path, monkeypatch) -> None:
    """W-04. A non-ASCII method name must survive INTO the server and back OUT of it.

    Say what this test CANNOT do, because it passes against the defect too and a reader will
    otherwise mistake it for a guard: decoding as cp1252 and then ENCODING as cp1252 is a lossless
    round-trip, so a pure echo returns the original bytes whether or not the codec was right. The
    corruption is only observable where the decoded text is KEPT -- see the artifact hash below.
    This is the positive control: the repair must not cost fidelity."""
    import json as _json

    probe = "h\u00e9llo \u2014 \u65e5\u672c\u8a9e"
    frame = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": probe},
                        ensure_ascii=False).encode("utf-8") + b"\n"
    raw = _drive_main(monkeypatch, tmp_path, frame)

    assert raw.strip(), "the server produced no response at all"
    reply = _json.loads(raw.decode("utf-8").splitlines()[0])
    assert reply["error"]["code"] == -32601
    assert probe in reply["error"]["message"], (
        "the method name was mangled in transit: the transport is not UTF-8 end to end")


def test_an_undecodable_input_frame_is_REPORTED_and_never_persisted(
        tmp_path: Path, monkeypatch) -> None:
    """W-04. `strict` on input is a deliberate divergence from `mcp_server/server.py`'s
    `errors="replace"`: that transport DISCARDS its frame, while this one turns input into
    persisted content with hashes computed over it, so silent U+FFFD substitution is precisely the
    corruption this unit exists to remove. A bad frame must be answered, not absorbed -- and the
    server must still be there for the next one."""
    import json as _json

    bad = b'{"jsonrpc":"2.0","id":1,"method":"ping","x":"\xff\xfe"}\n'
    good = _json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode("utf-8") + b"\n"
    raw = _drive_main(monkeypatch, tmp_path, bad + good)

    replies = [_json.loads(ln) for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    assert any(r.get("error", {}).get("code") == -32700 for r in replies), (
        f"an undecodable frame must be reported as a parse error; got {replies}")
    assert any(r.get("id") == 2 and "result" in r for r in replies), (
        "the server must survive a bad frame and still answer the next one")


def test_non_ascii_artifact_content_is_hashed_over_the_ORIGINAL_bytes(
        tmp_path: Path, monkeypatch) -> None:
    """W-04, the half an echo cannot see. `artifact_id` IS `sha256:<hash of the content bytes>`, so
    a transport that decoded the frame with the host ANSI codepage persists mojibake and computes
    the content hash over it -- a stored artifact whose id does not describe what the caller sent."""
    import hashlib
    import json as _json

    # Fixture sweep (U530): W-69 moved publish_artifact's semantics - a task reference is
    # validated BEFORE anything durable happens - so this leg now creates its task through
    # the REAL collaboration service first. The original fixture published into a task that
    # never existed, which is exactly what W-69 refuses. Creation needs a directing role;
    # the publishing identity below stays the worker the transport leg authenticates.
    creator = FakeApplicationControl("cond-1", "conductor", "grok_build", "grok-4.5")
    creator_rt = SovereignToolRuntime(creator, tmp_path, policy=SovereignPolicy())
    try:
        creator_rt.collaboration.create_task(
            creator_rt.identity, objective="non-ascii artifact transport leg",
            owner_node_ids=["w-1"], task_id="t-1")
    finally:
        creator_rt.close()

    content = "caf\u00e9 \u2014 \u65e5\u672c\u8a9e"
    frame = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": "publish_artifact",
                                    "arguments": {"task_id": "t-1", "content": content}}},
                        ensure_ascii=False).encode("utf-8") + b"\n"
    raw = _drive_main(monkeypatch, tmp_path, frame)

    reply = _json.loads(raw.decode("utf-8").splitlines()[0])
    assert reply["result"]["isError"] is False, reply
    artifact = reply["result"]["structuredContent"]
    assert artifact["artifact_id"] == "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(), (
        "the artifact was hashed over MOJIBAKE: the transport decoded the frame with the host "
        "ANSI codepage, so the stored id does not describe the bytes the caller sent")
    assert artifact["size_bytes"] == len(content.encode("utf-8"))
