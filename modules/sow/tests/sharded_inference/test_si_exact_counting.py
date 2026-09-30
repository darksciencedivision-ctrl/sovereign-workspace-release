"""D6: LONG counting answers are computed by the product, not estimated by the model.

Before: a counting objective over a big input was mapped and reduced by the model, and the
counts were the model's: on the 65k qualification input (2109 notes, 124 with 16 warnings) live
runs answered 100, 115 and 110. Now a model session writes a declarative extraction SPEC (data,
validated against an allow-list, never code), the product checks it on a sample, applies it to
the whole input in a child process with a hard time limit and integer arithmetic (ties included),
and the model writes prose from the computed table only. Failure injection: every spec the
allow-list refuses, a runaway engine, a cancel mid-count, a model that refuses / errs / lies
about a number, a resumed run, and the fallback to map/reduce with a note.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
if str(SOV_ROOT) not in sys.path:
    sys.path.insert(0, str(SOV_ROOT))

from sovereign_product import exact_counting as EC  # noqa: E402
from sovereign_product import exact_worker as EW  # noqa: E402
from sovereign_product import long_workload as LW  # noqa: E402
from sovereign_product.model_client import GenerationCancelled  # noqa: E402
from sovereign_product.shard_runner import ReplyTruncated  # noqa: E402

from test_si_p6_long_route import FakeLlama, _small_root, clean_env  # noqa: E402,F401

PATTERN = (r"Operations note (?P<note>\d+): the batch finished at step (?P<step>\d+) with "
           r"(?P<records>\d+) records processed, (?P<warnings>\d+) warnings")
FIELDS = {"note": "int", "step": "int", "records": "int", "warnings": "int"}
SPEC = {"applicable": True, "pattern": PATTERN, "flags": "", "fields": FIELDS,
        "aggregates": [{"op": "count"}, {"op": "max", "field": "warnings"},
                       {"op": "count_where", "field": "warnings", "cmp": "==", "value": 16}]}
OBJECTIVE = ("Using only the notes, state the step with the most warnings and its record "
             "count, and how many notes report 16 warnings.")


def _notes(count: int, seed: int = 7, warn_max: int = 16):
    rng = random.Random(seed)
    rows = [(i, rng.randint(0, 900), rng.randint(0, warn_max)) for i in range(count)]
    text = " ".join(f"Operations note {i}: the batch finished at step {i} with {rec} records "
                    f"processed, {warn} warnings, and a checksum ending in {i:04x}."
                    for i, rec, warn in rows)
    return text, rows


def _spec(**changes):
    value = json.loads(json.dumps(SPEC))
    value.update(changes)
    return value


# --- the engine -------------------------------------------------------------------------------

def test_counts_totals_maxima_minima_ties_and_groups_are_exact():
    text, rows = _notes(1500)
    spec = EW.parse_spec(_spec(aggregates=[
        {"op": "count"}, {"op": "sum", "field": "records"}, {"op": "max", "field": "warnings"},
        {"op": "min", "field": "warnings"},
        {"op": "count_where", "field": "warnings", "cmp": ">=", "value": 15},
        {"op": "group_count", "field": "warnings"}]))
    out = EW.execute(text, spec)
    count, total, top, low, ge15, groups = out["aggregates"]
    warnings = [w for _, _, w in rows]
    assert out["matched"] == count["result"] == 1500 and out["unmatched_anchor_mentions"] == 0
    assert total["result"] == sum(r for _, r, _ in rows)
    assert top["result"] == max(warnings) and top["attained_by"] == warnings.count(max(warnings))
    assert low["result"] == min(warnings) and low["attained_by"] == warnings.count(min(warnings))
    assert [e["note"] for e in top["examples"]] == [i for i, _, w in rows if w == max(warnings)][:5]
    assert ge15["result"] == sum(1 for w in warnings if w >= 15)
    assert groups["distinct"] == len(set(warnings))
    assert groups["top"][0]["count"] == max(warnings.count(w) for w in set(warnings))


def test_the_qualification_shaped_input_gives_the_ground_truth():
    text, rows = _notes(2109, seed=3)
    truth = re.findall(r"Operations note \d+: the batch finished at step \d+ with (\d+) records "
                       r"processed, (\d+) warnings", text)
    expected = sum(1 for _, w in truth if w == "16")
    out = EW.execute(text, EW.parse_spec(SPEC))
    assert out["aggregates"][2]["result"] == expected == out["aggregates"][1]["attained_by"]
    assert out["aggregates"][1]["result"] == 16 and out["input_chars"] == len(text)


def test_evidence_names_records_that_start_like_one_but_do_not_match():
    text = ("Operations note 1: the batch finished at step 1 with 10 records processed, 3 "
            "warnings. Operations note 2: garbled. Operations note 3: the batch finished at "
            "step 3 with 12 records processed, 4 warnings. Operations note 4")
    out = EW.execute(text, EW.parse_spec(SPEC))
    assert out["matched"] == 2 and out["anchor_attempts"] == 4
    assert out["unmatched_anchor_mentions"] == 2 and len(out["unmatched_offsets"]) == 2
    assert "2 place(s) start like a record" in EC.render_table(out)


def test_a_record_longer_than_the_window_is_not_matched_and_is_reported():
    long = "x" * (EW.RECORD_WINDOW_CHARS + 10)
    text = f"Operations note 1: the batch finished at step 1 with {long} 9 records processed, 3 warnings."
    out = EW.execute(text, EW.parse_spec(SPEC))
    assert out["matched"] == 0 and out["unmatched_anchor_mentions"] == 1


def test_a_value_that_cannot_be_read_is_left_out_and_counted():
    spec = EW.parse_spec({"applicable": True, "pattern": r"Item (?P<n>\S+) done", "flags": "",
                          "fields": {"n": "int"}, "aggregates": [{"op": "count"}]})
    out = EW.execute("Item 5 done. Item x done. Item 7 done.", spec)
    assert (out["matched"], out["parsed"], out["unparsed"]) == (3, 2, 1)
    assert out["aggregates"][0]["result"] == 2 and "could not be read" in EC.render_table(out)


def test_the_engine_stops_at_its_deadline():
    text, _ = _notes(3000)
    clock = iter(range(0, 10 ** 6, 100))
    with pytest.raises(EW.ExecutionError, match="time limit"):
        EW.execute(text, EW.parse_spec(SPEC), deadline=50, monotonic=lambda: next(clock))


def test_too_many_distinct_groups_is_refused_not_truncated(monkeypatch):
    monkeypatch.setattr(EW, "MAX_DISTINCT_GROUPS", 5)
    text, _ = _notes(50)
    spec = EW.parse_spec(_spec(aggregates=[{"op": "group_count", "field": "records"}]))
    with pytest.raises(EW.ExecutionError, match="distinct values"):
        EW.execute(text, spec)


# --- the allow-list ---------------------------------------------------------------------------

@pytest.mark.parametrize("change,message", [
    ({"pattern": ""}, "non-empty"),
    ({"pattern": "Operations note (?P<a>" + "1" * 2100}, "longer than"),
    ({"flags": "s"}, "flags"),
    ({"flags": "ii"}, "flags"),
    ({"pattern": "Operations (?P<note>\\d+"}, "not a valid regular expression"),
    ({"pattern": r"Operations note (?P<note>\d+) (?P<step>\d+) (?P<records>\d+) (?P<warnings>\d+)(?P=note)"},
     "not allowed"),
    ({"pattern": PATTERN + r"(?=x)"}, "not allowed"),
    ({"pattern": PATTERN + r"(?:ab|cd){1,5}"}, "alternation"),
    ({"pattern": PATTERN + r"(?:ab|cd)+"}, "single character"),
    ({"pattern": PATTERN + r"(?:\s\d+)+"}, "single character"),
    ({"pattern": PATTERN + r"(?:ab){1,5000}"}, "more than"),
    ({"pattern": PATTERN + r"(?:a+){2,5}"}, "nests an unbounded repeat"),
    ({"pattern": r"(?P<note>\d+) Operations (?P<step>\d+) (?P<records>\d+) (?P<warnings>\d+)"},
     "literal characters"),
    ({"fields": {"note": "int"}}, "exactly the fields"),
    ({"fields": {**FIELDS, "note": "float"}}, "int"),
    ({"fields": {**FIELDS, "bad name": "int"}}, "identifier"),
    ({"aggregates": []}, "aggregates"),
    ({"aggregates": [{"op": "count"}] * 9}, "aggregates"),
    ({"aggregates": [{"op": "median", "field": "warnings"}]}, "not one of"),
    ({"aggregates": [{"op": "max", "field": "nope"}]}, "not declared"),
    ({"aggregates": [{"op": "count", "field": "note"}]}, "does not take"),
    ({"aggregates": [{"op": "count_where", "field": "warnings", "cmp": "~", "value": 1}]}, "cmp"),
    ({"aggregates": [{"op": "count_where", "field": "warnings", "cmp": "==", "value": "16"}]},
     "integer value"),
    ({"aggregates": [{"op": "count_where", "field": "warnings", "cmp": "==", "value": True}]},
     "integer value"),
    ({"extra": 1}, "unknown spec keys"),
    ({"applicable": False}, "must be true"),
])
def test_the_allow_list_refuses(change, message):
    with pytest.raises(EW.SpecError, match=message):
        EW.parse_spec(_spec(**change))


def test_a_string_field_supports_equality_only_and_no_arithmetic():
    base = {"applicable": True, "pattern": r"Level=(?P<level>\w+) msg", "flags": "i",
            "fields": {"level": "str"}}
    ok = EW.parse_spec({**base, "aggregates": [
        {"op": "count_where", "field": "level", "cmp": "==", "value": "ERROR"},
        {"op": "group_count", "field": "level"}]})
    out = EW.execute("level=ERROR msg, Level=warn msg, LEVEL=ERROR msg", ok)
    assert out["aggregates"][0]["result"] == 2 and out["aggregates"][1]["distinct"] == 2
    with pytest.raises(EW.SpecError, match="== or !="):
        EW.parse_spec({**base, "aggregates": [
            {"op": "count_where", "field": "level", "cmp": "<", "value": "A"}]})
    with pytest.raises(EW.SpecError, match="needs an int field"):
        EW.parse_spec({**base, "aggregates": [{"op": "sum", "field": "level"}]})


# --- the child process ------------------------------------------------------------------------

def test_the_child_process_returns_the_same_result_as_the_engine(tmp_path):
    text, _ = _notes(400)
    direct = EW.execute(text, EW.parse_spec(SPEC))
    via_child = EC.run_engine(SPEC, text, work_dir=tmp_path, seconds=30)
    assert via_child == json.loads(json.dumps(direct))
    assert not list(tmp_path.glob("*.tmp"))  # the input copy is gone


def test_a_runaway_engine_is_killed_at_the_time_limit(tmp_path):
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    with pytest.raises(EC.ExactEngineError, match="did not finish"):
        EC.run_engine(SPEC, "x", work_dir=tmp_path, seconds=0.5, command=sleeper, grace=0.2)
    assert not list(tmp_path.glob("*.tmp"))


def test_a_cancel_kills_the_engine(tmp_path):
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    with pytest.raises(EC.ExactCancelled):
        EC.run_engine(SPEC, "x", work_dir=tmp_path, seconds=30, command=sleeper,
                      cancel_requested=lambda: True)


def test_an_engine_that_fails_says_why(tmp_path):
    crash = [sys.executable, "-c", "raise SystemExit(5)"]
    with pytest.raises(EC.ExactEngineError, match="returned no result"):
        EC.run_engine(SPEC, "x", work_dir=tmp_path, seconds=30, command=crash)
    with pytest.raises(EC.ExactEngineError, match="not allowed|unknown|must"):
        EC.run_engine(_spec(pattern=PATTERN + r"(?=x)"), "x", work_dir=tmp_path, seconds=30)


# --- the route, with a scripted model ---------------------------------------------------------

class Script:
    """A model port that replays ``replies`` (a reply that is an Exception is raised)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []
        self.systems = []

    def generate(self, *, system, prompt, max_tokens, should_stop):
        self.prompts.append(prompt)
        self.systems.append(system)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)


