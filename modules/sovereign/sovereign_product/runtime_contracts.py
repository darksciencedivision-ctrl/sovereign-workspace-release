from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

from .model_client import (
    GenerationCancelled,
    GenerationTimeout,
    ModelCapabilityError,
    ModelClientError,
    OllamaProtocolError,
    validate_loopback_ollama_url,
)

CancelCallback = Callable[[], bool]
validate_loopback_origin = validate_loopback_ollama_url

CAPABILITY_DECLARED = "declared"
CAPABILITY_SUPPORTED_BY_INTERFACE = "supported_by_interface"
CAPABILITY_EXPERIMENTALLY_DEMONSTRATED = "experimentally_demonstrated"
CAPABILITY_CONSUMER_QUALIFIED = "consumer_qualified"
CAPABILITY_UNSUPPORTED = "unsupported"
CAPABILITY_UNKNOWN = "unknown"
CAPABILITY_STATES = frozenset(
    {
        CAPABILITY_DECLARED,
        CAPABILITY_SUPPORTED_BY_INTERFACE,
        CAPABILITY_EXPERIMENTALLY_DEMONSTRATED,
        CAPABILITY_CONSUMER_QUALIFIED,
        CAPABILITY_UNSUPPORTED,
        CAPABILITY_UNKNOWN,
    }
)

BACKEND_OLLAMA = "ollama"
BACKEND_LLAMA_CPP = "llama.cpp"
BACKEND_FREETOKEN = "freetoken"
DEFAULT_INFERENCE_BACKEND = BACKEND_LLAMA_CPP
DEFAULT_LLAMA_CPP_BASE_URL = "http://127.0.0.1:18080"
DEFAULT_FREETOKEN_BASE_URL = "http://127.0.0.1:1919"


class InferenceProtocolError(OllamaProtocolError):
    """Malformed or incomplete response from a local inference runtime."""


class RuntimeControlError(ModelClientError):
    """Lifecycle or supervisor failure for a local inference runtime."""


class InferenceAuthError(ModelClientError):
    """The local inference runtime refused the API key (HTTP 401/403).

    Never degraded into a fallback: a wrong key fails every call, so callers that
    tolerate other probe failures must re-raise this one.
    """


LLAMA_CPP_KEY_ENV = "SOVEREIGN_LLAMA_CPP_API_KEY"
KEY_SOURCE_SUPERVISOR_FILE = "supervisor key file"
KEY_SOURCE_ENV = LLAMA_CPP_KEY_ENV
KEY_SOURCE_NONE = "none"


