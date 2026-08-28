from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.sovereign_paths import get_repo_root


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


@dataclass(frozen=True)
class EcologyPaths:
    root: Path
    ecology: Path
    library: Path
    retrieval: Path
    telemetry: Path
    memory_packets: Path
    reports: Path
    economics: Path
    ontology: Path
    abstraction_graphs: Path
    arbitration: Path
    social_cognition: Path
    evolution: Path
    configs: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_paths(root: str | Path | None = None) -> EcologyPaths:
    repo_root = Path(root).resolve() if root else get_repo_root()
    ecology = repo_root / "ecology"
    return EcologyPaths(
        root=repo_root,
        ecology=ecology,
        library=repo_root / "library",
        retrieval=ecology / "retrieval",
        telemetry=ecology / "telemetry",
        memory_packets=ecology / "memory_packets",
        reports=ecology / "reports",
        economics=ecology / "economics",
        ontology=ecology / "ontology",
        abstraction_graphs=ecology / "abstraction_graphs",
        arbitration=ecology / "arbitration",
        social_cognition=ecology / "social_cognition",
        evolution=ecology / "evolution",
        configs=ecology / "configs",
    )


def build_query_id(query: str) -> str:
    normalized = normalize_identifier(query)[:48] or "query"
    return f"ECO_{stamp_now()}_{normalized}"


def normalize_identifier(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned or "item"


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"[a-z0-9][a-z0-9_\-]*", (text or "").lower()):
        token = match.group(0).strip("_-")
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def summarize_text(text: str, limit: int = 320) -> str:
    compact = normalize_text(text)
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def recency_score(*, timestamp_text: Any = None, path: Path | None = None) -> float:
    parsed = parse_timestamp(timestamp_text)
    if parsed is None and path is not None and path.exists():
        parsed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    if parsed is None:
        return 0.25
    age_seconds = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    age_days = age_seconds / 86400.0
    return round(max(0.15, 1.0 / (1.0 + (age_days / 30.0))), 4)


def safe_read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return default


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path) -> list[Any]:
    if not path.exists():
        return []
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, payload: Any) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def validate_json_file(path: Path) -> bool:
    json.loads(path.read_text(encoding="utf-8-sig"))
    return True


def validate_jsonl_file(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        json.loads(stripped)
    return True


def read_path_text(path: Path, *, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    if path.suffix.lower() == ".json":
        payload = read_json(path, default={})
        text = json.dumps(payload, ensure_ascii=False, indent=2) if payload is not None else ""
    elif path.suffix.lower() == ".jsonl":
        text = "\n".join(json.dumps(row, ensure_ascii=False) for row in read_jsonl(path))
    else:
        text = safe_read_text(path)
    return text[:limit]


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def flatten(values: Iterable[Iterable[Any]]) -> list[Any]:
    flattened: list[Any] = []
    for group in values:
        for value in group:
            flattened.append(value)
    return flattened


def unique_preserve_order(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    ordered: list[Any] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def estimate_token_count(text: str) -> int:
    return max(1, math.ceil(len(text or "") / 4))