def _inproc(spec, text, **_kwargs):
    return json.loads(json.dumps(EW.execute(text, EW.parse_spec(spec))))


def _counter(port, tmp_path, engine=_inproc):
    return EC.ExactCounter(port, tmp_path, max_output_tokens=2048, engine=engine)


def _truth(text):
    values = [int(w) for w in re.findall(r"with \d+ records processed, (\d+) warnings", text)]
    return len(values), max(values), values.count(max(values))


def test_the_happy_path_answers_from_the_computed_table(tmp_path):
    text, _ = _notes(600)
    n, top, tied = _truth(text)
    port = Script(SPEC, {"ok": True},
                  f"The most warnings on any note is {top}, reached by {tied} notes; "
                  f"{tied} notes report {top} warnings.")
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer.startswith(f"The most warnings on any note is {top}")
    assert f"- records where warnings == 16: {tied}" in outcome.answer
    assert f"maximum warnings: {top}, reached by {tied} record(s)" in outcome.answer
    assert f"Computed by the product over {n} records" in outcome.answer
    assert outcome.telemetry["model_calls"] == 3 and outcome.telemetry["records_matched"] == n
    state = json.loads((tmp_path / EC.STATE_FILE).read_text(encoding="utf-8"))
    assert state["status"] == "answered" and state["spec"]["pattern"] == PATTERN
    assert "sample" in port.prompts[0].lower() and "Operations note" in port.prompts[0]


