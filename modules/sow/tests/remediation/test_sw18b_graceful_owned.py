"""SW-18 (part b): owned modules shut down gracefully and flush; teardown is recorded, not implied.

Close condition for SW-18: "start/stop/restart tests enumerate owned vs attached processes - owned
children exit and flush; intentionally-persistent services remain and are reported; unrelated services
untouched." These tests run the REAL module entry points (Distillery serve.py, the SOVEREIGN product
server, the Debate app) under the REAL Windows Job supervisor and stop them the way the shell does:
signal SWS_SHUTDOWN_EVENT, wait the grace period, force only if needed. Each must exit on its own
(graceful, exit 0, not TerminateJobObject's 1) and leave its state flushed. `shutdown_workspace` is
then exercised with an owned cooperating child, an owned child that ignores the event, an attached
persistent service and an unrelated process.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

if sys.platform != "win32":
    pytest.skip("the Job supervisor and shutdown Event are Windows-only", allow_module_level=True)

RELEASE_ROOT = Path(__file__).resolve().parents[4]
SHELL_SRC = RELEASE_ROOT / "shell" / "src"
MODULES = RELEASE_ROOT / "modules"
for _p in (str(RELEASE_ROOT), str(SHELL_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import adapter as adapter_mod  # noqa: E402
from shell.src import supervisor as sup_mod  # noqa: E402
from shell.src import teardown  # noqa: E402

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_EVIDENCE_DIR",
                  "SOVEREIGN_DB_PATH", "SOVEREIGN_ROOT", "SWS_SHUTDOWN_EVENT")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float = 60.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True  # answered (e.g. 403 host guard) - it is up
        except OSError:
            time.sleep(0.25)
    return False


def _env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in STATE_ENV_KEYS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _run_and_stop(argv, cwd, env, url, *, grace_s=15, ready_timeout=90.0):
    sup = sup_mod.JobSupervisor(max_processes=2)
    try:
        ph = sup.spawn("mod", argv, str(cwd), env)
        assert _wait_http(url, ready_timeout), f"module never answered {url}"
        assert ph.is_alive()
        record = sup.stop("mod", grace_s)
        return record, ph
    finally:
        sup.close()


# --- the real owned modules exit on the shutdown Event --------------------------------------------

def test_sw18b_distillery_console_exits_gracefully_on_the_shutdown_event():
    port = _free_port()
    record, ph = _run_and_stop([sys.executable, str(MODULES / "distillery" / "serve.py")],
                               MODULES / "distillery", _env(DISTILLERY_PORT=str(port)),
                               f"http://127.0.0.1:{port}/health", grace_s=10, ready_timeout=30)
    assert record["graceful"] is True and record["forced"] is False, record
    assert record["exit_code"] == 0, "exited by TerminateJobObject, not on its own"


def test_sw18b_sovereign_server_exits_gracefully_and_flushes_its_store(tmp_path):
    python = MODULES / "sovereign" / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        pytest.skip("sovereign venv not provisioned")
    port = _free_port()
    ws = tmp_path / "ws"
    env = _env(SOVEREIGN_WORKSPACE_STATE=str(ws), SOVEREIGN_INFERENCE_BACKEND="ollama")
    record, _ph = _run_and_stop(
        [str(python), "-m", "sovereign_product.server", "--root", str(MODULES / "sovereign"),
         "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
        MODULES / "sovereign", env, f"http://127.0.0.1:{port}/v1/health", grace_s=15)
    assert record["graceful"] is True and record["forced"] is False, record
    assert record["exit_code"] == 0
    runtime = ws / "sovereign" / "runtime"
    assert (runtime / "sovereign.db").is_file(), "the product never opened its external store"
    # A cleanly closed SQLite WAL database checkpoints and removes its -wal file; a killed
    # process leaves it behind. Its absence is the flush.
    assert not (runtime / "sovereign.db-wal").exists(), "store was not closed cleanly"


def test_sw18b_debate_app_exits_gracefully_and_runs_its_lifespan_shutdown(tmp_path):
    python = MODULES / "debate" / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        pytest.skip("debate venv not provisioned")
    port = _free_port()
    config = json.loads((MODULES / "debate" / "config.json").read_text(encoding="utf-8"))
    config["port"] = port
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    logs = tmp_path / "logs"
    env = _env(CONFIG_PATH=str(config_path), DEBATE_LOG_DIR=str(logs),
               SOVEREIGN_INFERENCE_BACKEND="ollama")
    record, _ph = _run_and_stop([str(python), "app.py"], MODULES / "debate", env,
                                f"http://127.0.0.1:{port}/", grace_s=15)
    assert record["graceful"] is True and record["forced"] is False, record
    assert record["exit_code"] == 0
    logged = "".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in logs.rglob("*") if p.is_file())
    assert "app_lifespan_shutdown" in logged, "the lifespan shutdown (flush) did not run"


def test_sw18b_shipped_adapters_declare_their_graceful_contract():
    schema = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "schema.json"))
    expected = {"sovereign": "shutdown_event", "debate": "shutdown_event",
                "distillery": "shutdown_event", "tokencenter": "shutdown_event", "sow": "none"}
    for mid, contract in expected.items():
        raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / f"{mid}.json"))
        adapter_mod._validate_against_schema(raw, schema)
        assert raw["stop"]["graceful"] == contract, mid


@pytest.mark.parametrize("stop,match", [
    ({"kind": "job_object", "grace_s": 5, "graceful": "sometimes"}, "stop.graceful"),
    ({"kind": "job_object", "grace_s": 5, "linger": 1}, "Unknown stop field"),
])
def test_sw18b_malformed_stop_contract_is_a_config_error(stop, match):
    schema = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "schema.json"))
    raw = adapter_mod._load_json(str(RELEASE_ROOT / "shell" / "modules" / "tokencenter.json"))
    raw["stop"] = stop
    with pytest.raises(adapter_mod.AdapterError, match=match):
        adapter_mod._validate_against_schema(raw, schema)


# --- shutdown_workspace: owned stop, attached untouched, unrelated untouched, receipt written -----

_COOP = """
import sys, threading
sys.path.insert(0, r"{shell_src}")
import graceful
done = threading.Event()
graceful.install_shutdown_watcher(done.set)
sys.exit(0 if done.wait(60) else 3)
"""


def _attached_stub():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"data": []}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_sw18b_shutdown_workspace_stops_owned_reports_attached_and_touches_nothing_else(tmp_path):
    from shell.src.server import shutdown_workspace
    from shell.src import states

    sup = sup_mod.JobSupervisor(max_processes=4)
    stub = _attached_stub()
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        coop = sup.spawn("coop", [sys.executable, "-c", _COOP.format(shell_src=SHELL_SRC)],
                         str(tmp_path), _env())
        stubborn = sup.spawn("stubborn", [sys.executable, "-c", "import time; time.sleep(120)"],
                             str(tmp_path), _env())
        legacy = sup.spawn("legacy", [sys.executable, "-c", "import time; time.sleep(120)"],
                           str(tmp_path), _env())
        time.sleep(1.0)  # let the cooperating child install its watcher

        url = f"http://127.0.0.1:{stub.server_address[1]}/models"
        attached = states.ModuleRunner("llamacpp", {
            "id": "llamacpp", "display_name": "llama.cpp", "state_class": "runnable",
            "lifecycle": "attached", "service": {"stop_hint": "Stop-LlamaCppSupervisor.ps1"},
            "readiness": {"kind": "http", "url": url, "timeout_s": 5, "poll_ms": 250},
            "identity": {"kind": "http_json", "url": url, "required_keys": ["data"]},
            "open": {"kind": "none"}}, sup)
        assert attached.poll() == states.ATTACHED

        def owned(contract):
            return SimpleNamespace(attached=False, state="READY",
                                   adapter={"stop": {"graceful": contract}})

        runners = {"coop": owned("shutdown_event"), "stubborn": owned("shutdown_event"),
                   "legacy": owned("none"), "llamacpp": attached}
        receipt, path = shutdown_workspace(sup, runners, str(tmp_path / "receipts"))

        by_id = {r["module_id"]: r for r in receipt["owned"]}
        assert by_id["coop"]["graceful"] and by_id["coop"]["exit_code"] == 0
        assert by_id["coop"]["graceful_contract_met"] is True
        assert by_id["stubborn"]["forced"] and by_id["stubborn"]["graceful_contract_met"] is False
        assert by_id["legacy"]["forced"] and by_id["legacy"]["graceful_contract_met"] is True
        assert receipt["all_owned_stopped"] is True
        assert receipt["graceful_contracts_met"] is False  # stubborn broke its promise, visibly
        for ph in (coop, stubborn, legacy):
            assert not ph.is_alive()

        assert receipt["attached"] == [{
            "module_id": "llamacpp", "observed_state": states.ATTACHED, "left_running": True,
            "stopped_by_shell": False, "stop_hint": "Stop-LlamaCppSupervisor.ps1"}]
        assert _wait_http(url, 5), "the attached persistent service was touched"
        assert unrelated.poll() is None, "an unrelated process was touched"

        on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
        assert on_disk == receipt
        lines = teardown.summarize(receipt)
        assert any("stubborn" in l and "contract NOT met" in l for l in lines)
        assert any(l.startswith("attached llamacpp: left running") for l in lines)
    finally:
        unrelated.kill()
        stub.shutdown()
        sup.close()


def test_sw18b_teardown_receipts_are_bounded(tmp_path):
    for _ in range(teardown.KEEP + 5):
        teardown.write_receipt({"schema": 1, "owned": [], "attached": []}, str(tmp_path))
    assert len(list(tmp_path.glob("teardown-*.json"))) == teardown.KEEP
    assert teardown.latest_receipt(str(tmp_path))["schema"] == 1


def test_sw18b_close_is_idempotent_and_reports_stop_records(tmp_path):
    sup = sup_mod.JobSupervisor(max_processes=1)
    ph = sup.spawn("x", [sys.executable, "-c", "import time; time.sleep(60)"], str(tmp_path),
                   _env())
    records = sup.close()
    assert [r["module_id"] for r in records] == ["x"] and records[0]["alive_after_stop"] is False
    assert not ph.is_alive()
    assert sup.close() == []
