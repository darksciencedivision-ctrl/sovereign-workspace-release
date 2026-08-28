from __future__ import annotations

import json
import ipaddress
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sovereign_version import PRODUCT_VERSION
from tools.sovereign_paths import get_repo_root, validate_repo_root

MANIFEST_FILENAME = "SYSTEM_MANIFEST.json"
REQUIRED_MODEL_KEYS = (
    "PRIMARY_REASONER",
    "ADVERSARIAL_CHALLENGER",
    "CRITIC",
    "SYNTHESIZER",
    "EMBEDDING_MODEL",
)
REQUIRED_RUNTIME_KEYS = (
    "CONTEXT_WINDOW",
    "MAX_OUTPUT_TOKENS",
    "OLLAMA_BASE_URL",
    "EMBEDDING_TIMEOUT_SECONDS",
)
REQUIRED_THRESHOLD_KEYS = (
    "CLAIM_AGREE_COSINE",
    "CLAIM_VARIANCE_COSINE",
    "CHALLENGE_ANSWER_COSINE",
)


class ManifestConfigError(RuntimeError):
    pass


def _coerce_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestConfigError(f"{label} must be a JSON object")
    return dict(value)


def find_sovereign_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return validate_repo_root(Path(root).expanduser())
    return get_repo_root()


def manifest_path_for(root: str | Path | None = None) -> Path:
    return find_sovereign_root(root) / MANIFEST_FILENAME


def _require_non_empty_string(mapping: dict[str, Any], key: str, label: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value:
        raise ManifestConfigError(f"{label}.{key} must be a non-empty string")
    return value


def _require_number(mapping: dict[str, Any], key: str, label: str) -> float:
    raw = mapping.get(key)
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ManifestConfigError(f"{label}.{key} must be numeric")
    value = float(raw)
    if not math.isfinite(value):
        raise ManifestConfigError(f"{label}.{key} must be finite")
    return value


def _require_loopback_ollama_url(mapping: dict[str, Any], key: str, label: str) -> str:
    value = _require_non_empty_string(mapping, key, label)
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError as exc:
        raise ManifestConfigError(f"{label}.{key} must be a valid URL") from exc
    if (
        parsed.scheme.lower() != "http"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65_535)
    ):
        raise ManifestConfigError(
            f"{label}.{key} must be an unambiguous loopback HTTP endpoint"
        )
    if host != "localhost":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ManifestConfigError(f"{label}.{key} must be loopback/local only")
    return value


def validate_system_manifest(data: Any, source: str | Path = MANIFEST_FILENAME) -> dict[str, Any]:
    manifest = _coerce_mapping(data, str(source))
    archive_version = str(manifest.get("ARCHIVE_VERSION", "")).strip()
    if archive_version and archive_version != PRODUCT_VERSION:
        raise ManifestConfigError(
            f"{source}.ARCHIVE_VERSION={archive_version!r} disagrees with "
            f"authoritative product version {PRODUCT_VERSION!r}"
        )

    models = _coerce_mapping(manifest.get("MODELS"), f"{source}.MODELS")
    runtime = _coerce_mapping(manifest.get("RUNTIME"), f"{source}.RUNTIME")
    thresholds = _coerce_mapping(manifest.get("THRESHOLDS"), f"{source}.THRESHOLDS")

    for key in REQUIRED_MODEL_KEYS:
        _require_non_empty_string(models, key, f"{source}.MODELS")
    runtime_label = f"{source}.RUNTIME"
    for key in REQUIRED_RUNTIME_KEYS:
        if key == "OLLAMA_BASE_URL":
            _require_loopback_ollama_url(runtime, key, runtime_label)
        else:
            _require_number(runtime, key, runtime_label)

    context_window = runtime.get("CONTEXT_WINDOW")
    maximum_output = runtime.get("MAX_OUTPUT_TOKENS")
    if (
        isinstance(context_window, bool)
        or not isinstance(context_window, int)
        or context_window < 4_096
    ):
        raise ManifestConfigError(
            f"{runtime_label}.CONTEXT_WINDOW must be an integer of at least 4096"
        )
    if (
        isinstance(maximum_output, bool)
        or not isinstance(maximum_output, int)
        or maximum_output <= 0
        or maximum_output >= context_window
    ):
        raise ManifestConfigError(
            f"{runtime_label}.MAX_OUTPUT_TOKENS must be a positive integer "
            "below CONTEXT_WINDOW"
        )
    embedding_timeout = _require_number(
        runtime,
        "EMBEDDING_TIMEOUT_SECONDS",
        runtime_label,
    )
    if embedding_timeout <= 0:
        raise ManifestConfigError(
            f"{runtime_label}.EMBEDDING_TIMEOUT_SECONDS must be positive"
        )

    threshold_label = f"{source}.THRESHOLDS"
    validated_thresholds: dict[str, float] = {}
    for key in REQUIRED_THRESHOLD_KEYS:
        value = _require_number(thresholds, key, threshold_label)
        if not -1.0 <= value <= 1.0:
            raise ManifestConfigError(
                f"{threshold_label}.{key} must be between -1.0 and 1.0"
            )
        validated_thresholds[key] = value
    if (
        validated_thresholds["CLAIM_VARIANCE_COSINE"]
        > validated_thresholds["CLAIM_AGREE_COSINE"]
    ):
        raise ManifestConfigError(
            f"{threshold_label}.CLAIM_VARIANCE_COSINE must not exceed "
            "CLAIM_AGREE_COSINE"
        )

    normalized = dict(manifest)
    normalized["ARCHIVE_VERSION"] = PRODUCT_VERSION
    normalized["MODELS"] = models
    normalized["RUNTIME"] = runtime
    normalized["THRESHOLDS"] = thresholds
    return normalized


def load_system_manifest(root: str | Path | None = None, manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve() if manifest_path is not None else manifest_path_for(root)
    if not path.exists():
        raise ManifestConfigError(f"Missing manifest: {path}")
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ManifestConfigError(f"Unable to read manifest {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestConfigError(f"Malformed manifest JSON {path}: {exc}") from exc
    return validate_system_manifest(data, path)


def model_name(key: str, manifest: dict[str, Any]) -> str:
    return _require_non_empty_string(_coerce_mapping(manifest.get("MODELS"), "MODELS"), key, "MODELS")


def runtime_value(key: str, manifest: dict[str, Any]) -> Any:
    runtime = _coerce_mapping(manifest.get("RUNTIME"), "RUNTIME")
    if key not in runtime:
        raise ManifestConfigError(f"RUNTIME.{key} missing from manifest")
    return runtime[key]


def threshold_value(key: str, manifest: dict[str, Any]) -> float:
    thresholds = _coerce_mapping(manifest.get("THRESHOLDS"), "THRESHOLDS")
    return _require_number(thresholds, key, "THRESHOLDS")
