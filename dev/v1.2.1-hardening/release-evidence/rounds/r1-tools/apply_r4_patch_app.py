from pathlib import Path

app = Path("app.py")
src = app.read_text(encoding="utf-8")

def rep(old, new, count=1):
    global src
    assert src.count(old) == count, f"x{src.count(old)} != x{count}: {old[:70]!r}"
    src = src.replace(old, new)

# 1. policy helper for permitted origins
rep(
    '''def resolve_ollama_base(''',
    '''def build_allowed_origins(port: int) -> frozenset:
    """Permitted browser origins for a loopback-bound deployment."""
    hosts = ("127.0.0.1", "localhost", "[::1]")
    return frozenset(
        f"{scheme}://{host}:{port}"
        for scheme in ("http", "https")
        for host in hosts
    )


def resolve_ollama_base(''',
)

# 2. DEFAULTS gains the documented non-browser exception flag
rep(
    'DEFAULTS = {\n    "ollama_url": "http://127.0.0.1:11434",\n    "allow_remote_ollama": False,\n',
    'DEFAULTS = {\n    "ollama_url": "http://127.0.0.1:11434",\n    "allow_remote_ollama": False,\n    "allow_originless_ws_clients": True,\n',
)
rep(
    '''    if not isinstance(normalized.get("allow_remote_ollama"), bool):
        normalized["allow_remote_ollama"] = False''',
    '''    if not isinstance(normalized.get("allow_remote_ollama"), bool):
        normalized["allow_remote_ollama"] = False
    if not isinstance(normalized.get("allow_originless_ws_clients"), bool):
        normalized["allow_originless_ws_clients"] = True''',
)

# 3. guard class + installation right after FastAPI creation
rep(
    'app = FastAPI(title="Debate Table", lifespan=lifespan)\n',
    '''LOOPBACK_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})
_MUTATION_PREFIXES = ("/api/",)


def _host_is_permitted(host_header: str, port: int) -> bool:
    hostname = host_header.strip().lower()
    if hostname.startswith("["):
        closing = hostname.find("]")
        if closing == -1:
            return False
        host_part = hostname[1:closing]
        remainder = hostname[closing + 1 :]
        if remainder.startswith(":"):
            return host_part in LOOPBACK_HOSTNAMES and remainder[1:] == str(port)
        return host_part in LOOPBACK_HOSTNAMES
    if ":" in hostname:
        host_part, _, port_part = hostname.rpartition(":")
        return host_part in LOOPBACK_HOSTNAMES and port_part == str(port)
    return hostname in LOOPBACK_HOSTNAMES


def _origin_permitted(origin: str, allowed_origins: frozenset) -> bool:
    candidate = origin.strip()
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if host not in LOOPBACK_HOSTNAMES:
        return False
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return f"{parts.scheme}://{host}{f'[{host}]' if ':' in host else ''}:{port}" in (
        allowed_origins
        | {
            f"{scheme}://[{h}]:{port}"
            for h in LOOPBACK_HOSTNAMES
            for scheme in ("http", "https")
        }
    )


class LoopbackControlPlaneGuard:
    """ASGI entry guard: Host validation, WS Origin policy, mutation defense.

    P0-11: only loopback Host headers are accepted.
    P0-10: WS handshakes with a foreign Origin are closed BEFORE accept();
           absent Origin is a non-browser client governed by the explicit
           allow_originless_ws_clients setting.
    P0-12: state-changing POSTs reject cross-site browser invocations.
    """

    def __init__(self, inner):
        self.inner = inner

    def _header(self, scope, name: bytes):
        for key, value in scope.get("headers", []):
            if key == name:
                return value.decode("latin-1")
        return None

    def _reject_http(self, send, status: int, message: str):
        body = json.dumps({"error": message}).encode("utf-8")
        reason = {400: "Bad Request", 403: "Forbidden", 421: "Misdirected Request"}[
            status
        ]

        async def send_wrapper(event):
            if event["type"] == "http.response.start":
                event = {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            elif event["type"] == "http.response.body":
                event = {"type": "http.response.body", "body": body}
            await send(event)

        # Emit the rejection directly without invoking the inner app.
        import asyncio

        async def _emit():
            await send_wrapper({"type": "http.response.start"})
            await send_wrapper({"type": "http.response.body", "body": body})

        return _emit()

    async def _reject_ws(self, send, code: int = 1008):
        await send({"type": "websocket.close", "code": code})

    async def __call__(self, scope, receive, send):
        scope_type = scope["type"]
        if scope_type not in ("http", "websocket"):
            return await self.inner(scope, receive, send)

        port = int(CONFIG["port"])
        host_header = self._header(scope, b"host")
        if host_header is None or not _host_is_permitted(host_header, port):
            if scope_type == "http":
                return await self._reject_http(send, 421, "invalid host header")
            return await self._reject_ws(send)

        allowed_origins = build_allowed_origins(port)

        if scope_type == "websocket":
            origin = self._header(scope, b"origin")
            if origin is not None:
                if not _origin_permitted(origin, allowed_origins):
                    return await self._reject_ws(send)
            elif not CONFIG["allow_originless_ws_clients"]:
                return await self._reject_ws(send)
            return await self.inner(scope, receive, send)

        # http scope
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        if (
            method == "POST"
            and any(path.startswith(p) for p in _MUTATION_PREFIXES)
            and path != "/api/models"
        ):
            sec_fetch_site = self._header(scope, b"sec-fetch-site")
            if sec_fetch_site and sec_fetch_site.strip().lower() == "cross-site":
                return await self._reject_http(
                    send, 403, "cross-site request rejected"
                )
            origin = self._header(scope, b"origin")
            if origin is not None and not _origin_permitted(origin, allowed_origins):
                return await self._reject_http(
                    send, 403, "foreign-origin request rejected"
                )
        return await self.inner(scope, receive, send)


app.add_middleware(LoopbackControlPlaneGuard)
''',
)

# urlsplit import comes from config_policy already; app.py needs it directly
rep(
    "import re\nimport sys\n",
    "import re\nimport sys\n",
)

app.write_bytes(src.encode("utf-8"))
print("R4_APP_PATCH_OK")
