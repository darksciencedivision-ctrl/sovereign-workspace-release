#!/usr/bin/env python3
from __future__ import annotations

# F-125 - QUARANTINE / SUPPORT DISPOSITION. This legacy Phase-8/9 engine (cycle_runner_v3.py,
# document_assembler.py, broker_v21/, synthesis/synth_king.py, clu/) is NOT on the shipped product
# route. Product DEEP traffic runs through sovereign_product/ (server.py ->
# semantic_deep.SemanticDeepExecutor); executors.DeepExecutor, the only code that drives this runner,
# refuses unless SOVEREIGN_ALLOW_LEGACY_DEEP=1 and is never the default executor. Do not add a
# product caller. It still ships and can be run directly, so bounded defects are corrected, each
# pinned by tests/test_legacy_engine_bounded_repairs.py:
#   (a) O(1) log append  (b)/(h) one cycle per root (OS lock; a concurrent cycle is refused with a
#   record, exit 9)  (c) STOP writes a record and exits 8  (d) broker tree-kill on timeout
#   (e) CLU via sys.executable; --stream/--no-stream meaningful  (f) stale PRAXIS result cleared;
#   Ollama call ignores ambient proxies  (g) synth_king O(1) append; one system-log read per run
#   (i) real U+2022 bullets  (k) broker debate under this interpreter and not killed by stderr
#   (l) broker_once honours STOP, writes the topic first, ignores stale synthesis, leaves no latch
#   (m) CLU reads runs/<session_id>.json.
# NOT repaired (unsupported legacy, recorded in the remediation register): per-session IPC paths
# (concurrency is refused instead); IntegrityGuard cost growing with past sessions (h); the LIVE
# shadow debate and "suspiciously stable" rejection (j) - a behavioural decision, not a defect fix;
# praxis/praxis_query.py and research/scripts/theorem_safe_runtime.py are not part of this module,
# so the Phase-9 publication path and safe theorem mode fail with that stated cause (m).

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import quality_gate
from artifact_integrity import (
    apply_provenance,
    build_stage_state,
    infer_dialog_origin,
    normalize_failure_reason,
    persist_artifact_integrity_report,
)
from claim_arbitrator import build_praxis_entries, persist_arbitration_stub
from sovereign_version import PRODUCT_VERSION

try:
    from evaluation.contract import enforce_contract
    from evaluation.contract_trace import trace_contract_status_from_mapping
    from evaluation.integrity import IntegrityGuard, IntegrityViolation
except ImportError:  # pragma: no cover - fallback for direct module execution
    from contract import enforce_contract
    from contract_trace import trace_contract_status_from_mapping
    from integrity import IntegrityGuard, IntegrityViolation

SCHEMA_VERSION = "1.0"
SOVEREIGN_VERSION = PRODUCT_VERSION
MODULE_NAME = "CYCLE_V3"
MAX_LOG_BYTES = 10 * 1024 * 1024
TOPIC_OPEN_TAG_RE = re.compile(r"\[TOPIC session_id=[^\]]+\]\s*", re.IGNORECASE)
TOPIC_CLOSE_TAG_RE = re.compile(r"\[/TOPIC\]\s*", re.IGNORECASE)
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SECTION_RE_TEMPLATE = r"(?ims)^\s*{name}\s*:\s*(.*?)(?=^\s*[A-Z_][A-Z_ ]{{2,40}}\s*:|\Z)"
VALID_MODES = {"OFF", "OBSERVE", "SANDBOX", "PROMOTE"}
INTEGRITY_FAILURE_EXIT_CODE = 97
_RUNTIME_WRITE_GUARD: IntegrityGuard | None = None
_RUNTIME_ALLOWED_WRITE_ROOTS: tuple[Path, ...] = ()
_RUNTIME_SESSION_ID = ""
CLU_RUNTIME_POLICY_RELATIVE_PATH = Path("library") / "config" / "clu_runtime_policy.json"
CLU_DISABLED_REASON = "CLU disabled by library/config/clu_runtime_policy.json"


def _runtime_allowed_write_roots(root: Path) -> tuple[Path, ...]:
    return (
        (root / "logs").resolve(),
        (root / "runs").resolve(),
        (root / "output").resolve(),
        (root / "praxis").resolve(),
        (root / "orchestra").resolve(),
        (root / "scheduler" / "state").resolve(),
        (root / "broker_v21" / "inbox").resolve(),
    )


def _configure_runtime_integrity(root: Path, session_id: str = "") -> None:
    global _RUNTIME_WRITE_GUARD, _RUNTIME_ALLOWED_WRITE_ROOTS, _RUNTIME_SESSION_ID
    _RUNTIME_WRITE_GUARD = IntegrityGuard(base_dir=root)
    _RUNTIME_ALLOWED_WRITE_ROOTS = _runtime_allowed_write_roots(root)
    _RUNTIME_SESSION_ID = str(session_id or "").strip()


def _set_runtime_session_id(session_id: str) -> None:
    global _RUNTIME_SESSION_ID
    _RUNTIME_SESSION_ID = str(session_id or "").strip()


def _clear_runtime_integrity() -> None:
    global _RUNTIME_WRITE_GUARD, _RUNTIME_ALLOWED_WRITE_ROOTS, _RUNTIME_SESSION_ID
    _RUNTIME_WRITE_GUARD = None
    _RUNTIME_ALLOWED_WRITE_ROOTS = ()
    _RUNTIME_SESSION_ID = ""


def _validate_runtime_write_path(path: str | Path) -> Path:
    if _RUNTIME_WRITE_GUARD is None:
        return Path(path)
    return _RUNTIME_WRITE_GUARD.validate_write_path(
        path,
        allowed_roots=_RUNTIME_ALLOWED_WRITE_ROOTS,
        session_id=_RUNTIME_SESSION_ID,
    )


@dataclass
class ParsedSynthesis:
    session_id: str
    claim: str
    evidence: List[str]
    counterarguments: List[str]
    uncertainties: List[str]
    final_synthesis: str
    raw_text: str


@dataclass(frozen=True)
class CycleRunPlan:
    """Resolved identity and output locations for one legacy cycle.

    Keeping this deterministic setup outside ``main`` makes the execution phase
    consume one validated object instead of rebuilding paths while it mutates
    runtime state.
    """

    topic: str
    session_id: str
    artifacts: Dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_cycle_run_plan(args: Any, root: Path, paths: Dict[str, Path]) -> CycleRunPlan:
    topic = str(args.topic or "").strip()
    if not topic:
        raw_topic = read_text(paths["topic_file"]).strip()
        raw_topic = TOPIC_OPEN_TAG_RE.sub("", raw_topic)
        topic = TOPIC_CLOSE_TAG_RE.sub("", raw_topic).strip()

    session_id = (
        validate_session_id(args.session_id)
        if str(args.session_id or "").strip()
        else generate_session_id(topic or "empty-topic")
    )
    artifacts: Dict[str, Any] = {
        "synthesis_path": str(paths["synthesis_path"]),
        "praxis_answer_path": str(paths["praxis_answer_path"]),
        "praxis_answer_session_path": str(
            root / "output" / "praxis" / f"{session_id}_praxis_answer.json"
        ),
        "sovereign_voice_path": str(paths["sovereign_voice_path"]),
        "sovereign_voice_session_path": str(
            root / "output" / "sovereign_voice" / f"{session_id}_sovereign_voice.md"
        ),
        "praxis_report_path": str(paths["praxis_report_path"]),
        "praxis_report_session_path": str(
            root / "output" / "praxis_reports" / f"{session_id}_praxis_report.md"
        ),
        "dialog_session_path": str(
            root / "output" / "dialog" / f"{session_id}_dialog.txt"
        ),
    }
    if args.safe_theorem_mode:
        artifacts["safe_theorem_manifest_path"] = str(
            Path(args.safe_theorem_manifest).expanduser().resolve()
        )
        artifacts["safe_theorem_mode"] = True
    artifacts.update(predict_artifact_integrity_paths(root, session_id))
    return CycleRunPlan(topic=topic, session_id=session_id, artifacts=artifacts)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return default


def load_required_json_object(path: Path, artifact_name: str) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{artifact_name} not found at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{artifact_name} is not valid JSON at {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"cannot read {artifact_name} at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{artifact_name} is not a JSON object at {path}")
    return payload


def resolve_clu_runtime_policy_path(root: Path) -> Path:
    return (root / CLU_RUNTIME_POLICY_RELATIVE_PATH).resolve()


def default_clu_runtime_policy() -> Dict[str, Any]:
    return {
        "clu_status": "DEPRECATED_AND_DISABLED",
        "default_enabled": False,
        "operator_override_required": True,
        "allow_automatic_invocation": False,
        "reason": "Phase 18.2 review found CLU mostly stubbed; disabled to prevent incomplete secondary autonomous system.",
    }


def load_clu_runtime_policy(root: Path, log_file: Path) -> Tuple[Dict[str, Any], str]:
    policy_path = resolve_clu_runtime_policy_path(root)
    policy = default_clu_runtime_policy()
    policy["policy_path"] = str(policy_path)

    if not policy_path.exists():
        log(f"CLU runtime policy missing at {policy_path}; fail-closed skip", log_file, "WARN")
        return policy, "missing"

    loaded = load_json(policy_path, None)
    if not isinstance(loaded, dict):
        log(f"CLU runtime policy invalid at {policy_path}; fail-closed skip", log_file, "WARN")
        return policy, "invalid"

    policy.update(loaded)
    policy["policy_path"] = str(policy_path)
    return policy, "loaded"


def clu_automatic_invocation_enabled(policy: Dict[str, Any]) -> bool:
    if policy.get("allow_automatic_invocation") is not True:
        return False
    if policy.get("default_enabled") is True:
        return True
    if policy.get("operator_override_required"):
        return bool(policy.get("operator_override_enabled"))
    return False


def skipped_clu_result(root: Path, policy: Dict[str, Any], policy_state: str) -> Dict[str, Any]:
    return {
        "executed": False,
        "ok": True,
        "status": "SKIPPED",
        "reason": CLU_DISABLED_REASON,
        "topic": "",
        "clu_status": policy.get("clu_status", "DEPRECATED_AND_DISABLED"),
        "policy_path": policy.get("policy_path") or str(resolve_clu_runtime_policy_path(root)),
        "policy_state": policy_state,
    }


def write_json_atomic(path: Path, data: Any) -> None:
    if _RUNTIME_WRITE_GUARD is not None:
        _RUNTIME_WRITE_GUARD.safe_write_json(
            path,
            data,
            allowed_roots=_RUNTIME_ALLOWED_WRITE_ROOTS,
            session_id=_RUNTIME_SESSION_ID,
        )
        return

    ensure_dir(path.parent)
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


def write_text_atomic(path: Path, content: str) -> None:
    if _RUNTIME_WRITE_GUARD is not None:
        _RUNTIME_WRITE_GUARD.safe_write_text(
            path,
            content,
            allowed_roots=_RUNTIME_ALLOWED_WRITE_ROOTS,
            session_id=_RUNTIME_SESSION_ID,
        )
        return

    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def append_text_atomic(path: Path, content: str) -> None:
    target = _validate_runtime_write_path(path)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(content)


def log(message: str, log_file: Path, level: str = "INFO") -> None:
    ensure_dir(log_file.parent)
    if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
        backup = Path(str(log_file) + ".1")
        if backup.exists():
            backup.unlink()
        os.replace(log_file, backup)
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}] [{MODULE_NAME}] [{level}] {message}"
    print(line, flush=True)
    append_text_atomic(log_file, line + "\n")


def defaults(root: Path) -> Dict[str, Path]:
    return {
        "broker_script": root / "broker_v21" / "broker.ps1",
        "topic_file": root / "broker_v21" / "inbox" / "topic.txt",
        "synthesis_path": root / "praxis" / "logs" / "synthesis.txt",
        "session_graph_path": root / "orchestra" / "session_graph.json",
        "runs_dir": root / "runs",
        "log_file": root / "logs" / "cycle_v3_log.txt",
        "system_log_path": root / "logs" / "system.txt",
        "praxis_answer_path": root / "output" / "praxis" / "praxis_answer.json",
        "sovereign_voice_path": root / "output" / "sovereign_voice" / "sovereign_voice.md",
        "praxis_report_path": root / "output" / "praxis_reports" / "praxis_report.md",
        "dialog_dir": root / "output" / "dialog",
        "constitution_state_path": root / "constitution" / "constitution_state.json",
        "clu_script": root / "clu" / "clu_loop.py",
        "praxis_commit_script": root / "praxis" / "praxis_commit.py",
        "praxis_commit_json": root / "praxis" / "commit.json",
        "praxis_done_txt": root / "praxis" / "commit_done.txt",
    }


def resolve_execution_paths(root: Path, broker_script_override: str = "", clu_script_override: str = "") -> Dict[str, Path]:
    paths = defaults(root)
    if broker_script_override.strip():
        paths["broker_script"] = Path(broker_script_override).expanduser().resolve()
    if clu_script_override.strip():
        paths["clu_script"] = Path(clu_script_override).expanduser().resolve()
    return paths


