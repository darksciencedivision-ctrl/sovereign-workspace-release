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


# --- the reply contract as real models answer it --------------------------------------------------

# The live qwen3.8:27b reply to the plan instruction, verbatim (captured 2026-09-24). The plan
# instruction asks for a JSON LIST in "result"; the model gave one, and the runner used to reject
# it three times ('reply must be an object with a string "result"'), failing the whole LONG run.
REAL_27B_PLAN_REPLY = (
    '{"result": ["Draft a 6-item checklist covering key generation, server reload, client update, '
    'and verification.", "Review the draft for practicality and safety, ensuring no step exceeds '
    '120 words.", "Finalize the checklist and format it as a concise, actionable list."], '
    '"ledger_update": {"add_facts": ["Objective is to create a 6-item checklist for API key '
    'rotation.", "Checklist must cover both server and client sides.", "Each step must be under '
    '120 words."], "add_decisions": ["Use 3 plan steps to complete the task.", "Focus on '
    'practical, actionable items."], "add_open_questions": [], "resolve_open_questions": []}}')


def test_si_p5_a_plan_given_as_a_json_list_is_accepted(tmp_path):
    base = _plan_script(["unused"])

    def script(prompt, n):
        if "INSTRUCTION (plan)" in prompt:
            return REAL_27B_PLAN_REPLY
        return base(prompt, n)

    mode, runner, state, model = _run_plan(tmp_path, script)
    assert state.status == "completed"
    steps = [t for t in state.tasks if t.kind == "step"]
    assert len(steps) == 3 and "key generation" in steps[0].instruction
    assert sum("INSTRUCTION (plan)" in p for p in model.prompts) == 1, "no retries needed"


@pytest.mark.parametrize("text,expected", [
    ('{"result": ["a", "b"]}', '["a", "b"]'),
    ('{"result": {"k": 1}}', '{"k": 1}'),
    ('{"result": 42}', "42"),
    ('{"result": "plain"}', "plain"),
])
def test_si_p5_structured_results_are_kept_as_canonical_json(text, expected):
    assert SR._parse_reply(text)[0] == expected


@pytest.mark.parametrize("text", ['{"ledger_update": {}}', '{"result": null}', '["a"]'])
def test_si_p5_a_reply_without_a_result_is_still_invalid(text):
    with pytest.raises(ValueError):
        SR._parse_reply(text)


# --- aggregation across disjoint parts --------------------------------------------------------------

def test_si_p4_every_map_and_reduce_prompt_carries_the_aggregation_rules(tmp_path):
    """Live (qwen3:30b-a3b, 65k input): maps answered as if each part were the whole input and the
    final reduce copied part 1's count (31) instead of adding the parts (31+29+26+25+6)."""
    text = "\n\n".join(f"Section {i}: " + "log line with a warning. " * 30 for i in range(200))
    mode, runner, state, model = _run_input(tmp_path, text, _map_reduce_script())
    maps = [p for p in model.prompts if "INSTRUCTION (map)" in p]
    reduces = [p for p in model.prompts if "INSTRUCTION (reduce)" in p]
    assert maps and len(reduces) >= 2
    for prompt in maps:
        assert "report for THIS PART ONLY" in prompt and "labeled" in prompt
    for prompt in reduces:
        assert "DIFFERENT, non-overlapping part" in prompt
        assert "ADD counts and totals" in prompt
        assert "Never give one part's value as the answer for the whole input" in prompt
    final = [p for p in reduces if "FINAL answer" in p]
    assert len(final) == 1 and "list the per-part values you combined" in final[0]
    assert all("keeping the same labeled values" in p for p in reduces if p not in final)
    # the longer instructions are part of the sizing: every session still fits the window
    assert all(count(SR.SYSTEM_ROLE) + count(p) <= LIMITS.context_tokens for p in model.prompts)


# --- a map whose reply was cut off is split, not retried as is --------------------------------------

def _truncating_script(truncate_whole_part: str, log: list[str] | None = None):
    """Part N of the input is too much for one reply; each of its slices fits."""
    base = _map_reduce_script()

    def script(prompt, n):
        if "INSTRUCTION (map)" in prompt and f"part {truncate_whole_part} of" in prompt \
                and "(Slice " not in prompt:
            if log is not None:
                log.append("cut")
            raise SR.ReplyTruncated("the reply was cut off at the 200-token limit")
        return base(prompt, n)
    return script


