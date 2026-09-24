"""SW-18 (part a): owned vs attached module lifecycle.

The finding: Start-Shell.ps1 starts a DETACHED llama.cpp supervisor before the shell, while the shell's
`llamacpp` adapter described a `watch` launch it could own - so "modules stop with the shell" was not
true for the inference service, and the tile could not honestly say who owned what. Adapters now
declare `lifecycle`: `owned` (launched in the shell's Job Object, stopped by it) or `attached` (a
persistent service the shell only observes). Failure injection: attached adapters that try to declare
a launch/stop/test, attached identity that needs a pid, Start/Stop/Restart/Test against an attached
service, a service that is down, and a foreign responder on its port.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
for _p in (str(RELEASE_ROOT), str(SHELL_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import adapter as adapter_mod  # noqa: E402
from shell.src import states  # noqa: E402

SCHEMA = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "schema.json"))


def _attached(**over) -> dict:
    raw = {
        "id": "svc",
        "display_name": "Persistent svc",
        "description": "an attached test service",
        "state_class": "runnable",
        "lifecycle": "attached",
        "root": "${install_root}/modules/sovereign",
        "service": {"start_hint": "run Start-Svc.ps1", "stop_hint": "run Stop-Svc.ps1"},
        "readiness": {"kind": "http", "url": "http://127.0.0.1:1/models", "expect_status": 200,
                      "timeout_s": 5, "poll_ms": 250},
        "identity": {"kind": "http_json", "url": "http://127.0.0.1:1/models",
                     "required_keys": ["data"]},
        "open": {"kind": "none"},
    }
    raw.update(over)
    return raw


def _validate(raw: dict) -> dict:
    adapter_mod._validate_against_schema(raw, SCHEMA)
    return adapter_mod.compile_adapter(raw)


# --- adapter contract -----------------------------------------------------------------------------

def test_sw18a_shipped_llamacpp_adapter_is_attached_with_no_launch():
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "llamacpp.json"))
    compiled = _validate(raw)
    assert compiled["lifecycle"] == "attached"
    for owned_only in ("launch", "stop", "startup_test"):
        assert owned_only not in compiled
    assert "Stop-LlamaCppSupervisor.ps1" in compiled["service"]["stop_hint"]


def test_sw18a_every_other_shipped_module_is_owned():
    for name in ("sovereign", "sow", "debate", "distillery", "tokencenter"):
        raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / f"{name}.json"))
        assert _validate(raw)["lifecycle"] == "owned", name


@pytest.mark.parametrize("field,value", [
    ("launch", {"cwd": "${root}", "argv": ["${root}/x.exe"]}),
    ("stop", {"kind": "job_object", "grace_s": 5}),
    ("startup_test", {}),
])
def test_sw18a_attached_adapter_may_not_declare_owned_lifecycle(field, value):
    with pytest.raises(adapter_mod.AdapterError, match="attached module may not declare"):
        _validate(_attached(**{field: value}))


def test_sw18a_attached_adapter_needs_http_readiness_and_http_identity():
    with pytest.raises(adapter_mod.AdapterError, match="readiness.kind must be http"):
        _validate(_attached(readiness={"kind": "process_window", "timeout_s": 5, "poll_ms": 250}))
    with pytest.raises(adapter_mod.AdapterError, match="no shell-owned pid"):
        _validate(_attached(identity={"kind": "process_image"}))


@pytest.mark.parametrize("over,match", [
    ({"lifecycle": "adopted"}, "lifecycle must be one of"),
    ({"service": {"reboot_hint": "x"}}, "Unknown service field"),
    ({"service": {"stop_hint": ""}}, "service.stop_hint"),
    ({"service": "run it"}, "service must be an object"),
])
def test_sw18a_malformed_lifecycle_fields_are_config_errors(over, match):
    with pytest.raises(adapter_mod.AdapterError, match=match):
        _validate(_attached(**over))


def test_sw18a_service_hints_are_only_valid_for_attached_modules():
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "tokencenter.json"))
    raw["service"] = {"stop_hint": "x"}
    with pytest.raises(adapter_mod.AdapterError, match="only valid for lifecycle 'attached'"):
        _validate(raw)


# --- runner behaviour -----------------------------------------------------------------------------

class _RecordingSupervisor:
    def __init__(self):
        self.calls = []

    def get_process(self, _mid):
        return None

    def spawn(self, *a, **k):
        self.calls.append(("spawn", a))
        raise AssertionError("an attached service must never be spawned")

    def stop(self, *a, **k):
        self.calls.append(("stop", a))
        raise AssertionError("an attached service must never be stopped")


def _serve(payload: dict | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload or {"not": "it"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _runner(port: int):
    url = f"http://127.0.0.1:{port}/models"
    compiled = _validate(_attached(
        readiness={"kind": "http", "url": url, "expect_status": 200, "timeout_s": 5,
                   "poll_ms": 250},
        identity={"kind": "http_json", "url": url, "required_keys": ["data"]}))
    sup = _RecordingSupervisor()
    return states.ModuleRunner("svc", compiled, sup), sup


def test_sw18a_running_attached_service_is_observed_as_attached_not_owned():
    server = _serve({"data": []})
    try:
        runner, sup = _runner(server.server_address[1])
        assert runner.poll() == states.ATTACHED
        rec = runner.to_dict()
        assert rec["lifecycle"] == "attached" and rec["persistent"] is True
        assert rec["service"]["stop_hint"] == "run Stop-Svc.ps1"
        assert sup.calls == []
    finally:
        server.shutdown()


def test_sw18a_foreign_responder_on_the_port_is_not_attached():
    server = _serve({"something": "else"})
    try:
        runner, _sup = _runner(server.server_address[1])
        runner.poll()
        assert runner.state == states.FAILED
        assert runner.reason == states.PORT_OCCUPIED_UNRECOGNIZED
    finally:
        server.shutdown()


def test_sw18a_down_attached_service_reports_not_running(monkeypatch):
    monkeypatch.setattr(states.probe_mod, "http_probe", lambda *a, **k: (False, 0.0, "refused"))
    runner, sup = _runner(1)
    assert runner.poll() == states.STOPPED
    assert runner.reason == "persistent service not running"
    assert sup.calls == []


def test_sw18a_start_stop_restart_never_touch_an_attached_service():
    server = _serve({"data": []})
    try:
        runner, sup = _runner(server.server_address[1])
        runner.poll()
        allowed, status, message = runner.can_start()
        assert (allowed, status) == (False, 409) and "run Start-Svc.ps1" in message
        display, detail = runner.start()
        assert "attached persistent service" in detail
        assert runner.stop() == states.ATTACHED
        assert runner.cancel() == states.ATTACHED
        assert sup.calls == [], "the shell touched a process it does not own"
    finally:
        server.shutdown()


def test_sw18a_api_refuses_lifecycle_actions_on_attached_services_with_409():
    from shell.src.server import ShellAPIHandler

    server = _serve({"data": []})
    try:
        runner, sup = _runner(server.server_address[1])
        errors = []
        fake = SimpleNamespace(
            _runner=lambda body: ("svc", runner),
            _send_error=lambda message, status=400: errors.append((status, message)),
            _send_json=lambda payload: errors.append((200, payload)),
        )
        ShellAPIHandler._handle_stop(fake, {"id": "svc"})
        ShellAPIHandler._handle_restart(fake, {"id": "svc"})
        ShellAPIHandler._handle_startup_test(fake, {"id": "svc"})
        assert [status for status, _ in errors] == [409, 409, 409]
        assert "Stop-Svc.ps1" in errors[0][1]
        assert sup.calls == []
    finally:
        server.shutdown()


def test_sw18a_state_payload_lists_persistent_services_separately():
    from shell.src.server import ShellAPIHandler

    server = _serve({"data": []})
    try:
        runner, _sup = _runner(server.server_address[1])
        runner.poll()
        sent = []
        fake = SimpleNamespace(lock=threading.Lock(), states={"svc": runner},
                               _send_json=sent.append)
        ShellAPIHandler._handle_get_state(fake)
        payload = sent[0]
        assert payload["persistent_services"] == [{
            "id": "svc", "state": states.ATTACHED, "reason": "",
            "service": {"start_hint": "run Start-Svc.ps1", "stop_hint": "run Stop-Svc.ps1"}}]
    finally:
        server.shutdown()


def test_sw18a_ui_disables_lifecycle_controls_for_attached_services():
    app = (RELEASE_ROOT / "shell" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'ATTACHED: { cls: "badge-external", label: "Attached (persistent service)" }' in app
    assert 'rec.lifecycle === "attached" && action !== "open"' in app
