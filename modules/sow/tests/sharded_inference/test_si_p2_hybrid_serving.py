"""Sharded inference P2: split big models across GPU VRAM and system RAM within a hard budget.

Components: a stdlib GGUF header reader (real layer/tensor sizes without loading weights), a
deterministic memory planner (dense: whole layers on the GPU; MoE: every layer on the GPU with the
experts of the first N layers in RAM), serving-profile fields for the plan, and the llama.cpp router
preset lines that realize it. The planner REFUSES a plan over the operator's 32 GB RAM budget.

Verified live on the operator's RTX 5060 Ti (8 GB) with llama.cpp b11160 (see the P2 commit):
qwen3.8:27b at ctx 131072 -> 16/65 layers on GPU, 7.07 GiB VRAM / 15.9 GiB RAM measured;
qwen3:30b-a3b at ctx 32768 -> experts of 40/48 layers in RAM, 55 tok/s prompt, 6.9 tok/s generation.
"""
from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import gguf_meta as G  # noqa: E402
from sovereign_product import memory_planner as MP  # noqa: E402
from sovereign_product.runtime_registry import (  # noqa: E402
    RegistryError, RuntimeRegistry, ServingProfile, hybrid_profile)
from sovereign_product.runtime_supervisor import LlamaCppSupervisor, SupervisorConfig  # noqa: E402

GIB, MIB = MP.GIB, MP.MIB


# --- a real (tiny) GGUF file ------------------------------------------------------------------------

