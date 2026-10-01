"""GPU/RAM plans for the multi-model research system's models (product completion P4, D7).

QUICK, CONTINUITY, DEEP and RESEARCH run the models named in SYSTEM_MANIFEST ``MODELS`` (the
embedding model aside). The llama.cpp router used to serve them with a fixed default profile (8
GPU layers, f16 KV cache), which left most of the GPU idle and ran a 14B model at about 4
tokens/s. The supervisor now plans each one like a LONG model: as many layers on the GPU as fit
the VRAM free at start (the operator frees VRAM for gaming by stopping the app), the KV cache
quantized, all within the operator's RAM budget. The context each model is served at stays the
one the product requests (``context_resolution``), so no request outgrows its window.

The router keeps one model resident, so every model is planned against the whole free VRAM.
The LONG models are planned first, by ``long_workload.apply_hybrid_plans``, and are never
replanned here.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .gguf_meta import read_gguf
from .long_workload import plan_model
from .memory_planner import GIB, MemoryBudget
from .runtime_registry import RuntimeRegistry, context_resolution

_NOT_SERVED_ROLES = ("EMBEDDING_MODEL",)


def role_model_names(manifest: Mapping[str, Any]) -> list[str]:
    """The distinct chat models the manifest assigns to roles, in role order."""
    models = manifest.get("MODELS")
    names: list[str] = []
    if isinstance(models, Mapping):
        for role, name in models.items():
            if role in _NOT_SERVED_ROLES or not isinstance(name, str) or not name.strip():
                continue
            if name.strip() not in names:
                names.append(name.strip())
    return names


def apply_role_plans(registry: RuntimeRegistry, manifest: Mapping[str, Any], *,
                     vram_bytes: int | None, ram_budget_gib: int, prompt_cache_mib: int,
                     already_planned: frozenset[str] = frozenset(),
                     reader: Callable[[str], Any] = read_gguf) -> dict[str, dict[str, Any]]:
    """Serve each role model with its planned split. Returns a per-model report.

    A model that is not installed, whose file cannot be read, or whose plan is refused keeps its
    default profile, which still serves it (slower); the reason is reported. Models in
    ``already_planned`` (the LONG models) are skipped.
    """
    names = [n for n in role_model_names(manifest) if n not in already_planned]
    if vram_bytes is None:
        return {n: {"applied": False, "reason": "free VRAM unknown (no nvidia-smi)"}
                for n in names}
    budget = MemoryBudget(vram_bytes=int(vram_bytes), ram_bytes=ram_budget_gib * GIB,
                          prompt_cache_mib=prompt_cache_mib)
    report: dict[str, dict[str, Any]] = {}
    for name in names:
        profiles = [p for p in registry.profiles.values() if p.model_id == name]
        if not profiles:
            report[name] = {"applied": False, "reason": "model not installed"}
            continue
        if profiles[0].embeddings:
            continue
        context = context_resolution(name).get("effective_cap")
        if isinstance(context, bool) or not isinstance(context, int) or context < 4096:
            report[name] = {"applied": False,
                            "reason": "no enforceable context cap for this model"}
            continue
        report[name] = plan_model(registry, name, context, budget, reader=reader)
    return report


def role_model_status(reports: Mapping[str, Any] | None, model: str) -> tuple[str, str | None]:
    """``(status, reason)`` of a role model from the supervisor's plan report.

    ``degraded`` when its plan was refused (it is then served by the slower default profile),
    ``unknown`` when the supervisor reported nothing for it, ``ready`` otherwise.
    """
    if reports is None:
        return "unknown", "no plan report from the supervisor (has it started?)"
    report = reports.get(model)
    if not isinstance(report, Mapping):
        return "unknown", "the supervisor's plan report has no entry for this model"
    if report.get("applied") is False:
        return "degraded", (f"served with the slower default profile: "
                            f"{report.get('reason') or 'no reason recorded'}")
    return "ready", None
