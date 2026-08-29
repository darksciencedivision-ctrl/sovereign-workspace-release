"""Canonical model registry (CP-M1 G38-G43). One dump serves every selector.

Existing hard-coded lists are consumed as declared seed with discovered_by set.
Live sources (ollama tags, provider CLI probes) are merged; nothing is invented.
"""
from __future__ import annotations

import json
from typing import Any

REQUIRED_FIELDS = (
    "model_id", "family", "parameter_count", "active_parameter_count", "provider",
    "runtime", "locality", "capabilities", "advertised_context", "validated_context",
    "production_context", "validation_evidence", "artifacts", "speculative_decoding",
    "promotion_state", "discovered_by", "availability", "health",
)


class IncompatibleSelection(ValueError):
    pass


def _row(**kw: Any) -> dict[str, Any]:
    base = {
        "model_id": "unknown",
        "family": "unknown",
        "parameter_count": "unknown",
        "active_parameter_count": "unknown",
        "provider": "unknown",
        "runtime": "unknown",
        "locality": "unknown",
        "capabilities": [],
        "advertised_context": None,
        "validated_context": None,
        "production_context": None,
        "validation_evidence": None,
        "artifacts": [],
        "speculative_decoding": {
            "supported": False, "method": None, "draft_model_id": None,
            "draft_artifact_id": None, "validated": False, "evidence": None,
        },
        "promotion_state": "CANDIDATE",
        "discovered_by": "unspecified",
        "availability": "unknown",
        "health": "unknown",
    }
    base.update(kw)
    return base


def _seed_conductor() -> list[dict[str, Any]]:
    from control_plane.conductor.registry import CONDUCTOR_MODEL_REGISTRY
    rows = []
    for r in CONDUCTOR_MODEL_REGISTRY:
        rows.append(_row(
            model_id=r.model_id,
            family=r.provider_id,
            provider=r.provider_id,
            runtime="agent_runtime",
            locality="frontier",
            capabilities=["reasoning", "synthesis"] if r.conductor_capable else [],
            advertised_context=128000,
            discovered_by="seed:CONDUCTOR_MODEL_REGISTRY",
            availability="configured",
            health="unknown",
        ))
    return rows


def _seed_roster() -> list[dict[str, Any]]:
    from adapters.roster import _REASONING_MODELS, _CODER_MODELS
    rows = []
    def _art(name: str) -> list[dict[str, Any]]:
        return [{
            "format": "gguf", "quantization": "unknown", "runtime": "ollama",
            "path": "ollama-store-tag:" + name, "sha256": "unknown",
            "validated": False, "artifact_id": name,
        }]
    for name in _REASONING_MODELS:
        rows.append(_row(
            model_id=name, family="qwen", provider="ollama", runtime="ollama",
            locality="local", capabilities=["reasoning"], advertised_context=32000,
            discovered_by="seed:roster._REASONING_MODELS", availability="seed",
            validation_evidence="NOT_MEASURED(SERVICE_LAUNCH_IS_OPERATOR_OWNED)",
            artifacts=_art(name),
        ))
    for name in _CODER_MODELS:
        rows.append(_row(
            model_id=name, family="coder", provider="ollama", runtime="ollama",
            locality="local", capabilities=["coding"], advertised_context=32000,
            discovered_by="seed:roster._CODER_MODELS", availability="seed",
            validation_evidence="NOT_MEASURED(SERVICE_LAUNCH_IS_OPERATOR_OWNED)",
            artifacts=_art(name),
        ))
    return rows


def _live_ollama() -> list[dict[str, Any]]:
    from adapters.detect import ollama_models
    rows = []
    for name in ollama_models():
        rows.append(_row(
            model_id=name, family="unknown", provider="ollama", runtime="ollama",
            locality="local", capabilities=[], advertised_context=None,
            discovered_by="live:ollama /api/tags", availability="live",
            health="reachable",
            validation_evidence="NOT_MEASURED(SERVICE_LAUNCH_IS_OPERATOR_OWNED)",
            artifacts=[{
                "format": "gguf", "quantization": "unknown", "runtime": "ollama",
                "path": "ollama-store-tag:" + name, "sha256": "unknown",
                "validated": False, "artifact_id": name,
            }],
        ))
    return rows


def build_canonical_registry() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (_seed_conductor(), _live_ollama(), _seed_roster()):
        for r in src:
            mid = r["model_id"]
            if mid in seen:
                continue
            seen.add(mid)
            rows.append(r)
    return {
        "schema": "canonical_registry@1.0",
        "models": rows,
        "count": len(rows),
    }


def dump_registry() -> dict[str, Any]:
    return build_canonical_registry()


BACKEND_TAKES_MODEL = {
    "local_model": True,
    "api_model": True,
    "opencode": False,
    "powershell": False,
    "none": False,
}
BACKEND_FORBIDDEN_LOCALITY = {
    "local_model": "frontier",
}


def refuse_incompatible(model_id: str, backend: str) -> None:
    """Refuse a selection the compatibility relation forbids, before any spawn."""
    if (model_id or "").lower() in {"opencode", "llama.cpp", "llamacpp"}:
        raise IncompatibleSelection(
            f"refused: {model_id!r} is a runtime/backend, not a model_id (S-10)")
    forbidden = BACKEND_FORBIDDEN_LOCALITY.get(backend)
    if forbidden:
        reg = dump_registry()
        hit = next((r for r in reg["models"] if r["model_id"] == model_id), None)
        if hit and hit.get("locality") == forbidden:
            raise IncompatibleSelection(
                f"refused: frontier model {model_id!r} is incompatible with backend {backend}")
    if BACKEND_TAKES_MODEL.get(backend) is False and model_id:
        raise IncompatibleSelection(
            f"refused: backend {backend} takes a null model reference")


def list_for_selectors() -> list[dict[str, Any]]:
    """The single list every Conductor/worker selector must consume."""
    return dump_registry()["models"]
