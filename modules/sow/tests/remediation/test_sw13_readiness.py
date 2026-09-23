"""SW-13 - Workspace readiness must not accept a degraded product as READY.

The finding: SOVEREIGN's /v1/health answers HTTP 200 even when it reports `ok=false`,
`status=degraded`, `configured_models_ready=false` (no model available). The shell's http
readiness matched only the status code, so the module reached READY and the tile presented a
finished, openable peer whose inference was unavailable. The fix separates LIVENESS (the
endpoint answered) from functional READINESS (the product reports it can serve) via an
adapter-declared `require_json` contract; a live-but-degraded product is DEGRADED, not READY,
keeps running, and flips to READY on the poll loop when its backend recovers - no shell restart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for _p in (str(RELEASE_ROOT), str(SHELL_SRC)):  # states.py imports `shell.src.*` absolutely
    if _p not in sys.path:
        sys.path.insert(0, _p)

import probe  # noqa: E402
import states  # noqa: E402
import adapter as adapter_mod  # noqa: E402


# --------------------------------------------------------------------------------------------
# 1. The probe primitive: liveness vs functional readiness
# --------------------------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status=200, body=b"{}"):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_open(monkeypatch, resp_or_exc):
    def fake_open(req, timeout):
        if isinstance(resp_or_exc, Exception):
            raise resp_or_exc
        return resp_or_exc
    monkeypatch.setattr(probe, "_open_direct", fake_open)


def test_functional_probe_ready_when_contract_met(monkeypatch):
    _patch_open(monkeypatch, _FakeResp(200, b'{"ok": true, "status": "ok"}'))
    live, ready, _lat, detail = probe.http_functional_probe(
        "http://127.0.0.1:9/v1/health", 200, {"ok": True}, timeout_s=1, poll_ms=50)
    assert live and ready and detail == ""


def test_functional_probe_degraded_is_live_not_ready(monkeypatch):
    # HTTP 200, but the product reports it cannot serve. The old status-only probe called this
    # READY; the functional probe must report live=True, ready=False and carry the reason.
    body = (b'{"ok": false, "status": "degraded", "configured_models_ready": false, '
            b'"detail": "configured model(s) not installed: qwen3:8b"}')
    _patch_open(monkeypatch, _FakeResp(200, body))
    live, ready, _lat, detail = probe.http_functional_probe(
        "http://127.0.0.1:9/v1/health", 200, {"ok": True}, timeout_s=1, poll_ms=200)
    assert live is True and ready is False
    assert "qwen3:8b" in detail  # the product's own reason reaches the tile


def test_functional_probe_dead_endpoint_is_not_live(monkeypatch):
    _patch_open(monkeypatch, ConnectionRefusedError("refused"))
    live, ready, _lat, detail = probe.http_functional_probe(
        "http://127.0.0.1:9/v1/health", 200, {"ok": True}, timeout_s=1, poll_ms=200)
    assert live is False and ready is False and detail  # transport error surfaced


def test_functional_probe_non_json_body_is_degraded(monkeypatch):
    _patch_open(monkeypatch, _FakeResp(200, b"<html>not json</html>"))
    live, ready, _lat, detail = probe.http_functional_probe(
        "http://127.0.0.1:9/v1/health", 200, {"ok": True}, timeout_s=1, poll_ms=200)
    assert live is True and ready is False and "JSON" in detail


# --------------------------------------------------------------------------------------------
# 2. The state machine: DEGRADED, not READY; kept running; recovers without restart
# --------------------------------------------------------------------------------------------
class _FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self._alive = True

    def is_alive(self):
        return self._alive


class _FakeSupervisor:
    def __init__(self):
        self._procs = {}
        self.spawns = 0
        self.stops = []

    def spawn(self, module_id, argv, cwd, env, log_ring=None):
        self.spawns += 1
        ph = _FakeProc()
        self._procs[module_id] = ph
        return ph

    def get_process(self, module_id):
        return self._procs.get(module_id)

    def stop(self, module_id, grace_s):
        self.stops.append(module_id)
        ph = self._procs.pop(module_id, None)
        if ph is not None:
            ph._alive = False


def _sovereign_like_adapter():
    return {
        "id": "sovereign",
        "display_name": "SOVEREIGN",
        "description": "test",
        "state_class": "runnable",
        "maturity": "preview",
        "root": "${install_root}/modules/sovereign",
        "runtime_writes": [],
        "launch": {"cwd": "${root}", "argv": ["${root}/python.exe", "-m", "x"],
                   "env_allowlist": [], "env_set": {}},
        "readiness": {"kind": "http", "url": "http://127.0.0.1:5175/v1/health",
                      "expect_status": 200, "require_json": {"ok": True},
                      "timeout_s": 5, "poll_ms": 250},
        "identity": {"kind": "http_json", "url": "http://127.0.0.1:5175/v1/health",
                     "required_keys": ["status"], "require": {"loopback_only": True}},
        "open": {"kind": "browser", "url": "http://127.0.0.1:5175/"},
        "stop": {"kind": "job_object", "grace_s": 5},
    }


@pytest.fixture
def runner(monkeypatch):
    # Never touch the real host port table or the network from these unit tests.
    monkeypatch.setattr(states, "port_owner_pid", lambda port: None)
    monkeypatch.setattr(states.probe_mod, "http_json_identity", lambda *a, **k: (True, ""))
    sup = _FakeSupervisor()
    r = states.ModuleRunner("sovereign", _sovereign_like_adapter(), sup)
    return r


def _drive_readiness(monkeypatch, live, ready, detail=""):
    monkeypatch.setattr(
        states.probe_mod, "http_functional_probe",
        lambda url, exp, rj, t, p: (live, ready, 0.01, detail))


def test_degraded_product_reaches_degraded_not_ready(runner, monkeypatch):
    _drive_readiness(monkeypatch, live=True, ready=False, detail="no model selected")
    display, _err = runner.start()
    assert runner.state == states.DEGRADED, "a degraded product must never show READY"
    assert runner.state != states.READY
    assert "no model selected" in runner.reason
    # The process is LEFT RUNNING so it can recover and the operator can open it.
    assert runner.supervisor.get_process("sovereign") is not None
    assert runner.supervisor.stops == []
    # Degraded is live + identified, so Open stays enabled - but honestly labeled DEGRADED.
    assert runner.can_open() is True
    d = runner.to_dict()
    assert d["state"] == "DEGRADED" and d["reason"]


def test_healthy_product_reaches_ready(runner, monkeypatch):
    _drive_readiness(monkeypatch, live=True, ready=True)
    runner.start()
    assert runner.state == states.READY


def test_dead_endpoint_fails_and_is_stopped(runner, monkeypatch):
    _drive_readiness(monkeypatch, live=False, ready=False, detail="connection refused")
    runner.start()
    assert runner.state == states.FAILED
    assert runner.supervisor.stops == ["sovereign"]  # a dead responder is torn down, not kept


def test_degraded_flips_to_ready_on_poll_without_restart(runner, monkeypatch):
    # Start degraded ...
    _drive_readiness(monkeypatch, live=True, ready=False, detail="no model")
    runner.start()
    assert runner.state == states.DEGRADED
    spawns_after_start = runner.supervisor.spawns
    # ... the backend comes up: the SAME probe now reports ready, and a poll must recover.
    _drive_readiness(monkeypatch, live=True, ready=True)
    runner.poll()
    assert runner.state == states.READY
    assert runner.supervisor.spawns == spawns_after_start, "recovery must not respawn the process"


def test_ready_degrades_on_poll_when_backend_lost(runner, monkeypatch):
    _drive_readiness(monkeypatch, live=True, ready=True)
    runner.start()
    assert runner.state == states.READY
    _drive_readiness(monkeypatch, live=True, ready=False, detail="model unloaded")
    runner.poll()
    assert runner.state == states.DEGRADED
    assert "model unloaded" in runner.reason


def test_degraded_but_wrong_identity_is_failed(runner, monkeypatch):
    # A live-but-degraded 200 from a FOREIGN responder must not be shown as our degraded module.
    _drive_readiness(monkeypatch, live=True, ready=False, detail="degraded")
    monkeypatch.setattr(states.probe_mod, "http_json_identity",
                        lambda *a, **k: (False, "loopback_only mismatch"))
    runner.start()
    assert runner.state == states.FAILED
    assert "IDENTITY_MISMATCH" in runner.reason
    assert runner.supervisor.stops == ["sovereign"]


# --------------------------------------------------------------------------------------------
# 3. Adapter contract: require_json is validated, and the shipped sovereign.json declares it
# --------------------------------------------------------------------------------------------
def _schema():
    return adapter_mod._load_json(adapter_mod._SCHEMA_PATH)


def test_require_json_accepted_and_compiled_for_http():
    a = _sovereign_like_adapter()
    adapter_mod._validate_against_schema(a, _schema())
    compiled = adapter_mod.compile_adapter(a)
    assert compiled["readiness"]["require_json"] == {"ok": True}


def test_require_json_rejected_for_non_http():
    a = _sovereign_like_adapter()
    a["readiness"] = {"kind": "process_window", "require_json": {"ok": True},
                      "timeout_s": 5, "poll_ms": 250}
    with pytest.raises(adapter_mod.AdapterError, match="only valid for http"):
        adapter_mod._validate_against_schema(a, _schema())


def test_require_json_rejects_non_scalar_value():
    a = _sovereign_like_adapter()
    a["readiness"]["require_json"] = {"ok": {"nested": "object"}}
    with pytest.raises(adapter_mod.AdapterError, match="JSON scalar"):
        adapter_mod._validate_against_schema(a, _schema())


def test_require_json_rejects_empty_object():
    a = _sovereign_like_adapter()
    a["readiness"]["require_json"] = {}
    with pytest.raises(adapter_mod.AdapterError, match="non-empty"):
        adapter_mod._validate_against_schema(a, _schema())


def test_shipped_sovereign_adapter_gates_on_ok():
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "sovereign.json"))
    adapter_mod._validate_against_schema(raw, _schema())
    compiled = adapter_mod.compile_adapter(raw)
    # The shipped adapter must require functional readiness, not merely a 200.
    assert compiled["readiness"]["require_json"] == {"ok": True}
