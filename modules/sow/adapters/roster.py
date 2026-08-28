"""Phase 6 multi-model roster (Plan §7-P6, §9.7; I-SC1/I-CH1).

Defines ≥3 backends behind capability descriptors and decides, by host detection, whether
each is a real local backend or a mock — recorded, never hidden. The control plane sees only
descriptors; the roster is the one place a concrete model is named.

Rosters (offline defaults per D-COND-02/D-CODEX-03):
  - local_reasoning : worker_reasoning, local, offline-eligible   (Ollama qwen3:8b/14b else mock)
  - coding_node     : worker_coding_specialist, local, offline    (OpenCode + qwen2.5-coder else mock)
  - mock_frontier   : worker_reasoning, frontier, NOT offline     (mock — live subscription is
                      out of scope by prohibition; deferred-live)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapters import detect
from adapters.base.backend import Backend, MockBackend, OllamaBackend
from control_plane.profiles.live_authorization import LiveAuthorization, load_live_authorization

# offline-default model preferences (first detected wins); names are here, not in task defs
_REASONING_MODELS = ("qwen3:8b", "qwen3:14b", "qwen2.5:7b-instruct", "qwen2.5:14b-instruct")
_CODER_MODELS = ("qwen2.5-coder:7b", "qwen2.5-coder:32b", "qwen3-coder:30b", "deepseek-coder-v2:latest")


@dataclass(frozen=True)
class RosterEntry:
    name: str
    node_class: str
    locality: str
    cost_class: str
    offline_profile_eligible: bool
    requires_network: bool
    subscription_backed: bool
    capability_descriptors: list[dict[str, Any]]
    backend_kind: str            # "ollama" | "mock"
    model: str | None
    harness: str | None = None
    notes: str = ""

    def build_backend(self) -> Backend:
        if self.backend_kind == "ollama" and self.model:
            return OllamaBackend(self.model)
        return MockBackend(name=f"mock:{self.name}")


def build_roster(
    *, allow_live: bool = True, live_auth: LiveAuthorization | None = None
) -> list[RosterEntry]:
    """Build the 3-backend roster from host detection. allow_live=False forces all-mock
    (used by the deterministic test suite).

    The frontier entry consults the LIVE_OPERATION_AUTHORIZED gate (directive §10.1) but
    STAYS MOCK in this sub-step (.liveflag): the live claude_code adapter is not wired yet
    (sub-step .adapter). The gate is recorded now so the barrier already exists the moment a
    live path lands — enforcement-by-absence must not be the only thing keeping live off.
    """
    if live_auth is None:
        live_auth = load_live_authorization()
    frontier_live_ok = live_auth.is_provider_live("claude_code")
    models = detect.ollama_models() if allow_live else []
    have_ollama = bool(models)
    reasoning_model = detect.pick_model(models, _REASONING_MODELS) if have_ollama else None
    coder_model = detect.pick_model(models, _CODER_MODELS) if have_ollama else None
    have_opencode = detect.opencode_available()

    local_reasoning = RosterEntry(
        name="local_reasoning", node_class="worker_reasoning", locality="local", cost_class="local",
        offline_profile_eligible=True, requires_network=False, subscription_backed=False,
        capability_descriptors=[
            {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                         "min_context": 32000, "locality": "any"}},
            {"capability": "review", "requirements": {"structured_output": True, "min_context": 32000}}],
        backend_kind="ollama" if reasoning_model else "mock", model=reasoning_model,
        notes=f"ollama {reasoning_model}" if reasoning_model else "mock (no local reasoning model detected)")

    coding_node = RosterEntry(
        name="coding_node", node_class="worker_coding_specialist", locality="local", cost_class="local",
        offline_profile_eligible=True, requires_network=False, subscription_backed=False,
        # HONEST descriptor (spec-audit F1): today this is a DIRECT local coder (single-shot
        # generate via Ollama), not a driven coding-TUI harness — so it advertises no
        # harness_class. A task that genuinely needs a coding_tui harness must NOT match this
        # node until OpenCode is really driven (the resolver enforces harness_class).
        capability_descriptors=[
            {"capability": "coding", "requirements": {"tool_use": True, "structured_output": True,
                                                      "min_context": 32000, "harness_class": None}}],
        backend_kind="ollama" if coder_model else "mock", model=coder_model,
        harness=None,  # not driving a harness yet; OpenCode programmatic drive deferred
        notes=(f"DIRECT local coder ({'ollama ' + coder_model if coder_model else 'mock coder'}); "
               f"OpenCode binary {'detected' if have_opencode else 'absent'} on host but its "
               "programmatic drive is deferred (interactive TUI) — no harness loop advertised (F1)"))

    mock_frontier = RosterEntry(
        name="mock_frontier", node_class="worker_reasoning", locality="frontier", cost_class="subscription",
        offline_profile_eligible=False, requires_network=True, subscription_backed=True,
        capability_descriptors=[
            {"capability": "reasoning", "requirements": {"tool_use": True, "structured_output": True,
                                                         "min_context": 128000, "locality": "frontier_ok"}},
            {"capability": "synthesis", "requirements": {"structured_output": True, "min_context": 128000}}],
        backend_kind="mock", model=None,
        notes=(
            "mock frontier (default roster). The live claude_code adapter EXISTS as of "
            "phase-14b.adapter (adapters/frontier/claude_code.py) but is spawned ONLY through the "
            "governed live path node_runtime/supervisor/frontier_spawn.py, never from this default "
            "roster — so the deterministic suite stays all-mock. "
            + ("LIVE_OPERATION_AUTHORIZED gate is SATISFIED for claude_code (OP-4/OP-5): a live "
               "terminal would be spawnable via frontier_spawn once operator terms are confirmed."
               if frontier_live_ok else
               "LIVE_OPERATION_AUTHORIZED gate is DENIED (enforcement-by-absence): frontier_spawn "
               "refuses a live terminal; this stays mock.")))

    return [local_reasoning, coding_node, mock_frontier]


def _validate_descriptors(descriptors: list[dict[str, Any]]) -> None:
    """Validate each capability descriptor against the frozen node@1.0 sub-schema (spec-audit
    F4) so a malformed roster is refused at registration, not silently stored."""
    import json
    from pathlib import Path

    import jsonschema
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "node.schema.json"
    node_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    cap_schema = {**node_schema["definitions"]["capability_descriptor"],
                  "$schema": "http://json-schema.org/draft-07/schema#"}
    for d in descriptors:
        jsonschema.validate(d, cap_schema)


def register_roster(registry: Any, roster: list[RosterEntry]) -> None:
    for e in roster:
        _validate_descriptors(e.capability_descriptors)
        registry.register(e.name, e.capability_descriptors, locality=e.locality,
                          cost_class=e.cost_class, offline_profile_eligible=e.offline_profile_eligible)
