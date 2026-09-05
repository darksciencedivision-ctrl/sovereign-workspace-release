"""
H-2b. A rejected state-changing request must not leave its body on the socket.

`_validate_state_changing_request` answers BEFORE the body is read - that ordering is
correct, a 403 should not require reading an attacker's payload. But the handler sets
`protocol_version = "HTTP/1.1"`, so without an explicit close the connection is reused
and those undrained body bytes are parsed as the NEXT request line. The smuggled request
is then parsed fresh, with a Host, Origin and CSRF nonce the caller chose - which is a
complete bypass of the Host/Origin control the first request just failed.

A browser can reach this: fetch() sends an arbitrary body cross-origin, and the 403 on
the outer request is exactly the condition that leaves the inner one queued.

These tests speak raw HTTP on a socket because urllib will not emit a pipelined body,
and they run the real ShellAPIHandler for the same reason test_hardening.py does.
"""
import shutil
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from shell.src.logring import LogRing
from shell.src.server import ShellAPIHandler
from shell.src.states import ModuleRunner
from shell.src.supervisor import JobSupervisor
from shell.tests._harness import free_port
from shell.tests.test_states import make_adapter


class TestRejectedRequestCannotSmuggle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h2b-")
        self.sup = JobSupervisor()
        self.port = free_port()
        adapter = make_adapter(self.tmp, free_port(), extra_args=("--unready",), timeout_s=5)
        ShellAPIHandler.supervisor = self.sup
        ShellAPIHandler.adapters = {"fix": adapter}
        ShellAPIHandler.states = {"fix": ModuleRunner("fix", adapter, self.sup, LogRing())}
        ShellAPIHandler.log_rings = {"fix": LogRing()}
        ShellAPIHandler.selftest = False
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), ShellAPIHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        try:
            self.sup.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _speak(self, payload: bytes) -> bytes:
        s = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5)
        try:
            s.sendall(payload)
            s.settimeout(3)
            buf = b""
            while True:
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
            return buf
        finally:
            s.close()

    def test_undrained_body_of_a_rejected_post_is_not_parsed_as_a_request(self):
        port = self.server.server_port
        smuggled = (
            "POST /api/start HTTP/1.1\r\n"
            "Host: 127.0.0.1:{p}\r\n"
            "Origin: http://127.0.0.1:{p}\r\n"
            "Content-Type: application/json\r\n"
            "X-CSRF-Nonce: {n}\r\n"
            "Content-Length: 0\r\n\r\n"
        ).format(p=port, n=ShellAPIHandler.csrf.nonce).encode()

        outer = (
            "POST /api/stop HTTP/1.1\r\n"
            "Host: 127.0.0.1:{p}\r\n"
            "Origin: https://evil.example\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: {n}\r\n\r\n"
        ).format(p=port, n=len(smuggled)).encode() + smuggled

        raw = self._speak(outer)
        self.assertIn(b"403", raw[:32], "cross-origin POST must be rejected")
        self.assertEqual(
            raw.count(b"HTTP/1.1 "), 1,
            "exactly one response: a second means the undrained body was parsed as a "
            "request, bypassing Host/Origin validation. Got:\n" + repr(raw[:400]))

    def test_rejected_request_closes_the_connection(self):
        port = self.server.server_port
        req = (
            "POST /api/stop HTTP/1.1\r\n"
            "Host: 127.0.0.1:{p}\r\n"
            "Origin: https://evil.example\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 0\r\n\r\n"
        ).format(p=port).encode()
        raw = self._speak(req)
        self.assertIn(b"Connection: close", raw, "an error response must close the connection")


class TestContentLengthIsStrict(unittest.TestCase):
    """int() accepts " 10 ", "+10", "1_0" and Unicode digits; http.server rejects none of
    them, so a permissive parse can disagree with the bytes actually framed on the wire."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sws-h2c-")
        self.sup = JobSupervisor()
        adapter = make_adapter(self.tmp, free_port(), extra_args=("--unready",), timeout_s=5)
        ShellAPIHandler.supervisor = self.sup
        ShellAPIHandler.adapters = {"fix": adapter}
        ShellAPIHandler.states = {"fix": ModuleRunner("fix", adapter, self.sup, LogRing())}
        ShellAPIHandler.log_rings = {"fix": LogRing()}
        ShellAPIHandler.selftest = False
        self.server = ThreadingHTTPServer(("127.0.0.1", free_port()), ShellAPIHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        try:
            self.sup.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _post_with_length(self, raw_len: str) -> bytes:
        port = self.server.server_port
        req = (
            "POST /api/stop HTTP/1.1\r\n"
            "Host: 127.0.0.1:{p}\r\n"
            "Origin: http://127.0.0.1:{p}\r\n"
            "Content-Type: application/json\r\n"
            "X-CSRF-Nonce: {n}\r\n"
            "Content-Length: {L}\r\n\r\n"
        ).format(p=port, n=ShellAPIHandler.csrf.nonce, L=raw_len).encode("utf-8")
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            s.sendall(req + b"{}")
            s.settimeout(3)
            try:
                return s.recv(65536)
            except socket.timeout:
                return b""
        finally:
            s.close()

    def test_non_ascii_digit_spellings_are_refused(self):
        for spelling in (" 2 ", "+2", "2_0", "٢", "0x2", "2.0", ""):
            with self.subTest(spelling=spelling):
                raw = self._post_with_length(spelling)
                self.assertIn(b"400", raw[:32],
                              "Content-Length {!r} must be refused".format(spelling))

    def test_duplicate_content_length_is_refused(self):
        port = self.server.server_port
        req = (
            "POST /api/stop HTTP/1.1\r\n"
            "Host: 127.0.0.1:{p}\r\n"
            "Origin: http://127.0.0.1:{p}\r\n"
            "Content-Type: application/json\r\n"
            "X-CSRF-Nonce: {n}\r\n"
            "Content-Length: 2\r\n"
            "Content-Length: 40\r\n\r\n"
        ).format(p=port, n=ShellAPIHandler.csrf.nonce).encode()
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            s.sendall(req + b"{}")
            s.settimeout(3)
            try:
                raw = s.recv(65536)
            except socket.timeout:
                raw = b""
        finally:
            s.close()
        self.assertIn(b"400", raw[:32], "two Content-Length headers is a framing ambiguity")


if __name__ == "__main__":
    unittest.main()
