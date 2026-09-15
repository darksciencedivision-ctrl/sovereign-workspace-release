"""CR-038 — behavior-preserving extraction of a pure phase from a large orchestration function,
pinned by a characterization test. Here: _normalize_response_format, extracted verbatim from
OllamaClient.generate (which dropped from 124 to 110 branch points)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOV_ROOT = Path(__file__).resolve().parents[4] / "modules" / "sovereign"
SOV = SOV_ROOT / "sovereign_product"
for import_root in (SOV_ROOT, SOV):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import model_client as mc  # noqa: E402
import cycle_runner_v3 as cycle  # noqa: E402
from sovereign_product import executors as legacy_executors  # noqa: E402
from sovereign_product import semantic_deep  # noqa: E402
from synthesis import live_orchestrator  # noqa: E402


def test_cr038_none_and_json_string():
    assert mc._normalize_response_format(None) is None
    assert mc._normalize_response_format("json") == "json"


def test_cr038_invalid_string_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format("xml")


def test_cr038_mapping_is_copied_and_validated():
    src = {"type": "object", "properties": {"a": {"type": "string"}}, "nums": [1, 2.5, True, None]}
    out = mc._normalize_response_format(src)
    assert out == src and out is not src  # a copy, not the caller's object


def test_cr038_non_string_key_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({1: "x"})


def test_cr038_non_finite_float_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({"v": float("inf")})


def test_cr038_non_json_value_rejected():
    with pytest.raises(ValueError):
        mc._normalize_response_format({"v": object()})


def test_cr038_non_mapping_type_rejected():
    with pytest.raises(TypeError):
        mc._normalize_response_format(12345)


def test_cr038_generate_still_uses_the_extraction(tmp_path):
    # end-to-end: a bad response_format is rejected by generate() via the extracted helper,
    # identical to before the extraction.
    client = mc.OllamaClient(session=object())
    with pytest.raises(ValueError):
        client.generate(model="m", prompt="hi", options={}, response_format="xml")


def test_cr038_cycle_identity_and_artifacts_are_one_deterministic_phase(tmp_path):
    topic_file = tmp_path / "topic.txt"
    topic_file.write_text("[TOPIC session_id=s] retained topic [/TOPIC]", encoding="utf-8")
    paths = {
        "topic_file": topic_file,
        "synthesis_path": tmp_path / "synthesis.json",
        "praxis_answer_path": tmp_path / "praxis.json",
        "sovereign_voice_path": tmp_path / "voice.md",
        "praxis_report_path": tmp_path / "report.md",
    }
    args = SimpleNamespace(
        topic="",
        session_id="session-1",
        safe_theorem_mode=False,
        safe_theorem_manifest="",
    )
    plan = cycle.build_cycle_run_plan(args, tmp_path, paths)
    assert plan.topic == "retained topic"
    assert plan.session_id == "session-1"
    assert plan.artifacts["dialog_session_path"].endswith("session-1_dialog.txt")


def test_cr038_legacy_executor_prepares_one_validated_launch_plan(tmp_path):
    plan = legacy_executors._prepare_legacy_deep_execution(
        root=tmp_path,
        artifact_root=tmp_path / "artifacts",
        python_executable=sys.executable,
        runner_path=tmp_path / "runner.py",
        session_id="session-1",
        topic="bounded topic",
        timeout_seconds=5,
    )
    assert plan.command[-2:] == ("--session-id", "session-1")
    assert plan.artifacts["result"].startswith("artifacts/deep/session-1/")
    with pytest.raises(ValueError, match="positive"):
        legacy_executors._prepare_legacy_deep_execution(
            root=tmp_path,
            artifact_root=tmp_path / "artifacts",
            python_executable=sys.executable,
            runner_path=tmp_path / "runner.py",
            session_id="session-1",
            topic="bounded topic",
            timeout_seconds=0,
        )


def test_cr038_semantic_request_phase_validates_and_seals_record():
    session_id, job_id, topic, options = semantic_deep._validate_semantic_execution_request(
        session_id="session-1",
        job_id="job-1",
        topic="question",
        options={"temperature": 0},
        timeout_seconds=30,
    )
    record = semantic_deep._semantic_request_record(
        session_id=session_id,
        job_id=job_id,
        execution_id="deep-1",
        topic=topic,
        model_slate={"member_1": "model"},
        model_provenance={"status": "resolved"},
        base_options={},
        runtime_options=options,
        timeout_seconds=30,
        evidence_supplied=False,
        evidence_builder_configured=False,
        started_at="2026-09-15T00:00:00Z",
    )
    assert record["record_type"] == "semantic_deep_request"
    assert len(record["record_sha256"]) == 64
    with pytest.raises(ValueError, match="topic"):
        semantic_deep._validate_semantic_execution_request(
            session_id="session-1",
            job_id=None,
            topic="",
            options=None,
            timeout_seconds=30,
        )


def test_cr038_live_orchestrator_resolves_models_and_deduplicates_warmup(monkeypatch):
    monkeypatch.setattr(live_orchestrator, "runtime_value", lambda key, manifest: "http://runtime")
    monkeypatch.setattr(live_orchestrator, "model_name", lambda role, manifest: f"model-{role}")
    args = SimpleNamespace(
        ollama_base_url="",
        model_a="explicit",
        model_b="",
        model_c="same",
        model_synth="same",
    )
    live_orchestrator._resolve_runtime_models(args, {})
    assert args.ollama_base_url == "http://runtime"
    assert args.model_a == "explicit"
    assert args.model_b == "model-ADVERSARIAL_CHALLENGER"
    assert live_orchestrator._warmup_model_names(args) == (
        "explicit",
        "model-ADVERSARIAL_CHALLENGER",
        "same",
    )
