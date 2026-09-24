from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence
import json
import math
import threading
import time

import requests

from .model_client import (
    CONTEXT_TEMPLATE_MARGIN_TOKENS,
    GenerationCancelled,
    GenerationResponse,
    GenerationTimeout,
    ModelCapabilityError,
    ModelClientError,
    ModelInventory,
    ModelProbe,
    OLLAMA_CONNECT_TIMEOUT_SECONDS,
    OLLAMA_GENERATION_TIMEOUT_SECONDS,
)
from .runtime_contracts import (
    CancelCallback,
    ChatResponse,
    InferenceProtocolError,
    validate_loopback_origin,
)
from .runtime_registry import RuntimeRegistry


class LlamaCppClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18080",
        *,
        api_key: str | None = None,
        registry: RuntimeRegistry | None = None,
        connect_timeout: float = OLLAMA_CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = OLLAMA_GENERATION_TIMEOUT_SECONDS,
        overall_timeout: float = OLLAMA_GENERATION_TIMEOUT_SECONDS,
        session: requests.Session | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        for name, value in (
            ("connect_timeout", connect_timeout),
            ("read_timeout", read_timeout),
            ("overall_timeout", overall_timeout),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        self.base_url = validate_loopback_origin(base_url)
        self.api_key = api_key
        self.registry = registry
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)
        self.overall_timeout = float(overall_timeout)
        self._session = session or requests.Session()
        if session is None:
            self._session.trust_env = False
        self._monotonic = monotonic or time.monotonic

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _engine_model(self, model: str) -> str:
        if self.registry is None:
            return model
        return self.registry.engine_id(model)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        stream: bool = False,
        timeout: tuple[float, float] | None = None,
    ) -> requests.Response:
        allowed = (
            path.startswith("/v1/")
            or path.startswith("/models")
            or path.startswith("/props")
            or path in {"/health", "/slots", "/tokenize", "/apply-template"}
        )
        if not allowed or path.startswith("/api/"):
            raise ModelClientError(f"llama.cpp client refuses native Ollama path {path}")
        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                json=None if json_body is None else dict(json_body),
                headers=self._headers(),
                stream=stream,
                timeout=timeout or (
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
            raise ModelClientError(f"llama.cpp request failed: {exc}") from exc
        if 300 <= int(getattr(response, "status_code", 0)) < 400:
            raise ModelClientError("llama.cpp redirects are not permitted")
        return response

    def native_context_length(self, model: str) -> int:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        engine_id = self._engine_model(model.strip())
        response = self._request("GET", "/v1/models")
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ModelClientError(f"llama.cpp model probe returned an HTTP error: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise InferenceProtocolError("llama.cpp model probe returned invalid JSON") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if not isinstance(payload, dict):
            raise InferenceProtocolError("llama.cpp model probe payload must be a JSON object")
        rows = payload.get("data")
        if not isinstance(rows, list):
            rows = payload.get("models")
        if not isinstance(rows, list):
            raise ModelCapabilityError(
                f"native context capability is unknown for model {model!r}"
            )
        candidates: set[int] = set()
        for entry in rows:
            if not isinstance(entry, Mapping):
                continue
            identity = str(entry.get("id") or entry.get("name") or "").strip()
            aliases = entry.get("aliases") if isinstance(entry.get("aliases"), list) else []
            names = {identity, *(str(item).strip() for item in aliases)}
            if engine_id not in names and model.strip() not in names:
                continue
            values = _extract_context_values(entry)
            candidates.update(values)
        if len(candidates) != 1:
            detail = "missing" if not candidates else "conflicting"
            raise ModelCapabilityError(
                f"native context capability is {detail} for model {model!r}"
            )
        return candidates.pop()

    def count_prompt_tokens(
        self,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        think: bool | None = None,
    ) -> int | None:
        """EXACT prompt tokens for ``messages`` as the server will run them, or None.

        Renders the conversation through the model's own chat template (``/apply-template``)
        and counts it with the model's own tokenizer (``/tokenize``) - the same bytes the
        generation request will evaluate. Any failure returns None so the caller falls back
        to the conservative one-token-per-byte bound: counting can only ever make capacity
        MORE accurate, never optimistic on error. In router mode both endpoints need the
        model name and load that model, which the generation that follows needs anyway.
        """
        engine_id = self._engine_model(model.strip())
        body: dict[str, Any] = {"model": engine_id, "messages": [dict(m) for m in messages]}
        if think is not None:
            body["chat_template_kwargs"] = {"enable_thinking": bool(think)}
        try:
            rendered = self._post_json("/apply-template", body)
            prompt = rendered.get("prompt") if isinstance(rendered, Mapping) else None
            if not isinstance(prompt, str):
                return None
            counted = self._post_json(
                "/tokenize", {"model": engine_id, "content": prompt, "add_special": True})
            tokens = counted.get("tokens") if isinstance(counted, Mapping) else None
        except (ModelClientError, ValueError):
            return None
        if not isinstance(tokens, list):
            return None
        return len(tokens)

    def count_text_tokens(self, model: str, text: str) -> int | None:
        """EXACT tokens of raw ``text`` (no chat template) by the model's tokenizer, or None.

        Used to size shards of a large input; like count_prompt_tokens, any failure returns
        None so the caller falls back to the conservative byte bound.
        """
        engine_id = self._engine_model(model.strip())
        try:
            counted = self._post_json(
                "/tokenize", {"model": engine_id, "content": text, "add_special": False})
        except (ModelClientError, ValueError):
            return None
        tokens = counted.get("tokens") if isinstance(counted, Mapping) else None
        return len(tokens) if isinstance(tokens, list) else None

    def _post_json(self, path: str, body: Mapping[str, Any]) -> Any:
        response = self._request("POST", path, json_body=body)
        try:
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise ModelClientError(f"llama.cpp {path} returned an HTTP error: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise InferenceProtocolError(f"llama.cpp {path} returned invalid JSON") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def _models_payload(self) -> dict[str, Any]:
        response = self._request("GET", "/models")
        try:
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ModelClientError(f"llama.cpp inventory probe returned an HTTP error: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise InferenceProtocolError("llama.cpp inventory probe returned invalid JSON") from exc
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if not isinstance(payload, dict):
            raise InferenceProtocolError("llama.cpp inventory probe payload must be a JSON object")
        return payload

    def probe_installed(self) -> ModelProbe:
        payload = self._models_payload()
        names = _model_ids(payload, loaded_only=False)
        return ModelProbe(endpoint="/models", models=tuple(sorted(names)), raw=payload)

    def probe_loaded(self) -> ModelProbe:
        payload = self._models_payload()
        names = _model_ids(payload, loaded_only=True)
        return ModelProbe(endpoint="/models", models=tuple(sorted(names)), raw=payload)

    def probe_models(self) -> ModelInventory:
        installed = self.probe_installed()
        loaded = self.probe_loaded()
        return ModelInventory(
            installed=installed.models,
            loaded=loaded.models,
            installed_raw=installed.raw,
            loaded_raw=loaded.raw,
        )

    def _resolve_generation_capacity(
        self,
        *,
        model: str,
        prompt: str,
        options: Mapping[str, Any],
        system: str | None,
        response_format: str | Mapping[str, Any] | None,
        exact_input_tokens: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
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
        if requested_context > native_context:
            raise ModelCapabilityError(
                f"requested num_ctx {requested_context} exceeds native/configured "
                f"limit {native_context} for model {model!r}; declared 131072 is "
                f"not supported and is not silently truncated"
            )
        effective_context = requested_context
        if exact_input_tokens is not None:
            # The templated prompt counted by the model's own tokenizer. The template margin is
            # still reserved below, so the only slack is the margin itself.
            input_bound = int(exact_input_tokens)
            input_count = "exact"
        else:
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
            input_bound = len(material)
            input_count = "conservative_bytes"
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
            "input_count": input_count,
            "context_safety_allowance": CONTEXT_TEMPLATE_MARGIN_TOKENS,
            "remaining_generation_capacity": remaining_generation,
            "effective_generation_max": effective_generation,
        }

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
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        messages: list[dict[str, Any]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        chat = self.chat(
            model=model,
            messages=messages,
            options=options,
            cancel_requested=cancel_requested,
            overall_timeout=overall_timeout,
            think=think,
            response_format=response_format,
            prompt_for_capacity=prompt,
            system_for_capacity=system,
        )
        return GenerationResponse(
            text=chat.text,
            model=chat.model,
            options=chat.options,
            raw_events=chat.raw_events,
            raw_lines=chat.raw_lines,
            telemetry=chat.telemetry,
            started_monotonic=chat.started_monotonic,
            completed_monotonic=chat.completed_monotonic,
        )

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
        prompt_for_capacity: str | None = None,
        system_for_capacity: str | None = None,
    ) -> ChatResponse:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        timeout_limit = self.overall_timeout if overall_timeout is None else float(overall_timeout)
        if timeout_limit <= 0:
            raise ValueError("overall_timeout must be positive")
        cancellation = cancel_requested or (lambda: False)
        if cancellation():
            raise GenerationCancelled("generation cancelled before request")
        if think is not None and not isinstance(think, bool):
            raise TypeError("think must be a boolean or None")
        request_options = dict(options or {})
        requested_format = _normalize_response_format(response_format)
        capacity_prompt = prompt_for_capacity
        if capacity_prompt is None:
            capacity_prompt = json.dumps(list(messages), ensure_ascii=False, separators=(",", ":"))
        # Exact counting needs a context budget to check against, and cannot see tool schemas
        # through the template endpoint; either way the conservative bound stays in force.
        exact_tokens = None
        if "num_ctx" in request_options and "num_predict" in request_options and not tools:
            exact_tokens = self.count_prompt_tokens(model, messages, think=think)
        request_options, capacity = self._resolve_generation_capacity(
            model=model,
            prompt=capacity_prompt,
            options=request_options,
            system=system_for_capacity,
            response_format=requested_format,
            exact_input_tokens=exact_tokens,
        )
        engine_id = self._engine_model(model.strip())
        payload: dict[str, Any] = {
            "model": engine_id,
            "messages": [dict(item) for item in messages],
            "stream": True,
        }
        if think is True:
            payload["chat_template_kwargs"] = {"enable_thinking": True}
            payload["reasoning_format"] = "deepseek"
        elif think is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        sampling = _sampling_from_options(request_options)
        payload.update(sampling)
        if requested_format == "json":
            payload["response_format"] = {"type": "json_object"}
        elif isinstance(requested_format, dict):
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": requested_format},
            }
        if tools:
            payload["tools"] = [dict(item) for item in tools]
        started = self._monotonic()
        connect_budget = min(self.connect_timeout, timeout_limit)
        read_budget = min(self.read_timeout, timeout_limit)
        response: requests.Response | Any | None = None
        raw_events: list[dict[str, Any]] = []
        raw_lines: list[str] = []
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        finish_reason: str | None = None
        reported_model = engine_id
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
            while not abort_watcher_stop.wait(0.05):
                if cancellation():
                    abort_observed.set()
                    close_active_response()
                    return

        abort_watcher = threading.Thread(
            target=watch_for_cancellation,
            name="sovereign-llamacpp-call-cancellation",
            daemon=True,
        )
        abort_watcher.start()
        try:
            response = self._request(
                "POST",
                "/v1/chat/completions",
                json_body=payload,
                stream=True,
                timeout=(connect_budget, read_budget),
            )
            if abort_observed.is_set() or cancellation():
                abort_observed.set()
                close_active_response()
                raise GenerationCancelled("generation cancelled")
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise ModelClientError(f"llama.cpp returned an HTTP error: {exc}") from exc
            try:
                for raw_line in response.iter_lines(decode_unicode=True):
                    now = self._monotonic()
                    if now - started > timeout_limit:
                        raise GenerationTimeout("overall")
                    if abort_observed.is_set() or cancellation():
                        raise GenerationCancelled("generation cancelled")
                    if raw_line is None:
                        continue
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
                    if not line.strip() or line.startswith(":"):
                        continue
                    raw_lines.append(line)
                    if not line.startswith("data:"):
                        raise InferenceProtocolError("llama.cpp stream emitted a non-SSE line")
                    data = line[5:].strip()
                    if data == "[DONE]":
                        saw_done = True
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise InferenceProtocolError("llama.cpp emitted invalid streaming JSON") from exc
                    if not isinstance(event, dict):
                        raise InferenceProtocolError("llama.cpp streaming event must be a JSON object")
                    raw_events.append(dict(event))
                    if event.get("error"):
                        raise ModelClientError(f"llama.cpp generation error: {event['error']}")
                    if isinstance(event.get("model"), str) and event["model"].strip():
                        reported_model = event["model"].strip()
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, Mapping):
                        raise InferenceProtocolError("llama.cpp choice must be an object")
                    if isinstance(choice.get("finish_reason"), str):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta") if isinstance(choice.get("delta"), Mapping) else {}
                    message = choice.get("message") if isinstance(choice.get("message"), Mapping) else {}
                    content = delta.get("content")
                    if content is None:
                        content = message.get("content")
                    if content is None:
                        content = ""
                    if not isinstance(content, str):
                        raise InferenceProtocolError("llama.cpp content chunk must be text")
                    reasoning = delta.get("reasoning_content")
                    if reasoning is None:
                        reasoning = delta.get("reasoning")
                    if reasoning is None:
                        reasoning = message.get("reasoning_content")
                    if reasoning is None:
                        reasoning = ""
                    if reasoning != "" and not isinstance(reasoning, str):
                        raise InferenceProtocolError("llama.cpp reasoning chunk must be text")
                    if content:
                        text_parts.append(content)
                    if reasoning:
                        reasoning_parts.append(str(reasoning))
                    observed_tools = delta.get("tool_calls") or message.get("tool_calls")
                    if isinstance(observed_tools, list):
                        _merge_tool_calls(tool_calls, observed_tools)
            except requests.ReadTimeout as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                raise GenerationTimeout("read") from exc
            except requests.ConnectionError as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                if "timed out" in str(exc).lower():
                    raise GenerationTimeout("read") from exc
                raise ModelClientError(f"llama.cpp stream failed: {exc}") from exc
            except requests.RequestException as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                raise ModelClientError(f"llama.cpp stream failed: {exc}") from exc
            except UnicodeError as exc:
                raise InferenceProtocolError("llama.cpp stream emitted invalid UTF-8") from exc
            except Exception as exc:
                if abort_observed.is_set() or cancellation():
                    raise GenerationCancelled("generation cancelled") from exc
                raise
            completed = self._monotonic()
            if completed - started > timeout_limit:
                raise GenerationTimeout("overall")
            if abort_observed.is_set() or cancellation():
                raise GenerationCancelled("generation cancelled")
            if not saw_done:
                raise InferenceProtocolError("llama.cpp stream ended without a done event")
            reasoning_text = "".join(reasoning_parts)
            telemetry = {
                "requested_model": model.strip(),
                "engine_model": engine_id,
                "reported_model": reported_model,
                "requested_think": think,
                "reasoning_text": reasoning_text,
                "finish_reason": finish_reason,
                "event_count": len(raw_events),
                "connect_timeout_seconds": self.connect_timeout,
                "read_timeout_seconds": self.read_timeout,
                "overall_timeout_seconds": timeout_limit,
                "effective_connect_timeout_seconds": connect_budget,
                "effective_read_timeout_seconds": read_budget,
                "endpoint": "/v1/chat/completions",
                **capacity,
            }
            return ChatResponse(
                text="".join(text_parts),
                reasoning=reasoning_text,
                model=reported_model,
                requested_model=model.strip(),
                think=think,
                finish_reason=finish_reason,
                tool_calls=tuple(tool_calls),
                options=request_options,
                raw_events=tuple(raw_events),
                raw_lines=tuple(raw_lines),
                telemetry=telemetry,
                started_monotonic=started,
                completed_monotonic=completed,
            )
        except ModelClientError as exc:
            terminal = raw_events[-1] if raw_events else {}
            setattr(
                exc,
                "partial_response",
                {
                    "text": "".join(text_parts),
                    "reasoning": "".join(reasoning_parts),
                    "model": terminal.get("model"),
                    "options": dict(request_options),
                    "raw_events": [dict(event) for event in raw_events],
                    "raw_lines": list(raw_lines),
                    "telemetry": {
                        "requested_model": model.strip(),
                        "requested_think": think,
                        "failure_type": type(exc).__name__,
                        "failure": str(exc),
                    },
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


def _merge_tool_calls(existing: list[dict[str, Any]], observed: list[Any]) -> None:
    for call in observed:
        if not isinstance(call, Mapping):
            continue
        index = call.get("index", len(existing))
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            continue
        while len(existing) <= index:
            existing.append({"type": "function", "function": {"name": "", "arguments": ""}})
        target = existing[index]
        if isinstance(call.get("id"), str) and call["id"]:
            target["id"] = call["id"]
        if isinstance(call.get("type"), str) and call["type"]:
            target["type"] = call["type"]
        function = call.get("function")
        if not isinstance(function, Mapping):
            continue
        dest = target.setdefault("function", {"name": "", "arguments": ""})
        if isinstance(function.get("name"), str) and function["name"]:
            dest["name"] = function["name"]
        if isinstance(function.get("arguments"), str):
            dest["arguments"] = str(dest.get("arguments") or "") + function["arguments"]


def _model_ids(payload: Mapping[str, Any], *, loaded_only: bool) -> set[str]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise InferenceProtocolError("llama.cpp inventory data must be a list")
    names: set[str] = set()
    for entry in rows:
        if not isinstance(entry, Mapping):
            continue
        identity = str(entry.get("id") or "").strip()
        if not identity:
            continue
        if loaded_only:
            status = entry.get("status")
            value = status.get("value") if isinstance(status, Mapping) else status
            if str(value).strip().lower() != "loaded":
                continue
        names.add(identity)
    return names


def _extract_context_values(entry: Mapping[str, Any]) -> set[int]:
    found: set[int] = set()
    for key in ("n_ctx_train", "context_length", "context_window"):
        value = entry.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            found.add(value)
    meta = entry.get("meta") if isinstance(entry.get("meta"), Mapping) else {}
    for key in ("n_ctx_train", "context_length", "context_window"):
        value = meta.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            found.add(value)
    return found


def _normalize_response_format(
    response_format: str | Mapping[str, Any] | None,
) -> str | dict[str, Any] | None:
    if response_format is None:
        return None
    if isinstance(response_format, str):
        if response_format != "json":
            raise ValueError("response_format text must be exactly 'json'")
        return response_format
    if isinstance(response_format, Mapping):
        payload = dict(response_format)

        def validate_json_value(value: Any) -> None:
            if value is None or isinstance(value, (str, bool, int)):
                return
            if isinstance(value, float):
                if not math.isfinite(value):
                    raise ValueError("response_format schema must contain finite JSON values")
                return
            if isinstance(value, list):
                for item in value:
                    validate_json_value(item)
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ValueError("response_format schema keys must be strings")
                    validate_json_value(item)
                return
            raise ValueError("response_format schema must contain only JSON-compatible values")

        validate_json_value(payload)
        return payload
    raise TypeError("response_format must be 'json', a JSON schema mapping, or None")


def _sampling_from_options(options: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    mapping = {
        "temperature": "temperature",
        "top_p": "top_p",
        "top_k": "top_k",
        "min_p": "min_p",
        "repeat_penalty": "repeat_penalty",
        "seed": "seed",
        "stop": "stop",
        "num_predict": "max_tokens",
    }
    for source, dest in mapping.items():
        if source in options:
            payload[dest] = options[source]
    return payload