def test_si_p4_a_cut_off_map_is_split_and_the_run_completes(tmp_path):
    text = "\n\n".join(f"Section {i}: " + "log line with a warning. " * 30 for i in range(60))
    cuts: list[str] = []
    mode = SM.InputShardMode(objective="count warnings", map_instruction="Summarize this part.",
                             reduce_instruction="Combine.", max_output_tokens=200)
    model = FakeModel(_truncating_script("2", cuts))
    runner = SR.ShardRunner(tmp_path, model, LIMITS, on_task_done=mode.on_task_done,
                            summary_kinds=mode.summary_kinds, split_task=mode.split_task)
    state = runner.start("count warnings", "input_shards", mode.plan(runner, text))
    assert state.status == "completed" and not state.failed
    assert cuts == ["cut"], "split on the first cut-off, no identical retries"
    ids = [t.task_id for t in state.tasks if t.kind == "map"]
    assert "map-0002" not in ids and ids[1:3] == ["map-0002a", "map-0002b"], ids
    reduce_prompts = [p for p in model.prompts if "INSTRUCTION (reduce)" in p]
    assert any("RESULT of map-0002a" in p and "RESULT of map-0002b" in p for p in reduce_prompts)
    events = [e["event"] for e in runner.log.events()]
    assert events.count("task_split") == 1
    slices = [t for t in state.tasks if t.task_id.startswith("map-0002")]
    assert all("Report for this slice only" in t.instruction for t in slices)


def test_si_p4_a_split_survives_a_restart(tmp_path):
    text = "\n\n".join(f"Section {i}: " + "log line with a warning. " * 30 for i in range(60))
    mode = SM.InputShardMode(objective="count warnings", map_instruction="Summarize this part.",
                             reduce_instruction="Combine.", max_output_tokens=200)
    splitting = _truncating_script("2")

    def crash_after_split(prompt, n):
        if "(Slice 1 of" in prompt:
            raise KeyboardInterrupt  # the product dies right after checkpointing the split
        return splitting(prompt, n)

    runner = SR.ShardRunner(tmp_path, FakeModel(crash_after_split), LIMITS,
                            on_task_done=mode.on_task_done, summary_kinds=mode.summary_kinds,
                            split_task=mode.split_task)
    with pytest.raises(KeyboardInterrupt):
        runner.start("count warnings", "input_shards", mode.plan(runner, text))
    again = SR.ShardRunner(tmp_path, FakeModel(splitting), LIMITS, on_task_done=mode.on_task_done,
                           summary_kinds=mode.summary_kinds, split_task=mode.split_task)
    state = again.resume()
    ids = [t.task_id for t in state.tasks]
    assert state.status == "completed" and len(ids) == len(set(ids))
    assert "map-0002" not in ids and {"map-0002a", "map-0002b"} <= set(ids)


def test_si_p4_a_small_cut_off_map_is_retried_not_split(tmp_path):
    mode = SM.InputShardMode(objective="o", map_instruction="Summarize.",
                             reduce_instruction="Combine.", max_output_tokens=200)
    small = SR.ShardTask("map-0001", "map", "Objective: o\nSummarize. This is part 1 of 1 of "
                         "the input.", content="tiny input " * 20, max_output_tokens=200)

    def always_cut(prompt, n):
        raise SR.ReplyTruncated("the reply was cut off at the 200-token limit")

    runner = SR.ShardRunner(tmp_path, FakeModel(always_cut), LIMITS,
                            on_task_done=mode.on_task_done, split_task=mode.split_task)
    state = runner.start("o", "input_shards", [small])
    assert state.failed["map-0001"] == "the reply was cut off at the 200-token limit"
    assert not any(t.task_id.startswith("map-0001") and t.task_id != "map-0001"
                   for t in state.tasks), "too small to split"
    assert not any(e["event"] == "task_split" for e in runner.log.events())
    map_calls = [p for p in runner.model.prompts if "INSTRUCTION (map)" in p]
    assert len(map_calls) == LIMITS.max_attempts


def test_si_p5_a_cut_off_plan_is_retried_not_split(tmp_path):
    base = _plan_script(["design", "build"])
    calls = {"plan": 0}

    def script(prompt, n):
        if "INSTRUCTION (plan)" in prompt:
            calls["plan"] += 1
            if calls["plan"] == 1:
                raise SR.ReplyTruncated("the reply was cut off at the 200-token limit")
        return base(prompt, n)

    mode = SM.PlanStepMode(objective="ship the feature")
    runner = SR.ShardRunner(tmp_path, FakeModel(script), LIMITS, on_task_done=mode.on_task_done,
                            validators=mode.validators, summary_kinds=mode.summary_kinds,
                            split_task=getattr(mode, "split_task", None))
    state = runner.start("ship the feature", "plan_steps", mode.plan(runner))
    assert state.status == "completed" and calls["plan"] == 2
    assert not any(e["event"] == "task_split" for e in runner.log.events())
