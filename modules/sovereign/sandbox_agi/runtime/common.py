from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SANDBOX_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def ensure_parent(path: Path | str) -> Path:
    normalized = normalize_path(path)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return normalized


def json_text(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def load_json(path: Path | str, default: Any | None = None) -> Any:
    normalized = normalize_path(path)
    if not normalized.exists():
        return default
    return json.loads(normalized.read_text(encoding="utf-8"))


def read_text(path: Path | str, default: str = "") -> str:
    normalized = normalize_path(path)
    if not normalized.exists():
        return default
    return normalized.read_text(encoding="utf-8")


def append_jsonl(path: Path | str, record: dict[str, Any]) -> None:
    normalized = ensure_parent(path)
    with normalized.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, sort_keys=True))
        handle.write("\n")


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    normalized = normalize_path(path)
    if not normalized.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in normalized.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        entries.append(json.loads(stripped))
    return entries


def sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path | str) -> str | None:
    normalized = normalize_path(path)
    if not normalized.exists() or not normalized.is_file():
        return None
    digest = sha256()
    with normalized.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def shorten(text: str, limit: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def bounded_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def tokenize_text(text: str, *, min_len: int = 3) -> set[str]:
    pattern = rf"[a-z0-9_]{{{min_len},}}"
    return {token for token in re.findall(pattern, str(text).lower()) if token}


def jaccard_similarity(left: str, right: str) -> float:
    left_terms = tokenize_text(left)
    right_terms = tokenize_text(right)
    if not left_terms or not right_terms:
        return 0.0
    union = left_terms | right_terms
    if not union:
        return 0.0
    return len(left_terms & right_terms) / len(union)
