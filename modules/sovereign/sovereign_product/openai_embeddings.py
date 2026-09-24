"""Opt-in local OpenAI embedding adapter; no production default is changed.

The base URL is an engine origin, not Sovereign's own /v1 application API.
Model and serving-profile qualification remain the caller's responsibility.
"""
from __future__ import annotations

import math

import requests

from embedding_client import EmbeddingClient, EmbeddingResponse
from .model_client import validate_loopback_ollama_url


class OpenAIEmbeddingClient(EmbeddingClient):
    """Keep the existing embedding interface while using /v1/embeddings."""

    def __init__(self, model: str, base_url: str, timeout_seconds: int,
                 *, expected_dimensions: int, api_key: str | None = None) -> None:
        super().__init__(model, validate_loopback_ollama_url(base_url), timeout_seconds)
        if isinstance(expected_dimensions, bool) or not isinstance(expected_dimensions, int) or expected_dimensions <= 0:
            raise ValueError("expected_dimensions must be a positive integer")
        self.expected_dimensions = expected_dimensions
        self.api_key = api_key

    def embed(self, text: str) -> EmbeddingResponse:
        original = "" if text is None else str(text)
        if not original.strip():
            return self._error(original, "EMPTY_INPUT", "Embedding input is empty.")
        if original in self._cache:
            return EmbeddingResponse(ok=True, text=original, model=self.model,
                                     vector=self._cache[original], cached=True)
        try:
            # Never inherit proxy or netrc settings, or follow an endpoint redirect.
            with requests.Session() as session:
                session.trust_env = False
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = session.post(
                    self.base_url + "/v1/embeddings",
                    json={"model": self.model, "input": original, "encoding_format": "float"},
                    headers=headers,
                    timeout=self.timeout_seconds, allow_redirects=False,
                )
                if response.status_code != 200:
                    return self._error(original, "HTTP_ERROR",
                                       f"Embedding request failed with HTTP {response.status_code}.")
                try:
                    data = response.json()
                except ValueError:
                    return self._error(original, "BAD_JSON", "Invalid embedding response JSON.")
        except requests.Timeout:
            return self._error(original, "TIMEOUT", f"Embedding request timed out after {self.timeout_seconds}s.")
        except requests.RequestException as exc:
            return self._error(original, "REQUEST_ERROR", f"{type(exc).__name__}: {exc}")

        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or rows[0].get("index") != 0:
            return self._error(original, "INVALID_RESPONSE", "Expected exactly one embedding with index 0.")
        vector = rows[0].get("embedding")
        if not isinstance(vector, list) or len(vector) != self.expected_dimensions:
            return self._error(original, "DIMENSION_MISMATCH", "Embedding dimensions do not match the serving profile.")
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) for x in vector):
            return self._error(original, "NON_NUMERIC_VECTOR", "Embedding contains non-numeric values.")
        values = tuple(float(x) for x in vector)
        if not all(math.isfinite(x) for x in values) or not any(values):
            return self._error(original, "INVALID_RESPONSE", "Embedding must be finite and nonzero.")
        self._cache[original] = values
        return EmbeddingResponse(ok=True, text=original, model=self.model, vector=values)
