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

from typing import Any

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


# --- SW-ORCH-001 F-20: what the session ACTUALLY got, after it started -------------------------
#
# THE DEFECT, measured on the operator's host 2026-09-05. A 2.2 GB 3B model opened by
# `build_interactive_ollama_command` loaded at **13 GB** with a **131072** context, 56% of it
# resident in system RAM, on a card with 8151 MiB. The daemon sizes an unspecified session to the
# model's architectural maximum, and nothing in this product noticed: the residency gate that
# admitted the pane priced it from `api/tags` DISK size, which carries no KV cache at all. So the
# pane was priced at effectively zero context and ran at 131072, and the operator's report was that
# smaller models were SLOWER than larger ones — which is exactly what a bigger KV spill produces.
#
# WHY THIS IS A VERIFIER AND NOT A COMMAND. `ollama run` exposes no context flag (measured on
# 0.33.3), `/set parameter num_ctx` does not change an already-loading session (measured, twice,
# the second time from a confirmed-cold daemon), and `OLLAMA_CONTEXT_LENGTH` belongs to
# `ollama serve` — a daemon this product ATTACHES to and never spawns. The product therefore cannot
# command the context. What it can do, and what invariant 27 says it must, is OBSERVE the result
# and refuse to present a pane whose session is not what was priced.
#
# Measured for the record, same host, same model, same `ollama run` path, against a daemon started
# with `OLLAMA_CONTEXT_LENGTH=4096`:
#
#     unpinned : context 131072 | 13.0 GB | 56%/44% CPU/GPU   <- what the operator had
#     pinned   : context   4096 |  2.5 GB | 100% GPU          <- fully resident
#
# So the honest posture is: the host is configured, and the product PROVES it per pane rather than
# assuming it. A session that comes back wrong is torn down and refused with both numbers named,
# never left running at an unpriced context.

#: What `/api/ps` must agree on before a local pane is offered to the operator. Exact, not a
#: tolerance: `size_vram < size` is the daemon's own report that part of the model is in system
#: RAM, and "nearly resident" is the state that produced the measurements above.
RESIDENCY_FIELDS = ("name", "model", "size", "size_vram", "context_length")


def classify_session_residency(payload: Any, *, model: str,
                               expected_num_ctx: int) -> dict[str, Any]:
    """Does the running session match what the admission gate priced? Pure, over an `/api/ps` body.

    Pure so the whole decision is pinned headlessly; the caller owns the HTTP read and the teardown.
    Every refusal names the measured numbers, because "the pane did not open" is not an answer an
    operator can act on and "context 131072, 56% on CPU, expected 4096" is.

    Returns a verdict mapping. `ok` is True only when the model is resident, ENTIRELY in VRAM, and
    at exactly the context it was priced at.
    """
    tag = str(model or "").strip()
    if not tag:
        return {"ok": False, "reason": "no model tag to verify — fail closed", "found": False}
    try:
        want_ctx = int(expected_num_ctx)
    except (TypeError, ValueError):
        want_ctx = 0
    if want_ctx <= 0:
        # An unpriced pane cannot be verified, and a verifier that passes when it was given nothing
        # to check is worse than no verifier: it manufactures the assurance it exists to provide.
        return {"ok": False, "found": False,
                "reason": ("no expected context was supplied, so nothing could be verified — a "
                           "local pane must be priced before it is checked (fail closed)")}

    models = (payload or {}).get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return {"ok": False, "found": False,
                "reason": "the daemon's /api/ps answer had no readable model list — fail closed"}

    row = next((m for m in models
                if isinstance(m, dict)
                and tag in (str(m.get("name") or ""), str(m.get("model") or ""))), None)
    if row is None:
        return {"ok": False, "found": False,
                "reason": f"the daemon reports no running session for {tag!r} — fail closed"}

    # F-136(5): the daemon's fields are not guaranteed numeric; int("1.5") / int({}) raised an
    # uncaught ValueError/TypeError. Coerce defensively - a non-numeric field reads as 0.
    def _as_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    size = _as_int(row.get("size"))
    size_vram = _as_int(row.get("size_vram"))
    got_ctx = _as_int(row.get("context_length"))
    cpu_split = size > 0 and size_vram < size
    pct = round(100 * size_vram / size) if size else 0

    verdict = {"ok": False, "found": True, "model": tag,
               "expected_num_ctx": want_ctx, "context_length": got_ctx,
               "size": size, "size_vram": size_vram, "pct_in_vram": pct, "cpu_split": cpu_split}

    if got_ctx != want_ctx:
        verdict["reason"] = (
            f"{tag} is running at context {got_ctx}, not the {want_ctx} it was priced at. The "
            f"daemon decides a session's context and this product does not spawn it, so the fix is "
            f"on the host: start the Ollama service with OLLAMA_CONTEXT_LENGTH={want_ctx}. "
            f"Refusing rather than running a pane whose cost nobody measured")
        return verdict
    if cpu_split:
        verdict["reason"] = (
            f"{tag} is loaded but only {pct}% of it is in VRAM ({size_vram} of {size} bytes) — the "
            f"rest is in system RAM, which is the silent spill that makes a small model slower than "
            f"a large one. Refusing rather than presenting a pane that will crawl")
        return verdict

    verdict["ok"] = True
    verdict["reason"] = (f"{tag} is fully resident ({size_vram} bytes, 100% VRAM) at the "
                         f"{got_ctx} context it was priced at")
    return verdict
