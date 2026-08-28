"""Loopback wire protocol + client for the Sovereign MCP server (Plan section 4.4; U6).

Transport decision (U6, recorded): the official Python MCP SDK is not installable under the
build's network prohibitions (pip is out of scope; only npm + vendor-doc reads are allowed),
so Phase 3A implements a minimal newline-delimited JSON request/response protocol over a
loopback TCP socket. The server is a genuinely separate OS process bound to 127.0.0.1. The
resource/tool op set mirrors Plan section 9.5; swapping in the MCP SDK later is an adapter
change behind this client.

Fail-closed: a disconnected client raises McpDisconnected; callers must checkpoint locally
and refuse shared-memory-dependent work rather than proceed on stale state (F5).

ONE narrow exception, added at Phase 17B `.legs`: a connection the SERVER has already closed is
re-established before the next request is written (see `_drop_if_peer_closed`). Nothing has been
sent at that point, so this cannot re-apply anything — it is a reconnect, not a retry of applied
work. Every other disconnect, and in particular a LOST RESPONSE, still fails closed exactly as
above, because a delivered request may already have been applied.
"""
from __future__ import annotations

import json
import select
import socket
from typing import Any


class McpError(Exception):
    """Server returned an error verdict (e.g. authorization denied)."""


class McpDisconnected(Exception):
    """Transport failure — fail closed, do not proceed on assumptions."""


def _send_line(sock: socket.socket, obj: dict[str, Any]) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))


def _recv_line(buf: "_LineBuffer") -> dict[str, Any]:
    return json.loads(buf.readline())


class _LineBuffer:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""

    def readline(self) -> str:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise McpDisconnected("server closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8")

    def pending(self) -> bool:
        """Unconsumed bytes from a PREVIOUS response. Strict request/response means this is always
        empty at the start of a call; anything here is a desync, not spare data."""
        return bool(self._buf)


class McpClient:
    def __init__(self, host: str, port: int, token: str, timeout: float = 10.0) -> None:
        self._addr = (host, port)
        self._token = token
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._buf: _LineBuffer | None = None

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection(self._addr, timeout=self._timeout)
            self._buf = _LineBuffer(self._sock)
        except OSError as exc:
            raise McpDisconnected(f"cannot reach MCP server at {self._addr}: {exc}") from exc

    def call(self, op: str, **args: Any) -> Any:
        self._drop_if_peer_closed()
        if self._sock is None:
            self.connect()
        assert self._sock is not None and self._buf is not None
        req = {"token": self._token, "op": op, "args": args}
        self._send_once(req, retry=True)
        try:
            resp = _recv_line(self._buf)
        except (OSError, McpDisconnected) as exc:
            # A SEND that succeeded may have been APPLIED by the server. Re-issuing it could publish
            # a second entry or repeat a status transition, so a lost RESPONSE fails closed: the
            # caller checkpoints and refuses rather than guessing (F5). Only the send is retried.
            self.close()
            raise McpDisconnected(str(exc)) from exc
        if not resp.get("ok"):
            raise McpError(resp.get("error", "unknown error"))
        return resp.get("result")

    def _drop_if_peer_closed(self) -> None:
        """Discard a socket the SERVER has already closed, BEFORE anything is written to it.

        U60's root cause (found at Phase 17B `.legs`): `MCPServer`'s handler carries `timeout = 60`
        so idle threads cannot linger (F6). A live `claude` worker call runs longer than that, so
        while the model is thinking the server reaps the caller's connection. Writing into that
        socket then SUCCEEDS — the FIN is unread and the bytes land in the local send buffer — and
        the failure surfaces on the READ as `WinError 10053`, where retrying is forbidden because a
        delivered request may already have been applied. So the send-side retry below never fires,
        and the governed run degrades: exactly what the first `.legs` live dispatch did.

        Checking BEFORE the write is what makes the recovery safe rather than a guess: nothing has
        been sent, so re-establishing cannot re-apply anything. This only ever discards a connection
        the peer has finished with — a healthy idle socket is neither readable nor errored, and this
        returns without touching it.

        It NARROWS the window; it does not close it. A reap landing between this check and the
        `sendall` below restores the old behaviour — the write succeeds into a FIN'd socket and the
        read fails closed. That outcome is correct (a possibly-applied request is never retried), it
        is just not recovered. Note the structural consequence: with a live worker call bounded at
        420 s against the server's 60 s handler timeout, EVERY live dispatch is reaped at least once
        and relies on this reconnect. That is a workaround for a timeout mismatch, not a resolution
        of it — recorded rather than papered over.
        """
        sock, buf = self._sock, self._buf
        if sock is None or buf is None:
            return
        if buf.pending():
            # A leftover response means the next read would answer THIS request with the PREVIOUS
            # one's result. Reconnecting would discard it silently and proceeding would mis-attribute
            # it — refuse instead (fail closed on ambiguity).
            self.close()
            raise McpDisconnected(
                "channel desync: an unconsumed response is buffered — refusing to send a request "
                "whose reply could not be told apart from it")
        try:
            fileno = sock.fileno()
        except Exception:               # noqa: BLE001 — not a real socket; nothing to check here
            return
        if not isinstance(fileno, int) or fileno < 0:
            self.close()                # already closed locally
            return
        try:
            readable, _, errored = select.select([sock], [], [sock], 0)
        except (OSError, ValueError):   # an invalid fd is not usable either
            self.close()
            return
        if not readable and not errored:
            return                      # healthy: no FIN, no error pending
        try:
            peeked = sock.recv(1, socket.MSG_PEEK)
        except OSError:                 # aborted/reset — dead, and nothing has been written yet
            self.close()
            return
        if not peeked:
            self.close()                # clean FIN: the server reaped this idle connection
            return
        # Readable with real data before we asked anything: same desync as above.
        self.close()
        raise McpDisconnected(
            "channel desync: unrequested data arrived on the channel — refusing to send a request "
            "whose reply could not be told apart from it")

    def _send_once(self, req: dict[str, Any], *, retry: bool) -> None:
        """Write one request line, re-establishing the socket ONCE if the write itself fails.

        U60 (narrowed here): across a multi-minute LIVE model call the caller's loopback socket sits
        idle and Windows can abort it (`WinError 10053`), so the very next request fails on the
        WRITE — before a complete line ever reaches the server. A request that was never delivered
        cannot have been applied (the server reads newline-delimited requests, and a partial write is
        not a request), so re-connecting and sending it again is safe in a way that retrying a lost
        RESPONSE is not. Exactly one retry: a second failure is a real transport fault, fail closed.
        """
        assert self._sock is not None
        try:
            _send_line(self._sock, req)
            return
        except OSError as exc:
            self.close()
            if not retry:
                raise McpDisconnected(str(exc)) from exc
        self.connect()                      # raises McpDisconnected when the server is truly gone
        self._send_once(req, retry=False)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._buf = None

    def __enter__(self) -> "McpClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
