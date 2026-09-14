"""The shell <-> control-plane IPC gateway (D-IPC-01).

A loopback WebSocket server that authenticates each connecting node, verifies every
envelope's schema and integrity, and forwards authorized control events to a ControlSurface.
It holds NO authorization logic of its own (I-M2): it authenticates, binds the claimed
identity to the credential, verifies integrity, and forwards. Any allow/deny beyond "is this
a real, unforged, authenticated node" belongs to the control plane behind the surface
(e.g. the MCP server's own policy). Grep this file for role checks: there are none.

Fail-closed ladder, in order, per inbound message:
  bad frame (wsframe)       -> close 1002 (protocol error)
  malformed JSON            -> close 1008 (cannot trust bytes)
  bad envelope schema       -> close 1008 (cannot trust fields)
  unknown credential        -> close 1008 (authentication failed)
  from_node != credential   -> close 1008 (identity spoof)
  bad integrity             -> close 1008 (tamper/forgery)
  authenticated but op errs -> SIGNED error response, connection stays up
Responses are themselves signed envelopes so the shell can verify the control plane in turn.
"""
from __future__ import annotations

import secrets
import socket
import socketserver
import sys
import time
import threading
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from control_plane.policy import Identity
from control_plane.ipc import envelope as env
from control_plane.ipc import wsframe

SERVICE_NODE_ID = "control-plane"
_ACCEPTED_INBOUND_TYPES = frozenset({"control_event"})
#: Memory backstop for the W-41 replay cache. Reaching it REFUSES rather than evicting:
#: silent eviction under load is a replay window that opens exactly when it is wanted.
_REPLAY_CACHE_MAX = 100_000


@dataclass(frozen=True)
class IpcCredential:
    identity: Identity
    key: bytes  # per-node shared secret for hmac-sha256 integrity (both directions)


