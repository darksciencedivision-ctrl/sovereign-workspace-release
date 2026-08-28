from __future__ import annotations

import json
import math
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from system_manifest import load_system_manifest, model_name, runtime_value


@dataclass(frozen=True)
class EmbeddingResponse:
    ok: bool
    text: str
    model: str
    vector: tuple[float, ...] | None = None
    error_code: str = ""
    error_message: str = ""
    cached: bool = False


class EmbeddingClient:
    def __init__(self, model: str, base_url: str, timeout_seconds: int) -> None:
        self.model = str(model).strip()
        self.base_url = str(base_url).strip().rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._cache: dict[str, tuple[float, ...]] = {}

    def _error(self, text: str, code: str, message: str) -> EmbeddingResponse:
        return EmbeddingResponse(
            ok=False,
            text=text,
            model=self.model,
            vector=None,
            error_code=code,
            error_message=message,
            cached=False,
        )

    def embed(self, text: str) -> EmbeddingResponse:
        original_text = "" if text is None else str(text)
        if not original_text.strip():
            return self._error(original_text, "EMPTY_INPUT", "Embedding input is empty.")

        cached = self._cache.get(original_text)
        if cached is not None:
            return EmbeddingResponse(
                ok=True,
                text=original_text,
                model=self.model,
                vector=cached,
                cached=True,
            )

        payload = {"model": self.model, "prompt": original_text}
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            return self._error(original_text, "PAYLOAD_ERROR", str(exc))

        request = urllib.request.Request(
            f"{self.base_url}/api/embeddings",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (TimeoutError, socket.timeout):
            return self._error(original_text, "TIMEOUT", f"Embedding request timed out after {self.timeout_seconds}s.")
        except urllib.error.HTTPError as exc:
            return self._error(original_text, "HTTP_ERROR", f"Embedding request failed with HTTP {exc.code}.")
        except (urllib.error.URLError, OSError) as exc:
            return self._error(original_text, "REQUEST_ERROR", f"{type(exc).__name__}: {exc}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return self._error(original_text, "BAD_JSON", f"Invalid embedding response JSON: {exc}")
        if not isinstance(data, dict):
            return self._error(original_text, "INVALID_RESPONSE", "Embedding response must be a JSON object.")

        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            return self._error(original_text, "INVALID_RESPONSE", "Embedding response missing non-empty 'embedding'.")

        try:
            vector = tuple(float(item) for item in embedding)
        except (TypeError, ValueError) as exc:
            return self._error(original_text, "NON_NUMERIC_VECTOR", f"Embedding contains non-numeric values: {exc}")

        self._cache[original_text] = vector
        return EmbeddingResponse(
            ok=True,
            text=original_text,
            model=self.model,
            vector=vector,
            cached=False,
        )


def build_manifest_embedding_client(root: str | None = None, manifest: dict[str, Any] | None = None) -> EmbeddingClient:
    cfg = manifest or load_system_manifest(root)
    return EmbeddingClient(
        model=model_name("EMBEDDING_MODEL", cfg),
        base_url=str(runtime_value("OLLAMA_BASE_URL", cfg)).strip(),
        timeout_seconds=int(runtime_value("EMBEDDING_TIMEOUT_SECONDS", cfg)),
    )


def cosine_similarity(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for left_value, right_value in zip(left, right):
        dot += float(left_value) * float(right_value)
        norm_left += float(left_value) * float(left_value)
        norm_right += float(right_value) * float(right_value)
    if norm_left <= 0.0 or norm_right <= 0.0:
        return None
    cosine = dot / (math.sqrt(norm_left) * math.sqrt(norm_right))
    return max(-1.0, min(1.0, cosine))
