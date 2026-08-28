from __future__ import annotations

from pathlib import Path

from distillery.common import ContractError, sha256_value, utc_now
from grounded.curation import select_trainable_turns
from grounded.harness_adapters import import_result_record, import_session_turns, source_session_key
from grounded.monitoring import verify_instrumentation_checksums
from grounded.telemetry import TraceStore


def _content_free_live_evidence(session: dict) -> dict:
    label = session["explicit_label"]
    failure_type = next((turn["measured"].get("failure_type") for turn in session["turns"] if turn["measured"].get("failure_type")), None)
    return {
        "session_id_hash": sha256_value(session["session_id"]),
        "turn_id_hashes": [sha256_value(turn["turn_id"]) for turn in session["turns"]],
        "started_at": session["started_at"],
        "ended_at": session["finished_at"],
        "harness": session["harness"],
        "route": session["route"],
        "teacher_provider_identifier": f"{session['provider']}:{session['model_id']}:{session['revision']}",
        "source_admission_class": session["source_admission_class"],
        "outcome": "failure" if session["outcome"] == "fail" else session["outcome"],
        "signal_type": "explicit",
        "label_path": label["path"],
        "label_origin": label["label_origin"],
        "label_timestamp": label["recorded_at"],
        "validator_result": failure_type or ("passed" if session["outcome"] == "success" else "failed"),
        "content_payload_present": False,
    }


def reevaluate_hg0(
    *,
    store: TraceStore,
    success_session_id: str,
    failure_session_id: str,
    expected_checksums: dict[str, str | dict],
    component_paths: dict[str, str | Path],
) -> dict:
    """Re-evaluate HG-0 from live marks plus preserved content-free evidence."""
    success = store.get(success_session_id)
    failure = store.get(failure_session_id)
    sessions = store.sessions()
    recovery = next(
        (
            session
            for session in sessions
            if session["outcome"] == "success"
            and any(turn["tool_status"] == "failed" and turn["superseded"] for turn in session["turns"])
            and any(turn["tool_status"] == "passed" and turn["recovery"] for turn in session["turns"])
        ),
        None,
    )
    unknown_rejected = next(
        (
            session
            for session in sessions
            if session["source_admission_class"] == "UNKNOWN"
            and {item["channel"] for item in session["rejections"]} >= {"training_shard", "synthetic_seed"}
        ),
        None,
    )
    labels_seen: set[str] = set()
    no_label_path_observed = False
    for event in store.event_history():
        if event["event"] == "label":
            labels_seen.add(event["session_id"])
        elif event["event"] == "outcome" and event["session_id"] not in labels_seen:
            no_label_path_observed = True
    dashboard = store.dashboard()
    alerts = store.alerts()
    checksum_guard = verify_instrumentation_checksums(expected_checksums, component_paths)
    assertions = {
        "G0-A": success["outcome"] == "success" and success["explicit_label"] is not None and success["explicit_label"]["path"] == "/success" and success["explicit_label"]["label_origin"] == "live_operator_mark" and bool(success["turns"]) and all(turn["content"] is None for turn in success["turns"]),
        "G0-B": failure["outcome"] == "fail" and failure["explicit_label"] is not None and failure["explicit_label"]["path"] == "/fail" and failure["explicit_label"]["label_origin"] == "live_operator_mark" and any(turn["tool_status"] == "failed" for turn in failure["turns"]) and all(turn["content"] is None for turn in failure["turns"]),
        "G0-C": recovery is not None,
        "G0-D": unknown_rejected is not None,
        "implicit_positive_signals": dashboard["implicit_signals"]["positive"] >= 1,
        "implicit_negative_signals": dashboard["implicit_signals"]["negative"] >= 1,
        "gold_accrual_dashboard": dashboard["gold_accrual_candidates"] >= 1,
        "explicit_label_compliance_dashboard": dashboard["explicit_label_compliance"]["rate"] == 1.0,
        "channel_rejection_metrics": dashboard["channel_rejections"].get("training_shard:UNKNOWN", 0) >= 1 and dashboard["channel_rejections"].get("synthetic_seed:UNKNOWN", 0) >= 1,
        "no_trace_alert_path": any(item["code"] == "NO_TRACE" and item["fixture"] is True for item in alerts),
        "no_label_alert_path": no_label_path_observed,
        "instrumentation_checksum_guard": checksum_guard["passed"],
        "fixture_alerts_distinguishable": all(item["fixture"] is True for item in alerts if item["code"] == "NO_TRACE"),
    }
    return {
        "status": "PASS" if all(assertions.values()) else "FAIL",
        "hg0": "PASS" if all(assertions.values()) else "LIMITED_PENDING_LIVE_OPERATOR_MARKS",
        "captured_at": utc_now(),
        "assertions": assertions,
        "live_success_evidence": _content_free_live_evidence(success),
        "live_failure_evidence": _content_free_live_evidence(failure),
        "preserved_recovery_session_id_hash": sha256_value(recovery["session_id"]) if recovery else None,
        "preserved_unknown_rejection_session_id_hash": sha256_value(unknown_rejected["session_id"]) if unknown_rejected else None,
        "dashboard": dashboard,
        "active_alerts": [{"code": item["code"], "session_id_hash": sha256_value(item["session_id"]), "fixture": item["fixture"]} for item in alerts],
        "checksum_guard": checksum_guard,
        "content_payload_present": False,
        "event_manifest": store.hashed_event_manifest(),
    }


