from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable


TOPIC_FILES = {
    "Sovereign System Overview": "sovereign-system-overview",
    "Master Library": "master-library",
    "Ecological Memory": "ecological-memory",
    "Route Policy Registry": "route-policy-registry",
    "Archive Simulation": "archive-simulation",
    "PRAXIS Retrieval": "praxis-retrieval",
    "Open Brain": "open-brain",
    "Knowledge Base Authority Model": "knowledge-base-authority-model",
}

TOPIC_KEYWORDS = {
    "Sovereign System Overview": ["SOVEREIGN", "system", "runtime", "URI", "library", "ecology"],
    "Master Library": ["library", "artifact", "ontology", "truth", "registry"],
    "Ecological Memory": ["ecology", "memory", "retrieval", "abstraction", "semantic"],
    "Route Policy Registry": ["route", "policy", "URI", "endpoint", "read_only"],
    "Archive Simulation": ["archive", "simulation", "cold", "restore", "replay"],
    "PRAXIS Retrieval": ["PRAXIS", "retrieval", "praxis_answer", "query"],
    "Open Brain": ["open brain", "proposal", "gap", "question", "hypothesis"],
    "Knowledge Base Authority Model": ["authority", "database", "wiki", "canonical", "knowledge"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_stamp() -> str:
    return utc_now().replace("-", "").replace(":", "")


def detect_repo_root(start: str | Path | None = None) -> Path:
    target = Path(start).resolve() if start else Path(__file__).resolve()
    for candidate in [target, *target.parents]:
        if candidate.is_dir() and (candidate / ".sovereign-root").exists():
            return candidate
    for candidate in [target, *target.parents]:
        if candidate.name.upper() == "SOVEREIGN":
            return candidate
    raise RuntimeError(f"Could not locate SOVEREIGN repo root from {target}")


def kb_root(root: str | Path | None = None) -> Path:
    return detect_repo_root(root) / "knowledge_base"


def read_text(path: str | Path, default: str = "") -> str:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return target.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return default


def read_json(path: str | Path, default: Any = None) -> Any:
    text = read_text(path, default="")
    if not text.strip():
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def read_jsonl(path: str | Path) -> list[Any]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[Any] = []
    try:
        for raw_line in target.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    target.write_text(rendered, encoding="utf-8")


def append_jsonl(path: str | Path, row: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if content and not content.endswith("\n"):
        content = content + "\n"
    target.write_text(content, encoding="utf-8")


def backup_file(path: str | Path, *, stamp: str | None = None, suffix: str | None = None) -> Path | None:
    target = Path(path)
    if not target.exists():
        return None
    stamp_value = stamp or utc_stamp()
    extra = suffix or f".bak_{stamp_value}"
    destination = target.with_name(target.name + extra)
    shutil.copy2(target, destination)
    return destination


def sha256_file(path: str | Path) -> str | None:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return None
    digest = sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_knowledge_directories(root: str | Path | None = None) -> None:
    base = kb_root(root)
    for relative in (
        "db",
        "facts",
        "entities",
        "relations",
        "provenance",
        "graph",
        "wiki/pages",
        "wiki/manifests",
        "wiki/stale",
        "wiki/drafts",
        "synthesis/fast",
        "synthesis/deep",
        "synthesis/packets",
        "open_brain/questions",
        "open_brain/proposals",
        "open_brain/gaps",
        "validators",
        "reports",
        "configs",
        "telemetry",
        "scripts",
    ):
        (base / relative).mkdir(parents=True, exist_ok=True)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "untitled"


def page_slug(topic: str) -> str:
    return TOPIC_FILES.get(topic, safe_slug(topic))


def list_topic_names() -> list[str]:
    return list(TOPIC_FILES.keys())


def current_store_paths(root: str | Path | None = None) -> dict[str, Path]:
    base = kb_root(root) / "db"
    return {
        "fact_store": base / "fact_store.jsonl",
        "entity_store": base / "entity_store.jsonl",
        "relation_store": base / "relation_store.jsonl",
        "claim_store": base / "claim_store.jsonl",
        "contradiction_store": base / "contradiction_store.jsonl",
    }


def load_stores(root: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    paths = current_store_paths(root)
    return {
        "facts": [row for row in read_jsonl(paths["fact_store"]) if isinstance(row, dict)],
        "entities": [row for row in read_jsonl(paths["entity_store"]) if isinstance(row, dict)],
        "relations": [row for row in read_jsonl(paths["relation_store"]) if isinstance(row, dict)],
        "claims": [row for row in read_jsonl(paths["claim_store"]) if isinstance(row, dict)],
        "contradictions": [row for row in read_jsonl(paths["contradiction_store"]) if isinstance(row, dict)],
    }


def fact_statement(fact: dict[str, Any]) -> str:
    return f"{fact.get('subject', '')} {fact.get('predicate', '')} {fact.get('object', '')}".strip()


def relation_statement(relation: dict[str, Any]) -> str:
    return (
        f"{relation.get('source_entity_id', '')} "
        f"{relation.get('relation_type', '')} "
        f"{relation.get('target_entity_id', '')}"
    ).strip()


def search_text(value: str) -> str:
    return value.lower().strip()


def fact_matches_query(fact: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(fact.get("subject", "")),
            str(fact.get("predicate", "")),
            str(fact.get("object", "")),
            str(fact.get("fact_type", "")),
            str(fact.get("status", "")),
        ]
    ).lower()
    return search_text(query) in haystack


def entity_matches_query(entity: dict[str, Any], query: str) -> bool:
    haystack = " ".join(
        [
            str(entity.get("entity_id", "")),
            str(entity.get("name", "")),
            str(entity.get("description", "")),
            " ".join(str(alias) for alias in entity.get("aliases", [])),
            str(entity.get("entity_type", "")),
        ]
    ).lower()
    return search_text(query) in haystack


def normalize_warning(value: str) -> str:
    text = value.strip()
    return text if text.startswith("WARN:") else f"WARN: {text}"


def safety_baseline(root: str | Path | None = None) -> dict[str, Any]:
    repo_root = detect_repo_root(root)
    runtime_contract = read_json(repo_root / "library" / "index" / "runtime_contract.json", {})
    runtime_mode = read_json(repo_root / "library" / "config" / "runtime_mode.json", {})
    loop_schedule = read_json(repo_root / "library" / "config" / "loop_schedule.json", {})
    clu_policy = read_json(repo_root / "library" / "config" / "clu_runtime_policy.json", {})
    recurring_constraints = read_json(repo_root / "sandbox_agi" / "cognition" / "environment" / "recurring_constraints.json", {})
    deletion_queue_path = repo_root / "library" / "queues" / "deletion_queue.jsonl"
    deletion_queue = read_jsonl(deletion_queue_path)
    phase_18_6_reports = sorted((repo_root / "ecology" / "reports").glob("PHASE18_6_*.md"))
    praxis_root = repo_root / "praxis"
    constraints = {row.get("name"): bool(row.get("active")) for row in recurring_constraints.get("constraints", []) if isinstance(row, dict)}
    loop_constraints = loop_schedule.get("phase_18_1_constraints", {})
    return {
        "runtime_contract_path": str(repo_root / "library" / "index" / "runtime_contract.json"),
        "runtime_mode_path": str(repo_root / "library" / "config" / "runtime_mode.json"),
        "loop_schedule_path": str(repo_root / "library" / "config" / "loop_schedule.json"),
        "clu_policy_path": str(repo_root / "library" / "config" / "clu_runtime_policy.json"),
        "fail_closed": runtime_contract.get("fail_closed") is True and runtime_mode.get("fail_closed") is True,
        "deletion_enabled": runtime_contract.get("deletion_enabled") is True or runtime_mode.get("deletion_enabled") is True,
        "DELETE_DISABLED": runtime_contract.get("DELETE_DISABLED") is True,
        "deletion_queue": len(deletion_queue),
        "clu_disabled": clu_policy.get("default_enabled") is False and clu_policy.get("allow_automatic_invocation") is False,
        "archive_movement_disabled": loop_constraints.get("no_archive_movement") is True,
        "quarantine_disabled": runtime_mode.get("quarantine_enabled") is False and loop_constraints.get("no_quarantine_movement") is True,
        "autonomous_mutation_disabled": constraints.get("no_live_mutation") is True and constraints.get("no_auto_promotion") is True,
        "raw_archive_blocked_from_live_retrieval": runtime_contract.get("no_raw_archive_runtime_retrieval") is True,
        "phase18_6_final_report_exists": bool(phase_18_6_reports),
        "phase18_6_reports": [str(path) for path in phase_18_6_reports],
        "production_praxis_root": str(praxis_root),
        "production_praxis_exists": praxis_root.exists(),
        "production_praxis_mtime_utc": (
            datetime.fromtimestamp(praxis_root.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            if praxis_root.exists()
            else None
        ),
    }


def list_operator_decision_files(root: str | Path | None = None) -> list[Path]:
    repo_root = detect_repo_root(root)
    decision_root = repo_root / "library" / "memory" / "operator_decisions"
    if not decision_root.exists():
        return []
    return sorted(path for path in decision_root.iterdir() if path.is_file())


def latest_matching(path: str | Path, pattern: str) -> Path | None:
    base = Path(path)
    files = sorted(base.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True) if base.exists() else []
    return files[0] if files else None


def read_markdown(path: str | Path) -> str:
    return read_text(path, default="")


def build_source_manifest_summary(source_artifacts: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for artifact in source_artifacts:
        artifact_path = Path(artifact)
        items.append(
            {
                "path": str(artifact_path),
                "exists": artifact_path.exists(),
                "sha256": sha256_file(artifact_path),
            }
        )
    return items

