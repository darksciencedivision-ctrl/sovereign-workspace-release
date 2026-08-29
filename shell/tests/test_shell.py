"""
SWS Test Suite — automated verification (SWS-UI-001 v1.2 §9).
"""
import json
import os
import sys
import tempfile
import unittest
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shell.src.adapter import load_all_adapters, compile_adapter, AdapterError
from shell.src.redact import redact
from shell.src.logring import LogRing
from shell.src.csrf import CsrfManager
from shell.src.distillery import get_distillery_status
from shell.tests._harness import request, start_shell, stop_shell
import urllib.error
import urllib.request


class TestAdapterSchema(unittest.TestCase):
    """Adapter schema validation and compilation tests."""

    def setUp(self):
        self.adapters = load_all_adapters()

    def test_all_adapters_load(self):
        """All 4 adapters load without error."""
        self.assertIn("sovereign", self.adapters)
        self.assertIn("debate", self.adapters)
        self.assertIn("sow", self.adapters)
        self.assertIn("distillery", self.adapters)
        for mid, adapter in self.adapters.items():
            self.assertNotIn("error", adapter, f"Adapter {mid} has error: {adapter.get('reason', '')}")

    def test_adapter_ids_match_pattern(self):
        """All adapter IDs match ^[a-z][a-z0-9_-]{0,31}$."""
        import re
        pattern = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
        for mid, adapter in self.adapters.items():
            if "error" in adapter:
                continue
            self.assertTrue(pattern.match(adapter.get("id", "")), f"Invalid id: {adapter.get('id')}")

    def test_runnable_have_launch(self):
        """All runnable adapters have launch, readiness, identity, open, stop."""
        for mid, adapter in self.adapters.items():
            if adapter.get("state_class") == "runnable":
                self.assertIn("launch", adapter, f"{mid} missing launch")
                self.assertIn("readiness", adapter, f"{mid} missing readiness")
                self.assertIn("identity", adapter, f"{mid} missing identity")
                self.assertIn("open", adapter, f"{mid} missing open")
                self.assertIn("stop", adapter, f"{mid} missing stop")

    def test_argv0_is_exe(self):
        """All compiled adapters have argv[0] ending in .exe."""
        for mid, adapter in self.adapters.items():
            if adapter.get("state_class") == "runnable":
                argv0 = adapter.get("launch", {}).get("argv", [""])[0]
                self.assertTrue(argv0.lower().endswith(".exe"), f"{mid} argv[0] not .exe: {argv0}")

    def test_no_forbidden_launchers(self):
        """No .cmd, .bat, .ps1, cmd.exe, or powershell.exe in argv[0]."""
        forbidden = [".cmd", ".bat", ".ps1", "cmd.exe", "powershell.exe"]
        for mid, adapter in self.adapters.items():
            if adapter.get("state_class") == "runnable":
                argv0 = adapter.get("launch", {}).get("argv", [""])[0].lower()
                for f in forbidden:
                    self.assertNotIn(f, argv0, f"{mid} argv[0] contains forbidden: {f}")

    def test_no_placeholder_literals(self):
        """No <PHASE-1-VERIFIED> literal remains in any adapter."""
        import re
        pattern = re.compile(r"<PHASE-1-VERIFIED>")
        for mid, adapter in self.adapters.items():
            if "error" in adapter:
                continue
            raw = json.dumps(adapter)
            self.assertFalse(pattern.search(raw), f"{mid} contains <PHASE-1-VERIFIED>")

    def test_sow_quota_guard(self):
        """SOW adapter has SOW_CONDUCTOR_AUTOLAUNCH=0."""
        sow = self.adapters.get("sow", {})
        if "error" in sow:
            self.skipTest("SOW adapter has error")
        env_set = sow.get("launch", {}).get("env_set", {})
        self.assertEqual(env_set.get("SOW_CONDUCTOR_AUTOLAUNCH"), "0", "SOW must set SOW_CONDUCTOR_AUTOLAUNCH=0")

    def test_timeout_bounds(self):
        """Readiness timeout_s and poll_ms within bounds."""
        for mid, adapter in self.adapters.items():
            if adapter.get("state_class") == "runnable":
                r = adapter.get("readiness", {})
                self.assertTrue(5 <= r.get("timeout_s", 0) <= 120, f"{mid} timeout_s out of bounds")
                self.assertTrue(250 <= r.get("poll_ms", 0) <= 5000, f"{mid} poll_ms out of bounds")

    def test_grace_bounds(self):
        """Stop grace_s within bounds."""
        for mid, adapter in self.adapters.items():
            if adapter.get("state_class") == "runnable":
                s = adapter.get("stop", {})
                self.assertTrue(1 <= s.get("grace_s", 0) <= 30, f"{mid} grace_s out of bounds")

    def test_invalid_adapter_id(self):
        """Invalid adapter id raises error."""
        with self.assertRaises(AdapterError):
            compile_adapter({"id": "INVALID!", "state_class": "not_started", "root": "C:/test",
                             "display_name": "X", "description": "X"})

    def test_unknown_variable_raises(self):
        """Unknown ${...} variable raises error."""
        with self.assertRaises(AdapterError):
            compile_adapter({"id": "test", "state_class": "not_started", "root": "C:/test",
                             "display_name": "X", "description": "X",
                             "runtime_writes": ["${unknown}/path"]})


