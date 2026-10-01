"""RESEARCH: one invalid phase reply must not end (or permanently poison) a long run."""
from __future__ import annotations

import json

from test_si_research_progress import PHASE_REPLIES, _paths
from sovereign_product.research import ResearchExecutor, ResearchLimits, ResearchStatus

LIMITS = ResearchLimits(minimum_iterations=1, maximum_model_calls=12,
                        require_rejected_hypothesis=False, require_revised_hypothesis=False)


class Replies:
    """Returns the scripted texts in order and remembers every prompt."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.prompts = []

    def generate(self, model, prompt, options=None, **kwargs):
        self.prompts.append(prompt)
        return {"text": self.texts.pop(0), "latency_seconds": 0.1}


def _good(index):
    return json.dumps(PHASE_REPLIES[index])


def _run(tmp_path, model):
    return ResearchExecutor(_paths(tmp_path), model).run(
        "r-1", "Does alpha hold?", model="qwen3:14b", limits=LIMITS)


def test_an_invalid_reply_is_retried_with_the_reason_and_the_run_completes(tmp_path):
    model = Replies("this is not json", *[_good(i) for i in range(5)])
    result = _run(tmp_path, model)
    assert result.status is ResearchStatus.COMPLETED, result.reason
    assert len(model.prompts) == 6
    assert "previous_reply_rejected" not in model.prompts[0]
    assert "previous_reply_rejected" in model.prompts[1]
    assert "strict JSON object" in model.prompts[1]
    assert "previous_reply_rejected" not in model.prompts[2]  # the note ends with the phase
    assert result.resources["phase_failures"] == 1
    assert result.resources["model_calls"] == 6


def test_a_phase_that_stays_invalid_still_fails_after_two_retries(tmp_path):
    model = Replies("bad", "still bad", "worse")
    result = _run(tmp_path, model)
    assert result.status is ResearchStatus.FAILED
    assert "strict JSON object" in result.reason
    assert len(model.prompts) == 3  # the first attempt and two retries
    assert result.resources["phase_failures"] == 3


def test_resuming_a_run_that_failed_on_an_invalid_reply_calls_the_model_again(tmp_path):
    limits = ResearchLimits(minimum_iterations=1, maximum_model_calls=30,
                            require_rejected_hypothesis=False, require_revised_hypothesis=False)
    paths = _paths(tmp_path)
    first = Replies("bad", "still bad", "worse")
    failed = ResearchExecutor(paths, first).run(
        "r-1", "Does alpha hold?", model="qwen3:14b", limits=limits)
    assert failed.status is ResearchStatus.FAILED
    second = Replies(*[_good(i) for i in range(5)])
    result = ResearchExecutor(paths, second).run(
        "r-1", "Does alpha hold?", model="qwen3:14b", limits=limits)
    assert result.status is ResearchStatus.COMPLETED, result.reason
    assert len(second.prompts) == 5  # the journaled bad reply was not replayed
    assert "previous_reply_rejected" in second.prompts[0]
    assert result.resources["model_calls"] == 8


def test_retries_spend_the_model_call_budget(tmp_path):
    tight = ResearchLimits(minimum_iterations=1, maximum_model_calls=5,
                           require_rejected_hypothesis=False, require_revised_hypothesis=False)
    model = Replies("bad", *[_good(i) for i in range(5)])
    result = ResearchExecutor(_paths(tmp_path), model).run(
        "r-1", "Does alpha hold?", model="qwen3:14b", limits=tight)
    assert result.status is ResearchStatus.BUDGET_EXHAUSTED
    assert result.reason == "maximum model-call budget reached"
    assert len(model.prompts) == 5
