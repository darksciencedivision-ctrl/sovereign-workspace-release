from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_text_utf8_bom_safe(path: str | Path, default: str = "") -> str:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return target.read_text(encoding="utf-8-sig")
    except OSError:
        return default


def read_json_bom_safe(path: str | Path, default: Any = None) -> Any:
    text = read_text_utf8_bom_safe(path, default="")
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def read_jsonl_bom_safe(path: str | Path) -> list[Any]:
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


def _write_text_atomic(path: Path, content: str) -> None:
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


def write_json_atomic(path: str | Path, data: Any) -> None:
    _write_text_atomic(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def append_jsonl(path: str | Path, record: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
