"""Split a model across GPU VRAM and system RAM within a hard memory budget (sharded inference P2).

Models bigger than the GPU run on llama.cpp with part of the model on the GPU and the rest in
system RAM (computed by the CPU). This planner decides that split deterministically from the model
file's real tensor sizes (``gguf_meta``) and the machine's budget, and REFUSES a plan that would
exceed the operator's RAM budget rather than letting the OS swap.

* **Dense models**: the last ``n_gpu_layers`` layers go to the GPU with their share of the KV
  cache; the rest (and their KV) stay in RAM. As many whole layers as fit after the compute reserve.
* **Mixture-of-experts models**: every layer's attention / shared weights go to the GPU
  (``n_gpu_layers`` = all) and the EXPERT weights of the first ``n_cpu_moe`` layers stay in RAM -
  only the few active experts are computed per token, so this is far faster than splitting whole
  layers. ``n_cpu_moe`` is the smallest value that fits.

Budgets are explicit (llama.cpp's own ``--fit`` is turned off) so a plan is reproducible and the RAM
cap is enforced here. KV sizes use ``gguf_meta.kv_bytes_per_token`` (only full-attention layers of
hybrid architectures carry a KV cache). Estimates are conservative; the SW-27 harness measures the
real figures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .gguf_meta import GGUFModel

GIB = 1024 ** 3
MIB = 1024 ** 2

#: Bytes per KV element for the cache types the planner offers (block-quantized sizes).
KV_TYPE_BYTES = {"f16": 2.0, "q8_0": 34 / 32, "q4_0": 18 / 32}
ALL_LAYERS = 999


class PlanRefused(ValueError):
    """No split fits the budget; the reason names the numbers."""


@dataclass(frozen=True)
class MemoryBudget:
    """What inference may use on this machine."""

    vram_bytes: int                      # usable VRAM (free, after other processes)
    ram_bytes: int = 32 * GIB            # operator decision: inference RAM cap
    vram_reserve_bytes: int = int(1.5 * GIB)   # CUDA context + compute buffers
    ram_overhead_bytes: int = 1 * GIB    # process + host compute buffers
    prompt_cache_mib: int = 2048         # llama.cpp --cache-ram (reused preambles across shards)

    def __post_init__(self) -> None:
        for name in ("vram_bytes", "ram_bytes", "vram_reserve_bytes", "ram_overhead_bytes",
                     "prompt_cache_mib"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class ServingPlan:
    model_path: str
    architecture: str
    moe: bool
    context: int
    n_gpu_layers: int
    n_cpu_moe: int | None
    cache_type: str
    flash_attn: str
    cache_ram_mib: int
    fit: str
    est_vram_bytes: int
    est_ram_bytes: int
    kv_bytes: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["est_vram_gib"] = round(self.est_vram_bytes / GIB, 2)
        data["est_ram_gib"] = round(self.est_ram_bytes / GIB, 2)
        data["kv_gib"] = round(self.kv_bytes / GIB, 2)
        return data

    def preset_lines(self) -> list[str]:
        """The llama.cpp router preset keys that realize this plan."""
        lines = [
            f"ctx-size = {self.context}",
            f"n-gpu-layers = {self.n_gpu_layers}",
            f"flash-attn = {self.flash_attn}",
            f"cache-type-k = {self.cache_type}",
            f"cache-type-v = {self.cache_type}",
            f"cache-ram = {self.cache_ram_mib}",
            f"fit = {self.fit}",
        ]
        if self.n_cpu_moe is not None:
            lines.append(f"n-cpu-moe = {self.n_cpu_moe}")
        return lines


def plan_serving(model: GGUFModel, *, context: int, budget: MemoryBudget,
                 cache_type: str = "q8_0") -> ServingPlan:
    """The split that fits ``budget`` at ``context`` tokens, or PlanRefused."""
    if cache_type not in KV_TYPE_BYTES:
        raise ValueError(f"cache_type must be one of {sorted(KV_TYPE_BYTES)}")
    if not isinstance(context, int) or context < 4096:
        raise ValueError("context must be an integer of at least 4096")
    if model.context_length and context > model.context_length:
        raise PlanRefused(f"context {context} exceeds the model's trained context "
                          f"{model.context_length}")
    layers = model.block_count
    if layers <= 0 or not model.tensors:
        raise PlanRefused("model file declares no layers/tensors; cannot plan")

    kv_total = model.kv_bytes_per_token(KV_TYPE_BYTES[cache_type]) * context
    kv_per_layer = kv_total / layers  # attention layers are interleaved; spread evenly
    vram_room = budget.vram_bytes - budget.vram_reserve_bytes
    ram_fixed = budget.ram_overhead_bytes + budget.prompt_cache_mib * MIB
    notes: list[str] = []
    if vram_room <= 0:
        raise PlanRefused(f"usable VRAM {budget.vram_bytes / GIB:.1f} GiB is below the "
                          f"{budget.vram_reserve_bytes / GIB:.1f} GiB compute reserve")

    if model.is_moe:
        # Attention/shared weights of every layer + output on the GPU; experts of the first N
        # layers in RAM. Token embeddings are counted on the CPU side (llama.cpp keeps them there).
        dense_gpu = sum(model.layer_bytes(i, experts=False) for i in range(layers))
        dense_gpu += model.non_layer_bytes // 2
        expert_per_layer = [model.layer_bytes(i, experts=True) for i in range(layers)]
        for n_cpu in range(0, layers + 1):
            gpu = dense_gpu + sum(expert_per_layer[n_cpu:]) + kv_total
            if gpu <= vram_room:
                break
        else:
            raise PlanRefused(
                f"even with every expert in RAM, attention weights + KV "
                f"({(dense_gpu + kv_total) / GIB:.1f} GiB) exceed usable VRAM "
                f"{vram_room / GIB:.1f} GiB; lower the context or use q4_0 KV")
        est_vram = gpu + budget.vram_reserve_bytes
        est_ram = sum(expert_per_layer[:n_cpu]) + (model.non_layer_bytes - model.non_layer_bytes // 2) + ram_fixed
        plan_ngl, plan_cpu_moe = ALL_LAYERS, n_cpu
        notes.append(f"experts of the first {n_cpu} of {layers} layers in RAM")
    else:
        per_layer = [model.layer_bytes(i) + kv_per_layer for i in range(layers)]
        output_gpu = model.non_layer_bytes // 2
        ngl, used = 0, output_gpu
        # llama.cpp offloads the LAST layers first; fill from the top down.
        for i in reversed(range(layers)):
            if used + per_layer[i] > vram_room:
                break
            used += per_layer[i]
            ngl += 1
        if ngl == 0:
            used = 0
            notes.append("no layer fits the GPU; CPU-only")
        cpu_layers = layers - ngl
        est_vram = used + budget.vram_reserve_bytes
        est_ram = (sum(model.layer_bytes(i) for i in range(cpu_layers))
                   + int(kv_per_layer * cpu_layers)
                   + (model.non_layer_bytes - (output_gpu if ngl else 0))
                   + ram_fixed)
        plan_ngl, plan_cpu_moe = (ALL_LAYERS if ngl == layers else ngl), None
        notes.append(f"{ngl} of {layers} layers on the GPU")

    if est_ram > budget.ram_bytes:
        raise PlanRefused(
            f"plan needs ~{est_ram / GIB:.1f} GiB RAM, over the {budget.ram_bytes / GIB:.0f} GiB "
            f"inference budget (context {context}, KV {cache_type}); lower the context or KV type")
    return ServingPlan(
        model_path=model.path, architecture=model.architecture, moe=model.is_moe,
        context=context, n_gpu_layers=plan_ngl, n_cpu_moe=plan_cpu_moe, cache_type=cache_type,
        flash_attn="on", cache_ram_mib=budget.prompt_cache_mib, fit="off",
        est_vram_bytes=int(est_vram), est_ram_bytes=int(est_ram), kv_bytes=int(kv_total),
        notes=tuple(notes))


def detect_free_vram_bytes() -> int | None:
    """Free VRAM on GPU 0 via nvidia-smi, or None when unavailable."""
    import shutil
    import subprocess

    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return int(float(out.splitlines()[0])) * MIB
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None
