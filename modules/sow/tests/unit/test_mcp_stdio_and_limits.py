"""W-34 — three unbounded surfaces on the MCP path: the stdio frame, artifact size, call rate.

All three are the same shape: a governed surface with no ceiling, where the caller is a model. The
review's concern is not malice — a worker that pastes a build log into `publish_artifact`, or loops
on a tool call, is the ordinary case.

WHAT EACH BOUND IS FOR, since they are not interchangeable:

  stdio frame   the read loop buffers a line with no limit, so one frame with no newline is
                unbounded memory in the server process BEFORE anything is parsed or authorized.
                The donor is `mcp_server/server.py:86` — the sibling transport already bounds its
                pre-auth buffering at 8 MiB and answers "request too large" (spec-audit F6).
  artifact      content is persisted into CAS and hashed. There is no frame to discard: an
                oversized artifact becomes a durable object.
  rate          a node that loops on a tool call is not stopped by either size bound, because each
                individual call is small.

NOT AUTHORIZATION (invariant 7). None of these decides who may call what. They are ceilings on a
surface this process already serves, and a refusal NAMES the ceiling it hit so the caller can act
on it rather than guess.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcp_server.sovereign_tools import (
    MAX_ARTIFACT_BYTES,
    MAX_STDIO_LINE_BYTES,
    SovereignToolRuntime,
    ToolError,
)

ROOT = Path(__file__).resolve().parents[2]


class _App:
    def identity_details(self) -> dict[str, str]:
        return {"node_id": "worker-1", "role": "worker", "project_id": "proj"}

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        return {"ok": True}


class _ConductorApp:
    """Directing-role identity for fixture setup that must create tasks (N4a/U537)."""

    def identity_details(self) -> dict[str, str]:
        return {"node_id": "cond-1", "role": "conductor", "project_id": "proj"}

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        return {"ok": True}


@pytest.fixture()
def runtime(tmp_path: Path):
    from control_plane.policy import SovereignPolicy

    rt = SovereignToolRuntime(_App(), tmp_path, policy=SovereignPolicy())
    yield rt
    rt.close()


# ---- artifact ceiling --------------------------------------------------------------------------

def test_a_20MB_artifact_is_refused_with_a_named_reason(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE, the directive's own case. Refused, and the refusal says WHY and WHAT the limit is.

    An artifact is not a frame that can be dropped — it is persisted into CAS and addressed by the
    hash of its content, so an unbounded one is a durable object nobody chose to keep.
    """
    payload = "x" * (20 * 1024 * 1024)
    with pytest.raises(ToolError) as exc:
        runtime.call("publish_artifact", {"task_id": "t-1", "content": payload})
    message = str(exc.value)
    assert "too large" in message, "the refusal must say the content was too large"
    assert str(MAX_ARTIFACT_BYTES) in message, "a ceiling the caller cannot see is not actionable"


def test_an_artifact_at_the_ceiling_is_still_accepted(
    runtime: SovereignToolRuntime, tmp_path: Path
) -> None:
    """POSITIVE: the bound must be a ceiling, not an off-by-one that rejects the legal maximum."""
    # Fixture sweep (N4a, registered U537): W-69 moved publish_artifact's semantics - a task
    # reference is validated - so this leg creates its task through the REAL collaboration
    # service first, exactly the U530 protocol-e2e pattern. Creation needs a directing role;
    # the publishing identity below stays the worker the runtime fixture authenticates.
    from control_plane.policy import SovereignPolicy

    creator = SovereignToolRuntime(_ConductorApp(), tmp_path, policy=SovereignPolicy())
    try:
        creator.collaboration.create_task(
            creator.identity, objective="artifact ceiling leg",
            owner_node_ids=["worker-1"], task_id="t-1")
    finally:
        creator.close()
    payload = "y" * MAX_ARTIFACT_BYTES
    result = runtime.call("publish_artifact", {"task_id": "t-1", "content": payload})
    assert result["artifact_id"].startswith("sha256:")


