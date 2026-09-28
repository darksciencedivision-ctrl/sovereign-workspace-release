"""H4: security audit of the LONG route and its llama.cpp backend.

Covered here: the llama-server key never goes on a command line; a refused key reaches no stored
artifact (job error, database, evidence, checkpoints); malformed job ids on the LONG endpoints are
refused (never a 500) and never touch the filesystem; request size limits hold; every listener the
product starts is loopback-only. (Key-resolution precedence and refusal wording are covered by
test_si_p6_llama_api_key.py; @input containment by test_si_p6_long_route.py.)

Found live on 2026-09-28: llama-server was started with ``--api-key <key>`` in its argv, so every
process listing (Task Manager, a WMI query, an orphan check in an agent transcript) showed the key.
"""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.runtime_contracts import KEY_SOURCE_ENV, RuntimeControlError  # noqa: E402
from sovereign_product.runtime_registry import RuntimeRegistry  # noqa: E402
from sovereign_product.runtime_supervisor import LlamaCppSupervisor, SupervisorConfig  # noqa: E402
from sovereign_product.server import (  # noqa: E402
    MAX_INPUT_CHARACTERS, MAX_JSON_BYTES, ProductService, _validate_bind_host, create_app)
from sovereign_product.store import SovereignStore  # noqa: E402

from test_si_long_failure_paths import _service  # noqa: E402
from test_si_p6_llama_api_key import keyed_server  # noqa: E402,F401
from test_si_p6_long_route import _small_root, clean_env  # noqa: E402,F401

SECRET = "k-h4-secret-5f3a9c0e7b1d42a6"


# --- the llama-server key stays off the command line ----------------------------------------------

class _Ready:
    status_code = 200

    def json(self):
        return {"data": []}


def test_h4_llama_server_gets_its_key_from_a_file_not_its_command_line(tmp_path):
    started = {}

    def popen(command, **kwargs):
        started["command"] = command
        return SimpleNamespace(pid=4242, poll=lambda: None)

    supervisor = LlamaCppSupervisor(
        SupervisorConfig(executable="llama-server.exe", port=1, work_dir=str(tmp_path),
                         api_key=SECRET, detach=True),
        RuntimeRegistry(), popen=popen,
        request_session=SimpleNamespace(request=lambda *a, **k: _Ready()))
    supervisor._assert_port_free = lambda: None  # port 1 is never probed
    supervisor.render_preset = lambda: "[m]\n"  # the preset is not what this test is about
    supervisor.start()
    command = started["command"]
    assert all(SECRET not in str(part) for part in command), "the key is in the argv"
    assert "--api-key" not in command
    key_file = Path(command[command.index("--api-key-file") + 1])
    assert key_file.parent == tmp_path
    assert key_file.read_bytes() == SECRET.encode() + b"\n", "one key, LF only"


def test_h4_every_listener_is_loopback_only():
    for host in ("127.0.0.1", "localhost", "::1"):
        assert _validate_bind_host(host) == host
    for host in ("0.0.0.0", "192.168.1.20", "::", "example.com", ""):
        with pytest.raises(Exception, match="loopback"):
            _validate_bind_host(host)
    with pytest.raises(RuntimeControlError, match="loopback"):
        LlamaCppSupervisor(SupervisorConfig(executable="x.exe", host="0.0.0.0"),
                           RuntimeRegistry())


def test_h4_the_supervisor_key_is_never_sent_to_a_url_it_does_not_serve(clean_env, tmp_path):
    from sovereign_product.runtime_contracts import KEY_SOURCE_NONE, resolve_llama_cpp_api_key

    service = tmp_path / "runtime" / "llamacpp_supervisor"
    service.mkdir(parents=True)
    (service / "api_key").write_bytes(SECRET.encode() + b"\n")
    (service / "consumer.env").write_bytes(
        b"SOVEREIGN_LLAMA_CPP_BASE_URL=http://127.0.0.1:18080\n")
    runtime = tmp_path / "runtime"
    assert resolve_llama_cpp_api_key(runtime, "http://127.0.0.1:18080", env={})[0] == SECRET
    assert resolve_llama_cpp_api_key(runtime, "http://127.0.0.1:18199", env={}) == (
        None, KEY_SOURCE_NONE)


# --- a refused key reaches no artifact --------------------------------------------------------------

def test_h4_a_refused_key_is_in_no_stored_artifact(clean_env, tmp_path, keyed_server):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    client = LlamaCppClient(keyed_server, api_key=SECRET, api_key_source=KEY_SOURCE_ENV)
    service = _service(root, store, client)
    session = store.create_session()
    job_id = store.create_job(session["session_id"], "LONG", "Draft a plan.")["job_id"]
    service._run_job(job_id)
    job = store.get_job(job_id)
    assert job["status"] == "failed" and "HTTP 401" in job["error"]
    assert SECRET not in job["error"]
    store.close()
    leaked = [str(p) for p in tmp_path.rglob("*")
              if p.is_file() and SECRET.encode() in p.read_bytes()]
    assert leaked == [], leaked


# --- malformed job ids on the LONG endpoints ------------------------------------------------------

@pytest.mark.parametrize("job_id", ["..", "a b", "x" * 200, "job;rm", "%2e%2e"])
@pytest.mark.parametrize("action", ["ledger", "resume"])
def test_h4_malformed_job_ids_are_refused_without_touching_files(clean_env, tmp_path, job_id,
                                                                 action):
    root = _small_root(tmp_path)
    store = SovereignStore(tmp_path / "state.db")
    service = _service(root, store, None)
    service.long_run = lambda i: ProductService.long_run(service, i)
    app = create_app(service=service).test_client()
    if action == "ledger":
        response = app.get(f"/v1/jobs/{job_id}/ledger")
    else:
        response = app.post(f"/v1/jobs/{job_id}/resume", json={})
    assert response.status_code in (400, 404), response.get_json()
    assert "internal" not in response.get_json()["error"]
    assert not (root / "ev").exists(), "a refused id never creates run state"


# --- request size limits ---------------------------------------------------------------------------

def test_h4_request_size_limits_hold():
    app = create_app(service=SimpleNamespace()).test_client()
    response = app.post("/v1/message", data=b"{" + b" " * MAX_JSON_BYTES + b"}",
                        content_type="application/json")
    assert response.status_code == 413
    fake = SimpleNamespace()
    with pytest.raises(ValueError, match="character limit"):
        ProductService.submit(fake, "session_x", "x" * (MAX_INPUT_CHARACTERS + 1))
    # an @input file is capped too (LW.MAX_INPUT_BYTES), without reading it whole first
    assert LW.MAX_INPUT_BYTES == 64 * 1024 * 1024
