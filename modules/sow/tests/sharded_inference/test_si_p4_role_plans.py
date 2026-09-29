"""P4 (D7): the multi-model research system's models are served with planned GPU/RAM splits.

Before: the router served qwen3:14b / qwen3:32b / qwen3:8b / qwen2.5:14b-instruct with fixed
default profiles (8 GPU layers, f16 KV cache; 16 for the 8B), about 4 tokens/s for the 14B
because most of the GPU sat idle. Now the supervisor plans each one like a LONG model against
the free VRAM, at the context the product requests, within the operator's RAM budget. A model
that cannot be planned keeps its default profile and the report says why; the LONG models'
plans are never touched; /v1/health reports how each model is served.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import gguf_meta as G  # noqa: E402
from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import memory_planner as MP  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product import role_plans as RP  # noqa: E402
from sovereign_product import runtime_registry as RR  # noqa: E402
from sovereign_product.runtime_registry import (  # noqa: E402
    SERVING_SLOTS, build_production_registry, context_resolution)
from sovereign_product.runtime_supervisor import LlamaCppSupervisor, SupervisorConfig  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402

from test_si_p6_long_route import _root, clean_env  # noqa: E402,F401

MANIFEST = {"MODELS": {
    "PRIMARY_REASONER": "qwen3:14b", "ADVERSARIAL_CHALLENGER": "qwen3:32b",
    "CRITIC": "qwen3:8b", "SYNTHESIZER": "qwen2.5:14b-instruct",
    "EMBEDDING_MODEL": "nomic-embed-text:latest"}}
FREE_VRAM = int(5.9 * MP.GIB)


@pytest.fixture(autouse=True)
def _no_blob_hashing(monkeypatch):
    """Building the production registry would SHA-256 every multi-GB model blob it finds."""
    monkeypatch.setattr(RR, "_verify_blob_digest", lambda path, digest: True)


def _fake_gguf(path):
    """A 40-layer dense model of 300 MiB per layer (bigger than the GPU), trained to 40960."""
    tensors = [G.TensorInfo(f"blk.{i}.w", i * 300 * MP.MIB, 300 * MP.MIB, i, False)
               for i in range(40)]
    meta = {"general.architecture": "qwen3", "qwen3.block_count": 40,
            "qwen3.context_length": 40960, "qwen3.attention.head_count_kv": 8,
            "qwen3.attention.head_count": 40, "qwen3.embedding_length": 5120,
            "qwen3.attention.key_length": 128}
    return G.GGUFModel(path=path, file_size=40 * 300 * MP.MIB, version=3, metadata=meta,
                       tensors=tensors)


def _plan(registry=None, *, vram=FREE_VRAM, ram_gib=32, already=frozenset(), manifest=MANIFEST):
    registry = registry if registry is not None else build_production_registry()
    report = RP.apply_role_plans(registry, manifest, vram_bytes=vram, ram_budget_gib=ram_gib,
                                 prompt_cache_mib=2048, already_planned=already,
                                 reader=_fake_gguf)
    return registry, report


def _profile(registry, model):
    (profile,) = [p for p in registry.profiles.values() if p.model_id == model]
    return profile


def test_the_role_models_are_the_manifest_chat_models():
    assert RP.role_model_names(MANIFEST) == [
        "qwen3:14b", "qwen3:32b", "qwen3:8b", "qwen2.5:14b-instruct"]
    assert RP.role_model_names({"MODELS": {"A": "m", "B": "m", "C": " "}}) == ["m"]
    assert RP.role_model_names({}) == []


def test_each_role_model_gets_more_gpu_layers_at_the_context_the_product_requests():
    default = build_production_registry()
    registry, report = _plan(build_production_registry())
    for model in RP.role_model_names(MANIFEST):
        assert report[model]["applied"] is True, report[model]
        profile = _profile(registry, model)
        cap = context_resolution(model)["effective_cap"]
        assert profile.context_configured == cap  # never below what a request may ask for
        assert profile.cache_type == "q8_0" and profile.flash_attn == "on"
        assert profile.fit == "off"
        if _profile(default, model).n_gpu_layers == 8:  # the fixed slot of the 14B/32B models
            assert profile.n_gpu_layers > 8, model
        assert profile.thinking_policy == _profile(default, model).thinking_policy
    assert _profile(registry, "qwen3:14b").n_gpu_layers > 8  # the fixed slot it replaces


def test_the_embedding_model_and_the_role_mappings_are_handled():
    default = build_production_registry()
    registry, report = _plan(build_production_registry())
    assert "nomic-embed-text:latest" not in report
    assert _profile(registry, "nomic-embed-text:latest") == _profile(
        default, "nomic-embed-text:latest")
    primary = registry.roles["PRIMARY_REASONER"]
    assert primary.profile_id == _profile(registry, "qwen3:14b").profile_id
    assert primary.profile_id in registry.profiles


def test_the_router_preset_carries_the_split_and_the_model_alias():
    registry, _ = _plan(build_production_registry())
    supervisor = LlamaCppSupervisor(SupervisorConfig(executable="x", work_dir="."), registry)
    preset = supervisor.render_preset()
    profile = _profile(registry, "qwen3:14b")
    section = preset.split(f"[{profile.engine_id}]")[1].split("\n\n")[0]
    assert f"n-gpu-layers = {profile.n_gpu_layers}" in section
    assert "cache-type-k = q8_0" in section and "flash-attn = on" in section
    assert "alias = qwen3:14b" in section  # the router still answers to the product's name


def test_an_unplannable_model_keeps_its_default_profile_and_says_why():
    default = build_production_registry()
    registry, report = _plan(build_production_registry(), ram_gib=4)
    for model in RP.role_model_names(MANIFEST):
        assert report[model]["applied"] is False
        assert "inference budget" in report[model]["reason"]
        assert _profile(registry, model) == _profile(default, model)
    _, unknown = _plan(build_production_registry(), vram=None)
    assert all(r["applied"] is False and "VRAM unknown" in r["reason"] for r in unknown.values())
    _, missing = _plan(build_production_registry(),
                       manifest={"MODELS": {"PRIMARY_REASONER": "no-such:model"}})
    assert missing == {"no-such:model": {"applied": False, "reason": "model not installed"}}


def test_a_model_the_long_route_plans_is_left_to_it():
    registry = build_production_registry()
    before = _profile(registry, "qwen3:14b")
    _, report = _plan(registry, already=frozenset({"qwen3:14b"}))
    assert "qwen3:14b" not in report and _profile(registry, "qwen3:14b") == before


def test_the_long_plans_do_not_change_when_role_plans_are_applied():
    config = LW.load_config(SOV_ROOT)
    registry = build_production_registry()
    long_only = LW.apply_hybrid_plans(registry, config, vram_bytes=FREE_VRAM, reader=_fake_gguf)
    long_profiles = {m.model: _profile(registry, m.model) for m in config.models
                     if long_only[m.model]["applied"]}
    RP.apply_role_plans(registry, MANIFEST, vram_bytes=FREE_VRAM, ram_budget_gib=32,
                        prompt_cache_mib=2048,
                        already_planned=frozenset(m.model for m in config.models),
                        reader=_fake_gguf)
    for model, profile in long_profiles.items():
        assert _profile(registry, model) == profile


def test_default_slot_contexts_still_bound_what_the_planner_may_serve():
    for model in RP.role_model_names(MANIFEST):
        assert context_resolution(model)["effective_cap"] <= SERVING_SLOTS[model]["ctx"]


# --- health ---------------------------------------------------------------------------------------

def _write_plans(root: Path, plans: dict) -> None:
    service = P.resolve_runtime_dir(root) / "llamacpp_supervisor"
    service.mkdir(parents=True, exist_ok=True)
    (service / "hybrid_plans.json").write_text(json.dumps(plans), encoding="utf-8")


def _health_view(root):
    return ProductService.role_models(SimpleNamespace(root=root, _manifest=lambda: MANIFEST))


def test_health_reports_how_each_role_model_is_served(clean_env, tmp_path):
    root = _root(tmp_path)
    view = _health_view(root)
    assert {m["status"] for m in view["models"]} == {"unknown"} and view["status"] == "ready"

    _write_plans(root, {
        "qwen3:14b": {"applied": True, "context": 40960, "n_gpu_layers": 13},
        "qwen3:32b": {"applied": False, "reason": "RAM budget"},
        "qwen3:8b": {"applied": True, "context": 16384, "n_gpu_layers": 26}})
    view = _health_view(root)
    by_model = {m["model"]: m for m in view["models"]}
    assert by_model["qwen3:14b"] == {"model": "qwen3:14b", "status": "ready", "reason": None,
                                     "n_gpu_layers": 13, "context": 40960}
    assert by_model["qwen3:32b"]["status"] == "degraded"
    assert "slower default profile: RAM budget" in by_model["qwen3:32b"]["reason"]
    assert by_model["qwen2.5:14b-instruct"]["status"] == "unknown"
    assert view["status"] == "degraded" and "qwen3:32b" in view["detail"]


def test_health_route_carries_the_role_models_and_a_slow_model_never_turns_a_route_off():
    from sovereign_product.server import create_app

    degraded = {"models": [{"model": "qwen3:32b", "status": "degraded", "reason": "x",
                            "n_gpu_layers": None, "context": None}],
                "status": "degraded", "detail": "qwen3:32b: x"}
    service = SimpleNamespace(
        store=SimpleNamespace(quick_check=lambda: None), _manifest=lambda: {},
        root=Path("."), deep_executor=lambda: None, workers_ready=lambda: True,
        _self_state=lambda: (_ for _ in ()).throw(RuntimeError("no live state")) or None,
        research_executor=object(), research_unavailable_reason=None,
        qualification=lambda: {"verdict": "accepted", "reasons": []}, _workers=[],
        long_route_ready=lambda: True, long_models=lambda: {"models": []},
        long_active_job=lambda: None, role_models=lambda: degraded)
    body = create_app(service=service).test_client().get("/v1/health").get_json()
    assert body["role_models"] == degraded
    assert body["routes"]["QUICK"] == body["routes"]["DEEP"] == body["routes"]["RESEARCH"]


def test_the_supervisor_writes_one_plan_report_for_the_long_and_the_role_models(
        clean_env, tmp_path, monkeypatch):
    from sovereign_product import supervisor_service as SS

    root = _root(tmp_path)
    (root / "SYSTEM_MANIFEST.json").write_bytes((SOV_ROOT / "SYSTEM_MANIFEST.json").read_bytes())
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(SS, "DEFAULT_EXE", exe)
    monkeypatch.setattr(SS, "_verify_binary", lambda path: None)
    monkeypatch.setattr(SS, "build_operational_registry",
                        lambda runtime=None: build_production_registry(runtime=runtime))
    monkeypatch.setattr(MP, "detect_free_vram_bytes", lambda: FREE_VRAM)
    SS.build_supervisor(root, port=18999, api_key="k")
    report = json.loads((SS.service_dir(root) / "hybrid_plans.json").read_text(encoding="utf-8"))
    assert {"qwen3.8:27b", "qwen3:30b-a3b"} <= set(report)          # the LONG models
    assert set(RP.role_model_names(MANIFEST)) <= set(report)        # and the role models
    assert all("applied" in entry for entry in report.values())