class TestRedaction(unittest.TestCase):
    """H-8 secret redaction tests."""

    def test_api_key_assignment(self):
        self.assertNotIn("my-secret-key", redact("api_key=my-secret-key"))
        self.assertIn("[REDACTED]", redact("api_key=my-secret-key"))

    def test_api_key_hyphen(self):
        self.assertNotIn("abc123", redact("api-key: abc123"))
        self.assertIn("[REDACTED]", redact("api-key: abc123"))

    def test_token_assignment(self):
        self.assertNotIn("tk123", redact("token=tk123"))

    def test_secret_assignment(self):
        self.assertNotIn("s3cr3t", redact("secret:s3cr3t"))

    def test_password_assignment(self):
        self.assertNotIn("p4ss", redact("password=p4ss"))

    def test_bearer_token(self):
        result = redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("eyJhbGci", result)

    def test_url_query_param(self):
        result = redact("https://api.example.com?api_key=abc123&other=val")
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("abc123", result)

    def test_case_insensitive(self):
        self.assertNotIn("KEY123", redact("API_KEY=KEY123"))

    def test_sentinel_absent(self):
        """A unique sentinel secret is absent from redacted output."""
        sentinel = "SENTINEL-X7K9M2P4"
        for form in [
            f"api_key={sentinel}",
            f"token: {sentinel}",
            f"Authorization: Bearer {sentinel}",
            f"?api_key={sentinel}",
            f"secret={sentinel}",
        ]:
            result = redact(form)
            self.assertNotIn(sentinel, result, f"Sentinel leaked in form: {form}")


class TestLogRing(unittest.TestCase):
    """Log ring buffer tests."""

    def test_write_and_read(self):
        lr = LogRing(max_lines=100)
        lr.write(b"hello\nworld\n")
        self.assertIn("hello", lr.read())
        self.assertIn("world", lr.read())

    def test_ansi_stripped(self):
        lr = LogRing()
        lr.write(b"\x1b[32mgreen\x1b[0m text\n")
        result = lr.read()
        self.assertNotIn("\x1b", result)
        self.assertIn("green text", result)

    def test_nul_stripped(self):
        lr = LogRing()
        lr.write(b"hello\x00world\n")
        result = lr.read()
        self.assertNotIn("\x00", result)

    def test_bounded_lines(self):
        lr = LogRing(max_lines=5)
        for i in range(10):
            lr.write(f"line{i}\n".encode())
        lines = lr.read_lines()
        self.assertLessEqual(len(lines), 5)

    def test_clear(self):
        lr = LogRing()
        lr.write(b"data\n")
        lr.clear()
        self.assertEqual(lr.read(), "")


class TestCsrf(unittest.TestCase):
    """CSRF nonce tests."""

    def test_generate_and_validate(self):
        csrf = CsrfManager()
        self.assertTrue(csrf.validate(csrf.nonce))
        self.assertFalse(csrf.validate("wrong"))
        self.assertEqual(len(csrf.nonce), 64)  # 32 bytes hex = 64 chars

    def test_regenerate(self):
        csrf = CsrfManager()
        old = csrf.nonce
        csrf.regenerate()
        self.assertNotEqual(old, csrf.nonce)


