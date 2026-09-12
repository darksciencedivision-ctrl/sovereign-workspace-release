"""Minimal, local-only Ollama client used by product executors.

The client deliberately has no remote-provider fallback.  A configured base URL
must name a loopback address, redirects are disabled, and generation telemetry is
returned alongside the exact streamed text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import json
import math
import threading
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import requests


CancelCallback = Callable[[], bool]
CONTEXT_TEMPLATE_MARGIN_TOKENS = 512
OLLAMA_CONNECT_TIMEOUT_SECONDS = 30.0
OLLAMA_GENERATION_TIMEOUT_SECONDS = 86_400.0
_CANCELLATION_POLL_SECONDS = 0.05


class ModelClientError(RuntimeError):
    """Base error for local model-client failures."""


class InvalidOllamaURL(ModelClientError, ValueError):
    """Raised when an Ollama URL is not an unambiguous loopback HTTP URL."""


class GenerationCancelled(ModelClientError):
    """Raised when a caller cancels an in-flight generation."""


class GenerationTimeout(ModelClientError, TimeoutError):
    """Raised when a connect, read, or overall generation timeout expires."""

    def __init__(self, timeout_kind: str, message: str | None = None) -> None:
        self.timeout_kind = timeout_kind
        super().__init__(message or f"Ollama {timeout_kind} timeout")


class OllamaProtocolError(ModelClientError):
    """Raised for malformed or incomplete Ollama responses."""


class ModelCapabilityError(ModelClientError):
    """Raised when Ollama cannot report one genuine native context length."""


@dataclass(frozen=True)
class GenerationResponse:
    """Exact generation output plus transport/model telemetry."""

    text: str
    model: str
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
            "model": self.model,
            "options": dict(self.options),
            "raw_events": [dict(event) for event in self.raw_events],
            "raw_lines": list(self.raw_lines),
            "telemetry": dict(self.telemetry),
            "latency_seconds": self.latency_seconds,
        }


@dataclass(frozen=True)
class ModelProbe:
    """One Ollama inventory probe with the unmodified response payload."""

    endpoint: str
    models: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ModelInventory:
    """Installed and currently loaded models, kept as distinct observations."""

    installed: tuple[str, ...]
    loaded: tuple[str, ...]
    installed_raw: dict[str, Any] = field(default_factory=dict)
    loaded_raw: dict[str, Any] = field(default_factory=dict)


def _is_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_loopback_ollama_url(base_url: str) -> str:
    """Validate and normalize a local Ollama URL.

    Hostnames other than the exact name ``localhost`` are not resolved.  This
    avoids accepting a DNS name which happens to resolve locally at validation
    time and could later be rebound.
    """

    if not isinstance(base_url, str) or not base_url.strip():
        raise InvalidOllamaURL("Ollama base URL must be a non-empty string")
    parsed = urlsplit(base_url.strip())
    if parsed.scheme.lower() != "http":
        raise InvalidOllamaURL("Ollama base URL must use http")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidOllamaURL("Ollama base URL must not contain credentials")
    if not _is_loopback_hostname(parsed.hostname):
        raise InvalidOllamaURL("Ollama base URL must use a loopback host")
    if parsed.query or parsed.fragment:
        raise InvalidOllamaURL("Ollama base URL must not contain query or fragment data")
    if parsed.path not in ("", "/"):
        raise InvalidOllamaURL("Ollama base URL must not contain an application path")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidOllamaURL("Ollama base URL contains an invalid port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise InvalidOllamaURL("Ollama base URL contains an invalid port")
    host = parsed.hostname or ""
    formatted_host = f"[{host}]" if ":" in host else host
    authority = f"{formatted_host}:{port}" if port is not None else formatted_host
    return f"http://{authority}"


class OllamaClient:
    """Streaming client for a loopback Ollama server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        *,
        connect_timeout: float = OLLAMA_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = OLLAMA_GENERATION_TIMEOUT_SECONDS,
        overall_timeout: float = OLLAMA_GENERATION_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        for name, value in (
            ("connect_timeout", connect_timeout),
            ("read_timeout", read_timeout),
            ("overall_timeout", overall_timeout),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        self.base_url = validate_loopback_ollama_url(base_url)
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)
        self.overall_timeout = float(overall_timeout)
        if session is not None:
            self._session = session
        else:
            # R23/F-109: this client only ever talks to a validated loopback Ollama. A registry or
            # environment proxy (HTTP_PROXY/HTTPS_PROXY) must never sit between us and 127.0.0.1 -
            # that would route the prompt and completion through a third party. requests honours
            # those env proxies by default; disable that here since we own this session.
            self._session = requests.Session()
            self._session.trust_env = False
        self._monotonic = monotonic

    def _show_model(self, model: str) -> dict[str, Any]:
        """Read Ollama's existing generic metadata for one exact model tag."""

        response: requests.Response | Any | None = None
        try:
            try:
                response = self._session.post(
                    f"{self.base_url}/api/show",
                    json={"model": model},
                    timeout=(
                        min(self.connect_timeout, self.overall_timeout),
                        min(self.read_timeout, self.overall_timeout),
                    ),
                    allow_redirects=False,
                )
            except requests.ConnectTimeout as exc:
                raise GenerationTimeout("connect") from exc
            except requests.ReadTimeout as exc:
                raise GenerationTimeout("read") from exc
            except requests.Timeout as exc:
                raise GenerationTimeout("transport") from exc
            except requests.RequestException as exc:
                raise ModelClientError(f"Ollama model-info probe failed: {exc}") from exc
            if 300 <= int(getattr(response, "status_code", 0)) < 400:
                raise ModelClientError("Ollama redirects are not permitted")
            try:
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise ModelClientError(
                    f"Ollama model-info probe returned an HTTP error: {exc}"
                ) from exc
            except (ValueError, json.JSONDecodeError) as exc:
                raise OllamaProtocolError(
                    "Ollama model-info probe returned invalid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise OllamaProtocolError(
                    "Ollama model-info probe payload must be a JSON object"
                )
            return dict(payload)
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

    def native_context_length(self, model: str) -> int:
        """Return the unguessed native context from generic Ollama metadata."""

        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        payload = self._show_model(model.strip())
        model_info = payload.get("model_info")
        if not isinstance(model_info, Mapping):
            raise ModelCapabilityError(
                f"native context capability is unknown for model {model!r}: "
                "Ollama /api/show omitted model_info"
            )
        candidates: set[int] = set()
        for key, value in model_info.items():
            field = str(key).casefold().rsplit(".", 1)[-1]
            if field not in {"context_length", "context_window"}:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ModelCapabilityError(
                    f"native context capability is invalid for model {model!r}"
                )
            candidates.add(value)
        if len(candidates) != 1:
            detail = "missing" if not candidates else "conflicting"
            raise ModelCapabilityError(
                f"native context capability is {detail} for model {model!r}"
            )
        return candidates.pop()

    @staticmethod
    def _conservative_input_bound(
        prompt: str,
        *,
        system: str | None,
        response_format: str | Mapping[str, Any] | None,
    ) -> int:
        material = prompt.encode("utf-8")
        if system is not None:
            material += system.encode("utf-8")
        if response_format is not None:
            material += json.dumps(
                response_format,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        # One UTF-8 byte per token is conservative for ordinary tokenizers.
        return len(material)

    def _resolve_generation_capacity(
        self,
        *,
        model: str,
        prompt: str,
        options: Mapping[str, Any],
        system: str | None,
        response_format: str | Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        resolved = dict(options)
        if "num_ctx" not in resolved or "num_predict" not in resolved:
            return resolved, {}
        requested_context = resolved["num_ctx"]
        requested_generation = resolved["num_predict"]
        if (
            isinstance(requested_context, bool)
            or not isinstance(requested_context, int)
            or requested_context <= 0
        ):
            raise ValueError("options.num_ctx must be a positive integer")
        if (
            isinstance(requested_generation, bool)
            or not isinstance(requested_generation, int)
            or requested_generation <= 0
        ):
            raise ValueError("options.num_predict must be a positive integer")
        native_context = self.native_context_length(model)
        effective_context = min(requested_context, native_context)
        input_bound = self._conservative_input_bound(
            prompt,
            system=system,
            response_format=response_format,
        )
        remaining_generation = (
            effective_context - input_bound - CONTEXT_TEMPLATE_MARGIN_TOKENS
        )
        if remaining_generation <= 0:
            raise ModelCapabilityError(
                f"input bound ({input_bound}) plus safety allowance "
                f"({CONTEXT_TEMPLATE_MARGIN_TOKENS}) leaves no generation capacity "
                f"inside effective context {effective_context} for model {model!r}"
            )
        effective_generation = min(requested_generation, remaining_generation)
        resolved["num_ctx"] = effective_context
        resolved["num_predict"] = effective_generation
        return resolved, {
            "native_context": native_context,
            "effective_context": effective_context,
            "input_bound": input_bound,
            "context_safety_allowance": CONTEXT_TEMPLATE_MARGIN_TOKENS,
            "remaining_generation_capacity": remaining_generation,
            "effective_generation_max": effective_generation,
        }

    def resolve_generation_options(
        self,
        *,
        model: str,
        prompt: str,
        options: Mapping[str, Any],
        system: str | None = None,
        response_format: str | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply model-native context and physical output-fit bounds."""

        resolved, _ = self._resolve_generation_capacity(
            model=model,
            prompt=prompt,
            options=options,
            system=system,
            response_format=response_format,
        )
        return resolved

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
    ) -> GenerationResponse:
        """Stream one Ollama generation and return exact text and raw events."""

        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        timeout_limit = self.overall_timeout if overall_timeout is None else float(overall_timeout)
        if timeout_limit <= 0:
            raise ValueError("overall_timeout must be positive")
        cancellation = cancel_requested or (lambda: False)
        if cancellation():
            raise GenerationCancelled("generation cancelled before request")

        request_options = dict(options or {})
        requested_format: str | dict[str, Any] | None
        if response_format is None:
            requested_format = None
        elif isinstance(response_format, str):
            if response_format != "json":
                raise ValueError("response_format text must be exactly 'json'")
            requested_format = response_format
        elif isinstance(response_format, Mapping):
            requested_format = dict(response_format)

            def validate_json_value(value: Any) -> None:
                if value is None or isinstance(value, (str, bool, int)):
                    return
                if isinstance(value, float):
                    if not math.isfinite(value):
                        raise ValueError(
                            "response_format schema must contain finite JSON values"
                        )
                    return
                if isinstance(value, list):
                    for item in value:
                        validate_json_value(item)
                    return
                if isinstance(value, dict):
                    for key, item in value.items():
                        if not isinstance(key, str):
                            raise ValueError(
                                "response_format schema keys must be strings"
                            )
                        validate_json_value(item)
                    return
                raise ValueError(
                    "response_format schema must contain only JSON-compatible values"
                )

            validate_json_value(requested_format)
        else:
            raise TypeError(
                "response_format must be 'json', a JSON schema mapping, or None"
            )
        request_options, capacity = self._resolve_generation_capacity(
            model=model,
            prompt=prompt,
            options=request_options,
            system=system,
            response_format=requested_format,
        )
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": request_options,
        }
        if system is not None:
            payload["system"] = system
        if think is not None:
            if not isinstance(think, bool):
                raise TypeError("think must be a boolean or None")
            # Ollama's thinking control is a top-level request field, not a
            # model option.  Keeping it out of ``options`` also makes the
            # requested mode unambiguous in captured telemetry.
            payload["think"] = think
        if requested_format is not None:
            payload["format"] = requested_format

        started = self._monotonic()
        connect_budget = min(self.connect_timeout, timeout_limit)
        read_budget = min(self.read_timeout, timeout_limit)
        response: requests.Response | Any | None = None
        raw_events: list[dict[str, Any]] = []
        raw_lines: list[str] = []
        text_parts: list[str] = []
        saw_done = False
        abort_observed = threading.Event()
        abort_watcher_stop = threading.Event()

        def close_active_response() -> None:
            current = response
            if current is None:
                return
            close = getattr(current, "close", None)
            if callable(close):
                close()

        def watch_for_cancellation() -> None:
            while not abort_watcher_stop.wait(_CANCELLATION_POLL_SECONDS):
                if cancellation():
                    abort_observed.set()
                    close_active_response()
                    return

        abort_watcher = threading.Thread(
            target=watch_for_cancellation,
            name="sovereign-ollama-call-cancellation",
            daemon=True,
        )
        abort_watcher.start()
        try:
            try:
                response = self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    stream=True,
                    timeout=(connect_budget, read_budget),
                    allow_redirects=False,
                )
            except requests.ConnectTimeout as exc:
                raise GenerationTimeout("connect") from exc
            except requests.ReadTimeout as exc:
                raise GenerationTimeout("read") from exc
            except requests.Timeout as exc:
                raise GenerationTimeout("transport") from exc
            except requests.RequestException as exc:
                raise ModelClientError(f"Ollama request failed: {exc}") from exc

            if abort_observed.is_set() or cancellation():
                abort_observed.set()
                close_active_response()
                raise GenerationCancelled("generation cancelled")

            if 300 <= int(getattr(response, "status_code", 0)) < 400:
                raise ModelClientError("Ollama redirects are not permitted")
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise ModelClientError(f"Ollama returned an HTTP error: {exc}") from exc

            try:
                line_iterator = response.iter_lines(decode_unicode=True)
                for raw_line in line_iterator:
                    now = self._monotonic()
                    if now - started > timeout_limit:
                        raise GenerationTimeout("overall")
                    if abort_observed.is_set() or cancellation():
                        raise GenerationCancelled("generation cancelled")
                    if raw_line is None:
                        continue
                    if isinstance(raw_line, bytes):
                        line = raw_line.decode("utf-8", errors="strict")
                    else:
                        line = str(raw_line)
                    if not line.strip():
                        continue
                    raw_lines.append(line)
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaProtocolError("Ollama emitted invalid streaming JSON") from exc
                    if not isinstance(event, dict):
                        raise OllamaProtocolError("Ollama streaming event must be a JSON object")
                    raw_events.append(dict(event))
                    if event.get("error"):
                        raise ModelClientError(f"Ollama generation error: {event['error']}")
                    chunk = event.get("response", "")
                    if not isinstance(chunk, str):
                        raise OllamaProtocolError("Ollama response chunk must be text")
                    try:
                        chunk.encode("utf-8", errors="strict")
                    except UnicodeEncodeError as exc:
                        raise OllamaProtocolError(
                            "Ollama response chunk contains invalid Unicode"
                        ) from exc
                    text_parts.append(chunk)
                    if event.get("done") is True:
                        saw_done = True
                        break
            except requests.ReadTimeout as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                raise GenerationTimeout("read") from exc
            except requests.ConnectionError as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                # urllib3 may wrap a streaming read timeout as ConnectionError.
                if "timed out" in str(exc).lower():
                    raise GenerationTimeout("read") from exc
                raise ModelClientError(f"Ollama stream failed: {exc}") from exc
            except requests.RequestException as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                # requests surfaces truncated chunked bodies and content-decoding
                # failures while iterating the response, after the HTTP request
                # itself has succeeded. Normalize every such streaming failure so
                # the outer ModelClientError handler can attach all text, events,
                # and raw lines observed before the wire failed.
                raise ModelClientError(f"Ollama stream failed: {exc}") from exc
            except UnicodeError as exc:
                # A malformed byte sequence can be yielded when the response has
                # no usable charset, while requests' own decoder can also raise a
                # UnicodeError. Both are protocol failures, not bare exceptions:
                # retaining that classification preserves the observed partial.
                raise OllamaProtocolError(
                    "Ollama stream emitted invalid UTF-8"
                ) from exc
            except Exception as exc:
                # Closing a Requests response from the cancellation watcher can
                # surface an implementation-level iterator error (for example,
                # its raw stream becoming None) instead of RequestException.
                # Normalize only a cancellation-observed failure; unrelated
                # iterator defects remain visible to their caller.
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                raise

            completed = self._monotonic()
            if completed - started > timeout_limit:
                raise GenerationTimeout("overall")
            if abort_observed.is_set() or cancellation():
                raise GenerationCancelled("generation cancelled")
            if not saw_done:
                raise OllamaProtocolError("Ollama stream ended without a done event")

            terminal = raw_events[-1] if raw_events else {}
            terminal_model = terminal.get("model")
            if not isinstance(terminal_model, str) or not terminal_model.strip():
                raise OllamaProtocolError(
                    "Ollama terminal event omitted a non-empty model identity"
                )
            telemetry = {
                key: value
                for key, value in terminal.items()
                if key
                not in {
                    "response",
                    "context",
                    "model",
                    "done",
                    "done_reason",
                }
            }
            telemetry.update(
                {
                    "done": terminal.get("done"),
                    "done_reason": terminal.get("done_reason"),
                    "event_count": len(raw_events),
                    "requested_model": model,
                    "requested_think": think,
                    "requested_response_format": requested_format,
                    "reported_model": terminal_model,
                    "connect_timeout_seconds": self.connect_timeout,
                    "read_timeout_seconds": self.read_timeout,
                    "overall_timeout_seconds": timeout_limit,
                    "effective_connect_timeout_seconds": connect_budget,
                    "effective_read_timeout_seconds": read_budget,
                    **capacity,
                }
            )
            return GenerationResponse(
                text="".join(text_parts),
                model=terminal_model,
                options=request_options,
                raw_events=tuple(raw_events),
                raw_lines=tuple(raw_lines),
                telemetry=telemetry,
                started_monotonic=started,
                completed_monotonic=completed,
            )
        except ModelClientError as exc:
            terminal = raw_events[-1] if raw_events else {}
            partial_telemetry = {
                "done": terminal.get("done"),
                "done_reason": terminal.get("done_reason"),
                "event_count": len(raw_events),
                "requested_model": model,
                "reported_model": terminal.get("model"),
                "requested_think": think,
                "requested_response_format": requested_format,
                "overall_timeout_seconds": timeout_limit,
                "failure_type": type(exc).__name__,
                "failure": str(exc),
            }
            # Exceptions retain every byte successfully observed before the
            # failure. Callers can therefore preserve cancellation, timeout,
            # protocol, and transport partials without presenting them as an
            # accepted answer.
            setattr(
                exc,
                "partial_response",
                {
                    "text": "".join(text_parts),
                    "model": terminal.get("model"),
                    "options": dict(request_options),
                    "raw_events": [dict(event) for event in raw_events],
                    "raw_lines": list(raw_lines),
                    "telemetry": partial_telemetry,
                    "latency_seconds": max(0.0, self._monotonic() - started),
                },
            )
            raise
        finally:
            abort_watcher_stop.set()
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            abort_watcher.join(timeout=0.2)

    def _probe(self, endpoint: str) -> ModelProbe:
        started = self._monotonic()
        try:
            response = self._session.get(
                f"{self.base_url}{endpoint}",
                timeout=(
                    min(self.connect_timeout, self.overall_timeout),
                    min(self.read_timeout, self.overall_timeout),
                ),
                allow_redirects=False,
            )
        except requests.ConnectTimeout as exc:
            raise GenerationTimeout("connect") from exc
        except requests.ReadTimeout as exc:
            raise GenerationTimeout("read") from exc
        except requests.Timeout as exc:
            raise GenerationTimeout("transport") from exc
        except requests.RequestException as exc:
            raise ModelClientError(f"Ollama probe failed: {exc}") from exc
        try:
            if 300 <= int(getattr(response, "status_code", 0)) < 400:
                raise ModelClientError("Ollama redirects are not permitted")
            try:
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise ModelClientError(f"Ollama probe returned an HTTP error: {exc}") from exc
            except (ValueError, json.JSONDecodeError) as exc:
                raise OllamaProtocolError("Ollama probe returned invalid JSON") from exc
            if self._monotonic() - started > self.overall_timeout:
                raise GenerationTimeout("overall")
            if not isinstance(payload, dict):
                raise OllamaProtocolError("Ollama probe payload must be a JSON object")
            names: set[str] = set()
            raw_models = payload.get("models", [])
            if not isinstance(raw_models, list):
                raise OllamaProtocolError("Ollama models field must be a list")
            for entry in raw_models:
                if not isinstance(entry, Mapping):
                    continue
                candidate = entry.get("name") or entry.get("model")
                if isinstance(candidate, str) and candidate.strip():
                    names.add(candidate.strip())
            return ModelProbe(endpoint=endpoint, models=tuple(sorted(names)), raw=dict(payload))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def probe_installed(self) -> ModelProbe:
        """Probe models installed in Ollama's local inventory."""

        return self._probe("/api/tags")

    def probe_loaded(self) -> ModelProbe:
        """Probe models currently loaded in Ollama memory."""

        return self._probe("/api/ps")

    def installed_models(self) -> tuple[str, ...]:
        return self.probe_installed().models

    def loaded_models(self) -> tuple[str, ...]:
        return self.probe_loaded().models

    def probe_models(self) -> ModelInventory:
        installed = self.probe_installed()
        loaded = self.probe_loaded()
        return ModelInventory(
            installed=installed.models,
            loaded=loaded.models,
            installed_raw=installed.raw,
            loaded_raw=loaded.raw,
        )
