"""Reference IPC client (Python, stdlib) for the loopback-WebSocket control channel.

Two roles:
  - it is the client used by the IPC test suite;
  - it is the reference the desktop shell's Node/Chromium client mirrors (same handshake,
    same signed-envelope contract) — the shell uses a native WebSocket, but the message
    framing and the compute/verify of integrity are identical.

Fail-closed: any transport fault raises IpcDisconnected; a response whose integrity does not
verify raises IpcIntegrityError. Callers must not proceed on unverified control-plane state.
"""
from __future__ import annotations

import socket
from typing import Any

from control_plane.ipc import envelope as env
from control_plane.ipc import wsframe


class IpcDisconnected(Exception):
    """Transport failure — fail closed, do not proceed on assumptions."""


class IpcIntegrityError(Exception):
    """A response envelope did not verify against the shared key — treat as untrusted."""


class IpcClient:
    def __init__(self, host: str, port: int, node_id: str, token: str, key: bytes,
                 scope: str = "project", timeout: float = 10.0) -> None:
        self._addr = (host, port)
        self._node_id = node_id
        self._token = token
        self._key = key
        self._scope = scope
        self._timeout = timeout
        self._sock: socket.socket | None = None
        self._conn: wsframe.FrameConn | None = None

    def connect(self) -> None:
        try:
            self._sock = socket.create_connection(self._addr, timeout=self._timeout)
            self._conn = wsframe.perform_client_handshake(self._sock, *self._addr)
        except (OSError, wsframe.WsError, wsframe.WsClosed) as exc:
            self.close()
            raise IpcDisconnected(f"cannot reach IPC gateway at {self._addr}: {exc}") from exc

    def control_event(self, payload: dict[str, Any], *, task_id: str | None = None) -> dict[str, Any]:
        """Send one control_event envelope, return the verified response payload."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        request = env.make_envelope(
            from_node=self._node_id, to=["control-plane"], msg_type="control_event",
            payload=payload, node_credential=self._token, scope=self._scope, key=self._key,
            task_id=task_id,
        )
        try:
            self._conn.send_text(_json_dumps(request))
            text = self._conn.recv_text()
        except (wsframe.WsClosed, wsframe.WsError, OSError) as exc:
            self.close()
            raise IpcDisconnected(str(exc)) from exc
        response = _json_loads(text)
        env.validate_structure(response)
        if not env.verify_integrity(self._key, response):
            raise IpcIntegrityError("response integrity did not verify")
        return response["payload"]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        elif self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def __enter__(self) -> "IpcClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _json_dumps(obj: dict[str, Any]) -> str:
    import json

    return json.dumps(obj)


def _json_loads(text: str) -> Any:
    import json

    return json.loads(text)
