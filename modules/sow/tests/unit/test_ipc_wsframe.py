"""Phase 14A / D-IPC-01: RFC 6455 framing correctness for the loopback WebSocket channel.

Uses a real socketpair so masking, length encodings, and control frames are exercised over
an actual kernel socket, not a mock.
"""
from __future__ import annotations

import socket
import struct
import threading

import pytest

from control_plane.ipc import wsframe


def test_accept_key_rfc6455_vector() -> None:
    # RFC 6455 section 1.3 worked example.
    assert wsframe.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_apply_mask_is_involutive() -> None:
    key = b"\x01\x02\x03\x04"
    data = b"sovereign-orchestration"
    assert wsframe.apply_mask(wsframe.apply_mask(data, key), key) == data


def _pair() -> tuple[wsframe.FrameConn, wsframe.FrameConn]:
    a, b = socket.socketpair()
    return wsframe.FrameConn(a, is_server=False), wsframe.FrameConn(b, is_server=True)


def _recv_in_thread(conn: wsframe.FrameConn) -> list:
    box: list = []
    t = threading.Thread(target=lambda: box.append(conn.recv_text()))
    t.start()
    return [t, box]


@pytest.mark.parametrize("size", [0, 5, 125, 126, 200, 65535, 65536, 70000])
def test_text_roundtrip_client_to_server(size: int) -> None:
    client, server = _pair()
    msg = "x" * size
    t, box = _recv_in_thread(server)
    client.send_text(msg)
    t.join(timeout=5)
    assert box == [msg]


def test_text_roundtrip_server_to_client() -> None:
    client, server = _pair()
    t, box = _recv_in_thread(client)
    server.send_text("hello shell")
    t.join(timeout=5)
    assert box == ["hello shell"]


def test_server_rejects_unmasked_client_frame() -> None:
    a, b = socket.socketpair()
    server = wsframe.FrameConn(b, is_server=True)
    # a raw client that (wrongly) sends an UNMASKED text frame
    a.sendall(wsframe.build_frame(b"hi", wsframe.OPCODE_TEXT, mask=False))
    with pytest.raises(wsframe.WsError, match="not masked"):
        server.recv_text()


def test_client_rejects_masked_server_frame() -> None:
    a, b = socket.socketpair()
    client = wsframe.FrameConn(a, is_server=False)
    b.sendall(wsframe.build_frame(b"hi", wsframe.OPCODE_TEXT, mask=True))
    with pytest.raises(wsframe.WsError, match="is masked"):
        client.recv_text()


def test_ping_is_auto_ponged_and_message_still_delivered() -> None:
    client, server = _pair()
    t, box = _recv_in_thread(server)
    # client sends a ping, then the real text; server must pong and return the text
    client._send_control(wsframe.OPCODE_PING, b"probe")  # noqa: SLF001 (intentional low-level)
    client.send_text("after-ping")
    t.join(timeout=5)
    assert box == ["after-ping"]
    # and a pong came back to the client
    opcode, payload = client._read_frame()[1:]  # noqa: SLF001
    assert opcode == wsframe.OPCODE_PONG and payload == b"probe"


def test_close_frame_raises_wsclosed() -> None:
    client, server = _pair()
    client.close(wsframe.CLOSE_NORMAL, "bye")
    with pytest.raises(wsframe.WsClosed):
        server.recv_text()


def test_reserved_bits_rejected() -> None:
    a, b = socket.socketpair()
    server = wsframe.FrameConn(b, is_server=True)
    a.sendall(bytes([0x81 | 0x40, 0x80, 0, 0, 0, 0]))  # RSV1 set, masked, len 0
    with pytest.raises(wsframe.WsError, match="reserved bits"):
        server.recv_text()


def test_oversized_length_rejected_before_buffering() -> None:
    a, b = socket.socketpair()
    server = wsframe.FrameConn(b, is_server=True)
    # masked text frame claiming a huge 64-bit length; no payload actually sent
    a.sendall(bytes([0x81, 0x80 | 127]) + struct.pack("!Q", wsframe.MAX_MESSAGE + 1))
    with pytest.raises(wsframe.WsError, match="MAX_MESSAGE"):
        server.recv_text()


def test_eof_during_read_raises_wsclosed() -> None:
    a, b = socket.socketpair()
    server = wsframe.FrameConn(b, is_server=True)
    a.close()
    with pytest.raises(wsframe.WsClosed):
        server.recv_text()