def _gguf_string(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _write_gguf(path: Path, metadata: dict, tensors: list[tuple[str, int]]) -> None:
    """tensors: (name, byte size). Writes a valid v3 header with aligned data offsets."""
    body = b""
    for key, value in metadata.items():
        body += _gguf_string(key)
        if isinstance(value, str):
            body += struct.pack("<I", 8) + _gguf_string(value)
        elif isinstance(value, list):
            body += struct.pack("<I", 9) + struct.pack("<I", 4) + struct.pack("<Q", len(value))
            body += b"".join(struct.pack("<I", v) for v in value)
        else:
            body += struct.pack("<I", 4) + struct.pack("<I", value)
    offset, infos = 0, b""
    for name, size in tensors:
        infos += _gguf_string(name) + struct.pack("<I", 1) + struct.pack("<Q", size)
        infos += struct.pack("<I", 0) + struct.pack("<Q", offset)
        offset += (size + 31) // 32 * 32
    header = b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", len(tensors))
    header += struct.pack("<Q", len(metadata)) + body + infos
    header += b"\0" * ((32 - len(header) % 32) % 32)
    path.write_bytes(header + b"\0" * offset)


def test_si_p2_gguf_reader_gets_shape_and_real_tensor_sizes(tmp_path):
    meta = {"general.architecture": "llama", "llama.block_count": 2,
            "llama.context_length": 8192, "llama.embedding_length": 64,
            "llama.attention.head_count": 8, "llama.attention.head_count_kv": 2,
            "tokenizer.ggml.token_type": [1, 2, 3]}
    tensors = [("token_embd.weight", 4096), ("blk.0.attn_q.weight", 1000),
               ("blk.0.ffn_up.weight", 3000), ("blk.1.attn_q.weight", 1000),
               ("blk.1.ffn_up.weight", 3000), ("output.weight", 4096)]
    path = tmp_path / "tiny.gguf"
    _write_gguf(path, meta, tensors)
    model = G.read_gguf(path)
    assert model.architecture == "llama" and model.block_count == 2
    assert model.context_length == 8192
    # sizes come from offsets (aligned to 32), never from a quant-type table
    assert model.layer_bytes(0) == 1024 + 3008 and model.layer_bytes(1) == 1024 + 3008
    assert model.non_layer_bytes == 4096 + 4096
    # KV per token: 2 layers * 2 kv heads * (8 + 8) head dim * 2 bytes
    assert model.kv_bytes_per_token(2) == 2 * 2 * 16 * 2
    assert model.metadata["tokenizer.ggml.token_type"] is None  # vocab arrays are skipped


@pytest.mark.parametrize("content", [b"NOPE" + b"\0" * 64, b"GGUF" + struct.pack("<I", 1), b"GG"])
def test_si_p2_not_a_gguf_file_fails_closed(tmp_path, content):
    path = tmp_path / "bad.gguf"
    path.write_bytes(content)
    with pytest.raises(G.GGUFError):
        G.read_gguf(path)


# --- the planner ------------------------------------------------------------------------------------

def _model(*, layers=40, layer_bytes=400 * MIB, expert_share=0.0, kv_heads=4, key_len=128,
           interval=None, ctx=262144, arch="qwen3") -> G.GGUFModel:
    meta = {"general.architecture": arch, f"{arch}.block_count": layers,
            f"{arch}.context_length": ctx, f"{arch}.attention.head_count_kv": kv_heads,
            f"{arch}.attention.head_count": 32, f"{arch}.embedding_length": 4096,
            f"{arch}.attention.key_length": key_len}
    if interval:
        meta[f"{arch}.full_attention_interval"] = interval
    if expert_share:
        meta[f"{arch}.expert_count"] = 128
        meta[f"{arch}.expert_used_count"] = 8
    tensors, offset = [], 0
    for i in range(layers):
        experts = int(layer_bytes * expert_share)
        for name, size, is_expert in ((f"blk.{i}.attn.weight", layer_bytes - experts, False),
                                      (f"blk.{i}.ffn_up_exps.weight", experts, True)):
            if size:
                tensors.append(G.TensorInfo(name, offset, size, i, is_expert))
                offset += size
    tensors.append(G.TensorInfo("output.weight", offset, 800 * MIB, None, False))
    return G.GGUFModel(path="m.gguf", file_size=offset + 800 * MIB, version=3, metadata=meta,
                       tensors=tensors)


BUDGET = MP.MemoryBudget(vram_bytes=int(7.17 * GIB))


def test_si_p2_dense_model_puts_as_many_layers_on_the_gpu_as_fit():
    plan = MP.plan_serving(_model(), context=32768, budget=BUDGET)
    assert not plan.moe and plan.n_cpu_moe is None
    assert 0 < plan.n_gpu_layers < 40
    assert plan.est_vram_bytes <= BUDGET.vram_bytes
    assert plan.est_ram_bytes <= BUDGET.ram_bytes
    bigger_ctx = MP.plan_serving(_model(), context=131072, budget=BUDGET)
    assert bigger_ctx.n_gpu_layers <= plan.n_gpu_layers  # more KV per layer, fewer layers fit


def test_si_p2_small_dense_model_goes_entirely_on_the_gpu():
    plan = MP.plan_serving(_model(layers=8, layer_bytes=200 * MIB), context=8192, budget=BUDGET)
    assert plan.n_gpu_layers == MP.ALL_LAYERS


def test_si_p2_moe_keeps_every_layer_on_the_gpu_and_experts_in_ram():
    plan = MP.plan_serving(_model(expert_share=0.9), context=32768, budget=BUDGET)
    assert plan.moe and plan.n_gpu_layers == MP.ALL_LAYERS
    assert 0 < plan.n_cpu_moe <= 40
    assert plan.est_vram_bytes <= BUDGET.vram_bytes


def test_si_p2_hybrid_attention_models_only_pay_kv_for_attention_layers():
    full = _model(layers=64)
    hybrid = _model(layers=64, interval=4)
    assert hybrid.attention_layer_count == 16
    assert hybrid.kv_bytes_per_token(2) * 4 == full.kv_bytes_per_token(2)


def test_si_p2_plan_over_the_ram_budget_is_refused():
    huge = _model(layers=80, layer_bytes=600 * MIB)  # ~47 GiB of weights
    with pytest.raises(MP.PlanRefused, match="inference budget"):
        MP.plan_serving(huge, context=32768, budget=BUDGET)


def test_si_p2_moe_whose_attention_and_kv_cannot_fit_the_gpu_is_refused():
    with pytest.raises(MP.PlanRefused, match="exceed usable VRAM"):
        MP.plan_serving(_model(expert_share=0.5, kv_heads=16), context=262144, budget=BUDGET)


def test_si_p2_context_beyond_the_trained_window_is_refused():
    with pytest.raises(MP.PlanRefused, match="trained context"):
        MP.plan_serving(_model(ctx=32768), context=65536, budget=BUDGET)


def test_si_p2_no_usable_vram_is_refused():
    with pytest.raises(MP.PlanRefused, match="compute reserve"):
        MP.plan_serving(_model(), context=8192, budget=MP.MemoryBudget(vram_bytes=GIB))


@pytest.mark.parametrize("kwargs", [dict(context=1000), dict(context=8192, cache_type="q2")])
def test_si_p2_bad_planner_arguments(kwargs):
    with pytest.raises(ValueError):
        MP.plan_serving(_model(), budget=BUDGET, **kwargs)


# --- profile + preset -------------------------------------------------------------------------------

def test_si_p2_plan_becomes_a_profile_and_the_router_preset_realizes_it(tmp_path):
    plan = MP.plan_serving(_model(expert_share=0.9), context=32768, budget=BUDGET)
    profile = hybrid_profile("qwen3:30b-a3b", plan)
    assert profile.n_cpu_moe == plan.n_cpu_moe and profile.cache_type == "q8_0"
    supervisor = LlamaCppSupervisor(SupervisorConfig(executable="llama-server.exe",
                                                     work_dir=str(tmp_path)), RuntimeRegistry())
    preset = supervisor.render_preset({profile.profile_id: profile})
    for line in plan.preset_lines():
        if not line.startswith(("ctx-size", "n-gpu-layers")):
            assert line in preset, line
    assert f"n-gpu-layers = {MP.ALL_LAYERS}" in preset and "ctx-size = 32768" in preset
    # round-trips through the registry's JSON form
    from dataclasses import asdict
    data = json.loads(json.dumps(asdict(profile)))
    again = ServingProfile(**{**data, "stop": tuple(data["stop"])})
    assert again == profile


@pytest.mark.parametrize("field,value", [("flash_attn", "maybe"), ("cache_type", "q2"),
                                         ("fit", "yes"), ("n_cpu_moe", -1),
                                         ("cache_ram_mib", True)])
def test_si_p2_invalid_split_fields_are_refused(field, value):
    base = dict(profile_id="p", model_id="m", engine_id="p", model_path="m.gguf",
                embeddings=False, context_configured=8192, context_tested=None, n_gpu_layers=1)
    with pytest.raises(RegistryError):
        ServingProfile(**{**base, field: value})


def test_si_p2_profiles_without_split_fields_render_as_before(tmp_path):
    profile = ServingProfile(profile_id="p", model_id="m", engine_id="p", model_path="m.gguf",
                             embeddings=False, context_configured=8192, context_tested=None,
                             n_gpu_layers=8)
    preset = LlamaCppSupervisor(SupervisorConfig(executable="x.exe", work_dir=str(tmp_path)),
                                RuntimeRegistry()).render_preset({"p": profile})
    for key in ("flash-attn", "cache-type", "cache-ram", "n-cpu-moe", "fit ="):
        assert key not in preset


# --- the real 27B header (operator machine) ---------------------------------------------------------

def _ollama_blob(name: str, tag: str) -> Path | None:
    manifest = Path(os.path.expanduser(
        f"~/.ollama/models/manifests/registry.ollama.ai/library/{name}/{tag}"))
    if not manifest.is_file():
        return None
    layers = json.loads(manifest.read_text())["layers"]
    digest = [l for l in layers if l["mediaType"].endswith("model")][0]["digest"]
    blob = Path(os.path.expanduser("~/.ollama/models/blobs")) / digest.replace(":", "-")
    return blob if blob.is_file() else None


def test_si_p2_real_27b_plan_matches_the_measured_load():
    blob = _ollama_blob("qwen3.8", "27b")
    if blob is None:
        pytest.skip("qwen3.8:27b not installed on this machine")
    model = G.read_gguf(blob)
    assert model.architecture == "qwen35" and model.block_count == 65
    assert model.attention_layer_count == 16  # hybrid: 1 full-attention layer in 4
    plan = MP.plan_serving(model, context=131072, budget=BUDGET)
    assert plan.n_gpu_layers == 16  # measured live: 7.07 GiB VRAM, 15.9 GiB RAM
    assert plan.est_ram_bytes <= 32 * GIB
