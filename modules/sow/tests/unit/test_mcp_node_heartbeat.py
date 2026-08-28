"""W-62 — U434: a node can now be VERIFIED, not only provoked.

Before this unit there was no server->node ping and no node heartbeat, so two true things about a
node could not be told apart from silence: an idle-but-healthy worker, and a node doing store-only
MCP work — `read_messages`, `close_debate`, `publish_synthesis`, artifact reads — which is WORKING
and yet never reaches the gateway, because `_lastSeen` (`apps/desktop/control/sovereign-control-server.js`)
observes gateway-mediated calls only. U434 named the closure: "A heartbeat the node makes on a
cadence shorter than the staleness window closes both." The repair is `NodeHeartbeat` in
`mcp_server/sovereign_tools.py`, started by `_DeferredRuntime._build` the moment a node's
capability resolves, beating on the gateway's `identity` operation — the one operation that stamps
`_lastSeen` WITHOUT an `_recordOperation` entry, because a liveness beat is not work.

KEY EQUIVALENCE, stated because the tests rely on it: from the gateway's point of view, store-only
work and idleness are the SAME silence — neither produces a gateway arrival. Proving the heartbeat
keeps an idle node fresh therefore proves it keeps a store-only-working node fresh; the control
test below pins the equivalence's other half (a store write reaches the store and NOT the gateway).

THE FRESHNESS RULE these tests apply is the gateway's own — `age <= window` means `connected`,
older means `stale` (UNVERIFIED) — at a window scaled to test time (150 ms instead of 180000 ms).
The production window's VALUE is pinned where it lives, by the desktop suite
(`sovereign-control-server.test.js`); what is verified here is the MECHANISM: arrivals inside the
window are what keep a node verified, and the heartbeat supplies them without provocation.

WHAT THIS DOES NOT CLAIM: that a never-established node is verified — a node that never resolved
its capability has no heartbeat and reads `configured`/`disconnected`, exactly as before; the
heartbeat serves ESTABLISHED nodes, the only kind U434's silence misled anyone about.
"""
from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