def test_a_lying_number_in_the_prose_is_rejected_and_the_table_carries_the_answer(tmp_path):
    text, _ = _notes(300)
    n, top, tied = _truth(text)
    lie = f"{top + 999} notes report {top} warnings."
    port = Script(SPEC, {"ok": True}, lie, lie, lie)
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert str(top + 999) not in outcome.answer  # the invented number never reaches the answer
    assert f"records where warnings == 16: {tied}" in outcome.answer
    assert outcome.telemetry["prose_from_model"] is False
    assert "not in the results" in port.prompts[-1]


def test_prose_numbers_are_checked_against_the_table_and_the_objective():
    table = {"aggregates": [{"result": 124, "examples": [{"step": 3}]}]}
    assert EC.prose_numbers_ok("124 notes report 16 warnings (step 3).", table, OBJECTIVE)
    assert EC.prose_numbers_ok("about 125 notes", table, OBJECTIVE) is False


def test_a_model_that_says_not_applicable_falls_back_and_stays_fallen_back(tmp_path):
    text, _ = _notes(50)
    port = Script({"applicable": False, "reason": "a list is asked for"})
    counter = _counter(port, tmp_path)
    outcome = counter.run("List the components.", text)
    assert outcome.answer is None and "not a counting question" in outcome.note
    again = _counter(Script(), tmp_path).run("List the components.", text)  # no model call
    assert again.answer is None and "not a counting question" in again.note


