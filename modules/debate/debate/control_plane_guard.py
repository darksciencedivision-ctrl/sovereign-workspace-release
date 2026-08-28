"""Local control-plane isolation guard (P0-10, P0-11, P0-12).

Installed as ASGI middleware so HTTP and WebSocket scopes are both policed
at the entry point, before any route handler or ws.accept() runs.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

LOOPBACK_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def build_allowed_origins(port: int) -> frozenset:
    """Permitted browser origins for a loopback-bound deployment."""
    hosts = ("127.0.0.1", "localhost", "[::1]")
    return frozenset(
        f"{scheme}://{host}:{port}" for scheme in ("http", "https") for host in hosts
    )


def _host_is_permitted(host_header: str, port: int) -> bool:
    value = host_header.strip().lower()
    if value.startswith("["):
        closing = value.find("]")
        if closing == -1:
            return False
        host_part = value[1:closing]
        remainder = value[closing + 1:]
        if remainder.startswith(":"):
            return host_part in LOOPBACK_HOSTNAMES and remainder[1:] == str(port)
        return host_part in LOOPBACK_HOSTNAMES
    if ":" in value:
        host_part, _, port_part = value.rpartition(":")
        return host_part in LOOPBACK_HOSTNAMES and port_part == str(port)
    return value in LOOPBACK_HOSTNAMES


def _origin_permitted(origin: str, port: int) -> bool:
    try:
        parts = urlsplit(origin.strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    if host not in LOOPBACK_HOSTNAMES:
        return False
    effective_port = parts.port or (443 if parts.scheme == "https" else 80)
    return effective_port == port


class LoopbackControlPlaneGuard:
    """ASGI entry guard enforcing local control-plane isolation.

    P0-11: only loopback Host headers are accepted (421 / close otherwise).
    P0-10: WS handshakes carrying a foreign Origin are closed BEFORE accept();
           absent Origin is a non-browser client governed by the explicit
           allow_originless_ws_clients setting.
    P0-12: state-changing POSTs reject cross-site browser invocations
           (Sec-Fetch-Site=cross-site or foreign Origin) with 403.
    """

    def __init__(self, inner, config):
        self.inner = inner
        self.config = config

    @staticmethod
    def _header(scope, name: bytes):
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None

    async def _reject_http(self, send, status: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        scope_type = scope["type"]
        if scope_type not in ("http", "websocket"):
            return await self.inner(scope, receive, send)

        port = int(self.config["port"])
        host_header = self._header(scope, b"host")
        if host_header is None or not _host_is_permitted(host_header, port):
            if scope_type == "http":
                await self._reject_http(send, 421, "invalid host header")
            else:
                await send({"type": "websocket.close", "code": 1008})
            return

        if scope_type == "websocket":
            origin = self._header(scope, b"origin")
            if origin is not None:
                if not _origin_permitted(origin, port):
                    await send({"type": "websocket.close", "code": 1008})
                    return
            elif not self.config["allow_originless_ws_clients"]:
                await send({"type": "websocket.close", "code": 1008})
                return
            return await self.inner(scope, receive, send)

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if method == "POST" and path.startswith("/api/") and path != "/api/models":
            sec_fetch_site = self._header(scope, b"sec-fetch-site")
            if sec_fetch_site and sec_fetch_site.strip().lower() == "cross-site":
                await self._reject_http(send, 403, "cross-site request rejected")
                return
            origin = self._header(scope, b"origin")
            if origin is not None and not _origin_permitted(origin, port):
                await self._reject_http(send, 403, "foreign-origin request rejected")
                return
        return await self.inner(scope, receive, send)