WINDOW_MS = 150          # the gateway's rule at test scale (production: 180000, pinned in JS)
BEAT_INTERVAL_S = 0.05   # a cadence inside the test window, as 60 s is inside 180 s


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class _LivenessGateway:
    """The smallest app-control gateway that can speak liveness: it answers every operation and
    records the ARRIVAL TIME of every authenticated request — which is exactly the `_lastSeen`
    stamp the real gateway takes (`_handle`, before dispatch)."""

    def __init__(self, port: int = 0) -> None:
        self.arrivals: list[float] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:                       # noqa: N802 - stdlib naming
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                outer.arrivals.append(time.time())
                # A CONDUCTOR identity: the control leg below does a store-only task write, and
                # only the conductor/operator may create assignments (authorize_task_create).
                payload = json.dumps({"ok": True, "result": {
                    "node_id": "conductor-1", "role": "conductor", "project_id": "proj"}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args: Any) -> None:      # keep pytest output clean
                return

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def age_ms(self) -> float | None:
        """The gateway's own evidence, aged the way `connectionState` ages it."""
        if not self.arrivals:
            return None
        return (time.time() - self.arrivals[-1]) * 1000.0

    def fresh(self) -> bool:
        age = self.age_ms()
        return age is not None and age <= WINDOW_MS

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _runtime(gateway: _LivenessGateway, tmp_path: Path):
    from control_plane.policy import SovereignPolicy
    from mcp_server.sovereign_tools import AppControlClient, SovereignToolRuntime

    app = AppControlClient(gateway.port, "t", timeout=5.0)
    return SovereignToolRuntime(app, tmp_path, policy=SovereignPolicy())


# ---- negative: the defect -----------------------------------------------------------------------

def test_an_established_node_keeps_itself_verifiably_alive_without_being_provoked(tmp_path: Path) -> None:
    """NEGATIVE. The node establishes itself (construction round-trips `identity`), then goes
    QUIET — the state that covers idleness and store-only work alike, since neither produces a
    gateway arrival. Pre-repair nothing beat for it, so the gateway's evidence aged into `stale`
    and the node was unverifiable until provoked; the capability this asserts did not exist
    [OBSERVED pre-repair: "assert hasattr(runtime, 'start_heartbeat')"]. Repaired, the heartbeat
    keeps arrivals inside the window on its own cadence."""
    gateway = _LivenessGateway()
    runtime = _runtime(gateway, tmp_path)
    try:
        assert hasattr(runtime, "start_heartbeat"), (
            "U434: an established node has no way to keep itself verifiably alive — it can only "
            "be provoked or waited for")
        runtime.start_heartbeat(interval_s=BEAT_INTERVAL_S)
        time.sleep(0.25)                     # several beats; no tool call, no provocation
        assert len(gateway.arrivals) >= 3, (
            f"the heartbeat did not keep arriving on cadence: {len(gateway.arrivals)} arrivals")
        assert gateway.fresh(), (
            f"the node's liveness evidence aged out of the window (age "
            f"{gateway.age_ms():.0f} ms > {WINDOW_MS} ms) despite a live heartbeat")
    finally:
        runtime.close()
        gateway.stop()


# ---- control: the defect's mechanics, pinned ------------------------------------------------------

def test_store_only_work_is_invisible_to_the_gateway_and_goes_stale(tmp_path: Path) -> None:
    """CONTROL (passes pre-repair as well — INHERITED mechanics, now pinned beside the repair).
    A store write reaches the store and NOT the gateway, and without a heartbeat the gateway's
    evidence ages out of the window: this is the silence U434 describes, demonstrated, not
    asserted away. If store-only work ever gains a gateway arrival of its own, this test fails
    and the equivalence the negative test relies on must be re-argued."""
    gateway = _LivenessGateway()
    runtime = _runtime(gateway, tmp_path)
    try:
        arrived_before = len(gateway.arrivals)
        # store-only work: a task is created in the SQLite substrate; nothing reaches the gateway
        task = runtime.collaboration.create_task(
            runtime.identity, objective="w62 store-only probe", owner_node_ids=["worker-1"])
        assert task["task_id"], "the store write itself must succeed"
        assert len(gateway.arrivals) == arrived_before, (
            "a store-only write reached the gateway — store-only work is no longer silent")
        time.sleep(WINDOW_MS / 1000.0 + 0.05)
        assert not gateway.fresh(), (
            "without a beat, the gateway's evidence must age out of the window — that aging is "
            "the defect the heartbeat closes")
    finally:
        runtime.close()
        gateway.stop()


# ---- positive: the repair's declared bounds -------------------------------------------------------

def test_the_heartbeat_is_bounded_and_stops_cleanly(tmp_path: Path) -> None:
    """POSITIVE. The beat's HTTP call carries its own short timeout, the stop has a budget it
    reports rather than exceeds, and the thread is a daemon — a heartbeat may never hold the
    process open or outlive `close()`."""
    gateway = _LivenessGateway()
    runtime = _runtime(gateway, tmp_path)
    try:
        heartbeat = runtime.start_heartbeat(interval_s=BEAT_INTERVAL_S)
        deadline = time.time() + 2.0
        while heartbeat.beats == 0 and time.time() < deadline:
            time.sleep(0.01)
        assert heartbeat.beats >= 1, "no beat landed within the bounded wait"
        started = time.time()
        assert heartbeat.stop(timeout_s=1.0) is True, "the heartbeat thread outlived its budget"
        assert time.time() - started < 1.0, "stop exceeded the budget it reports against"
        assert heartbeat._thread.daemon is True, "a heartbeat may not hold the process open"
    finally:
        runtime.close()
        gateway.stop()


def test_a_beat_against_a_dead_gateway_is_swallowed_not_raised() -> None:
    """POSITIVE. A heartbeat that could break a tool call — or crash the node — would be worse
    than the silence it exists to remove: the failed beat is swallowed, reported False, and the
    next beat retries."""
    from mcp_server.sovereign_tools import AppControlClient, NodeHeartbeat

    app = AppControlClient(_closed_port(), "t", timeout=5.0)
    heartbeat = NodeHeartbeat(app, interval_s=BEAT_INTERVAL_S, call_timeout_s=0.5)
    assert heartbeat.beat() is False, "a beat against a dead gateway must report False"
    assert heartbeat.beats == 0, "a failed beat is not a beat"


def test_the_deferred_runtime_starts_the_heartbeat_when_the_capability_resolves(
        tmp_path: Path, monkeypatch: Any) -> None:
    """POSITIVE — the wiring that ships. `_DeferredRuntime._build` starts the cadence the moment
    the capability resolves, so production nodes heartbeat without anyone asking; the interval
    honours the env override a test (or an operator) can set."""
    from mcp_server.sovereign_tools import _DeferredRuntime

    gateway = _LivenessGateway()
    monkeypatch.setenv("SOVEREIGN_HEARTBEAT_INTERVAL_S", str(BEAT_INTERVAL_S))
    holder = _DeferredRuntime(str(gateway.port), "t", tmp_path)
    try:
        holder.call("get_worker_status", {})      # first tool call -> capability resolves
        assert holder._runtime is not None and holder._runtime.heartbeat is not None, (
            "a resolved capability must start the node's liveness cadence")
        time.sleep(0.25)
        assert gateway.fresh(), "the production heartbeat did not keep the node inside the window"
    finally:
        holder.close()
        gateway.stop()
    assert holder._runtime is None or holder._runtime.heartbeat.stop(timeout_s=1.0), (
        "close must leave no heartbeat running")