def test_the_ceiling_counts_ENCODED_bytes_not_characters(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE: the stored object is UTF-8 bytes, so a character count would under-measure.

    One `€` is 3 bytes. A limit applied to `len(str)` would admit an object three times the
    ceiling, which is the bound being wrong in the direction that matters.
    """
    payload = "€" * MAX_ARTIFACT_BYTES        # MAX characters, 3x MAX bytes
    with pytest.raises(ToolError) as exc:
        runtime.call("publish_artifact", {"task_id": "t-1", "content": payload})
    assert "too large" in str(exc.value)


# ---- per-node rate limit -----------------------------------------------------------------------

def test_a_node_looping_on_a_tool_call_is_rate_limited(runtime: SovereignToolRuntime) -> None:
    """NEGATIVE: neither size bound stops a loop, because each call is small."""
    from mcp_server.sovereign_tools import MAX_CALLS_PER_WINDOW

    for _ in range(MAX_CALLS_PER_WINDOW):
        runtime.call("get_worker_status", {})
    with pytest.raises(ToolError) as exc:
        runtime.call("get_worker_status", {})
    message = str(exc.value)
    assert "rate" in message.lower()
    assert str(MAX_CALLS_PER_WINDOW) in message, "the refusal must name the ceiling it hit"


def test_the_rate_limit_window_rolls_forward(runtime: SovereignToolRuntime) -> None:
    """POSITIVE: a limit that never releases is an outage, not a ceiling.

    Time is injected rather than slept, so the test states the property instead of taking a second
    of wall clock to observe it.
    """
    from mcp_server.sovereign_tools import RATE_LIMIT_WINDOW_S, MAX_CALLS_PER_WINDOW

    now = [1000.0]
    runtime._clock = lambda: now[0]
    for _ in range(MAX_CALLS_PER_WINDOW):
        runtime.call("get_worker_status", {})
    with pytest.raises(ToolError):
        runtime.call("get_worker_status", {})
    now[0] += RATE_LIMIT_WINDOW_S + 1
    runtime.call("get_worker_status", {})      # the window has rolled; this must succeed


# ---- stdio frame bound -------------------------------------------------------------------------

def test_an_oversized_stdio_frame_is_refused_without_buffering_it_all(tmp_path: Path, stub_gateway: int) -> None:
    """NEGATIVE, driven through the REAL process, because the bound is a property of the read loop.

    A test that called a helper would not prove the `for line in ...` iteration was replaced. This
    spawns the server and feeds it one frame larger than the ceiling with no trailing newline until
    the end.
    """
    oversize = MAX_STDIO_LINE_BYTES + 1024
    frame = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"publish_artifact",' \
            '"arguments":{"task_id":"t","content":"' + ("z" * oversize) + '"}}}\n'
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "mcp_server.sovereign_tools"],
        input=frame, capture_output=True, text=True, timeout=120, cwd=str(ROOT),
        env=_env(tmp_path, stub_gateway),
    )
    out = proc.stdout.strip().splitlines()
    assert out, f"the server produced no reply; stderr={proc.stderr[:400]}"
    reply = json.loads(out[-1])
    assert "error" in reply, f"an oversized frame must be answered with an error: {reply}"
    assert "too large" in json.dumps(reply).lower()


def test_a_normal_frame_still_round_trips(tmp_path: Path, stub_gateway: int) -> None:
    """POSITIVE: the bound must not break the ordinary path. Same process, a small frame."""
    frame = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n'
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "mcp_server.sovereign_tools"],
        input=frame, capture_output=True, text=True, timeout=120, cwd=str(ROOT),
        env=_env(tmp_path, stub_gateway),
    )
    out = proc.stdout.strip().splitlines()
    assert out, f"no reply; stderr={proc.stderr[:400]}"
    reply = json.loads(out[-1])
    assert "result" in reply and reply["result"]["tools"], reply


def _env(tmp_path: Path, port: int) -> dict[str, str]:
    import os

    return {**os.environ, "SOVEREIGN_STORE_ROOT": str(tmp_path),
            "SOVEREIGN_CONTROL_PORT": str(port), "SOVEREIGN_CONTROL_TOKEN": "t",
            "PYTHONPATH": str(ROOT)}


@pytest.fixture()
def stub_gateway():
    """The smallest app-control surface the server needs to finish starting.

    The MCP server performs a synchronous HTTP round-trip to the application before it reads a
    single byte of stdin, so a subprocess test cannot reach the read loop without one. (That startup
    ordering is W-55's finding and is NOT addressed here — this fixture works around it so the frame
    bound can be driven through the real process, which is the only place that property lives.)
    """
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:                       # noqa: N802 - stdlib naming
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            payload = json.dumps({"ok": True, "result": {
                "node_id": "worker-1", "role": "worker", "project_id": "proj"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: Any) -> None:      # keep pytest output clean
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
