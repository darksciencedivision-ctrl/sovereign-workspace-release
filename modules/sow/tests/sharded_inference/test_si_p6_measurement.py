"""P6 (O5, O6): the LONG run reports where its time went, and the KV cache type is a config option.

O5: how much of a run is /tokenize and /apply-template? The client now counts calls and seconds
per endpoint and the LONG telemetry reports the sizing time and the tokenizer share, so a real
run answers it. O6: q4_0 quarters the KV cache (q8_0 halves it), which frees GPU layers at a long
context; ``cache_type`` per model in long_workload.json chooses it and the plan report names it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import memory_planner as MP  # noqa: E402
from sovereign_product.llama_cpp_client import LlamaCppClient  # noqa: E402

from test_si_p6_long_route import (FakeLlama, _fake_gguf, _registry_with, _root,  # noqa: E402,F401
                                   _small_root, clean_env)


def _config_with(tmp_path, **model_fields):
    doc = json.loads((SOV_ROOT / LW.CONFIG_FILE).read_text(encoding="utf-8"))
    doc["models"][0].update(model_fields)
    return _root(tmp_path, doc)


def test_the_cache_type_defaults_to_q8_0_and_can_be_chosen_per_model(clean_env, tmp_path):
    assert {m.cache_type for m in LW.load_config(SOV_ROOT).models} == {"q8_0"}
    config = LW.load_config(_config_with(tmp_path, cache_type="q4_0"))
    assert config.models[0].cache_type == "q4_0" and config.models[1].cache_type == "q8_0"


def test_an_unknown_cache_type_is_refused(clean_env, tmp_path):
    with pytest.raises(LW.LongWorkloadError, match="cache_type must be one of"):
        LW.load_config(_config_with(tmp_path, cache_type="q2_k"))


def test_the_planner_serves_the_chosen_cache_type_and_reports_it(clean_env, tmp_path):
    roots = {}
    for name, cache in (("a", "q8_0"), ("b", "q4_0")):
        registry = _registry_with("qwen3.8:27b")
        (tmp_path / name).mkdir()
        config = LW.load_config(_config_with(tmp_path / name, cache_type=cache))
        report = LW.apply_hybrid_plans(registry, config, vram_bytes=int(5.9 * MP.GIB),
                                       reader=_fake_gguf)["qwen3.8:27b"]
        (profile,) = [p for p in registry.profiles.values() if p.model_id == "qwen3.8:27b"]
        assert report["applied"] and report["cache_type"] == cache and profile.cache_type == cache
        roots[cache] = report
    # a quarter-size cache leaves room for at least as many GPU layers
    assert roots["q4_0"]["n_gpu_layers"] >= roots["q8_0"]["n_gpu_layers"]
    assert roots["q4_0"]["kv_gib"] < roots["q8_0"]["kv_gib"]


class _Session:
    def request(self, method, url, json=None, **kwargs):
        class Response:
            status_code = 200

            def json(self):
                return {"tokens": [1, 2, 3], "prompt": "x"}

            def raise_for_status(self):
                return None

            def close(self):
                pass

        return Response()


def test_the_client_counts_calls_and_seconds_per_tokenizer_endpoint():
    ticks = iter(x * 0.5 for x in range(100))
    client = LlamaCppClient("http://127.0.0.1:18080", api_key="k", session=_Session())
    import sovereign_product.llama_cpp_client as module

    real = module.time.perf_counter
    module.time.perf_counter = lambda: next(ticks)
    try:
        assert client.count_text_tokens("m", "hello") == 3
        assert client.count_text_tokens("m", "again") == 3
        assert client.count_prompt_tokens("m", [{"role": "user", "content": "hi"}]) == 3
    finally:
        module.time.perf_counter = real
    assert client.endpoint_stats["/tokenize"] == [3, 1.5]
    assert client.endpoint_stats["/apply-template"] == [1, 0.5]


class _CountingLlama(FakeLlama):
    def __init__(self):
        super().__init__(context=8192)
        self.endpoint_stats = {"/tokenize": [5, 1.0]}  # calls made before this run

    def count_text_tokens(self, model, text):
        stats = self.endpoint_stats.setdefault("/tokenize", [0, 0.0])
        stats[0] += 1
        stats[1] += 0.25
        return super().count_text_tokens(model, text)


def test_the_run_telemetry_says_where_the_time_went(clean_env, tmp_path):
    root = _small_root(tmp_path)
    client = _CountingLlama()
    material = "\n\n".join(f"Section {i}: " + "entry. " * 200 for i in range(6))
    executor = LW.LongWorkloadExecutor(root=root, evidence_dir=root / "ev", client=client,
                                       config=LW.load_config(root), exact_counting=False)
    result = executor.run("job-t", f"Describe the entries.\n---\n{material}",
                          cancel_requested=lambda: False, progress_callback=lambda e: None)
    telemetry = result["telemetry"]
    tokenizer = telemetry["tokenizer_endpoints"]["/tokenize"]
    assert tokenizer["calls"] > 0 and tokenizer["seconds"] == pytest.approx(0.25 * tokenizer["calls"])
    assert telemetry["tokenizer_seconds"] == tokenizer["seconds"]  # the earlier 5 calls excluded
    assert telemetry["plan_seconds"] >= 0 and telemetry["wall_seconds"] >= telemetry["plan_seconds"]
