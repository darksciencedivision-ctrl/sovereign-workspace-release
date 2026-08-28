"""Model capability registry and prompt-budget math (Phase 8).

Context windows are discovered from Ollama at runtime (/api/show) rather
than hard-coded per model family; a conservative fallback applies when a
model cannot be introspected. The registry caches per process.
"""

from __future__ import annotations

from dataclasses import dataclass

SAFETY_MARGIN_TOKENS = 64
FALLBACK_CONTEXT_WINDOW = 8192


@dataclass(frozen=True)
class ModelCapabilities:
    model: str
    context_window: int
    safe_context: int          # input ceiling incl. this turn's output reserve
    output_allowance: int
    qualification: str         # "runtime-discovered" | "fallback"


def capabilities_from_window(
    model: str, context_window: int | None, output_allowance: int
) -> ModelCapabilities:
    window = int(context_window) if context_window else FALLBACK_CONTEXT_WINDOW
    return ModelCapabilities(
        model=model,
        context_window=window,
        safe_context=max(512, window - SAFETY_MARGIN_TOKENS),
        output_allowance=int(output_allowance),
        qualification="runtime-discovered" if context_window else "fallback",
    )


def estimate_tokens(text: str) -> int:
    """Cheap deterministic token estimate (~4 chars/token)."""
    return max(1, (len(text) + 3) // 4)


def extract_context_length(payload: dict) -> int | None:
    """Pull the largest *.context_length value out of an /api/show body."""
    info = payload.get("model_info") or {}
    values = [
        int(value)
        for key, value in info.items()
        if key.endswith(".context_length") and isinstance(value, (int, float))
    ]
    return max(values) if values else None


class CapabilityRegistry:
    def __init__(self):
        self._cache: dict[str, ModelCapabilities] = {}

    def seed(self, model: str, context_window: int | None, output_allowance: int) -> ModelCapabilities:
        caps = capabilities_from_window(model, context_window, output_allowance)
        self._cache[model] = caps
        return caps

    async def get_or_load(
        self,
        model: str,
        output_allowance: int,
        client_factory=None,
    ) -> ModelCapabilities:
        cached = self._cache.get(model)
        if cached is not None:
            return cached
        window = None
        if client_factory is not None:
            try:
                async with client_factory() as client:
                    response = await client.post("/api/show", json={"model": model})
                    response.raise_for_status()
                    window = extract_context_length(response.json())
            except Exception:
                window = None
        return self.seed(model, window, output_allowance)


registry = CapabilityRegistry()