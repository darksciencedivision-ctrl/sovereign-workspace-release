"""Model backend abstraction (Plan §5 recommended stack; I-CH1/I-SC1).

A Backend is the thing behind an adapter that actually produces text. Adapters are
capability-described and vendor-neutral; the backend is where a concrete model (local
Ollama, a mocked frontier CLI, a coding harness) plugs in. Keeping this behind one small
`generate` interface is what lets the scheduler pick by capability without the control
plane ever naming a model.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol, runtime_checkable

from adapters.detect import OLLAMA_HOST


class BackendAuthPause(Exception):
    """A subscription/auth condition (expired login, revoked credit, rate cap) that must
    PAUSE the node fail-closed (Plan §18.4) rather than be swallowed as an ordinary task
    failure. The generic worker adapter re-raises this so the supervisor can pause and surface
    it; there is NO silent fallback to another auth path. Concrete backends subclass it."""


@runtime_checkable
class Backend(Protocol):
    name: str

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str: ...
    def list_models(self) -> dict: ...
    def load_model(self, artifact_id: str) -> dict: ...
    def unload_model(self, artifact_id: str) -> dict: ...
    def cancel(self, request_id: str) -> dict: ...
    def health(self) -> dict: ...
    def capabilities(self) -> dict: ...


@runtime_checkable
class ConductorBackend(Protocol):
    """What the Phase-4 ConductorAdapter binds as its runtime selection (I-CN1). The conductor
    is an INTERFACE; any object satisfying this small contract can back it — the deterministic
    `MockReasoningBackend` (Phase 4), or a live provider bridged onto it (Phase 15B `.conductor`
    wraps the `claude_code` worker backend as `ClaudeCodeConductorBackend`). Formalising the
    shape is what makes "conductor-capable" a checkable claim rather than a duck-typing accident.

    `model_name` is the EXECUTING model recorded on every decision (honesty: the selection label
    on the adapter's capability may differ from the checkpoint that actually ran — directive
    §11 15D); `calls` counts backend invocations for succession export; `propose_plan` decomposes
    an objective into a decision dict (it PROPOSES — the conductor never self-promotes, invariant
    16). It carries NO credential and asserts no authority."""

    model_name: str
    calls: int

    def propose_plan(self, objective: str, conductor_files: dict[str, str],
                     cycle: int) -> dict: ...


class MockBackend:
    """Deterministic generate() for tests — no network, replayable."""

    def __init__(self, name: str = "mock-backend") -> None:
        self.name = name
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        import hashlib
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return f"[{self.name}] deterministic response to prompt (h={h}): {prompt[:80]}"

    def list_models(self) -> dict:
        return {"supported": True, "models": [self.name]}
    def load_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "mock backend has no load"}
    def unload_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "mock backend has no unload"}
    def cancel(self, request_id: str) -> dict:
        return {"supported": False, "reason": "mock backend has no cancel"}
    def health(self) -> dict:
        return {"supported": True, "ok": True}
    def capabilities(self) -> dict:
        return {"generate": True, "stream": False, "load": False, "unload": False, "cancel": False}


class OllamaBackend:
    """Real local backend over the Ollama daemon (127.0.0.1). No credentials, local only —
    permitted under the build prohibitions (a detected local model MAY be used). Never used
    by the default test suite (which stays deterministic); exercised by the opt-in live smoke.
    """

    def __init__(self, model: str, host: str = OLLAMA_HOST) -> None:
        self.model = model
        self.name = f"ollama:{model}"
        self._host = host
        # cost-to-accepted-output instrumentation (Buildout §4): the mock backends have always
        # counted their calls, so a REAL backend without a counter reports 0 for exactly the legs
        # that consume resources — an inverted usage record. Counted here for every backend.
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        body = json.dumps({
            "model": self.model, "prompt": prompt, "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.0},
        }).encode("utf-8")
        req = urllib.request.Request(f"{self._host}/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("response", "")


    def list_models(self) -> dict:
        return {"supported": True, "models": [self.model]}

    def load_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "Ollama loads on first generate; explicit load is not a native API"}

    def unload_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "Ollama has no explicit unload in the local HTTP generate API"}

    def cancel(self, request_id: str) -> dict:
        return {"supported": False, "reason": "Ollama /api/generate cancel is not exposed on this adapter"}

    def health(self) -> dict:
        try:
            urllib.request.urlopen(f"{self._host}/api/tags", timeout=3)
            return {"supported": True, "ok": True}
        except Exception as e:
            return {"supported": True, "ok": False, "reason": str(e)}

    def capabilities(self) -> dict:
        return {"generate": True, "stream": False, "load": False, "unload": False, "cancel": False}