def load_safe_theorem_manifest(path_text: str, expected_runtime_root: Path) -> Dict[str, Any]:
    manifest_path_text = str(path_text or "").strip()
    if not manifest_path_text:
        raise ValueError("safe theorem mode requires --safe-theorem-manifest")
    manifest_path = Path(manifest_path_text).expanduser().resolve()
    manifest = load_required_json_object(manifest_path, "safe theorem manifest")
    # Imported here, not at module level: research/ is not a tracked part of this module, so the
    # top-level import made the whole runner unimportable in every checkout and install - not only
    # safe theorem mode, the one path that needs it. That path now fails with its actual cause.
    try:
        from research.scripts.theorem_safe_runtime import validate_safe_theorem_manifest
    except ImportError as exc:
        raise ValueError(
            "safe theorem mode requires research/scripts/theorem_safe_runtime.py, which this "
            f"installation does not include ({exc})") from exc
    errors = validate_safe_theorem_manifest(manifest, expected_runtime_root)
    if errors:
        raise ValueError("; ".join(errors))
    return manifest


def slugify(text: str, max_len: int = 24) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_len] if slug else "topic"


def generate_session_id(topic: str) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{slugify(topic)}_{uuid.uuid4().hex[:8]}"


def validate_session_id(value: str) -> str:
    """Return a filename-safe externally supplied run correlation ID."""
    session_id = str(value or "").strip()
    if not SESSION_ID_RE.fullmatch(session_id) or ".." in session_id:
        raise ValueError(
            "session id must be 1-96 filename-safe ASCII characters "
            "([A-Za-z0-9._-]), start with an alphanumeric character, and not contain '..'"
        )
    return session_id


def normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_section(text: str, names: List[str]) -> str:
    body = normalize_text(text)
    for name in names:
        match = re.search(SECTION_RE_TEMPLATE.format(name=re.escape(name)), body)
        if match:
            return normalize_text(match.group(1))
    return ""


def split_bullets(text: str) -> List[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []

    # F-125(i): "?" was the U+2022 bullet lost in an encoding round-trip, so real bullets were never
    # recognised and a line beginning "? " was stripped as one.
    bullet_pattern = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
    lines = cleaned.splitlines()

    if any(bullet_pattern.match(line) for line in lines):
        items: List[str] = []
        for raw_line in lines:
            line = bullet_pattern.sub("", raw_line).strip()
            if line:
                items.append(line)
        if items:
            return items

    if len(lines) > 1:
        items = [line.strip() for line in lines if line.strip()]
        if items:
            return items

    semicolon_items = [part.strip() for part in cleaned.split(";") if part.strip()]
    if len(semicolon_items) > 1:
        return semicolon_items

    paragraph = re.sub(r"\s+", " ", cleaned).strip()
    if not paragraph:
        return []

    sentence_parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', paragraph)
    abbreviations = ("e.g.", "i.e.", "etc.", "vs.", "U.S.", "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.")
    merged: List[str] = []
    for part in sentence_parts:
        item = part.strip()
        if not item:
            continue
        if merged and any(merged[-1].endswith(abbr) for abbr in abbreviations):
            merged[-1] = f"{merged[-1]} {item}"
        else:
            merged.append(item)

    meaningful = [item for item in merged if len(item.split()) >= 4]
    if len(meaningful) > 1:
        return meaningful
    return [paragraph]


def ensure_synthesis_tag(raw_text: str, session_id: str) -> str:
    if re.search(r"\[SYNTH\s+session_id=", raw_text, re.IGNORECASE):
        return raw_text
    return f"[SYNTH session_id={session_id}]\n{raw_text.strip()}\n[/SYNTH]\n"


def parse_synthesis(raw_text: str, expected_session_id: str) -> ParsedSynthesis:
    claim = extract_section(raw_text, ["CLAIM"])
    evidence = split_bullets(extract_section(raw_text, ["EVIDENCE"]))
    counterarguments = split_bullets(extract_section(raw_text, ["COUNTERARGUMENTS", "CHALLENGE"]))
    uncertainties = split_bullets(extract_section(raw_text, ["UNCERTAINTIES", "UNCERTAINTY"]))
    final_synthesis = extract_section(raw_text, ["FINAL_SYNTHESIS", "SYNTHESIS"]) or normalize_text(raw_text)
    return ParsedSynthesis(expected_session_id, claim, evidence, counterarguments, uncertainties, final_synthesis, raw_text)


def derive_metrics(parsed: ParsedSynthesis) -> Dict[str, float]:
    # NOTE: these are STRUCTURAL metrics derived purely from the shape of the response
    # (counts of evidence/counterargument/uncertainty bullets and the length of the final
    # synthesis). They measure FORM, not truth: `structural_completeness` and
    # `response_elaboration` say how fully-formed and elaborated the output is, NOT how
    # correct or well-supported it is. Do not read them as convergence-on-truth or
    # calibrated confidence. (Historically mislabeled "convergence"/"confidence".)
    evidence_count = len(parsed.evidence)
    counter_count = len(parsed.counterarguments)
    uncertainty_count = len(parsed.uncertainties)
    final_len = len(parsed.final_synthesis)
    structural_completeness = min(0.98, 0.42 + evidence_count * 0.12 + final_len / 1200.0 - uncertainty_count * 0.04)
    response_elaboration = min(0.96, 0.38 + evidence_count * 0.1 + final_len / 1500.0 - counter_count * 0.03 - uncertainty_count * 0.05)
    return {
        "structural_completeness": round(max(0.0, structural_completeness), 4),
        "response_elaboration": round(max(0.0, response_elaboration), 4),
    }


def determine_status(parsed: ParsedSynthesis) -> str:
    if not parsed.final_synthesis.strip():
        return "failed"
    if not (parsed.claim.strip() or parsed.evidence):
        return "failed"
    return "completed"


def init_session_graph() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "generated_at": utc_now_iso(), "sessions": []}


