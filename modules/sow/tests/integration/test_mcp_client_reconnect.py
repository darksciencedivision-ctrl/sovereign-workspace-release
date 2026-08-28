"""U60 — a caller's loopback channel survives a long LIVE call, without ever re-applying a write.

ROOT CAUSE (found at Phase 17B `.legs`, 2026-07-26): U60 recorded the multi-minute live symptom as
"transient loopback flakiness". It is not transient. `MCPServer`'s handler carries `timeout = 60`
(an F6 resource guard: idle handler threads must not linger). A live `claude` worker call takes
longer than that, so while the model runs the SERVER closes the caller's connection; the caller's
next request then fails on the WRITE with `WinError 10053` and the governed run degrades — exactly
what the first `.legs` live attempt did.

THE RULE UNDER TEST: a request whose WRITE failed never reached the server (it reads newline-
delimited requests, and a partial write is not a request), so re-establishing and sending it again
cannot double-apply it. A request whose write SUCCEEDED may already have been applied, so a lost
RESPONSE is never retried — it fails closed (F5). These two halves are what make the reconnect safe
rather than merely convenient, and both are asserted here.
"""
from __future__ import annotations

import base64
import time

import pytest

from mcp_server.protocol import McpClient, McpDisconnected, McpError
from mcp_server.server import MCPServer


@pytest.fixture()
def srv(tmp_path):
    s = MCPServer(tmp_path / "store")
    s.start()
    yield s
    s.stop()


def _client(srv, node_id="node-1", role="worker"):
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue(node_id, role, "proj"))
    c.connect()
    return c


def _bodies(srv) -> list[str]:
    """Every CANDIDATE body in the project, read back through a fresh operator client."""
    reader = _client(srv, "audit", "operator")
    try:
        entries = reader.call("read_status", status="CANDIDATE")
        return [base64.b64decode(reader.call("get_content", entry_id=e["entry_id"])["content_b64"]).decode("utf-8")
                for e in entries]
    finally:
        reader.close()


def _publish(client, body: str):
    return client.call("publish", kind="finding", tier="shared_project",
                       content_b64=base64.b64encode(body.encode("utf-8")).decode("ascii"),
                       provenance={"author_node": "node-1", "task_id": None,
                                   "ts": "2026-07-26T00:00:00+00:00",
                                   "directive_version": "v2.4", "confidence": "medium"},
                       status="CANDIDATE")


def test_a_write_to_a_socket_the_server_dropped_reconnects_and_succeeds(srv) -> None:
    """The U60 scenario, reproduced deterministically: the connection is gone when the caller comes
    back from a long call. The publish still lands — once."""
    client = _client(srv)
    first = _publish(client, "before the long call")

    # exactly what the server's 60 s idle timeout does to an idle caller, without waiting 60 s
    client._sock.close()          # noqa: SLF001 — reproducing a dropped connection is the point

    second = _publish(client, "after the long call")
    assert second["entry_id"] and second["entry_id"] != first["entry_id"]

    assert _bodies(srv).count("after the long call") == 1, "the retried write was applied twice"
    client.close()


def test_a_connection_the_server_reaped_is_re_established_before_the_next_write(srv) -> None:
    """The ACTUAL U60 scenario, driven through the server's REAL idle-reap path.

    The handler's `timeout` (60 s in the product, shortened here so the test does not sleep a
    minute) is what closes an idle caller's connection while a live model call runs. The client's
    socket stays locally valid — it holds an unread FIN — which is precisely NOT the locally-closed
    socket the sibling test forces: a write into a FIN'd socket SUCCEEDS into the local send buffer,
    so the send-side retry never fires and the failure lands on the READ, where retrying is
    forbidden. The caller must come back from its long call and still have its publish land, once.
    """
    srv._server.RequestHandlerClass.timeout = 0.5   # noqa: SLF001 — the product value is 60 s
    client = _client(srv)
    first = _publish(client, "before the long call")

    time.sleep(1.5)                                 # the "multi-minute live model call", compressed

    second = _publish(client, "after the reap")
    assert second["entry_id"] and second["entry_id"] != first["entry_id"]
    assert _bodies(srv).count("after the reap") == 1, "the re-sent write was applied twice"
    assert _bodies(srv).count("before the long call") == 1, "the pre-call write was re-applied"
    client.close()


def test_unread_data_on_the_channel_fails_closed_rather_than_reconnecting(srv) -> None:
    """A buffered line means a previous response was never consumed, so this channel is desynced:
    the next read would answer THIS request with the PREVIOUS one's result. Reconnecting would
    silently discard it and proceeding would mis-attribute it — both are worse than refusing
    (fail closed on ambiguity, Buildout §4)."""
    client = _client(srv)
    client._buf._buf = b'{"ok": true, "result": "a response for some earlier request"}\n'  # noqa: SLF001
    with pytest.raises(McpDisconnected, match="desync"):
        _publish(client, "must not be sent onto a desynced channel")
    client.close()


def test_a_lost_RESPONSE_is_never_retried(srv, monkeypatch) -> None:
    """The other half: the request WAS delivered, so it may have been applied. Re-sending could
    double-publish — the call fails closed instead (F5)."""
    client = _client(srv)
    import mcp_server.protocol as protocol

    def _boom(_buf):
        raise OSError("connection reset while awaiting the response")

    monkeypatch.setattr(protocol, "_recv_line", _boom)
    with pytest.raises(McpDisconnected):
        _publish(client, "response lost in flight")
    client.close()

    # the entry the server may have applied is NOT duplicated by a retry from this client
    monkeypatch.undo()
    assert _bodies(srv).count("response lost in flight") <= 1


def test_the_write_is_retried_exactly_once_then_fails_closed(srv) -> None:
    """A second write failure is a real transport fault, not a stale socket — no retry loop."""
    client = _client(srv)
    sends: list[int] = []

    class _DeadSocket:
        def sendall(self, _data):
            sends.append(1)
            raise OSError("dead")

        def close(self):
            pass

    client._sock = _DeadSocket()   # noqa: SLF001
    srv.stop()                     # so the reconnect cannot succeed either
    with pytest.raises(McpDisconnected):
        _publish(client, "never lands")
    assert len(sends) == 1, "the dead socket was written to more than once"


def test_a_reconnect_still_presents_the_same_credential(srv) -> None:
    """The retry re-establishes a socket; it does not re-issue or widen authority. A client whose
    token was never valid stays refused after a reconnect (invariant 7 — MCP is access, not
    authority; the loop must not turn a transport retry into an authorization event)."""
    bad = McpClient("127.0.0.1", srv.port, "not-a-real-token")
    bad.connect()
    bad._sock.close()              # noqa: SLF001 — force the reconnect path
    with pytest.raises(McpError, match="authentication failed") as exc:
        bad.call("read", tier="shared_project")
    assert "authentication failed" in str(exc.value).lower()
    bad.close()
