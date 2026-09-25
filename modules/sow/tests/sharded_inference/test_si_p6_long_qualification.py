"""Sharded inference: qualifying the LONG route's hybrid profiles with the SW-27 harness.

LONG profiles (`"kind": "long"`) name a big hybrid-served model and a ladder of input sizes (0 =
agentic plan steps; N = map/reduce over ~N tokens placed in the product's `long_inputs` inbox). The
harness drives them through the product's HTTP API like every other scenario and records end-to-end
time, shards and chunks per hour, peak VRAM/RAM, and cold vs warm model load (whether the model was
resident in llama.cpp when the job was submitted). A LONG envelope is REPORTED only: it never gates
the QUICK/DEEP configuration and cannot be installed. Failure injection: malformed LONG profiles,
LONG on Ollama, a missing LONG SLO, installing a LONG envelope, a failed rung ending the input limit.
"""
from __future__ import annotations

import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import qualification as Q  # noqa: E402
from sovereign_product import qualification_harness as H  # noqa: E402

SHIPPED = json.loads((SOV_ROOT / "qualification" / "profiles.json").read_text(encoding="utf-8"))
LONG_IDS = {"llamacpp-long-dense-27b", "llamacpp-long-moe-30b-a3b"}


def _profile(doc, profile_id):
    return next(p for p in doc["profiles"] if p["id"] == profile_id)


# --- profiles -------------------------------------------------------------------------------------

def test_si_long_profiles_ship_for_both_long_models_and_never_gate_quick_deep():
    doc = Q.load_profiles(SOV_ROOT)
    long_profiles = {p["id"]: p for p in doc["profiles"] if p.get("kind") == "long"}
    assert set(long_profiles) == LONG_IDS
    long_config = json.loads((SOV_ROOT / "long_workload.json").read_text(encoding="utf-8"))
    configured = {m["model"] for m in long_config["models"]}
    assert {p["primary_model"] for p in long_profiles.values()} == configured
    for profile in long_profiles.values():
        assert Q.find_profile(doc, "llama.cpp", profile["primary_model"]) is None
    assert Q.find_profile(doc, "llama.cpp", "qwen3:14b")["id"] == "llamacpp-production-slate"


@pytest.mark.parametrize("mutate,match", [
    (lambda d: _profile(d, "llamacpp-long-dense-27b").update(backend="ollama"), "only on llama.cpp"),
    (lambda d: _profile(d, "llamacpp-long-dense-27b")["ladder"].update(input_tokens=[-1]), ">= 0"),
    (lambda d: _profile(d, "llamacpp-long-dense-27b")["ladder"].update(input_tokens=[]), "non-empty"),
    (lambda d: _profile(d, "llamacpp-long-dense-27b")["ladder"].update(input_tokens=[16, 0]),
     "ascending"),
    (lambda d: _profile(d, "llamacpp-long-dense-27b").update(kind="huge"), "kind"),
    (lambda d: d["slo"].pop("long_p95_seconds"), "long_p95_seconds"),
])
def test_si_long_malformed_profiles_fail_closed(mutate, match):
    doc = copy.deepcopy(SHIPPED)
    mutate(doc)
    with pytest.raises(Q.QualificationError, match=match):
        Q.validate_profiles(doc)


def test_si_long_slo_is_only_required_when_a_long_profile_exists():
    doc = copy.deepcopy(SHIPPED)
    doc["profiles"] = [p for p in doc["profiles"] if p.get("kind") != "long"]
    doc["slo"].pop("long_p95_seconds")
    Q.validate_profiles(doc)


# --- envelope -------------------------------------------------------------------------------------

def _results(runs, profile="llamacpp-long-moe-30b-a3b"):
    return {"schema": Q.RESULTS_SCHEMA, "profile": profile, "kind": "long",
            "started_utc": "t0", "finished_utc": "t1", "runs": runs, "repetitions": 1,
            "resources": {"peak_vram_mib": 7400}, "results_file": "r.json"}


def _run(step, status="completed", latency=600.0, shards=4, cold=False):
    run = {"scenario": "long_plan" if step == 0 else "long_input", "input_tokens": step,
           "status": status, "latency_seconds": latency, "shards": shards, "cold": cold}
    if status == "completed":
        run["chunks_per_hour"] = shards * 3600.0 / latency
    return run


def test_si_long_envelope_reports_rungs_chunks_per_hour_and_cold_vs_warm():
    runs = [_run(0, latency=900.0, cold=True), _run(32768, latency=1800.0, shards=3),
            _run(65536, latency=3600.0, shards=6)]
    env = Q.derive_envelope(_results(runs), SHIPPED)
    assert env["kind"] == "long" and env["limits"] == {}
    assert env["qualified_workflows"] == {"LONG_plan_steps": True, "LONG_input_shards": True}
    assert env["qualified_input_tokens"] == 65536
    plan, big = env["scenarios"]["long_plan"], env["scenarios"]["long_input_65536"]
    assert plan["cold_runs"] == 1 and plan["cold_latency_p50_seconds"] == 900.0
    assert big["warm_runs"] == 1 and big["shards_max"] == 6
    assert big["chunks_per_hour_p50"] == pytest.approx(6.0)
    report = Q.render_report(env, _results(runs))
    assert "LONG qualification report" in report and "long_input_65536" in report


