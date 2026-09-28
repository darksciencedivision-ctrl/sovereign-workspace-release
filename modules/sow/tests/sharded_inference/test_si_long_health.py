"""H2: `/v1/health` tells the truth about the LONG route's models.

Live (2026-09-26), with the GPU busy the supervisor refused the MoE's GPU/RAM plan and served it at
an 8k default; health still said LONG was ready and every run on it then failed. Now each LONG model
carries a status from the supervisor's plan report (hybrid_plans.json): a refused plan or a context
below the configured one is ``degraded`` with the reason, and LONG is unavailable when every model
is degraded. Failure injection: refused plan, short context, missing report, missing entry.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product import paths as P  # noqa: E402
from sovereign_product.server import ProductService, create_app  # noqa: E402

from test_si_p6_long_route import _root, clean_env  # noqa: E402,F401

REFUSED = {"applied": False,
           "reason": "attention weights + KV (2.3 GiB) exceed usable VRAM 0.6 GiB"}


def _write_plans(root: Path, plans: dict) -> None:
    service = P.resolve_runtime_dir(root) / "llamacpp_supervisor"
    service.mkdir(parents=True, exist_ok=True)
    (service / "hybrid_plans.json").write_text(json.dumps(plans), encoding="utf-8")


def _by_model(info: dict) -> dict:
    return {m["model"]: m for m in info["models"]}


def test_h2_a_refused_plan_marks_the_model_and_the_route_degraded(clean_env, tmp_path):
    root = _root(tmp_path)
    _write_plans(root, {"qwen3.8:27b": {"applied": True, "context": 131072},
                        "qwen3:30b-a3b": REFUSED})
    info = ProductService.long_models(SimpleNamespace(root=root))
    models = _by_model(info)
    assert models["qwen3.8:27b"]["status"] == "ready" and models["qwen3.8:27b"]["reason"] is None
    assert models["qwen3:30b-a3b"]["status"] == "degraded"
    assert "plan refused" in models["qwen3:30b-a3b"]["reason"]
    assert "usable VRAM" in models["qwen3:30b-a3b"]["reason"]
    assert info["status"] == "degraded" and "qwen3:30b-a3b: plan refused" in info["detail"]


def test_h2_a_context_below_the_configured_one_is_degraded(clean_env, tmp_path):
    root = _root(tmp_path)
    _write_plans(root, {"qwen3.8:27b": {"applied": True, "context": 65536},
                        "qwen3:30b-a3b": {"applied": True, "context": 32768}})
    models = _by_model(ProductService.long_models(SimpleNamespace(root=root)))
    assert models["qwen3.8:27b"]["status"] == "degraded"
    assert "65536-token context, below the configured 131072" in models["qwen3.8:27b"]["reason"]
    assert models["qwen3:30b-a3b"]["status"] == "ready"


def test_h2_every_model_planned_is_ready(clean_env, tmp_path):
    root = _root(tmp_path)
    _write_plans(root, {"qwen3.8:27b": {"applied": True, "context": 131072},
                        "qwen3:30b-a3b": {"applied": True, "context": 32768}})
    info = ProductService.long_models(SimpleNamespace(root=root))
    assert info["status"] == "ready" and info["detail"] is None
    assert {m["status"] for m in info["models"]} == {"ready"}


def test_h2_no_report_or_no_entry_is_unknown_not_degraded(clean_env, tmp_path):
    root = _root(tmp_path)
    info = ProductService.long_models(SimpleNamespace(root=root))
    assert {m["status"] for m in info["models"]} == {"unknown"}
    assert "no plan report" in info["models"][0]["reason"] and info["status"] == "ready"
    _write_plans(root, {"qwen3.8:27b": {"applied": True, "context": 131072}})
    models = _by_model(ProductService.long_models(SimpleNamespace(root=root)))
    assert models["qwen3:30b-a3b"]["status"] == "unknown"
    assert "no entry for this model" in models["qwen3:30b-a3b"]["reason"]


def test_h2_model_status_ignores_a_malformed_context():
    entry = LW.LongModel(model="m", context=32768)
    assert LW.model_status({"m": {"applied": True, "context": "32k"}}, entry) == ("ready", None)
    assert LW.model_status({"m": {"applied": True, "context": True}}, entry) == ("ready", None)


def _health(long_route: dict, ready: bool = True):
    service = SimpleNamespace(
        store=SimpleNamespace(quick_check=lambda: None), _manifest=lambda: {},
        root=Path("."), deep_executor=lambda: None, workers_ready=lambda: True,
        _self_state=lambda: (_ for _ in ()).throw(RuntimeError("no live state")) or None,
        research_executor=object(), research_unavailable_reason=None,
        qualification=lambda: {"verdict": "accepted", "reasons": []}, _workers=[],
        long_route_ready=lambda: ready, long_models=lambda: long_route,
        long_active_job=lambda: None)
    return create_app(service=service).test_client().get("/v1/health").get_json()


def test_h2_health_route_is_unavailable_only_when_every_model_is_degraded():
    some = {"default_model": "a", "status": "degraded", "detail": "b: plan refused: x",
            "models": [{"model": "a", "status": "ready"},
                       {"model": "b", "status": "degraded", "reason": "plan refused: x"}]}
    body = _health(some)
    assert body["routes"]["LONG"] is True
    assert body["long_route"]["status"] == "degraded"
    assert body["long_route"]["models"][1]["reason"] == "plan refused: x"

    every = {"default_model": "a", "status": "degraded", "detail": "...",
             "models": [{"model": "a", "status": "degraded", "reason": "plan refused: x"}]}
    assert _health(every)["routes"]["LONG"] is False
    assert _health(some, ready=False)["routes"]["LONG"] is False