def run_live_acceptance(
    *,
    success_turn_paths: list[str | Path],
    failure_result_path: str | Path,
    recovery_failure_result_path: str | Path,
    recovery_success_result_path: str | Path,
    no_trace_source_id: str,
    store: TraceStore,
    expected_checksums: dict[str, str | dict],
    component_paths: dict[str, str | Path],
) -> dict:
    """Import content-free Sovereign records without representing import labels as live."""
    pre_label_codes: set[str] = set()

    success_import = import_session_turns(success_turn_paths, store)
    success_id = success_import["session_id"]
    store.success(success_id)
    pre_label_codes.update(item["code"] for item in store.alerts())
    store.explicit_label(success_id, "success", label_origin="import_time_classification")
    store.implicit_signal(success_id, "positive", "clean_completed_trace", evidence_hash=sha256_value(store.get(success_id)["turns"]))

    failure_import = import_result_record(failure_result_path, store)
    failure_id = failure_import["session_id"]
    store.fail(failure_id)
    pre_label_codes.update(item["code"] for item in store.alerts())
    store.explicit_label(failure_id, "fail", label_origin="import_time_classification")
    store.implicit_signal(failure_id, "negative", "process_failure", evidence_hash=sha256_value(store.get(failure_id)["turns"]))

    recovery_failure = import_result_record(recovery_failure_result_path, store, superseded=True)
    recovery_id = recovery_failure["session_id"]
    store.implicit_signal(recovery_id, "negative", "cancelled_attempt", evidence_hash=sha256_value(store.get(recovery_id)["turns"][-1]))
    recovery_success = import_result_record(recovery_success_result_path, store, recovery=True, superseded=False)
    if recovery_success["session_id"] != recovery_id:
        raise ContractError("recovery records did not join to one stable session")
    store.success(recovery_id)
    pre_label_codes.update(item["code"] for item in store.alerts())
    store.explicit_label(recovery_id, "success", label_origin="import_time_classification")
    store.implicit_signal(recovery_id, "positive", "eventual_success_after_failure", evidence_hash=sha256_value(store.get(recovery_id)["turns"]))

    corpus_rejected = seed_rejected = False
    try:
        store.admit_for_corpus(success_id, "UNKNOWN")
    except ContractError:
        corpus_rejected = True
    try:
        store.admit_as_seed(success_id, "UNKNOWN")
    except ContractError:
        seed_rejected = True

    no_trace_id = source_session_key(no_trace_source_id)
    store.start(no_trace_id, harness="sovereign_product.session", provider="UNKNOWN", model_id="UNKNOWN", revision="UNKNOWN", fixture=True)
    current_alerts = store.alerts()
    dashboard = store.dashboard()
    checksum_guard = verify_instrumentation_checksums(expected_checksums, component_paths)

    success = store.get(success_id)
    failure = store.get(failure_id)
    recovery = store.get(recovery_id)
    selected_recovery = select_trainable_turns(recovery)
    assertions = {
        "G0-A": len(success["turns"]) >= 2 and success["outcome"] == "success" and success["explicit_label"]["path"] == "/success" and success["explicit_label"]["label_origin"] == "live_operator_mark" and all(all(turn["provenance"].get(name) for name in ("harness", "provider", "model_id", "revision")) for turn in success["turns"]),
        "G0-B": len(failure["turns"]) >= 1 and failure["outcome"] == "fail" and failure["explicit_label"]["path"] == "/fail" and failure["explicit_label"]["label_origin"] == "live_operator_mark",
        "G0-C": recovery["outcome"] == "success" and any(turn["tool_status"] == "failed" and turn["superseded"] for turn in recovery["turns"]) and any(turn["recovery"] and turn["tool_status"] == "passed" for turn in recovery["turns"]) and all(turn["tool_status"] != "failed" and not turn["superseded"] for turn in selected_recovery) and any(turn["recovery"] for turn in selected_recovery),
        "G0-D": bool(success["turns"]) and corpus_rejected and seed_rejected and len(success["rejections"]) == 2,
        "implicit_positive_signals": dashboard["implicit_signals"]["positive"] >= 2,
        "implicit_negative_signals": dashboard["implicit_signals"]["negative"] >= 2,
        "gold_accrual_dashboard": dashboard["gold_accrual_candidates"] >= 2,
        "explicit_label_compliance_dashboard": dashboard["explicit_label_compliance"]["rate"] == 1.0,
        "channel_rejection_metrics": dashboard["channel_rejections"].get("training_shard:UNKNOWN") == 1 and dashboard["channel_rejections"].get("synthetic_seed:UNKNOWN") == 1,
        "no_trace_alert_path": any(item["code"] == "NO_TRACE" and item["session_id"] == no_trace_id and item["fixture"] is True for item in current_alerts),
        "no_label_alert_path": "NO_LABEL" in pre_label_codes,
        "instrumentation_checksum_guard": checksum_guard["passed"],
    }
    non_operator_assertions = {key: value for key, value in assertions.items() if key not in {"G0-A", "G0-B"}}
    fully_passed = all(assertions.values())
    limited_only_by_marks = all(non_operator_assertions.values()) and not (assertions["G0-A"] and assertions["G0-B"])
    return {
        "status": "PASS" if fully_passed else "PASS_WITH_LIMITATIONS" if limited_only_by_marks else "FAIL",
        "hg0": "PASS" if fully_passed else "LIMITED_PENDING_LIVE_OPERATOR_MARKS" if limited_only_by_marks else "BLOCKED",
        "captured_at": utc_now(),
        "real_evidence": True,
        "raw_content_copied": False,
        "source_admission": "UNKNOWN",
        "telemetry_blocked_by_admission": False,
        "sessions": {"success": success_id, "failure": failure_id, "recovery": recovery_id, "no_trace_monitor": no_trace_id},
        "turn_counts": {"success": len(success["turns"]), "failure": len(failure["turns"]), "recovery": len(recovery["turns"])},
        "assertions": assertions,
        "dashboard": dashboard,
        "active_alerts": current_alerts,
        "checksum_guard": checksum_guard,
        "content_free_evidence": True,
        "label_origins": {"success": success["explicit_label"]["label_origin"], "failure": failure["explicit_label"]["label_origin"], "recovery": recovery["explicit_label"]["label_origin"]},
        "hashed_event_manifest": store.hashed_event_manifest(),
        "limitation": None if fully_passed else "G0-A and G0-B require new live_operator_mark evidence; import-time classification is retained as real telemetry but does not satisfy the operator-mark contract.",
    }
