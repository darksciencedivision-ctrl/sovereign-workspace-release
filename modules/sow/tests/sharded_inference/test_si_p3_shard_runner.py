"""Sharded inference P3: the fresh-context shard runner (ledger, retries, checkpoints, resume).

Every shard is a new session built only from a fixed role, its instruction, the bounded LEDGER and its
own input - never the transcript. Failure injection: malformed replies, a model call that throws, a
crash mid-run, cancellation, a tampered checkpoint or stored output, a ledger that outgrows its
budget (and one that cannot be condensed), a shard that cannot fit the window, and a call budget.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import shard_runner as SR  # noqa: E402


def reply(result: str, **update) -> str:
    return json.dumps({"result": result, "ledger_update": update})


class FakeModel:
    """Scripted model: `script(prompt, call_index)` -> reply text (or raises)."""

    def __init__(self, script):
        self.script = script
        self.prompts: list[str] = []

    def generate(self, *, system, prompt, max_tokens, should_stop):
        assert system == SR.SYSTEM_ROLE
        self.prompts.append(prompt)
        return self.script(prompt, len(self.prompts))

    def count_tokens(self, text):
        return len(text) // 4


LIMITS = SR.RunLimits(context_tokens=8192, ledger_budget_tokens=1500)


def tasks(n, content="x" * 40):
    return [SR.ShardTask(task_id=f"t{i}", kind="map", instruction=f"handle part {i}",
                         content=content, max_output_tokens=256) for i in range(n)]


def test_si_p3_each_shard_is_a_fresh_session_carrying_only_the_ledger(tmp_path):
    def script(prompt, n):
        return reply(f"FULL OUTPUT {n} " + "detail " * 200 + f"TAIL-{n}",
                     add_facts=[f"fact from call {n}"])

    model = FakeModel(script)
    state = SR.ShardRunner(tmp_path, model, LIMITS).start("objective", "map", tasks(3))
    assert state.status == "completed" and len(state.completed) == 3
    second = model.prompts[1]
    assert "fact from call 1" in second            # carried through the ledger
    # Only a bounded summary of each result is carried, never the full output (transcript).
    assert "TAIL-1" not in second
    assert state.ledger.facts == ["fact from call 1", "fact from call 2", "fact from call 3"]
    runner = SR.ShardRunner(tmp_path, model, LIMITS)
    assert runner.output_of(runner.load(), "t0").startswith("FULL OUTPUT 1")


def test_si_p3_invalid_replies_are_retried_fresh_then_recorded_as_failed(tmp_path):
    def script(prompt, n):
        if "handle part 0" in prompt:
            return "not json at all"
        return reply("fine")

    model = FakeModel(script)
    state = SR.ShardRunner(tmp_path, model, LIMITS).start("o", "map", tasks(2))
    assert state.status == "failed" and "t0" in state.failed and "t1" in state.completed
    t0_prompts = [p for p in model.prompts if "handle part 0" in p]
    assert len(t0_prompts) == LIMITS.max_attempts
    assert "previous attempt at this step was rejected" in t0_prompts[1]


def test_si_p3_a_model_error_is_retried_and_can_recover(tmp_path):
    calls = {"n": 0}

    def script(prompt, n):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("backend hiccup")
        return reply("ok")

    state = SR.ShardRunner(tmp_path, FakeModel(script), LIMITS).start("o", "map", tasks(1))
    assert state.status == "completed" and state.completed["t0"]["attempts"] == 2


def test_si_p3_a_crash_resumes_without_rerunning_finished_shards(tmp_path):
    def crashing(prompt, n):
        if "handle part 2" in prompt:
            raise KeyboardInterrupt  # process dies mid-run
        return reply(f"r{n}")

    with pytest.raises(KeyboardInterrupt):
        SR.ShardRunner(tmp_path, FakeModel(crashing), LIMITS).start("o", "map", tasks(4))
    healthy = FakeModel(lambda prompt, n: reply("after restart"))
    state = SR.ShardRunner(tmp_path, healthy, LIMITS).resume()
    assert state.status == "completed" and len(state.completed) == 4
    assert all("handle part 0" not in p and "handle part 1" not in p for p in healthy.prompts)
    assert len(healthy.prompts) == 2


def test_si_p3_cancel_stops_between_shards_and_the_run_is_resumable(tmp_path):
    stop = {"now": False}

    def script(prompt, n):
        stop["now"] = True  # operator cancels while shard 1 runs
        return reply("done")

    runner = SR.ShardRunner(tmp_path, FakeModel(script), LIMITS, should_stop=lambda: stop["now"])
    state = runner.start("o", "map", tasks(3))
    assert state.status == "cancelled" and len(state.completed) == 1
    stop["now"] = False
    later = FakeModel(lambda p, n: reply("resumed"))
    state = SR.ShardRunner(tmp_path, later, LIMITS).resume()
    assert state.status == "completed" and len(later.prompts) == 2


@pytest.mark.parametrize("target", ["checkpoint", "output"])
def test_si_p3_tampering_is_detected_on_load(tmp_path, target):
    SR.ShardRunner(tmp_path, FakeModel(lambda p, n: reply("r")), LIMITS).start("o", "map",
                                                                                tasks(2))
    if target == "checkpoint":
        path = sorted((tmp_path / "checkpoints").glob("*task_completed.json"))[0]
        record = json.loads(path.read_text())
        record["payload"]["summary"] = "forged"
        path.write_text(json.dumps(record))
    else:
        path = next((tmp_path / "outputs").glob("*.txt"))
        path.write_text("forged output")
    with pytest.raises(SR.ShardRunError):
        SR.ShardRunner(tmp_path, FakeModel(lambda p, n: reply("r")), LIMITS).load()


def test_si_p3_ledger_is_condensed_in_its_own_session_when_over_budget(tmp_path):
    def script(prompt, n):
        if prompt.startswith("INSTRUCTION:\nCondense"):
            return json.dumps({"result": "condensed", "ledger": {
                "facts": ["merged facts"], "decisions": [], "open_questions": [],
                "results": [{"task": "t*", "summary": "earlier parts done"}]}})
        return reply("r", add_facts=[f"long fact {n} " + "y" * 900])

    model = FakeModel(script)
    state = SR.ShardRunner(tmp_path, model, LIMITS).start("o", "map", tasks(10))
    assert state.status == "completed" and len(state.completed) == 10
    events = [e["event"] for e in SR.CheckpointLog(tmp_path / "checkpoints").events()]
    assert "ledger_compacted" in events
    assert any(p.startswith("INSTRUCTION:\nCondense") for p in model.prompts)


def test_si_p3_a_ledger_that_cannot_be_condensed_stops_the_run(tmp_path):
    def script(prompt, n):
        if prompt.startswith("INSTRUCTION:\nCondense"):
            return "no"
        return reply("r", add_facts=[f"long fact {n} " + "z" * 1500])

    with pytest.raises(SR.ShardRunError, match="could not be condensed"):
        SR.ShardRunner(tmp_path, FakeModel(script), LIMITS).start("o", "map", tasks(6))


def test_si_p3_a_shard_that_cannot_fit_the_window_is_refused_before_any_call(tmp_path):
    model = FakeModel(lambda p, n: reply("r"))
    with pytest.raises(SR.ShardRunError, match="does not fit"):
        SR.ShardRunner(tmp_path, model, LIMITS).start("o", "map", tasks(1, content="w" * 40000))
    assert model.prompts == []


def test_si_p3_model_call_budget_ends_the_run_resumably(tmp_path):
    limits = SR.RunLimits(context_tokens=8192, ledger_budget_tokens=1500, max_model_calls=2)
    state = SR.ShardRunner(tmp_path, FakeModel(lambda p, n: reply("r")), limits).start(
        "o", "map", tasks(4))
    assert state.status == "budget_exhausted" and len(state.completed) == 2


def test_si_p3_a_mode_can_add_work_and_resume_does_not_duplicate_it(tmp_path):
    def reduce_when_maps_done(runner, state, task):
        maps = [t for t in state.tasks if t.kind == "map"]
        if all(t.task_id in state.completed for t in maps):
            runner.add_tasks([SR.ShardTask(task_id="reduce-1", kind="reduce",
                                           instruction="combine", max_output_tokens=256)])

    model = FakeModel(lambda p, n: reply(f"r{n}"))
    runner = SR.ShardRunner(tmp_path, model, LIMITS, on_task_done=reduce_when_maps_done)
    state = runner.start("o", "map_reduce", tasks(2))
    assert state.status == "completed" and "reduce-1" in state.completed
    again = SR.ShardRunner(tmp_path, model, LIMITS, on_task_done=reduce_when_maps_done).load()
    assert [t.task_id for t in again.tasks].count("reduce-1") == 1


def test_si_p3_duplicate_ids_and_double_start_are_refused(tmp_path):
    model = FakeModel(lambda p, n: reply("r"))
    with pytest.raises(SR.ShardRunError, match="unique"):
        SR.ShardRunner(tmp_path / "a", model, LIMITS).start("o", "map", tasks(1) + tasks(1))
    SR.ShardRunner(tmp_path / "b", model, LIMITS).start("o", "map", tasks(1))
    with pytest.raises(SR.ShardRunError, match="already holds a run"):
        SR.ShardRunner(tmp_path / "b", model, LIMITS).start("o", "map", tasks(1))


@pytest.mark.parametrize("kwargs", [dict(context_tokens=1000),
                                    dict(context_tokens=8192, ledger_budget_tokens=5000),
                                    dict(context_tokens=8192, max_attempts=0)])
def test_si_p3_bad_limits_are_refused(kwargs):
    with pytest.raises(SR.ShardRunError):
        SR.RunLimits(**kwargs)
