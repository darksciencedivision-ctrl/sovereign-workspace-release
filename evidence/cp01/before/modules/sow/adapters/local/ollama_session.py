"""INTERACTIVE local-model session argv (Phase 17B `.ticket`; directive §16 track 17B, U70).

`adapters/local/worker.py` is the headless local worker (a `LocalWorkerAdapter` driving the Ollama
HTTP API through the governed adapter contract). This module builds the OTHER shape 17B needs: the
argv for an interactive `ollama run <tag>` session the operator can watch and type into in a pane —
the local half of the operator's definition-of-done (c) ("selecting a model on a pane, incl. local
`qwen3:8b`, launches that live worker, governed").

Deliberately tiny and deterministic. Two rules it enforces, both fail-closed:

  * a model TAG is required and must be a tag, not a flag — an argument beginning with `-` would be
    read by the CLI as an option, so a caller cannot smuggle one through the model field;
  * no prompt argument is ever appended — `ollama run <tag>` with a trailing prompt is the one-shot
    mode, and an interactive pane session is the point here.

Locality (invariant 19/20): a local model involves NO subscription and NO credential, so nothing in
this path reads or transmits one — the governance that applies is VRAM residency (invariant 22),
enforced by the caller through the ResidencyPlanner before this argv is ever launched.
"""
from __future__ import annotations

OLLAMA_LOCAL_ADAPTER = "ollama_local"
OLLAMA_RUN_SUBCOMMAND = "run"


def build_interactive_ollama_command(executable: str = "ollama", *, model: str) -> list[str]:
    """Argv for an interactive local session on `model` (an `ollama list` tag, e.g. `qwen3:8b`).

    Pure: it builds argv only — the ConPTY spawn, the residency reservation and the supervised
    admission all stay with the caller."""
    tag = model.strip() if isinstance(model, str) else ""
    if not tag:
        raise ValueError("an interactive local session needs a model tag — fail closed")
    if tag.startswith("-"):
        raise ValueError(
            f"refuse to build an ollama command whose model tag {tag!r} would be read as a flag "
            f"(fail closed)")
    # No `or "ollama"` fallback. That is the `exe = resolved or "claude"` shape the conductor path's
    # `_resolved_binary` gate (worker_pane_spawn, gate `binary_unresolved`) was introduced to close:
    # a blank executable became a BARE NAME the shell PATH-searches at spawn time, so what ran was
    # decided after the gate, by whatever PATH offered — and `ollama` is exactly the basename the
    # shell's allowlist accepts, so nothing downstream would have caught it. Unreachable today only
    # because the one caller resolves first; a fail-open defended solely by its caller is the
    # coupling that gate exists to refuse (spec-audit MINOR-1, 2026-07-26). The parameter default is
    # a STATED choice for callers building illustrative argv; a blank passed in is a producer fault.
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError(
            "an interactive local session needs a resolved executable — a blank one would be "
            "PATH-searched at spawn time, deciding what runs after the gate ran (fail closed)")
    return [executable.strip(), OLLAMA_RUN_SUBCOMMAND, tag]
