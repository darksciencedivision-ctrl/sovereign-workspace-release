"""Phase 14A / D-IPC-01: the IPC gateway runs as a genuinely separate OS process over a
loopback WebSocket, and this process drives it through the full governance path — handshake,
per-node auth, schema validation, hmac integrity, fail-closed on every violation, and a real
bridge to the existing control plane (the MCP server).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from control_plane.ipc import wsframe
from control_plane.ipc.client import IpcClient, IpcDisconnected

ROOT = Path(__file__).resolve().parents[2]


def _read_prefixed(proc: subprocess.Popen, prefix: str, timeout_s: float = 15.0) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line.startswith(prefix):
            return line.strip().split("=", 1)[1]
        if not line and proc.poll() is not None:
            break
    raise AssertionError(f"process never emitted {prefix}")


def _spawn(args: list[str], env_extra: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", *args], cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, **env_extra},
    )


def _kill(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture()
def echo_gateway():
    env_extra = {"SOVEREIGN_IPC_NODE": "shell-1", "SOVEREIGN_IPC_ROLE": "operator",
                 "SOVEREIGN_IPC_PROJECT": "proj"}
    proc = _spawn(["control_plane.ipc.run_gateway", "0"], env_extra)
    try:
        port = int(_read_prefixed(proc, "IPC_PORT="))
        token = _read_prefixed(proc, "IPC_TOKEN=")
        key = bytes.fromhex(_read_prefixed(proc, "IPC_KEY="))
        yield port, token, key
    finally:
        _kill(proc)


def test_authenticated_control_event_roundtrip(echo_gateway) -> None:
    port, token, key = echo_gateway
    with IpcClient("127.0.0.1", port, "shell-1", token, key) as c:
        resp = c.control_event({"op": "ping", "nonce": "n42"})
    assert resp == {"ok": True, "op": "ping", "result": {"pong": "n42", "node": "shell-1"}}


def test_bad_credential_is_closed_fail_closed(echo_gateway) -> None:
    port, _token, key = echo_gateway
    c = IpcClient("127.0.0.1", port, "shell-1", "not-a-real-token", key)
    c.connect()
    # pin the SPECIFIC fail-closed reason so a different-but-still-closing path can't pass
    with pytest.raises(IpcDisconnected, match="authentication failed"):
        c.control_event({"op": "ping"})


def test_tampered_integrity_is_closed_fail_closed(echo_gateway) -> None:
    port, token, _key = echo_gateway
    # correct token but WRONG shared key -> integrity mismatch at the gateway
    c = IpcClient("127.0.0.1", port, "shell-1", token, b"z" * 32)
    c.connect()
    with pytest.raises(IpcDisconnected, match="integrity check failed"):
        c.control_event({"op": "ping"})


def test_identity_spoof_is_closed_fail_closed(echo_gateway) -> None:
    port, token, key = echo_gateway
    # valid credential, but from_node claims a different node than the credential's owner
    c = IpcClient("127.0.0.1", port, "some-other-node", token, key)
    c.connect()
    with pytest.raises(IpcDisconnected, match="identity mismatch"):
        c.control_event({"op": "ping"})


def test_malformed_envelope_is_closed_fail_closed(echo_gateway) -> None:
    port, _token, _key = echo_gateway
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    conn = wsframe.perform_client_handshake(sock, "127.0.0.1", port)
    conn.send_text('{"not":"an envelope"}')
    with pytest.raises(wsframe.WsClosed, match="envelope failed schema"):
        conn.recv_text()


def test_credential_store_install_persists_a_fixed_credential() -> None:
    """Recovery model (directive §9 track 14A): install() lets a control plane re-issue the
    SAME per-node credential across a restart, so a reconnecting shell re-verifies. It adds no
    authorization — it only binds a (token, key) to an identity, exactly as issue() does."""
    from control_plane.ipc.gateway import IpcCredentialStore

    store = IpcCredentialStore()
    key = bytes.fromhex("ab" * 32)
    store.install("tok-fixed", key, "shell", "shell", "proj")
    cred = store.verify("tok-fixed")
    assert cred is not None
    assert cred.key == key
    assert cred.identity.node_id == "shell" and cred.identity.role == "shell"
    assert store.verify("nope") is None  # still fail-closed on an unknown token


def test_restart_reissues_the_same_fixed_credential(monkeypatch=None) -> None:
    """A gateway restarted with IPC_FIXED_TOKEN/IPC_FIXED_KEY re-issues that exact credential —
    the reconnection path the shell's live recovery test relies on, proven at the process level."""
    fixed_token = "recovery-token-xyz"
    fixed_key = "cd" * 32
    env_extra = {
        "SOVEREIGN_IPC_NODE": "shell-1", "SOVEREIGN_IPC_ROLE": "shell", "SOVEREIGN_IPC_PROJECT": "proj",
        "IPC_ALLOW_FIXED_CRED": "1", "IPC_FIXED_TOKEN": fixed_token, "IPC_FIXED_KEY": fixed_key,
    }
    ports_seen = []
    for _ in range(2):  # start, "restart" — the credential must be identical both times
        proc = _spawn(["control_plane.ipc.run_gateway", "0"], env_extra)
        try:
            port = int(_read_prefixed(proc, "IPC_PORT="))
            token = _read_prefixed(proc, "IPC_TOKEN=")
            key = bytes.fromhex(_read_prefixed(proc, "IPC_KEY="))
            assert token == fixed_token
            assert key == bytes.fromhex(fixed_key)
            with IpcClient("127.0.0.1", port, "shell-1", token, key) as c:
                resp = c.control_event({"op": "health"})
            assert resp["ok"] and resp["op"] == "health"
            ports_seen.append(port)
        finally:
            _kill(proc)
    assert len(ports_seen) == 2  # two independent processes, same credential honored by both