def test_si_long_a_failed_rung_ends_the_qualified_input_size():
    runs = [_run(0), _run(32768, status="failed"), _run(65536)]
    env = Q.derive_envelope(_results(runs), SHIPPED)
    assert env["qualified_input_tokens"] == 0
    assert env["qualified_workflows"]["LONG_input_shards"] is False
    runs = [_run(0, latency=99999.0), _run(32768), _run(65536)]
    assert Q.derive_envelope(_results(runs), SHIPPED)["qualified_workflows"][
        "LONG_plan_steps"] is False, "a plan run above the LONG p95 SLO is not qualified"


def test_si_long_envelope_is_never_installed(tmp_path):
    env = Q.derive_envelope(_results([_run(0), _run(32768), _run(65536)]), SHIPPED)
    with pytest.raises(Q.QualificationError, match="never installed"):
        Q.write_envelope(tmp_path, env)
    with pytest.raises(Q.QualificationError, match="never installed"):
        Q.apply_envelope(tmp_path, env)


# --- the harness, end-to-end over HTTP against a fake product -------------------------------------

class _FakeProduct(BaseHTTPRequestHandler):
    """Just enough of the product API: sessions, LONG jobs with shard progress, self-state."""

    state: dict = {}

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        st = self.state
        if self.path == "/v1/health":
            return self._send(200, {"product_version": "t", "worker_count": 1,
                                    "routes": {"LONG": True}})
        if self.path == "/v1/self-state":
            return self._send(200, {"inference": {"llama_cpp": {
                "service": "llama.cpp", "loaded_models": sorted(st["loaded"])}}})
        if self.path.startswith("/v1/jobs/"):
            job_id = self.path.rsplit("/", 1)[1]
            polls = st["polls"][job_id] = st["polls"].get(job_id, 0) + 1
            if polls == 1:
                return self._send(200, {"job_id": job_id, "status": "running",
                                        "progress": {"current": 1, "total": 3, "percent": 33}})
            st["loaded"].add(st["model"])
            return self._send(200, {"job_id": job_id, "status": "completed",
                                    "progress": {"percent": 100, "stage": "completed"},
                                    "metrics": {"tokens": None, "elapsed_seconds": 1.0}})
        return self._send(404, {"error": "no route"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v1/sessions":
            return self._send(201, {"session": {"session_id": "s1"}})
        if self.path == "/v1/message":
            self.state["messages"].append(body)
            job_id = f"j{len(self.state['messages'])}"
            return self._send(202, {"job_id": job_id, "status": "queued"})
        return self._send(404, {"error": "no route"})


@pytest.fixture
def fake_product():
    _FakeProduct.state = {"loaded": set(), "polls": {}, "messages": [], "model": None}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeProduct)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _FakeProduct.state
    finally:
        server.shutdown()
        server.server_close()


def test_si_long_harness_drives_every_rung_through_the_product(fake_product, tmp_path):
    base_url, state = fake_product
    profile = copy.deepcopy(_profile(SHIPPED, "llamacpp-long-moe-30b-a3b"))
    state["model"] = profile["primary_model"]
    inbox = tmp_path / "state" / "long_inputs"
    results = H.run_long_qualification(profile, base_url=base_url, inbox_dir=inbox,
                                       poll=0.01, log=lambda m: None)
    runs = results["runs"]
    assert [r["input_tokens"] for r in runs] == [0, 32768, 65536]
    assert all(r["status"] == "completed" and r["shards"] == 3 for r in runs)
    assert all(r["chunks_per_hour"] > 0 for r in runs)
    assert [r["cold"] for r in runs] == [True, False, False]
    texts = [m["input"] for m in state["messages"]]
    assert all(m["route_override"] == "LONG" for m in state["messages"])
    assert all(t.startswith("@model: qwen3:30b-a3b\n") for t in texts)
    assert "---" not in texts[0], "rung 0 is objective-only (plan steps)"
    assert texts[2].endswith("---\n@input: qualification-65536.txt")
    material = (inbox / "qualification-65536.txt").read_text(encoding="utf-8")
    assert len(material) >= 65536 * H.CHARS_PER_TOKEN * 0.9
    assert len(texts[2]) < 1024, "big inputs go through the inbox, not the message"
    env = Q.derive_envelope(results, SHIPPED)
    assert env["qualified_input_tokens"] == 65536
