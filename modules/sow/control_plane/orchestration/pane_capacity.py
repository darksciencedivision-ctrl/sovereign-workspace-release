"""How many worker panes this host can actually hold. EPC-03 L6-4.

The directive's own note on this item:

> **L6-4 matters more than it looks.** Four 8B models cannot be co-resident in 8 GB; a conductor
> that can spawn without a bound will thrash the card. The bound is derived, and it advises the
> operator rather than silently capping him.

MEASURED, from the same host measurements that produced the observation budget. Loading
`qwen3:8b` at four context lengths and reading `/api/ps` and `nvidia-smi`:

    weights   ~4740 MiB for an 8B model at Q4
    KV cache   ~145 MiB per 1k tokens of context, below the spill point
    total       8151 MiB, of which ~1669 MiB was already held by the desktop

The conductor itself occupies a seat. On this card that is ~5900 MiB at an 8192 context, leaving
roughly 580 MiB after the host reserve — which holds ZERO additional 8B workers and about one 3B
worker at a short context. That is precisely why D-2 puts the workers at ≤4B: not a preference,
an arithmetic consequence of the operator's own hardware.

WHAT THE NUMBER MEANS, EXACTLY. It is how many worker models can be VRAM-RESIDENT AT ONCE, which
is the bound on how many workers can be GENERATING at once. It is NOT a limit on how many terminals
may be open. An `ollama run` pane holds no VRAM while it is idle - the daemon unloads a model after
its keep-alive - so a host can carry more open panes than it can carry simultaneous answers, and
the extra ones cost a model swap per turn rather than a refusal.

Getting that distinction wrong in either direction produces a wrong product: bound the terminals by
this number and the operator is told he cannot open a window he plainly can; bound nothing by it
and a conductor dispatches four tasks at once to a card that then pages, which is the thrash the
directive names.

IT ADVISES, IT DOES NOT CAP THE OPERATOR. Same posture as the model-ceiling advisory and for the
same recorded reason (ENTRY 030): a bound derived from hardware is a fact the operator should see,
and his own decision to run past it is his to make. What it DOES cap is a MODEL: the conductor's
spawn requests are bounded here, because a model asking for terminals is not the operator asking
for terminals, and the whole point of D-3 is that a model-initiated spawn passes every gate the
operator's click passes plus this one.
"""
from __future__ import annotations

from typing import Any

#: From `pane_observation`, which carries the measurement and its provenance. Imported rather than
#: re-declared: two copies of a measured constant is how one of them silently goes stale.
from control_plane.orchestration.pane_observation import (
    HOST_VRAM_RESERVE_MIB,
    MEASURED_KV_MIB_PER_1K,
)

#: Weights by nameplate class, MiB, at the Q4-ish quantisations this host actually holds. Read off
#: `ollama list` sizes on 2026-08-31: qwen3:8b 5.23 GB, phi4-mini:3.8b 2.49 GB, llama3.2:3b and
#: qwen2.5:3b-instruct ~2.0 GB. Disk size understates resident size (the KV cache is added below),
#: which is why these are the DISK figures and the cache is counted separately rather than folded
#: in — folding it in would hide which half moved when a number stops matching the host.
_WEIGHTS_MIB: dict[float, int] = {
    3.0: 2_000,
    4.0: 2_500,
    8.0: 4_740,
    14.0: 8_900,
}

#: A worker pane's context. Smaller than the conductor's: a worker answers one task and does not
#: hold a plan, a roster and several panes of observation in its head.
WORKER_NUM_CTX = 4_096


def _weights_for(parameters_b: float) -> int:
    """The nearest measured weight class at or above `parameters_b`.

    Rounding UP is the fail-closed direction: under-estimating a model's footprint produces a
    bound that authorises a pane the card cannot hold, and the operator finds out when the daemon
    starts paging to system RAM — silently, since `/api/ps` still reports the model loaded.
    """
    for nameplate in sorted(_WEIGHTS_MIB):
        if parameters_b <= nameplate:
            return _WEIGHTS_MIB[nameplate]
    largest = max(_WEIGHTS_MIB)
    # Linear extrapolation past the largest measured class, and SAID to be an extrapolation.
    return int(_WEIGHTS_MIB[largest] * (parameters_b / largest))


