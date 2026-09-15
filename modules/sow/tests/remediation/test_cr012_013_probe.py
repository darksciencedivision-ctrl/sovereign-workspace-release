"""CR-012 (preflight reports the wrong port for custom shell ports) and
CR-013 (successful HTTP probe responses are not reliably closed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SHELL_SRC = Path(__file__).resolve().parents[4] / "shell" / "src"
if str(SHELL_SRC) not in sys.path:
    sys.path.insert(0, str(SHELL_SRC))

import probe  # noqa: E402


# -- CR-012 ----------------------------------------------------------------
def _shell_check(checks):
    return next(c for c in checks if c["id"] == "port_shell")


def test_cr012_custom_port_occupied_is_the_shell():
    ports = {"5175": {"free": True}, "8700": {"free": True}, "5181": {"free": False}}
    checks = probe.resolve_preflight_checks({}, {}, ports, shell_port=5181)
    sc = _shell_check(checks)
    assert sc["port"] == 5181
    assert sc["status"] == "ok" and "5181" in sc["detail"] and "shell" in sc["detail"]
    # the wrong-port id must not appear
    assert not any(c["id"] == "port_5180" for c in checks)


def test_cr012_custom_port_free_is_flagged_not_silently_ok():
    # Before the fix, a missing '5180' key made free=False -> "ok/shell" even when the real shell
    # port (5181) was actually free. Now the status reflects the configured port's real state.
    ports = {"5181": {"free": True}}
    checks = probe.resolve_preflight_checks({}, {}, ports, shell_port=5181)
    sc = _shell_check(checks)
    assert sc["status"] == "bad" and "free" in sc["detail"] and "5181" in sc["detail"]


def test_cr012_shell_port_derived_from_origin_env(monkeypatch):
    monkeypatch.setenv("SWS_SHELL_ORIGIN", "http://127.0.0.1:5199")
    assert probe._shell_port() == 5199
    monkeypatch.delenv("SWS_SHELL_ORIGIN", raising=False)
    assert probe._shell_port() == 5180  # default


def test_cr012_default_port_still_ok():
    ports = {"5175": {"free": True}, "8700": {"free": True}, "5180": {"free": False}}
    checks = probe.resolve_preflight_checks({}, {}, ports, shell_port=5180)
    sc = _shell_check(checks)
    assert sc["port"] == 5180 and sc["status"] == "ok"


# -- CR-013 ----------------------------------------------------------------
class _FakeResp:
    def __init__(self, status=200, body=b'{"models": []}'):
        self.status = status
        self._body = body
        self.closed = False

    def read(self):
        return self._body

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def test_cr013_http_probe_closes_response(monkeypatch):
    fakes = []

    def fake_open(req, timeout):
        f = _FakeResp(status=200)
        fakes.append(f)
        return f

    monkeypatch.setattr(probe, "_open_direct", fake_open)
    ok, _elapsed, _err = probe.http_probe("http://127.0.0.1:9/x", 200, timeout_s=1, poll_ms=10)
    assert ok
    assert fakes and all(f.closed for f in fakes), "probe response left open"


def test_cr013_html_identity_closes_response(monkeypatch):
    fake = _FakeResp(status=200, body=b"<html>MARKER</html>")
    monkeypatch.setattr(probe, "_open_direct", lambda req, timeout: fake)
    ok, _ = probe.http_html_identity("http://127.0.0.1:9/x", "MARKER")
    assert ok and fake.closed


def test_cr013_preflight_ollama_closes_response(monkeypatch):
    fake = _FakeResp(status=200, body=b'{"models": [{"name": "m"}]}')
    monkeypatch.setattr(probe, "_open_direct", lambda req, timeout: fake)
    out = probe.preflight_ollama()
    assert out["reachable"] and fake.closed
