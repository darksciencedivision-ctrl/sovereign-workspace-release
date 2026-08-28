from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_MODES = {"OFF", "OBSERVE", "SANDBOX", "PROMOTE"}
ROLE_ORDER = ["analyzer", "architect", "coder", "tester", "auditor", "benchmark", "promoter"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            if not payload.endswith("\n"):
                handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_constitution_state(root: Path) -> dict[str, Any]:
    state = read_json(root / "constitution" / "constitution_state.json", {})
    if not isinstance(state, dict):
        state = {}
    mode = str(state.get("mode", "OBSERVE")).strip().upper() or "OBSERVE"
    if mode not in VALID_MODES:
        mode = "OBSERVE"
    state["mode"] = mode
    return state


def latest_run_record(root: Path, session_id: str = "") -> dict[str, Any]:
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return {}
    files = sorted(runs_dir.glob("cycle-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for file_path in files:
        data = read_json(file_path, {})
        if not isinstance(data, dict):
            continue
        if session_id and str(data.get("session_id", "")).strip() != session_id:
            continue
        data["_path"] = str(file_path)
        return data
    return {}


def latest_praxis_answer(root: Path, session_id: str = "") -> dict[str, Any]:
    answer_path = root / "output" / "praxis" / "praxis_answer.json"
    answer = read_json(answer_path, {})
    if not isinstance(answer, dict):
        return {}
    if session_id and str(answer.get("session_id", "")).strip() not in {"", session_id}:
        return {}
    answer["_path"] = str(answer_path)
    return answer


def constitutional_validation(state: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    if not bool(answer.get("canonical", False)):
        violations.append("canonical_answer_missing_canonical_flag")
    if not bool(answer.get("memory_allowed", False)):
        violations.append("canonical_answer_not_memory_allowed")
    outputs = answer.get("outputs", {}) if isinstance(answer.get("outputs"), dict) else {}
    voice_path = str(outputs.get("sovereign_voice_path", "")).lower()
    report_path = str(outputs.get("praxis_report_path", "")).lower()
    if voice_path and "sovereign_voice" not in voice_path:
        violations.append("voice_path_not_isolated")
    if report_path and "praxis_report" not in report_path:
        violations.append("report_path_not_isolated")
    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "mode": state.get("mode", "OBSERVE"),
    }


def role_report(role: str, state: dict[str, Any], run_record: dict[str, Any], answer: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    metrics = run_record.get("metrics", {}) if isinstance(run_record.get("metrics"), dict) else {}
    answer_metrics = answer.get("metrics", {}) if isinstance(answer.get("metrics"), dict) else {}
    convergence = metrics.get("structural_completeness", answer_metrics.get("structural_completeness", 0))
    confidence = metrics.get("response_elaboration", answer_metrics.get("response_elaboration", 0))
    findings: list[str] = []
    if role == "analyzer":
        findings.append(f"Latest structural_completeness={convergence} response_elaboration={confidence}")
        findings.append("Analyze only the canonical Praxis Answer and run metadata.")
    elif role == "architect":
        findings.append("Prefer additive changes and sandbox-first proposals.")
    elif role == "coder":
        findings.append("Never apply direct production code changes autonomously.")
    elif role == "tester":
        findings.append("Benchmarks and tests must stay inside sandbox outputs.")
    elif role == "auditor":
        findings.append("Audit constitutional separation of canonical and non-canonical channels.")
        if validation["violations"]:
            findings.extend(validation["violations"])
    elif role == "benchmark":
        findings.append("Prepare benchmark scope only when mode is SANDBOX or PROMOTE.")
    elif role == "promoter":
        findings.append("Promotion requires explicit human review and reversible artifacts.")
    return {
        "role": role,
        "mode": state.get("mode", "OBSERVE"),
        "ts": utc_now_iso(),
        "session_id": run_record.get("session_id") or answer.get("session_id", ""),
        "findings": findings,
    }


def write_role_artifacts(root: Path, mode: str, session_id: str, reports: list[dict[str, Any]], validation: dict[str, Any]) -> dict[str, str]:
    paths: dict[str, str] = {}
    if mode in {"SANDBOX", "PROMOTE"}:
        candidate_path = root / "sandbox" / "candidate_patches" / f"{session_id}_clu_candidate.md"
        candidate_text = "\n".join(
            [
                "# CLU Candidate Packet",
                "",
                f"Session: {session_id}",
                f"Mode: {mode}",
                "",
                "This packet is advisory only. It must not be auto-applied to production.",
                "",
                "## Role Summaries",
            ] + [f"- {report['role']}: {' | '.join(report['findings'])}" for report in reports]
        )
        write_text_atomic(candidate_path, candidate_text)
        paths["candidate_patch_report"] = str(candidate_path)

        benchmark_path = root / "sandbox" / "benchmarks" / f"{session_id}_benchmark_scope.json"
        write_json_atomic(
            benchmark_path,
            {
                "schema_version": "1.0",
                "generated_at": utc_now_iso(),
                "session_id": session_id,
                "mode": mode,
                "validation": validation,
                "scope": "No benchmark executed automatically; sandbox scope prepared only.",
            },
        )
        paths["benchmark_scope"] = str(benchmark_path)

    if mode == "PROMOTE":
        target_dir = root / "ledger" / "promotions" if validation["passed"] else root / "ledger" / "rejections"
        proposal_path = target_dir / f"{session_id}_promotion_packet.json"
        write_json_atomic(
            proposal_path,
            {
                "schema_version": "1.0",
                "generated_at": utc_now_iso(),
                "session_id": session_id,
                "mode": mode,
                "validation": validation,
                "status": "proposal_only",
                "human_review_required": True,
            },
        )
        paths["promotion_packet"] = str(proposal_path)

    return paths


def run_loop(root: Path, session_id: str = "", trigger: str = "manual") -> dict[str, Any]:
    state = load_constitution_state(root)
    mode = state.get("mode", "OBSERVE")
    run_record = latest_run_record(root, session_id)
    answer = latest_praxis_answer(root, session_id)
    effective_session_id = str(session_id or run_record.get("session_id") or answer.get("session_id") or "unknown-session").strip()
    validation = constitutional_validation(state, answer)
    reports = [role_report(role, state, run_record, answer, validation) for role in ROLE_ORDER]
    artifacts = write_role_artifacts(root, mode, effective_session_id, reports, validation)

    audit = {
        "schema_version": "1.0",
        "generated_at": utc_now_iso(),
        "trigger": trigger,
        "mode": mode,
        "session_id": effective_session_id,
        "run_record_path": run_record.get("_path", ""),
        "praxis_answer_path": answer.get("_path", ""),
        "validation": validation,
        "role_reports": reports,
        "artifacts": artifacts,
    }
    audit_path = root / "ledger" / "constitution_audits" / f"{effective_session_id}_clu_audit.json"
    write_json_atomic(audit_path, audit)
    audit["audit_path"] = str(audit_path)
    return audit


def run_role_only(root: Path, role: str, session_id: str = "", trigger: str = "manual") -> dict[str, Any]:
    if role not in ROLE_ORDER:
        raise ValueError(f"Unknown CLU role: {role}")
    state = load_constitution_state(root)
    run_record = latest_run_record(root, session_id)
    answer = latest_praxis_answer(root, session_id)
    validation = constitutional_validation(state, answer)
    report = role_report(role, state, run_record, answer, validation)
    out_dir = root / "sandbox" / "test_reports"
    if role == "benchmark":
        out_dir = root / "sandbox" / "benchmarks"
    elif role == "promoter":
        out_dir = root / "sandbox" / "promotion_reports"
    path = out_dir / f"{(session_id or run_record.get('session_id') or 'unknown-session')}_{role}.json"
    write_json_atomic(
        path,
        {
            "schema_version": "1.0",
            "generated_at": utc_now_iso(),
            "trigger": trigger,
            "report": report,
            "validation": validation,
        },
    )
    return {"ok": True, "role": role, "path": str(path), "report": report, "validation": validation}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOVEREIGN CLU control plane loop")
    parser.add_argument("--root", default=None,
                        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--role", default="")
    return parser.parse_args()


def _resolve_root(cli_root: str | None) -> Path:
    """Resolve SOVEREIGN root via the single authority (tools/sovereign_paths.py)."""
    repo = Path(__file__).resolve().parents[1]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from tools.sovereign_paths import get_repo_root, configure_root
    return configure_root(cli_root) if cli_root else get_repo_root()


def main() -> int:
    args = _parse_args()
    root = _resolve_root(args.root)
    args.root = str(root)
    if args.role:
        result = run_role_only(root, args.role.strip().lower(), args.session_id.strip(), args.trigger.strip() or "manual")
    else:
        result = run_loop(root, args.session_id.strip(), args.trigger.strip() or "manual")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
