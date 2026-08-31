"""How much of a worker pane a conductor can actually read. EPC-03 L4-3/L4-4.

The shell can now produce a redacted, bounded `pane_observation@1.0` record per pane
(`apps/desktop/control/pane-observation.js`). This module answers the question that record cannot
answer for itself: how much of it fits.

WHY IT IS DERIVED AND NOT WRITTEN DOWN. The conductor's local brain is `qwen3:8b` (D-2), and its
usable context is a function of THIS machine's VRAM, not of a number anyone typed. The same
lesson has now cost this build twice: an 8B model was run at `num_ctx: 131_072`, spilled to 23.2
GB of system RAM on an 8 GB card, and every timed leg measured the swap rather than the model. So
the budget comes from `model_ceiling.hardware_profile()`, the same measured VRAM the ceiling
advisory uses, and the derivation states its own assumptions in the record it returns.

WHY IT IS ADVISORY IN THE SAME SENSE THE CEILING IS. It recommends a budget; it does not select a
model, refuse a pane, or cap the operator. A caller that wants a larger window may ask for one and
gets it with the overrun reported. What is NOT negotiable is the reporting: a window that silently
did not fit is a conductor reasoning from a truncated screen while believing it read the whole one.

WHAT AN OBSERVATION IS NOT. It carries no leg and never becomes one. `_assert_legs_honest` and
`build_acceptance_packet` remain the only things that may say a worker executed anything, and both
are untouched here. Seeing a pane is not being executed on by it - the same distinction
`pane_presence` draws, for the same reason.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

#: The record shape the shell produces. Pinned so a drifted producer is refused rather than
#: silently half-read.
OBSERVATION_SCHEMA = "pane_observation@1.0"

#: Characters per token, measured conservatively. English prose runs ~4; terminal output runs
#: DENSER in tokens per character - paths, hex, punctuation and CamelCase all fragment - so 3.0 is
#: used deliberately. Under-estimating characters-per-token over-estimates the token cost of a
#: window, which errs toward giving the conductor a smaller window than it could hold. That is the
#: recoverable direction: a short window costs context, an overrun costs the whole turn.
CHARS_PER_TOKEN = 3.0

#: What the rest of the turn needs, in tokens, before any pane text is added: the conductor's
#: system prompt and objective, the decomposition instructions, and room for it to ANSWER.
#: `LOCAL_CONDUCTOR_MAX_TOKENS` in `adapters/local/conductor_backend.py` is 2048, which is the
#: answer half; the prompt half is measured against the decomposition prompt that adapter builds.
RESERVED_PROMPT_TOKENS = 1_200
RESERVED_RESPONSE_TOKENS = 2_048

#: The floor. Below this an observation is not worth carrying at all - roughly a dozen lines of
#: terminal output - and a caller is better told that than handed a window it cannot reason from.
MIN_OBSERVATION_CHARS = 600

#: The ceiling on a SINGLE turn's observation budget regardless of hardware. A conductor that
#: reads 32k characters of scrollback is not reasoning about its workers; it is being buried by
#: them, and the useful signal is the tail either way.
MAX_OBSERVATION_CHARS = 8_000


#: MEASURED on the operator's host, 2026-08-31, by loading `qwen3:8b` at four context lengths and
#: reading `/api/ps` and `nvidia-smi` at each (RTX with 8151 MiB total, 1669 MiB already in use):
#:
#:     num_ctx   2048: resident 5030 MiB | in VRAM 5030 MiB | gpu 6830/8151
#:     num_ctx   4096: resident 5320 MiB | in VRAM 5320 MiB | gpu 7120/8151
#:     num_ctx   8192: resident 5900 MiB | in VRAM 5900 MiB | gpu 7339/8151
#:     num_ctx  16384: resident 7450 MiB | in VRAM 5809 MiB | gpu 7249/8151   <- SPILLED
#:
#: Two facts come out of it. The KV cache costs ~145 MiB per 1k tokens below the spill point
#: (~194 above it, as the runtime starts paging), and the weights sit at ~4740 MiB. And 16384 is
#: where this card gives up: 1641 MiB of the model moved to system RAM while `/api/ps` still
#: reported it loaded. That is the exact failure this build has already paid for twice - an 8B
#: model run at `num_ctx: 131_072` spilled to 23.2 GB and every timed leg measured the swap.
#:
#: The first draft of this module carried "roughly 0.5 MiB per 1k tokens", which is ~290x too
#: small and was arithmetic nobody had run. It is replaced by the measurement, and the measurement
#: is written here so the next person can check it rather than trust it.
MEASURED_KV_MIB_PER_1K = 145.0
MEASURED_8B_WEIGHTS_MIB = 4_740

#: What the rest of the machine is holding while the conductor runs - the desktop, the Electron
#: shell, and whatever the operator has open. Measured at 1669 MiB idle on this host and rounded
#: UP, because the direction that hurts is under-reserving: the model spills silently and the
#: daemon still reports it loaded.
HOST_VRAM_RESERVE_MIB = 2_000


def recommended_num_ctx(vram_mib: int | None = None) -> tuple[int, str]:
    """A context length this machine can hold for an 8B conductor, with the reason.

    Derived from the measurements above, not from a written-down constant, and stepped DOWN to a
    standard size so the recommendation is stable across small changes in what else is running.
    """
    if vram_mib is None:
        try:
            from adapters.local.model_ceiling import hardware_profile  # noqa: PLC0415
            profile = hardware_profile()
            vram_mib = int(profile.get("vram_mib") or 0)
            source = str(profile.get("source") or "hardware_profile")
        except Exception:  # noqa: BLE001 - a display/planning path must not raise
            vram_mib, source = 0, "unavailable"
    else:
        vram_mib, source = int(vram_mib), "caller"

    if vram_mib <= 0:
        # Refusing to guess. 8k is Ollama's own conservative default and is stated as such rather
        # than dressed up as a measurement.
        return 8_192, "VRAM could not be measured; falling back to the 8192 default"

    headroom_mib = vram_mib - MEASURED_8B_WEIGHTS_MIB - HOST_VRAM_RESERVE_MIB
    if headroom_mib <= 0:
        # The honest answer on a card that cannot hold an 8B model plus the desktop. 2048 is
        # named rather than 0 because the conductor still has to run; what it must not do is ask
        # for a context this card will silently page to system RAM.
        return 2_048, (
            f"{vram_mib} MiB of VRAM does not hold an 8B model ({MEASURED_8B_WEIGHTS_MIB} MiB) "
            f"plus the {HOST_VRAM_RESERVE_MIB} MiB the rest of the host is using; the smallest "
            f"context keeps it resident rather than spilling")
    tokens = int((headroom_mib / MEASURED_KV_MIB_PER_1K) * 1_000)
    detail = (f"{vram_mib} MiB VRAM measured by {source}, {headroom_mib} MiB left after "
              f"{MEASURED_8B_WEIGHTS_MIB} MiB of weights and a {HOST_VRAM_RESERVE_MIB} MiB host "
              f"reserve, at a measured {MEASURED_KV_MIB_PER_1K:.0f} MiB per 1k tokens")
    for step in (32_768, 16_384, 8_192, 4_096, 2_048):
        if tokens >= step:
            return step, detail
    return 2_048, detail + " — below the smallest standard context, so the floor is used"


def observation_budget(vram_mib: int | None = None, num_ctx: int | None = None) -> dict[str, Any]:
    """The character budget for ALL pane observations in one conductor turn, and why.

    Returns the figures rather than only the answer, so a receipt can show the derivation instead
    of asserting a number. Every field here is measured or declared above; nothing is a literal
    chosen to make an outcome fit.
    """
    if num_ctx is None:
        num_ctx, reason = recommended_num_ctx(vram_mib)
    else:
        num_ctx, reason = int(num_ctx), "caller-supplied num_ctx"

    available_tokens = num_ctx - RESERVED_PROMPT_TOKENS - RESERVED_RESPONSE_TOKENS
    raw_chars = int(max(0, available_tokens) * CHARS_PER_TOKEN)
    chars = max(0, min(raw_chars, MAX_OBSERVATION_CHARS))
    fits = chars >= MIN_OBSERVATION_CHARS
    return {
        "num_ctx": num_ctx,
        "num_ctx_reason": reason,
        "reserved_prompt_tokens": RESERVED_PROMPT_TOKENS,
        "reserved_response_tokens": RESERVED_RESPONSE_TOKENS,
        "chars_per_token": CHARS_PER_TOKEN,
        "total_max_chars": chars if fits else 0,
        "capped_by_ceiling": raw_chars > MAX_OBSERVATION_CHARS,
        "fits": fits,
        "reason": (
            None if fits else
            f"a {num_ctx}-token context leaves {max(0, available_tokens)} tokens after the prompt "
            f"and the response, which is under the {MIN_OBSERVATION_CHARS}-character floor: this "
            f"conductor cannot usefully read its panes and should not pretend to"),
    }


def _is_observation(record: Any) -> bool:
    return (isinstance(record, Mapping)
            and record.get("schema") == OBSERVATION_SCHEMA
            and isinstance(record.get("pane_id"), str))


def observation_evidence(records: Iterable[Any], budget: Mapping[str, Any] | None = None
                         ) -> dict[str, Any]:
    """Fold pane observations into the record the conductor surface carries.

    Deliberately shaped like `presence_feed` and for the same reason: it describes what was SEEN
    and never what was done. There is no `legs` key here and there must never be one - a reviewer
    reading this fold should be able to see in the SHAPE that it cannot make an execution claim.

    A record that does not carry the pinned schema is REFUSED rather than best-effort parsed. A
    drifted producer feeding a conductor half-understood text is worse than a conductor with no
    observation at all, which is a state this fold can express honestly.
    """
    rows = list(records or ())
    accepted = [r for r in rows if _is_observation(r)]
    refused = [
        {"reason": "not a pane_observation@1.0 record",
         "schema": (r.get("schema") if isinstance(r, Mapping) else None)}
        for r in rows if not _is_observation(r)
    ]
    answerable = [r for r in accepted if r.get("answerable") is True]
    total_chars = sum(int(r.get("chars") or 0) for r in answerable)
    redactions = sum(int(r.get("redactions") or 0) for r in answerable)
    kinds = sorted({k for r in answerable for k in (r.get("redaction_kinds") or [])})
    limit = int((budget or {}).get("total_max_chars") or 0)

    return {
        "schema": OBSERVATION_SCHEMA,
        "observed": [
            {"pane_id": r.get("pane_id"), "chars": int(r.get("chars") or 0),
             "truncated": r.get("truncated") is True,
             "dropped_chars": int(r.get("dropped_chars") or 0),
             "redactions": int(r.get("redactions") or 0),
             "redaction_kinds": list(r.get("redaction_kinds") or [])}
            for r in answerable],
        "unanswerable": [
            {"pane_id": r.get("pane_id"), "reason": r.get("reason")}
            for r in accepted if r.get("answerable") is not True],
        "refused": refused,
        "panes_observed": len(answerable),
        "total_chars": total_chars,
        "budget_chars": limit,
        # Reported, never silently corrected. A conductor whose window did not fit is reasoning
        # from a truncated screen, and it must be possible to see that from the receipt.
        "within_budget": bool(limit) and total_chars <= limit,
        "redactions": redactions,
        "redaction_kinds": kinds,
        "note": (
            "An observation is what a pane was SHOWING, redacted and bounded. It is NOT a claim "
            "that any pane executed work: a live worker leg is derived from evidence by the "
            "acceptance packet, and nothing here touches that. Redaction is a net, not a proof - "
            "`redactions` reports what was removed, never that nothing remains."
        ),
    }