def test_a_spec_the_allow_list_refuses_is_corrected_then_used(tmp_path):
    text, _ = _notes(200)
    bad = _spec(pattern=PATTERN + r"(?:ab|cd){1,5}")
    port = Script(bad, SPEC, {"ok": True}, "Done.")
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer and "alternation" in port.prompts[1]  # the reason went back to the model


def test_no_valid_spec_after_the_corrections_falls_back(tmp_path):
    text, _ = _notes(200)
    bad = _spec(aggregates=[{"op": "median", "field": "warnings"}])
    outcome = _counter(Script(bad, bad, bad), tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None and "no valid spec after corrections" in outcome.note


def test_a_pattern_that_matches_nothing_in_the_sample_is_sent_back(tmp_path):
    text, _ = _notes(200)
    wrong = _spec(pattern=r"Log entry (?P<note>\d+) (?P<step>\d+) (?P<records>\d+) (?P<warnings>\d+)")
    port = Script(wrong, SPEC, {"ok": True}, "Done.")
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer and "matched no record in the sample" in port.prompts[1]


def test_the_model_can_correct_a_spec_it_does_not_confirm(tmp_path):
    text, _ = _notes(200)
    first = _spec(aggregates=[{"op": "count"}])
    port = Script(first, {"ok": False, **SPEC}, {"ok": True}, "Done.")
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    state = json.loads((tmp_path / EC.STATE_FILE).read_text(encoding="utf-8"))
    assert outcome.answer and len(state["spec"]["aggregates"]) == 3  # the corrected spec ran


def test_an_unconfirmed_spec_falls_back(tmp_path):
    text, _ = _notes(200)
    port = Script(SPEC, {"ok": False, "note": "no"}, "not json at all", )
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None and "did not" in outcome.note


def test_replies_that_are_cut_off_or_not_json_end_the_route(tmp_path):
    text, _ = _notes(50)
    truncated = ReplyTruncated("cut off")
    outcome = _counter(Script(truncated, "no json here"), tmp_path).run(OBJECTIVE, text)
    assert outcome.answer is None and "did not return a spec" in outcome.note


def test_an_engine_failure_falls_back_with_the_reason(tmp_path):
    text, _ = _notes(100)
    calls = {"n": 0}

    def engine(spec, text, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # the whole-input run (the first is the sample check)
            raise EC.ExactEngineError("counting did not finish within 300 s")
        return _inproc(spec, text)

    outcome = _counter(Script(SPEC, {"ok": True}), tmp_path, engine).run(OBJECTIVE, text)
    assert outcome.answer is None and "counting failed" in outcome.note


def test_a_pattern_that_matches_nothing_in_the_whole_input_falls_back(tmp_path):
    text, _ = _notes(2000)
    text = "Operations note 1: the batch finished at step 1 with 5 records processed, 2 warnings. " \
        + "filler " * 5000 + text[100:100]  # the sample is the head, the rest has no records
    calls = {"n": 0}

    def engine(spec, text, **kw):
        calls["n"] += 1
        return _inproc(spec, text if calls["n"] == 1 else "nothing to see here")

    outcome = _counter(Script(SPEC, {"ok": True}), tmp_path, engine).run(OBJECTIVE, text)
    assert outcome.answer is None and "matched no record in the whole input" in outcome.note


def test_a_cancel_and_an_outage_reach_the_caller(tmp_path):
    text, _ = _notes(50)
    with pytest.raises(GenerationCancelled):
        _counter(Script(GenerationCancelled("stop")), tmp_path).run(OBJECTIVE, text)


def test_a_resumed_run_reuses_what_it_recorded(tmp_path):
    text, _ = _notes(300)
    first = _counter(Script(SPEC, {"ok": True}, GenerationCancelled("stopped before the answer")),
                     tmp_path)
    with pytest.raises(GenerationCancelled):
        first.run(OBJECTIVE, text)
    state = json.loads((tmp_path / EC.STATE_FILE).read_text(encoding="utf-8"))
    assert "results" in state and state.get("status") != "answered"

    def no_engine(*a, **k):
        raise AssertionError("the counting must not run again")

    port = Script("The answer.")
    outcome = _counter(port, tmp_path, no_engine).run(OBJECTIVE, None)  # the input is not needed
    assert outcome.answer.startswith("The answer.") and len(port.prompts) == 1
    done = _counter(Script(), tmp_path, no_engine).run(OBJECTIVE, None)  # answered: no model call
    assert done.answer == outcome.answer


def test_the_sample_carries_the_head_the_middle_and_the_tail():
    text, _ = _notes(3000)
    sample = EC.make_sample(text)
    assert len(sample) < EC.SAMPLE_CHARS + 400 and sample.startswith("Operations note 0:")
    assert sample.rstrip(".").endswith(text[-60:].rstrip("."))
    assert sample.count("characters omitted") == 3 and EC.make_sample("short") == "short"


def test_which_objectives_try_the_exact_route():
    for text in ("How many notes report 16 warnings?", "Count the errors.", "the total of X",
                 "Which step has the most warnings", "smallest record count"):
        assert EC.is_countable_objective(text), text
    for text in ("List the components of the design.", "Summarize the document.",
                 "Explain the retry policy."):
        assert not EC.is_countable_objective(text), text


# --- through the LONG executor ----------------------------------------------------------------

class ExactFake(FakeLlama):
    """A llama.cpp fake whose spec / confirm / answer calls follow the exact route."""

    def __init__(self, spec=SPEC, answer=None, refuse=False):
        super().__init__(context=8192)
        self.spec, self.answer, self.refuse = spec, answer, refuse
        self.exact_calls = []

    def chat(self, *, model, messages, options, think, cancel_requested):
        if messages[0]["content"] not in (EC.SYSTEM, EC.PROSE_SYSTEM):
            return super().chat(model=model, messages=messages, options=options, think=think,
                                cancel_requested=cancel_requested)
        prompt = messages[-1]["content"]
        self.exact_calls.append(prompt[:40])
        if self.refuse:
            text = json.dumps({"applicable": False, "reason": "not for this"})
        elif "Does this extract the records" in prompt:
            text = json.dumps({"ok": True})
        elif "Exact results computed" in prompt:
            text = self.answer
        else:
            text = json.dumps(self.spec)
        return SimpleNamespace(text=text, reasoning="", finish_reason="stop")


def _run(root, client, text, job="job-x", **kw):
    executor = LW.LongWorkloadExecutor(root=root, evidence_dir=root / "ev", client=client, **kw,
                                       config=LW.load_config(root))
    events = []
    result = executor.run(job, text, cancel_requested=lambda: False,
                          progress_callback=events.append)
    return result, events


def test_a_counting_objective_over_material_is_answered_by_the_exact_route(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(500)
    n, top, tied = _truth(text)
    client = ExactFake(answer=f"{tied} notes report the maximum of {top} warnings.")
    result, events = _run(root, client, f"{OBJECTIVE}\n---\n{text}")
    assert result["status"] == "completed" and result["telemetry"]["mode"] == "exact_counting"
    assert f"{tied} notes report the maximum of {top} warnings." in result["answer"]
    assert f"records where warnings == 16: {tied}" in result["answer"]
    assert len(client.exact_calls) == 3 and all(c["messages"][0]["content"].startswith("You produce")
                                                for c in client.chats)  # no map / reduce ran
    stages = [e.get("stage") for e in events]
    assert "exact_counting" in stages
    percents = [e["percent"] for e in events if "percent" in e]
    assert percents == sorted(percents)


def test_a_list_objective_keeps_the_map_reduce_route(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)
    client = ExactFake()
    result, _events = _run(root, client, f"List the steps that appear.\n---\n{text}")
    assert client.exact_calls == [] and result["telemetry"]["mode"] == "input_shards"
    assert "exact counting was not used" not in result["answer"]


def test_a_refused_counting_objective_falls_back_to_map_reduce_with_a_note(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)
    client = ExactFake(refuse=True)
    result, _events = _run(root, client, f"{OBJECTIVE}\n---\n{text}")
    assert result["status"] == "completed" and result["telemetry"]["mode"] == "input_shards"
    assert "exact counting was not used" in result["answer"] and "estimate, not computed" in result["answer"]


def test_a_cancel_during_the_exact_route_ends_the_job_cancelled(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)

    class CancelledFake(ExactFake):
        def chat(self, **kw):
            raise GenerationCancelled("stopped")

    result, _events = _run(root, CancelledFake(), f"{OBJECTIVE}\n---\n{text}")
    assert result["status"] == "cancelled"


def test_an_outage_during_the_exact_route_interrupts_the_job(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)

    class DownFake(ExactFake):
        def chat(self, **kw):
            raise RuntimeError("connection refused")

        def count_text_tokens(self, model, text):
            return None

    result, _events = _run(root, DownFake(), f"{OBJECTIVE}\n---\n{text}")
    assert result["status"] == "interrupted" and "resume the job" in result["reason"]


# --- the @exact directive ---------------------------------------------------------------------

def test_directives_read_in_either_order_and_leave_the_objective_alone():
    d = LW.split_directives
    assert d("Plan it.") == (None, "auto", "Plan it.")
    assert d("@model: qwen3:30b-a3b\nPlan it.") == ("qwen3:30b-a3b", "auto", "Plan it.")
    assert d("@exact: off\nPlan it.") == (None, "off", "Plan it.")
    assert d("@model: m\n@exact: OFF\nPlan it.") == ("m", "off", "Plan it.")
    assert d("@exact: off\n@model: m\nPlan it.") == ("m", "off", "Plan it.")
    assert d("﻿@exact: auto\r\nPlan it.") == (None, "auto", "Plan it.")
    # only the leading lines count; a second @exact stays in the objective
    assert d("@exact: off\n@exact: auto\nPlan it.") == (None, "off", "@exact: auto\nPlan it.")
    with pytest.raises(LW.LongWorkloadError, match="'off' or 'auto'"):
        d("@exact: maybe\nPlan it.")


def test_exact_off_keeps_a_counting_objective_on_map_reduce(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)
    client = ExactFake()
    result, _events = _run(root, client, f"@exact: off\n{OBJECTIVE}\n---\n{text}")
    assert client.exact_calls == [] and result["telemetry"]["mode"] == "input_shards"
    assert "exact counting was not used" not in result["answer"]  # it was switched off, not refused


def test_a_fallback_continues_the_progress_from_where_the_exact_route_reached(clean_env, tmp_path):
    root = _small_root(tmp_path)
    text, _ = _notes(60)
    client = ExactFake(refuse=True)
    _result, events = _run(root, client, f"{OBJECTIVE}\n---\n{text}")
    percents = [e["percent"] for e in events if "percent" in e]
    assert percents == sorted(percents), percents  # never backwards, so the product keeps them all
    assert any(e.get("stage") == "exact_counting" for e in events) and percents[-1] >= 8


# --- overnight review: nested bounded repeats multiply (2026-09-29) -----------------------------

def _spec_for(pattern):
    return {"applicable": True, "pattern": pattern, "flags": "", "fields": {"n": "int"},
            "aggregates": [{"op": "count"}]}


def test_nested_bounded_repeats_with_a_huge_product_are_refused():
    # Measured: (?:\d{1,1000}){1,1000} on a 60-digit record ran for more than a minute.
    with pytest.raises(EW.SpecError, match="nested inside repeats"):
        EW.parse_spec(_spec_for(r"Note (?P<n>(?:\d{1,1000}){1,1000})x"))


def test_small_nested_bounded_repeats_and_sibling_repeats_are_still_accepted():
    EW.parse_spec(_spec_for(r"Note (?P<n>(?:\d{1,5}){1,3})x"))
    EW.parse_spec(_spec_for(r"Note (?P<n>\d{1,1000}) ([a-z]{1,1000}) (?:z{1,1000})?x"))


def test_a_greedy_tail_does_not_swallow_the_next_record():
    # Live (2026-09-29, 32k input): the model wrote a pattern ending in [^,]*; it ran on into the
    # next note, so every second note was skipped and the count was 31 instead of 63.
    text, rows = _notes(400, seed=11)
    greedy = _spec(pattern=r"Operations note \d+: the batch finished at step (?P<step>\d+) with "
                           r"(?P<records>\d+) records processed, (?P<warnings>\d+) warnings, "
                           r"and a checksum ending in [^,]*",
                   fields={"step": "int", "records": "int", "warnings": "int"},
                   aggregates=[{"op": "count"}, {"op": "max", "field": "warnings"},
                               {"op": "count_where", "field": "warnings", "cmp": "==",
                                "value": 16}])
    out = EW.execute(text, EW.parse_spec(greedy))
    warnings = [w for _, _, w in rows]
    assert out["matched"] == 400 and out["unmatched_anchor_mentions"] == 0
    assert out["aggregates"][2]["result"] == warnings.count(16)


def test_the_answer_step_is_asked_for_prose_not_for_a_json_object(tmp_path):
    # Live: the answer came back as {"step_with_most_warnings": ..} because the answer call
    # reused the "reply with exactly one JSON object" system prompt of the spec calls.
    text, _ = _notes(60)
    port = Script(SPEC, {"ok": True}, "Done.")
    _counter(port, tmp_path).run(OBJECTIVE, text)
    assert port.systems[:2] == [EC.SYSTEM, EC.SYSTEM]
    assert port.systems[2] == EC.PROSE_SYSTEM and "JSON" in EC.PROSE_SYSTEM
    assert "exactly one JSON object" not in port.systems[2]


# --- line records: tables and logs whose lines start with a varying value ----------------------

def _table():
    rows = [(i, ["ok", "late", "lost"][i % 3], (i * 37) % 500) for i in range(1, 301)]
    body = "\n".join(f"{i},{state},{amount}" for i, state, amount in rows)
    return "id,state,amount\n\n" + body + "\n", rows


LINE_SPEC = {"applicable": True, "pattern": r"^(?P<id>\d+),(?P<state>[a-z]+),(?P<amount>\d+)$",
             "flags": "m", "fields": {"id": "int", "state": "str", "amount": "int"},
             "aggregates": [{"op": "count"}, {"op": "count_where", "field": "state", "cmp": "==",
                                              "value": "late"},
                            {"op": "max", "field": "amount"}, {"op": "sum", "field": "amount"},
                            {"op": "group_count", "field": "state"}]}


def test_a_table_whose_lines_start_with_a_varying_value_counts_exactly():
    text, rows = _table()
    out = EW.execute(text, EW.parse_spec(LINE_SPEC))
    count, late, top, total, groups = out["aggregates"]
    amounts = [a for _, _, a in rows]
    assert count["result"] == out["matched"] == 300
    assert late["result"] == sum(1 for _, s, _ in rows if s == "late")
    assert top["result"] == max(amounts) and top["attained_by"] == amounts.count(max(amounts))
    assert total["result"] == sum(amounts)
    assert groups["distinct"] == 3
    # the header is the one non-blank line that is not a record; the blank line is nothing
    assert out["unmatched_anchor_mentions"] == 1 and out["anchor"] == "start of a line"
    assert "non-blank line(s) did not match" in EC.render_table(out)


def test_a_log_file_with_levels_counts_errors_per_component():
    lines = []
    for i in range(500):
        level = ["INFO", "WARN", "ERROR"][i % 3 if i % 7 else 2]
        lines.append(f"{2020 + i % 5}-01-{i % 28 + 1:02d} 10:00:{i % 60:02d} {level} "
                     f"comp{i % 4}: took {i % 90} ms")
    text = "\r\n".join(lines) + "\r\n"  # Windows line ends
    spec = EW.parse_spec({"applicable": True, "flags": "m",
                          "pattern": r"^\d{4}-\d\d-\d\d [\d:]+ (?P<level>[A-Z]+) (?P<comp>\w+): "
                                     r"took (?P<ms>\d+) ms\s*$",
                          "fields": {"level": "str", "comp": "str", "ms": "int"},
                          "aggregates": [{"op": "count_where", "field": "level", "cmp": "==",
                                          "value": "ERROR"},
                                         {"op": "group_count", "field": "comp"}]})
    out = EW.execute(text, spec)
    errors = sum(1 for line in lines if " ERROR " in line)
    assert out["matched"] == 500 and out["unmatched_anchor_mentions"] == 0
    assert out["aggregates"][0]["result"] == errors
    assert out["aggregates"][1]["distinct"] == 4


def test_a_variable_start_without_the_line_flag_is_still_refused():
    with pytest.raises(EW.SpecError, match=r'start with \^'):
        EW.parse_spec({**LINE_SPEC, "flags": ""})
    with pytest.raises(EW.SpecError, match="at least 3 literal"):
        EW.parse_spec({**LINE_SPEC, "pattern": r"(?P<id>\d+),(?P<state>[a-z]+),(?P<amount>\d+)"})


def test_the_spec_prompt_tells_the_model_how_to_describe_line_records():
    assert '"flags": "m"' in EC.SPEC_FORMAT and "each line is one record" in EC.SPEC_FORMAT
    assert "(no \\n in it)" in EC.SPEC_FORMAT  # a literal backslash-n, not a line break
    assert "do not start the pattern with ^" in EC.SPEC_FORMAT


def test_a_line_anchor_on_records_that_share_a_line_is_stripped_and_counted(tmp_path):
    # Live 2026-09-30: the model wrote ^ with flags m on one-line notes, and kept doing so
    # after the correction prompt. The product drops the ^ and counts every record.
    text, rows = _notes(40)
    bad = {"applicable": True, "flags": "m",
           "pattern": r"^Operations note \d+: the batch finished at step (?P<step>\d+) with "
                      r"(?P<records>\d+) records processed, (?P<warnings>\d+) warnings, "
                      r"and a checksum ending in [^\.]+",
           "fields": {"step": "int", "records": "int", "warnings": "int"},
           "aggregates": [{"op": "max", "field": "warnings"},
                          {"op": "count_where", "field": "warnings", "cmp": "==", "value": 16}]}
    counted = EW.execute(text, EW.parse_spec(bad))
    assert counted["matched"] == 1
    assert counted["unmatched_anchor_mentions"] > counted["matched"]
    class Confirm(Script):
        def generate(self, *, system, prompt, max_tokens, should_stop):
            if not self.replies:
                self.prompts.append(prompt)
                self.systems.append(system)
                if "Exact results computed" in prompt:
                    return "step 0 has 0 records. 0 notes report 16 warnings."
                return json.dumps({"ok": True})
            return super().generate(system=system, prompt=prompt, max_tokens=max_tokens,
                                    should_stop=should_stop)

    port = Confirm(bad)
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer and f"over {len(rows)} records" in outcome.answer
    assert "over 1 records" not in outcome.answer


def test_a_false_refusal_of_a_counting_objective_is_corrected(tmp_path):
    # Live 2026-09-30: the model replied applicable false ("Missing aggregate to find step
    # with most warnings") and the product fell back without asking for a spec.
    text, rows = _notes(40)
    warnings = [w for _, _, w in rows]
    top, tied, n16 = max(warnings), warnings.count(max(warnings)), warnings.count(16)
    refusal = {"applicable": False, "reason": "Missing aggregate to find step with most warnings"}
    port = Script(refusal, SPEC, {"ok": True},
                  f"The most warnings on any note is {top}, reached by {tied} notes; "
                  f"{n16} notes report 16 warnings.")
    outcome = _counter(port, tmp_path).run(OBJECTIVE, text)
    assert outcome.answer and f"over {len(rows)} records" in outcome.answer
    assert f"records where warnings == 16: {n16}" in outcome.answer


def test_a_prose_request_that_says_most_does_not_pay_for_a_spec_call():
    # Every LONG run that tries the exact route spends one thinking-model call (minutes) on the
    # spec; "summarize the most important risks" is not a counting question.
    for text in ("Summarize the most important risks.", "List the largest customers.",
                 "Describe the minimum viable design.", "Write a plan for the total rollout."):
        assert not EC.is_countable_objective(text), text
    for text in ("List how many notes report 16 warnings.", "Summarize and count the errors.",
                 "Which order has the highest amount?", "What is the total of all amounts?"):
        assert EC.is_countable_objective(text), text
