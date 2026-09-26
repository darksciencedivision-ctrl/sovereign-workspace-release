"""`/v1/health` names a queued or running LONG job so the UI can warn before a model swap."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.server import ProductService, create_app  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402


def test_long_active_job_is_a_queued_or_running_long_job(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    session = store.create_session()
    quick = store.create_job(session["session_id"], "QUICK", "hello")
    store.transition_job(quick["job_id"], "running")
    service = SimpleNamespace(store=store)
    assert ProductService.long_active_job(service) is None

    queued = store.create_job(session["session_id"], "LONG", "count the notes")
    assert ProductService.long_active_job(service) == queued["job_id"]
    store.transition_job(queued["job_id"], "running")
    assert ProductService.long_active_job(service) == queued["job_id"]
    store.transition_job(queued["job_id"], "completed")
    assert ProductService.long_active_job(service) is None


def _health_service(root: Path, job_id: str | None):
    return SimpleNamespace(
        store=SimpleNamespace(quick_check=lambda: None),
        _manifest=lambda: {},
        root=root,
        deep_executor=lambda: None,
        workers_ready=lambda: True,
        _self_state=lambda: (_ for _ in ()).throw(RuntimeError("no live state")) or None,
        research_executor=object(),
        research_unavailable_reason=None,
        qualification=lambda: {"verdict": "accepted", "reasons": []},
        _workers=[],
        long_route_ready=lambda: True,
        long_models=lambda: {"default_model": "fake", "models": []},
        long_active_job=lambda: job_id,
    )


def test_health_reports_long_active_job(tmp_path):
    with_job = create_app(service=_health_service(tmp_path, "job-long-1")).test_client()
    body = with_job.get("/v1/health").get_json()
    assert body["long_active_job"] == "job-long-1"

    idle = create_app(service=_health_service(tmp_path, None)).test_client()
    assert idle.get("/v1/health").get_json()["long_active_job"] is None
