"""A conductor backed by a LOCAL model.

EPC-02 A-4, authorized by the operator as option A-3a (ENTRY 032).

The architecture already said the conductor was an interface. `adapters/conductor/adapter.py`
opens with it: *"The conductor is an INTERFACE; the current runtime selection (today: fable-5)
backs it but the architecture knows only this contract (I-CN1)."* Only one implementation of
that interface existed, and it was the Claude Code CLI - a frontier provider. Measured during
EPC-02 A-1:

  * `node_runtime/supervisor/conductor_spawn.py` raises `ClaudeCliUnavailable` when the
    `claude` CLI is absent, so with no frontier authorization the conductor cannot spawn.
  * `adapters/conductor/adapter.py` defaults to `MockReasoningBackend()`, so a conductor
    constructed without an explicit backend reasons against a deterministic mock.
  * `control_plane/conductor/registry.py` nevertheless DERIVES local conductor seats from the
    operator's model ceiling - the system offered a local conductor seat that no code path
    could spawn.

That is what this module closes. It is the second implementation of an interface that always
claimed to have more than one.

WHAT IT DELIBERATELY REUSES. `_build_decomposition_prompt` and `_parse_decomposition` are
imported from the claude_code module rather than reimplemented. Two parsers for one decision
format would drift, and the drift would show up as a conductor that behaves differently
depending on which model backs it - the exact thing an interface exists to prevent. Verified
before importing: that module has no import-time side effects and holds no credential.

WHAT IT DOES NOT DO. It holds no credential and needs none: Ollama is loopback-local and
unauthenticated. It adds no authority - it proposes a decomposition and returns it; the
ConductorAdapter records the result as CANDIDATE, exactly as it does for the frontier path
(invariant 16: the conductor may propose, never promote).
"""
from __future__ import annotations

from typing import Any

from adapters.base.backend import OllamaBackend
from adapters.frontier.claude_code import (
    _build_decomposition_prompt,
    _parse_decomposition,
)

#: Visible-token budget for one decomposition. Generous enough that a local 8B model finishes
#: a plan rather than truncating mid-task - the failure that discarded six minutes of DEEP
#: deliberation elsewhere in this session (ENTRY 034) and would silently produce short plans
#: here.
LOCAL_CONDUCTOR_MAX_TOKENS = 2048


class OllamaConductorBackend:
    """The `ConductorBackend` contract over a local Ollama model.

    Mirrors `ClaudeCodeConductorBackend`: same three attributes the ConductorAdapter binds
    (`model_name`, `calls`, `propose_plan`), same decision dict, same fail-closed parse.
    """

    def __init__(self, model: str, *, backend: Any | None = None,
                 model_name: str | None = None) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a local conductor needs a model tag")
        self._backend = backend if backend is not None else OllamaBackend(model.strip())
        self.model_name = model_name or f"ollama:{model.strip()}"
        self.calls = 0

    @property
    def wrapped_backend(self) -> Any:
        """The backend this binding wraps, read-only. Grants no authority: it produces text."""
        return self._backend

    def propose_plan(self, objective: str, conductor_files: dict[str, str],
                     cycle: int) -> dict[str, Any]:
        """Decompose an objective into a conductor DECISION dict.

        The conductor PROPOSES; the ConductorAdapter records the result as CANDIDATE.

        `model_verified` is reported honestly and is the one place this differs in substance
        from the frontier binding. That path verifies a vendor CHECKPOINT ID datable to the
        call just made. Ollama has no such notion: the model tag is the whole identity, and
        the daemon runs the tag it was given. So verification here means the daemon confirmed
        the model it ran, and nothing stronger is claimed. When the backend cannot report it,
        the flag is False rather than assumed - a CANDIDATE must never read as a confirmed
        checkpoint.
        """
        self.calls += 1
        prompt = _build_decomposition_prompt(objective, conductor_files, cycle)
        raw = self._backend.generate(prompt, max_tokens=LOCAL_CONDUCTOR_MAX_TOKENS)
        tasks, mode = _parse_decomposition(raw)

        reported = getattr(self._backend, "last_reported_model", None)
        verified = isinstance(reported, str) and bool(reported.strip())

        return {
            "model": reported if verified else self.model_name,
            "model_selection": self.model_name,
            "model_verified": verified,
            "cycle": cycle,
            "objective_ack": objective,
            "proposed_tasks": tasks,
            "files_considered": sorted(conductor_files),
            "parse_mode": mode,
            "raw_excerpt": (raw or "")[:500],
            "rationale": (f"local conductor decomposition via {self.model_name} "
                          f"({mode}; {len(tasks)} task(s))"),
        }
