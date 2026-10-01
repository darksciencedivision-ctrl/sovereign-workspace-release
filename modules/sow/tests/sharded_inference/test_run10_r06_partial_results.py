"""Qualification: measurements survive a run that is cut off (a driver caps and kills it)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sovereign"))

from sovereign_product import qualification as Q  # noqa: E402
from sovereign_product import qualification_harness as QH  # noqa: E402
from test_run10_r06_harness import FakeProduct  # noqa: E402


class Instant(FakeProduct):
    """Every submitted job is already completed."""

    def health(self):
        return {}

    def _call(self, method, path, body=None):
        if path == "/v1/message":
            return 202, {"job_id": "j1", "status": "completed", "metrics": {"tokens": 5}}
        return super()._call(method, path, body)


def test_quick_qualification_reports_every_run_to_the_checkpoint(monkeypatch):
    monkeypatch.setattr(QH, "ProductClient", lambda base_url: Instant())
    profile = {"id": "p", "backend": "llama.cpp", "primary_model": "m",
               "ladder": {"repetitions": 1, "context_tokens": [1000], "concurrency": [1]}}
    seen = []
    results = QH.run_qualification(profile, base_url="http://127.0.0.1:1", ollama_url="",
                                   include_deep=False, log=lambda message: None,
                                   checkpoint=lambda runs: seen.append(len(runs)))
    assert seen == list(range(1, len(results["runs"]) + 1)) and len(seen) >= 4


def test_long_qualification_reports_every_run_to_the_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(QH, "ProductClient", lambda base_url: Instant())
    profile = {"id": "p", "backend": "llama.cpp", "primary_model": "m",
               "ladder": {"input_tokens": [0, 400], "repetitions": 1}}
    seen = []
    results = QH.run_long_qualification(profile, base_url="http://127.0.0.1:1", inbox_dir=tmp_path,
                                        poll=0.0, log=lambda message: None,
                                        checkpoint=lambda runs: seen.append(len(runs)))
    assert seen == [1, 2] and len(results["runs"]) == 2


def test_partial_results_are_written_atomically_and_marked(tmp_path):
    out = tmp_path / "r3.results.json"
    Q.write_partial_results(out, "profile-x", [{"scenario": "long_plan", "status": "completed"}])
    partial = json.loads(Path(str(out) + ".partial").read_text(encoding="utf-8"))
    assert partial["partial"] is True and partial["profile"] == "profile-x"
    assert partial["schema"] == Q.RESULTS_SCHEMA and partial["runs"][0]["scenario"] == "long_plan"
    assert [p.name for p in tmp_path.iterdir()] == ["r3.results.json.partial"]