def _same_origin(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    try:
        return validate_loopback_origin(left) == validate_loopback_origin(right)
    except (ValueError, ModelClientError):
        return str(left).strip().rstrip("/").lower() == str(right).strip().rstrip("/").lower()


def resolve_llama_cpp_api_key(
    runtime_dir: Any | None,
    base_url: str | None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, str]:
    """The llama.cpp API key for ``base_url`` and where it came from: ``(key, source)``.

    The supervisor in this state home (``<runtime>/llamacpp_supervisor``) was started with
    its ``api_key`` file, so that file is AUTHORITATIVE for the URL that supervisor serves
    (``consumer.env``; a key file without one is taken as serving the configured URL). The
    ``SOVEREIGN_LLAMA_CPP_API_KEY`` variable only carries that same value to consumers, so
    when it disagrees it is stale - e.g. persisted at user level from another state home -
    and must not win. The variable is used for a URL the supervisor does not serve (an
    externally managed server), and as the fallback when this state home has no key file.
    """
    import os
    from pathlib import Path

    environment = os.environ if env is None else env
    env_key = str(environment.get(LLAMA_CPP_KEY_ENV) or "").strip() or None
    file_key: str | None = None
    served_url: str | None = None
    if runtime_dir is not None:
        supervisor_dir = Path(runtime_dir) / "llamacpp_supervisor"
        try:
            file_key = (supervisor_dir / "api_key").read_text(encoding="utf-8").strip() or None
        except OSError:
            file_key = None
        try:
            for line in (supervisor_dir / "consumer.env").read_text(encoding="utf-8").splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() == "SOVEREIGN_LLAMA_CPP_BASE_URL":
                    served_url = value.strip() or None
        except OSError:
            served_url = None
    target = str(base_url or "").strip() or DEFAULT_LLAMA_CPP_BASE_URL
    if file_key and (served_url is None or _same_origin(served_url, target)):
        return file_key, KEY_SOURCE_SUPERVISOR_FILE
    if env_key:
        return env_key, KEY_SOURCE_ENV
    if file_key:
        return file_key, KEY_SOURCE_SUPERVISOR_FILE
    return None, KEY_SOURCE_NONE


@dataclass(frozen=True)
class ChatResponse:
    text: str
    reasoning: str
    model: str
    requested_model: str
    think: bool | None
    finish_reason: str | None
    tool_calls: tuple[dict[str, Any], ...]
    options: dict[str, Any]
    raw_events: tuple[dict[str, Any], ...]
    raw_lines: tuple[str, ...]
    telemetry: dict[str, Any]
    started_monotonic: float
    completed_monotonic: float

    @property
    def latency_seconds(self) -> float:
        return max(0.0, self.completed_monotonic - self.started_monotonic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "reasoning": self.reasoning,
            "model": self.model,
            "requested_model": self.requested_model,
            "think": self.think,
            "finish_reason": self.finish_reason,
            "tool_calls": [dict(call) for call in self.tool_calls],
            "options": dict(self.options),
            "raw_events": [dict(event) for event in self.raw_events],
            "raw_lines": list(self.raw_lines),
            "telemetry": dict(self.telemetry),
            "latency_seconds": self.latency_seconds,
        }


@dataclass(frozen=True)
class RuntimeInventory:
    registered: tuple[str, ...]
    available: tuple[str, ...]
    loaded: tuple[str, ...]
    raw: dict[str, Any] = field(default_factory=dict)


class InferenceClient(Protocol):
    def generate(
        self,
        *,
        model: str,
        prompt: str,
        options: Mapping[str, Any] | None = None,
        cancel_requested: CancelCallback | None = None,
        overall_timeout: float | None = None,
        system: str | None = None,
        think: bool | None = None,
        response_format: str | Mapping[str, Any] | None = None,
    ) -> Any:
        ...

    def chat(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        options: Mapping[str, Any] | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        cancel_requested: CancelCallback | None = None,
        overall_timeout: float | None = None,
        think: bool | None = None,
        response_format: str | Mapping[str, Any] | None = None,
    ) -> ChatResponse:
        ...

    def native_context_length(self, model: str) -> int:
        ...


class RuntimeController(Protocol):
    def start(self) -> None:
        ...

    def ready(self) -> bool:
        ...

    def inventory(self) -> RuntimeInventory:
        ...

    def load(self, model: str) -> dict[str, Any]:
        ...

    def unload(self, model: str) -> dict[str, Any]:
        ...

    def switch(self, model: str) -> dict[str, Any]:
        ...

    def inspect_context(self, model: str) -> dict[str, Any]:
        ...

    def logs(self) -> str:
        ...

    def stop(self) -> None:
        ...

    def recover(self) -> None:
        ...


def normalize_inference_backend(value: str | None) -> str:
    if value is None or not str(value).strip():
        selected = DEFAULT_INFERENCE_BACKEND
    else:
        selected = str(value).strip().lower()
    if selected == BACKEND_OLLAMA:
        return BACKEND_OLLAMA
    if selected in {BACKEND_LLAMA_CPP, "llamacpp", "llama_cpp"}:
        return BACKEND_LLAMA_CPP
    if selected in {BACKEND_FREETOKEN, "free-token", "free_token"}:
        return BACKEND_FREETOKEN
    raise ValueError(f"unsupported inference backend: {value!r}")


def load_default_llama_cpp_api_key(base_url: str | None = None) -> str | None:
    import os

    target = (
        base_url
        or str(os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL") or "").strip()
        or DEFAULT_LLAMA_CPP_BASE_URL
    )
    runtime_dir = None
    try:
        from system_manifest import find_sovereign_root

        from .paths import resolve_runtime_dir

        runtime_dir = resolve_runtime_dir(find_sovereign_root(None))
    except Exception:
        runtime_dir = None
    return resolve_llama_cpp_api_key(runtime_dir, target)[0]


def resolve_selected_backend(backend: str | None = None) -> str:
    """Effective backend for client construction.

    Precedence: explicit argument -> SOVEREIGN_INFERENCE_BACKEND env (explicit
    provider choices preserved) -> persistent runtime/backend_selection.json
    designation -> factory default (llama.cpp). Root resolution failures and
    invalid selection documents degrade to the factory default.
    """
    import os

    if backend is not None and str(backend).strip():
        return normalize_inference_backend(backend)
    env = str(os.environ.get("SOVEREIGN_INFERENCE_BACKEND") or "").strip()
    if env:
        return normalize_inference_backend(env)
    try:
        from system_manifest import find_sovereign_root

        from .backend_selection import resolve_backend

        return resolve_backend(find_sovereign_root(None))
    except Exception:
        return DEFAULT_INFERENCE_BACKEND


def create_generation_client(
    backend: str | None = None,
    **kwargs: Any,
) -> Any:
    import os

    selected = resolve_selected_backend(backend)
    if selected == BACKEND_OLLAMA:
        from .model_client import OllamaClient

        return OllamaClient(**kwargs)
    from .llama_cpp_client import LlamaCppClient

    if "base_url" not in kwargs:
        if selected == BACKEND_FREETOKEN:
            env_url = str(os.environ.get("SOVEREIGN_FREETOKEN_BASE_URL") or "").strip()
            if env_url:
                kwargs["base_url"] = env_url
            else:
                # On-demand activation: a designated FreeToken workload starts
                # the supervisor with its configured profile (GPU ownership
                # transition included) instead of requiring a manual launch.
                from .freetoken_service import ensure_runtime

                kwargs["base_url"] = str(ensure_runtime()["base_url"])
            if "api_key" not in kwargs:
                kwargs["api_key"] = os.environ.get("SOVEREIGN_FREETOKEN_API_KEY") or None
        else:
            kwargs["base_url"] = (
                str(os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL") or "").strip()
                or DEFAULT_LLAMA_CPP_BASE_URL
            )
            if "api_key" not in kwargs:
                kwargs["api_key"] = load_default_llama_cpp_api_key(kwargs["base_url"])
    return LlamaCppClient(**kwargs)
