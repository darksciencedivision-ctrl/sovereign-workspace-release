from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas"
if str(SCHEMAS_DIR) not in sys.path:
    sys.path.insert(0, str(SCHEMAS_DIR))

from validate_arbitration_artifact import (  # noqa: E402
    ARBITRATION_ARTIFACT_SCHEMA_VERSION,
    ArbitrationArtifactValidationError,
    normalize_artifact_payload,
    validate_artifact_payload,
)

DEFAULT_OUTPUT_DIR = ROOT / "arbitration"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=str(path.parent),
        prefix=f"{path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def persist_arbitration_artifact(
    artifact: dict[str, Any],
    session_id: str,
    batch_id: str | None = None,
    run_type: str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    allow_overwrite: bool = False,
    source_paths: list[str] | None = None,
) -> Path:
    output_root = Path(output_dir).expanduser().resolve()
    target_path = output_root / f"{session_id}.json"

    normalized = normalize_artifact_payload(
        artifact,
        session_id=session_id,
        batch_id=batch_id,
        run_type=run_type,
        source_paths=source_paths,
    )
    normalized["schema_version"] = ARBITRATION_ARTIFACT_SCHEMA_VERSION
    normalized["artifact_path"] = str(target_path)

    errors = validate_artifact_payload(normalized)
    if errors:
        raise ArbitrationArtifactValidationError("; ".join(errors))

    if target_path.exists() and not allow_overwrite:
        raise FileExistsError(f"refusing to overwrite existing arbitration artifact: {target_path}")

    _write_json_atomic(target_path, normalized)
    return target_path