class IpcCredentialStore:
    """Per-node (token, key) issuer. Mirrors mcp_server.auth.CredentialStore, adding the
    shared HMAC key the envelope integrity field is computed against."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_token: dict[str, IpcCredential] = {}

    def issue(self, node_id: str, role: str, project_id: str) -> tuple[str, bytes]:
        token = secrets.token_urlsafe(24)
        key = secrets.token_bytes(32)
        with self._lock:
            self._by_token[token] = IpcCredential(Identity(node_id, role, project_id), key)
        return token, key

    def install(self, token: str, key: bytes, node_id: str, role: str, project_id: str) -> None:
        """Install a caller-supplied (token, key) — used to model a control plane whose
        credential store SURVIVES a restart, so a reconnecting shell re-verifies against the
        same per-node credential (directive §9 track 14A recovery). This does not weaken the
        gateway: it still authenticates every node and verifies every envelope's HMAC; it only
        makes credential lifetime outlive one process, which a persistent store would anyway."""
        with self._lock:
            self._by_token[token] = IpcCredential(Identity(node_id, role, project_id), key)

    def verify(self, token: str) -> IpcCredential | None:
        with self._lock:
            return self._by_token.get(token)

    def revoke(self, token: str) -> None:
        with self._lock:
            self._by_token.pop(token, None)


class ControlSurface(Protocol):
    """What the gateway is allowed to ask the control plane on an authenticated node's
    behalf. Implementations decide their own op set; the gateway only routes."""

    def handle(self, identity: Identity, payload: dict[str, Any]) -> dict[str, Any]: ...


class EchoControlSurface:
    """Diagnostic surface: proves the full transport+auth+integrity path with no dependency
    on a running control plane. Never used where a real surface is available.

    ``health`` is answered here as well as by ``McpControlSurface`` so that ``health`` is a
    UNIVERSAL liveness op every surface satisfies — the shell's supervisor uses it as its
    readiness heartbeat (apps/desktop/supervisor.js) and must get a truthful ``ok`` on any
    surface it is pointed at, not only the MCP-bridged one. It reports only that the
    authenticated channel is alive; it persists nothing (a diagnostic ack, not a write)."""

    def handle(self, identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op == "ping":
            return {"ok": True, "op": "ping", "result": {"pong": payload.get("nonce"), "node": identity.node_id}}
        if op == "health":
            return {"ok": True, "op": "health", "result": {"status": "alive", "surface": "echo", "node": identity.node_id}}
        return {"ok": False, "op": op, "error": f"echo surface: unsupported op {op!r}"}


class McpControlSurface:
    """Bridges a small READ-ONLY op set to the EXISTING control plane (the MCP server),
    proving the chain shell -> IPC gateway -> control plane end to end. This surface adds no
    authorization of its own; MCP applies its own policy (I-M2).

    Honest limitation (spec-audit MINOR, this sub-step): the onward MCP call authenticates
    with a single pre-configured MCP credential, so MCP sees ONE identity for all IPC nodes,
    not the per-node ``identity`` argument. That is safe here because the exposed ops are
    read-only diagnostics. Per-node identity propagation (an IPC->MCP credential broker) is
    required before this surface may carry write ops; tracked as a Phase-14A follow-up so no
    later reuse silently collapses per-node scoping (I-8/I-9). ``identity`` is passed for that
    forward-compatible signature and for logging, and is intentionally not yet forwarded."""

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client_factory = client_factory

    def handle(self, identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op not in ("health", "read_status"):
            return {"ok": False, "op": op, "error": f"mcp surface: unsupported op {op!r}"}
        client = self._client_factory()
        try:
            client.connect()
            if op == "health":
                result = client.call("health")
            else:
                result = client.call("read_status", status=payload.get("status", "ACCEPTED"))
            return {"ok": True, "op": op, "result": result}
        except Exception as exc:  # fail closed: surface the control-plane error, do not fabricate
            return {"ok": False, "op": op, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                client.close()
            except Exception:
                pass


class SubscriptionStatusControlSurface:
    """READ-ONLY observability of the subscription concurrency governor (I-X3; Plan §18.2).

    Exposes the governor's per-subscription ``n/allowance`` count so the shell status bar can
    show live terminal usage (directive §11 track 15A: "the n/2 count live in the shell status
    bar"). Like ``McpControlSurface`` it adds NO authorization of its own (I-M2): the governor
    OWNS the concurrency decision (acquire/refuse) — this surface only reports the count it
    already computed. It cannot register, acquire, or release; it cannot raise an allowance. The
    only ops are ``health`` (universal liveness) and the read-only ``subscription_status``.

    Fail-closed: the ``status_provider`` is called inside a try/except so a control-plane fault
    surfaces as a signed ``{ok: False, error}`` the shell renders as an unknown (never a
    fabricated count), rather than a fabricated or half-built count. The provider returns the
    plain dict from ``SubscriptionGovernor.status()`` (``{ref: {provider, allowance, active,
    in_use}}``); this surface never widens or mutates it."""

    def __init__(self, status_provider: Callable[[], dict[str, Any]]) -> None:
        self._status_provider = status_provider

    def handle(self, identity: Identity, payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op == "health":
            return {"ok": True, "op": "health",
                    "result": {"status": "alive", "surface": "subscription", "node": identity.node_id}}
        if op != "subscription_status":
            return {"ok": False, "op": op, "error": f"subscription surface: unsupported op {op!r}"}
        try:
            return {"ok": True, "op": op, "result": self._status_provider()}
        except Exception as exc:  # fail closed: report the fault, never fabricate a count
            return {"ok": False, "op": op, "error": f"{type(exc).__name__}: {exc}"}


class IpcGateway:
    def __init__(self, credentials: IpcCredentialStore, surface: ControlSurface) -> None:
        self.credentials = credentials
        self.surface = surface
        self._server: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None
        # W-41 replay cache: (from_node, msg_id) -> monotonic time first seen. Its own lock, guarding
        # exactly this state; the credential store keeps its own for its own.
        self._replay_lock = threading.Lock()
        self._replay_seen: dict[tuple[str, str], float] = {}

    # -- per-connection governance --------------------------------------------
    def _serve_conn(self, sock: socket.socket) -> None:
        # F-136(10): idle gateway threads must not linger forever; match MCP handler's 60s bound.
        sock.settimeout(60)
        try:
            conn = wsframe.perform_server_handshake(sock)
        except (wsframe.WsError, wsframe.WsClosed, TimeoutError, OSError):
            try:
                sock.close()
            except OSError:
                pass
            return
        try:
            while True:
                try:
                    text = conn.recv_text()
                except wsframe.WsError:
                    conn.close(wsframe.CLOSE_PROTOCOL_ERROR, "protocol error")
                    return
                verdict = self._authenticate(text)
                if isinstance(verdict, str):  # a close reason -> fail closed, drop the node
                    conn.close(wsframe.CLOSE_POLICY_VIOLATION, verdict)
                    return
                request, cred = verdict
                response = self._dispatch(request, cred)
                conn.send_text(_json_dumps(response))
        except (wsframe.WsClosed, TimeoutError, OSError):
            return
        finally:
            conn.close()

    def _authenticate(self, text: str) -> tuple[dict[str, Any], IpcCredential] | str:
        """Return (request_envelope, credential) on success, or a close-reason string."""
        try:
            request = _json_loads(text)
        except ValueError:
            return "malformed envelope"
        if not isinstance(request, dict):
            return "malformed envelope"
        try:
            env.validate_structure(request)
        except env.EnvelopeError:
            return "envelope failed schema"
        cred = self.credentials.verify(request["auth"]["node_credential"])
        if cred is None:
            return "authentication failed"
        if request["from_node"] != cred.identity.node_id:
            return "identity mismatch"  # claimed from_node is not this credential's node
        # W-41. The ORDER below is the ruling, and two steps in it are load-bearing.
        #
        # (a) Integrity FIRST, over the whole envelope except `integrity` itself, so `from_node`,
        #     `type`, `task_id`, `msg_id` and `ts` are all covered. They were not.
        # (b) The SIGNED `ts` inside the freshness window. Signed, so it is a bound rather than a
        #     claim — and it is what allows the replay cache to be bounded at all.
        # (c) Only THEN the replay identity. Nothing may enter the cache before integrity and
        #     freshness pass, or unauthenticated traffic poisons it: an attacker who observed a
        #     `msg_id` could pre-register it and have the genuine envelope refused as a replay.
        # (d) The record happens INSIDE the same lock as the lookup, before this returns and
        #     therefore before dispatch. Two concurrent copies must not both clear the lookup.
        if not env.verify_integrity(cred.key, request):
            return "integrity check failed"
        if not env.envelope_is_fresh(request):
            return "envelope outside the freshness window"
        if not self._remember_or_reject(request["from_node"], request["msg_id"]):
            return "replayed envelope"
        return request, cred

    def _remember_or_reject(self, from_node: str, msg_id: str) -> bool:
        """Atomically: is `(from_node, msg_id)` unseen, and if so record it? W-41.

        Uses the lock this server already has rather than introducing a second synchronization
        model. Lookup and record are one critical section: split them and two concurrent copies of
        the same envelope each find the cache clear before either writes.

        Bounded by the FRESHNESS WINDOW, not by an entry count. R06: a record must be retained
        through the message's LATEST permissible acceptance time, not merely one window after first
        receipt. Freshness accepts a `ts` up to FRESHNESS_WINDOW_S in the FUTURE, so a message from
        a clock that far ahead stays fresh until ts + FRESHNESS_WINDOW_S -- up to TWO windows after
        it was first seen. Expiring the record at one window let the identical signed envelope be
        accepted again at t = window+epsilon while it was still fresh. Retention is therefore two
        windows. The hard ceiling below is a memory backstop only, and it REFUSES rather than
        evicting: silent eviction under load opens a replay window exactly when one is wanted.
        """
        now = time.monotonic()
        key = (from_node, msg_id)
        with self._replay_lock:
            cutoff = now - 2 * env.FRESHNESS_WINDOW_S
            expired = [k for k, seen_at in self._replay_seen.items() if seen_at <= cutoff]
            for k in expired:
                del self._replay_seen[k]
            if key in self._replay_seen:
                return False
            if len(self._replay_seen) >= _REPLAY_CACHE_MAX:
                return False            # refuse, never evict
            self._replay_seen[key] = now
            return True

    def _dispatch(self, request: dict[str, Any], cred: IpcCredential) -> dict[str, Any]:
        if request["type"] not in _ACCEPTED_INBOUND_TYPES:
            payload = {"ok": False, "error": f"unsupported message type {request['type']!r}"}
        else:
            try:
                payload = self.surface.handle(cred.identity, request["payload"])
            except Exception as exc:  # fail closed: never leak a stack, never drop the reply
                payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return env.make_envelope(
            from_node=SERVICE_NODE_ID,
            to=[cred.identity.node_id],
            msg_type="control_event",
            payload=payload,
            node_credential=SERVICE_NODE_ID,
            scope="service",
            key=cred.key,
            task_id=request.get("task_id"),
        )

    # -- lifecycle -------------------------------------------------------------
    def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        outer = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                outer._serve_conn(self.request)

        class Server(socketserver.ThreadingTCPServer):
            # W-31. `SO_REUSEADDR` does NOT mean the same thing on both platforms, and this class
            # carried the POSIX meaning onto Windows:
            #
            #   POSIX   — a listener may reclaim an address still in TIME_WAIT. Correct, and needed:
            #             without it a gateway restarted inside that window refuses its own port.
            #   Windows — a SECOND LIVE BIND to the same address is permitted.
            #
            # F-2 measured both consequences on this host. Gateway-first, a squatter co-bound the
            # live port (the gateway kept its 20 connections, so that leg is survivable).
            # Squatter-first is the serious one: `start()` SUCCEEDED and reported the port healthy
            # while 20 of 20 connections went to the squatter — a silent failure, with no raise and
            # no log. It compounds with W-40, which prints `IPC_TOKEN=`/`IPC_KEY=` to stdout
            # immediately after that false-healthy bind.
            #
            # NARROWED BY EXECUTION (W-40): credentials are written to child stdout, but that stdout
            # is a private pipe consumed by `resolveGateway`; it is not the stream the logger
            # mirrors. The logging-exposure premise was not reproduced. Origin/Host validation
            # remained a confirmed independent defect and was repaired. The compounding sentence
            # above is therefore narrower than it reads: a squatter serving the PORT does not
            # thereby see the bootstrap credential, which never leaves the parent-child pipe.
            # Left as written and corrected here rather than rewritten.
            #
            # Clearing it is therefore correct on win32 and WRONG on POSIX, so the split is by
            # platform rather than unconditional. `SO_EXCLUSIVEADDRUSE` was considered and not
            # taken: clearing the flag was the change the review MEASURED as sufficient here
            # (Windows refused the second bind), and an explicitly-set socket option is a larger
            # change than this finding's causal chain reaches.
            #
            # The sibling `allow_reuse_address = True` at `mcp_server/server.py:118` is recorded in
            # U447 item 1 as OUTSIDE W-31 as written, and is deliberately left alone.
            allow_reuse_address = sys.platform != "win32"
            daemon_threads = True

        self._server = Server((host, port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="ipc-gateway")
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


def _json_dumps(obj: dict[str, Any]) -> str:
    import json

    return json.dumps(obj)


def _json_loads(text: str) -> Any:
    import json

    return json.loads(text)
