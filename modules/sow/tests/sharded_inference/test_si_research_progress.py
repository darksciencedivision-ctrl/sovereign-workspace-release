"""P2: a RESEARCH job shows progress while it runs, not "1%" for the whole run.

Before: the executor's progress events carried no percent, so the job's progress callback read
each one as 0% and the store refused it ("progress percent cannot regress" against the 1% the
worker sets at the start); the job showed 1% until it ended, which on a CPU-bound model is over
an hour. Now every event names a stage and a detail and carries a percent that only grows.
"""
from __future__ import annotations

import inspect
import json
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product.paths import ROOT_MARKER, ROOT_MARKER_CONTENT, ProductPaths  # noqa: E402
from sovereign_product.research import ResearchExecutor, ResearchLimits  # noqa: E402
from sovereign_product.server import ProductService  # noqa: E402
from sovereign_product.store import SovereignStore  # noqa: E402

PHASE_REPLIES = [
    {"testable_components": ["alpha holds", "beta holds"], "rationale": "r",
     "falsifiers": ["f"], "assumptions": []},
    {"evidence_assessment": "a", "analysis_plan": ["p"],
     "hypothesis_component_classifications": {
         "component_01": "supported", "component_02": "unsupported"}},
    {"challenge": "c", "severity": "low"},
    {"decision": "revise", "reason": "r", "revised_hypothesis": "alpha holds"},
    {"objective_adherence": "o", "synthesis": "s", "recommendations": ["r"],
     "confidence": "low"},
]


class ScriptedModel:
    """Answers the five phases of a one-iteration run in order."""

    def __init__(self):
        self.calls = 0

    def generate(self, model, prompt, options=None, **kwargs):
        reply = PHASE_REPLIES[self.calls]
        self.calls += 1
        return {"text": json.dumps(reply), "latency_seconds": 0.1}


def _paths(tmp_path):
    root = tmp_path / "root"
    (root / "state").mkdir(parents=True)
    (root / ROOT_MARKER).write_text(ROOT_MARKER_CONTENT, encoding="utf-8")
    return ProductPaths(root=root, state_dir=root / "state", db_path=root / "state" / "s.db",
                        evidence_dir=root / "evidence")


LIMITS = ResearchLimits(minimum_iterations=1, maximum_model_calls=5,
                        require_rejected_hypothesis=False, require_revised_hypothesis=False)


def _run(tmp_path, progress):
    executor = ResearchExecutor(_paths(tmp_path), ScriptedModel())
    return executor.run("r-1", "Does alpha hold?", model="qwen3:14b", limits=LIMITS,
                        progress_callback=progress)


def test_every_event_names_its_stage_and_the_percent_only_grows(tmp_path):
    events: list = []
    result = _run(tmp_path, events.append)
    assert result.completed, result
    assert len(events) > 5  # more than the one update per iteration
    percents = [e["percent"] for e in events]
    assert all(isinstance(p, (int, float)) and 1 <= p <= 100 for p in percents), percents
    assert percents == sorted(percents), percents
    assert len(set(percents)) > 5
    assert percents[-1] == 100 and percents[-2] < 100
    assert all(e["stage"] and e["detail"] for e in events)
    assert {"hypothesis_generation", "adversarial_challenge", "final_synthesis"} <= {
        e["stage"] for e in events}


def test_a_running_job_shows_the_progress_through_the_service(tmp_path):
    store = SovereignStore(tmp_path / "state.db")
    job_id = store.create_job(store.create_session()["session_id"], "RESEARCH", "q")["job_id"]
    store.transition_job(job_id, "running", expected_status="queued", worker_id="w")
    store.update_job_progress(job_id, {"percent": 1, "stage": "running"})
    service = SimpleNamespace(store=store)
    service._progress_callback = types.MethodType(
        inspect.getattr_static(ProductService, "_progress_callback"), service)
    callback = service._progress_callback(job_id)
    seen: list = []

    def relay(event):
        callback(event)
        progress = store.get_job(job_id)["progress"]
        seen.append((progress["percent"], progress["stage"]))

    _run(tmp_path, relay)
    stages = [stage for percent, stage in seen]
    assert len(set(percent for percent, stage in seen)) > 5, seen
    assert "hypothesis_generation" in stages and "final_synthesis" in stages


# --- H-2: the thinking switch for the research phases (an option, off by default) ----------------

class ThinkRecorder(ScriptedModel):
    def __init__(self):
        super().__init__()
        self.thinks = []

    def generate(self, model, prompt, options=None, **kwargs):
        self.thinks.append(kwargs.get("think", "not passed"))
        return super().generate(model, prompt, options, **kwargs)


def _thinks(tmp_path, **kwargs):
    model = ThinkRecorder()
    result = ResearchExecutor(_paths(tmp_path), model, **kwargs).run(
        "r-1", "Does alpha hold?", model="qwen3:14b", limits=LIMITS)
    assert result.completed
    return model.thinks


def test_research_leaves_the_models_thinking_alone_unless_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("SOVEREIGN_RESEARCH_THINK", raising=False)
    assert set(_thinks(tmp_path)) == {"not passed"}


def test_research_can_run_its_phases_without_thinking(tmp_path, monkeypatch):
    monkeypatch.delenv("SOVEREIGN_RESEARCH_THINK", raising=False)
    assert set(_thinks(tmp_path / "a", think=False)) == {False}
    monkeypatch.setenv("SOVEREIGN_RESEARCH_THINK", "off")
    assert set(_thinks(tmp_path / "b")) == {False}
    monkeypatch.setenv("SOVEREIGN_RESEARCH_THINK", "on")
    assert set(_thinks(tmp_path / "c")) == {True}
    monkeypatch.setenv("SOVEREIGN_RESEARCH_THINK", "maybe")  # not a switch: ignored
    assert set(_thinks(tmp_path / "d")) == {"not passed"}
