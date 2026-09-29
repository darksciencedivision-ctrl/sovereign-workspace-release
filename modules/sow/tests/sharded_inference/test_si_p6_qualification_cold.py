"""P6 (O8): the qualification harness labels a start cold only when the model was not resident.

Before: on llama.cpp ``quick_cold`` was recorded cold=True unconditionally (the "first request of
the run"), so a run against a router that already held the model reported a warm start as cold,
and the r2 LONG rungs were all warm while the report could not say so. Now the harness reads the
router's resident models before the first request, records the answer per run, and keeps the
models resident at the start in the results (with a fresh stack per profile the resource
baseline is then an idle GPU).
"""
from __future__ import annotations

import sys
from pathlib import Path

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import qualification_harness as H  # noqa: E402

PROFILE = {"id": "llamacpp-test", "backend": "llama.cpp", "primary_model": "qwen3:14b",
           "ladder": {"context_tokens": [2048], "concurrency": [1], "repetitions": 1}}


class FakeProduct:
    def __init__(self, loaded):
        self.loaded = loaded
        self.submitted = 0

    def __call__(self, base_url, timeout=30.0):
        return self

    def health(self):
        return {"product_version": "t", "worker_count": 1, "deep_model_slate": {},
                "qualification": {}}

    def new_session(self, title):
        return "s"

    def submit(self, session, text, route):
        self.submitted += 1
        return 202, {"job_id": f"j{self.submitted}", "status": "completed"}

    def job(self, job_id):
        return {"status": "completed"}

    def cancel(self, job_id):
        return {}

    def _call(self, method, path, body=None):
        assert path == "/v1/self-state"
        if self.loaded is None:
            raise OSError("no state")
        return 200, {"llama": {"service": "llama.cpp", "loaded_models": self.loaded}}


def _quick_cold(monkeypatch, loaded):
    fake = FakeProduct(loaded)
    monkeypatch.setattr(H, "ProductClient", fake)
    results = H.run_qualification(PROFILE, base_url="http://127.0.0.1:1", ollama_url="",
                                  repetitions=1, include_deep=False, log=lambda m: None)
    (cold,) = [r for r in results["runs"] if r["scenario"] == "quick_cold"]
    return cold, results


def test_a_resident_model_makes_the_first_request_a_warm_start(monkeypatch):
    cold, results = _quick_cold(monkeypatch, ["qwen3:14b", "qwen3-14b"])
    assert cold["cold"] is False and "ALREADY resident" in cold["note"]
    assert results["runtime"]["models_loaded_at_start"] == ["qwen3:14b", "qwen3-14b"]


def test_a_model_the_router_does_not_hold_is_a_cold_start(monkeypatch):
    cold, results = _quick_cold(monkeypatch, ["qwen3:8b"])
    assert cold["cold"] is True and "not resident" in cold["note"]
    assert _quick_cold(monkeypatch, [])[0]["cold"] is True


def test_unknown_residency_is_not_claimed_as_cold(monkeypatch):
    cold, results = _quick_cold(monkeypatch, None)
    assert cold["cold"] is None and "not proven cold" in cold["note"]
    assert results["runtime"]["models_loaded_at_start"] is None


def test_model_is_cold_helper():
    assert H.model_is_cold(["a"], "b") is True and H.model_is_cold(["b"], "b") is False
    assert H.model_is_cold(None, "b") is None


def test_the_long_run_records_what_the_router_held_at_the_start(monkeypatch, tmp_path):
    fake = FakeProduct(["qwen3:30b-a3b"])
    monkeypatch.setattr(H, "ProductClient", fake)
    profile = {"id": "long-test", "backend": "llama.cpp", "primary_model": "qwen3:30b-a3b",
               "ladder": {"input_tokens": [0], "repetitions": 1}}
    results = H.run_long_qualification(profile, base_url="http://127.0.0.1:1", inbox_dir=tmp_path,
                                       poll=0.0, log=lambda m: None)
    assert results["runtime"]["models_loaded_at_start"] == ["qwen3:30b-a3b"]
    assert results["runs"][0]["cold"] is False
