"""Unified, same-origin local service for the SOVEREIGN product.

The service is intentionally boring at its trust boundaries:

* it binds only to a loopback address;
* it serves the built UI and ``/v1`` API from the same Flask origin;
* every mutation is JSON and rejects cross-origin browser requests;
* sessions, messages, settings, and job transitions are durable;
* only an accepted result belonging to the exact queued job becomes a
  SOVEREIGN chat message.

The module has no import-time server or database side effects.  ``main`` is the
canonical executable entry point and ``create_app`` is the test/embedding
surface.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import ipaddress
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlsplit

from flask import Flask, Response, jsonify, request, send_file
from werkzeug.exceptions import HTTPException, NotFound as WerkzeugNotFound

from sovereign_version import PRODUCT_VERSION

from .evidence import EvidenceBuilder
from .executors import ExecutionStatus, QuickExecutor
from .introspection import (
    answer_self_query,
    collect_self_state,
    model_service_authority,
    status_answer,
)
from .manifest_overrides import (
    ManifestOverrideError,
    apply_overrides,
    load_overrides,
    write_model_overrides,
)
from .model_client import (
    OLLAMA_CONNECT_TIMEOUT_SECONDS,
    OLLAMA_GENERATION_TIMEOUT_SECONDS,
    OllamaClient,
)
from .paths import (
    STATE_POINTER_PREFIX,
    PathResolutionError,
    ProductPaths,
    UnsafeArtifactPointer,
    resolve_product_paths,
    resolve_root,
)
from .quality import (
    build_quick_prompt,
    quick_escalation_policy,
    validate_quick_response,
)
from .router import Route, RoutingDecision, route_query
from .semantic_deep import SemanticDeepExecutor
from .shutdown_watcher import install_shutdown_watcher
from .state_migration import ensure_state_home
from .store import InvalidTransition, NotFound, SovereignStore
from system_manifest import (
    ManifestConfigError,
    load_shipped_manifest,
    load_system_manifest,
    validate_system_manifest,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5175
DEFAULT_WORKERS = 2
MAX_JSON_BYTES = 1_048_576
MAX_INPUT_CHARACTERS = 131_072
MAX_TITLE_CHARACTERS = 200
SETTINGS_META_KEY = "product.settings.v1"
CONFIGURABLE_MODEL_ROLES = (
    "PRIMARY_REASONER",
    "ADVERSARIAL_CHALLENGER",
    "CRITIC",
    "SYNTHESIZER",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "defaultWorkspace": "",
    "startupBehavior": "restore-last",
    "orchestrationProfile": "default",
    "approvalMode": "manual",
    "evidenceLogsEnabled": True,
    "memoryEnabled": True,
    "auditTrailEnabled": True,
    "privacyMode": "local-only",
}
FIXED_PRODUCT_POLICIES: dict[str, Any] = {
    "startupBehavior": "restore-last",
    "approvalMode": "manual",
    "evidenceLogsEnabled": True,
    "memoryEnabled": True,
    "auditTrailEnabled": True,
    "privacyMode": "local-only",
}

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ACTIVE_STATES = {"queued", "running"}
LOGGER = logging.getLogger(__name__)


class ServiceConfigurationError(RuntimeError):
    """The local service cannot be initialized safely."""


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _host_authority(raw: str) -> tuple[str, int | None] | None:
    """Parse an HTTP Host/origin authority without DNS resolution."""

    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = urlsplit("//" + raw.strip())
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return None
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not _is_loopback_host(hostname)
    ):
        return None
    return hostname, port


def _origin_authority(raw: str) -> tuple[str, str, int | None] | None:
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == "null":
        return None
    try:
        parsed = urlsplit(raw.strip())
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "http"
        or not hostname
        or not _is_loopback_host(hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        return None
    return parsed.scheme.lower(), hostname, port


def _same_origin(origin: str, host_header: str, request_scheme: str) -> bool:
    parsed_origin = _origin_authority(origin)
    parsed_host = _host_authority(host_header)
    if parsed_origin is None or parsed_host is None:
        return False
    scheme, origin_host, origin_port = parsed_origin
    host, host_port = parsed_host
    effective_origin_port = origin_port or (80 if scheme == "http" else None)
    effective_host_port = host_port or (80 if request_scheme == "http" else None)
    return (
        scheme == request_scheme.lower()
        and origin_host == host
        and effective_origin_port == effective_host_port
    )


def _validate_bind_host(host: str) -> str:
    candidate = str(host or "").strip()
    if not _is_loopback_host(candidate):
        raise ServiceConfigurationError(
            "SOVEREIGN may bind only to localhost or a numeric loopback address"
        )
    return candidate


def _json_error(message: str, status: int, **extra: Any) -> tuple[Response, int]:
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return jsonify(payload), status


def _enum_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _result_fields(result: Any) -> dict[str, Any]:
    """Normalize typed and injected executor results without accepting guesses."""

    if isinstance(result, Mapping):
        raw = dict(result)
    else:
        converter = getattr(result, "to_dict", None)
        if callable(converter):
            converted = converter()
            raw = dict(converted) if isinstance(converted, Mapping) else {}
        else:
            raw = {
                key: getattr(result, key)
                for key in (
                    "status",
                    "answer",
                    "reason",
                    "error",
                    "model",
                    "artifacts",
                    "telemetry",
                    "escalation_requested",
                    "escalation_reason",
                )
                if hasattr(result, key)
            }
    raw["status"] = _enum_text(raw.get("status"))
    return raw


def _authoritative_task_tokens(fields: Mapping[str, Any]) -> int | None:
    """Sum only authoritative Ollama prompt and generation token counts."""

    for candidate in (fields.get("telemetry"), fields.get("resources")):
        if not isinstance(candidate, Mapping):
            continue
        prompt_count = candidate.get("prompt_eval_count")
        output_count = candidate.get("eval_count")
        valid_prompt = (
            isinstance(prompt_count, int)
            and not isinstance(prompt_count, bool)
            and prompt_count >= 0
        )
        valid_output = (
            isinstance(output_count, int)
            and not isinstance(output_count, bool)
            and output_count >= 0
        )
        if valid_prompt and valid_output:
            if candidate.get("token_usage_complete") is False:
                return None
            return int(prompt_count) + int(output_count)
    return None


def _job_elapsed_seconds(job: Mapping[str, Any]) -> float | None:
    started_at = job.get("started_at")
    finished_at = job.get("finished_at")
    if not isinstance(started_at, str) or not isinstance(finished_at, str):
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None or finished.tzinfo is None:
        return None
    return max(0.0, (finished - started).total_seconds())


def _job_metrics(job: Mapping[str, Any]) -> dict[str, Any] | None:
    elapsed_seconds = _job_elapsed_seconds(job)
    if elapsed_seconds is None:
        return None
    metadata = job.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    tokens = metadata.get("task_tokens")
    if (
        not isinstance(tokens, int)
        or isinstance(tokens, bool)
        or tokens < 0
    ):
        tokens = _authoritative_task_tokens(
            {
                "telemetry": metadata.get("telemetry"),
                "resources": metadata.get("resources"),
            }
        )
    return {
        "tokens": tokens,
        "elapsed_seconds": elapsed_seconds,
    }


def _terminal_status(engine_status: str, *, has_answer: bool) -> str:
    normalized = str(engine_status or "").strip().lower()
    if normalized in {"accepted", "completed"}:
        return "completed" if has_answer else "rejected"
    if normalized in {"empty", "rejected", "concurrence_not_reached"}:
        return "rejected"
    if normalized == "cancelled":
        return "cancelled"
    if normalized == "interrupted":
        return "interrupted"
    return "failed"


def _safe_progress(value: Any, *, fallback_stage: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        progress = {
            str(key): item
            for key, item in value.items()
            if str(key)
            in {
                "percent",
                "percentage",
                "stage",
                "phase",
                "state",
                "detail",
                "message",
                "current",
                "total",
                "stream",
                "sequence",
                "model",
                "job_id",
                "execution_id",
                "recovery_artifact",
                "evidence_pointer",
            }
        }
    else:
        progress = {}
    if "stage" not in progress and "phase" in progress:
        progress["stage"] = progress.pop("phase")
    if "detail" not in progress and "message" in progress:
        progress["detail"] = progress.pop("message")
    if "percent" not in progress and "percentage" in progress:
        progress["percent"] = progress.pop("percentage")
    if "stage" not in progress:
        progress["stage"] = fallback_stage
    raw_percent = progress.get("percent")
    if not isinstance(raw_percent, (int, float)):
        current = progress.get("current")
        total = progress.get("total")
        if (
            isinstance(current, (int, float))
            and not isinstance(current, bool)
            and math.isfinite(float(current))
            and isinstance(total, (int, float))
            and not isinstance(total, bool)
            and math.isfinite(float(total))
            and total > 0
        ):
            raw_percent = current / total * 100
        else:
            raw_percent = 0
    if isinstance(raw_percent, bool) or not math.isfinite(float(raw_percent)):
        raise ValueError("progress percent must be finite")
    progress["percent"] = max(
        0,
        min(100, round(float(raw_percent), 2)),
    )
    return progress


def _record_digest(value: Mapping[str, Any]) -> str:
    record = dict(value)
    record.pop("record_sha256", None)
    encoded = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verified_semantic_request(
    path: Path,
    *,
    job_id: str,
    session_id: str,
    execution_id: str,
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    digest = payload.get("record_sha256")
    return bool(
        payload.get("record_type") == "semantic_deep_request"
        and payload.get("job_id") == job_id
        and payload.get("session_id") == session_id
        and payload.get("execution_id") == execution_id
        and isinstance(digest, str)
        and len(digest) == 64
        and digest == _record_digest(payload)
    )


def _normalize_settings(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("settings value must be an object")
    merged = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if key in raw:
            merged[key] = raw[key]
    # Migrate legacy decorative values to the policies the executable product
    # actually enforces. Only the theme is currently operator-editable.
    merged.update(FIXED_PRODUCT_POLICIES)
    return _validate_settings(merged)


def _settings_value(raw: Any) -> dict[str, Any]:
    try:
        return _normalize_settings(raw)
    except ValueError:
        return dict(DEFAULT_SETTINGS)


def _validate_settings(raw: Mapping[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(raw) - set(DEFAULT_SETTINGS))
    if unknown:
        raise ValueError(f"unknown setting(s): {', '.join(unknown)}")
    merged = {**DEFAULT_SETTINGS, **dict(raw)}
    if merged["theme"] not in {"dark", "light"}:
        raise ValueError("theme must be 'dark' or 'light'")
    if merged["startupBehavior"] not in {"new-chat", "restore-last"}:
        raise ValueError("startupBehavior is invalid")
    if merged["approvalMode"] not in {"manual", "auto"}:
        raise ValueError("approvalMode is invalid")
    if merged["privacyMode"] not in {"local-only", "api-enabled"}:
        raise ValueError("privacyMode is invalid")
    for key in ("defaultWorkspace", "orchestrationProfile"):
        if not isinstance(merged[key], str) or len(merged[key]) > 1_024:
            raise ValueError(f"{key} must be bounded text")
    for key in (
        "evidenceLogsEnabled",
        "memoryEnabled",
        "auditTrailEnabled",
    ):
        if not isinstance(merged[key], bool):
            raise ValueError(f"{key} must be boolean")
    mismatched_policies = [
        key
        for key, expected in FIXED_PRODUCT_POLICIES.items()
        if merged.get(key) != expected
    ]
    if mismatched_policies:
        raise ValueError(
            "fixed product policy cannot be changed: "
            + ", ".join(sorted(mismatched_policies))
        )
    return merged


class ProductService:
    """Own durable product state, bounded executors, and worker recovery."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        paths: ProductPaths | None = None,
        store: SovereignStore | None = None,
        model_client: OllamaClient | None = None,
        quick_executor: Any | None = None,
        deep_executor: Any | None = None,
        research_executor: Any | None = None,
        evidence_builder: EvidenceBuilder | None = None,
        worker_count: int = DEFAULT_WORKERS,
        start_workers: bool = True,
        introspection_http_get: Callable[[str, float], Any] | None = None,
        introspection_timeout: float = 0.6,
        quick_timeout: float = OLLAMA_GENERATION_TIMEOUT_SECONDS,
        deep_timeout: float | None = None,
    ) -> None:
        if paths is None:
            # SW-25: bring legacy install-tree state across (copy-only, once) before
            # anything opens the store or evidence dirs in the external state home.
            ensure_state_home(resolve_root(root))
        self.paths = paths or resolve_product_paths(root, create=True)
        self.root = self.paths.root
        # ProductService always validates its explicit root manifest, including
        # when tests or embedding callers inject transport/executor doubles.
        self._manifest()
        self.store = store or SovereignStore(self.paths.db_path)
        self.model_client = model_client or self._default_model_client()
        self._injected_quick_executor = quick_executor
        self._injected_deep_executor = deep_executor
        self._configuration_lock = threading.RLock()
        self.evidence_builder = evidence_builder or EvidenceBuilder(
            self.root,
            approved_paths=self._approved_evidence_paths(),
            message_source=self.store,
            max_bytes=8_192,
            max_tokens=4_096,
            max_source_bytes=2_048,
            query_relevance=True,
        )
        self.deep_executor = deep_executor or self._default_deep_executor()
        self.research_executor = research_executor
        self.research_unavailable_reason: str | None = None
        if self.research_executor is None:
            self.research_executor = self._discover_research_executor()
        if worker_count < 1 or worker_count > 32:
            raise ValueError("worker_count must be between 1 and 32")
        if not 0 < float(introspection_timeout) < 2:
            raise ValueError("introspection_timeout must be below two seconds")
        self.worker_count = int(worker_count)
        self.introspection_http_get = introspection_http_get
        self.introspection_timeout = float(introspection_timeout)
        self.quick_timeout = float(quick_timeout)
        self.deep_timeout = None if deep_timeout is None else float(deep_timeout)
        self.ui_dist = self.root / "ui" / "ui_shell" / "dist"
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._closed = threading.Event()
        self._queue_lock = threading.RLock()
        self._enqueued: set[str] = set()
        self._active_cancel: dict[str, threading.Event] = {}
        self._active_executor: dict[str, Any] = {}
        self._shutdown_survivors: list[str] = []  # CR-026: workers still alive after a bounded drain
        recovery = self.store.recover_incomplete_jobs()
        for job_id in recovery["queued"]:
            self._enqueue(job_id)
        if start_workers:
            self.start()

    def _manifest(self) -> dict[str, Any]:
        try:
            return load_system_manifest(
                manifest_path=self.root / "SYSTEM_MANIFEST.json"
            )
        except ManifestConfigError as exc:
            raise ServiceConfigurationError(
                f"invalid SYSTEM_MANIFEST configuration: {exc}"
            ) from exc

    def _default_model_client(self) -> Any:
        from .backend_selection import resolve_backend, resolve_freetoken_profile
        from .runtime_contracts import (
            BACKEND_FREETOKEN,
            BACKEND_OLLAMA,
            DEFAULT_LLAMA_CPP_BASE_URL,
            load_default_llama_cpp_api_key,
        )

        # Precedence: explicit SOVEREIGN_INFERENCE_BACKEND env choice, then the
        # persistent runtime/backend_selection.json designation, then llama.cpp.
        backend = resolve_backend(self.root)
        manifest = self._manifest()
        runtime = manifest["RUNTIME"]
        if backend == BACKEND_OLLAMA:
            return OllamaClient(
                str(runtime["OLLAMA_BASE_URL"]),
                connect_timeout=OLLAMA_CONNECT_TIMEOUT_SECONDS,
                read_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
                overall_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
            )
        from .llama_cpp_client import LlamaCppClient

        if backend == BACKEND_FREETOKEN:
            ft_url = str(os.environ.get("SOVEREIGN_FREETOKEN_BASE_URL") or "").strip()
            if not ft_url:
                # Designated FreeToken workload: the supervisor is started
                # on demand with its configured profile (GPU ownership
                # transition included); no manual launch or shell variables.
                from .freetoken_service import ensure_runtime

                ft_url = str(
                    ensure_runtime(
                        self.root,
                        profile=resolve_freetoken_profile(self.root),
                    )["base_url"]
                )
            return LlamaCppClient(
                ft_url,
                api_key=os.environ.get("SOVEREIGN_FREETOKEN_API_KEY") or None,
                connect_timeout=OLLAMA_CONNECT_TIMEOUT_SECONDS,
                read_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
                overall_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
            )
        llama_url = (
            str(os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL") or "").strip()
            or DEFAULT_LLAMA_CPP_BASE_URL
        )
        llama_key = str(os.environ.get("SOVEREIGN_LLAMA_CPP_API_KEY") or "").strip()
        if not llama_key:
            key_file = self.paths.state_dir / "llamacpp_supervisor" / "api_key"
            if key_file.is_file():
                llama_key = key_file.read_text(encoding="utf-8").strip()
        if not llama_key:
            llama_key = load_default_llama_cpp_api_key() or ""
        return LlamaCppClient(
            llama_url,
            api_key=llama_key or None,
            connect_timeout=OLLAMA_CONNECT_TIMEOUT_SECONDS,
            read_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
            overall_timeout=OLLAMA_GENERATION_TIMEOUT_SECONDS,
        )

    def _primary_model(self) -> str:
        value = self._manifest()["MODELS"]["PRIMARY_REASONER"]
        if not isinstance(value, str) or not value.strip():
            raise ServiceConfigurationError(
                "SYSTEM_MANIFEST MODELS.PRIMARY_REASONER must be non-empty"
            )
        return value.strip()

    def _default_deep_executor(self) -> SemanticDeepExecutor:
        return self._deep_executor_from_manifest(self._manifest())

    @staticmethod
    def _runtime_model_options(
        manifest: Mapping[str, Any],
        models_in_use: tuple[str, ...] | None = None,
    ) -> dict[str, int]:
        """Generation options every model in ``models_in_use`` can actually serve.

        SW-27: DEEP runs several models with ONE set of base options. The window used to be
        derived from the primary reasoner alone, so a slate member with a smaller configured
        cap (qwen2.5:14b-instruct 32768, qwen3:8b 16384) failed its capability check and every
        DEEP run failed on the shipped configuration. The effective window is now the smallest
        cap across every model that will receive these options (default: the primary).
        """
        runtime = manifest.get("RUNTIME")
        runtime_values = dict(runtime) if isinstance(runtime, Mapping) else {}
        context_window = runtime_values.get("CONTEXT_WINDOW")
        maximum_output = runtime_values.get("MAX_OUTPUT_TOKENS")
        if (
            isinstance(context_window, bool)
            or not isinstance(context_window, int)
            or context_window < 4_096
        ):
            raise ServiceConfigurationError(
                "SYSTEM_MANIFEST RUNTIME.CONTEXT_WINDOW must be an integer "
                "of at least 4096"
            )
        if (
            isinstance(maximum_output, bool)
            or not isinstance(maximum_output, int)
            or maximum_output <= 0
            or maximum_output >= context_window
        ):
            raise ServiceConfigurationError(
                "SYSTEM_MANIFEST RUNTIME.MAX_OUTPUT_TOKENS must be a positive "
                "integer below CONTEXT_WINDOW"
            )
        from .runtime_registry import PRODUCTION_ROLES, context_resolution

        models = manifest.get("MODELS")
        primary = PRODUCTION_ROLES["PRIMARY_REASONER"]
        if isinstance(models, Mapping):
            configured_primary = models.get("PRIMARY_REASONER")
            if isinstance(configured_primary, str) and configured_primary.strip():
                primary = configured_primary.strip()
        effective = None
        for model in models_in_use or (primary,):
            resolution = context_resolution(model)
            cap = resolution.get("effective_cap") or resolution.get("configured")
            if not isinstance(cap, int) or cap < 4_096:
                raise ServiceConfigurationError(
                    f"no enforceable context cap for {model}; declared "
                    f"{context_window} is not treated as supported"
                )
            effective = cap if effective is None else min(effective, cap)
        if context_window > effective:
            num_ctx = effective
        else:
            num_ctx = context_window
        num_predict = maximum_output if maximum_output < num_ctx else num_ctx - 1
        return {
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }

    def _deep_executor_from_manifest(
        self,
        manifest: Mapping[str, Any],
    ) -> SemanticDeepExecutor:
        models = manifest.get("MODELS")
        roles = dict(models) if isinstance(models, Mapping) else {}

        def role(name: str) -> str:
            value = roles.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ServiceConfigurationError(
                    f"SYSTEM_MANIFEST MODELS.{name} must be non-empty"
                )
            return value.strip()

        primary = role("PRIMARY_REASONER")
        critic = role("CRITIC")
        synthesizer = role("SYNTHESIZER")
        verifier = role("ADVERSARIAL_CHALLENGER")
        return SemanticDeepExecutor(
            self.root,
            self.model_client,
            member_models=(primary, synthesizer, critic),
            critic_model=critic,
            synthesizer_model=synthesizer,
            verifier_model=verifier,
            artifact_root=self.paths.evidence_dir / "semantic_deep",
            state_dir=self.paths.state_dir,
            evidence_builder=self.evidence_builder,
            base_options=self._runtime_model_options(
                manifest,
                tuple(dict.fromkeys((primary, synthesizer, critic, verifier))),
            ),
        )

    def _write_model_overrides(self, updates: Mapping[str, str]) -> None:
        """SW-25: record model assignments as operator overrides in the state home.

        The shipped SYSTEM_MANIFEST.json is never written. The merged (shipped + overrides)
        manifest is validated BEFORE anything is persisted, and re-loaded after, so an
        assignment that would make the effective manifest invalid is refused unchanged.
        """
        path = self.root / "SYSTEM_MANIFEST.json"
        try:
            shipped = load_shipped_manifest(manifest_path=path)
            current = load_overrides(self.root, shipped)
            proposed = dict(current.get("MODELS") or {})
            proposed.update(updates)
            validate_system_manifest(
                apply_overrides(shipped, {**current, "MODELS": proposed}), path
            )
            write_model_overrides(self.root, shipped, updates)
            load_system_manifest(manifest_path=path)
        except (ManifestConfigError, ManifestOverrideError) as exc:
            raise ServiceConfigurationError(
                f"invalid SYSTEM_MANIFEST update: {exc}"
            ) from exc

    def _approved_evidence_paths(self) -> tuple[str, ...]:
        candidates = (
            "SYSTEM_MANIFEST.json",
            "sovereign_version.py",
            "constitution/constitution_state.json",
            "synthesis/model_hierarchy.json",
            "runtime_profile.json",
        )
        return tuple(item for item in candidates if (self.root / item).is_file())

    def _discover_research_executor(self) -> Any | None:
        """Load a research executor only through an explicit local factory/class."""

        try:
            module = importlib.import_module("sovereign_product.research")
        except ModuleNotFoundError:
            self.research_unavailable_reason = (
                "RESEARCH is unavailable: no local research executor is installed"
            )
            return None
        except Exception as exc:
            self.research_unavailable_reason = (
                f"RESEARCH initialization failed: {type(exc).__name__}"
            )
            return None

        candidate = None
        for name in (
            "create_research_executor",
            "build_research_executor",
            "ResearchExecutor",
        ):
            value = getattr(module, name, None)
            if callable(value):
                candidate = value
                break
        if candidate is None:
            self.research_unavailable_reason = (
                "RESEARCH is unavailable: research.py exposes no executor factory"
            )
            return None
        available = {
            "root": self.root,
            "store": self.store,
            "paths": self.paths,
            "artifact_root": self.paths.evidence_dir,
            "evidence_dir": self.paths.evidence_dir,
            "model_client": self.model_client,
            "client": self.model_client,
        }
        try:
            signature = inspect.signature(candidate)
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            kwargs = (
                available
                if accepts_kwargs
                else {
                    key: value
                    for key, value in available.items()
                    if key in signature.parameters
                }
            )
            executor = candidate(**kwargs)
        except Exception as exc:
            self.research_unavailable_reason = (
                f"RESEARCH initialization failed: {type(exc).__name__}"
            )
            return None
        self.research_unavailable_reason = None
        return executor

    def qualification(self) -> dict[str, Any]:
        """SW-27: the qualification verdict for the configuration this service is running.

        `rejected` when the configuration exceeds an envelope MEASURED on this machine (new
        jobs are refused and health reports degraded until it is re-qualified or lowered with
        `python -m sovereign_product.qualification apply`); `unqualified` when a dimension was
        never measured (reported, never used to refuse); `qualified` otherwise.
        """
        from .backend_selection import resolve_backend
        from .qualification import UNQUALIFIED, evaluate

        try:
            manifest = self._manifest()
            options = self._runtime_model_options(manifest)
            models = manifest.get("MODELS")
            primary = (
                str(models.get("PRIMARY_REASONER") or "")
                if isinstance(models, Mapping)
                else ""
            )
            backend = resolve_backend(self.root)
        except Exception as exc:
            return {
                "verdict": UNQUALIFIED,
                "profile": None,
                "reasons": [f"configuration unavailable: {exc}"],
                "unqualified": ["configuration"],
            }
        return evaluate(
            self.root,
            backend=backend,
            primary_model=primary,
            num_ctx=options["num_ctx"],
            num_predict=options["num_predict"],
            workers=self.worker_count,
        )

    def start(self) -> None:
        if self._closed.is_set() or self._workers:
            return
        for index in range(self.worker_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"sovereign-worker-{index + 1}",
                daemon=True,
            )
            thread.start()
            self._workers.append(thread)

    def close(self) -> dict[str, Any]:
        """CR-026: shut down without silently forgetting workers that outlive the bounded drain.

        In-flight, cancellation-aware jobs are asked to stop; the queue is poison-pilled; workers are
        joined under ONE shared deadline (not an unbounded per-worker wait). Workers still alive after
        the drain are SURVIVORS: retained in `_workers`, recorded in `_shutdown_survivors`, and
        reported in the returned record, so shutdown never claims success while jobs keep running.
        Storage (per-thread connections) is still closed, and the record says whether it was clean.
        """
        if self._closed.is_set():
            survivors = [t for t in self._workers if t.is_alive()]
            return {"clean": not survivors, "survivors": [t.name for t in survivors]}
        self._closed.set()
        for event in list(self._active_cancel.values()):
            event.set()
        for _thread in self._workers:
            self._queue.put(None)
        deadline = time.monotonic() + 2.0
        for thread in self._workers:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                thread.join(timeout=remaining)
        survivors = [t for t in self._workers if t.is_alive()]
        self._workers[:] = survivors  # forget finished workers; keep the survivors tracked
        self._shutdown_survivors.extend(t.name for t in survivors)
        self.store.close()
        return {"clean": not survivors, "survivors": [t.name for t in survivors]}

    def _enqueue(self, job_id: str) -> None:
        with self._queue_lock:
            if job_id in self._enqueued:
                return
            self._enqueued.add(job_id)
            self._queue.put(job_id)

    def _worker_loop(self) -> None:
        while not self._closed.is_set():
            job_id = self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            with self._queue_lock:
                self._enqueued.discard(job_id)
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _cancel_callback(
        self, job_id: str, event: threading.Event
    ) -> Callable[[], bool]:
        def requested() -> bool:
            if event.is_set() or self._closed.is_set():
                return True
            try:
                return bool(self.store.get_job(job_id)["cancel_requested"])
            except Exception:
                return event.is_set()

        return requested

    def _progress_callback(self, job_id: str) -> Callable[[dict[str, Any]], None]:
        attribution_lock = threading.Lock()
        bound_execution_id: str | None = None
        last_sequence: int | None = None
        last_percent = 0.0

        def update(progress: dict[str, Any]) -> None:
            nonlocal bound_execution_id, last_sequence, last_percent
            try:
                with attribution_lock:
                    if (
                        progress.get("job_id") is not None
                        and str(progress["job_id"]) != job_id
                    ):
                        return
                    safe = _safe_progress(progress, fallback_stage="running")
                    # A callback may propose a recovery artifact, but it may
                    # never inject the content pointer that the store exposes.
                    # That pointer is derived only after the immutable request
                    # record and its exact execution path are verified below.
                    safe.pop("evidence_pointer", None)
                    job = self.store.get_job(job_id)
                    execution_value = safe.get("execution_id")
                    execution_id = (
                        execution_value.strip()
                        if isinstance(execution_value, str)
                        else ""
                    )
                    if bound_execution_id is not None and not execution_id:
                        return
                    if execution_id:
                        if safe.get("job_id") != job_id:
                            return
                        if (
                            bound_execution_id is not None
                            and execution_id != bound_execution_id
                        ):
                            return
                    recovery_artifact = safe.get("recovery_artifact")
                    if isinstance(recovery_artifact, str) and recovery_artifact:
                        if not execution_id:
                            return
                        if recovery_artifact.startswith(STATE_POINTER_PREFIX):
                            candidate = self.paths.resolve_pointer(
                                recovery_artifact, must_exist=True
                            ).resolve(strict=True)
                        else:
                            raw = Path(recovery_artifact)
                            candidate = (
                                raw if raw.is_absolute() else self.root / raw
                            ).resolve(strict=True)
                        if not candidate.is_file():
                            return
                        expected_request = (
                            self.paths.evidence_dir
                            / "semantic_deep"
                            / str(job["session_id"])
                            / execution_id
                            / "request.json"
                        ).resolve()
                        if candidate != expected_request:
                            return
                        if not _verified_semantic_request(
                            candidate,
                            job_id=job_id,
                            session_id=str(job["session_id"]),
                            execution_id=execution_id,
                        ):
                            return
                        safe["evidence_pointer"] = self.paths.pointer(candidate)
                    elif execution_id and bound_execution_id is None:
                        # The first semantic progress event must bind its exact
                        # request artifact before any recovery identity is
                        # trusted or persisted.
                        return
                    sequence = safe.get("sequence")
                    if sequence is not None:
                        if (
                            isinstance(sequence, bool)
                            or not isinstance(sequence, int)
                            or sequence <= 0
                            or (
                                last_sequence is not None
                                and sequence <= last_sequence
                            )
                        ):
                            return
                    percent = float(safe["percent"])
                    if percent < last_percent:
                        return
                    self.store.update_job_progress(job_id, safe)
                    if execution_id and bound_execution_id is None:
                        bound_execution_id = execution_id
                    if isinstance(sequence, int):
                        last_sequence = sequence
                    last_percent = percent
            except (
                InvalidTransition,
                NotFound,
                OSError,
                PathResolutionError,
                UnsafeArtifactPointer,
                ValueError,
            ):
                return

        return update

    def _quick_executor(self, query: str) -> Any:
        if self._injected_quick_executor is not None:
            return self._injected_quick_executor
        return QuickExecutor(
            self.model_client,
            self.paths.evidence_dir,
            acceptance_validator=lambda response, evidence: validate_quick_response(
                response,
                evidence,
                query=query,
            ),
            escalation_policy=quick_escalation_policy,
            prompt_builder=build_quick_prompt,
        )

    @staticmethod
    def _invoke(
        executor: Any,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> Any:
        target = getattr(executor, "execute", executor)
        if not callable(target):
            raise TypeError("configured executor has no callable execute method")
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            return target(session_id, text, **kwargs)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        supported = (
            kwargs
            if accepts_kwargs
            else {
                key: value
                for key, value in kwargs.items()
                if key in signature.parameters
            }
        )
        return target(session_id, text, **supported)

    def _execute_job(
        self,
        job: Mapping[str, Any],
        *,
        cancel_requested: Callable[[], bool],
        progress_callback: Callable[[dict[str, Any]], None],
    ) -> tuple[Any, Any]:
        route = Route.parse(str(job["route"]))
        session_id = str(job["session_id"])
        text = str(job["input"])
        if route in {Route.QUICK, Route.CONTINUITY}:
            evidence = self.evidence_builder.build(session_id, query=text)
            executor = self._quick_executor(text)
            with self._queue_lock:
                self._active_executor[str(job["job_id"])] = executor
            # Continuity recall is a lookup, not a composition: sampling only
            # adds a chance of paraphrasing an exact operator fact away.
            temperature = 0.0 if route is Route.CONTINUITY else 0.2
            result = self._invoke(
                executor,
                session_id,
                text,
                model=self._primary_model(),
                evidence=evidence,
                options={
                    **self._runtime_model_options(self._manifest()),
                    "temperature": temperature,
                },
                cancel_requested=cancel_requested,
                overall_timeout=self.quick_timeout,
                progress_callback=progress_callback,
                route=route.value,
                job_id=str(job["job_id"]),
            )
            return result, executor
        if route is Route.DEEP:
            evidence = self.evidence_builder.build(session_id, query=text)
            executor = self.deep_executor
            with self._queue_lock:
                self._active_executor[str(job["job_id"])] = executor
            result = self._invoke(
                executor,
                session_id,
                text,
                evidence=evidence,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                timeout_seconds=self.deep_timeout,
                route=route.value,
                job_id=str(job["job_id"]),
            )
            return result, executor
        if route is Route.RESEARCH:
            if self.research_executor is None:
                raise ServiceConfigurationError(
                    self.research_unavailable_reason
                    or "RESEARCH is unavailable: no executor is configured"
                )
            evidence = self.evidence_builder.build(session_id, query=text)
            executor = self.research_executor
            with self._queue_lock:
                self._active_executor[str(job["job_id"])] = executor
            run = getattr(executor, "run", None)
            if not callable(run):
                raise TypeError(
                    "configured RESEARCH executor has no callable run method"
                )
            result = run(
                str(job["job_id"]),
                text,
                model=self._primary_model(),
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                local_sources=self.evidence_builder.approved_paths,
                execution_evidence=(),
                model_options=self._runtime_model_options(self._manifest()),
                resume_existing=True,
            )
            return result, executor
        raise ValueError(f"{route.value} is not a queued route")

    def _artifact_pointers(
        self,
        artifacts: Any,
        *,
        executor: Any,
    ) -> dict[str, str]:
        if not isinstance(artifacts, Mapping):
            return {}
        converted: dict[str, str] = {}
        executor_artifact_root = getattr(executor, "artifact_root", None)
        for key, value in artifacts.items():
            if not isinstance(value, (str, os.PathLike)) or not str(value):
                continue
            text = str(value)
            if text.startswith(("sovereign://", STATE_POINTER_PREFIX)):
                try:
                    self.paths.resolve_pointer(text, must_exist=True)
                except (PathResolutionError, UnsafeArtifactPointer):
                    continue
                converted[str(key)] = text
                continue
            raw = Path(text)
            candidates: list[Path] = []
            if raw.is_absolute():
                candidates.append(raw)
            else:
                candidates.append(self.root / raw)
                if executor_artifact_root is not None:
                    candidates.append(Path(executor_artifact_root) / raw)
                candidates.append(self.paths.evidence_dir / raw)
            for candidate in candidates:
                try:
                    resolved = candidate.resolve(strict=True)
                    if not resolved.is_file():
                        continue
                    converted[str(key)] = self.paths.pointer(resolved)
                    break
                except (
                    OSError,
                    PathResolutionError,
                    UnsafeArtifactPointer,
                    ValueError,
                ):
                    continue
        return converted

    @staticmethod
    def _select_evidence_pointer(
        pointers: Mapping[str, str],
        *,
        terminal_status: str = "",
    ) -> str | None:
        """Choose the pointer an operator or grader lands on first.

        A completed grounded job points at the machine-readable evidence
        manifest rather than accepted.txt, so the exact source provenance behind
        an answer can actually be resolved. accepted.txt and every other
        forensic artifact stay in the artifact map untouched; only the preferred
        pointer changes, and only for completed jobs that have a manifest.
        """

        if terminal_status.lower() == "completed" and pointers.get("evidence"):
            preference = ("evidence", "accepted", "result", "run_record", "raw")
        else:
            preference = ("accepted", "result", "evidence", "run_record", "raw")
        for key in preference:
            value = pointers.get(key)
            if value:
                return value
        return next(iter(pointers.values()), None)

    def _research_answer(
        self,
        fields: Mapping[str, Any],
        pointers: Mapping[str, str],
    ) -> str:
        """Read only the exact completed report emitted by ResearchExecutor."""

        if str(fields.get("status") or "").lower() != "completed":
            return ""
        pointer = pointers.get("final_report")
        if not pointer:
            return ""
        try:
            path = self.paths.resolve_pointer(pointer, must_exist=True)
            if not path.is_file() or path.stat().st_size > 1_048_576:
                return ""
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError, PathResolutionError, UnsafeArtifactPointer):
            return ""

    def _run_job(self, job_id: str) -> None:
        try:
            queued = self.store.get_job(job_id)
        except NotFound:
            return
        if queued["status"] != "queued":
            return
        try:
            job = self.store.transition_job(
                job_id,
                "running",
                expected_status="queued",
                worker_id=threading.current_thread().name,
            )
            self.store.update_job_progress(
                job_id,
                {"percent": 1, "stage": "running"},
            )
        except InvalidTransition:
            return

        cancel_event = threading.Event()
        with self._queue_lock:
            self._active_cancel[job_id] = cancel_event
        result: Any = None
        executor: Any = None
        try:
            result, executor = self._execute_job(
                job,
                cancel_requested=self._cancel_callback(job_id, cancel_event),
                progress_callback=self._progress_callback(job_id),
            )
            fields = _result_fields(result)
            answer = fields.get("answer")
            answer_text = answer.strip() if isinstance(answer, str) else ""
            pointers = self._artifact_pointers(
                fields.get("artifacts"),
                executor=executor,
            )
            if (
                str(job["route"]).upper() == Route.RESEARCH.value
                and not answer_text
            ):
                answer_text = self._research_answer(fields, pointers)
            current = self.store.get_job(job_id)
            if current["cancel_requested"]:
                terminal = "cancelled"
                answer_text = ""
            else:
                terminal = _terminal_status(
                    str(fields.get("status") or ""),
                    has_answer=bool(answer_text),
                )
            evidence_pointer = self._select_evidence_pointer(
                pointers,
                terminal_status=terminal,
            )
            reason = fields.get("reason") or fields.get("error")
            metadata = {
                "engine_status": str(fields.get("status") or "unknown"),
                "model": fields.get("model"),
                "artifacts": pointers,
                "telemetry": fields.get("telemetry")
                if isinstance(fields.get("telemetry"), Mapping)
                else {},
                "task_tokens": _authoritative_task_tokens(fields),
                "escalation_requested": bool(
                    fields.get("escalation_requested")
                ),
                "escalation_reason": fields.get("escalation_reason"),
            }
            if terminal == "completed":
                message = self.store.append_message(
                    str(job["session_id"]),
                    "sovereign",
                    answer_text,
                    status="accepted",
                    route=str(job["route"]),
                    job_id=job_id,
                    evidence_pointer=evidence_pointer,
                    metadata={
                        "engine_status": fields.get("status"),
                        "model": fields.get("model"),
                    },
                )
                self.store.update_job_progress(
                    job_id,
                    {"percent": 100, "stage": "completed"},
                )
                self.store.transition_job(
                    job_id,
                    "completed",
                    expected_status="running",
                    evidence_pointer=evidence_pointer,
                    output_message_id=message["message_id"],
                    metadata=metadata,
                )
            else:
                self.store.transition_job(
                    job_id,
                    terminal,
                    expected_status="running",
                    error=str(reason or f"executor ended as {terminal}"),
                    evidence_pointer=evidence_pointer,
                    metadata=metadata,
                )
        except Exception as exc:
            try:
                current = self.store.get_job(job_id)
                if current["status"] == "running":
                    terminal = (
                        "cancelled"
                        if current["cancel_requested"]
                        else "failed"
                    )
                    self.store.transition_job(
                        job_id,
                        terminal,
                        expected_status="running",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            except Exception as terminal_exc:
                primary_message = str(exc).replace("\r", " ").replace("\n", " ")[:500]
                terminal_message = (
                    str(terminal_exc).replace("\r", " ").replace("\n", " ")[:500]
                )
                LOGGER.error(
                    "job terminal transition persistence failed "
                    "job_id=%s primary_exception=%s primary_message=%s "
                    "terminal_exception=%s terminal_message=%s timestamp=%s",
                    job_id,
                    type(exc).__name__,
                    primary_message,
                    type(terminal_exc).__name__,
                    terminal_message,
                    datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                )
        finally:
            with self._queue_lock:
                self._active_cancel.pop(job_id, None)
                self._active_executor.pop(job_id, None)

    def route(self, text: str, override: str | None) -> RoutingDecision:
        normalized_override = None
        if override is not None and str(override).strip().upper() != "AUTO":
            normalized_override = str(override)
        return route_query(text, normalized_override)

    def active_job(self, session_id: str) -> dict[str, Any] | None:
        jobs = self.store.list_jobs(
            status=("queued", "running"),
            session_id=session_id,
            limit=1,
        )
        return jobs[0] if jobs else None

    def submit(
        self,
        session_id: str,
        text: str,
        *,
        route_override: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("input must be non-empty text")
        if len(text) > MAX_INPUT_CHARACTERS:
            raise ValueError(
                f"input exceeds {MAX_INPUT_CHARACTERS} character limit"
            )
        self.store.get_session(session_id, include_messages=False)
        decision = self.route(text, route_override)
        if decision.route is not Route.STATUS:
            # SW-27: never run inference on a configuration that exceeds the envelope measured
            # on this machine. STATUS (self-inspection) stays available for remediation.
            qualification = self.qualification()
            if qualification.get("verdict") == "rejected":
                return {
                    "ok": False,
                    "error": (
                        "configuration exceeds the measured qualification envelope: "
                        + "; ".join(qualification.get("reasons") or [])
                    ),
                    "qualification": qualification,
                }, 409
        active = self.active_job(session_id)
        if active is not None:
            return {
                "ok": False,
                "error": "this session already has an active job",
                "job": self.public_job(active),
                **self.public_job(active),
            }, 409

        user_message = self.store.append_message(
            session_id,
            "user",
            text.strip(),
            status="accepted",
            route=decision.route.value,
            metadata={"routing": decision.as_dict()},
        )
        job = self.store.create_job(
            session_id,
            decision.route.value,
            decision.normalized_query or text.strip(),
            input_message_id=user_message["message_id"],
            metadata={"routing": decision.as_dict()},
        )
        self.store.update_job_progress(
            job["job_id"],
            {"percent": 0, "stage": "queued"},
        )
        if decision.route is Route.STATUS:
            return self._run_status_job(job["job_id"], decision.normalized_query), 200
        self._enqueue(job["job_id"])
        public = self.public_job(self.store.get_job(job["job_id"]))
        return {
            "ok": True,
            "job": public,
            **public,
        }, 202

    def _self_state(self) -> dict[str, Any]:
        state = collect_self_state(
            paths=self.paths,
            store=self.store,
            http_get=self.introspection_http_get,
            timeout=self.introspection_timeout,
        )
        store_state = state.get("store")
        if isinstance(store_state, dict):
            summary = store_state.get("summary")
            if isinstance(summary, dict) and "database" in summary:
                summary["database"] = self.paths.pointer(self.paths.db_path)
        return state

    def _self_answer(self, query: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            state = self._self_state()
            return (
                answer_self_query(query, state),
                state,
            )
        except Exception as exc:
            answer = {
                "route": "STATUS",
                "kind": "machine_status",
                "answer": (
                    "SOVEREIGN could not complete a live self-state inspection. "
                    f"The inspection failed as {type(exc).__name__}; no runtime "
                    "facts beyond this failure are asserted."
                ),
                "sources": [],
                "limitations": [
                    "Live machine state was unavailable for this response."
                ],
            }
            return answer, {"inspection_error": type(exc).__name__}

    def _write_status_artifact(
        self,
        *,
        session_id: str,
        job_id: str,
        query: str,
        response: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> str:
        target = (
            self.paths.evidence_dir
            / "status"
            / session_id
            / f"{job_id}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        payload = {
            "schema": "sovereign.status_evidence.v1",
            "session_id": session_id,
            "job_id": job_id,
            "query": query,
            "response": dict(response),
            "self_state": dict(state),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=str,
        )
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return self.paths.pointer(target)

    def _run_status_job(self, job_id: str, query: str) -> dict[str, Any]:
        job = self.store.transition_job(
            job_id,
            "running",
            expected_status="queued",
            worker_id="request:STATUS",
        )
        self.store.update_job_progress(
            job_id,
            {"percent": 25, "stage": "introspection"},
        )
        response, state = self._self_answer(query)
        answer = str(response.get("answer") or "").strip()
        if not answer:
            self.store.transition_job(
                job_id,
                "failed",
                expected_status="running",
                error="deterministic status response was empty",
            )
            public = self.public_job(self.store.get_job(job_id))
            return {"ok": False, "job": public, **public}
        pointer = self._write_status_artifact(
            session_id=str(job["session_id"]),
            job_id=job_id,
            query=query,
            response=response,
            state=state,
        )
        message = self.store.append_message(
            str(job["session_id"]),
            "sovereign",
            answer,
            status="accepted",
            route="STATUS",
            job_id=job_id,
            evidence_pointer=pointer,
            metadata={
                "kind": response.get("kind"),
                "sources": response.get("sources", []),
                "limitations": response.get("limitations", []),
            },
        )
        self.store.update_job_progress(
            job_id,
            {"percent": 100, "stage": "completed"},
        )
        self.store.transition_job(
            job_id,
            "completed",
            expected_status="running",
            evidence_pointer=pointer,
            output_message_id=message["message_id"],
            metadata={
                "deterministic": True,
                "task_tokens": 0,
                "sources": response.get("sources", []),
                "kind": response.get("kind"),
            },
        )
        public = self.public_job(self.store.get_job(job_id))
        return {"ok": True, "job": public, **public}

    @staticmethod
    def _evidence_reference(pointer: str | None) -> dict[str, str] | None:
        if not pointer:
            return None
        return {
            "pointer": pointer,
            "url": f"/v1/evidence?pointer={quote(pointer, safe='')}",
        }

    def public_message(
        self,
        message: Mapping[str, Any],
        *,
        job_status: str | None = None,
        job: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "id": str(message["message_id"]),
            "message_id": str(message["message_id"]),
            "session_id": str(message["session_id"]),
            "role": str(message["role"]),
            "content": str(message["content"]),
            "timestamp": str(message["created_at"]),
            "created_at": str(message["created_at"]),
            "status": str(message.get("status") or "accepted"),
            "route": message.get("route"),
            "job_id": message.get("job_id"),
        }
        if job_status is not None:
            result["job_status"] = job_status
        if job is not None:
            metrics = _job_metrics(job)
            if metrics is not None:
                result["metrics"] = metrics
        evidence = self._evidence_reference(message.get("evidence_pointer"))
        if evidence is not None:
            result["evidence"] = evidence
            result["evidence_pointer"] = evidence["pointer"]
            result["evidence_url"] = evidence["url"]
        return result

    def public_job(self, job: Mapping[str, Any]) -> dict[str, Any]:
        status = str(job["status"])
        progress = _safe_progress(
            job.get("progress"),
            fallback_stage=status,
        )
        if status == "completed":
            progress["percent"] = 100
            progress["stage"] = "completed"
        result: dict[str, Any] = {
            "job_id": str(job["job_id"]),
            "session_id": str(job["session_id"]),
            "route": str(job["route"]),
            "status": status,
            "progress": progress,
            "error": job.get("error"),
            "cancel_requested": bool(job.get("cancel_requested")),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "updated_at": job.get("updated_at"),
        }
        metrics = _job_metrics(job)
        if metrics is not None:
            result["metrics"] = metrics
        evidence = self._evidence_reference(job.get("evidence_pointer"))
        if evidence is not None:
            result["evidence"] = evidence
            result["evidence_pointer"] = evidence["pointer"]
            result["evidence_url"] = evidence["url"]
        output_id = job.get("output_message_id")
        if status == "completed" and output_id:
            try:
                message = self.store.get_message(str(output_id))
            except NotFound:
                result["error"] = "completed job output message is missing"
            else:
                if (
                    message.get("job_id") == job.get("job_id")
                    and message.get("session_id") == job.get("session_id")
                    and message.get("role") == "sovereign"
                ):
                    result["message"] = self.public_message(
                        message,
                        job_status="completed",
                        job=job,
                    )
                else:
                    result["error"] = (
                        "completed job output attribution failed validation"
                    )
        return result

    def public_session(self, session: Mapping[str, Any]) -> dict[str, Any]:
        session_id = str(session["session_id"])
        jobs = self.store.list_jobs(session_id=session_id, limit=500)
        jobs_by_id = {str(job["job_id"]): job for job in jobs}
        messages: list[dict[str, Any]] = []
        for message in self.store.list_messages(session_id):
            role = str(message.get("role"))
            if role == "user":
                messages.append(self.public_message(message))
                continue
            if role != "sovereign":
                continue
            linked = jobs_by_id.get(str(message.get("job_id") or ""))
            if linked is None or linked["status"] != "completed":
                # A crash between message append and terminal transition can
                # never expose an uncommitted answer.
                continue
            if linked.get("output_message_id") != message.get("message_id"):
                continue
            messages.append(
                self.public_message(
                    message,
                    job_status="completed",
                    job=linked,
                )
            )
        active = next(
            (job for job in jobs if job["status"] in _ACTIVE_STATES),
            None,
        )
        last = jobs[0] if jobs else None
        result: dict[str, Any] = {
            "session_id": session_id,
            "title": str(session["title"]),
            "created_at": str(session["created_at"]),
            "updated_at": str(session["updated_at"]),
            "active_model_profile": str(session["active_model_profile"]),
            "orchestration_mode": str(session["orchestration_mode"]),
            "messages": messages,
        }
        if active is not None:
            result["active_job_id"] = str(active["job_id"])
            result["active_job"] = self.public_job(active)
        if last is not None:
            result["last_job"] = self.public_job(last)
        for message in reversed(messages):
            evidence = message.get("evidence")
            if isinstance(evidence, Mapping):
                result["evidence"] = dict(evidence)
                result["evidence_pointer"] = evidence.get("pointer")
                result["evidence_url"] = evidence.get("url")
                break
        return result

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.request_cancel(job_id)
        if job["status"] == "running":
            with self._queue_lock:
                event = self._active_cancel.get(job_id)
                executor = self._active_executor.get(job_id)
            if event is not None:
                event.set()
            cancel = getattr(executor, "cancel", None)
            if callable(cancel):
                try:
                    cancel(str(job["session_id"]))
                except Exception:
                    pass
            job = self.store.get_job(job_id)
        return self.public_job(job)

    def models(self) -> list[dict[str, Any]]:
        state = self._self_state()
        _service_label, model_service = model_service_authority(state)
        configured_roles = (
            state.get("manifest", {}).get("configured_models_by_role", {})
            if isinstance(state.get("manifest"), Mapping)
            else {}
        )
        configured_roles = (
            configured_roles if isinstance(configured_roles, Mapping) else {}
        )
        installed_raw = model_service.get("installed_models")
        loaded_raw = model_service.get("loaded_models")
        installed = (
            {str(item) for item in installed_raw}
            if isinstance(installed_raw, list)
            else None
        )
        loaded = (
            {str(item) for item in loaded_raw}
            if isinstance(loaded_raw, list)
            else None
        )
        names = {
            str(model)
            for model in configured_roles.values()
            if isinstance(model, str)
        }
        if installed is not None:
            names.update(installed)
        result: list[dict[str, Any]] = []
        for name in sorted(names):
            roles = sorted(
                str(role)
                for role, model in configured_roles.items()
                if model == name
            )
            status = (
                "unknown"
                if installed is None
                else ("available" if name in installed else "unavailable")
            )
            result.append(
                {
                    "id": name,
                    "name": name,
                    "source": "local",
                    "status": status,
                    "configured_roles": roles,
                    "installed": None if installed is None else name in installed,
                    "loaded": None if loaded is None else name in loaded,
                }
            )
        return result

    def profile(self) -> dict[str, Any]:
        models = self._manifest().get("MODELS")
        assignments = []
        if isinstance(models, Mapping):
            assignments = [
                {"role": str(role), "modelId": str(model)}
                for role, model in sorted(models.items())
                if isinstance(model, str)
            ]
        return {
            "name": "manifest-default",
            "assignments": assignments,
            "source": "sovereign://SYSTEM_MANIFEST.json",
            "mutable": True,
            "editableRoles": list(CONFIGURABLE_MODEL_ROLES),
            "restartRequired": False,
        }

    def update_model_assignments(
        self,
        raw: Mapping[str, Any],
    ) -> dict[str, Any]:
        unknown = sorted(set(raw) - {"assignments"})
        if unknown:
            raise ValueError(
                f"unknown model assignment field(s): {', '.join(unknown)}"
            )
        submitted = raw.get("assignments")
        if not isinstance(submitted, list) or not submitted:
            raise ValueError("assignments must be a non-empty list")

        updates: dict[str, str] = {}
        for item in submitted:
            if not isinstance(item, Mapping):
                raise ValueError("each model assignment must be an object")
            item_unknown = sorted(set(item) - {"role", "modelId"})
            if item_unknown:
                raise ValueError(
                    "unknown model assignment field(s): "
                    + ", ".join(item_unknown)
                )
            role = item.get("role")
            model_id = item.get("modelId")
            if role not in CONFIGURABLE_MODEL_ROLES:
                if role == "EMBEDDING_MODEL":
                    raise ValueError(
                        "EMBEDDING_MODEL is read-only because the local registry "
                        "does not expose reliable embedding compatibility metadata"
                    )
                raise ValueError(f"unsupported configurable model role: {role}")
            if role in updates:
                raise ValueError(f"duplicate model assignment role: {role}")
            if (
                not isinstance(model_id, str)
                or not model_id.strip()
                or len(model_id) > 512
            ):
                raise ValueError("modelId must be non-empty bounded text")
            updates[str(role)] = model_id.strip()

        state = self._self_state()
        _service_label, model_service = model_service_authority(state)
        installed_raw = model_service.get("installed_models")
        if not isinstance(installed_raw, list):
            raise ValueError(
                "local model inventory is unavailable; assignments were not changed"
            )
        installed = {str(item) for item in installed_raw}
        missing = sorted(set(updates.values()) - installed)
        if missing:
            raise ValueError(
                "model assignment rejected; model is not installed: "
                + ", ".join(missing)
            )

        with self._configuration_lock:
            manifest = self._manifest()
            models = manifest.get("MODELS")
            if not isinstance(models, Mapping):
                raise ValueError("SYSTEM_MANIFEST MODELS configuration is unavailable")
            updated_models = dict(models)
            updated_models.update(updates)
            updated_manifest = dict(manifest)
            updated_manifest["MODELS"] = updated_models
            replacement_deep = (
                None
                if self._injected_deep_executor is not None
                else self._deep_executor_from_manifest(updated_manifest)
            )
            self._write_model_overrides(updates)
            if replacement_deep is not None:
                self.deep_executor = replacement_deep
        return self.profile()

    def settings(self) -> dict[str, Any]:
        return self.store.get_meta_validated_recovering(
            SETTINGS_META_KEY,
            DEFAULT_SETTINGS,
            _normalize_settings,
        )

    def update_settings(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        current = self.settings()
        validated = _validate_settings({**current, **dict(raw)})
        self.store.set_meta(SETTINGS_META_KEY, validated)
        return validated


def create_app(
    root: str | Path | None = None,
    *,
    service: ProductService | None = None,
    **service_kwargs: Any,
) -> Flask:
    """Create the same-origin Flask application."""

    owned_service = service or ProductService(root, **service_kwargs)
    app = Flask(__name__, static_folder=None)
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_JSON_BYTES,
        JSON_SORT_KEYS=True,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.extensions["sovereign_service"] = owned_service

    @app.before_request
    def enforce_local_boundary() -> tuple[Response, int] | None:
        host_header = request.headers.get("Host", "")
        if _host_authority(host_header) is None:
            return _json_error("untrusted Host header", 403)
        if request.method in _MUTATION_METHODS:
            if request.mimetype != "application/json":
                return _json_error(
                    "mutating requests require application/json",
                    415,
                )
            fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
            if fetch_site and fetch_site not in {"same-origin", "none"}:
                return _json_error("cross-origin mutation rejected", 403)
            origin = request.headers.get("Origin")
            if origin and not _same_origin(
                origin,
                host_header,
                request.scheme,
            ):
                return _json_error("cross-origin mutation rejected", 403)
            referer = request.headers.get("Referer")
            if not origin and referer:
                parsed = urlsplit(referer)
                referer_origin = (
                    f"{parsed.scheme}://{parsed.netloc}"
                    if parsed.scheme and parsed.netloc
                    else ""
                )
                if not _same_origin(
                    referer_origin,
                    host_header,
                    request.scheme,
                ):
                    return _json_error("cross-origin mutation rejected", 403)
        return None

    @app.after_request
    def harden_response(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
        # Deliberately do not emit Access-Control-Allow-*.
        return response

    @app.errorhandler(413)
    def too_large(_error: Exception) -> tuple[Response, int]:
        return _json_error(
            f"request exceeds {MAX_JSON_BYTES} byte limit",
            413,
        )

    @app.errorhandler(NotFound)
    def store_not_found(error: NotFound) -> tuple[Response, int]:
        return _json_error(str(error), 404)

    @app.errorhandler(ValueError)
    def invalid_value(error: ValueError) -> tuple[Response, int]:
        return _json_error(str(error), 400)

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> tuple[Response, int]:
        return _json_error(error.description, int(error.code or 500))

    @app.errorhandler(Exception)
    def internal_error(_error: Exception) -> tuple[Response, int]:
        return _json_error("internal service error", 500)

    def json_object() -> Mapping[str, Any]:
        payload = request.get_json(silent=False)
        if not isinstance(payload, Mapping):
            raise ValueError("JSON body must be an object")
        return payload

    @app.get("/v1/health")
    def health() -> Response:
        store_ok = True
        detail: list[str] = []
        try:
            owned_service.store.quick_check()
        except Exception:
            store_ok = False
            detail.append("durable store integrity check failed")
        try:
            owned_service._manifest()
            manifest_ok = True
        except ServiceConfigurationError:
            manifest_ok = False
        legacy_runner_present = (owned_service.root / "cycle_runner_v3.py").is_file()
        deep_target = getattr(owned_service.deep_executor, "execute", None)
        deep_ok = callable(deep_target) or callable(owned_service.deep_executor)
        deep_engine = (
            type(owned_service.deep_executor).__module__
            + "."
            + type(owned_service.deep_executor).__name__
        )
        deep_model_slate = getattr(
            owned_service.deep_executor,
            "model_slate",
            None,
        )
        if not manifest_ok:
            detail.append("system manifest missing")
        if not deep_ok:
            detail.append("configured DEEP executor is not callable")
        worker_ok = (
            len(owned_service._workers) == owned_service.worker_count
            and all(thread.is_alive() for thread in owned_service._workers)
        )
        if not worker_ok:
            detail.append("durable job workers are not ready")
        try:
            state = owned_service._self_state()
            _service_label, model_service = model_service_authority(state)
            model_service_ok = bool(model_service.get("reachable"))
            configured = {
                str(item) for item in (model_service.get("configured_models") or [])
            }
            installed_raw = model_service.get("installed_models")
            installed = (
                {str(item) for item in installed_raw}
                if isinstance(installed_raw, list)
                else set()
            )
            missing_models = sorted(configured - installed)
            models_ok = model_service_ok and not missing_models
            constitution = (
                state.get("constitution")
                if isinstance(state.get("constitution"), Mapping)
                else {}
            )
            mode = str(constitution.get("mode") or "UNKNOWN")
        except Exception:
            model_service_ok = False
            models_ok = False
            missing_models = []
            mode = "UNKNOWN"
            detail.append("live self-state inspection failed")
        if not model_service_ok:
            detail.append("loopback model service is unavailable")
        elif missing_models:
            detail.append(
                "configured model(s) not installed: "
                + ", ".join(missing_models)
            )
        research_ok = owned_service.research_executor is not None
        if not research_ok:
            detail.append(
                owned_service.research_unavailable_reason
                or "research executor is unavailable"
            )
        qualification = owned_service.qualification()
        qualification_ok = qualification.get("verdict") != "rejected"
        if not qualification_ok:
            detail.append(
                "qualification: "
                + "; ".join(qualification.get("reasons") or ["rejected"])
            )
        ready = all(
            (
                store_ok,
                manifest_ok,
                deep_ok,
                worker_ok,
                models_ok,
                research_ok,
                qualification_ok,
            )
        )
        status = "ok" if ready else "degraded"
        return jsonify(
            {
                "ok": ready,
                "status": status,
                "product_version": PRODUCT_VERSION,
                "engine_version": PRODUCT_VERSION,
                "orchestration_mode": mode,
                "loopback_only": True,
                "same_origin": True,
                "durable_store": store_ok,
                "worker_count": len(owned_service._workers),
                "workers_ready": worker_ok,
                "model_service_reachable": model_service_ok,
                "configured_models_ready": models_ok,
                "missing_configured_models": missing_models,
                "research_ready": research_ok,
                "deep_engine": deep_engine,
                "deep_model_slate": (
                    deep_model_slate
                    if isinstance(deep_model_slate, Mapping)
                    else None
                ),
                "legacy_cycle_runner_present": legacy_runner_present,
                "qualification": qualification,
                "routes": {
                    "STATUS": True,
                    "QUICK": models_ok,
                    "CONTINUITY": models_ok,
                    "DEEP": deep_ok and models_ok,
                    "RESEARCH": research_ok and models_ok,
                },
                "detail": "; ".join(detail) if detail else "ready",
            }
        )

    @app.get("/v1/status")
    def status() -> Response:
        state = owned_service._self_state()
        return jsonify({"status": "ok", **status_answer(state)})

    @app.get("/v1/self-state")
    def self_state() -> Response:
        return jsonify(owned_service._self_state())

    @app.get("/v1/models")
    def models() -> Response:
        return jsonify({"models": owned_service.models()})

    @app.get("/v1/models/profile")
    def model_profile() -> Response:
        return jsonify({"profile": owned_service.profile()})

    @app.post("/v1/models/active")
    def active_models() -> Response:
        profile = owned_service.update_model_assignments(json_object())
        return jsonify({"ok": True, "profile": profile})

    @app.get("/v1/settings")
    def get_settings() -> Response:
        return jsonify({"settings": owned_service.settings()})

    @app.put("/v1/settings")
    def put_settings() -> Response:
        settings = owned_service.update_settings(json_object())
        return jsonify({"ok": True, "settings": settings})

    @app.post("/v1/sessions")
    def create_session() -> tuple[Response, int]:
        payload = json_object()
        allowed = {
            "session_id",
            "title",
            "active_model_profile",
            "orchestration_mode",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(
                f"unknown session field(s): {', '.join(unknown)}"
            )
        title = payload.get("title", "New chat")
        if not isinstance(title, str) or len(title) > MAX_TITLE_CHARACTERS:
            raise ValueError("title must be bounded text")
        session = owned_service.store.create_session(
            payload.get("session_id"),
            title=title,
            active_model_profile=str(
                payload.get("active_model_profile", "default")
            ),
            orchestration_mode=str(
                payload.get("orchestration_mode", "AUTO")
            ),
        )
        return jsonify(
            {"session": owned_service.public_session(session)}
        ), 201

    @app.get("/v1/sessions")
    def list_sessions() -> Response:
        try:
            limit = int(request.args.get("limit", "200"))
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
        sessions = [
            owned_service.public_session(session)
            for session in owned_service.store.list_sessions(limit=limit)
        ]
        return jsonify({"sessions": sessions})

    @app.get("/v1/sessions/<session_id>")
    def get_session(session_id: str) -> Response:
        session = owned_service.store.get_session(
            session_id,
            include_messages=False,
        )
        return jsonify({"session": owned_service.public_session(session)})

    @app.delete("/v1/sessions/<session_id>")
    def delete_session(session_id: str) -> Response | tuple[Response, int]:
        json_object()
        active = owned_service.active_job(session_id)
        if active is not None:
            return _json_error(
                "cannot delete a session with an active job",
                409,
                job=owned_service.public_job(active),
            )
        if not owned_service.store.delete_session(session_id):
            raise NotFound(f"session not found: {session_id}")
        return jsonify({"ok": True, "session_id": session_id})

    @app.post("/v1/message")
    def message() -> tuple[Response, int]:
        payload = json_object()
        allowed = {"input", "session_id", "route_override"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ValueError(
                f"unknown message field(s): {', '.join(unknown)}"
            )
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be non-empty text")
        text = payload.get("input")
        if not isinstance(text, str):
            raise ValueError("input must be text")
        override = payload.get("route_override")
        if override is not None and not isinstance(override, str):
            raise ValueError("route_override must be text")
        response, status_code = owned_service.submit(
            session_id,
            text,
            route_override=override,
        )
        return jsonify(response), status_code

    @app.get("/v1/jobs")
    def list_jobs() -> Response:
        status_filter = request.args.get("status")
        statuses = (
            [item for item in status_filter.split(",") if item]
            if status_filter
            else None
        )
        try:
            limit = int(request.args.get("limit", "500"))
        except ValueError as exc:
            raise ValueError("limit must be an integer") from exc
        jobs = owned_service.store.list_jobs(
            status=statuses,
            session_id=request.args.get("session_id"),
            limit=limit,
        )
        return jsonify(
            {"jobs": [owned_service.public_job(job) for job in jobs]}
        )

    @app.get("/v1/jobs/<job_id>")
    def get_job(job_id: str) -> Response:
        return jsonify(
            owned_service.public_job(owned_service.store.get_job(job_id))
        )

    @app.post("/v1/jobs/<job_id>/cancel")
    def cancel_job(job_id: str) -> Response:
        json_object()
        return jsonify(owned_service.cancel_job(job_id))

    @app.get("/v1/evidence")
    def evidence() -> Response | tuple[Response, int]:
        pointer = request.args.get("pointer", "")
        if not pointer:
            raise ValueError("pointer is required")
        try:
            path = owned_service.paths.resolve_pointer(
                pointer,
                must_exist=True,
            )
        except UnsafeArtifactPointer as exc:
            return _json_error(str(exc), 400)
        except PathResolutionError as exc:
            return _json_error(str(exc), 404)
        if not path.is_file():
            return _json_error("evidence pointer is not a file", 404)
        mime, _encoding = mimetypes.guess_type(path.name)
        response = send_file(
            path,
            mimetype=mime or "application/octet-stream",
            as_attachment=False,
            conditional=True,
            download_name=path.name,
        )
        response.headers["Content-Disposition"] = (
            f"inline; filename*=UTF-8''{quote(path.name)}"
        )
        return response

    @app.get("/")
    def index() -> Response | tuple[Response, int]:
        index_path = owned_service.ui_dist / "index.html"
        if not index_path.is_file():
            return _json_error("built UI is unavailable", 503)
        return send_file(index_path, mimetype="text/html")

    @app.get("/<path:asset_path>")
    def static_or_spa(asset_path: str) -> Response | tuple[Response, int]:
        if asset_path == "v1" or asset_path.startswith("v1/"):
            return _json_error("API endpoint not found", 404)
        if (
            not asset_path
            or "\\" in asset_path
            or "\x00" in asset_path
            or any(part in {"", ".", ".."} for part in asset_path.split("/"))
        ):
            return _json_error("static path rejected", 404)
        dist = owned_service.ui_dist.resolve(strict=False)
        candidate = (dist / Path(asset_path)).resolve(strict=False)
        try:
            candidate.relative_to(dist)
        except ValueError:
            return _json_error("static path rejected", 404)
        if candidate.is_file():
            return send_file(candidate)
        if Path(asset_path).suffix:
            raise WerkzeugNotFound()
        index_path = dist / "index.html"
        if not index_path.is_file():
            return _json_error("built UI is unavailable", 503)
        return send_file(index_path, mimetype="text/html")

    return app


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the unified local SOVEREIGN product service"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="marker-validated SOVEREIGN install root",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    host = _validate_bind_host(args.host)
    if not 1 <= int(args.port) <= 65_535:
        raise SystemExit("--port must be between 1 and 65535")
    service = ProductService(
        args.root,
        worker_count=args.workers,
    )
    app = create_app(service=service)
    # SW-18: serve through an explicit werkzeug server (what app.run wraps) so the shell's
    # graceful-shutdown Event can stop it: the watcher calls server.shutdown(), serve_forever()
    # returns, and service.close() drains the job workers and closes the store BEFORE the shell's
    # TerminateJobObject fallback would fire.
    from werkzeug.serving import make_server

    server = make_server(host, int(args.port), app, threaded=True)
    install_shutdown_watcher(server.shutdown)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
