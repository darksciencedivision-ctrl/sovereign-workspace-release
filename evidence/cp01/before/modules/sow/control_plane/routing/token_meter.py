"""Token metering for context-routing measurement (Plan §7-P9).

Uses a real tokenizer (tiktoken cl100k_base) when available; otherwise falls back to a
whitespace-word proxy. Which method was used is always recorded so a measured reduction is
never misrepresented as a real token count when it is a proxy.
"""
from __future__ import annotations

from dataclasses import dataclass


def _make_counter():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda s: len(enc.encode(s))), "tiktoken:cl100k_base"
    except Exception:
        return (lambda s: len(s.split())), "word-proxy"


_COUNT, _METHOD = _make_counter()


def count_tokens(text: str) -> int:
    return _COUNT(text)


def tokenizer_method() -> str:
    return _METHOD


@dataclass(frozen=True)
class ReductionResult:
    scoped_tokens: int
    naive_tokens: int
    tokenizer: str

    @property
    def reduction_pct(self) -> float:
        if self.naive_tokens == 0:
            return 0.0
        return round(100.0 * (self.naive_tokens - self.scoped_tokens) / self.naive_tokens, 2)


def measure_reduction(scoped_text: str, naive_text: str) -> ReductionResult:
    return ReductionResult(count_tokens(scoped_text), count_tokens(naive_text), _METHOD)