def load_or_init_session_graph(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return init_session_graph()
    data = load_required_json_object(path, "session graph")
    if not isinstance(data.get("sessions"), list):
        raise ValueError(f"session graph is missing sessions list: {path}")
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("generated_at", utc_now_iso())
    return data


def upsert_session(graph: Dict[str, Any], record: Dict[str, Any]) -> None:
    sessions = graph.setdefault("sessions", [])
    for index, item in enumerate(sessions):
        if item.get("session_id") == record["session_id"]:
            sessions[index] = record
            graph["generated_at"] = utc_now_iso()
            return
    sessions.append(record)
    graph["generated_at"] = utc_now_iso()


def load_canonical_answer(path: Path, session_id: str) -> Dict[str, Any]:
    answer = load_json(path, {})
    if not isinstance(answer, dict):
        return {}
    found_id = str(answer.get("session_id", "")).strip()
    if found_id != session_id:
        return {}
    return answer


def load_constitution_state(path: Path) -> Dict[str, Any]:
    state = load_json(path, None)
    if not isinstance(state, dict):
        raise ValueError(f"constitution_state.json is missing or malformed: {path}")
    schema_version = str(state.get("schema_version", "")).strip()
    if not schema_version:
        raise ValueError(f"constitution_state.json is missing schema_version: {path}")
    mode = str(state.get("mode", "")).strip().upper()
    if not mode:
        raise ValueError(f"constitution_state.json is missing mode: {path}")
    if mode not in VALID_MODES:
        raise ValueError(f"constitution_state.json has invalid mode '{mode}': {path}")
    state["mode"] = mode
    return state


_SYNTH_LOG_CACHE: Dict[Tuple[str, int, int], List[str]] = {}


def _synth_log_lines(system_log_path: Path) -> List[str]:
    """F-125(g): a run summarised the whole never-rotated system log three times. Reuse one read
    while the file's size and mtime are unchanged; any append invalidates it."""
    stat = system_log_path.stat()
    key = (str(system_log_path), int(stat.st_size), int(stat.st_mtime_ns))
    lines = _SYNTH_LOG_CACHE.get(key)
    if lines is None:
        _SYNTH_LOG_CACHE.clear()
        lines = system_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        _SYNTH_LOG_CACHE[key] = lines
    return lines


def load_synth_log_events(system_log_path: Path, session_id: str) -> List[Dict[str, Any]]:
    if not system_log_path.exists():
        return []
    events: List[Dict[str, Any]] = []
    for raw_line in _synth_log_lines(system_log_path):
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("source") != "synth_king":
            continue
        if payload.get("session_id") != session_id:
            continue
        if not isinstance(payload, dict):
            continue
        events.append(payload)
    return events


def summarize_synth_stage_events(system_log_path: Path, session_id: str) -> Dict[str, Any]:
    events = load_synth_log_events(system_log_path, session_id)
    attempts_by_key: Dict[Tuple[Any, Any, Any, Any, Any], List[Dict[str, Any]]] = {}
    transient_stage_failures: List[Dict[str, Any]] = []
    terminal_failure_event: Dict[str, Any] | None = None
    synth_completed = False

    for event in events:
        event_type = event.get("event")
        if event_type == "stage_attempt":
            key = (
                event.get("stage"),
                event.get("round_number"),
                event.get("wing_name"),
                event.get("role"),
                event.get("model"),
            )
            attempts_by_key.setdefault(key, []).append(event)
        elif event_type == "stage_terminal_failure":
            terminal_failure_event = event
        elif event_type == "synthesis_summary":
            synth_completed = True

    for attempt_events in attempts_by_key.values():
        recovered = any(bool(item.get("validation_passed")) for item in attempt_events)
        if not recovered:
            continue
        for item in attempt_events:
            if item.get("validation_passed"):
                continue
            transient_stage_failures.append(
                {
                    "stage": item.get("stage"),
                    "round_number": item.get("round_number"),
                    "wing_name": item.get("wing_name"),
                    "role": item.get("role"),
                    "model": item.get("model"),
                    "attempt": item.get("attempt"),
                    "failure_category": item.get("failure_category"),
                    "failure_reason": item.get("failure_reason"),
                    "missing_sections": item.get("missing_sections") or [],
                    "raw_output_preview": item.get("raw_output_preview"),
                    "raw_output_length": item.get("raw_output_length"),
                }
            )

    return {
        "synth_completed": synth_completed,
        "transient_stage_failures": transient_stage_failures,
        "terminal_failure_stage": terminal_failure_event.get("stage") if terminal_failure_event else None,
        "terminal_failure_reason": terminal_failure_event.get("failure_reason") if terminal_failure_event else None,
        "terminal_failure_category": terminal_failure_event.get("failure_category") if terminal_failure_event else None,
        "model_calls_observed": bool(events),
        "model_event_count": len(events),
    }


def enrich_run_record_with_synth_summary(run_record: Dict[str, Any], system_log_path: Path, session_id: str) -> Dict[str, Any]:
    run_record.update(summarize_synth_stage_events(system_log_path, session_id))
    return run_record


def _terminate_owned_tree(pid: int) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(pid, 15)
        except (ProcessLookupError, OSError):
            try:
                os.kill(pid, 15)
            except (ProcessLookupError, OSError):
                pass


def run_broker(
    root: Path,
    broker_script: Path,
    topic: str,
    topic_file: Path,
    session_id: str,
    timeout_sec: int,
    once: bool,
    stream_output: bool,
    *,
    safe_theorem_mode: bool = False,
    safe_theorem_manifest: Dict[str, Any] | None = None,
) -> Tuple[int, str, str]:
    payload = f"[TOPIC session_id={session_id}]\n{topic.strip()}\n[/TOPIC]\n"
    write_text_atomic(topic_file, payload)
    env = os.environ.copy()
    env["SOVEREIGN_SESSION_ID"] = session_id
    command = [
        _powershell_exe(),
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", str(broker_script),
        "-Root", str(root),
        # F-125(k): broker.ps1 defaulted -PythonExe to bare "python" from PATH, so the debate ran
        # under whatever interpreter PATH yielded rather than the one running this cycle.
        "-PythonExe", sys.executable,
    ]
    if safe_theorem_mode:
        manifest = dict(safe_theorem_manifest or {})
        live_orchestrator_path = str(((manifest.get("source_entrypoints") or {}).get("live_orchestrator", ""))).strip()
        safe_manifest_path = str(manifest.get("safe_theorem_manifest_path", "")).strip()
        if not live_orchestrator_path:
            raise ValueError("safe theorem manifest missing source_entrypoints.live_orchestrator")
        if not safe_manifest_path:
            raise ValueError("safe theorem manifest missing safe_theorem_manifest_path")
        command.extend(
            [
                "-LiveOrchestratorPath",
                live_orchestrator_path,
                "-SafeTheoremMode",
                "-SafeTheoremManifestPath",
                safe_manifest_path,
            ]
        )
    if once:
        command.append("-Once")
    kwargs: dict[str, Any] = {"env": env}
    if not stream_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    proc = subprocess.Popen(command, **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _terminate_owned_tree(int(proc.pid))
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
        raise
    return proc.returncode, stdout or "", stderr or ""


def invoke_clu(root: Path, clu_script: Path, session_id: str, topic: str, log_file: Path) -> Dict[str, Any]:
    policy, policy_state = load_clu_runtime_policy(root, log_file)
    if not clu_automatic_invocation_enabled(policy):
        log(f"CLU invocation skipped by policy at {policy.get('policy_path')}", log_file)
        clu_result = skipped_clu_result(root, policy, policy_state)
        clu_result["topic"] = topic
        return clu_result
    if not clu_script.exists():
        return {"ok": False, "error": f"missing {clu_script}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(clu_script), "--root", str(root), "--session-id", session_id, "--trigger", "post_cycle"],
            capture_output=True,
            text=True,
            timeout=150,
            cwd=str(root),
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            log(f"CLU loop failed exit={proc.returncode} stderr={stderr[:300]}", log_file, "WARN")
            return {"ok": False, "error": f"exit={proc.returncode}", "stderr": stderr[:400]}
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {"raw": stdout[:4000]}
        payload["ok"] = True
        payload["topic"] = topic
        return payload
    except IntegrityViolation:
        raise
    except Exception as exc:
        log(f"CLU loop exception: {exc}", log_file, "WARN")
        return {"ok": False, "error": str(exc)}


def load_dialog_artifact(root: Path, canonical_answer: Dict[str, Any], session_id: str) -> Tuple[str, str, str]:
    outputs = canonical_answer.get("outputs") if isinstance(canonical_answer.get("outputs"), dict) else {}
    candidate_paths: List[Tuple[str, Path]] = []
    for key in ("dialog_session_path", "dialog_path"):
        value = str(outputs.get(key, "")).strip() if isinstance(outputs, dict) else ""
        if value:
            origin = "session_dialog_artifact" if key == "dialog_session_path" else "shared_dialog_artifact"
            candidate_paths.append((origin, Path(value)))
    candidate_paths.append(("session_dialog_artifact", root / "output" / "dialog" / f"{session_id}_dialog.txt"))
    candidate_paths.append(("shared_dialog_artifact", root / "output" / "dialog" / "debate_dialog.txt"))

    for origin, candidate in candidate_paths:
        if candidate.exists():
            return read_text(candidate), str(candidate), origin
    raise FileNotFoundError(f"dialog artifact missing for session {session_id}")


def run_praxis_commit(
    root: Path,
    paths: Dict[str, Path],
    session_id: str,
    topic: str,
    synthesis: str,
    arbitration_artifact: Dict[str, Any],
    log_file: Path,
    *,
    safe_theorem_mode: bool = False,
) -> Dict[str, Any]:
    if safe_theorem_mode:
        raise RuntimeError("PRAXIS disabled in safe mode")
    commit_script = paths["praxis_commit_script"]
    if not commit_script.exists():
        log(f"WARN: praxis_commit.py not found at {commit_script}", log_file, "WARN")
        return {"executed": False, "ok": False, "reason": f"missing {commit_script}"}

    entries: List[Dict[str, Any]] = [
        {
            "type": "synthesis",
            "channel": "canonical",
            "content": synthesis,
        }
    ]
    if arbitration_artifact:
        entries.extend(build_praxis_entries(arbitration_artifact, str(paths["synthesis_path"])))

    payload = {
        "session_id": session_id,
        "topic": topic,
        "entries": entries,
    }
    write_json_atomic(paths["praxis_commit_json"], payload)
    if paths["praxis_done_txt"].exists():
        paths["praxis_done_txt"].unlink()

    try:
        proc = subprocess.run(
            [sys.executable, str(commit_script)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(root),
        )
    except subprocess.TimeoutExpired:
        log(f"ERROR: praxis_commit.py timed out for session={session_id}", log_file, "ERROR")
        return {"executed": True, "ok": False, "reason": "timeout", "entries": len(entries)}
    except OSError as exc:
        log(f"ERROR: cannot run praxis_commit.py: {exc}", log_file, "ERROR")
        return {"executed": True, "ok": False, "reason": str(exc), "entries": len(entries)}

    done_text = read_text(paths["praxis_done_txt"]).strip() if paths["praxis_done_txt"].exists() else ""
    ok = proc.returncode == 0 and done_text == "OK"
    if ok:
        log(f"PRAXIS commit OK for session={session_id}", log_file)
    else:
        log(f"WARN: praxis_commit failed exit={proc.returncode} done={done_text!r}", log_file, "WARN")
    return {
        "executed": True,
        "ok": ok,
        "entries": len(entries),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
        "done_path": str(paths["praxis_done_txt"]),
        "commit_json_path": str(paths["praxis_commit_json"]),
    }


def blank_parsed_synthesis(session_id: str) -> ParsedSynthesis:
    return ParsedSynthesis(session_id=session_id, claim="", evidence=[], counterarguments=[], uncertainties=[], final_synthesis="", raw_text="")


def zero_metrics() -> Dict[str, Any]:
    return {
        "structural_completeness": 0.0,
        "response_elaboration": 0.0,
        "arbitration_score": 0.0,
        "arbitration_score_strict": 0.0,
        "arbitration_score_soft": 0.0,
        "unresolved_conflict_count": 0,
        "contradiction_count": 0,
        "agreed_ratio": 0.0,
        "contradiction_density": 0.0,
        "coverage_factor": 0.0,
        "evidence_overlap": 0.0,
        "quality_gate_passed": False,
    }


def default_clu_result() -> Dict[str, Any]:
    return {"executed": False, "ok": False, "reason": "CLU not run"}


def default_praxis_commit_result(reason: str = "praxis commit not run") -> Dict[str, Any]:
    return {"executed": False, "ok": False, "reason": reason, "visible_failure": False}


def default_arbitration_result(session_id: str, topic: str, reason: str = "arbitration not run") -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "topic": topic,
        "analysis_status": "not_run",
        "executed": False,
        "artifact_path": "",
        "warnings": [],
        "metrics": {
            "arbitration_score": 0.0,
            "arbitration_score_strict": 0.0,
            "arbitration_score_soft": 0.0,
            "evidence_overlap": 0.0,
            "contradiction_count": 0,
            "agreed_ratio": 0.0,
            "contradiction_density": 0.0,
            "coverage_factor": 0.0,
            "unresolved_conflict_count": 0,
        },
        "failure_reason": normalize_failure_reason(reason),
        "model_turns": [],
    }


def default_quality_gate_result(
    session_id: str,
    topic: str,
    status: str,
    execution_mode: str,
    dialog_origin: str,
    failure_reason: str,
    arbitration_result: Dict[str, Any],
    model_calls_observed: bool = False,
    model_turns: List[Dict[str, Any]] | None = None,
    quality_gate_state: str = "not_run",
) -> Dict[str, Any]:
    normalized_reason = normalize_failure_reason(failure_reason) or "quality gate not run"
    return quality_gate.build_result(
        session_id=session_id,
        topic=topic,
        status=status,
        passed=False,
        reasons=[normalized_reason],
        warnings=[],
        arbitration_executed=bool(arbitration_result.get("executed")),
        arbitration_skipped_reason=normalized_reason,
        arbitration_artifact_path=str(arbitration_result.get("artifact_path", "")),
        arbitration_warnings=list(arbitration_result.get("warnings") or []),
        arbitration_metrics=dict(arbitration_result.get("metrics") or {}),
        arbitration_status=str(arbitration_result.get("analysis_status", "not_run")),
        arbitration_failure_reason=arbitration_result.get("failure_reason") or normalized_reason,
        convergence_value=0.0,
        confidence_value=0.0,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=model_calls_observed,
        execution_complete=False,
        failure_reason=normalized_reason,
        model_turns=model_turns or list(arbitration_result.get("model_turns") or []),
        quality_gate_state=quality_gate_state,
    )


def initial_execution_state() -> Dict[str, Dict[str, Any]]:
    return {
        "broker": build_stage_state("broker", "not_run", False, failure_reason="broker not started"),
        "synthesis": build_stage_state("synthesis", "not_run", False, failure_reason="synthesis not available"),
        "constitution": build_stage_state("constitution", "not_run", False, failure_reason="constitution mode not loaded"),
        "clu": build_stage_state("clu", "not_run", False, failure_reason="CLU not run"),
        "arbitration": build_stage_state("arbitration", "not_run", False, failure_reason="arbitration not run"),
        "quality_gate": build_stage_state("quality_gate", "not_run", False, failure_reason="quality gate not run"),
        "session_graph": build_stage_state("session_graph", "not_run", False, failure_reason="session graph not updated"),
        "praxis_commit": build_stage_state("praxis_commit", "not_run", False, failure_reason="praxis commit not run"),
    }


def join_failure_reasons(*reasons: Any) -> str | None:
    unique: List[str] = []
    for reason in reasons:
        normalized = normalize_failure_reason(reason)
        if normalized and normalized not in unique:
            unique.append(normalized)
    return "; ".join(unique) if unique else None


def predict_artifact_integrity_paths(root: Path, session_id: str) -> Dict[str, str]:
    scheduler_state = root / "scheduler" / "state"
    return {
        "artifact_integrity_summary_path": str(scheduler_state / "artifact_integrity_report.json"),
        "artifact_integrity_report_path": str(scheduler_state / "artifact_integrity" / f"{session_id}.json"),
    }


def _violation_types(violations: List[Dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    items: List[str] = []
    for violation in violations:
        violation_type = str(violation.get("violation_type", "")).strip()
        if not violation_type:
            continue
        key = violation_type.casefold()
        if key in seen:
            continue
        seen.add(key)
        items.append(violation_type)
    return items


def finalize_integrity_failure(
    *,
    root: Path,
    paths: Dict[str, Path],
    session_id: str,
    topic: str,
    started_at: str,
    execution_mode: str,
    dialog_origin: str,
    model_calls_observed: bool,
    model_turns: List[Dict[str, Any]],
    broker_exit_code: int | None,
    execution_state: Dict[str, Any],
    arbitration_result: Dict[str, Any],
    quality_gate_result: Dict[str, Any],
    praxis_commit_result: Dict[str, Any],
    clu_result: Dict[str, Any],
    artifacts: Dict[str, Any],
    stdout_text: str,
    stderr_text: str,
    stream_mode: bool,
    violation: IntegrityViolation,
) -> int:
    normalized_session_id = str(violation.session_id or session_id or "unknown").strip() or "unknown"
    violation_payload = violation.to_report()
    violation_payload.update(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "integrity_violation",
            "status": "invalid",
            "session_id": normalized_session_id,
            "topic": topic,
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "broker_exit_code": broker_exit_code,
            "execution_state": execution_state,
            "failure_reason": str(violation),
            "violation_count": len(violation.violations),
            "violation_types": _violation_types(violation.violations),
        }
    )
    runtime_dir = root / "output" / "live_runtime" / normalized_session_id
    output_path = runtime_dir / "integrity_violation.json"
    write_json_atomic(output_path, violation_payload)
    violation_payload["output_path"] = str(output_path)
    artifacts = dict(artifacts)
    artifacts["integrity_violation_report"] = str(output_path)

    run_path = paths["runs_dir"] / f"{normalized_session_id}.json"
    run_record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "run_record",
        "timestamp": utc_now_iso(),
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "session_id": normalized_session_id,
        "topic": topic,
        "status": "invalid",
        "run_valid": False,
        "broker_exit_code": broker_exit_code,
        "failure_reason": str(violation),
        "execution_state": execution_state,
        "clu": clu_result,
        "quality_gate": quality_gate_result,
        "arbitration": {
            "status": arbitration_result.get("analysis_status") or (quality_gate_result.get("arbitration") or {}).get("status"),
            "artifact_path": arbitration_result.get("artifact_path") or (quality_gate_result.get("arbitration") or {}).get("artifact_path"),
            "failure_reason": arbitration_result.get("failure_reason") or (quality_gate_result.get("arbitration") or {}).get("failure_reason"),
            "warnings": list(arbitration_result.get("warnings") or []),
        },
        "praxis_commit": praxis_commit_result,
        "integrity_violation": violation_payload,
        "artifacts": artifacts,
    }
    if not stream_mode:
        run_record["stdout_tail"] = stdout_text[-4000:]
        run_record["stderr_tail"] = stderr_text[-4000:]
    apply_provenance(
        run_record,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=model_calls_observed,
        execution_complete=False,
        failure_reason=str(violation),
        session_id=normalized_session_id,
        timestamp=run_record["timestamp"],
        model_turns=model_turns,
    )
    write_json_atomic(run_path, run_record)
    print(json.dumps(run_record, ensure_ascii=False, indent=2))
    return INTEGRITY_FAILURE_EXIT_CODE


def persist_pre_gate_artifacts(
    *,
    root: Path,
    session_id: str,
    topic: str,
    status: str,
    execution_mode: str,
    dialog_origin: str,
    failure_reason: str,
    model_calls_observed: bool,
    model_turns: List[Dict[str, Any]] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    normalized_reason = normalize_failure_reason(failure_reason) or "upstream failure before quality gate"
    existing_artifact_path = (root / "arbitration" / f"{session_id}.json").resolve()
    if existing_artifact_path.exists():
        try:
            arbitration_result = load_required_json_object(existing_artifact_path, "existing arbitration artifact")
        except (FileNotFoundError, OSError, ValueError) as exc:
            arbitration_result = default_arbitration_result(session_id, topic, normalized_reason)
            arbitration_result["analysis_status"] = "failed"
            arbitration_result["artifact_path"] = str(existing_artifact_path)
            arbitration_result["warnings"] = [normalized_reason, f"existing arbitration artifact unreadable: {exc}"]
        else:
            merged_warnings = list(arbitration_result.get("warnings") or [])
            if normalized_reason not in merged_warnings:
                merged_warnings.append(normalized_reason)
            arbitration_result["warnings"] = merged_warnings
            arbitration_result["artifact_path"] = str(existing_artifact_path)
            arbitration_result["failure_reason"] = arbitration_result.get("failure_reason") or normalized_reason
    else:
        arbitration_result = persist_arbitration_stub(
            root=root,
            session_id=session_id,
            topic=topic,
            source_path="",
            warnings=[normalized_reason],
            failure_reason=normalized_reason,
            analysis_status="skipped",
            execution_mode=execution_mode,
            dialog_origin=dialog_origin,
            model_calls_observed=model_calls_observed,
            model_turns=model_turns or [],
        )
    quality_gate_result = default_quality_gate_result(
        session_id,
        topic,
        status,
        execution_mode,
        dialog_origin,
        normalized_reason,
        arbitration_result,
        model_calls_observed=model_calls_observed,
        model_turns=model_turns or list(arbitration_result.get("model_turns") or []),
        quality_gate_state="not_run",
    )
    quality_gate_result = quality_gate.persist_result(root, quality_gate_result)
    return arbitration_result, quality_gate_result


def build_session_record(
    session_id: str,
    round_label: str,
    topic: str,
    parsed: ParsedSynthesis,
    metrics: Dict[str, Any],
    status: str,
    artifacts: Dict[str, Any],
    execution_mode: str,
    dialog_origin: str,
    model_calls_observed: bool,
    model_turns: List[Dict[str, Any]],
    execution_complete: bool,
    failure_reason: str | None,
    execution_state: Dict[str, Any],
    arbitration_result: Dict[str, Any],
    quality_gate_result: Dict[str, Any],
    praxis_commit_result: Dict[str, Any],
) -> Dict[str, Any]:
    record = {
        "artifact_type": "session_record",
        "session_id": session_id,
        "round_label": round_label,
        "topic": topic,
        "timestamp": utc_now_iso(),
        "status": status,
        "claim": parsed.claim,
        "evidence": parsed.evidence,
        "counterarguments": parsed.counterarguments,
        "uncertainties": parsed.uncertainties,
        "final_synthesis": parsed.final_synthesis,
        "metrics": metrics,
        "artifacts": artifacts,
        "execution_state": execution_state,
        "autonomy_mode": execution_mode,
        "failure_reason": normalize_failure_reason(failure_reason),
        "SOVEREIGN_version": SOVEREIGN_VERSION,
        "arbitration": {
            "status": arbitration_result.get("analysis_status") or quality_gate_result.get("arbitration", {}).get("status") or "not_run",
            "executed": bool(arbitration_result.get("executed")),
            "artifact_path": arbitration_result.get("artifact_path") or quality_gate_result.get("arbitration", {}).get("artifact_path"),
            "warnings": list(arbitration_result.get("warnings") or []),
            "failure_reason": arbitration_result.get("failure_reason") or quality_gate_result.get("arbitration", {}).get("failure_reason"),
        },
        "quality_gate": {
            "state": quality_gate_result.get("quality_gate_state"),
            "passed": bool(quality_gate_result.get("passed")),
            "arbitration_executed": bool(quality_gate_result.get("arbitration_executed")),
            "reasons": list(quality_gate_result.get("reasons") or []),
            "warnings": list(quality_gate_result.get("warnings") or []),
            "path": quality_gate_result.get("session_output_path") or quality_gate_result.get("output_path"),
            "failure_reason": quality_gate_result.get("failure_reason"),
        },
        "praxis_commit": praxis_commit_result,
    }
    apply_provenance(
        record,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=model_calls_observed,
        execution_complete=execution_complete,
        failure_reason=failure_reason,
        session_id=session_id,
        timestamp=record["timestamp"],
        model_turns=model_turns,
    )
    return record


# --------------------------------------------------------------------------
# Concurrence loop (PHASE2/concurrence/DESIGN.md v1.2; V5.0 standing approval 3).
# Flag-gated: runtime_profile.json concurrence_loop.enabled — absent/false means
# the runner byte-path is the stock single-pass behavior above/below this block.
# --------------------------------------------------------------------------

_CONCURRENCE_ADDRESSABLE_PATTERNS = (
    re.compile(r"^arbitration_score_strict .* < threshold"),
    re.compile(r"^unresolved_conflict_count .* > threshold"),
    re.compile(r"^convergence \d.* < threshold"),
    re.compile(r"^confidence \d.* < threshold"),
)
_CONCURRENCE_FLOOR_PATTERNS = {
    "gate_convergence_floor": re.compile(r"^convergence \d.* < threshold"),
    "gate_confidence_floor": re.compile(r"^confidence \d.* < threshold"),
}


def load_concurrence_config(root: Path) -> Dict[str, Any]:
    profile = load_json(root / "runtime_profile.json", {})
    config = profile.get("concurrence_loop") if isinstance(profile, dict) else None
    if not isinstance(config, dict):
        return {"enabled": False}
    return config


def concurrence_trigger(quality_gate_result: Dict[str, Any]) -> bool:
    """DESIGN S4 trigger: loop-addressable gate failure only. Upstream failures
    (broker timeout, empty synthesis, session mismatch) never reach this point;
    non-addressable gate reasons (invalid values, arbitration not executed) do not
    trigger."""
    if bool(quality_gate_result.get("passed")):
        return False
    reasons = [str(r) for r in quality_gate_result.get("reasons") or []]
    return any(pattern.match(reason) for reason in reasons for pattern in _CONCURRENCE_ADDRESSABLE_PATTERNS)


def _concurrence_floor_items(reasons: List[str], round_number: int) -> List[Dict[str, Any]]:
    """Confidence/convergence floor failures enter the ledger as items so their
    retries draw from the same global round budget (DESIGN S4: no per-gate budgets).
    CRITICAL because they block output; refreshed from each round's gate reasons."""
    items: List[Dict[str, Any]] = []
    for issue_id, pattern in _CONCURRENCE_FLOOR_PATTERNS.items():
        matched = [r for r in reasons if pattern.match(r)]
        if matched:
            items.append(
                {
                    "issue_id": issue_id,
                    "claim_id": issue_id,
                    "claim_text": "(quality-gate floor)",
                    "issue_type": "validation",
                    "issue_type_source": matched[0],
                    "disputed_evidence_ids": [],
                    "fingerprint": issue_id,
                    "issue": matched[0],
                    "raised_by": {"roles": ["QUALITY_GATE"], "precision": "gate_reason"},
                    "first_raised_round": round_number,
                    "parent_issue": None,
                    "severity": "CRITICAL",
                    "severity_reason": "gate_floor_unmet_fail_closed",
                    "status": "OPEN",
                    "evidence_needed": "a re-synthesis whose derived metrics clear the floor",
                    "resolution": None,
                }
            )
    return items


def _refresh_floor_items(ledger: Dict[str, Any], gate_result: Dict[str, Any], round_number: int) -> None:
    reasons = [str(r) for r in gate_result.get("reasons") or []]
    for item in ledger["items"]:
        if item.get("issue_type") != "validation" or item.get("status") != "OPEN":
            continue
        pattern = _CONCURRENCE_FLOOR_PATTERNS.get(item["issue_id"])
        if pattern is not None and not any(pattern.match(r) for r in reasons):
            item["status"] = "RESOLVED"
            item["resolution"] = f"floor cleared in round {round_number}"


def _parsed_to_answer(parsed: "ParsedSynthesis") -> Dict[str, Any]:
    return {
        "claim": parsed.claim,
        "evidence": list(parsed.evidence),
        "counterarguments": list(parsed.counterarguments),
        "uncertainties": list(parsed.uncertainties),
        "final_synthesis": parsed.final_synthesis,
    }


def _sections_to_parsed(sections: Dict[str, Any], session_id: str, raw_text: str) -> "ParsedSynthesis":
    return ParsedSynthesis(
        session_id=session_id,
        claim=str(sections["claim"]),
        evidence=list(sections["evidence"]),
        counterarguments=list(sections["counterarguments"]),
        uncertainties=list(sections["uncertainties"]),
        final_synthesis=str(sections["final_synthesis"]),
        raw_text=raw_text,
    )


def run_concurrence_rounds(
    *,
    root: Path,
    paths: Dict[str, Path],
    args: argparse.Namespace,
    log_file: Path,
    session_id: str,
    topic: str,
    stream_mode: bool,
    safe_theorem_manifest: Dict[str, Any],
    execution_mode: str,
    raw_synthesis: str,
    parsed: "ParsedSynthesis",
    metrics: Dict[str, Any],
    synthesis_status: str,
    quality_gate_result: Dict[str, Any],
    arbitration_result: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Bounded targeted re-round controller (DESIGN S4). Round 1 is the stock pass
    already completed by the caller; this runs rounds 2..max under round-scoped
    session ids ({parent}__r{n}), preserving every per-round artifact, and returns
    the accepted candidate + the concurrence run block. The global budget covers
    every re-synthesis path (arbitration re-round, floor retry) — no resets."""
    import concurrence_ledger as concurrence

    classifier = concurrence.load_classifier(root)
    max_rounds = int(config.get("max_rounds", 3))
    conc_dir = _validate_runtime_write_path(root / "output" / "concurrence" / session_id)
    ensure_dir(conc_dir)

    canonical_r1 = load_canonical_answer(paths["praxis_answer_path"], session_id)
    candidate = {
        "round": 1,
        "session_id": session_id,
        "raw_synthesis": raw_synthesis,
        "parsed": parsed,
        "metrics": dict(metrics),
        "synthesis_status": synthesis_status,
        "quality_gate_result": quality_gate_result,
        "arbitration_result": arbitration_result,
        "sections": concurrence.sections_of(canonical_r1 or _parsed_to_answer(parsed)),
    }

    claim_map = concurrence.derive_claim_map(
        arbitration_result, canonical_r1 or _parsed_to_answer(parsed), classifier, round_number=1
    )
    write_json_atomic(conc_dir / "claim_map_r1.json", claim_map)
    ledger = concurrence.new_ledger(session_id, classifier)
    opened_r1 = concurrence.merge_new_items(
        ledger, concurrence.items_from_artifact(arbitration_result, claim_map, classifier, 1)
    )
    gate_reasons_r1 = [str(r) for r in quality_gate_result.get("reasons") or []]
    opened_r1 += concurrence.merge_new_items(ledger, _concurrence_floor_items(gate_reasons_r1, 1))
    ledger["rounds"].append(
        {
            "round": 1,
            "session_id": session_id,
            "agenda_issue_ids": [],
            "arbitration": {
                "artifact_path": str(arbitration_result.get("artifact_path", "")),
                "metrics": dict((arbitration_result.get("metrics") or {})),
            },
            "quality_gate": {"passed": bool(quality_gate_result.get("passed")), "reasons": gate_reasons_r1},
            "items_opened": opened_r1,
            "items_closed": [],
            "wall_time_sec": None,
            "synthesis_mode": "full",
            "exit": None,
        }
    )
    ledger["rounds_used"] = 1

    exit_name: str | None = None
    exit_detail = ""
    while True:
        gate_passed = bool(candidate["quality_gate_result"].get("passed"))
        at_cap = ledger["rounds_used"] >= max_rounds
        exit_name, exit_detail = concurrence.evaluate_exit(ledger, gate_passed=gate_passed, at_cap=at_cap)
        if exit_name:
            break
        agenda_items = concurrence.open_critical_items(ledger) or concurrence.open_items(ledger)
        if not agenda_items:
            exit_name, exit_detail = "CONCURRENCE_NOT_REACHED", "gate failed with no addressable agenda (fail-closed: no agenda-less rounds)"
            break

        round_number = ledger["rounds_used"] + 1
        ledger["rounds_used"] = round_number  # budget drawn BEFORE the broker call (DESIGN S4)
        round_sid = f"{session_id}__r{round_number}"
        payload = concurrence.agenda_payload(agenda_items, round_number)
        write_json_atomic(conc_dir / f"agenda_r{round_number}.json", payload)
        round_topic = concurrence.agenda_topic_block(topic, payload)
        round_record: Dict[str, Any] = {
            "round": round_number,
            "session_id": round_sid,
            "agenda_issue_ids": payload["issue_ids"],
            "synthesis_mode": "patch",
            "exit": None,
        }
        log(
            f"CONCURRENCE round {round_number} starting | session={round_sid} agenda={len(agenda_items)} item(s)",
            log_file,
        )
        started = time.time()
        broker_failure = ""
        # Mapping S3.2: cognitive probes are advisory inside the loop; the orchestrator
        # honors this env var for the re-round only (round 1 / stock runs never set it).
        os.environ["SOVEREIGN_CONCURRENCE_ROUND"] = "1"
        try:
            code, _out, _err = run_broker(
                root,
                paths["broker_script"],
                round_topic,
                paths["topic_file"],
                round_sid,
                args.timeout_sec,
                args.once,
                stream_mode,
                safe_theorem_mode=args.safe_theorem_mode,
                safe_theorem_manifest=safe_theorem_manifest,
            )
            if code != 0:
                broker_failure = f"broker exited with code {code}"
        except IntegrityViolation:
            raise
        except subprocess.TimeoutExpired:
            broker_failure = f"broker timeout after {args.timeout_sec}s"
        except Exception as exc:  # noqa: BLE001 — round failure never crashes the cycle
            broker_failure = f"broker call failed: {exc}"
        finally:
            os.environ.pop("SOVEREIGN_CONCURRENCE_ROUND", None)

        round_raw = "" if broker_failure else normalize_text(read_text(paths["synthesis_path"]))
        if not broker_failure:
            if not round_raw:
                broker_failure = "synthesis output missing"
            elif f"session_id={round_sid}" not in round_raw:
                broker_failure = "synthesis session_id mismatch or stale content"
        if broker_failure:
            # round consumed; prior candidate stands (mapping S3.2: a failed round
            # destroys at most its own delta, never completed prior work)
            round_record.update(
                {
                    "failure_reason": broker_failure,
                    "quality_gate": {"passed": False, "reasons": [broker_failure]},
                    "items_opened": [],
                    "items_closed": [],
                    "wall_time_sec": round(time.time() - started, 1),
                }
            )
            ledger["rounds"].append(round_record)
            log(f"CONCURRENCE round {round_number} failed upstream: {broker_failure}", log_file, "WARN")
            continue

        round_raw = ensure_synthesis_tag(round_raw, round_sid)
        round_parsed = parse_synthesis(round_raw, round_sid)
        round_answer = load_canonical_answer(paths["praxis_answer_path"], round_sid)
        if round_answer:
            round_parsed = ParsedSynthesis(
                session_id=round_sid,
                claim=str(round_answer.get("claim", round_parsed.claim)).strip(),
                evidence=[str(i).strip() for i in round_answer.get("evidence", round_parsed.evidence) if str(i).strip()],
                counterarguments=[str(i).strip() for i in round_answer.get("counterarguments", round_parsed.counterarguments) if str(i).strip()],
                uncertainties=[str(i).strip() for i in round_answer.get("uncertainties", round_parsed.uncertainties) if str(i).strip()],
                final_synthesis=str(round_answer.get("final_synthesis", round_parsed.final_synthesis)).strip(),
                raw_text=round_raw,
            )
        round_metrics = (
            dict(round_answer.get("metrics")) if isinstance(round_answer.get("metrics"), dict) else derive_metrics(round_parsed)
        )
        # DESIGN S3 condition 3 on the re-round: structural variance (the calibrated
        # cognitive instrument, G-SV 0.90) is enforced here from the round's telemetry;
        # remaining cognitive probes are advisory and disclosed (mapping S3.2 — G-IS is
        # binary-degenerate per P2.1 and would structurally kill every targeted
        # re-round, whose entire purpose is answering challenges, not propagating them).
        cognitive_report = load_json(root / "output" / "live_runtime" / round_sid / "cognitive_validation_report.json", {})
        if isinstance(cognitive_report, dict) and cognitive_report:
            round_record["cognitive_validation_advisory"] = {
                "passed": bool(cognitive_report.get("passed")),
                "failures": [str(f) for f in cognitive_report.get("failures") or []],
            }
            sv_test = (cognitive_report.get("tests") or {}).get("structural_variance")
            if isinstance(sv_test, dict) and sv_test.get("passed") is False:
                round_record.update(
                    {
                        "failure_reason": "structural_variance failed in concurrence re-round (G-SV enforced by controller)",
                        "quality_gate": {"passed": False, "reasons": ["structural_variance failed in re-round"]},
                        "items_opened": [],
                        "items_closed": [],
                        "wall_time_sec": round(time.time() - started, 1),
                    }
                )
                ledger["rounds"].append(round_record)
                log(f"CONCURRENCE round {round_number} rejected: structural variance failed (G-SV)", log_file, "WARN")
                continue
        round_dir = conc_dir / f"round_r{round_number}"
        ensure_dir(round_dir)
        write_text_atomic(round_dir / "synthesis_raw.txt", round_raw)
        if round_answer:
            write_json_atomic(round_dir / "praxis_answer_raw.json", round_answer)

        permitted = concurrence.permitted_sections(payload["items"], classifier)
        assembled, patch_report = concurrence.assemble_patch(
            candidate["sections"], concurrence.sections_of(_parsed_to_answer(round_parsed)), permitted
        )
        assembled_text = concurrence.render_synthesis_text(assembled, round_sid)
        assembled_parsed = _sections_to_parsed(assembled, round_sid, assembled_text)
        assembled_status = determine_status(assembled_parsed)
        write_json_atomic(round_dir / "patch_report.json", patch_report)
        write_text_atomic(round_dir / "synthesis_assembled.txt", assembled_text)
        round_record["patch_report"] = patch_report

        dialog_text = ""
        dialog_path = ""
        round_dialog_origin = infer_dialog_origin()
        try:
            dialog_text, dialog_path, round_dialog_origin = load_dialog_artifact(root, round_answer or {}, round_sid)
        except FileNotFoundError as exc:
            log(f"WARN: concurrence round {round_number}: {exc}", log_file, "WARN")
        synth_summary = summarize_synth_stage_events(paths["system_log_path"], round_sid)
        round_calls = bool(synth_summary.get("model_calls_observed")) or bool(dialog_text.strip())

        round_gate = quality_gate.evaluate(
            synthesis=assembled_text,
            session_id=round_sid,
            confidence=round_metrics.get("response_elaboration", 0.0),
            root=str(root),
            dialog_text=dialog_text or None,
            topic=topic,
            convergence=round_metrics.get("structural_completeness"),
            status=assembled_status,
            dialog_source_path=dialog_path,
            execution_mode=execution_mode,
            dialog_origin=round_dialog_origin,
            model_calls_observed=round_calls,
            persist=True,
        )
        round_arb_path = str((round_gate.get("arbitration") or {}).get("artifact_path", "")).strip()
        round_arb: Dict[str, Any] = {}
        if round_arb_path:
            try:
                round_arb = load_required_json_object(Path(round_arb_path), "concurrence round arbitration artifact")
            except (FileNotFoundError, OSError, ValueError) as exc:
                log(f"WARN: concurrence round {round_number}: arbitration reload failed: {exc}", log_file, "WARN")

        claim_map = concurrence.derive_claim_map(round_arb, dict(assembled), classifier, round_number=round_number)
        write_json_atomic(conc_dir / f"claim_map_r{round_number}.json", claim_map)
        closed = concurrence.refresh_statuses(ledger, round_arb, claim_map, classifier, round_number)
        _refresh_floor_items(ledger, round_gate, round_number)
        opened = concurrence.merge_new_items(
            ledger, concurrence.items_from_artifact(round_arb, claim_map, classifier, round_number)
        )
        round_record.update(
            {
                "arbitration": {"artifact_path": round_arb_path, "metrics": dict(round_gate.get("metrics") or {})},
                "quality_gate": {
                    "passed": bool(round_gate.get("passed")),
                    "reasons": [str(r) for r in round_gate.get("reasons") or []],
                },
                "items_opened": opened,
                "items_closed": closed,
                "wall_time_sec": round(time.time() - started, 1),
            }
        )
        ledger["rounds"].append(round_record)
        log(
            f"CONCURRENCE round {round_number} complete | gate_passed={bool(round_gate.get('passed'))} "
            f"opened={len(opened)} closed={len(closed)}",
            log_file,
        )

        if bool(round_gate.get("passed")):
            round_arbitration_result = round_arb if round_arb else default_arbitration_result(round_sid, topic)
            round_arbitration_result.setdefault("artifact_path", round_arb_path)
            candidate = {
                "round": round_number,
                "session_id": round_sid,
                "raw_synthesis": assembled_text,
                "parsed": assembled_parsed,
                "metrics": dict(round_metrics),
                "synthesis_status": assembled_status,
                "quality_gate_result": round_gate,
                "arbitration_result": round_arbitration_result,
                "sections": assembled,
            }

    if ledger["rounds"]:
        ledger["rounds"][-1]["exit"] = exit_name
    ledger["exit"] = exit_name
    ledger_path = conc_dir / "ledger.json"
    write_json_atomic(ledger_path, ledger)
    if candidate["round"] > 1 and exit_name in ("FINALIZE", "FINALIZE_WITH_DISCLOSURE"):
        # accepted (patch-assembled) answer for downstream harnesses: the round's raw
        # praxis answer is NOT the accepted content once patch assembly ran. Never
        # written on CONCURRENCE_NOT_REACHED (nothing is accepted there).
        write_json_atomic(
            conc_dir / "accepted_answer.json",
            {
                "session_id": candidate["session_id"],
                "parent_session_id": session_id,
                "final_selected_round": candidate["round"],
                "topic": topic,
                "claim": candidate["sections"]["claim"],
                "evidence": list(candidate["sections"]["evidence"]),
                "counterarguments": list(candidate["sections"]["counterarguments"]),
                "uncertainties": list(candidate["sections"]["uncertainties"]),
                "final_synthesis": candidate["sections"]["final_synthesis"],
                "metrics": dict(candidate["metrics"]),
            },
        )
    snapshot_hash = concurrence.ledger_hash(ledger)
    log(
        f"CONCURRENCE_{exit_name} | session={session_id} rounds_used={ledger['rounds_used']} "
        f"detail={exit_detail} ledger_sha256={snapshot_hash}",
        log_file,
    )
    irreducible = [i for i in ledger["items"] if i["status"] == "IRREDUCIBLE"]
    block = {
        "enabled": True,
        "triggered": True,
        "exit": exit_name,
        "exit_detail": exit_detail,
        "rounds_used": ledger["rounds_used"],
        "max_rounds": max_rounds,
        # on CONCURRENCE_NOT_REACHED nothing is selected/emitted (DESIGN S4 exit 3);
        # the internal candidate is disclosed via unconcurred_* fields by the caller
        "final_selected_round": candidate["round"] if exit_name in ("FINALIZE", "FINALIZE_WITH_DISCLOSURE") else 1,
        "final_selected_session_id": candidate["session_id"] if exit_name in ("FINALIZE", "FINALIZE_WITH_DISCLOSURE") else session_id,
        "parent_session_id": session_id,
        "previous_round_session_ids": [r.get("session_id") for r in ledger["rounds"][:-1]],
        "agenda_issue_fingerprints": sorted({i["fingerprint"] for i in ledger["items"]}),
        "claim_map_version": classifier["version"],
        "ledger_path": str(ledger_path),
        "ledger_sha256": snapshot_hash,
        "irreducible_disclosure": [
            {"issue_id": i["issue_id"], "issue": i["issue"], "resolution": i["resolution"], "evidence_needed": i["evidence_needed"]}
            for i in irreducible
        ],
        "items_total": len(ledger["items"]),
        "items_by_status": {
            status: sum(1 for i in ledger["items"] if i["status"] == status)
            for status in ("OPEN", "RESOLVED", "WITHDRAWN", "IRREDUCIBLE")
        },
    }
    return {"candidate": candidate, "exit": exit_name, "block": block, "ledger": ledger}


def finalize_run(
    *,
    root: Path,
    paths: Dict[str, Path],
    session_id: str,
    topic: str,
    round_label: str,
    started_at: str,
    parsed: ParsedSynthesis,
    metrics: Dict[str, Any],
    status: str,
    execution_mode: str,
    dialog_origin: str,
    model_turns: List[Dict[str, Any]],
    model_calls_observed: bool,
    failure_reason: str | None,
    artifacts: Dict[str, Any],
    execution_state: Dict[str, Any],
    arbitration_result: Dict[str, Any],
    quality_gate_result: Dict[str, Any],
    praxis_commit_result: Dict[str, Any],
    broker_exit_code: int | None,
    stdout_text: str,
    stderr_text: str,
    stream_mode: bool,
    clu_result: Dict[str, Any],
    return_code: int,
    log_file: Path,
    concurrence_result: Dict[str, Any] | None = None,
) -> int:
    synth_summary = summarize_synth_stage_events(paths["system_log_path"], session_id)
    normalized_model_turns = [dict(item) for item in (model_turns or []) if isinstance(item, dict)]
    if not normalized_model_turns:
        normalized_model_turns = [dict(item) for item in quality_gate_result.get("model_turns", []) if isinstance(item, dict)]
    if not normalized_model_turns:
        normalized_model_turns = [dict(item) for item in arbitration_result.get("model_turns", []) if isinstance(item, dict)]
    observed_model_calls = bool(model_calls_observed or synth_summary.get("model_calls_observed") or normalized_model_turns)

    artifacts.update(predict_artifact_integrity_paths(root, session_id))
    ensure_dir(paths["runs_dir"])
    # One deterministic filename per engine session gives the durable product
    # service exact run-to-job correlation.  Caller-supplied session IDs are
    # validated before this function is reached.
    run_path = paths["runs_dir"] / f"{validate_session_id(session_id)}.json"
    artifacts["run_record_path"] = str(run_path)

    final_failure_reason = join_failure_reasons(
        failure_reason,
        quality_gate_result.get("failure_reason"),
        arbitration_result.get("failure_reason"),
        synth_summary.get("terminal_failure_reason"),
    )
    final_status = status
    execution_complete = final_status == "completed"

    execution_state["session_graph"] = build_stage_state(
        "session_graph",
        "updated",
        True,
        artifact_path=str(paths["session_graph_path"]),
    )
    session_record = build_session_record(
        session_id,
        round_label,
        topic,
        parsed,
        metrics,
        final_status,
        artifacts,
        execution_mode,
        dialog_origin,
        observed_model_calls,
        normalized_model_turns,
        execution_complete,
        final_failure_reason,
        execution_state,
        arbitration_result,
        quality_gate_result,
        praxis_commit_result,
    )

    try:
        graph = load_or_init_session_graph(paths["session_graph_path"])
        upsert_session(graph, session_record)
        write_json_atomic(paths["session_graph_path"], graph)
        log(f"session_graph updated: {paths['session_graph_path']}", log_file)
    except IntegrityViolation:
        raise
    except Exception as exc:
        graph_failure_reason = f"session graph update failed: {exc}"
        execution_state["session_graph"] = build_stage_state(
            "session_graph",
            "failed",
            True,
            failure_reason=graph_failure_reason,
            artifact_path=str(paths["session_graph_path"]),
        )
        final_failure_reason = join_failure_reasons(final_failure_reason, graph_failure_reason)
        final_status = "failed"
        execution_complete = False
        if return_code == 0:
            return_code = 9
        session_record = build_session_record(
            session_id,
            round_label,
            topic,
            parsed,
            metrics,
            final_status,
            artifacts,
            execution_mode,
            dialog_origin,
            observed_model_calls,
            normalized_model_turns,
            execution_complete,
            final_failure_reason,
            execution_state,
            arbitration_result,
            quality_gate_result,
            praxis_commit_result,
        )
        log(f"ERROR: {graph_failure_reason}", log_file, "ERROR")

    run_record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "run_record",
        "timestamp": utc_now_iso(),
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "session_id": session_id,
        "topic": topic,
        "status": final_status,
        "broker_exit_code": broker_exit_code,
        "metrics": metrics,
        "session_graph_path": str(paths["session_graph_path"]),
        "dialog_path": str(artifacts.get("dialog_session_path") or artifacts.get("dialog_path") or ""),
        "autonomy_mode": execution_mode,
        "execution_state": execution_state,
        "failure_reason": final_failure_reason,
        "clu": clu_result,
        "quality_gate": quality_gate_result,
        "arbitration": {
            "status": arbitration_result.get("analysis_status") or quality_gate_result.get("arbitration", {}).get("status"),
            "artifact_path": arbitration_result.get("artifact_path") or quality_gate_result.get("arbitration", {}).get("artifact_path"),
            "failure_reason": arbitration_result.get("failure_reason") or quality_gate_result.get("arbitration", {}).get("failure_reason"),
            "warnings": list(arbitration_result.get("warnings") or []),
        },
        "praxis_commit": praxis_commit_result,
        "artifacts": artifacts,
    }
    if concurrence_result is not None:
        run_record["concurrence"] = concurrence_result
    if not stream_mode:
        run_record["stdout_tail"] = stdout_text[-4000:]
        run_record["stderr_tail"] = stderr_text[-4000:]

    enrich_run_record_with_synth_summary(run_record, paths["system_log_path"], session_id)
    apply_provenance(
        run_record,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=observed_model_calls,
        execution_complete=execution_complete,
        failure_reason=final_failure_reason,
        session_id=session_id,
        timestamp=run_record["timestamp"],
        model_turns=normalized_model_turns,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "artifact_integrity_report",
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "session_id": session_id,
        "topic": topic,
        "status": final_status,
        "broker_exit_code": broker_exit_code,
        "execution_state": execution_state,
        "failure_reason": final_failure_reason,
        "arbitration_result": {
            "status": arbitration_result.get("analysis_status") or quality_gate_result.get("arbitration", {}).get("status"),
            "executed": bool(arbitration_result.get("executed")),
            "artifact_path": arbitration_result.get("artifact_path") or quality_gate_result.get("arbitration", {}).get("artifact_path"),
            "failure_reason": arbitration_result.get("failure_reason") or quality_gate_result.get("arbitration", {}).get("failure_reason"),
            "warnings": list(arbitration_result.get("warnings") or []),
            "metrics": dict(arbitration_result.get("metrics") or {}),
        },
        "quality_gate_result": {
            "state": quality_gate_result.get("quality_gate_state"),
            "passed": bool(quality_gate_result.get("passed")),
            "artifact_path": quality_gate_result.get("session_output_path") or quality_gate_result.get("output_path"),
            "failure_reason": quality_gate_result.get("failure_reason"),
            "reasons": list(quality_gate_result.get("reasons") or []),
            "warnings": list(quality_gate_result.get("warnings") or []),
        },
        "session_graph_update": execution_state["session_graph"],
        "artifacts": artifacts,
    }
    apply_provenance(
        report,
        execution_mode=execution_mode,
        dialog_origin=dialog_origin,
        model_calls_observed=observed_model_calls,
        execution_complete=execution_complete,
        failure_reason=final_failure_reason,
        session_id=session_id,
        timestamp=utc_now_iso(),
        model_turns=normalized_model_turns,
    )
    report = persist_artifact_integrity_report(root, session_id, report)
    run_record["artifact_integrity_report"] = {
        "output_path": report.get("output_path"),
        "session_output_path": report.get("session_output_path"),
    }

    write_json_atomic(run_path, run_record)
    log(f"=== cycle_runner_v3 complete | status={final_status} gate_passed={quality_gate_result.get('passed')} ===", log_file)
    print(json.dumps(run_record, ensure_ascii=False, indent=2))
    return return_code


def _resolve_root(cli_root: str | None) -> Path:
    """Resolve the SOVEREIGN root via the single authority (tools/sovereign_paths.py).
    Fails closed if no --root / SOVEREIGN_ROOT / .sovereign-root marker is found."""
    repo = Path(__file__).resolve().parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from tools.sovereign_paths import get_repo_root, configure_root
    return configure_root(cli_root) if cli_root else get_repo_root()


def _powershell_exe() -> str:
    """Locate a PowerShell executable: pwsh (cross-platform) then Windows PowerShell."""
    import shutil
    for name in ("pwsh", "powershell", "powershell.exe"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "No PowerShell executable found. Install PowerShell (pwsh) or Windows PowerShell "
        "and ensure it is on PATH."
    )


def _ollama_installed_models() -> set[str]:
    """Return the set of model tags reported by `ollama list`. Raises if the ollama
    executable is missing or the command fails (fail closed)."""
    import shutil
    exe = shutil.which("ollama")
    if not exe:
        raise RuntimeError("`ollama` executable not found on PATH — install Ollama and ensure it is running.")
    try:
        proc = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30)
    except Exception as exc:
        raise RuntimeError(f"could not run `ollama list`: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"`ollama list` failed (exit {proc.returncode}): {proc.stderr.strip()}")
    models: set[str] = set()
    for idx, line in enumerate(proc.stdout.splitlines()):
        if idx == 0 and line.upper().startswith("NAME"):
            continue  # header row
        parts = line.split()
        if parts:
            models.add(parts[0].strip())
    return models


def preflight_models(root: Path) -> tuple[bool, list[str], list[str]]:
    """Verify every model in SYSTEM_MANIFEST.json is present in `ollama list`.
    Returns (ok, required, missing). Fails closed on any error by re-raising."""
    from system_manifest import load_system_manifest
    data = load_system_manifest(root)
    required = sorted(set(str(v).strip() for v in data.get("MODELS", {}).values() if str(v).strip()))
    installed = _ollama_installed_models()
    missing = [m for m in required if m not in installed]
    return (len(missing) == 0, required, missing)


def run_preflight(root: Path, log_file: Path | None = None) -> int:
    """Run the model-roster preflight. Returns 0 on success, non-zero (fail closed) if
    any manifest model is missing or ollama is unreachable."""
    try:
        ok, required, missing = preflight_models(root)
    except Exception as exc:
        msg = f"PREFLIGHT FAILED: {exc}"
        print(msg, file=sys.stderr)
        if log_file is not None:
            log(msg, log_file, "ERROR")
        return 3
    if not ok:
        msg = ("PREFLIGHT FAILED: missing Ollama models required by SYSTEM_MANIFEST.json: "
               + ", ".join(missing)
               + f" | required={required}. Pull them (see PREREQUISITES.md) before running a cycle.")
        print(msg, file=sys.stderr)
        if log_file is not None:
            log(msg, log_file, "ERROR")
        return 4
    msg = f"PREFLIGHT OK: all {len(required)} manifest models present ({', '.join(required)})."
    print(msg)
    if log_file is not None:
        log(msg, log_file, "INFO")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOVEREIGN canonical cycle runner v3")
    parser.add_argument("--root", default=None,
                        help="SOVEREIGN root (default: auto-detect via .sovereign-root marker)")
    parser.add_argument("--check", action="store_true",
                        help="Run the model-roster preflight (verify SYSTEM_MANIFEST models are in `ollama list`) and exit.")
    parser.add_argument("--topic", default="")
    parser.add_argument(
        "--session-id",
        default="",
        help="Optional caller-supplied, filename-safe run correlation ID.",
    )
    parser.add_argument("--round-label", default="S1")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=2250)
    parser.add_argument("--fail-closed", action="store_true")
    # F-125(e): `--stream` was store_true with default=True, so it could never change anything.
    parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=True,
                        help="stream broker output (default); --no-stream captures it instead")
    parser.add_argument("--broker-script", default="")
    parser.add_argument("--clu-script", default="")
    parser.add_argument("--safe-theorem-mode", action="store_true")
    parser.add_argument("--safe-theorem-manifest", default="")
    return parser.parse_args()


_CYCLE_LOCK_HANDLE: Any = None
CONCURRENT_CYCLE_EXIT = 9


def acquire_cycle_lock(root: Path) -> Any:
    """F-125(b)/(h): at most ONE legacy cycle per root.

    Every cycle shares global IPC files (broker inbox topic.txt, praxis synthesis/commit files,
    praxis_answer.json), and IntegrityGuard treats another cycle's writes under evaluation/ as drift,
    so two concurrent cycles overwrote each other's topic or aborted each other. Per-session IPC
    would mean re-plumbing the broker, praxis and orchestrator of an unsupported pipeline; the
    bounded correction is to refuse the concurrency those files cannot survive. The OS lock is held
    by an open handle, so it is released when the process exits however it exits - no stale lock.
    Returns the handle, or None when another cycle holds the lock."""
    lock_path = root / "logs" / "cycle_runner_v3.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def create_stop(root: Path) -> None:
    stop_path = _RUNTIME_WRITE_GUARD.validate_write_path(root / "STOP", allowed_roots=[root], session_id=_RUNTIME_SESSION_ID) if _RUNTIME_WRITE_GUARD is not None else root / "STOP"
    praxis_root = root / "praxis"
    praxis_stop_path = _RUNTIME_WRITE_GUARD.validate_write_path(praxis_root / "STOP", allowed_roots=[praxis_root], session_id=_RUNTIME_SESSION_ID) if _RUNTIME_WRITE_GUARD is not None else praxis_root / "STOP"
    stop_path.touch()
    ensure_dir(praxis_root)
    praxis_stop_path.touch()


def main() -> int:
    args = parse_args()
    try:
        root = _resolve_root(args.root)
    except Exception as exc:
        print(f"ERROR: cannot resolve SOVEREIGN root: {exc}", file=sys.stderr)
        return 2
    args.root = str(root)
    paths = resolve_execution_paths(root, args.broker_script, args.clu_script)
    log_file = paths["log_file"]

    # --check: run the preflight only and exit.
    if getattr(args, "check", False):
        return run_preflight(root, log_file)

    # Startup preflight: fail closed before any cycle work if a manifest model is missing.
    preflight_rc = run_preflight(root, log_file)
    if preflight_rc != 0:
        return preflight_rc

    _configure_runtime_integrity(root)
    global _CYCLE_LOCK_HANDLE
    _CYCLE_LOCK_HANDLE = acquire_cycle_lock(root)
    if _CYCLE_LOCK_HANDLE is None:
        log("Another cycle_runner_v3 holds this root's cycle lock. Refusing to run concurrently.",
            log_file, "ERROR")
        ensure_dir(paths["runs_dir"])
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        record = {"status": "refused", "reason": "another cycle is running on this root",
                  "session_id": getattr(args, "session_id", "") or ""}
        write_text_atomic(paths["runs_dir"] / f"concurrent-refused-{stamp}.json", json.dumps(record, indent=2))
        return CONCURRENT_CYCLE_EXIT
    safe_theorem_manifest: Dict[str, Any] = {}

    session_id = ""
    topic = ""
    started_at = utc_now_iso()
    parsed = blank_parsed_synthesis("unknown")
    metrics = zero_metrics()
    artifacts: Dict[str, Any] = {}
    execution_state = initial_execution_state()
    execution_mode = "UNKNOWN"
    dialog_origin = infer_dialog_origin()
    model_turns: List[Dict[str, Any]] = []
    model_calls_observed = False
    failure_reason: str | None = None
    arbitration_result = default_arbitration_result("unknown", "")
    quality_gate_result = default_quality_gate_result(
        "unknown",
        "",
        "failed",
        execution_mode,
        dialog_origin,
        "quality gate not run",
        arbitration_result,
    )
    praxis_commit_result = default_praxis_commit_result()
    clu_result = default_clu_result()
    broker_exit_code: int | None = None
    stdout_text = ""
    stderr_text = ""
    stream_mode = bool(args.stream)

    try:
        if args.safe_theorem_mode:
            safe_theorem_manifest = load_safe_theorem_manifest(args.safe_theorem_manifest, root)
        log(f"=== cycle_runner_v3 starting | root={root} ===", log_file)

        if (root / "STOP").exists() or (root / "praxis" / "STOP").exists():
            log("STOP file present. Aborting.", log_file, "WARN")
            ensure_dir(paths["runs_dir"])
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            record = {
                "status": "aborted",
                "reason": "STOP file present",
                "session_id": getattr(args, "session_id", "") or "",
            }
            write_text_atomic(paths["runs_dir"] / f"stop-abort-{stamp}.json", json.dumps(record, indent=2))
            return 8

        ensure_dir(paths["runs_dir"])

        plan = build_cycle_run_plan(args, root, paths)
        topic = plan.topic
        session_id = plan.session_id
        _set_runtime_session_id(session_id)
        parsed = blank_parsed_synthesis(session_id)
        metrics = zero_metrics()
        artifacts = dict(plan.artifacts)

        execution_state = initial_execution_state()
        execution_mode = "UNKNOWN"
        dialog_origin = infer_dialog_origin()
        model_turns = []
        model_calls_observed = False
        failure_reason = None
        arbitration_result = default_arbitration_result(session_id, topic)
        quality_gate_result = default_quality_gate_result(
            session_id,
            topic,
            "failed",
            execution_mode,
            dialog_origin,
            "quality gate not run",
            arbitration_result,
        )
        praxis_commit_result = default_praxis_commit_result()
        clu_result = default_clu_result()
        broker_exit_code = None
        stdout_text = ""
        stderr_text = ""

        def finalize_upstream_failure(code: int, reason: str) -> int:
            nonlocal failure_reason, arbitration_result, quality_gate_result
            failure_reason = reason
            arbitration_result, quality_gate_result = persist_pre_gate_artifacts(
                root=root,
                session_id=session_id,
                topic=topic,
                status="failed",
                execution_mode=execution_mode,
                dialog_origin=dialog_origin,
                failure_reason=reason,
                model_calls_observed=model_calls_observed,
                model_turns=model_turns,
            )
            execution_state["arbitration"] = build_stage_state(
                "arbitration",
                "skipped",
                False,
                failure_reason=reason,
                artifact_path=arbitration_result.get("artifact_path"),
            )
            execution_state["quality_gate"] = build_stage_state(
                "quality_gate",
                "skipped",
                False,
                failure_reason=reason,
                artifact_path=quality_gate_result.get("session_output_path") or quality_gate_result.get("output_path"),
                details={"state": quality_gate_result.get("quality_gate_state")},
            )
            if arbitration_result.get("artifact_path"):
                artifacts["arbitration_path"] = str(arbitration_result["artifact_path"])
            if quality_gate_result.get("output_path"):
                artifacts["quality_gate_path"] = str(quality_gate_result["output_path"])
            if quality_gate_result.get("session_output_path"):
                artifacts["quality_gate_session_path"] = str(quality_gate_result["session_output_path"])
            if args.fail_closed:
                create_stop(root)
            return finalize_run(
                root=root,
                paths=paths,
                session_id=session_id,
                topic=topic,
                round_label=args.round_label,
                started_at=started_at,
                parsed=parsed,
                metrics=metrics,
                status="failed",
                execution_mode=execution_mode,
                dialog_origin=dialog_origin,
                model_turns=model_turns,
                model_calls_observed=model_calls_observed,
                failure_reason=reason,
                artifacts=artifacts,
                execution_state=execution_state,
                arbitration_result=arbitration_result,
                quality_gate_result=quality_gate_result,
                praxis_commit_result=praxis_commit_result,
                broker_exit_code=broker_exit_code,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                stream_mode=stream_mode,
                clu_result=clu_result,
                return_code=code,
                log_file=log_file,
            )

        if not topic:
            reason = "topic is empty - no --topic arg and topic file is empty"
            log(f"ERROR: {reason}", log_file, "ERROR")
            return finalize_upstream_failure(1, reason)

        try:
            broker_exit_code, stdout_text, stderr_text = run_broker(
                root,
                paths["broker_script"],
                topic,
                paths["topic_file"],
                session_id,
                args.timeout_sec,
                args.once,
                stream_mode,
                safe_theorem_mode=args.safe_theorem_mode,
                safe_theorem_manifest=safe_theorem_manifest,
            )
        except IntegrityViolation:
            raise
        except subprocess.TimeoutExpired:
            reason = f"broker timeout after {args.timeout_sec}s"
            log(f"ERROR: {reason}", log_file, "ERROR")
            execution_state["broker"] = build_stage_state("broker", "failed", True, failure_reason=reason)
            return finalize_upstream_failure(2, reason)
        except Exception as exc:
            reason = f"broker call failed: {exc}"
            log(f"ERROR: {reason}", log_file, "ERROR")
            execution_state["broker"] = build_stage_state("broker", "failed", True, failure_reason=reason)
            return finalize_upstream_failure(3, reason)

        execution_state["broker"] = build_stage_state(
            "broker",
            "completed",
            True,
            details={"exit_code": broker_exit_code},
        )

        if broker_exit_code != 0:
            error_message = f"broker exited with code {broker_exit_code}"
            detail_parts = []
            if not stream_mode and stderr_text.strip():
                detail_parts.append(f"stderr={stderr_text[-500:].strip()}")
            if not stream_mode and stdout_text.strip():
                detail_parts.append(f"stdout={stdout_text[-500:].strip()}")
            detail_text = " | ".join(detail_parts)
            log(f"ERROR: {error_message}{(' | ' + detail_text) if detail_text else ''}", log_file, "ERROR")
            execution_state["broker"] = build_stage_state(
                "broker",
                "failed",
                True,
                failure_reason=error_message,
                details={"exit_code": broker_exit_code},
            )
            return finalize_upstream_failure(4, error_message)

        raw_synthesis = normalize_text(read_text(paths["synthesis_path"]))
        if not raw_synthesis:
            reason = "synthesis output missing"
            log("ERROR: synthesis.txt empty after broker run", log_file, "ERROR")
            execution_state["synthesis"] = build_stage_state(
                "synthesis",
                "failed",
                True,
                failure_reason=reason,
                artifact_path=str(paths["synthesis_path"]),
            )
            return finalize_upstream_failure(5, reason)

        if f"session_id={session_id}" not in raw_synthesis:
            reason = "synthesis session_id mismatch or stale content"
            log("ERROR: synthesis.txt session_id mismatch or stale content after broker run", log_file, "ERROR")
            execution_state["synthesis"] = build_stage_state(
                "synthesis",
                "failed",
                True,
                failure_reason=reason,
                artifact_path=str(paths["synthesis_path"]),
            )
            return finalize_upstream_failure(6, reason)

        raw_synthesis = ensure_synthesis_tag(raw_synthesis, session_id)
        write_text_atomic(paths["synthesis_path"], raw_synthesis)
        parsed = parse_synthesis(raw_synthesis, session_id)

        canonical_answer = load_canonical_answer(paths["praxis_answer_path"], session_id)
        if canonical_answer:
            parsed = ParsedSynthesis(
                session_id=session_id,
                claim=str(canonical_answer.get("claim", parsed.claim)).strip(),
                evidence=[str(item).strip() for item in canonical_answer.get("evidence", parsed.evidence) if str(item).strip()],
                counterarguments=[str(item).strip() for item in canonical_answer.get("counterarguments", parsed.counterarguments) if str(item).strip()],
                uncertainties=[str(item).strip() for item in canonical_answer.get("uncertainties", parsed.uncertainties) if str(item).strip()],
                final_synthesis=str(canonical_answer.get("final_synthesis", parsed.final_synthesis)).strip(),
                raw_text=raw_synthesis,
            )

        metrics = dict(canonical_answer.get("metrics")) if isinstance(canonical_answer.get("metrics"), dict) else derive_metrics(parsed)
        synthesis_status = determine_status(parsed)
        execution_state["synthesis"] = build_stage_state(
            "synthesis",
            "completed" if synthesis_status == "completed" else "failed",
            True,
            failure_reason=None if synthesis_status == "completed" else "parsed synthesis is incomplete",
            artifact_path=str(paths["synthesis_path"]),
        )

        try:
            constitution_state = load_constitution_state(paths["constitution_state_path"])
        except ValueError as exc:
            reason = str(exc)
            log(f"ERROR: {reason}", log_file, "ERROR")
            execution_state["constitution"] = build_stage_state(
                "constitution",
                "failed",
                True,
                failure_reason=reason,
                artifact_path=str(paths["constitution_state_path"]),
            )
            return finalize_upstream_failure(7, reason)

        execution_mode = constitution_state["mode"]
        execution_state["constitution"] = build_stage_state(
            "constitution",
            "completed",
            True,
            artifact_path=str(paths["constitution_state_path"]),
            details={"mode": execution_mode},
        )

        try:
            clu_result = invoke_clu(root, paths["clu_script"], session_id, topic, log_file)
        except IntegrityViolation:
            raise
        except Exception as exc:
            reason = f"CLU invocation failed: {exc}"
            log(f"ERROR: {reason}", log_file, "ERROR")
            clu_result = {"executed": True, "ok": False, "reason": str(exc)}
            execution_state["clu"] = build_stage_state("clu", "failed", True, failure_reason=reason, artifact_path=str(paths["clu_script"]))
            return finalize_upstream_failure(7, reason)

        execution_state["clu"] = build_stage_state(
            "clu",
            "skipped" if clu_result.get("status") == "SKIPPED" else ("completed" if clu_result.get("ok", True) else "failed"),
            bool(clu_result.get("executed")),
            failure_reason=clu_result.get("reason") if clu_result.get("status") == "SKIPPED" else (None if clu_result.get("ok", True) else clu_result.get("reason")),
            artifact_path=clu_result.get("audit_path") or clu_result.get("policy_path") or str(paths["clu_script"]),
        )

        if isinstance(canonical_answer.get("outputs"), dict):
            artifacts.update(canonical_answer["outputs"])
        if clu_result.get("audit_path"):
            artifacts["clu_audit_path"] = clu_result["audit_path"]
        synthesis_audit = root / "ledger" / "constitution_audits" / f"{session_id}_synthesis_audit.json"
        if synthesis_audit.exists():
            artifacts["synthesis_audit_path"] = str(synthesis_audit)
        if safe_theorem_manifest:
            artifacts["safe_theorem_runtime_root"] = str(root)

        dialog_text = ""
        dialog_path = str(artifacts.get("dialog_session_path") or artifacts.get("dialog_path") or "")
        try:
            dialog_text, dialog_path, dialog_origin = load_dialog_artifact(root, canonical_answer, session_id)
            artifacts["dialog_path"] = str(artifacts.get("dialog_path") or dialog_path)
            artifacts["dialog_session_path"] = str(artifacts.get("dialog_session_path") or dialog_path)
        except FileNotFoundError as exc:
            dialog_origin = infer_dialog_origin(dialog_source_path=dialog_path)
            log(f"WARN: {exc}", log_file, "WARN")

        synth_summary = summarize_synth_stage_events(paths["system_log_path"], session_id)
        model_calls_observed = bool(synth_summary.get("model_calls_observed")) or bool(dialog_text.strip())

        quality_gate_result = quality_gate.evaluate(
            synthesis=raw_synthesis,
            session_id=session_id,
            confidence=metrics.get("response_elaboration", 0.0),
            root=str(root),
            dialog_text=dialog_text or None,
            topic=topic,
            convergence=metrics.get("structural_completeness"),
            status=synthesis_status,
            dialog_source_path=dialog_path,
            execution_mode=execution_mode,
            dialog_origin=dialog_origin,
            model_calls_observed=model_calls_observed,
            persist=True,
        )
        if quality_gate_result.get("output_path"):
            artifacts["quality_gate_path"] = str(quality_gate_result["output_path"])
        if quality_gate_result.get("session_output_path"):
            artifacts["quality_gate_session_path"] = str(quality_gate_result["session_output_path"])
        execution_state["quality_gate"] = build_stage_state(
            "quality_gate",
            "passed" if quality_gate_result.get("passed") else "failed",
            True,
            failure_reason=quality_gate_result.get("failure_reason"),
            artifact_path=quality_gate_result.get("session_output_path") or quality_gate_result.get("output_path"),
            details={"state": quality_gate_result.get("quality_gate_state")},
        )

        metrics.update(quality_gate_result.get("metrics") or {})
        metrics["quality_gate_passed"] = bool(quality_gate_result.get("passed"))

        arbitration_path = str((quality_gate_result.get("arbitration") or {}).get("artifact_path", "")).strip()
        arbitration_reload_error = ""
        if arbitration_path:
            artifacts["arbitration_path"] = arbitration_path
            try:
                arbitration_result = load_required_json_object(Path(arbitration_path), "arbitration artifact")
            except (FileNotFoundError, OSError, ValueError) as exc:
                arbitration_reload_error = str(exc)
                quality_gate_result["warnings"] = list(quality_gate_result.get("warnings") or []) + ["arbitration artifact reload failed after gate evaluation"]
                quality_gate_result["reasons"] = list(quality_gate_result.get("reasons") or []) + [arbitration_reload_error]
                quality_gate_result["failure_reason"] = join_failure_reasons(quality_gate_result.get("failure_reason"), arbitration_reload_error)
                arbitration_result = default_arbitration_result(session_id, topic, arbitration_reload_error)
                arbitration_result["analysis_status"] = "failed"
                arbitration_result["artifact_path"] = arbitration_path
                arbitration_result["warnings"] = list(quality_gate_result.get("warnings") or [])
                arbitration_result["model_turns"] = list(quality_gate_result.get("model_turns") or [])
                log(f"ERROR: {arbitration_reload_error}", log_file, "ERROR")
        else:
            arbitration_result = default_arbitration_result(
                session_id,
                topic,
                (quality_gate_result.get("arbitration") or {}).get("failure_reason") or "arbitration artifact missing",
            )

        contract_report = enforce_contract(arbitration_result, guard=_RUNTIME_WRITE_GUARD)
        trace_contract_status_from_mapping(
            base_dir=root,
            session_id=session_id,
            checkpoint="CONTRACT_RETURNED",
            container=contract_report,
            container_name="contract_report",
            source_file=Path(__file__),
            guard=_RUNTIME_WRITE_GUARD,
        )
        quality_gate_result["contract"] = contract_report
        arbitration_result["contract_status"] = contract_report.get("contract_status")
        arbitration_result["contract_message"] = contract_report.get("contract_message")
        arbitration_result["contract_violations"] = list(contract_report.get("contract_violations") or [])
        trace_contract_status_from_mapping(
            base_dir=root,
            session_id=session_id,
            checkpoint="CONTRACT_ATTACHED",
            container=quality_gate_result.get("contract") if isinstance(quality_gate_result.get("contract"), dict) else None,
            container_name="quality_gate_result.contract",
            source_file=Path(__file__),
            guard=_RUNTIME_WRITE_GUARD,
        )

        model_turns = [dict(item) for item in arbitration_result.get("model_turns", []) if isinstance(item, dict)]
        if not model_turns:
            model_turns = [dict(item) for item in quality_gate_result.get("model_turns", []) if isinstance(item, dict)]
        model_calls_observed = bool(model_calls_observed or model_turns)

        execution_state["arbitration"] = build_stage_state(
            "arbitration",
            arbitration_result.get("analysis_status") or (quality_gate_result.get("arbitration") or {}).get("status") or "not_run",
            bool(arbitration_result.get("executed")),
            failure_reason=arbitration_result.get("failure_reason") or (quality_gate_result.get("arbitration") or {}).get("failure_reason"),
            artifact_path=arbitration_path or arbitration_result.get("artifact_path"),
        )

        # Concurrence loop (flag-gated; stock single-pass behavior when disabled)
        concurrence_config = load_concurrence_config(root)
        concurrence_run: Dict[str, Any] | None = None
        concurrence_exit: str | None = None
        if bool(concurrence_config.get("enabled")):
            concurrence_run = {"enabled": True, "triggered": False}
            if not args.safe_theorem_mode and concurrence_trigger(quality_gate_result):
                try:
                    concurrence_outcome = run_concurrence_rounds(
                        root=root,
                        paths=paths,
                        args=args,
                        log_file=log_file,
                        session_id=session_id,
                        topic=topic,
                        stream_mode=stream_mode,
                        safe_theorem_manifest=safe_theorem_manifest,
                        execution_mode=execution_mode,
                        raw_synthesis=raw_synthesis,
                        parsed=parsed,
                        metrics=metrics,
                        synthesis_status=synthesis_status,
                        quality_gate_result=quality_gate_result,
                        arbitration_result=arbitration_result,
                        config=concurrence_config,
                    )
                except IntegrityViolation:
                    raise
                except Exception as exc:  # noqa: BLE001 — controller failure falls back to stock outcome
                    log(f"ERROR: concurrence controller failed: {exc}", log_file, "ERROR")
                    concurrence_run = {"enabled": True, "triggered": True, "controller_error": str(exc)}
                else:
                    concurrence_run = concurrence_outcome["block"]
                    concurrence_exit = concurrence_outcome["exit"]
                    candidate = concurrence_outcome["candidate"]
                    if concurrence_exit == "CONCURRENCE_NOT_REACHED" and candidate["round"] > 1:
                        # DESIGN S4 exit 3: a later round's gate passed but critical
                        # items remained open at the cap — no silent acceptance. The
                        # round-1 (failed) results stay canonical; the unconcurred
                        # passing round is disclosed, never emitted.
                        concurrence_run["unconcurred_round_gate_passed"] = True
                        concurrence_run["unconcurred_round"] = candidate["round"]
                        log(
                            f"CONCURRENCE exit 3 with gate-passing round {candidate['round']} — output withheld (no silent acceptance)",
                            log_file,
                            "WARN",
                        )
                    elif candidate["round"] > 1:
                        raw_synthesis = candidate["raw_synthesis"]
                        parsed = candidate["parsed"]
                        synthesis_status = candidate["synthesis_status"]
                        quality_gate_result = candidate["quality_gate_result"]
                        arbitration_result = candidate["arbitration_result"]
                        write_text_atomic(paths["synthesis_path"], raw_synthesis)
                        metrics = dict(candidate["metrics"])
                        metrics.update(quality_gate_result.get("metrics") or {})
                        metrics["quality_gate_passed"] = bool(quality_gate_result.get("passed"))
                        arbitration_path = str(arbitration_result.get("artifact_path", "")).strip()
                        if arbitration_path:
                            artifacts["arbitration_path"] = arbitration_path
                        if quality_gate_result.get("output_path"):
                            artifacts["quality_gate_path"] = str(quality_gate_result["output_path"])
                        if quality_gate_result.get("session_output_path"):
                            artifacts["quality_gate_session_path"] = str(quality_gate_result["session_output_path"])
                        contract_report = enforce_contract(arbitration_result, guard=_RUNTIME_WRITE_GUARD)
                        quality_gate_result["contract"] = contract_report
                        arbitration_result["contract_status"] = contract_report.get("contract_status")
                        arbitration_result["contract_message"] = contract_report.get("contract_message")
                        arbitration_result["contract_violations"] = list(contract_report.get("contract_violations") or [])
                        adopted_turns = [dict(item) for item in arbitration_result.get("model_turns", []) if isinstance(item, dict)]
                        if adopted_turns:
                            model_turns = adopted_turns
                        model_calls_observed = bool(model_calls_observed or model_turns)
                        execution_state["quality_gate"] = build_stage_state(
                            "quality_gate",
                            "passed" if quality_gate_result.get("passed") else "failed",
                            True,
                            failure_reason=quality_gate_result.get("failure_reason"),
                            artifact_path=quality_gate_result.get("session_output_path") or quality_gate_result.get("output_path"),
                            details={"state": quality_gate_result.get("quality_gate_state"), "concurrence_round": candidate["round"]},
                        )
                        execution_state["arbitration"] = build_stage_state(
                            "arbitration",
                            arbitration_result.get("analysis_status") or "completed",
                            bool(arbitration_result.get("executed")),
                            failure_reason=arbitration_result.get("failure_reason"),
                            artifact_path=arbitration_path or arbitration_result.get("artifact_path"),
                        )
                    artifacts["concurrence_ledger_path"] = str(concurrence_run.get("ledger_path", ""))

        memory_allowed = bool(canonical_answer.get("memory_allowed", True))
        if execution_mode == "OBSERVE":
            reason = "constitution mode OBSERVE blocks all PRAXIS commits"
            log(f"INFO: {reason} for session={session_id}", log_file, "INFO")
            praxis_commit_result = {
                "executed": False,
                "ok": True,
                "reason": reason,
                "blocked_by_mode": execution_mode,
                "constitution_state_path": str(paths["constitution_state_path"]),
                "visible_failure": False,
            }
            execution_state["praxis_commit"] = build_stage_state("praxis_commit", "blocked", False, failure_reason=reason)
        elif bool(quality_gate_result.get("passed")) and arbitration_path and arbitration_reload_error:
            reason = "arbitration artifact reload failed; PRAXIS commit aborted"
            log(f"ERROR: {reason} for session={session_id}", log_file, "ERROR")
            praxis_commit_result = {
                "executed": False,
                "ok": False,
                "reason": reason,
                "error": arbitration_reload_error,
                "artifact_path": arbitration_path,
                "visible_failure": True,
            }
            execution_state["praxis_commit"] = build_stage_state("praxis_commit", "failed", False, failure_reason=reason, artifact_path=arbitration_path)
        elif args.safe_theorem_mode:
            reason = "safe theorem mode disables PRAXIS commits"
            praxis_commit_result = {
                "executed": False,
                "ok": True,
                "reason": reason,
                "safe_theorem_mode": True,
                "safe_theorem_manifest_path": str(Path(args.safe_theorem_manifest).expanduser().resolve()),
                "visible_failure": False,
            }
            execution_state["praxis_commit"] = build_stage_state(
                "praxis_commit",
                "blocked",
                False,
                failure_reason=reason,
                artifact_path=str(Path(args.safe_theorem_manifest).expanduser().resolve()),
            )
        elif bool(quality_gate_result.get("passed")) and memory_allowed:
            praxis_commit_result = run_praxis_commit(
                root,
                paths,
                session_id,
                topic,
                raw_synthesis,
                arbitration_result,
                log_file,
                safe_theorem_mode=args.safe_theorem_mode,
            )
            execution_state["praxis_commit"] = build_stage_state(
                "praxis_commit",
                "completed" if praxis_commit_result.get("ok") else "failed",
                bool(praxis_commit_result.get("executed")),
                failure_reason=None if praxis_commit_result.get("ok") else praxis_commit_result.get("reason"),
                artifact_path=praxis_commit_result.get("commit_json_path"),
            )
        elif not memory_allowed:
            reason = "canonical answer marked non-memory"
            praxis_commit_result = {"executed": False, "ok": False, "reason": reason, "visible_failure": False}
            execution_state["praxis_commit"] = build_stage_state("praxis_commit", "skipped", False, failure_reason=reason)
        else:
            reason = "quality gate did not pass"
            praxis_commit_result = {"executed": False, "ok": False, "reason": reason, "visible_failure": False}
            execution_state["praxis_commit"] = build_stage_state("praxis_commit", "skipped", False, failure_reason=reason)

        fatal_post_gate_error = bool(praxis_commit_result.get("visible_failure"))
        if synthesis_status != "completed":
            final_status = "failed"
            failure_reason = join_failure_reasons("parsed synthesis is incomplete", quality_gate_result.get("failure_reason"))
        elif bool(quality_gate_result.get("passed")) and not fatal_post_gate_error:
            final_status = "completed"
            failure_reason = None
        elif bool(quality_gate_result.get("passed")) and fatal_post_gate_error:
            final_status = "failed"
            failure_reason = join_failure_reasons(praxis_commit_result.get("reason"), arbitration_reload_error)
        else:
            # DESIGN S4 exit 3: structured failure distinct from stock 'rejected'
            final_status = "concurrence_not_reached" if concurrence_exit == "CONCURRENCE_NOT_REACHED" else "rejected"
            failure_reason = quality_gate_result.get("failure_reason")

        if args.fail_closed and final_status != "completed":
            create_stop(root)

        return finalize_run(
            root=root,
            paths=paths,
            session_id=session_id,
            topic=topic,
            round_label=args.round_label,
            started_at=started_at,
            parsed=parsed,
            metrics=metrics,
            status=final_status,
            execution_mode=execution_mode,
            dialog_origin=dialog_origin,
            model_turns=model_turns,
            model_calls_observed=model_calls_observed,
            failure_reason=failure_reason,
            concurrence_result=concurrence_run,
            artifacts=artifacts,
            execution_state=execution_state,
            arbitration_result=arbitration_result,
            quality_gate_result=quality_gate_result,
            praxis_commit_result=praxis_commit_result,
            broker_exit_code=broker_exit_code,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            stream_mode=stream_mode,
            clu_result=clu_result,
            return_code=0 if final_status == "completed" else 8,
            log_file=log_file,
        )
    except IntegrityViolation as exc:
        normalized_session_id = str(exc.session_id or session_id or "unknown").strip() or "unknown"
        _set_runtime_session_id(normalized_session_id)
        structured_failure = {
            "event": "integrity_violation_abort",
            "session_id": normalized_session_id,
            "state_drifted": bool(exc.state_drifted),
            "violation_count": len(exc.violations),
            "violation_types": _violation_types(exc.violations),
            "message": str(exc),
        }
        try:
            log(json.dumps(structured_failure, ensure_ascii=False, sort_keys=True), log_file, "ERROR")
        except IntegrityViolation:
            print(json.dumps(structured_failure, ensure_ascii=False, sort_keys=True), flush=True)
        if args.fail_closed:
            create_stop(root)
        return finalize_integrity_failure(
            root=root,
            paths=paths,
            session_id=normalized_session_id,
            topic=topic,
            started_at=started_at,
            execution_mode=execution_mode,
            dialog_origin=dialog_origin,
            model_calls_observed=model_calls_observed,
            model_turns=model_turns,
            broker_exit_code=broker_exit_code,
            execution_state=execution_state,
            arbitration_result=arbitration_result,
            quality_gate_result=quality_gate_result,
            praxis_commit_result=praxis_commit_result,
            clu_result=clu_result,
            artifacts=artifacts,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            stream_mode=stream_mode,
            violation=exc,
        )
    finally:
        _clear_runtime_integrity()


if __name__ == "__main__":
    raise SystemExit(main())
