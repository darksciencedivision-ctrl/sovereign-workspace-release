"""Minimal RFC 6455 WebSocket framing on the Python stdlib (no pip, prohibition 2.7).

Scope is deliberately the subset the shell <-> control-plane channel needs: a single
loopback connection, text messages carrying one JSON envelope each, plus the mandatory
control frames (close/ping/pong). It is NOT a general-purpose WebSocket stack — no
extensions, no permessage-deflate, no streaming fragment API beyond reassembly.

Correctness points that matter for the trust boundary:
  - a server MUST reject an unmasked client frame and a client MUST reject a masked server
    frame (RFC 6455 section 5.1); we fail closed on both;
  - payload length is bounded (MAX_MESSAGE) so a peer cannot force unbounded buffering
    before the envelope is even parsed (mirrors the MCP pre-auth bound, spec-audit F6);
  - reads that hit EOF raise WsClosed so callers fail closed rather than spin.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import socket
import struct

# RFC 6455 opcodes
OPCODE_CONT = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC 6455 section 1.3
MAX_MESSAGE = 8 * 1024 * 1024  # bound buffering before parse (F6)

# Close codes we use (RFC 6455 section 7.4.1)
CLOSE_NORMAL = 1000
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_POLICY_VIOLATION = 1008
CLOSE_MESSAGE_TOO_BIG = 1009


class WsError(Exception):
    """Protocol violation by the peer — the caller should close the connection."""


class WsClosed(Exception):
    """Peer closed the connection (clean or abrupt) — fail closed, do not assume state."""

    def __init__(self, code: int | None = None, reason: str = "") -> None:
        super().__init__(reason or (f"closed ({code})" if code else "connection closed"))
        self.code = code
        self.reason = reason


def accept_key(sec_websocket_key: str) -> str:
    """The Sec-WebSocket-Accept value for a client's Sec-WebSocket-Key (RFC 6455 4.2.2)."""
    digest = hashlib.sha1((sec_websocket_key + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def apply_mask(data: bytes, mask: bytes) -> bytes:
    return bytes(b ^ mask[i & 3] for i, b in enumerate(data))


def build_frame(payload: bytes, opcode: int = OPCODE_TEXT, *, fin: bool = True, mask: bool = False) -> bytes:
    """Serialize one frame. Clients set mask=True (RFC 6455 5.3); servers leave it False."""
    b0 = (0x80 if fin else 0x00) | (opcode & 0x0F)
    length = len(payload)
    header = bytearray([b0])
    mask_bit = 0x80 if mask else 0x00
    if length < 126:
        header.append(mask_bit | length)
    elif length < 65536:
        header.append(mask_bit | 126)
        header += struct.pack("!H", length)
    else:
        header.append(mask_bit | 127)
        header += struct.pack("!Q", length)
    if mask:
        mask_key = secrets.token_bytes(4)
        return bytes(header) + mask_key + apply_mask(payload, mask_key)
    return bytes(header) + payload


class FrameConn:
    """Frame-level view of one WebSocket connection over a blocking socket.

    ``is_server`` fixes the two asymmetric rules: a server unmasks (and requires) masked
    inbound frames and sends unmasked; a client does the reverse.
    """

    def __init__(self, sock: socket.socket, *, is_server: bool, initial: bytes = b"") -> None:
        self._sock = sock
        self._is_server = is_server
        self._buf = bytearray(initial)
        self._closed = False

    # -- low-level socket reads ------------------------------------------------
    def _read_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            try:
                chunk = self._sock.recv(65536)
            except OSError as exc:
                raise WsClosed(reason=str(exc)) from exc
            if not chunk:
                raise WsClosed(reason="peer closed the socket")
            self._buf += chunk
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def _read_frame(self) -> tuple[bool, int, bytes]:
        b0, b1 = self._read_exact(2)
        fin = bool(b0 & 0x80)
        if b0 & 0x70:
            raise WsError("reserved bits set (no negotiated extension)")
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", self._read_exact(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", self._read_exact(8))
        if length > MAX_MESSAGE:
            raise WsError(f"frame length {length} exceeds MAX_MESSAGE")
        # Masking is asymmetric and mandatory in one direction (RFC 6455 5.1).
        if self._is_server and not masked:
            raise WsError("client frame is not masked")
        if not self._is_server and masked:
            raise WsError("server frame is masked")
        mask_key = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = apply_mask(payload, mask_key)
        return fin, opcode, payload

    # -- message-level API -----------------------------------------------------
    def recv_message(self) -> tuple[int, bytes]:
        """Return (opcode, data) for the next TEXT/BINARY message.

        Control frames are handled inline: PING -> auto PONG, PONG ignored, CLOSE -> echo
        close then raise WsClosed. Fragmented data messages are reassembled.
        """
        data = bytearray()
        msg_opcode: int | None = None
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode in (OPCODE_CLOSE, OPCODE_PING, OPCODE_PONG):
                if opcode == OPCODE_CLOSE:
                    code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else None
                    self._send_control(OPCODE_CLOSE, payload[:2] if len(payload) >= 2 else b"")
                    self._closed = True
                    raise WsClosed(code=code, reason=payload[2:].decode("utf-8", "replace"))
                if opcode == OPCODE_PING:
                    self._send_control(OPCODE_PONG, payload)
                continue  # pong: nothing to do
            if opcode == OPCODE_CONT:
                if msg_opcode is None:
                    raise WsError("continuation frame with no message started")
            else:
                if msg_opcode is not None:
                    raise WsError("new data frame while a message was unfinished")
                msg_opcode = opcode
            data += payload
            if len(data) > MAX_MESSAGE:
                raise WsError("reassembled message exceeds MAX_MESSAGE")
            if fin:
                return msg_opcode, bytes(data)

    def recv_text(self) -> str:
        opcode, data = self.recv_message()
        if opcode != OPCODE_TEXT:
            raise WsError(f"expected text message, got opcode {opcode:#x}")
        return data.decode("utf-8")

    # -- writes ----------------------------------------------------------------
    def _send_raw(self, frame: bytes) -> None:
        try:
            self._sock.sendall(frame)
        except OSError as exc:
            raise WsClosed(reason=str(exc)) from exc

    def _send_control(self, opcode: int, payload: bytes) -> None:
        self._send_raw(build_frame(payload, opcode, mask=not self._is_server))

    def send_text(self, text: str) -> None:
        self._send_raw(build_frame(text.encode("utf-8"), OPCODE_TEXT, mask=not self._is_server))

    def close(self, code: int = CLOSE_NORMAL, reason: str = "") -> None:
        if not self._closed:
            self._closed = True
            try:
                self._send_control(OPCODE_CLOSE, struct.pack("!H", code) + reason.encode("utf-8"))
            except WsClosed:
                pass
        try:
            self._sock.close()
        except OSError:
            pass


# -- HTTP upgrade handshake ----------------------------------------------------
def _read_http_headers(sock: socket.socket, max_bytes: int = 16 * 1024) -> tuple[dict[str, str], bytes]:
    """Read the request/response head up to CRLFCRLF; return (headers, leftover bytes)."""
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise WsClosed(reason="peer closed during handshake")
        buf += chunk
        if len(buf) > max_bytes:
            raise WsError("handshake headers too large")
    head, _, rest = bytes(buf).partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers: dict[str, str] = {"": lines[0]}  # request/status line under empty key
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers, rest


def perform_server_handshake(sock: socket.socket) -> FrameConn:
    """Complete the server side of the upgrade; return a ready FrameConn (is_server=True)."""
    headers, leftover = _read_http_headers(sock)
    if "websocket" not in headers.get("upgrade", "").lower():
        _reject(sock, "426 Upgrade Required", "expected Upgrade: websocket")
        raise WsError("not a websocket upgrade request")
    key = headers.get("sec-websocket-key")
    if not key:
        _reject(sock, "400 Bad Request", "missing Sec-WebSocket-Key")
        raise WsError("missing Sec-WebSocket-Key")
    resp = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(key)}\r\n\r\n"
    )
    sock.sendall(resp.encode("ascii"))
    return FrameConn(sock, is_server=True, initial=leftover)


def _reject(sock: socket.socket, status: str, body: str) -> None:
    try:
        sock.sendall(f"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n{body}".encode("ascii"))
    except OSError:
        pass


def perform_client_handshake(sock: socket.socket, host: str, port: int, path: str = "/") -> FrameConn:
    """Complete the client side of the upgrade; verify Sec-WebSocket-Accept."""
    nonce = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {nonce}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(req.encode("ascii"))
    headers, leftover = _read_http_headers(sock)
    status = headers.get("", "")
    if "101" not in status:
        raise WsError(f"handshake rejected: {status}")
    if headers.get("sec-websocket-accept") != accept_key(nonce):
        raise WsError("bad Sec-WebSocket-Accept (server did not complete the handshake)")
    return FrameConn(sock, is_server=False, initial=leftover)
