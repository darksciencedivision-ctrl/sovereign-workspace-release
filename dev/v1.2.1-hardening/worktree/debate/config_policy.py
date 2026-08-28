"""Canonical configuration policy for Debate Table.

Single source of truth for: config parsing (encoding + fail-closed), the
Ollama endpoint classification, and the loopback-only default policy with
explicit remote opt-in. Runtime, bootstrap verification, diagnostics and
tests must consume these functions rather than re-deriving behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ConfigurationError(RuntimeError):
    """Raised when configuration cannot be parsed or violates policy.

    The original file bytes are never modified when this is raised.
    """


def _read_config_text(path: Path) -> str:
    # utf-8-sig is the single documented config interpretation, shared with
    # scripts/bootstrap.ps1 and scripts/bootstrap.sh model checks, so a BOM
    # written by an editor cannot split runtime behavior from bootstrap.
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ConfigurationError(f"config unreadable at {path}: {exc}") from exc


def _parse_config_document(path: Path, text: str) -> dict:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(document, dict):
        raise ConfigurationError(
            f"config root must be a JSON object in {path}, got {type(document).__name__}"
        )
    return document


def classify_ollama_endpoint(url: str) -> str:
    """Classify an Ollama base URL as "loopback" or "remote".

    Loopback means the resolved host is 127.0.0.1, localhost, or ::1.
    Anything else - including other 127.x addresses - is remote.
    """
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ConfigurationError(f"unparseable ollama_url {url!r}: {exc}") from exc
    if parts.scheme not in ("http", "https"):
        raise ConfigurationError(
            f"ollama_url {url!r} must use http:// or https://"
        )
    host = (parts.hostname or "").strip("[ ]").lower()
    if not host:
        raise ConfigurationError(f"ollama_url {url!r} has no host")
    return "loopback" if host in LOOPBACK_HOSTS else "remote"


def resolve_ollama_base(
    config_url: str,
    env_url: str | None,
    allow_remote: bool,
    config_path: Path,
) -> tuple[str, str]:
    """Return (effective_base_url, endpoint_class) applying P0-05 policy.

    The environment variable is a source for the value, never a bypass:
    whatever URL wins must still satisfy the loopback-default policy.
    """
    chosen = (env_url or config_url).rstrip("/")
    origin = "OLLAMA_URL environment" if env_url else f"{config_path}"
    endpoint_class = classify_ollama_endpoint(chosen)
    if endpoint_class == "remote" and not allow_remote:
        raise ConfigurationError(
            f"ollama_url {chosen!r} from {origin} is non-loopback;"
            " remote Ollama requires deliberate opt-in:"
            ' set "allow_remote_ollama": true in config.json'
        )
    return chosen, endpoint_class


def effective_summary(config_path: str) -> dict:
    """Bootstrap-facing summary of effective configuration.

    Used by scripts/effective_config.py so bootstrap checks consume exactly
    the same resolution logic as the runtime.
    """
    path = Path(config_path)
    document = _parse_config_document(path, _read_config_text(path))
    allow_remote = bool(document.get("allow_remote_ollama", False))
    raw_url = str(document.get("ollama_url", "")).strip() or "http://127.0.0.1:11434"
    base, endpoint_class = resolve_ollama_base(raw_url, None, allow_remote, path)
    port = document.get("port", 8700)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigurationError(f"config.port: invalid port value {port!r}")
    return {
        "config_path": str(path),
        "ollama_url": base,
        "endpoint_class": endpoint_class,
        "allow_remote_ollama": allow_remote,
        "port": port,
    }