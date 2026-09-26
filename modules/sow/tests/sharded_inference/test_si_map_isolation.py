"""Inject the live map-count leak through the production LONG executor."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sovereign"))
from sovereign_product import long_workload as LW
from sovereign_product.shard_runner import CheckpointLog, Ledger, RunLimits, ShardRunner, ShardTask


class LeakingModel:
    def __init__(self, crash=False):
        self.prompts = []
        self.values = []
        self.crash = crash

    def native_context_length(self, model):
        return 8192

    def count_text_tokens(self, model, text):
        return len(text) // 4

    def chat(self, *, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if self.crash and len(self.prompts) == 2:
            raise KeyboardInterrupt
        if "INSTRUCTION (map)" in prompt:
            own = int(re.search(r"part (\d+) of", prompt)[1])
            self.values.append(own)
            leaked = sum(map(int, re.findall(r"notes_with_16_warnings: (\d+)", prompt)))
            result = f"part_value: {own + leaked}"
            update = {"add_facts": [f"notes_with_16_warnings: {own}"]}
        else:
            result = str(sum(map(int, re.findall(r"part_value: (\d+)", prompt))))
            update = {}
        return SimpleNamespace(text=json.dumps({"result": result, "ledger_update": update}))


def executor(tmp_path, model):
    config = LW.LongConfig(default_model="fake", models=(LW.LongModel("fake", 8192),),
                           ram_budget_gib=32, prompt_cache_mib=0,
                           ledger_budget_tokens=600, max_output_tokens=200)
    return LW.LongWorkloadExecutor(root=tmp_path, evidence_dir=tmp_path, client=model, config=config)


def run(ex):
    return ex.run("job", "count warnings\n---\n" + "note x\n" * 14000,
                  cancel_requested=lambda: False, progress_callback=lambda event: None)


def ledger_in(prompt):
    return json.loads(prompt.split("LEDGER (from earlier steps):\n")[1].split("\n\n")[0])


def test_maps_never_read_or_checkpoint_other_parts_facts(tmp_path):
    model = LeakingModel()
    result = run(executor(tmp_path, model))
    assert result["status"] == "completed" and len(model.values) > 1
    assert all(ledger_in(p) == json.loads(Ledger().render()) for p in model.prompts)
    records = CheckpointLog(tmp_path / "long/job/checkpoints").events()
    maps = [e["payload"] for e in records if e["event"] == "task_completed"
            and e["payload"]["kind"] == "map"]
    assert all(m["ledger"] == Ledger().to_dict() for m in maps)
    assert all((tmp_path / "long/job/outputs" / (m["output_sha256"] + ".txt")).is_file()
               for m in maps)


def test_live_style_count_leak_cannot_inflate_the_sum(tmp_path):
    model = LeakingModel()
    result = run(executor(tmp_path, model))
    assert len(model.values) > 1
    assert result["answer"].split("\n\n")[0] == str(sum(model.values))


def test_resume_after_crash_does_not_carry_map_facts(tmp_path):
    first = LeakingModel(crash=True)
    with pytest.raises(KeyboardInterrupt):
        run(executor(tmp_path, first))
    resumed = LeakingModel()
    result = run(executor(tmp_path, resumed))
    assert result["status"] == "completed"
    assert all(ledger_in(p)["facts"] == [] for p in resumed.prompts)
    assert result["answer"].split("\n\n")[0] == str(sum(first.values + resumed.values))


def test_answer_keeps_part_values_when_reduce_omits_the_breakdown(tmp_path):
    model = LeakingModel()  # reduce deliberately returns only the scalar total
    result = run(executor(tmp_path, model))
    assert "Per-part results:" in result["answer"]
    for index, value in enumerate(model.values, 1):
        assert f"map-{index:04d}:\npart_value: {value}" in result["answer"]
    # A completed checkpoint replay must deliver identical evidence without new model calls.
    replay = LeakingModel()
    assert run(executor(tmp_path, replay))["answer"] == result["answer"]
    assert replay.prompts == []


def test_isolated_task_leaves_existing_ledger_unchanged(tmp_path):
    class Model:
        def count_tokens(self, text):
            return len(text) // 4

        def generate(self, *, prompt, **kwargs):
            if "(map)" in prompt:
                assert ledger_in(prompt)["facts"] == []
            return json.dumps({"result": "ok", "ledger_update": {"add_facts": ["kept"]}})

    runner = ShardRunner(tmp_path, Model(), RunLimits(8192, 600), isolated_kinds={"map"})
    state = runner.start("o", "mixed", [ShardTask("step", "step", "remember"),
                                         ShardTask("map", "map", "independent")])
    assert state.completed["map"]["ledger"] == state.completed["step"]["ledger"]
