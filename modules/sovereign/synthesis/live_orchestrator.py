#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
for candidate in (SCRIPT_DIR, ROOT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import synth_king as base
from debate_output_normalizer import normalize_debate_turn
from claim_arbitrator import analyze_dialog, challenge_answered_by, classify_claim_similarity, persist_arbitration_stub
from semantic_claim_matching import compute_semantic_similarity, load_semantic_matching_config
from system_manifest import load_system_manifest, model_name, runtime_value
from runtime_integrity.provenance_stamp import attach_canonical_provenance, build_canonical_provenance

try:
    from evaluation.contract import enforce_contract
    from evaluation.contract_trace import trace_contract_status_from_mapping
    from evaluation.integrity import IntegrityGuard, IntegrityViolation
except ImportError:  # pragma: no cover - fallback for direct module execution
    from contract import enforce_contract
    from contract_trace import trace_contract_status_from_mapping
    from integrity import IntegrityGuard, IntegrityViolation

# Phase 20.2 — Contradiction-Aware Synthesis (opt-in via env var)
try:
    from contradiction_synthesis_loader import ContradictionSynthesisLoader as _ContradictionSynthesisLoader
except ImportError:
    _ContradictionSynthesisLoader = None  # type: ignore[assignment,misc]

# Phase 20.4 — Pressure-Adaptive Routing (opt-in via env var)
try:
    from pressure_routing_loader import PressureRoutingLoader as _PressureRoutingLoader
except ImportError:
    _PressureRoutingLoader = None  # type: ignore[assignment,misc]

LIVE_EXECUTION_MODE = "LIVE"
LEARNING_TELEMETRY_SCHEMA_VERSION = "22.0B"
# G-SV 0.90 per V5.0 standing approval 2 (P2.1 evidence floor 0.895415 — never below);
# was 0.95 (calibrated from 0.97 for LLM section-reordering variance); unrelated validation unchanged.
STRUCTURAL_VARIANCE_COMBINED_THRESHOLD = 0.90
STRUCTURAL_VARIANCE_CLAIM_THRESHOLD = 0.90
SEMANTIC_AUDIT_PASS_LOWER = STRUCTURAL_VARIANCE_COMBINED_THRESHOLD
SEMANTIC_AUDIT_PASS_UPPER = 0.965
SEMANTIC_AUDIT_FAIL_LOWER = 0.93
SEMANTIC_AUDIT_FAIL_UPPER = STRUCTURAL_VARIANCE_COMBINED_THRESHOLD
SEMANTIC_AUDIT_STATUS_PENDING = "pending_manual_review"
SEMANTIC_AUDIT_REASON_BORDERLINE_PASS = "borderline_pass_review_band"
SEMANTIC_AUDIT_REASON_BORDERLINE_FAIL = "borderline_fail_review_band"
PLACEHOLDER_MARKERS = (
    "No explicit claim provided.",
    "No explicit challenge provided.",
    "No additional evidence provided.",
    "Unknown or not explicitly stated.",
    "Synthesis incomplete due to missing components.",
)

# Phase 2.5F: latency telemetry schema version
LATENCY_TELEMETRY_SCHEMA_VERSION = "2.5F"
SEMANTIC_AUDIT_COMPLETE = "COMPLETE"
SEMANTIC_AUDIT_PARTIAL = "PARTIAL"
SEMANTIC_AUDIT_FAILED_PRE_SYNTHESIS = "FAILED_PRE_SYNTHESIS"
SEMANTIC_AUDIT_NOT_APPLICABLE = "NOT_APPLICABLE"

SYNTHESIS_STATUS_COMPLETE = "COMPLETE"
SYNTHESIS_STATUS_PARTIAL = "PARTIAL"
SYNTHESIS_STATUS_FAILED = "FAILED"
SYNTHESIS_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

# Phase 2.5F: default timeout baseline (seconds)
DEFAULT_TURN_TIMEOUT_SEC = 225


def _resolve_turn_timeout_sec(model: str, role: str, default: int = DEFAULT_TURN_TIMEOUT_SEC) -> int:
    """
    Phase 2.5F: Resolve turn timeout for a specific model/role.
    Priority chain: per-model > per-role > global > default (225s).
    """
    # Per-model env vars
    model_key = model.replace(":", "_").replace("-", "_").replace(".", "_").upper()
    model_env = f"SOVEREIGN_{model_key}_TIMEOUT_SEC"
    val = os.environ.get(model_env, "").strip()
    if val.isdigit():
        return int(val)

    # Specific known model timeout
    if "deepseek" in model.lower() and "r1" in model.lower():
        val = os.environ.get("SOVEREIGN_DEEPSEEK_R1_TIMEOUT_SEC", "").strip()
        if val.isdigit():
            return int(val)

    # Per-role env var: PRIMARY_REASONER
    if "PRIMARY" in role.upper() or "REASONER" in role.upper():
        val = os.environ.get("SOVEREIGN_PRIMARY_REASONER_TIMEOUT_SEC", "").strip()
        if val.isdigit():
            return int(val)

    # Global env var
    val = os.environ.get("SOVEREIGN_TURN_TIMEOUT_SEC", "").strip()
    if val.isdigit():
        return int(val)

    return default


def _run_warmup(
    model: str,
    ollama_base: str,
    timeout_sec: int = 90,
) -> dict[str, Any]:
    """
    Phase 2.5F: Run a lightweight warmup invocation for a model.
    Status values: PASS, TIMEOUT, ERROR, SKIPPED.
    Warmup output never enters the debate transcript.
    Warmup failure is non-fatal.
    """
    if os.environ.get("SOVEREIGN_ENABLE_MODEL_WARMUP", "").strip() != "1":
        return {"model": model, "status": "SKIPPED", "reason": "warmup_disabled"}

    warmup_timeout = int(os.environ.get("SOVEREIGN_WARMUP_TIMEOUT_SEC", str(timeout_sec)))
    warmup_prompt = "Respond with one word: ready"

    started = time.monotonic()
    try:
        _ = base.ollama_generate(
            model=model,
            prompt=warmup_prompt,
            ollama_base=ollama_base,
            temperature=0.0,
            max_tokens=8,
            seed=0,
            timeout_sec=warmup_timeout,
        )
        duration = round(time.monotonic() - started, 3)
        return {"model": model, "status": "PASS", "duration_sec": duration}
    except Exception as exc:
        duration = round(time.monotonic() - started, 3)
        exc_str = str(exc).lower()
        if "timeout" in exc_str or "timed out" in exc_str:
            return {"model": model, "status": "TIMEOUT", "duration_sec": duration}
        return {"model": model, "status": "ERROR", "duration_sec": duration, "error": str(exc)[:200]}


def _latency_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Phase 2.5F: Compute latency distribution summary from timing records."""
    durations = [r.get("duration_sec", 0.0) for r in records if r.get("duration_sec") is not None]
    if not durations:
        return {"count": 0, "total": 0.0, "min": None, "max": None, "mean": None}
    return {
        "count": len(durations),
        "total": round(sum(durations), 3),
        "min": round(min(durations), 3),
        "max": round(max(durations), 3),
        "mean": round(sum(durations) / len(durations), 3),
    }


def _write_turn_latency_telemetry(
    runtime_dir: Path,
    session_id: str,
    latency_records: list[dict[str, Any]],
    timeout_config: dict[str, Any] | None = None,
) -> str:
    """
    Phase 2.5F: Write turn_latency_telemetry.json to the session runtime directory.
    Written on both success and exception paths.
    """
    distribution = _latency_distribution(latency_records)
    telemetry = {
        "schema_version": LATENCY_TELEMETRY_SCHEMA_VERSION,
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "record_count": len(latency_records),
        "distribution": distribution,
        "timeout_config": timeout_config or {},
        "records": latency_records,
    }
    out_path = runtime_dir / "turn_latency_telemetry.json"
    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(telemetry, indent=2), encoding="utf-8")
    except OSError:
        pass
    return str(out_path)


def _paths(root: Path, session_id: str) -> dict[str, Path]:
    runtime_dir = root / "output" / "live_runtime" / session_id
    return {
        "runtime_dir": runtime_dir,
        "turn_dir": runtime_dir / "turns",
        "turn_manifest": runtime_dir / "turn_manifest.json",
        "role_map": runtime_dir / "role_model_mapping.json",
        "activation": runtime_dir / "live_activation_report.json",
        "cognitive": runtime_dir / "cognitive_validation_report.json",
        "interaction": runtime_dir / "interaction_validation_report.json",
        "probes": runtime_dir / "validation_probes.json",
        "structural_variance_telemetry": runtime_dir / "structural_variance_telemetry.json",
        "semantic_audit_record": runtime_dir / "semantic_audit_record.json",
        "synthesis_outcome_record": runtime_dir / "synthesis_outcome_record.json",
    }


def _slug(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(text or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return (slug or "item")[:max_len]


def _broker_metadata(session_id: str) -> dict[str, str]:
    broker_only = str(os.environ.get("SOVEREIGN_BROKER_ONLY", "")).strip()
    broker_session_id = str(os.environ.get("SOVEREIGN_BROKER_SESSION_ID", "")).strip()
    broker_script = str(os.environ.get("SOVEREIGN_BROKER_SCRIPT", "")).strip()
    broker_root = str(os.environ.get("SOVEREIGN_BROKER_ROOT", "")).strip()
    if broker_only != "1":
        raise base.SynthesisError("LIVE execution requires broker-owned invocation (SOVEREIGN_BROKER_ONLY=1).")
    if broker_session_id != session_id:
        raise base.SynthesisError(
            f"LIVE execution requires broker session ownership; expected session_id={session_id}, got {broker_session_id or '[missing]'}."
        )
    if not broker_script:
        raise base.SynthesisError("LIVE execution requires broker metadata (SOVEREIGN_BROKER_SCRIPT missing).")
    if not broker_root:
        raise base.SynthesisError("LIVE execution requires broker metadata (SOVEREIGN_BROKER_ROOT missing).")
    return {
        "broker_only": broker_only,
        "broker_session_id": broker_session_id,
        "broker_script": broker_script,
        "broker_root": broker_root,
    }


def _runtime_provenance(root: Path, broker: dict[str, str]) -> dict[str, Any]:
    provenance = build_canonical_provenance(root, broker.get("broker_root", ""))
    if provenance["runtime_root"] == "" or provenance["broker_root"] == "":
        raise base.SynthesisError("LIVE execution requires explicit runtime_root and broker_root provenance.")
    if provenance["root_classification"] != "ACTIVE_D_ROOT":
        raise base.SynthesisError(
            f"LIVE execution requires ACTIVE_D_ROOT provenance; observed {provenance['root_classification'] or '[missing]'}."
        )
    if provenance["broker_root_verified"] is not True:
        raise base.SynthesisError(
            f"LIVE execution requires verified broker root lineage; runtime_root={provenance['runtime_root']} broker_root={provenance['broker_root']}."
        )
    return provenance


def _template_hits(text: str) -> list[str]:
    normalized = base.normalize_text(text)
    if not normalized:
        return []
    hits = [marker for marker in PLACEHOLDER_MARKERS if marker in normalized]
    if re.search(r"\bbootstrap-[a-z0-9_-]+\b", normalized, re.IGNORECASE):
        hits.append("bootstrap-marker")
    if "[FALLBACK_MODEL=" in normalized:
        hits.append("fallback-model-marker")
    return hits


def _role_mapping(hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for wing_name in ("alpha", "beta"):
        for index, role_cfg in enumerate(hierarchy.get(f"{wing_name}_wing", []), start=1):
            rows.append(
                {
                    "stage_group": f"{wing_name}_wing",
                    "wing": wing_name,
                    "position_index": index,
                    "role": str(role_cfg.get("role", "")).strip(),
                    "model": str(role_cfg.get("model", "")).strip(),
                    "stance": str(role_cfg.get("stance", "")).strip(),
                }
            )
    for wing_name in ("alpha", "beta"):
        rec_cfg = hierarchy.get("wing_reconciliation", {}).get(wing_name, {})
        rows.append(
            {
                "stage_group": "wing_reconciliation",
                "wing": wing_name,
                "role": str(rec_cfg.get("role", "")).strip(),
                "model": str(rec_cfg.get("model", "")).strip(),
            }
        )
    for channel_name in ("critique", "cross_exam"):
        cfg = hierarchy.get("cross_channel", {}).get(channel_name, {})
        rows.append(
            {
                "stage_group": "cross_channel",
                "channel": channel_name,
                "role": str(cfg.get("role", "")).strip(),
                "model": str(cfg.get("model", "")).strip(),
            }
        )
    king_cfg = hierarchy.get("king_synthesizer", {})
    rows.append(
        {
            "stage_group": "king_synthesizer",
            "role": str(king_cfg.get("role", "")).strip(),
            "model": str(king_cfg.get("model", "")).strip(),
        }
    )
    return rows


def _write_role_map(
    paths: dict[str, Path],
    session_id: str,
    topic: str,
    hierarchy: dict[str, Any],
    ollama_base_url: str,
    broker: dict[str, str],
    provenance: dict[str, Any],
) -> str:
    payload = {
        "schema_version": "1.0",
        "generated_at": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "topic": topic,
        "provider": {"name": "ollama", "base_url": str(ollama_base_url).strip()},
        "broker": broker,
        "mappings": _role_mapping(hierarchy),
    }
    base.write_json_atomic(paths["role_map"], attach_canonical_provenance(payload, provenance["runtime_root"], provenance["broker_root"]))
    return str(paths["role_map"])


def _persist_turn(paths: dict[str, Path], record: dict[str, Any], sink: list[dict[str, Any]]) -> None:
    file_name = "__".join(
        part
        for part in [
            _slug(str(record.get("stage", ""))),
            _slug(str(record.get("wing_name", ""))) if record.get("wing_name") else "",
            f"r{int(record['round_number']):02d}" if record.get("round_number") is not None else "",
            f"a{int(record.get('attempt', 0) or 0):02d}",
            _slug(str(record.get("role", ""))),
        ]
        if part
    ) + ".json"
    artifact_path = paths["turn_dir"] / file_name
    base.write_json_atomic(artifact_path, record)
    persisted = dict(record)
    persisted["artifact_path"] = str(artifact_path)
    sink.append(persisted)


def _write_turn_manifest(
    paths: dict[str, Path],
    session_id: str,
    topic: str,
    turns: list[dict[str, Any]],
    provenance: dict[str, Any],
) -> str:
    payload = {
        "schema_version": "1.0",
        "generated_at": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "topic": topic,
        "turn_count": len(turns),
        "records": turns,
    }
    base.write_json_atomic(paths["turn_manifest"], attach_canonical_provenance(payload, provenance["runtime_root"], provenance["broker_root"]))
    return str(paths["turn_manifest"])


def _runtime_contract_signal_path(root: Path, session_id: str) -> str:
    return str(root / "evaluation" / "verification" / "runtime_signals" / session_id / "contract_executed.json")


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _normalize_contract_status(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"VALID", "DEGRADED", "FAILED"}:
        return text
    return "UNKNOWN"


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _collect_model_route(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    route: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for turn in turns:
        role = str(turn.get("role", "")).strip()
        model = str(turn.get("model", "")).strip()
        if not role and not model:
            continue
        key = (role, model)
        if key in seen:
            continue
        seen.add(key)
        route.append({"role": role, "model": model})
    return route


def _turn_stage_seen(turns: list[dict[str, Any]], stage_name: str) -> bool:
    return any(str(turn.get("stage", "")).strip() == stage_name for turn in turns)


def _report_failures(report: dict[str, Any] | None) -> list[str]:
    failures = report.get("failures", []) if isinstance(report, dict) else []
    if not isinstance(failures, list):
        return []
    return [str(item).strip() for item in failures if str(item).strip()]


def _primary_failure_reason(
    *,
    structural_variance: dict[str, Any] | None = None,
    contract_report: dict[str, Any] | None = None,
    interaction_report: dict[str, Any] | None = None,
    activation_report: dict[str, Any] | None = None,
    explicit_error: str = "",
) -> str | None:
    candidates = [
        str((structural_variance or {}).get("failure_reason", "")).strip(),
        str((contract_report or {}).get("contract_message", "")).strip(),
        *(_report_failures(interaction_report)),
        *(_report_failures(activation_report)),
        explicit_error.strip(),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _semantic_audit_status(
    *,
    structural_variance: dict[str, Any] | None,
    king_synthesis_reached: bool,
    cognitive_validation_reached: bool,
) -> str:
    structural_variance = structural_variance if isinstance(structural_variance, dict) else {}
    if structural_variance:
        if structural_variance.get("probe_completed") is True:
            return SEMANTIC_AUDIT_COMPLETE
        if king_synthesis_reached:
            return SEMANTIC_AUDIT_PARTIAL
    if king_synthesis_reached:
        return SEMANTIC_AUDIT_PARTIAL
    if cognitive_validation_reached:
        return SEMANTIC_AUDIT_FAILED_PRE_SYNTHESIS
    return SEMANTIC_AUDIT_NOT_APPLICABLE


def _build_learning_limitations(
    *,
    semantic_status: str,
    synthesis_status: str,
    structural_variance: dict[str, Any] | None,
    activation_report: dict[str, Any] | None,
    interaction_report: dict[str, Any] | None,
    explicit_error: str = "",
) -> list[str]:
    structural_variance = structural_variance if isinstance(structural_variance, dict) else {}
    limitations: list[str] = []
    if semantic_status == SEMANTIC_AUDIT_FAILED_PRE_SYNTHESIS:
        limitations.append("semantic_evaluation_not_reached")
    if semantic_status == SEMANTIC_AUDIT_PARTIAL:
        limitations.append("semantic_evaluation_incomplete")
    if synthesis_status == SYNTHESIS_STATUS_NOT_APPLICABLE:
        limitations.append("final_synthesis_not_reached")
    elif synthesis_status == SYNTHESIS_STATUS_PARTIAL:
        limitations.append("final_synthesis_incomplete")
    elif synthesis_status == SYNTHESIS_STATUS_FAILED:
        limitations.append("final_synthesis_failed")
    probe_error = str(structural_variance.get("probe_error", "")).strip()
    if probe_error:
        limitations.append(probe_error)
    failure_reason = str(structural_variance.get("failure_reason", "")).strip()
    if failure_reason:
        limitations.append(failure_reason)
    limitations.extend(_report_failures(interaction_report))
    limitations.extend(_report_failures(activation_report))
    if explicit_error.strip():
        limitations.append(explicit_error.strip())
    return _dedupe_strings(limitations)


def _structural_variance_failure_reason(
    *,
    anchor_ok: bool,
    combined_cosine: float | None,
    claim_cosine: float | None,
) -> str:
    if not anchor_ok:
        return "anchor_contradiction"
    if combined_cosine is None:
        return "combined_cosine_missing"
    if combined_cosine < STRUCTURAL_VARIANCE_COMBINED_THRESHOLD:
        return "combined_cosine_below_threshold"
    if claim_cosine is None:
        return "claim_cosine_missing"
    if claim_cosine < STRUCTURAL_VARIANCE_CLAIM_THRESHOLD:
        return "claim_cosine_below_threshold"
    return ""


def _format_optional_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _empty_semantic_audit_state() -> dict[str, Any]:
    return {
        "flagged": False,
        "audit_reason": "",
        "audit_status": "",
        "borderline_pass": False,
        "borderline_fail": False,
        "trigger_metrics": [],
    }


def _extract_semantic_audit_conclusion(text: str) -> dict[str, str]:
    for section_names, source in (
        (["FINAL_SYNTHESIS"], "final_synthesis"),
        (["RESOLUTION"], "resolution"),
        (["CONCLUSION"], "conclusion"),
        (["CLAIM_SUMMARY"], "claim_summary"),
        (["CLAIM"], "claim"),
    ):
        extracted = base.extract_section(text, section_names).strip()
        if extracted:
            return {
                "text": extracted,
                "source": source,
            }
    return {
        "text": "",
        "source": "",
    }


def _semantic_audit_trigger_metrics(
    *,
    combined_cosine: float | None,
    claim_cosine: float | None,
    lower: float,
    upper: float,
) -> list[str]:
    triggered: list[str] = []
    if combined_cosine is not None and lower <= combined_cosine < upper:
        triggered.append("combined_cosine")
    if claim_cosine is not None and lower <= claim_cosine < upper:
        triggered.append("claim_cosine")
    return triggered


def _build_semantic_audit_state(
    *,
    actual_king: str,
    structural_probe_output: str,
    passed: bool,
    anchor_ok: bool,
    combined_cosine: float | None,
    claim_cosine: float | None,
) -> dict[str, Any]:
    semantic_audit = _empty_semantic_audit_state()
    if passed:
        triggered_metrics = _semantic_audit_trigger_metrics(
            combined_cosine=combined_cosine,
            claim_cosine=claim_cosine,
            lower=SEMANTIC_AUDIT_PASS_LOWER,
            upper=SEMANTIC_AUDIT_PASS_UPPER,
        )
        if triggered_metrics:
            semantic_audit.update(
                {
                    "flagged": True,
                    "audit_reason": f"{SEMANTIC_AUDIT_REASON_BORDERLINE_PASS}:{','.join(triggered_metrics)}",
                    "audit_status": SEMANTIC_AUDIT_STATUS_PENDING,
                    "borderline_pass": True,
                    "trigger_metrics": triggered_metrics,
                }
            )
    elif anchor_ok:
        triggered_metrics = _semantic_audit_trigger_metrics(
            combined_cosine=combined_cosine,
            claim_cosine=claim_cosine,
            lower=SEMANTIC_AUDIT_FAIL_LOWER,
            upper=SEMANTIC_AUDIT_FAIL_UPPER,
        )
        if triggered_metrics:
            semantic_audit.update(
                {
                    "flagged": True,
                    "audit_reason": f"{SEMANTIC_AUDIT_REASON_BORDERLINE_FAIL}:{','.join(triggered_metrics)}",
                    "audit_status": SEMANTIC_AUDIT_STATUS_PENDING,
                    "borderline_fail": True,
                    "trigger_metrics": triggered_metrics,
                }
            )

    baseline_conclusion = _extract_semantic_audit_conclusion(actual_king)
    perturbed_conclusion = _extract_semantic_audit_conclusion(structural_probe_output)
    if baseline_conclusion["text"]:
        semantic_audit["baseline_conclusion_text"] = baseline_conclusion["text"]
        semantic_audit["baseline_conclusion_source"] = baseline_conclusion["source"]
    if perturbed_conclusion["text"]:
        semantic_audit["perturbed_conclusion_text"] = perturbed_conclusion["text"]
        semantic_audit["perturbed_conclusion_source"] = perturbed_conclusion["source"]
    return semantic_audit


def _build_structural_variance_summary_counters(structural_variance: dict[str, Any]) -> dict[str, int]:
    semantic_audit = (
        structural_variance.get("semantic_audit")
        if isinstance(structural_variance.get("semantic_audit"), dict)
        else _empty_semantic_audit_state()
    )
    passed = bool(structural_variance.get("passed"))
    return {
        "total_runs": 1,
        "structural_variance_passes": int(passed),
        "structural_variance_fails": int(not passed),
        "semantic_audit_flagged": int(bool(semantic_audit.get("flagged"))),
        "borderline_passes": int(bool(semantic_audit.get("borderline_pass"))),
        "borderline_fails": int(bool(semantic_audit.get("borderline_fail"))),
    }


def _build_structural_variance_telemetry(
    *,
    session_id: str,
    structural_variance: dict[str, Any],
    model_metadata: dict[str, Any] | None = None,
    stage_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comparison = structural_variance.get("comparison")
    telemetry = {
        "schema_version": "1.0",
        "timestamp": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "run_id": session_id,
        "anchor_ok": bool(structural_variance.get("anchor_ok")),
        "combined_cosine": structural_variance.get("combined_cosine"),
        "claim_cosine": structural_variance.get("claim_cosine"),
        "combined_threshold": STRUCTURAL_VARIANCE_COMBINED_THRESHOLD,
        "claim_threshold": STRUCTURAL_VARIANCE_CLAIM_THRESHOLD,
        "threshold_used": {
            "combined_cosine": STRUCTURAL_VARIANCE_COMBINED_THRESHOLD,
            "claim_cosine": STRUCTURAL_VARIANCE_CLAIM_THRESHOLD,
        },
        "passed": bool(structural_variance.get("passed")),
        "failure_reason": str(structural_variance.get("failure_reason") or ""),
    }
    if isinstance(comparison, dict):
        telemetry["anchor_classification"] = comparison.get("anchor_classification")
        telemetry["changed_sections"] = comparison.get("changed_sections") or []
    semantic_audit = structural_variance.get("semantic_audit")
    if isinstance(semantic_audit, dict):
        telemetry["semantic_audit"] = {
            "flagged": bool(semantic_audit.get("flagged")),
            "audit_reason": str(semantic_audit.get("audit_reason") or ""),
            "audit_status": str(semantic_audit.get("audit_status") or ""),
            "borderline_pass": bool(semantic_audit.get("borderline_pass")),
            "borderline_fail": bool(semantic_audit.get("borderline_fail")),
            "trigger_metrics": list(semantic_audit.get("trigger_metrics") or []),
        }
    telemetry["summary_counters"] = _build_structural_variance_summary_counters(structural_variance)
    if model_metadata:
        telemetry["model_metadata"] = dict(model_metadata)
    if stage_metadata:
        telemetry["stage_metadata"] = dict(stage_metadata)
    return telemetry


def _write_structural_variance_telemetry(paths: dict[str, Path], telemetry: dict[str, Any]) -> str:
    base.write_json_atomic(paths["structural_variance_telemetry"], telemetry)
    return str(paths["structural_variance_telemetry"])


def _build_semantic_audit_record(
    *,
    session_id: str,
    structural_variance: dict[str, Any],
    model_metadata: dict[str, Any] | None = None,
    stage_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    semantic_audit = structural_variance.get("semantic_audit")
    if not isinstance(semantic_audit, dict) or not bool(semantic_audit.get("flagged")):
        return {}
    record = {
        "schema_version": "1.0",
        "timestamp": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "run_id": session_id,
        "combined_cosine": structural_variance.get("combined_cosine"),
        "claim_cosine": structural_variance.get("claim_cosine"),
        "passed": bool(structural_variance.get("passed")),
        "audit_reason": str(semantic_audit.get("audit_reason") or ""),
        "audit_status": str(semantic_audit.get("audit_status") or SEMANTIC_AUDIT_STATUS_PENDING),
        "trigger_metrics": list(semantic_audit.get("trigger_metrics") or []),
        "borderline_pass": bool(semantic_audit.get("borderline_pass")),
        "borderline_fail": bool(semantic_audit.get("borderline_fail")),
    }
    if semantic_audit.get("baseline_conclusion_text"):
        record["baseline_conclusion_text"] = semantic_audit["baseline_conclusion_text"]
        record["baseline_conclusion_source"] = semantic_audit.get("baseline_conclusion_source")
    if semantic_audit.get("perturbed_conclusion_text"):
        record["perturbed_conclusion_text"] = semantic_audit["perturbed_conclusion_text"]
        record["perturbed_conclusion_source"] = semantic_audit.get("perturbed_conclusion_source")
    if model_metadata:
        record["model_metadata"] = dict(model_metadata)
    if stage_metadata:
        record["stage_metadata"] = dict(stage_metadata)
    return record


def _write_semantic_audit_record(paths: dict[str, Path], record: dict[str, Any]) -> str:
    base.write_json_atomic(paths["semantic_audit_record"], record)
    return str(paths["semantic_audit_record"])


def _build_learning_semantic_audit_record(
    *,
    session_id: str,
    runtime_root: str,
    broker_root: str,
    contract_status: str,
    structural_variance: dict[str, Any] | None,
    synthesis_artifact: str | None,
    model_route: list[dict[str, str]],
    activation_report: dict[str, Any] | None,
    interaction_report: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    explicit_error: str = "",
    model_metadata: dict[str, Any] | None = None,
    stage_metadata: dict[str, Any] | None = None,
    contract_report: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structural_variance = structural_variance if isinstance(structural_variance, dict) else {}
    semantic_audit = (
        structural_variance.get("semantic_audit")
        if isinstance(structural_variance.get("semantic_audit"), dict)
        else _empty_semantic_audit_state()
    )
    king_synthesis_reached = _turn_stage_seen(turns, "king_synthesis")
    cognitive_validation_reached = isinstance(interaction_report, dict) or isinstance(activation_report, dict)
    semantic_status = _semantic_audit_status(
        structural_variance=structural_variance,
        king_synthesis_reached=king_synthesis_reached,
        cognitive_validation_reached=cognitive_validation_reached,
    )
    synthesis_status = SYNTHESIS_STATUS_COMPLETE if synthesis_artifact else (
        SYNTHESIS_STATUS_PARTIAL if king_synthesis_reached else SYNTHESIS_STATUS_NOT_APPLICABLE
    )
    limitations = _build_learning_limitations(
        semantic_status=semantic_status,
        synthesis_status=synthesis_status,
        structural_variance=structural_variance,
        activation_report=activation_report,
        interaction_report=interaction_report,
        explicit_error=explicit_error,
    )
    degradation_reason = None
    normalized_contract = _normalize_contract_status(contract_status)
    if normalized_contract in {"DEGRADED", "FAILED"}:
        degradation_reason = _primary_failure_reason(
            structural_variance=structural_variance,
            contract_report=contract_report,
            interaction_report=interaction_report,
            activation_report=activation_report,
            explicit_error=explicit_error,
        )
    record = {
        "schema_version": LEARNING_TELEMETRY_SCHEMA_VERSION,
        "session_id": session_id,
        "generated_utc": base.utc_now_iso(),
        "runtime_root": runtime_root,
        "broker_root": broker_root,
        "semantic_audit_status": semantic_status,
        "contract_status": normalized_contract,
        "cosine_score": _coerce_optional_float(structural_variance.get("combined_cosine"))
        if structural_variance.get("combined_cosine") is not None
        else None,
        "degradation_reason": degradation_reason,
        "synthesis_artifact": synthesis_artifact or None,
        "model_route": model_route,
        "evidence_available": bool(turns or activation_report or interaction_report or structural_variance),
        "limitations": limitations,
        "root_stamp_schema_version": str((provenance or {}).get("root_stamp_schema_version", "21.5C") or "21.5C"),
        "run_id": session_id,
        "execution_mode": LIVE_EXECUTION_MODE,
        "combined_cosine": _coerce_optional_float(structural_variance.get("combined_cosine"))
        if structural_variance.get("combined_cosine") is not None
        else None,
        "claim_cosine": _coerce_optional_float(structural_variance.get("claim_cosine"))
        if structural_variance.get("claim_cosine") is not None
        else None,
        "passed": bool(structural_variance.get("passed")) if structural_variance else False,
        "audit_reason": str(semantic_audit.get("audit_reason") or ""),
        "audit_status": str(semantic_audit.get("audit_status") or ""),
        "trigger_metrics": list(semantic_audit.get("trigger_metrics") or []),
        "borderline_pass": bool(semantic_audit.get("borderline_pass")),
        "borderline_fail": bool(semantic_audit.get("borderline_fail")),
    }
    if semantic_audit.get("baseline_conclusion_text"):
        record["baseline_conclusion_text"] = semantic_audit["baseline_conclusion_text"]
        record["baseline_conclusion_source"] = semantic_audit.get("baseline_conclusion_source")
    if semantic_audit.get("perturbed_conclusion_text"):
        record["perturbed_conclusion_text"] = semantic_audit["perturbed_conclusion_text"]
        record["perturbed_conclusion_source"] = semantic_audit.get("perturbed_conclusion_source")
    if model_metadata:
        record["model_metadata"] = dict(model_metadata)
    if stage_metadata:
        record["stage_metadata"] = dict(stage_metadata)
    return record


def _build_synthesis_outcome_record(
    *,
    session_id: str,
    runtime_root: str,
    broker_root: str,
    contract_status: str,
    synthesis_artifact: str | None,
    praxis_artifact: str | None,
    arbitration_artifact: str | None,
    activation_report: dict[str, Any] | None,
    interaction_report: dict[str, Any] | None,
    structural_variance: dict[str, Any] | None,
    turns: list[dict[str, Any]],
    explicit_error: str = "",
    error_category: str = "",
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    king_synthesis_reached = _turn_stage_seen(turns, "king_synthesis")
    cognitive_validation_reached = isinstance(interaction_report, dict)
    normalized_contract = _normalize_contract_status(contract_status)
    if synthesis_artifact:
        synthesis_status = SYNTHESIS_STATUS_COMPLETE
    elif king_synthesis_reached and error_category in {"schema/section validation failure", "model timeout", "empty response", "Ollama/API error"}:
        synthesis_status = SYNTHESIS_STATUS_FAILED
    elif king_synthesis_reached or cognitive_validation_reached or arbitration_artifact:
        synthesis_status = SYNTHESIS_STATUS_PARTIAL
    else:
        synthesis_status = SYNTHESIS_STATUS_NOT_APPLICABLE
    failure_reason = _primary_failure_reason(
        structural_variance=structural_variance,
        interaction_report=interaction_report,
        activation_report=activation_report,
        explicit_error=explicit_error,
    )
    limitations = _build_learning_limitations(
        semantic_status="",
        synthesis_status=synthesis_status,
        structural_variance=structural_variance,
        activation_report=activation_report,
        interaction_report=interaction_report,
        explicit_error=explicit_error,
    )
    learning_usable = synthesis_status == SYNTHESIS_STATUS_COMPLETE or (
        synthesis_status == SYNTHESIS_STATUS_PARTIAL
        and normalized_contract in {"VALID", "DEGRADED"}
        and bool(arbitration_artifact)
    )
    return {
        "schema_version": LEARNING_TELEMETRY_SCHEMA_VERSION,
        "session_id": session_id,
        "generated_utc": base.utc_now_iso(),
        "runtime_root": runtime_root,
        "synthesis_status": synthesis_status,
        "synthesis_artifact": synthesis_artifact or None,
        "praxis_artifact": praxis_artifact or None,
        "arbitration_artifact": arbitration_artifact or None,
        "failure_reason": failure_reason,
        "contract_status": normalized_contract,
        "learning_usable": learning_usable,
        "limitations": limitations,
        "broker_root": broker_root,
        "root_stamp_schema_version": str((provenance or {}).get("root_stamp_schema_version", "21.5C") or "21.5C"),
        "king_synthesis_reached": king_synthesis_reached,
        "cognitive_validation_reached": cognitive_validation_reached,
    }


def _write_synthesis_outcome_record(paths: dict[str, Path], record: dict[str, Any]) -> str:
    base.write_json_atomic(paths["synthesis_outcome_record"], record)
    return str(paths["synthesis_outcome_record"])


def _structural_variance_log_line(structural_variance: dict[str, Any]) -> str:
    status = "PASS" if structural_variance.get("passed") else "FAIL"
    line = (
        "[STRUCTURAL_VARIANCE] "
        f"{status} "
        f"combined_cosine={_format_optional_metric(structural_variance.get('combined_cosine'))} "
        f"claim_cosine={_format_optional_metric(structural_variance.get('claim_cosine'))} "
        f"thresholds=(combined>={STRUCTURAL_VARIANCE_COMBINED_THRESHOLD:.2f}, "
        f"claim>={STRUCTURAL_VARIANCE_CLAIM_THRESHOLD:.2f}) "
        f"anchor_ok={bool(structural_variance.get('anchor_ok'))}"
    )
    failure_reason = str(structural_variance.get("failure_reason") or "").strip()
    if failure_reason:
        line += f" reason={failure_reason}"
    return line


def _semantic_audit_log_line(*, session_id: str, structural_variance: dict[str, Any]) -> str:
    semantic_audit = (
        structural_variance.get("semantic_audit")
        if isinstance(structural_variance.get("semantic_audit"), dict)
        else _empty_semantic_audit_state()
    )
    return (
        "[SEMANTIC_AUDIT] "
        f"FLAGGED run_id={session_id} "
        f"combined_cosine={_format_optional_metric(structural_variance.get('combined_cosine'))} "
        f"claim_cosine={_format_optional_metric(structural_variance.get('claim_cosine'))} "
        f"passed={bool(structural_variance.get('passed'))} "
        f"audit_reason={str(semantic_audit.get('audit_reason') or '')} "
        f"audit_status={str(semantic_audit.get('audit_status') or '')}"
    )


def _report_probe_artifacts(
    paths: dict[str, Path],
    structural_variance_telemetry_path: str = "",
    semantic_audit_record_path: str = "",
) -> dict[str, str]:
    artifacts = {"validation_probe_path": str(paths["probes"])}
    if structural_variance_telemetry_path:
        artifacts["structural_variance_telemetry_path"] = structural_variance_telemetry_path
    if semantic_audit_record_path:
        artifacts["semantic_audit_record_path"] = semantic_audit_record_path
    return artifacts


def _turns_observed_model_output(turns: list[dict[str, Any]]) -> bool:
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        if turn.get("call_completed") and int(turn.get("raw_output_length") or 0) > 0:
            return True
    return False



def _materialize_runtime_contract(
    *,
    root: Path,
    session_id: str,
    topic: str,
    manifest: dict[str, Any] | None,
    turns: list[dict[str, Any]] | None,
    dialog_text: str,
    dialog_source_path: str,
    failure_reason: str,
    prefer_dialog_analysis: bool,
    provenance: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_turns = [dict(turn) for turn in (turns or []) if isinstance(turn, dict)]
    normalized_source_path = str(dialog_source_path or "").strip()
    normalized_failure_reason = str(failure_reason or "").strip()
    model_calls_observed = _turns_observed_model_output(normalized_turns)

    arbitration_warning = ""
    if prefer_dialog_analysis and str(dialog_text or "").strip():
        try:
            arbitration_artifact = analyze_dialog(
                dialog_text=str(dialog_text),
                session_id=session_id,
                root=root,
                topic=topic,
                source_path=normalized_source_path,
                manifest=manifest,
                execution_mode=LIVE_EXECUTION_MODE,
                dialog_origin="broker_live",
                model_calls_observed=model_calls_observed,
            )
        except IntegrityViolation:
            raise
        except Exception as exc:
            arbitration_warning = f"runtime dialog arbitration fell back to stub: {exc}"
            arbitration_artifact = {}
    else:
        arbitration_artifact = {}

    if not arbitration_artifact:
        stub_reason = normalized_failure_reason or arbitration_warning or "runtime contract attachment executed before full dialog arbitration"
        stub_warnings = [item for item in [arbitration_warning, normalized_failure_reason] if item]
        arbitration_artifact = persist_arbitration_stub(
            root=root,
            session_id=session_id,
            topic=topic,
            source_path=normalized_source_path,
            warnings=stub_warnings or [stub_reason],
            failure_reason=stub_reason,
            analysis_status="failed" if arbitration_warning and not normalized_failure_reason else "skipped",
            execution_mode=LIVE_EXECUTION_MODE,
            dialog_origin="broker_live",
            model_calls_observed=model_calls_observed,
            model_turns=normalized_turns,
        )

    arbitration_artifact = attach_canonical_provenance(arbitration_artifact, provenance["runtime_root"], provenance["broker_root"])
    guard = IntegrityGuard(base_dir=root)
    contract_report = enforce_contract(arbitration_artifact, guard=guard)
    trace_contract_status_from_mapping(
        base_dir=root,
        session_id=session_id,
        checkpoint="CONTRACT_RETURNED",
        container=contract_report,
        container_name="runtime_contract_report",
        source_file=Path(__file__),
        guard=guard,
    )
    return arbitration_artifact, contract_report



def _runtime_contract_metadata(
    *,
    root: Path,
    session_id: str,
    arbitration_artifact: dict[str, Any],
    contract_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_path": str(arbitration_artifact.get("artifact_path", "")).strip(),
        "analysis_status": str(arbitration_artifact.get("analysis_status", "")).strip(),
        "contract_execution_signal_path": _runtime_contract_signal_path(root, session_id),
        "contract_status": str(contract_report.get("contract_status", "")).strip(),
        "contract_message": str(contract_report.get("contract_message", "")).strip(),
        "contract_violations": list(contract_report.get("contract_violations") or []),
    }


def _retry_prompt(prompt: str, stage: str, failure_reason: str) -> str:
    required = base.required_sections_for_stage(stage)
    retry_notes = [
        'RETRY REQUIREMENTS:',
        f'- Previous attempt was invalid: {failure_reason or "unknown failure"}.',
        f'- Start with {required[0]}: on the first non-empty line.',
        f'- Return ONLY these headers exactly once, in order: {", ".join(required)}.',
        '- Do not echo transcript lines, role markers, or earlier turns.',
        '- Do not add text before the first header or after the final section.',
    ]
    return prompt.rstrip() + "\n\n" + "\n".join(retry_notes)


def _run_stage(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    prompt: str,
    ollama_base: str,
    temperature: float,
    max_tokens: int,
    seed: int,
    timeout_sec: int,
    validation_details_fn,
    *,
    round_number: int | None = None,
    wing_name: str | None = None,
    system_prompt: str | None = None,
    max_attempts: int = 2,
    record_events: bool = True,
    runtime_paths: dict[str, Path] | None = None,
    turn_records: list[dict[str, Any]] | None = None,
    latency_sink: list[dict[str, Any]] | None = None,
    warmup_applied: bool = False,
) -> str:
    last_reason = "unknown failure"
    last_category = "unexpected exception"
    last_missing_sections: list[str] = []
    last_preview: str | None = None
    last_output_length = 0
    endpoint = ollama_base.rstrip("/") + "/api/generate"

    for attempt in range(1, max_attempts + 1):
        response_text: str | None = None
        raw_preview: str | None = None
        raw_output_length = 0
        raw_missing: list[str] = []
        template_hits: list[str] = []
        attempt_prompt = prompt if attempt == 1 else _retry_prompt(prompt, stage, last_reason)
        # Phase 2.5F: monotonic timing
        _stage_started = time.monotonic()
        _started_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _stage_status = "success"
        _stage_error: str = ""
        try:
            response_text = base.ollama_generate(model, attempt_prompt, ollama_base, temperature, max_tokens, seed, timeout_sec, system_prompt=system_prompt)
            # BOOT-FIX v2 Step B: strip-only normalization (axis-1 leading preamble /
            # header decoration) applied before contract parsing, for every role. The
            # true raw output is preserved in the turn record below; trailing echoed
            # scaffold, non-English content, and fabricated claims are left untouched
            # and still fail the strict contract.
            normalized_text = normalize_debate_turn(response_text)
            normalizer_changed = normalized_text != response_text
            raw_preview = base.build_output_preview(response_text)
            raw_output_length = len(response_text)
            raw_validation_reason, raw_missing = validation_details_fn(response_text)
            effective_validation_reason, effective_missing = validation_details_fn(normalized_text)
            template_hits = _template_hits(response_text)
            failure_reason = effective_validation_reason
            failure_category = ""
            if template_hits:
                failure_reason = "template/bootstrap markers detected in raw live output"
                failure_category = "template/bootstrap contamination"

            record = {
                "schema_version": "1.0",
                "generated_at": base.utc_now_iso(),
                "execution_mode": LIVE_EXECUTION_MODE,
                "session_id": session_id,
                "stage": stage,
                "round_number": round_number,
                "wing_name": wing_name,
                "role": role,
                "model": model,
                "attempt": attempt,
                "provider": "ollama",
                "provider_endpoint": endpoint,
                "call_completed": True,
                "validation_passed": not failure_reason,
                "raw_validation_passed": not raw_validation_reason,
                "normalized_validation_passed": not effective_validation_reason,
                "normalizer_applied": normalizer_changed,
                "failure_category": failure_category or ("schema/section validation failure" if failure_reason else ""),
                "failure_reason": failure_reason,
                "missing_sections": effective_missing,
                "template_markers": template_hits,
                "prompt": attempt_prompt,
                "raw_output": response_text,
                "raw_output_preview": raw_preview,
                "raw_output_length": raw_output_length,
                "normalized_output": normalized_text,
            }
            if runtime_paths is not None and turn_records is not None:
                _persist_turn(runtime_paths, record, turn_records)

            if not failure_reason:
                if record_events:
                    base.log_stage_event(
                        root=root,
                        session_id=session_id,
                        stage=stage,
                        role=role,
                        model=model,
                        attempt=attempt,
                        validation_passed=True,
                        raw_validation_passed=not raw_validation_reason,
                        raw_missing_sections=raw_missing,
                        guard_applied=False,
                        guard_inserted_sections=[],
                        raw_output_preview=raw_preview,
                        raw_output_length=raw_output_length,
                        round_number=round_number,
                        wing_name=wing_name,
                    )
                # Phase 2.5F: record latency on success path
                if latency_sink is not None:
                    _ended_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    latency_sink.append({
                        "stage": stage,
                        "round": round_number,
                        "role": role,
                        "model": model,
                        "attempt": attempt,
                        "timeout_sec": timeout_sec,
                        "started_at_utc": _started_utc,
                        "ended_at_utc": _ended_utc,
                        "duration_sec": round(time.monotonic() - _stage_started, 3),
                        "status": "success",
                        "output_chars": raw_output_length,
                        "error": None,
                        "warmup_applied": warmup_applied,
                        "timeout_diagnostic": None,
                    })
                # Return the strip-normalized text so downstream parsing/transcript
                # uses the contract-valid form; the true raw is retained in the record.
                return normalized_text

            last_reason = failure_reason
            last_category = failure_category or "schema/section validation failure"
            last_missing_sections = [] if template_hits else effective_missing
            last_preview = raw_preview
            last_output_length = raw_output_length
            if record_events:
                base.log_stage_event(
                    root=root,
                    session_id=session_id,
                    stage=stage,
                    role=role,
                    model=model,
                    attempt=attempt,
                    validation_passed=False,
                    raw_validation_passed=not raw_validation_reason,
                    failure_category=last_category,
                    failure_reason=failure_reason,
                    raw_missing_sections=raw_missing,
                    missing_sections_list=last_missing_sections,
                    guard_applied=False,
                    guard_inserted_sections=[],
                    raw_output_preview=raw_preview,
                    raw_output_length=raw_output_length,
                    round_number=round_number,
                    wing_name=wing_name,
                )
        except IntegrityViolation:
            raise
        except Exception as exc:
            last_reason = str(exc)
            last_category = base.classify_stage_failure(exc)
            # Phase 2.5F: record latency on exception path
            _exc_str = str(exc).lower()
            _is_timeout = "timeout" in _exc_str or "timed out" in _exc_str
            if latency_sink is not None:
                _ended_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                latency_sink.append({
                    "stage": stage,
                    "round": round_number,
                    "role": role,
                    "model": model,
                    "attempt": attempt,
                    "timeout_sec": timeout_sec,
                    "started_at_utc": _started_utc,
                    "ended_at_utc": _ended_utc,
                    "duration_sec": round(time.monotonic() - _stage_started, 3),
                    "status": "timeout" if _is_timeout else "error",
                    "output_chars": len(response_text) if response_text else 0,
                    "error": str(exc)[:200],
                    "warmup_applied": warmup_applied,
                    "timeout_diagnostic": f"timeout_sec={timeout_sec}" if _is_timeout else None,
                })
            last_missing_sections = []
            last_preview = base.build_output_preview(response_text)
            last_output_length = len(response_text) if response_text else 0
            record = {
                "schema_version": "1.0",
                "generated_at": base.utc_now_iso(),
                "execution_mode": LIVE_EXECUTION_MODE,
                "session_id": session_id,
                "stage": stage,
                "round_number": round_number,
                "wing_name": wing_name,
                "role": role,
                "model": model,
                "attempt": attempt,
                "provider": "ollama",
                "provider_endpoint": endpoint,
                "call_completed": bool(response_text),
                "validation_passed": False,
                "raw_validation_passed": None,
                "failure_category": last_category,
                "failure_reason": last_reason,
                "missing_sections": [],
                "template_markers": _template_hits(response_text or ""),
                "prompt": attempt_prompt,
                "raw_output": response_text or "",
                "raw_output_preview": last_preview,
                "raw_output_length": last_output_length,
            }
            if runtime_paths is not None and turn_records is not None:
                _persist_turn(runtime_paths, record, turn_records)
            if record_events:
                base.log_stage_event(
                    root=root,
                    session_id=session_id,
                    stage=stage,
                    role=role,
                    model=model,
                    attempt=attempt,
                    validation_passed=False,
                    failure_category=last_category,
                    failure_reason=str(exc),
                    missing_sections_list=last_missing_sections,
                    raw_output_preview=last_preview,
                    raw_output_length=last_output_length,
                    round_number=round_number,
                    wing_name=wing_name,
                )

    if record_events:
        base.log_terminal_stage_failure(
            root=root,
            session_id=session_id,
            stage=stage,
            role=role,
            model=model,
            retry_count=max_attempts,
            failure_category=last_category,
            failure_reason=last_reason,
            missing_sections_list=last_missing_sections,
            raw_output_preview=last_preview,
            raw_output_length=last_output_length,
            round_number=round_number,
            wing_name=wing_name,
        )
    raise base.SynthesisError(f"stage={stage} role={role} model={model} retries={max_attempts} reason={last_reason}")

def _execute_debate(
    root: Path,
    session_id: str,
    topic: str,
    hierarchy: dict[str, Any],
    ollama_base_url: str,
    debate_rounds: int,
    debate_temp: float,
    synth_temp: float,
    max_tokens_turn: int,
    max_tokens_synth: int,
    seed: int,
    turn_timeout_sec: int,
    synth_timeout_sec: int,
    system_prompt: str | None = None,
    *,
    record_events: bool = True,
    runtime_paths: dict[str, Path] | None = None,
    turn_records: list[dict[str, Any]] | None = None,
    contradiction_context_str: str | None = None,
    latency_sink: list[dict[str, Any]] | None = None,
    warmed_up_models: set[str] | None = None,
) -> dict[str, Any]:
    neutral_prompt_mode = bool(system_prompt)
    trace: list[dict[str, Any]] = []
    transcript_blocks: list[str] = []
    wing_buffers: dict[str, list[str]] = {"alpha": [], "beta": []}
    stage_outputs: dict[str, dict[str, Any]] = {}

    for round_number in range(1, max(1, int(debate_rounds)) + 1):
        for wing_name in ("alpha", "beta"):
            for role_cfg in hierarchy[f"{wing_name}_wing"]:
                role = str(role_cfg.get("role", f"{wing_name.upper()}_ROLE")).strip()
                model = str(role_cfg.get("model", "")).strip()
                stance = str(role_cfg.get("stance", "Reason carefully.")).strip()
                prompt = base.build_neutral_debate_prompt(topic, "\n\n".join(transcript_blocks), round_number=round_number) if neutral_prompt_mode else base.build_position_prompt(topic, "\n\n".join(transcript_blocks), role, stance, f"{wing_name.upper()}_POSITIONS", round_number)
                raw = _run_stage(root, session_id, f"{wing_name}_positions", role, model, prompt, ollama_base_url, debate_temp, max_tokens_turn, seed, _resolve_turn_timeout_sec(model, role, turn_timeout_sec), base.debate_validation_details, round_number=round_number, wing_name=wing_name, system_prompt=system_prompt, record_events=record_events, runtime_paths=runtime_paths, turn_records=turn_records, latency_sink=latency_sink, warmup_applied=model in (warmed_up_models or set()))
                trace.append({"stage": f"{wing_name}_positions", "round": round_number, "role": role, "model": model, "output": raw})
                block = base.render_block(f"{role} R{round_number}", model, raw)
                transcript_blocks.append(block)
                wing_buffers[wing_name].append(block)

    for wing_name in ("alpha", "beta"):
        rec_cfg = hierarchy["wing_reconciliation"][wing_name]
        role = str(rec_cfg.get("role", f"{wing_name.upper()}_RECONCILER")).strip()
        model = str(rec_cfg.get("model", "")).strip()
        prompt = base.build_neutral_debate_prompt(topic, "\n\n".join(wing_buffers[wing_name])) if neutral_prompt_mode else base.build_reconciliation_prompt(topic, wing_name, "\n\n".join(wing_buffers[wing_name]), role)
        raw = _run_stage(root, session_id, f"{wing_name}_reconciliation", role, model, prompt, ollama_base_url, debate_temp, max_tokens_turn, seed, _resolve_turn_timeout_sec(model, role, turn_timeout_sec), base.debate_validation_details, wing_name=wing_name, system_prompt=system_prompt, record_events=record_events, runtime_paths=runtime_paths, turn_records=turn_records, latency_sink=latency_sink, warmup_applied=model in (warmed_up_models or set()))
        trace.append({"stage": f"{wing_name}_reconciliation", "role": role, "model": model, "output": raw})
        block = base.render_block(role, model, raw)
        transcript_blocks.append(block)
        wing_buffers[wing_name].append(block)
        stage_outputs[f"{wing_name}_reconciliation"] = {"role": role, "model": model, "raw": raw, "block": block}

    alpha_summary = "\n\n".join(wing_buffers["alpha"])
    beta_summary = "\n\n".join(wing_buffers["beta"])
    pre_challenge_transcript = "\n\n".join(transcript_blocks)

    critique_cfg = hierarchy["cross_channel"]["critique"]
    critique_role = str(critique_cfg.get("role", "CROSS_CRITIC")).strip()
    critique_model = str(critique_cfg.get("model", "")).strip()
    critique_prompt = base.build_neutral_debate_prompt(topic, alpha_summary + "\n\n" + beta_summary) if neutral_prompt_mode else base.build_cross_prompt(topic, alpha_summary, beta_summary, critique_role, "cross critique")
    critique_raw = _run_stage(root, session_id, "cross_critique", critique_role, critique_model, critique_prompt, ollama_base_url, debate_temp, max_tokens_turn, seed, _resolve_turn_timeout_sec(critique_model, critique_role, turn_timeout_sec), base.debate_validation_details, system_prompt=system_prompt, record_events=record_events, runtime_paths=runtime_paths, turn_records=turn_records, latency_sink=latency_sink, warmup_applied=critique_model in (warmed_up_models or set()))
    trace.append({"stage": "cross_critique", "role": critique_role, "model": critique_model, "output": critique_raw})
    critique_block = base.render_block(critique_role, critique_model, critique_raw)
    transcript_blocks.append(critique_block)
    stage_outputs["cross_critique"] = {"role": critique_role, "model": critique_model, "raw": critique_raw, "block": critique_block}

    cross_cfg = hierarchy["cross_channel"]["cross_exam"]
    cross_role = str(cross_cfg.get("role", "CROSS_EXAMINER")).strip()
    cross_model = str(cross_cfg.get("model", "")).strip()
    cross_prompt = base.build_neutral_debate_prompt(topic, alpha_summary + "\n\n" + beta_summary + "\n\n" + critique_raw) if neutral_prompt_mode else base.build_cross_prompt(topic, alpha_summary + "\n\n" + critique_raw, beta_summary + "\n\n" + critique_raw, cross_role, "cross examination")
    cross_raw = _run_stage(root, session_id, "cross_exam", cross_role, cross_model, cross_prompt, ollama_base_url, debate_temp, max_tokens_turn, seed, _resolve_turn_timeout_sec(cross_model, cross_role, turn_timeout_sec), base.debate_validation_details, system_prompt=system_prompt, record_events=record_events, runtime_paths=runtime_paths, turn_records=turn_records, latency_sink=latency_sink, warmup_applied=cross_model in (warmed_up_models or set()))
    trace.append({"stage": "cross_exam", "role": cross_role, "model": cross_model, "output": cross_raw})
    cross_block = base.render_block(cross_role, cross_model, cross_raw)
    transcript_blocks.append(cross_block)
    stage_outputs["cross_exam"] = {"role": cross_role, "model": cross_model, "raw": cross_raw, "block": cross_block}

    king_cfg = hierarchy["king_synthesizer"]
    king_role = str(king_cfg.get("role", "KING_SYNTHESIZER")).strip()
    king_model = str(king_cfg.get("model", "")).strip()

    # Phase 20.2 — inject contradiction context into king synthesis prompt (once, opt-in)
    king_transcript = "\n\n".join(transcript_blocks)
    contradiction_aware_meta: dict[str, Any] = {"enabled": False}
    if contradiction_context_str:
        king_transcript = king_transcript + "\n\n" + contradiction_context_str
        contradiction_aware_meta = {
            "enabled": True,
            "mode": "injected_into_king_prompt",
            "context_length": len(contradiction_context_str),
        }

    king_prompt = base.build_neutral_king_prompt(topic, king_transcript, session_id) if neutral_prompt_mode else base.build_king_prompt(topic, king_transcript, session_id)
    king_raw = _run_stage(root, session_id, "king_synthesis", king_role, king_model, king_prompt, ollama_base_url, synth_temp, max_tokens_synth, seed, _resolve_turn_timeout_sec(king_model, king_role, synth_timeout_sec), base.canonical_validation_details, system_prompt=system_prompt, record_events=record_events, runtime_paths=runtime_paths, turn_records=turn_records, latency_sink=latency_sink, warmup_applied=king_model in (warmed_up_models or set()))
    trace.append({"stage": "king_synthesis", "role": king_role, "model": king_model, "output": king_raw})
    stage_outputs["king_synthesis"] = {"role": king_role, "model": king_model, "raw": king_raw}

    return {
        "trace": trace,
        "transcript_blocks": transcript_blocks,
        "alpha_summary": alpha_summary,
        "beta_summary": beta_summary,
        "pre_challenge_transcript": pre_challenge_transcript,
        "stage_outputs": stage_outputs,
        "king_role": king_role,
        "king_model": king_model,
        "king_raw": king_raw,
        "neutral_prompt_mode": neutral_prompt_mode,
        "contradiction_aware_synthesis": contradiction_aware_meta,
    }


def _extract_bundle(text: str) -> dict[str, str]:
    return {
        "claim": base.extract_section(text, ["CLAIM"]),
        "challenge": base.extract_section(text, ["CHALLENGE", "COUNTERARGUMENTS"]),
        "evidence": "\n".join(_split_probe_items(base.extract_section(text, ["EVIDENCE"]))),
        "uncertainty": "\n".join(_split_probe_items(base.extract_section(text, ["UNCERTAINTY", "UNCERTAINTIES"]))),
        "final": base.extract_section(text, ["FINAL_SYNTHESIS"]),
    }


def _bundle_text(bundle: dict[str, str]) -> str:
    return "\n\n".join(value.strip() for value in bundle.values() if str(value or "").strip()).strip()


def _split_probe_items(text: str) -> list[str]:
    normalized = base.normalize_text(text)
    if not normalized:
        return []
    items: list[str] = []
    for line in normalized.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
            continue
        items.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
    return [item for item in items if item]


def _trace_label(entry: dict[str, Any]) -> str:
    stage = str(entry.get("stage", ""))
    role = str(entry.get("role", "")).strip()
    round_number = entry.get("round")
    if stage.endswith("_positions") and round_number is not None:
        return f"{role} R{int(round_number)}"
    return role


def _render_trace_block(entry: dict[str, Any], output_text: str | None = None) -> str:
    return base.render_block(
        _trace_label(entry),
        str(entry.get("model", "")).strip(),
        str(output_text if output_text is not None else entry.get("output", "")),
    )


def _run_probe_stage(
    root: Path,
    session_id: str,
    stage: str,
    role: str,
    model: str,
    prompt: str,
    ollama_base: str,
    temperature: float,
    max_tokens: int,
    seed: int,
    timeout_sec: int,
    validation_details_fn,
    *,
    wing_name: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    try:
        output = _run_stage(
            root,
            session_id,
            stage,
            role,
            model,
            prompt,
            ollama_base,
            temperature,
            max_tokens,
            seed,
            timeout_sec,
            validation_details_fn,
            wing_name=wing_name,
            system_prompt=system_prompt,
            record_events=False,
        )
        return {
            "completed": True,
            "output": output,
            "error": "",
            "error_category": "",
        }
    except IntegrityViolation:
        raise
    except Exception as exc:
        return {
            "completed": False,
            "output": "",
            "error": str(exc),
            "error_category": base.classify_stage_failure(exc),
        }


def _compare_reasoning_outputs(left: str, right: str, *, manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    config = load_semantic_matching_config(root=root, manifest=manifest)
    anchor_threshold = max(float(config["threshold_agree"]), 0.97)
    section_threshold = max(float(config["threshold_agree"]), 0.985)

    left_bundle = _extract_bundle(left)
    right_bundle = _extract_bundle(right)
    anchor_left = left_bundle["claim"] or left_bundle["final"] or _bundle_text(left_bundle)
    anchor_right = right_bundle["claim"] or right_bundle["final"] or _bundle_text(right_bundle)
    anchor_classification, anchor_features = classify_claim_similarity(
        anchor_left,
        anchor_right,
        manifest=manifest,
        root=root,
    )
    anchor_cosine = anchor_features.get("cosine")
    combined = compute_semantic_similarity(
        _bundle_text(left_bundle),
        _bundle_text(right_bundle),
        manifest=manifest,
        root=root,
    )
    combined_cosine = combined.get("cosine")
    section_similarity: dict[str, Any] = {}
    changed_sections: list[str] = []

    for key, label in (
        ("claim", "claim"),
        ("challenge", "challenge"),
        ("evidence", "evidence"),
        ("uncertainty", "uncertainty"),
        ("final", "final_synthesis"),
    ):
        left_value = left_bundle.get(key, "").strip()
        right_value = right_bundle.get(key, "").strip()
        if not left_value or not right_value:
            continue
        if key in {"claim", "final"}:
            section_classification, section_features = classify_claim_similarity(
                left_value,
                right_value,
                manifest=manifest,
                root=root,
            )
            section_similarity[label] = dict(section_features)
            section_cosine = section_features.get("cosine")
            section_changed = (
                section_classification == "CONTRADICTION"
                or section_cosine is None
                or float(section_cosine) < section_threshold
            )
        else:
            details = compute_semantic_similarity(
                left_value,
                right_value,
                manifest=manifest,
                root=root,
            )
            section_similarity[label] = details
            section_cosine = details.get("cosine")
            section_changed = section_cosine is None or float(section_cosine) < section_threshold
        if section_changed:
            changed_sections.append(label)

    anchor_changed = (
        anchor_classification == "CONTRADICTION"
        or anchor_cosine is None
        or float(anchor_cosine) < anchor_threshold
    )
    signature_changed = any(
        label in changed_sections for label in ("claim", "challenge", "final_synthesis")
    )
    body_changed = combined_cosine is None or float(combined_cosine) < section_threshold
    meaningful_change = bool(
        (anchor_changed and signature_changed)
        or (signature_changed and len(changed_sections) >= 2)
        or (body_changed and len(changed_sections) >= 2)
    )
    return {
        "meaningful_change": meaningful_change,
        "anchor_classification": anchor_classification,
        "anchor_features": anchor_features,
        "combined_similarity": combined,
        "changed_sections": changed_sections,
        "section_similarity": section_similarity,
        "thresholds": {
            "anchor_threshold": round(anchor_threshold, 4),
            "section_threshold": round(section_threshold, 4),
        },
    }

def _bullet_list(text: str, fallback: str) -> str:
    items = _split_probe_items(text)
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def _structural_variant_debate_block(text: str) -> str:
    claim = base.extract_section(text, ["CLAIM"]).strip() or "No explicit claim provided."
    challenge = base.extract_section(text, ["CHALLENGE", "COUNTERARGUMENTS"]).strip() or "No explicit challenge was preserved in this structural probe."
    evidence = base.extract_section(text, ["EVIDENCE"]).strip() or "- No explicit evidence was preserved in this structural probe."
    uncertainty = base.extract_section(text, ["UNCERTAINTY", "UNCERTAINTIES"]).strip() or "No explicit uncertainty was preserved in this structural probe."
    return "\n\n".join(
        [
            f"EVIDENCE:\n{evidence}",
            f"CLAIM:\n{claim}",
            f"UNCERTAINTY:\n{uncertainty}",
            f"CHALLENGE:\n{challenge}",
        ]
    ).strip()


def _invert_claim(text: str) -> str:
    claim = base.normalize_text(text)
    if not claim:
        return "The upstream conclusion should be treated as unreliable rather than accepted."
    if re.search(r"\bnot\b", claim, re.IGNORECASE):
        stripped = re.sub(r"\bnot\b\s*", "", claim, count=1, flags=re.IGNORECASE).strip()
        return stripped or "The upstream conclusion should be accepted."
    return f"It is more plausible that the opposite conclusion holds than: {claim}"


def _perturb_debate_block(text: str) -> str:
    claim = _invert_claim(base.extract_section(text, ["CLAIM"]))
    return "\n\n".join(
        [
            f"CLAIM:\n{claim}",
            "CHALLENGE:\nThe original reasoning overstates support and should not be accepted without stronger counter-evidence.",
            "EVIDENCE:\n- The upstream evidence can be read in the opposite direction under a counterfactual interpretation.\n- The earlier reasoning leaves open failure cases that reverse the conclusion.",
            "UNCERTAINTY:\nThis perturbation intentionally stress-tests whether downstream synthesis tracks upstream reasoning changes.",
        ]
    ).strip()


def _replace_block(blocks: list[str], original_block: str, replacement_block: str) -> list[str]:
    replaced: list[str] = []
    swapped = False
    for block in blocks:
        if not swapped and block == original_block:
            replaced.append(replacement_block)
            swapped = True
        else:
            replaced.append(block)
    if not swapped:
        raise base.SynthesisError("Unable to locate target block for perturbation validation.")
    return replaced


def _neutralize_challenge_block(text: str) -> str:
    claim = base.extract_section(text, ["CLAIM"]).strip()
    evidence = _split_probe_items(base.extract_section(text, ["EVIDENCE"]))
    uncertainty = base.extract_section(text, ["UNCERTAINTY", "UNCERTAINTIES"]).strip()
    evidence_lines = evidence or ["The support remains unchanged for this challenge-removal probe."]
    return "\n\n".join(
        [
            f"CLAIM:\n{claim or 'No explicit claim provided.'}",
            "CHALLENGE:\nNo substantive challenge is provided in this probe variant.",
            "EVIDENCE:\n" + "\n".join(f"- {item}" for item in evidence_lines),
            f"UNCERTAINTY:\n{uncertainty or 'The challenge channel was intentionally withheld for validation.'}",
        ]
    ).strip()


def _build_dependency_test_result(*, actual_output: str, probe_output: str, manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    comparison = _compare_reasoning_outputs(actual_output, probe_output, manifest=manifest, root=root)
    return {
        "passed": bool(comparison.get("meaningful_change")),
        "comparison": comparison,
    }

def _build_non_cosmetic_challenge_result(
    *,
    actual_king: str,
    challenge_removed_king: str,
    challenge_texts: list[str],
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    comparison = _compare_reasoning_outputs(actual_king, challenge_removed_king, manifest=manifest, root=root)
    actual_bundle = _extract_bundle(actual_king)
    targets = [
        actual_bundle.get("challenge", ""),
        actual_bundle.get("uncertainty", ""),
        actual_bundle.get("final", ""),
    ]
    # imperfect_synthesis propagation detection uses the manifest-approved
    # challenge-answer cosine (CHALLENGE_ANSWER_COSINE=0.6). A prior hardcoded
    # max(..., 0.9) floor overrode that approved value and scored genuinely
    # incorporated challenges (BOOT_PROOF_02: cosine 0.706-0.784, meaningful_change=true)
    # as "not propagated". Recalibrated to the approved threshold; this is the
    # propagation-detection gate ONLY and does NOT touch the structural-variance
    # G-SV 0.90 gate. Revert: restore max(..., 0.9) around the expression below.
    answer_threshold = float(load_semantic_matching_config(root=root, manifest=manifest)["threshold_answer"])
    answered: list[dict[str, Any]] = []
    for challenge in challenge_texts:
        normalized = base.normalize_text(challenge)
        if not normalized:
            continue
        matched = any(
            challenge_answered_by(normalized, candidate, manifest=manifest, root=root)
            for candidate in targets
            if str(candidate or "").strip()
        )
        if not matched:
            for candidate in targets:
                if not str(candidate or "").strip():
                    continue
                details = compute_semantic_similarity(normalized, candidate, manifest=manifest, root=root)
                cosine = details.get("cosine")
                if cosine is not None and float(cosine) >= answer_threshold:
                    matched = True
                    break
        answered.append({
            "challenge": normalized,
            "propagated_to_synthesis": matched,
        })
    propagated_count = sum(1 for item in answered if item["propagated_to_synthesis"])
    passed = bool(comparison.get("meaningful_change")) and propagated_count > 0
    return {
        "passed": passed,
        "comparison": comparison,
        "challenge_propagation": answered,
        "propagated_count": propagated_count,
    }


def _build_structural_variance_result(
    *,
    actual_king: str,
    structural_probe_output: str,
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    comparison = _compare_reasoning_outputs(actual_king, structural_probe_output, manifest=manifest, root=root)
    anchor_ok = str(comparison.get("anchor_classification", "")).strip().upper() != "CONTRADICTION"
    combined_cosine = _coerce_optional_float(((comparison.get("combined_similarity") or {}).get("cosine")))
    claim_cosine = _coerce_optional_float((((comparison.get("section_similarity") or {}).get("claim") or {}).get("cosine")))
    passed = bool(
        anchor_ok
        and combined_cosine is not None
        and combined_cosine >= STRUCTURAL_VARIANCE_COMBINED_THRESHOLD
        and claim_cosine is not None
        and claim_cosine >= STRUCTURAL_VARIANCE_CLAIM_THRESHOLD
    )
    failure_reason = (
        ""
        if passed
        else _structural_variance_failure_reason(
            anchor_ok=anchor_ok,
            combined_cosine=combined_cosine,
            claim_cosine=claim_cosine,
        )
    )
    result = {
        "passed": passed,
        "comparison": comparison,
        "anchor_ok": anchor_ok,
        "combined_cosine": combined_cosine,
        "claim_cosine": claim_cosine,
        "combined_threshold": STRUCTURAL_VARIANCE_COMBINED_THRESHOLD,
        "claim_threshold": STRUCTURAL_VARIANCE_CLAIM_THRESHOLD,
        "threshold_used": {
            "combined_cosine": STRUCTURAL_VARIANCE_COMBINED_THRESHOLD,
            "claim_cosine": STRUCTURAL_VARIANCE_CLAIM_THRESHOLD,
        },
        "failure_reason": failure_reason,
    }
    result["semantic_audit"] = _build_semantic_audit_state(
        actual_king=actual_king,
        structural_probe_output=structural_probe_output,
        passed=passed,
        anchor_ok=anchor_ok,
        combined_cosine=combined_cosine,
        claim_cosine=claim_cosine,
    )
    result["summary_counters"] = _build_structural_variance_summary_counters(result)
    return result


def _divergence_test(
    *,
    primary_trace: list[dict[str, Any]],
    shadow_trace: list[dict[str, Any]],
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    if len(primary_trace) != len(shadow_trace):
        return {
            "passed": False,
            "reason": f"trace length mismatch: primary={len(primary_trace)} shadow={len(shadow_trace)}",
        }
    stage_pairs: list[dict[str, Any]] = []
    divergent_count = 0
    summary_stage_divergence = 0
    for left_entry, right_entry in zip(primary_trace, shadow_trace):
        comparison = _compare_reasoning_outputs(
            str(left_entry.get("output", "")),
            str(right_entry.get("output", "")),
            manifest=manifest,
            root=root,
        )
        meaningful = bool(comparison.get("meaningful_change"))
        if meaningful:
            divergent_count += 1
            if not str(left_entry.get("stage", "")).endswith("_positions"):
                summary_stage_divergence += 1
        stage_pairs.append(
            {
                "stage": left_entry.get("stage"),
                "round": left_entry.get("round"),
                "role": left_entry.get("role"),
                "model": left_entry.get("model"),
                "meaningful_change": meaningful,
                "anchor_classification": comparison.get("anchor_classification"),
                "changed_sections": comparison.get("changed_sections") or [],
            }
        )
    required_divergent = max(2, max(1, len(stage_pairs) // 3))
    return {
        "passed": divergent_count >= required_divergent and summary_stage_divergence >= 1,
        "divergent_stage_count": divergent_count,
        "required_divergent_stage_count": required_divergent,
        "summary_stage_divergence": summary_stage_divergence,
        "stage_pairs": stage_pairs,
    }


def _cognitive_validation_report(
    *,
    session_id: str,
    topic: str,
    constraint_sensitivity: dict[str, Any],
    failure_modes: dict[str, Any],
    structural_variance: dict[str, Any],
    imperfect_synthesis: dict[str, Any],
    probe_artifacts: dict[str, Any],
) -> dict[str, Any]:
    tests = {
        "constraint_sensitivity": constraint_sensitivity,
        "failure_modes": failure_modes,
        "structural_variance": structural_variance,
        "imperfect_synthesis": imperfect_synthesis,
    }
    failed = [name for name, result in tests.items() if not bool(result.get("passed"))]
    suspicious_reasons: list[str] = []

    def _meaningfully_unchanged(result: dict[str, Any]) -> bool:
        if not bool(result.get("probe_completed")):
            return False
        comparison = result.get("comparison")
        return isinstance(comparison, dict) and not bool(comparison.get("meaningful_change"))

    if _meaningfully_unchanged(constraint_sensitivity):
        suspicious_reasons.append("Constraint sensitivity probe stayed clean and materially unchanged after upstream reasoning was withheld.")
    perturbation_probe = failure_modes.get("counterfactual_perturbation", {})
    if _meaningfully_unchanged(perturbation_probe):
        suspicious_reasons.append("Failure-mode perturbation stayed clean and materially unchanged after the debate content was inverted.")
    if _meaningfully_unchanged(imperfect_synthesis):
        suspicious_reasons.append("Imperfect-synthesis probe stayed clean and materially unchanged after challenge signals were removed.")
    divergence_shadow = failure_modes.get("divergence_shadow", {})
    if divergence_shadow.get("stage_pairs") and not bool(divergence_shadow.get("passed")):
        suspicious_reasons.append("Shadow LIVE replay remained unusually consistent with the primary trace.")
    if len(suspicious_reasons) >= 3:
        suspicious_reasons.insert(0, "Adverse probes remained consistently clean across the LIVE orchestration path.")
    summary_counters = _build_structural_variance_summary_counters(structural_variance)

    return {
        "schema_version": "1.0",
        "generated_at": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "topic": topic,
        "passed": len(failed) == 0 and not suspicious_reasons,
        "suspicious": bool(suspicious_reasons),
        "suspicious_reasons": suspicious_reasons,
        "tests": tests,
        "probe_artifacts": probe_artifacts,
        "summary_counters": summary_counters,
        "failures": failed,
    }


def _write_cognitive_validation_report(paths: dict[str, Path], report: dict[str, Any]) -> None:
    base.write_json_atomic(paths["cognitive"], report)
    base.write_json_atomic(paths["interaction"], report)


def _activation_report(
    session_id: str,
    topic: str,
    turns: list[dict[str, Any]],
    role_map_path: str,
    turn_manifest_path: str,
    broker: dict[str, str],
    provenance: dict[str, Any],
    ollama_base_url: str,
    failure_reason: str = "",
) -> dict[str, Any]:
    attempted_turns = [turn for turn in turns if turn.get("provider") == "ollama"]
    non_empty_turns = [
        turn
        for turn in turns
        if turn.get("call_completed") and int(turn.get("raw_output_length") or 0) > 0
    ]
    successful_turns = [
        turn
        for turn in turns
        if turn.get("call_completed") and turn.get("validation_passed")
    ]
    template_hits = [
        {
            "stage": turn.get("stage"),
            "role": turn.get("role"),
            "attempt": turn.get("attempt"),
            "hits": list(turn.get("template_markers") or []),
        }
        for turn in turns
        if turn.get("template_markers")
    ]
    checks = {
        "broker_only_execution": bool(broker.get("broker_script")),
        "model_call_attempted": bool(attempted_turns),
        "actual_model_calls_occurred": bool(non_empty_turns),
        "raw_outputs_persisted": bool(turn_manifest_path and turns),
        "role_model_mapping_persisted": bool(role_map_path),
        "template_path_executed": bool(template_hits),
        "outputs_model_generated": bool(successful_turns) and not template_hits,
    }
    failures: list[str] = []
    if not checks["broker_only_execution"]:
        failures.append("broker-only execution proof missing")
    if not checks["model_call_attempted"]:
        failures.append("no broker-driven model call attempts were recorded")
    if not checks["actual_model_calls_occurred"]:
        failures.append("no broker-driven model call returned output")
    if not checks["raw_outputs_persisted"]:
        failures.append("raw model outputs were not persisted")
    if not checks["role_model_mapping_persisted"]:
        failures.append("role-to-model mapping was not persisted")
    if checks["template_path_executed"]:
        failures.append("template/bootstrap markers were detected in live turn outputs")
    if not checks["outputs_model_generated"]:
        failures.append("no validated live model outputs were produced")
    if failure_reason:
        failures.append(failure_reason)
    payload = {
        "schema_version": "1.0",
        "generated_at": base.utc_now_iso(),
        "execution_mode": LIVE_EXECUTION_MODE,
        "session_id": session_id,
        "topic": topic,
        "passed": len(failures) == 0,
        "checks": checks,
        "broker": {
            **broker,
            "provider": "ollama",
            "base_url": str(ollama_base_url).strip(),
        },
        "artifacts": {
            "role_model_mapping_path": role_map_path,
            "turn_manifest_path": turn_manifest_path,
        },
        "evidence": {
            "model_call_attempt_count": len(attempted_turns),
            "non_empty_output_count": len(non_empty_turns),
            "successful_model_output_count": len(successful_turns),
            "turn_count": len(turns),
            "template_marker_hits": template_hits,
            "stage_summary": [
                {
                    "stage": turn.get("stage"),
                    "round_number": turn.get("round_number"),
                    "wing_name": turn.get("wing_name"),
                    "role": turn.get("role"),
                    "model": turn.get("model"),
                    "attempt": turn.get("attempt"),
                    "validation_passed": turn.get("validation_passed"),
                    "raw_output_length": turn.get("raw_output_length"),
                    "artifact_path": turn.get("artifact_path"),
                }
                for turn in turns
            ],
        },
        "failures": failures,
    }
    return attach_canonical_provenance(payload, provenance["runtime_root"], provenance["broker_root"])


def main() -> int:
    args = base._parse_args()
    root = Path(args.root).resolve()
    paths = _paths(root, args.session_id)
    turns: list[dict[str, Any]] = []
    probe_artifacts: dict[str, Any] = {}
    role_map_path = ""
    turn_manifest_path = ""
    activation_report: dict[str, Any] | None = None
    interaction_report: dict[str, Any] | None = None
    structural_variance: dict[str, Any] = {}
    structural_variance_telemetry_path = ""
    semantic_audit_record_path = str(paths["semantic_audit_record"])
    synthesis_outcome_record_path = str(paths["synthesis_outcome_record"])
    broker: dict[str, str] = {}
    provenance: dict[str, Any] = build_canonical_provenance(root, "")
    manifest = load_system_manifest(root)
    args.ollama_base_url = str(args.ollama_base_url).strip() or str(
        runtime_value("OLLAMA_BASE_URL", manifest)
    ).strip()
    args.model_a = str(args.model_a).strip() or model_name("PRIMARY_REASONER", manifest)
    args.model_b = str(args.model_b).strip() or model_name(
        "ADVERSARIAL_CHALLENGER",
        manifest,
    )
    args.model_c = str(args.model_c).strip() or model_name("CRITIC", manifest)
    args.model_synth = str(args.model_synth).strip() or model_name(
        "SYNTHESIZER",
        manifest,
    )

    # Phase 20.4 — Pressure-Adaptive Routing block (single block, between model-arg resolution and debate)
    _routing_meta: dict[str, Any] = {"enabled": False}
    _contradiction_context_str: str | None = None
    _routing_enable_cas: bool = False
    if _PressureRoutingLoader is not None and os.environ.get("SOVEREIGN_ENABLE_PRESSURE_ROUTING", "").strip() == "1":
        try:
            _cognition_root = os.environ.get("SOVEREIGN_COGNITION_ROOT", "") or str(root / "cognition")
            _routing_loader = _PressureRoutingLoader(cognition_root=_cognition_root)
            _routing_signal = _routing_loader.get_routing_signal_and_log(
                topic=args.topic,
                session_id=args.session_id,
                root=str(root),
            )
            _applied = _routing_signal.get("applied") or {}
            # Applied action 1: debate depth
            _routed_rounds = _applied.get("debate_rounds")
            if isinstance(_routed_rounds, int) and _routed_rounds > 0:
                args.debate_rounds = _routed_rounds
            # Applied action 2: model strength via env overrides
            _model_overrides = {
                "SOVEREIGN_ROUTING_PRIMARY_REASONER_MODEL": "model_a",
                "SOVEREIGN_ROUTING_ALPHA_SKEPTIC_MODEL": "model_b",
                "SOVEREIGN_ROUTING_CRITIC_MODEL": "model_c",
                "SOVEREIGN_ROUTING_KING_SYNTHESIZER_MODEL": "model_synth",
            }
            for env_key, arg_attr in _model_overrides.items():
                _override = os.environ.get(env_key, "").strip()
                if _override:
                    setattr(args, arg_attr, _override)
            # Applied action 3: enable contradiction-aware synthesis when routing recommends
            _routing_enable_cas = bool(_applied.get("enable_contradiction_aware_synthesis", False))
            _routing_meta = {
                "enabled": True,
                "tier": _routing_signal.get("tier"),
                "aggregate_pressure": _routing_signal.get("aggregate_pressure"),
                "applied": _applied,
                "recommended": _routing_signal.get("recommended"),
            }
        except Exception:  # pragma: no cover - routing failure must not block debate
            _routing_meta = {"enabled": True, "error": "routing_loader_failed"}

    # Phase 20.2 — Build contradiction context before debate (opt-in via env var or routing)
    _enable_cas = (
        os.environ.get("SOVEREIGN_ENABLE_CONTRADICTION_AWARE_SYNTHESIS", "").strip() == "1"
        or _routing_enable_cas
    )
    if _enable_cas and _ContradictionSynthesisLoader is not None:
        try:
            _cas_cognition_root = os.environ.get("SOVEREIGN_COGNITION_ROOT", "") or str(root / "cognition")
            _cas_limit = int(os.environ.get("SOVEREIGN_CONTRADICTION_LIMIT", "5"))
            _cas_min_pressure = float(os.environ.get("SOVEREIGN_CONTRADICTION_MIN_PRESSURE", "0.0"))
            _cas_loader = _ContradictionSynthesisLoader(cognition_root=_cas_cognition_root)
            _contradiction_context_str = _cas_loader.format_contradiction_context_for_prompt(
                topic=args.topic,
                limit=_cas_limit,
                min_pressure=_cas_min_pressure,
            ) or None
        except Exception:  # pragma: no cover - CAS failure must not block debate
            _contradiction_context_str = None

    # Phase 2.5F: warmup block — runs before debate try, non-fatal
    _warmed_up_models: set[str] = set()
    _warmup_results: list[dict[str, Any]] = []
    if os.environ.get("SOVEREIGN_ENABLE_MODEL_WARMUP", "").strip() == "1":
        _warmup_models = [
            str(args.model_a).strip(),
            str(args.model_b).strip(),
            str(args.model_c).strip(),
            str(args.model_synth).strip(),
        ]
        for _wm in dict.fromkeys(m for m in _warmup_models if m):
            _wr = _run_warmup(_wm, args.ollama_base_url)
            _warmup_results.append(_wr)
            if _wr.get("status") == "PASS":
                _warmed_up_models.add(_wm)

    # Phase 2.5F: latency records list — passed to main debate, NOT to shadow runs
    _latency_records: list[dict[str, Any]] = []
    _timeout_config = {
        "SOVEREIGN_DEEPSEEK_R1_TIMEOUT_SEC": os.environ.get("SOVEREIGN_DEEPSEEK_R1_TIMEOUT_SEC", ""),
        "SOVEREIGN_TURN_TIMEOUT_SEC": os.environ.get("SOVEREIGN_TURN_TIMEOUT_SEC", ""),
        "SOVEREIGN_ENABLE_MODEL_WARMUP": os.environ.get("SOVEREIGN_ENABLE_MODEL_WARMUP", ""),
        "SOVEREIGN_WARMUP_TIMEOUT_SEC": os.environ.get("SOVEREIGN_WARMUP_TIMEOUT_SEC", ""),
        "default_turn_timeout_sec": args.turn_timeout_sec,
    }

    try:
        broker = _broker_metadata(args.session_id)
        provenance = _runtime_provenance(root, broker)
        contract = base.load_contract(root)
        hierarchy = base.load_hierarchy(root, args)
        state = base.load_constitution_state(root)
        mode = state["mode"]
        system_prompt = base.load_system_prompt(args.system_prompt_file)
        role_map_path = _write_role_map(
            paths,
            args.session_id,
            args.topic,
            hierarchy,
            args.ollama_base_url,
            broker,
            provenance,
        )

        debate = _execute_debate(
            root,
            args.session_id,
            args.topic,
            hierarchy,
            args.ollama_base_url,
            args.debate_rounds,
            args.debate_temp,
            args.synth_temp,
            args.max_tokens_turn,
            args.max_tokens_synth,
            args.seed,
            args.turn_timeout_sec,
            args.synth_timeout_sec,
            system_prompt=system_prompt,
            record_events=True,
            runtime_paths=paths,
            turn_records=turns,
            contradiction_context_str=_contradiction_context_str,
            latency_sink=_latency_records,
            warmed_up_models=_warmed_up_models,
        )
        turn_manifest_path = _write_turn_manifest(paths, args.session_id, args.topic, turns, provenance)
        activation_report = _activation_report(
            args.session_id,
            args.topic,
            turns,
            role_map_path,
            turn_manifest_path,
            broker,
            provenance,
            args.ollama_base_url,
        )
        base.write_json_atomic(paths["activation"], activation_report)
        if not activation_report.get("passed"):
            interaction_report = {
                "schema_version": "1.0",
                "generated_at": base.utc_now_iso(),
                "execution_mode": LIVE_EXECUTION_MODE,
                "session_id": args.session_id,
                "topic": args.topic,
                "passed": False,
                "suspicious": False,
                "suspicious_reasons": [],
                "tests": {},
                "probe_artifacts": _report_probe_artifacts(paths, structural_variance_telemetry_path, semantic_audit_record_path),
                "failures": ["phase 1 live activation failed"],
            }
            _write_cognitive_validation_report(paths, interaction_report)
            raise base.SynthesisError("live activation validation failed")

        stage_outputs = debate["stage_outputs"]
        neutral_prompt_mode = bool(debate["neutral_prompt_mode"])
        alpha_reconciliation = stage_outputs["alpha_reconciliation"]
        if neutral_prompt_mode:
            dependency_prompt = base.build_neutral_debate_prompt(
                args.topic,
                "UPSTREAM_REASONING_WITHHELD_FOR_DEPENDENCY_TEST.",
            )
        else:
            dependency_prompt = base.build_reconciliation_prompt(
                args.topic,
                "alpha",
                "UPSTREAM_REASONING_WITHHELD_FOR_DEPENDENCY_TEST.",
                str(alpha_reconciliation["role"]),
            )
        dependency_probe = _run_probe_stage(
            root,
            f"{args.session_id}__dependency_probe",
            "alpha_reconciliation_dependency_probe",
            str(alpha_reconciliation["role"]),
            str(alpha_reconciliation["model"]),
            dependency_prompt,
            args.ollama_base_url,
            args.debate_temp,
            args.max_tokens_turn,
            args.seed + 101,
            args.turn_timeout_sec,
            base.debate_validation_details,
            wing_name="alpha",
            system_prompt=system_prompt,
        )
        constraint_sensitivity = {
            "passed": False,
            "probe_completed": bool(dependency_probe["completed"]),
            "probe_error": dependency_probe["error"],
            "probe_error_category": dependency_probe["error_category"],
            "comparison": None,
        }
        if dependency_probe["completed"]:
            constraint_sensitivity = _build_dependency_test_result(
                actual_output=str(alpha_reconciliation["raw"]),
                probe_output=str(dependency_probe["output"]),
                manifest=manifest,
                root=root,
            )
            constraint_sensitivity.update(
                {
                    "probe_completed": True,
                    "probe_error": "",
                    "probe_error_category": "",
                }
            )
        probe_artifacts["dependency_probe"] = {
            "stage": "alpha_reconciliation",
            "role": str(alpha_reconciliation["role"]),
            "model": str(alpha_reconciliation["model"]),
            "prompt": dependency_prompt,
            "completed": bool(dependency_probe["completed"]),
            "error": dependency_probe["error"],
            "error_category": dependency_probe["error_category"],
            "output": dependency_probe["output"],
        }

        perturbed_blocks = [
            _render_trace_block(entry, _perturb_debate_block(str(entry.get("output", ""))))
            for entry in debate["trace"]
            if str(entry.get("stage", "")) != "king_synthesis"
        ]
        perturbed_transcript = "\n\n".join(perturbed_blocks)
        if neutral_prompt_mode:
            perturbation_prompt = base.build_neutral_king_prompt(
                args.topic,
                perturbed_transcript,
                f"{args.session_id}__perturbation_probe",
            )
        else:
            perturbation_prompt = base.build_king_prompt(
                args.topic,
                perturbed_transcript,
                f"{args.session_id}__perturbation_probe",
            )
        perturbation_probe = _run_probe_stage(
            root,
            f"{args.session_id}__perturbation_probe",
            "king_synthesis_perturbation_probe",
            str(debate["king_role"]),
            str(debate["king_model"]),
            perturbation_prompt,
            args.ollama_base_url,
            args.synth_temp,
            args.max_tokens_synth,
            args.seed + 202,
            args.synth_timeout_sec,
            base.canonical_validation_details,
            system_prompt=system_prompt,
        )
        perturbation_test = {
            "passed": False,
            "probe_completed": bool(perturbation_probe["completed"]),
            "probe_error": perturbation_probe["error"],
            "probe_error_category": perturbation_probe["error_category"],
            "comparison": None,
        }
        if perturbation_probe["completed"]:
            perturbation_test = _build_dependency_test_result(
                actual_output=str(debate["king_raw"]),
                probe_output=str(perturbation_probe["output"]),
                manifest=manifest,
                root=root,
            )
            perturbation_test.update(
                {
                    "probe_completed": True,
                    "probe_error": "",
                    "probe_error_category": "",
                }
            )
        probe_artifacts["perturbation_probe"] = {
            "stage": "king_synthesis",
            "role": str(debate["king_role"]),
            "model": str(debate["king_model"]),
            "prompt": perturbation_prompt,
            "completed": bool(perturbation_probe["completed"]),
            "error": perturbation_probe["error"],
            "error_category": perturbation_probe["error_category"],
            "output": perturbation_probe["output"],
        }

        challenge_removed_blocks = [
            _render_trace_block(entry, _neutralize_challenge_block(str(entry.get("output", ""))))
            for entry in debate["trace"]
            if str(entry.get("stage", "")) != "king_synthesis"
        ]
        challenge_removed_transcript = "\n\n".join(challenge_removed_blocks)
        if neutral_prompt_mode:
            challenge_probe_prompt = base.build_neutral_king_prompt(
                args.topic,
                challenge_removed_transcript,
                f"{args.session_id}__challenge_probe",
            )
        else:
            challenge_probe_prompt = base.build_king_prompt(
                args.topic,
                challenge_removed_transcript,
                f"{args.session_id}__challenge_probe",
            )
        challenge_probe = _run_probe_stage(
            root,
            f"{args.session_id}__challenge_probe",
            "king_synthesis_challenge_probe",
            str(debate["king_role"]),
            str(debate["king_model"]),
            challenge_probe_prompt,
            args.ollama_base_url,
            args.synth_temp,
            args.max_tokens_synth,
            args.seed + 303,
            args.synth_timeout_sec,
            base.canonical_validation_details,
            system_prompt=system_prompt,
        )
        raw_challenge_texts = (
            _split_probe_items(base.extract_section(str(stage_outputs["cross_critique"]["raw"]), ["CHALLENGE"]))
            + _split_probe_items(base.extract_section(str(stage_outputs["cross_exam"]["raw"]), ["CHALLENGE"]))
        )
        challenge_texts = list(dict.fromkeys(text for text in raw_challenge_texts if base.normalize_text(text)))
        non_cosmetic_challenge_test = {
            "passed": False,
            "probe_completed": bool(challenge_probe["completed"]),
            "probe_error": challenge_probe["error"],
            "probe_error_category": challenge_probe["error_category"],
            "comparison": None,
            "challenge_propagation": [],
            "propagated_count": 0,
        }
        if challenge_probe["completed"]:
            non_cosmetic_challenge_test = _build_non_cosmetic_challenge_result(
                actual_king=str(debate["king_raw"]),
                challenge_removed_king=str(challenge_probe["output"]),
                challenge_texts=challenge_texts,
                manifest=manifest,
                root=root,
            )
            non_cosmetic_challenge_test.update(
                {
                    "probe_completed": True,
                    "probe_error": "",
                    "probe_error_category": "",
                }
            )
        probe_artifacts["challenge_probe"] = {
            "stage": "king_synthesis",
            "model": str(debate["king_model"]),
            "prompt": challenge_probe_prompt,
            "completed": bool(challenge_probe["completed"]),
            "error": challenge_probe["error"],
            "error_category": challenge_probe["error_category"],
            "output": challenge_probe["output"],
        }

        structural_blocks = [
            _render_trace_block(entry, _structural_variant_debate_block(str(entry.get("output", ""))))
            for entry in debate["trace"]
            if str(entry.get("stage", "")) != "king_synthesis"
        ]
        structural_transcript = "\n\n".join(structural_blocks)
        if neutral_prompt_mode:
            structural_prompt = base.build_neutral_king_prompt(
                args.topic,
                structural_transcript,
                f"{args.session_id}__structural_probe",
            )
        else:
            structural_prompt = base.build_king_prompt(
                args.topic,
                structural_transcript,
                f"{args.session_id}__structural_probe",
            )
        structural_probe = _run_probe_stage(
            root,
            f"{args.session_id}__structural_probe",
            "king_synthesis_structural_probe",
            str(debate["king_role"]),
            str(debate["king_model"]),
            structural_prompt,
            args.ollama_base_url,
            args.synth_temp,
            args.max_tokens_synth,
            args.seed + 404,
            args.synth_timeout_sec,
            base.canonical_validation_details,
            system_prompt=system_prompt,
        )
        structural_variance = {
            "passed": False,
            "probe_completed": bool(structural_probe["completed"]),
            "probe_error": structural_probe["error"],
            "probe_error_category": structural_probe["error_category"],
            "comparison": None,
            "semantic_audit": _empty_semantic_audit_state(),
        }
        structural_variance["summary_counters"] = _build_structural_variance_summary_counters(structural_variance)
        if structural_probe["completed"]:
            structural_variance = _build_structural_variance_result(
                actual_king=str(debate["king_raw"]),
                structural_probe_output=str(structural_probe["output"]),
                manifest=manifest,
                root=root,
            )
            structural_variance.update(
                {
                    "probe_completed": True,
                    "probe_error": "",
                    "probe_error_category": "",
                }
            )
            model_metadata = {
                "role": str(debate["king_role"]),
                "model": str(debate["king_model"]),
            }
            stage_metadata = {
                "validation_stage": "structural_variance",
                "source_stage": "king_synthesis",
                "probe_stage": "king_synthesis_structural_probe",
            }
            structural_variance_telemetry = _build_structural_variance_telemetry(
                session_id=args.session_id,
                structural_variance=structural_variance,
                model_metadata=model_metadata,
                stage_metadata=stage_metadata,
            )
            structural_variance_telemetry_path = _write_structural_variance_telemetry(paths, structural_variance_telemetry)
            structural_variance["telemetry_path"] = structural_variance_telemetry_path
            probe_artifacts["structural_variance_telemetry_path"] = structural_variance_telemetry_path
            if semantic_audit_record_path:
                structural_variance["semantic_audit"]["artifact_path"] = semantic_audit_record_path
                probe_artifacts["semantic_audit_record_path"] = semantic_audit_record_path
            if structural_variance["semantic_audit"].get("flagged"):
                print(_semantic_audit_log_line(session_id=args.session_id, structural_variance=structural_variance), flush=True)
            print(_structural_variance_log_line(structural_variance), flush=True)
        probe_artifacts["structural_probe"] = {
            "stage": "king_synthesis",
            "role": str(debate["king_role"]),
            "model": str(debate["king_model"]),
            "prompt": structural_prompt,
            "completed": bool(structural_probe["completed"]),
            "error": structural_probe["error"],
            "error_category": structural_probe["error_category"],
            "output": structural_probe["output"],
        }

        shadow_run: dict[str, Any] | None = None
        shadow_error = ""
        shadow_error_category = ""
        try:
            shadow_run = _execute_debate(
                root,
                f"{args.session_id}__divergence_shadow",
                args.topic,
                hierarchy,
                args.ollama_base_url,
                args.debate_rounds,
                max(args.debate_temp, 0.95),
                max(args.synth_temp, 0.55),
                args.max_tokens_turn,
                args.max_tokens_synth,
                args.seed + 997,
                args.turn_timeout_sec,
                args.synth_timeout_sec,
                system_prompt=system_prompt,
                record_events=False,
            )
            divergence_test = _divergence_test(
                primary_trace=list(debate["trace"]),
                shadow_trace=list(shadow_run["trace"]),
                manifest=manifest,
                root=root,
            )
        except IntegrityViolation:
            raise
        except Exception as exc:
            shadow_error = str(exc)
            shadow_error_category = base.classify_stage_failure(exc)
            divergence_test = {
                "passed": False,
                "reason": shadow_error,
                "stage_pairs": [],
            }
        probe_artifacts["divergence_shadow"] = {
            "seed": args.seed + 997,
            "debate_temp": max(args.debate_temp, 0.95),
            "synth_temp": max(args.synth_temp, 0.55),
            "completed": shadow_run is not None,
            "error": shadow_error,
            "error_category": shadow_error_category,
            "trace": list(shadow_run["trace"]) if shadow_run is not None else [],
        }

        failure_modes = {
            "passed": bool(perturbation_test.get("passed")) and bool(divergence_test.get("passed")),
            "counterfactual_perturbation": perturbation_test,
            "divergence_shadow": divergence_test,
        }

        base.write_json_atomic(paths["probes"], probe_artifacts)
        interaction_report = _cognitive_validation_report(
            session_id=args.session_id,
            topic=args.topic,
            constraint_sensitivity=constraint_sensitivity,
            failure_modes=failure_modes,
            structural_variance=structural_variance,
            imperfect_synthesis=non_cosmetic_challenge_test,
            probe_artifacts=_report_probe_artifacts(paths, structural_variance_telemetry_path, semantic_audit_record_path),
        )
        _write_cognitive_validation_report(paths, interaction_report)
        if not interaction_report.get("passed"):
            if os.environ.get("SOVEREIGN_CONCURRENCE_ROUND") == "1":
                # Concurrence re-round (IMPLEMENTATION_MAPPING S3.2: no cognitive-probe
                # enforcement inside the loop). The report above is still written; the
                # loop controller enforces structural variance from the telemetry and
                # the quality gate remains the acceptance oracle. Round 1 and stock
                # runs are unaffected (env var set only by run_concurrence_rounds).
                print(
                    f"[live_orchestrator] cognitive validation advisory-only for concurrence re-round "
                    f"(failures={interaction_report.get('failures')})",
                    flush=True,
                )
            else:
                raise base.SynthesisError("cognitive validation failed")

        metrics = base.deterministic_metrics(str(debate["king_raw"]))
        answer = base.build_answer_payload(
            session_id=args.session_id,
            topic=args.topic,
            metrics=metrics,
            governance={
                "autonomy_mode": mode,
                "constitution_state_path": str(
                    root / "constitution" / "constitution_state.json"
                ),
                "contract_path": str(root / "synthesis" / "synthesis_contract.json"),
                "system_prompt_file": (
                    str(Path(args.system_prompt_file).resolve())
                    if args.system_prompt_file
                    else None
                ),
                "execution_mode": LIVE_EXECUTION_MODE,
            },
            hierarchy=hierarchy,
            trace=list(debate["trace"]),
            king_text=str(debate["king_raw"]),
            output_paths={},
        )
        voice = base.build_sovereign_voice(answer, {"autonomy_mode": mode})
        report = base.build_praxis_report(answer, {"autonomy_mode": mode})
        dialog_text = "\n\n".join(
            list(debate["transcript_blocks"])
            + [
                base.render_block(
                    str(debate["king_role"]),
                    str(debate["king_model"]),
                    str(debate["king_raw"]),
                )
            ]
        )
        outputs = base.write_outputs(root, args.session_id, answer, voice, report, dialog_text)
        outputs.update(
            {
                "live_runtime_dir": str(paths["runtime_dir"]),
                "live_turn_manifest_path": str(paths["turn_manifest"]),
                "role_model_mapping_path": str(paths["role_map"]),
                "live_activation_report_path": str(paths["activation"]),
                "cognitive_validation_report_path": str(paths["cognitive"]),
                "interaction_validation_report_path": str(paths["interaction"]),
                "validation_probe_path": str(paths["probes"]),
                "structural_variance_telemetry_path": structural_variance_telemetry_path,
                "semantic_audit_record_path": semantic_audit_record_path,
                "synthesis_outcome_record_path": synthesis_outcome_record_path,
            }
        )
        arbitration_artifact, contract_report = _materialize_runtime_contract(
            root=root,
            session_id=args.session_id,
            topic=args.topic,
            manifest=manifest,
            turns=turns,
            dialog_text=dialog_text,
            dialog_source_path=str(outputs.get("dialog_session_path", "")),
            failure_reason="",
            prefer_dialog_analysis=True,
            provenance=provenance,
        )
        runtime_contract = _runtime_contract_metadata(
            root=root,
            session_id=args.session_id,
            arbitration_artifact=arbitration_artifact,
            contract_report=contract_report,
        )
        semantic_audit_record = _build_learning_semantic_audit_record(
            session_id=args.session_id,
            runtime_root=str(provenance.get("runtime_root", "")),
            broker_root=str(provenance.get("broker_root", "")),
            contract_status=contract_report.get("contract_status"),
            structural_variance=structural_variance,
            synthesis_artifact=str(outputs.get("praxis_answer_session_path", "")).strip() or None,
            model_route=_collect_model_route(turns),
            activation_report=activation_report,
            interaction_report=interaction_report,
            turns=turns,
            model_metadata={"role": str(debate["king_role"]), "model": str(debate["king_model"])},
            stage_metadata={
                "validation_stage": "structural_variance",
                "source_stage": "king_synthesis",
                "probe_stage": "king_synthesis_structural_probe",
            },
            contract_report=contract_report,
            provenance=provenance,
        )
        semantic_audit_record_path = _write_semantic_audit_record(paths, semantic_audit_record)
        synthesis_outcome_record = _build_synthesis_outcome_record(
            session_id=args.session_id,
            runtime_root=str(provenance.get("runtime_root", "")),
            broker_root=str(provenance.get("broker_root", "")),
            contract_status=contract_report.get("contract_status"),
            synthesis_artifact=str(outputs.get("praxis_answer_session_path", "")).strip() or None,
            praxis_artifact=str(outputs.get("praxis_answer_path", "")).strip() or None,
            arbitration_artifact=runtime_contract.get("artifact_path"),
            activation_report=activation_report,
            interaction_report=interaction_report,
            structural_variance=structural_variance,
            turns=turns,
            provenance=provenance,
        )
        synthesis_outcome_record_path = _write_synthesis_outcome_record(paths, synthesis_outcome_record)
        outputs["arbitration_path"] = runtime_contract["artifact_path"]
        outputs["contract_execution_signal_path"] = runtime_contract["contract_execution_signal_path"]
        answer["outputs"] = outputs
        # Phase 20.2 — record CAS metadata from debate result
        answer["contradiction_aware_synthesis"] = debate.get("contradiction_aware_synthesis", {"enabled": False})
        # Phase 20.4 — record routing metadata
        answer["pressure_routing"] = _routing_meta
        base.write_json_atomic(Path(outputs["praxis_answer_path"]), answer)
        base.write_json_atomic(Path(outputs["praxis_answer_session_path"]), answer)
        audit_path = base.audit_synthesis(root, args.session_id, answer, mode)
        summary = {
            "ok": True,
            "session_id": args.session_id,
            "topic": args.topic,
            "mode": mode,
            "execution_mode": LIVE_EXECUTION_MODE,
            "contract": contract,
            "runtime_contract": runtime_contract,
            "outputs": outputs,
            "constitution_audit_path": audit_path,
            "metrics": metrics,
            "summary_counters": _build_structural_variance_summary_counters(structural_variance),
        }
        trace_contract_status_from_mapping(
            base_dir=root,
            session_id=args.session_id,
            checkpoint="CONTRACT_ATTACHED",
            container=summary.get("runtime_contract") if isinstance(summary.get("runtime_contract"), dict) else None,
            container_name="synthesis_summary.runtime_contract",
            source_file=Path(__file__),
            guard=IntegrityGuard(base_dir=root),
        )
        base.append_log_line(
            root / "logs" / "system.txt",
            {
                "ts": base.utc_now_iso(),
                "source": "synth_king",
                "event": "synthesis_summary",
                "summary": summary,
                "session_id": args.session_id,
            },
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        # Phase 2.5F: write latency telemetry on success path
        _write_turn_latency_telemetry(
            paths["runtime_dir"],
            args.session_id,
            _latency_records,
            timeout_config=_timeout_config,
        )
        return 0
    except IntegrityViolation:
        raise
    except Exception as exc:
        if turns and not turn_manifest_path:
            turn_manifest_path = _write_turn_manifest(
                paths,
                args.session_id,
                args.topic,
                turns,
                provenance,
            )
        elif not turn_manifest_path and paths["turn_manifest"].exists():
            turn_manifest_path = str(paths["turn_manifest"])
        if probe_artifacts and not paths["probes"].exists():
            base.write_json_atomic(paths["probes"], probe_artifacts)
        if activation_report is None:
            activation_report = _activation_report(
                args.session_id,
                args.topic,
                turns,
                role_map_path,
                turn_manifest_path,
                broker,
                provenance,
                args.ollama_base_url,
                failure_reason=str(exc),
            )
            base.write_json_atomic(paths["activation"], activation_report)
        if interaction_report is None:
            interaction_report = {
                "schema_version": "1.0",
                "generated_at": base.utc_now_iso(),
                "execution_mode": LIVE_EXECUTION_MODE,
                "session_id": args.session_id,
                "topic": args.topic,
                "passed": False,
                "suspicious": False,
                "suspicious_reasons": [],
                "tests": {},
                "probe_artifacts": _report_probe_artifacts(paths, structural_variance_telemetry_path),
                "failures": [str(exc)],
            }
            _write_cognitive_validation_report(paths, interaction_report)
        error = {
            "ok": False,
            "session_id": args.session_id,
            "topic": args.topic,
            "error": str(exc),
            "error_category": base.classify_stage_failure(exc),
            "live_activation_report_path": str(paths["activation"]),
            "cognitive_validation_report_path": str(paths["cognitive"]),
            "interaction_validation_report_path": str(paths["interaction"]),
        }
        arbitration_artifact, contract_report = _materialize_runtime_contract(
            root=root,
            session_id=args.session_id,
            topic=args.topic,
            manifest=manifest,
            turns=turns,
            dialog_text="",
            dialog_source_path=turn_manifest_path or (str(paths["turn_manifest"]) if paths["turn_manifest"].exists() else ""),
            failure_reason=str(exc),
            prefer_dialog_analysis=False,
            provenance=provenance,
        )
        runtime_contract = _runtime_contract_metadata(
            root=root,
            session_id=args.session_id,
            arbitration_artifact=arbitration_artifact,
            contract_report=contract_report,
        )
        error["runtime_contract"] = runtime_contract
        model_metadata = None
        if turns and _turn_stage_seen(turns, "king_synthesis"):
            for turn in turns:
                if str(turn.get("stage", "")).strip() == "king_synthesis":
                    model_metadata = {
                        "role": str(turn.get("role", "")).strip(),
                        "model": str(turn.get("model", "")).strip(),
                    }
                    break
        try:
            semantic_audit_record = _build_learning_semantic_audit_record(
                session_id=args.session_id,
                runtime_root=str(provenance.get("runtime_root", "")),
                broker_root=str(provenance.get("broker_root", "")),
                contract_status=contract_report.get("contract_status"),
                structural_variance=structural_variance if isinstance(structural_variance, dict) else None,
                synthesis_artifact=None,
                model_route=_collect_model_route(turns),
                activation_report=activation_report,
                interaction_report=interaction_report,
                turns=turns,
                explicit_error=str(exc),
                model_metadata=model_metadata,
                stage_metadata={
                    "validation_stage": "structural_variance",
                    "source_stage": "king_synthesis",
                    "probe_stage": "king_synthesis_structural_probe",
                }
                if model_metadata
                else None,
                contract_report=contract_report,
                provenance=provenance,
            )
            semantic_audit_record_path = _write_semantic_audit_record(paths, semantic_audit_record)
        except Exception as record_exc:
            error["semantic_audit_record_error"] = str(record_exc)
        try:
            synthesis_outcome_record = _build_synthesis_outcome_record(
                session_id=args.session_id,
                runtime_root=str(provenance.get("runtime_root", "")),
                broker_root=str(provenance.get("broker_root", "")),
                contract_status=contract_report.get("contract_status"),
                synthesis_artifact=None,
                praxis_artifact=None,
                arbitration_artifact=runtime_contract.get("artifact_path"),
                activation_report=activation_report,
                interaction_report=interaction_report,
                structural_variance=structural_variance if isinstance(structural_variance, dict) else None,
                turns=turns,
                explicit_error=str(exc),
                error_category=error["error_category"],
                provenance=provenance,
            )
            synthesis_outcome_record_path = _write_synthesis_outcome_record(paths, synthesis_outcome_record)
        except Exception as record_exc:
            error["synthesis_outcome_record_error"] = str(record_exc)
        trace_contract_status_from_mapping(
            base_dir=root,
            session_id=args.session_id,
            checkpoint="CONTRACT_ATTACHED",
            container=error.get("runtime_contract") if isinstance(error.get("runtime_contract"), dict) else None,
            container_name="synthesis_error.runtime_contract",
            source_file=Path(__file__),
            guard=IntegrityGuard(base_dir=root),
        )
        base.append_log_line(
            root / "logs" / "system.txt",
            {
                "ts": base.utc_now_iso(),
                "source": "synth_king",
                "event": "synthesis_error",
                **error,
            },
        )
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        # Phase 2.5F: write latency telemetry on exception path
        _write_turn_latency_telemetry(
            paths["runtime_dir"],
            args.session_id,
            _latency_records,
            timeout_config=_timeout_config,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())






