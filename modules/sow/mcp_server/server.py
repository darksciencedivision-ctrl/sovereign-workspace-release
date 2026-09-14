"""Sovereign MCP server: access/transport over a loopback socket (Plan sections 3.2, 9.5).

Responsibilities are deliberately thin (I-M2): parse the wire envelope, AUTHENTICATE the
token to an Identity (auth.py), and DISPATCH to the memory service. It contains NO
authorization logic of its own — every write path's allow/deny is decided by
control_plane.policy inside the memory service. Grep this file for role checks: there are
none. That absence is the invariant.

Runs as a genuinely separate OS process bound to 127.0.0.1 (see run_server.py). Threaded so
the concurrent-writer conflict test exercises real parallel requests.
"""
from __future__ import annotations

import json
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

from control_plane.policy import SovereignPolicy
from mcp_server.auth import CredentialStore
from mcp_server.memory_service import MemoryService, MemoryServiceError
from mcp_server import lifecycle
from persistence import ContentAddressedStore, SovereignStore


class MCPServer:
    def __init__(self, store_dir: Path) -> None:
        store_dir = Path(store_dir)
        self.store = SovereignStore(store_dir / "sovereign.db")
        self.cas = ContentAddressedStore(store_dir / "cas")
        self.policy = SovereignPolicy()
        self.credentials = CredentialStore()
        self.service = MemoryService(self.store, self.cas, self.policy)
        self._server: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None

    # -- op dispatch (authenticate, then delegate; no authorization here) ------
    def handle(self, req: dict[str, Any]) -> dict[str, Any]:
        token = req.get("token")
        op = req.get("op")
        args = req.get("args", {})
        identity = self.credentials.verify(token) if isinstance(token, str) else None
        if identity is None:
            return {"ok": False, "error": "authentication failed"}
        try:
            result = self._dispatch(identity, op, args)
            return {"ok": True, "result": result}
        except (MemoryServiceError, lifecycle.IllegalStatusTransition) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # fail closed, but say what broke
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _dispatch(self, identity: Any, op: str, args: dict[str, Any]) -> Any:
        svc = self.service
        if op == "health":
            return svc.health(identity)
        if op == "read_status":
            return svc.read_status(identity, identity.project_id, args["status"])
        if op == "get_head":
            return svc.get_head_entry(identity, args["entry_id"])
        if op == "get_content":
            return svc.get_entry_content(identity, args["entry_id"])
        if op == "publish":
            return svc.publish(identity, kind=args["kind"], tier=args.get("tier", "shared_project"),
                               content=_from_b64(args["content_b64"]), provenance=args["provenance"],
                               status=args.get("status", "CANDIDATE"))
        if op == "transition":
            return svc.transition(identity, entry_id=args["entry_id"], requested_status=args["requested_status"],
                                  successor_ref=args.get("successor_ref"), reviewer_note=args.get("reviewer_note"))
        if op == "put_artifact":
            return svc.put_artifact(identity, content=_from_b64(args["content_b64"]),
                                    media_type=args.get("media_type", "application/octet-stream"),
                                    task_id=args.get("task_id"))
        if op == "get_artifact":
            return svc.get_artifact(identity, args["artifact_id"])
        if op == "list_conflicts":
            return svc.list_conflicts(identity, args.get("key"))
        raise MemoryServiceError(f"unknown op: {op}")

    # -- lifecycle -------------------------------------------------------------
    def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        outer = self

        max_line = 8 * 1024 * 1024  # bound pre-auth buffering (spec-audit F6)

        class Handler(socketserver.StreamRequestHandler):
            timeout = 60  # idle handler threads must not linger forever (F6)

            def handle(self) -> None:
                try:
                    while True:
                        raw = self.rfile.readline(max_line + 1)
                        if not raw:
                            break
                        if len(raw) > max_line:
                            self.wfile.write(b'{"ok": false, "error": "request too large"}\n')
                            self.wfile.flush()
                            break
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            req = json.loads(line)
                        except json.JSONDecodeError:
                            resp = {"ok": False, "error": "malformed request"}
                        else:
                            resp = outer.handle(req)
                        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
                        self.wfile.flush()
                except (TimeoutError, OSError):
                    pass  # client vanished or idled out; just end the handler
                finally:
                    outer.store.close_thread_conn()  # don't leak this thread's WAL connection (F5)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = sys.platform != "win32"
            daemon_threads = True

        self._server = Server((host, port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="mcp-server")
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self.store.close()


def _from_b64(s: str) -> bytes:
    import base64
    return base64.b64decode(s.encode("ascii"))
