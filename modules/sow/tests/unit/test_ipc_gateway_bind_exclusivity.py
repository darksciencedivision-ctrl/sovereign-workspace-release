"""W-31 — the control gateway's loopback port must not be co-bindable by another local process.

F-2 measured this on the target host, in BOTH directions, and the second direction is the serious
one:

  leg a  gateway first  -> a second bind SUCCEEDS, but the gateway keeps all 20 connections.
  leg b  squatter first -> the gateway's ``start()`` SUCCEEDS and reports its port as healthy while
                           **20 of 20 connections go to the squatter**.

Leg b is why this is HIGH rather than a hardening nicety: the failure is silent. The gateway does
not raise, does not log, and reports a healthy port it does not own. It compounds with W-40, which
prints ``IPC_TOKEN=``/``IPC_KEY=`` to stdout immediately after that false-healthy bind -- so the
bearer credential is emitted to a channel a squatter is already serving.

NARROWED BY EXECUTION (W-40): credentials are written to child stdout, but that stdout is a private
pipe consumed by ``resolveGateway``; it is not the stream the logger mirrors. The logging-exposure
premise was not reproduced, and a squatter holding the PORT does not thereby see the bootstrap
credential -- it never leaves the parent-child pipe. Origin/Host validation remained a confirmed
independent defect and was repaired in the same unit. The paragraph above is left as written and
corrected here rather than rewritten.

WHY ``SO_REUSEADDR`` IS THE CAUSE. ``socketserver`` sets it from ``allow_reuse_address``. On POSIX
it only lets a listener reclaim a socket in TIME_WAIT, which is why it is the correct default there
and why this class carried it. On Windows it means something else entirely: it permits a SECOND LIVE
BIND to the same address. The review measured the A/B directly -- with the flag set a second
``SO_REUSEADDR`` socket bound the live port; with it clear, Windows refused.

SCOPE, stated so a reader does not think it was missed. A second
``allow_reuse_address = True`` exists at ``mcp_server/server.py:118``. Register row U447 item 1
records it as OUTSIDE W-31 as written, and it is deliberately NOT changed here.

THREAT BOUNDARY, not overstated. The boundary is "same Windows user", which is the boundary
``docs/THREAT_MODEL.md`` itself scopes to. A squatter cannot forge envelopes -- the per-node HMAC key
is not derivable from the socket -- so this is availability and credential exposure, not authority.
"""
from __future__ import annotations

import socket
import sys

import pytest

from control_plane.ipc.gateway import EchoControlSurface, IpcCredentialStore, IpcGateway


def _gateway() -> IpcGateway:
    return IpcGateway(IpcCredentialStore(), EchoControlSurface())


@pytest.mark.skipif(sys.platform != "win32",
                    reason="SO_REUSEADDR permits a second LIVE bind only on Windows; on POSIX it "
                           "reclaims TIME_WAIT and clearing it would break restart-in-place")
def test_a_second_process_cannot_co_bind_the_live_gateway_port() -> None:
    """NEGATIVE (F-2 leg a): the squatter's bind must be REFUSED, not merely out-raced."""
    gw = _gateway()
    port = gw.start()
    try:
        squatter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            with pytest.raises(OSError) as excinfo:
                squatter.bind(("127.0.0.1", port))
            # Windows refuses with WSAEACCES (10013) when the holder did not share the address.
            assert excinfo.value.errno in (socket.errno.EACCES, socket.errno.EADDRINUSE) or \
                getattr(excinfo.value, "winerror", None) in (10013, 10048), \
                f"unexpected refusal: {excinfo.value!r}"
        finally:
            squatter.close()
    finally:
        gw.stop()


@pytest.mark.skipif(sys.platform != "win32",
                    reason="see above; the squatter-first leg is a Windows SO_REUSEADDR property")
def test_the_gateway_refuses_to_start_on_a_port_someone_else_already_holds() -> None:
    """NEGATIVE (F-2 leg b, the serious one): starting behind a squatter must RAISE.

    Pre-repair this returned a port number and reported healthy while every connection went to the
    squatter. A gateway that cannot tell it does not own its port cannot fail closed, and the
    credential print in W-40 lands on the squatter's channel.
    """
    squatter = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    squatter.bind(("127.0.0.1", 0))
    squatter.listen(5)
    held_port = squatter.getsockname()[1]
    gw = _gateway()
    try:
        with pytest.raises(OSError):
            gw.start(port=held_port)
    finally:
        gw.stop()
        squatter.close()


def test_the_gateway_still_starts_and_reports_its_own_port() -> None:
    """POSITIVE: refusing to share must not stop it binding a free port normally.

    Runs on every platform: a repair that makes the gateway unstartable would be caught here rather
    than by the whole suite going dark.
    """
    gw = _gateway()
    try:
        port = gw.start()
        assert isinstance(port, int) and port > 0
        assert gw.port == port
        probe = socket.create_connection(("127.0.0.1", port), timeout=5)
        probe.close()
    finally:
        gw.stop()


def test_reuse_is_disabled_on_windows_and_preserved_on_posix() -> None:
    """The platform split is the decision, so it is asserted directly rather than inferred.

    Clearing the flag unconditionally would be a POSIX regression: there SO_REUSEADDR only reclaims
    TIME_WAIT, so a gateway restarted within the TIME_WAIT window would refuse to bind its own port.
    """
    from control_plane.ipc import gateway as gw_mod

    source = (gw_mod.__file__ or "")
    assert source, "gateway module has no file"
    gw = _gateway()
    try:
        gw.start()
        server = gw._server
        assert server is not None
        expected = sys.platform != "win32"
        assert server.allow_reuse_address is expected, (
            "on win32 SO_REUSEADDR permits a second live bind and must be OFF; on POSIX it only "
            "reclaims TIME_WAIT and must stay ON"
        )
    finally:
        gw.stop()