def test_fixed_credential_is_ignored_without_the_explicit_opt_in() -> None:
    """Fail-closed: the recovery-model fixed credential must NEVER activate silently. Without
    IPC_ALLOW_FIXED_CRED=1 the gateway mints a fresh random credential and ignores the fixed one,
    so the shim cannot be turned on by accident in a real deployment."""
    env_extra = {
        "SOVEREIGN_IPC_NODE": "shell-1", "SOVEREIGN_IPC_ROLE": "shell", "SOVEREIGN_IPC_PROJECT": "proj",
        # note: NO IPC_ALLOW_FIXED_CRED
        "IPC_FIXED_TOKEN": "should-be-ignored", "IPC_FIXED_KEY": "ee" * 32,
    }
    proc = _spawn(["control_plane.ipc.run_gateway", "0"], env_extra)
    try:
        _ = int(_read_prefixed(proc, "IPC_PORT="))
        token = _read_prefixed(proc, "IPC_TOKEN=")
        assert token != "should-be-ignored"  # fresh random credential, not the fixed one
    finally:
        _kill(proc)


def test_bridge_to_existing_control_plane_mcp(tmp_path: Path) -> None:
    """shell -> IPC gateway -> MCP server: prove the chain to the real control plane."""
    store_dir = tmp_path / "store"
    mcp = _spawn(
        ["mcp_server.run_server", str(store_dir), "0"],
        {"SOVEREIGN_BOOTSTRAP_ROLE": "operator", "SOVEREIGN_BOOTSTRAP_NODE": "boot",
         "SOVEREIGN_BOOTSTRAP_PROJECT": "proj"},
    )
    gateway = None
    try:
        mcp_port = int(_read_prefixed(mcp, "MCP_PORT="))
        mcp_token = _read_prefixed(mcp, "BOOTSTRAP_TOKEN=")
        gateway = _spawn(
            ["control_plane.ipc.run_gateway", "0", "--mcp-host", "127.0.0.1",
             "--mcp-port", str(mcp_port), "--mcp-token", mcp_token],
            {"SOVEREIGN_IPC_NODE": "shell-1", "SOVEREIGN_IPC_ROLE": "operator",
             "SOVEREIGN_IPC_PROJECT": "proj"},
        )
        port = int(_read_prefixed(gateway, "IPC_PORT="))
        token = _read_prefixed(gateway, "IPC_TOKEN=")
        key = bytes.fromhex(_read_prefixed(gateway, "IPC_KEY="))
        with IpcClient("127.0.0.1", port, "shell-1", token, key) as c:
            resp = c.control_event({"op": "health"})
        assert resp["ok"] and resp["op"] == "health"
        assert resp["result"]["ok"] is True  # MCP server's own health verdict, via the gateway
    finally:
        if gateway is not None:
            _kill(gateway)
        _kill(mcp)