class TestDistilleryParser(unittest.TestCase):
    """Distillery file parser tests."""

    def test_returns_not_started(self):
        status = get_distillery_status()
        self.assertEqual(status["state"], "NOT_STARTED")

    def test_has_handoff(self):
        status = get_distillery_status()
        self.assertIn("handoff", status)
        self.assertEqual(status["handoff"]["status"], "not started")

    def test_has_questions(self):
        status = get_distillery_status()
        self.assertIn("questions", status)
        self.assertIn("open_count", status["questions"])

    def test_has_snapshot(self):
        status = get_distillery_status()
        self.assertIn("snapshot", status)

    def test_verbatim_line(self):
        status = get_distillery_status()
        self.assertIn("No runtime", status["verbatim"])


class TestServerEndpoints(unittest.TestCase):
    """Integration tests against a shell instance this class starts and stops itself (R3-1).

    setUpClass launches `py -3.12 -m shell.src --port <ephemeral>` and waits for readiness;
    tearDownClass terminates it. No test assumes port 5180 and none requires a server that
    someone started by hand.
    """

    proc = None
    port = None
    nonce = ""

    @classmethod
    def setUpClass(cls):
        cls.proc, cls.port, cls.nonce = start_shell()

    @classmethod
    def tearDownClass(cls):
        stop_shell(cls.proc)

    # -- happy paths --------------------------------------------------------
    def test_shell_started_on_ephemeral_port(self):
        self.assertIsNotNone(self.port)
        self.assertNotEqual(self.port, 5180,
                            "the suite must not depend on the default port")

    def test_csrf_nonce_served_in_html(self):
        self.assertTrue(self.nonce, "the shell's own HTML must carry the CSRF nonce")
        self.assertGreaterEqual(len(self.nonce), 32)

    def test_get_state(self):
        status, _h, data = request(self.port, "/api/state")
        self.assertEqual(status, 200)
        self.assertIn("modules", json.loads(data))

    def test_get_shell_info(self):
        status, _h, data = request(self.port, "/api/shell-info")
        self.assertEqual(status, 200)
        self.assertIn("version", json.loads(data))

    def test_get_preflight(self):
        status, _h, data = request(self.port, "/api/preflight")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertIsInstance(payload.get("checks"), list)
        self.assertTrue(payload["checks"], "preflight payload must carry resolved checks")

    def test_preflight_panel_ids_resolved(self):
        """THEME-01 G7 (D4): every panel id resolves end-to-end through /api/preflight.

        Directive section 4.1 semantics: each of ollama/py312/node/npm/port_5175/
        port_8700/port_5180 must yield a definite (ok|bad) status - never unknown -
        and a non-empty detail, computed by the server from live probes.
        """
        status, _h, data = request(self.port, "/api/preflight")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        checks = {c.get("id"): c for c in payload.get("checks", [])}
        expected = ["ollama", "py312", "node", "npm",
                    "port_5175", "port_8700", "port_5180"]
        unresolved = []
        for cid in expected:
            entry = checks.get(cid)
            if not isinstance(entry, dict):
                unresolved.append((cid, "missing from payload.checks"))
                continue
            st = entry.get("status")
            detail = str(entry.get("detail", "")).strip()
            if st not in ("ok", "bad"):
                unresolved.append((cid, "status={!r}".format(st)))
            elif not detail:
                unresolved.append((cid, "empty detail"))
        self.assertEqual(
            unresolved, [],
            "pre-flight ids without a definite status/detail: {}".format(unresolved))

    def test_get_distillery(self):
        status, _h, data = request(self.port, "/api/distillery")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["state"], "NOT_STARTED")

    def test_unknown_path_404(self):
        status, _h, _d = request(self.port, "/api/nope")
        self.assertEqual(status, 404)

    # -- H-3 headers --------------------------------------------------------
    def test_security_headers_on_api(self):
        status, headers, _d = request(self.port, "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertIn("camera=()", headers.get("Permissions-Policy", ""))
        csp = headers.get("Content-Security-Policy", "")
        for token in ("default-src 'self'", "script-src 'self'", "style-src 'self'",
                      "connect-src 'self'", "img-src 'self' data:",
                      "frame-src http://127.0.0.1:8765",
                      "frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'"):
            self.assertIn(token, csp)

    def test_security_headers_on_index(self):
        status, headers, _d = request(self.port, "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")

    def test_no_cors_headers_anywhere(self):
        """N-4: the shell is same-origin; no Access-Control-* header may be emitted."""
        for path in ("/", "/api/state", "/api/shell-info", "/static/app.css"):
            for method in ("GET", "OPTIONS"):
                _s, headers, _d = request(self.port, path, method=method)
                leaked = [k for k in headers if k.lower().startswith("access-control-")]
                self.assertEqual(leaked, [],
                                 "{} {} emitted {}".format(method, path, leaked))

    # -- H-2 negatives, one per rule ---------------------------------------
    def _post(self, headers, body=None, path="/api/start"):
        body = {"id": "distillery"} if body is None else body
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:{}{}".format(self.port, path), data=data, method="POST")
        for k, v in headers.items():
            if v is not None:
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def _good_headers(self):
        return {
            "Content-Type": "application/json",
            "Origin": "http://127.0.0.1:{}".format(self.port),
            "X-CSRF-Nonce": self.nonce,
        }

    def test_h2_missing_origin_rejected(self):
        h = self._good_headers()
        del h["Origin"]
        status, body = self._post(h)
        self.assertEqual(status, 403, body)

    def test_h2_wrong_origin_rejected(self):
        h = self._good_headers()
        h["Origin"] = "http://evil.invalid"
        self.assertEqual(self._post(h)[0], 403)

    def test_h2_localhost_origin_rejected(self):
        """N-4: localhost is NOT an accepted alternate spelling of 127.0.0.1."""
        h = self._good_headers()
        h["Origin"] = "http://localhost:{}".format(self.port)
        self.assertEqual(self._post(h)[0], 403)

    def test_h2_wrong_host_rejected(self):
        h = self._good_headers()
        h["Host"] = "localhost:{}".format(self.port)
        self.assertEqual(self._post(h)[0], 403)

    def test_h2_missing_content_type_rejected(self):
        h = self._good_headers()
        del h["Content-Type"]
        self.assertEqual(self._post(h)[0], 400)

    def test_h2_wrong_content_type_rejected(self):
        h = self._good_headers()
        h["Content-Type"] = "text/plain"
        self.assertEqual(self._post(h)[0], 400)

    def test_h2_missing_csrf_rejected(self):
        h = self._good_headers()
        del h["X-CSRF-Nonce"]
        self.assertEqual(self._post(h)[0], 403)

    def test_h2_wrong_csrf_rejected(self):
        h = self._good_headers()
        h["X-CSRF-Nonce"] = "0" * 64
        self.assertEqual(self._post(h)[0], 403)

    def test_h2_oversized_body_rejected(self):
        """Content-Length above 16 KB is refused before the body is read."""
        big = {"id": "distillery", "pad": "x" * 20000}
        status, _ = self._post(self._good_headers(), body=big)
        self.assertEqual(status, 400)

    def test_h2_body_under_limit_is_read(self):
        """A body under the cap passes H-2 and is judged on its merits, not its size."""
        body = {"id": "nope", "pad": "x" * 8000}
        status, text = self._post(self._good_headers(), body=body)
        self.assertEqual(status, 400)
        self.assertIn("unknown module", text.lower())

    def test_h2_non_get_verbs_validated(self):
        for method in ("PUT", "DELETE", "PATCH"):
            req = urllib.request.Request(
                "http://127.0.0.1:{}/api/start".format(self.port), data=b"{}", method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = resp.status
            except urllib.error.HTTPError as e:
                code = e.code
            self.assertIn(code, (400, 403, 405), "{} was not rejected".format(method))

    # -- start refusals -----------------------------------------------------
    def test_distillery_is_declared_runnable(self):
        adapter = load_all_adapters()["distillery"]
        self.assertEqual(adapter["state_class"], "runnable")

    def test_start_unknown_module_refused(self):
        status, _ = self._post(self._good_headers(), body={"id": "nope"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