def pane_footprint_mib(parameters_b: float, num_ctx: int = WORKER_NUM_CTX) -> int:
    """Resident MiB for one pane running a model of this nameplate size at this context."""
    return int(_weights_for(float(parameters_b))
               + (MEASURED_KV_MIB_PER_1K * max(0, int(num_ctx)) / 1_000))


def max_concurrent_panes(
    *,
    vram_mib: int | None = None,
    worker_parameters_b: float = 4.0,
    conductor_parameters_b: float | None = 8.0,
    conductor_num_ctx: int = 8_192,
    worker_num_ctx: int = WORKER_NUM_CTX,
) -> dict[str, Any]:
    """The advised maximum concurrent worker panes, with the whole derivation.

    Returns the figures, not just the number, so a refusal can state its arithmetic instead of
    asserting a limit. Never raises: this runs on a conductor turn and on a display path.
    """
    source = "caller"
    if vram_mib is None:
        try:
            from adapters.local.model_ceiling import hardware_profile  # noqa: PLC0415
            profile = hardware_profile()
            vram_mib = int(profile.get("vram_mib") or 0)
            source = str(profile.get("source") or "hardware_profile")
        except Exception:  # noqa: BLE001 - a display path must not raise
            vram_mib, source = 0, "unavailable"

    vram_mib = int(vram_mib or 0)
    conductor_mib = (pane_footprint_mib(conductor_parameters_b, conductor_num_ctx)
                     if conductor_parameters_b else 0)
    worker_mib = pane_footprint_mib(worker_parameters_b, worker_num_ctx)
    available = vram_mib - HOST_VRAM_RESERVE_MIB - conductor_mib

    if vram_mib <= 0:
        return {
            "max_panes": 1, "measured": False, "vram_mib": 0, "source": source,
            "conductor_mib": conductor_mib, "worker_mib": worker_mib, "available_mib": 0,
            "reason": ("this host's VRAM could not be measured, so the bound is the smallest that "
                       "is still a workspace: one worker pane. This is a refusal to guess, not a "
                       "measurement"),
        }

    panes = max(0, int(available // worker_mib)) if worker_mib > 0 else 0
    reason = (
        f"{vram_mib} MiB VRAM measured by {source}, less a {HOST_VRAM_RESERVE_MIB} MiB host "
        f"reserve and {conductor_mib} MiB for the conductor at {conductor_num_ctx} context, "
        f"leaves {max(0, available)} MiB; a ~{worker_parameters_b:g}B worker at "
        f"{worker_num_ctx} context costs {worker_mib} MiB")
    advice = None
    if panes == 0:
        reason += (" — so no worker can be resident ALONGSIDE the conductor. Terminals still open; "
                   "each answer costs a model swap, which is slow rather than impossible")
        # Name what would change it. A bound of zero that says only "no" is a bound the operator
        # cannot act on, and the two levers are both his to pull.
        shortfall = worker_mib - max(0, available)
        advice = (
            f"a co-resident worker needs {shortfall} MiB more than this slate leaves. The two "
            f"levers: a SMALLER conductor (each nameplate class down frees roughly 2 GiB) or a "
            f"SHORTER conductor context (every 1k tokens costs {MEASURED_KV_MIB_PER_1K:.0f} MiB). "
            f"Neither is taken here — the slate is the operator's to pin")
    return {
        # The bound on simultaneous GENERATION, not on open terminals. See the module docstring:
        # conflating the two produces a wrong product in either direction.
        "max_panes": panes,
        "bounds": "concurrently resident worker models, not open terminals",
        "measured": True, "vram_mib": vram_mib, "source": source,
        "conductor_mib": conductor_mib, "worker_mib": worker_mib,
        "available_mib": max(0, available), "reason": reason, "advice": advice,
    }
