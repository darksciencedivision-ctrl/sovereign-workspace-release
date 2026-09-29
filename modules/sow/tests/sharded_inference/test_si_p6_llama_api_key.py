"""Sharded inference P6 fix: the product's llama.cpp client sends the key of the supervisor it talks to.

Live failure: a LONG job died with `401 Unauthorized` on /v1/models. A SOVEREIGN_LLAMA_CPP_API_KEY
persisted at Windows user level (from another state home) outranked the isolated state home's
supervisor key file, while introspection read the file and still reported llama.cpp reachable.

Now one resolver serves every reader: the state home's supervisor key file is authoritative for the
URL that supervisor serves; the variable is used for any other URL and as the fallback. A key the
server refuses (stale, wrong or missing) is a clear InferenceAuthError naming the key's source (never
the key), and token counting re-raises it instead of degrading to the byte bound. A present key
leads to success.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import gpu_occupancy  # noqa: E402
from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402
from sovereign_product.runtime_contracts import (  # noqa: E402
    KEY_SOURCE_ENV,
    KEY_SOURCE_NONE,
    KEY_SOURCE_SUPERVISOR_FILE,
    InferenceAuthError,
    resolve_llama_cpp_api_key,
)

STATE_ENV_KEYS = ("SOVEREIGN_STATE_HOME", "SOVEREIGN_STATE_DIR", "SOVEREIGN_WORKSPACE_STATE",
                  "SOVEREIGN_ROOT", "SOVEREIGN_LLAMA_CPP_API_KEY", "SOVEREIGN_LLAMA_CPP_BASE_URL",
                  "SOVEREIGN_INFERENCE_BACKEND")
GOOD_KEY = "k-supervisor-0123456789abcdef"
STALE_KEY = "k-stale-user-level-fedcba9876543210"
SUPERVISOR_URL = "http://127.0.0.1:18080"


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in STATE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    return tmp_path / "LocalAppData"


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "install"
    root.mkdir()
    (root / P.ROOT_MARKER).write_text(P.ROOT_MARKER_CONTENT, encoding="utf-8")
    (root / P.STATE_LAYOUT_FILE).write_text(json.dumps({"schema": 1, "state": "external"}),
                                            encoding="utf-8")
    shipped = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    (root / LW.CONFIG_FILE).write_text(json.dumps(shipped), encoding="utf-8")
    return root


def _supervisor(runtime: Path, *, key: str = GOOD_KEY, url: str | None = SUPERVISOR_URL) -> Path:
    """What supervisor_service.start leaves behind: api_key and (usually) consumer.env."""
    service = runtime / "llamacpp_supervisor"
    service.mkdir(parents=True, exist_ok=True)
    (service / "api_key").write_text(key + "\n", encoding="utf-8")
    if url is not None:
        (service / "consumer.env").write_text(
            f"SOVEREIGN_INFERENCE_BACKEND=llama.cpp\nSOVEREIGN_LLAMA_CPP_BASE_URL={url}\n"
            f"SOVEREIGN_LLAMA_CPP_API_KEY={key}\n", encoding="utf-8")
    return service


# --- the resolver ---------------------------------------------------------------------------------

def test_si_p6_supervisor_key_file_beats_a_stale_environment_key(clean_env, tmp_path):
    runtime = tmp_path / "state" / "runtime"
    _supervisor(runtime)
    env = {"SOVEREIGN_LLAMA_CPP_API_KEY": STALE_KEY}
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL, env=env) == (
        GOOD_KEY, KEY_SOURCE_SUPERVISOR_FILE)
    # the same origin spelled differently is still the supervisor's URL
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL + "/", env=env)[0] == GOOD_KEY


def test_si_p6_key_file_without_consumer_env_still_wins(clean_env, tmp_path):
    runtime = tmp_path / "state" / "runtime"
    _supervisor(runtime, url=None)
    env = {"SOVEREIGN_LLAMA_CPP_API_KEY": STALE_KEY}
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL, env=env)[0] == GOOD_KEY


def test_si_p6_environment_key_serves_a_url_the_supervisor_does_not(clean_env, tmp_path):
    runtime = tmp_path / "state" / "runtime"
    _supervisor(runtime)
    env = {"SOVEREIGN_LLAMA_CPP_API_KEY": "k-external-server"}
    assert resolve_llama_cpp_api_key(runtime, "http://127.0.0.1:18199", env=env) == (
        "k-external-server", KEY_SOURCE_ENV)


def test_si_p6_environment_is_the_fallback_and_none_is_reported(clean_env, tmp_path):
    runtime = tmp_path / "state" / "runtime"
    env = {"SOVEREIGN_LLAMA_CPP_API_KEY": "k-env-only"}
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL, env=env) == (
        "k-env-only", KEY_SOURCE_ENV)
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL, env={}) == (None, KEY_SOURCE_NONE)
    (runtime / "llamacpp_supervisor").mkdir(parents=True)
    (runtime / "llamacpp_supervisor" / "api_key").write_text("  \n", encoding="utf-8")
    assert resolve_llama_cpp_api_key(runtime, SUPERVISOR_URL, env={}) == (None, KEY_SOURCE_NONE)


# --- every reader agrees --------------------------------------------------------------------------

def test_si_p6_product_client_uses_the_isolated_supervisor_key_over_user_env(
        clean_env, tmp_path, monkeypatch):
    """The live failure: stale user-level key + isolated state home -> the product sent the stale key."""
    from sovereign_product.server import ProductService

    state_dir = tmp_path / "e2e-ws" / "sovereign" / "runtime"
    _supervisor(state_dir)
    monkeypatch.setenv("SOVEREIGN_INFERENCE_BACKEND", "llama.cpp")
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_BASE_URL", SUPERVISOR_URL)
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_API_KEY", STALE_KEY)
    fake = SimpleNamespace(root=tmp_path / "install", paths=SimpleNamespace(state_dir=state_dir),
                           _manifest=lambda: {"RUNTIME": {}})
    client = ProductService._default_model_client(fake)
    assert isinstance(client, LlamaCppClient)
    assert client.api_key == GOOD_KEY
    assert client.api_key_source == KEY_SOURCE_SUPERVISOR_FILE


def test_si_p6_gpu_occupancy_uses_the_same_key(clean_env, tmp_path, monkeypatch):
    root = _root(tmp_path)
    _supervisor(P.resolve_runtime_dir(root))
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_API_KEY", STALE_KEY)
    assert gpu_occupancy.llama_cpp_api_key(root) == GOOD_KEY


# --- a refused key is a clear refusal; the right key succeeds ---------------------------------------

class _KeyedLlama(BaseHTTPRequestHandler):
    """Minimal llama-server: every endpoint requires `Authorization: Bearer <GOOD_KEY>`."""

    def log_message(self, *args):  # keep test output quiet
        pass

    def _authorized(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {GOOD_KEY}":
            return True
        body = b'{"error":{"code":401,"message":"Invalid API Key","type":"authentication_error"}}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self._authorized():
            self._json({"data": [{"id": "m", "meta": {"n_ctx_train": 4096}}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if self._authorized():
            self._json({"tokens": [1, 2, 3]})


@pytest.fixture
def keyed_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KeyedLlama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("key,source,sent", [
    (STALE_KEY, KEY_SOURCE_ENV, "refused an API key"),
    ("k-wrong", KEY_SOURCE_SUPERVISOR_FILE, "refused an API key"),
    (None, KEY_SOURCE_NONE, "refused no API key"),
])
def test_si_p6_refused_key_is_a_clear_refusal_naming_its_source(keyed_server, key, source, sent):
    client = LlamaCppClient(keyed_server, api_key=key, api_key_source=source)
    with pytest.raises(InferenceAuthError) as refused:
        client.native_context_length("m")
    message = str(refused.value)
    assert sent in message and "HTTP 401" in message
    assert f"key source: {source}" in message
    assert key is None or key not in message, "the refusal must never echo the key"
    # token counting must not hide a refused key behind its byte-bound fallback
    with pytest.raises(InferenceAuthError):
        client.count_text_tokens("m", "hello")
    with pytest.raises(InferenceAuthError):
        client.count_prompt_tokens("m", [{"role": "user", "content": "hi"}])


def test_si_p6_present_key_succeeds(keyed_server):
    client = LlamaCppClient(keyed_server, api_key=GOOD_KEY,
                            api_key_source=KEY_SOURCE_SUPERVISOR_FILE)
    assert client.native_context_length("m") == 4096
    assert client.count_text_tokens("m", "hello") == 3


def test_si_p6_self_state_probes_with_the_key_the_client_sends(clean_env, tmp_path, keyed_server,
                                                               monkeypatch):
    """Introspection read only the key file, so it said "online" while the client sent another key."""
    from sovereign_product.introspection import _probe_llama_cpp

    state_dir = tmp_path / "state" / "runtime"
    service = state_dir / "llamacpp_supervisor"
    service.mkdir(parents=True)
    (service / "state.json").write_text(json.dumps({"pid": 0}), encoding="utf-8")
    paths = P.ProductPaths(root=tmp_path / "install", state_dir=state_dir,
                           db_path=state_dir / "sovereign.db", evidence_dir=state_dir / "evidence")
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_BASE_URL", keyed_server)
    # an externally managed server: no key file here, the variable carries its key
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_API_KEY", GOOD_KEY)
    report = _probe_llama_cpp(paths, configured_models=["m"], timeout=1.0)
    assert report["probe_status"] == "online", report
    # the supervisor serving this URL has its own key file: a stale variable must not be used
    _supervisor(state_dir, url=keyed_server)
    monkeypatch.setenv("SOVEREIGN_LLAMA_CPP_API_KEY", STALE_KEY)
    assert LlamaCppClient(keyed_server, api_key=resolve_llama_cpp_api_key(
        state_dir, keyed_server)[0]).native_context_length("m") == 4096
    report = _probe_llama_cpp(paths, configured_models=["m"], timeout=1.0)
    assert report["probe_status"] == "online", report


def test_si_p6_long_run_with_a_refused_key_fails_with_the_auth_refusal(clean_env, tmp_path,
                                                                       keyed_server):
    root = _root(tmp_path)
    client = LlamaCppClient(keyed_server, api_key=STALE_KEY, api_key_source=KEY_SOURCE_ENV)
    executor = LW.LongWorkloadExecutor(root=root, evidence_dir=root / "ev", client=client,
                                       config=LW.load_config(root))
    with pytest.raises(InferenceAuthError, match="key source: SOVEREIGN_LLAMA_CPP_API_KEY"):
        executor.run("job-auth", "objective", cancel_requested=lambda: False,
                     progress_callback=lambda *_a, **_k: None)
