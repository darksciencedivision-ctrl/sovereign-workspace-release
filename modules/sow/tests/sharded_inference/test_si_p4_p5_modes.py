"""Sharded inference P4 (input shards, map/reduce) and P5 (agentic plan steps).

P4: a large input is split at natural boundaries into chunks sized by the model's own token counter,
each mapped in a fresh session, then reduced in rounds until one answer remains; a failed chunk is
named in the reduce input. P5: a plan session writes steps, each step runs fresh against the ledger,
bounded review rounds may add steps, and a synthesis session writes the answer. Failure injection:
text with no boundaries, a failed chunk, an invalid plan, a crash mid-run with resume.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import shard_modes as SM  # noqa: E402
from sovereign_product import shard_runner as SR  # noqa: E402


def count(text: str) -> int:
    return len(text) // 4


def reply(result: str, **update) -> str:
    return json.dumps({"result": result, "ledger_update": update})


class FakeModel:
    def __init__(self, script):
        self.script = script
        self.prompts: list[str] = []

    def generate(self, *, system, prompt, max_tokens, should_stop):
        self.prompts.append(prompt)
        return self.script(prompt, len(self.prompts))

    def count_tokens(self, text):
        return count(text)


# --- splitting ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(40)),
    "\n".join(f"line {i} " + "x" * 90 for i in range(200)),
    " ".join(f"Sentence number {i} has some words in it." for i in range(400)),
    "z" * 20000,  # no boundaries at all
])
def test_si_p4_split_respects_the_budget_and_loses_nothing(text):
    chunks = SM.split_text(text, count_tokens=count, max_tokens=500)
    assert "".join(chunks) == text
    assert all(count(c) <= 500 for c in chunks)
    assert len(chunks) >= count(text) // 500


def test_si_p4_split_prefers_paragraph_boundaries():
    paragraphs = [f"P{i} " + "word " * 80 + "\n\n" for i in range(10)]
    chunks = SM.split_text("".join(paragraphs), count_tokens=count, max_tokens=250)
    assert all(c.endswith("\n\n") for c in chunks)


# --- P4: map / reduce -----------------------------------------------------------------------------

LIMITS = SR.RunLimits(context_tokens=4096, ledger_budget_tokens=600, margin_tokens=128)


def _map_reduce_script(fail_map: str | None = None):
    def script(prompt, n):
        task = re.search(r"part (\d+) of (\d+)", prompt)
        if "(map)" in prompt and task:
            if fail_map and f"part {fail_map} of" in prompt:
                return "garbage"
            # long enough that several map results fill a reduce -> multiple reduce rounds
            return reply(f"summary of part {task.group(1)} " + "detail " * 400)
        if "(reduce)" in prompt:
            parts = re.findall(r"RESULT of ([\w-]+)", prompt)
            gaps = set(re.findall(r"RESULT of ([\w-]+): FAILED", prompt))
            for carried in re.findall(r"gaps: ([\w,-]+)", prompt):
                gaps.update(g for g in carried.split(",") if g != "none")
            return reply(f"merged {len(parts)} results; gaps: {','.join(sorted(gaps)) or 'none'}")
        raise AssertionError("unexpected prompt")
    return script


def _run_input(tmp_path, text, script, runner_limits=LIMITS, max_output=200):
    mode = SM.InputShardMode(objective="count warnings", map_instruction="Summarize this part.",
                             reduce_instruction="Combine.", max_output_tokens=max_output)
    model = FakeModel(script)
    runner = SR.ShardRunner(tmp_path, model, runner_limits, on_task_done=mode.on_task_done,
                            summary_kinds=mode.summary_kinds)
    state = runner.start("count warnings", "input_shards", mode.plan(runner, text))
    return mode, runner, state, model


def test_si_p4_a_large_input_is_mapped_then_reduced_to_one_answer(tmp_path):
    text = "\n\n".join(f"Section {i}: " + "log line with a warning. " * 30 for i in range(200))
    mode, runner, state, model = _run_input(tmp_path, text, _map_reduce_script())
    maps = [t for t in state.tasks if t.kind == "map"]
    reduces = [t for t in state.tasks if t.kind == "reduce"]
    assert len(maps) > 5 and reduces and state.status == "completed"
    rounds = {t.task_id.split("-")[1] for t in reduces}
    assert len(rounds) >= 2, "more results than one reduce can hold -> multiple rounds"
    final = mode.final_output(runner, state)
    assert final.startswith("merged") and "gaps: none" in final
    # every session fit the window
    assert all(count(SR.SYSTEM_ROLE) + count(p) <= LIMITS.context_tokens for p in model.prompts)


def test_si_p4_a_failed_chunk_is_reported_as_a_coverage_gap(tmp_path):
    text = "\n\n".join(f"Section {i}: " + "entry. " * 60 for i in range(120))
    mode, runner, state, _ = _run_input(tmp_path, text, _map_reduce_script(fail_map="3"))
    assert state.status == "failed" and any(t.startswith("map-") for t in state.failed)
    final = mode.final_output(runner, state)
    assert final is not None and "map-0003" in final


def test_si_p4_a_single_chunk_needs_no_reduce(tmp_path):
    mode, runner, state, _ = _run_input(tmp_path, "short input", _map_reduce_script())
    assert [t.kind for t in state.tasks] == ["map"]
    assert mode.final_output(runner, state).startswith("summary of part 1 ")


def test_si_p4_resume_after_a_crash_finishes_without_duplicate_reduces(tmp_path):
    text = "\n\n".join(f"Section {i}: " + "entry. " * 60 for i in range(200))
    calls = {"n": 0}
    base = _map_reduce_script()

    def crashing(prompt, n):
        calls["n"] += 1
        if calls["n"] == 9:
            raise KeyboardInterrupt
        return base(prompt, n)

    mode = SM.InputShardMode(objective="o", map_instruction="Summarize this part.",
                             reduce_instruction="Combine.", max_output_tokens=200)
    runner = SR.ShardRunner(tmp_path, FakeModel(crashing), LIMITS, on_task_done=mode.on_task_done,
                            summary_kinds=mode.summary_kinds)
    with pytest.raises(KeyboardInterrupt):
        runner.start("o", "input_shards", mode.plan(runner, text))
    again = SR.ShardRunner(tmp_path, FakeModel(base), LIMITS, on_task_done=mode.on_task_done,
                           summary_kinds=mode.summary_kinds)
    state = again.resume()
    assert state.status == "completed"
    ids = [t.task_id for t in state.tasks]
    assert len(ids) == len(set(ids))
    assert mode.final_output(again, state).startswith("merged")


# --- P5: plan steps -------------------------------------------------------------------------------

def _plan_script(steps, review_adds=None, bad_plan_first=False):
    state = {"plans": 0}

    def script(prompt, n):
        if "INSTRUCTION (plan)" in prompt:
            state["plans"] += 1
            if bad_plan_first and state["plans"] == 1:
                return reply("I think we should do several things")
            return reply(json.dumps(steps))
        if "INSTRUCTION (step)" in prompt:
            number = re.search(r"Do step (\d+)", prompt).group(1)
            return reply(f"did step {number}", add_facts=[f"step {number} finding"])
        if "INSTRUCTION (review)" in prompt:
            return reply(json.dumps(review_adds or []))
        if "INSTRUCTION (synthesize)" in prompt:
            facts = re.findall(r"step \d+ finding", prompt)
            return reply(f"final answer from {len(facts)} findings")
        raise AssertionError(prompt[:80])
    return script


def _run_plan(tmp_path, script, **mode_kwargs):
    mode = SM.PlanStepMode(objective="ship the feature", **mode_kwargs)
    model = FakeModel(script)
    runner = SR.ShardRunner(tmp_path, model, LIMITS, on_task_done=mode.on_task_done,
                            validators=mode.validators, summary_kinds=mode.summary_kinds)
    state = runner.start("ship the feature", "plan_steps", mode.plan(runner))
    return mode, runner, state, model


def test_si_p5_plan_steps_review_and_synthesize(tmp_path):
    mode, runner, state, model = _run_plan(
        tmp_path, _plan_script(["design", "build", "test"], review_adds=["document"]))
    kinds = [t.kind for t in state.tasks]
    assert kinds == ["plan", "step", "step", "step", "review", "step", "synthesize"]
    assert [t.task_id for t in state.tasks if t.kind == "step"][-1] == "step-r01-001"
    assert state.status == "completed"
    assert mode.final_output(runner, state) == "final answer from 4 findings"
    step_prompts = [p for p in model.prompts if "INSTRUCTION (step)" in p]
    assert "step 1 finding" in step_prompts[1]  # later steps see earlier findings via the ledger


def test_si_p5_an_invalid_plan_is_retried_in_a_fresh_session(tmp_path):
    _, _, state, model = _run_plan(tmp_path, _plan_script(["a", "b"], bad_plan_first=True))
    assert state.completed["plan"]["attempts"] == 2
    assert state.status == "completed"


def test_si_p5_step_count_is_bounded(tmp_path):
    _, _, state, _ = _run_plan(tmp_path, _plan_script([f"s{i}" for i in range(50)],
                                                      review_adds=["more"]), max_steps=5)
    assert len([t for t in state.tasks if t.kind == "step"]) == 5
    assert not any(t.kind == "review" for t in state.tasks)  # no room left to add steps


def test_si_p5_resume_mid_plan_does_not_duplicate_steps(tmp_path):
    calls = {"n": 0}
    base = _plan_script(["a", "b", "c", "d"], review_adds=["e", "f"])

    def crashing(prompt, n):
        calls["n"] += 1
        if calls["n"] == 7:
            raise KeyboardInterrupt
        return base(prompt, n)

    mode = SM.PlanStepMode(objective="o")
    runner = SR.ShardRunner(tmp_path, FakeModel(crashing), LIMITS,
                            on_task_done=mode.on_task_done, validators=mode.validators)
    with pytest.raises(KeyboardInterrupt):
        runner.start("o", "plan_steps", mode.plan(runner))
    again = SR.ShardRunner(tmp_path, FakeModel(base), LIMITS, on_task_done=mode.on_task_done,
                           validators=mode.validators)
    state = again.resume()
    ids = [t.task_id for t in state.tasks]
    assert state.status == "completed" and len(ids) == len(set(ids))
    assert ids.count("synthesize") == 1 and len([i for i in ids if i.startswith("step-")]) == 6
