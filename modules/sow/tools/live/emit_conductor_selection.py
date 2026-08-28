"""Authoritative CONDUCTOR selection feed — Phase 16C `.selection` (directive §15 track 16C; OP-10).

Closes **U65**. The shell renders pane-1's CONDUCTOR badge + Resume→Select control. Until now it
read those from hand-maintained literals in `apps/desktop/main.js` that MUST mirror
`control_plane.conductor.selection.OPERATOR_SELECTED_CONDUCTOR` — a drift risk the register flagged
(U65): a copy the operator's authority could silently disagree with.

This tool is the ONE authority the shell sources from instead. It imports the operator's conductor
SELECTION and the succession affordance from their canonical modules and emits them as a stable JSON
contract (`conductor_selection_feed@1.0`). The shell renders exactly what Python holds; the two can
no longer drift. This mirrors the 16B picker read-source pattern (`enumerate_pane_picker --emit-picker`
→ `apps/desktop/picker/source.js`): the option/record set is produced by ONE Python authority and
rendered verbatim by the shell.

Honesty (invariant 3, §6/§10.4): the feed is the honest PRE-LAUNCH binding — the selection LABEL
("fable-5"), `executing.model` None, `verified` False. Nothing has executed yet; a live checkpoint is
recorded only when a live reply reports one (that is the later `.spawn`/`.dispatch` work). Read-only:
the executed path makes no model call, no credential access, no network (§2.2/§2.4) — it imports two
records via their canonical modules and prints them. (The succession affordance is imported from
`conductor_pane_spawn`, whose transitive import graph is heavier than these two leaf records; that is
an import-graph shape, not a runtime call — U71 tracks relocating the pure builder to a leaf module.)

`--emit-conductor-selection` prints ONLY the feed JSON (the stable shell contract, one line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Run as a script (`py -3.12 tools/live/emit_conductor_selection.py`), Python puts the SCRIPT dir on
# sys.path, not the repo root — so the repo imports below would fail. Bootstrap the root exactly as
# tools/live/enumerate_pane_picker.py does (the 16B read-source), so the shell can invoke it directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control_plane.conductor.selection import (  # noqa: E402  (path bootstrap must precede repo imports)
    OPERATOR_SELECTED_CONDUCTOR,
    ConductorSelection,
    bind_conductor_selection,
)
from adapters.frontier.claude_model_probe import (  # noqa: E402
    ModelProbeLedger,
    resolve_launch_model,
)
from node_runtime.supervisor.conductor_pane_spawn import conductor_succession_affordance  # noqa: E402
from control_plane.conductor.registry import (  # noqa: E402
    ConductorDescriptor,
    load_runtime_conductor_descriptor,
)
from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER  # noqa: E402

#: Pinned so the shell source can validate the shape it parses (a drifted producer is refused).
CONDUCTOR_SELECTION_FEED_SCHEMA = "conductor_selection_feed@1.0"


def build_conductor_selection_feed(
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    *,
    probe_ledger: ModelProbeLedger | None = None,
    descriptor: ConductorDescriptor | None = None,
) -> dict[str, Any]:
    """The authoritative CONDUCTOR badge + succession feed the shell renders.

    `selection_record` is `bind_conductor_selection(selection).as_record()` — the pre-launch binding:
    `selection` is the operator LABEL, `executing.model` is None and `verified` is False (nothing has
    run; invariant 3). `succession` is `conductor_succession_affordance(selection)` — the Resume→Select
    control (invariant 28 / OP-8 §13.7). BOTH come from their canonical sources, so the shell cannot
    drift from the operator's authority (the U65 fix).

    Phase 17A `.roundtrip`: the badge also carries the recorded MODEL PROBE verdict, read offline
    from the host ledger. Without it `is_fallback` was structurally always False — on a host whose
    CLI rejects the operator's label, the badge read "fable-5" while pane 1 ran the vendor default.
    That is the exact silence directive §11 15B / §16 17A forbid ("unavailable ⇒ recorded fallback,
    SURFACED, never silent"). An unprobed or inconclusive host is unchanged (label verbatim)."""
    desc = descriptor
    if desc is not None:
        selection = ConductorSelection(
            model=desc.model_id, reason="operator_selected",
            since="2026-08-02T00:00:00+00:00", adapter=desc.adapter_id,
            subscription_ref=desc.subscription_ref)
    resolution = (resolve_launch_model(selection.model, ledger=probe_ledger)
                  if selection.adapter == CLAUDE_CODE_ADAPTER else {
                      "label": selection.model,
                      "model": selection.model,
                      "model_available": True,
                      "source": "registered-exact-slug",
                      "record": None,
                  })
    binding = bind_conductor_selection(
        selection, requested_model=resolution["model"] if resolution["model"] else None,
        model_available=resolution["model_available"])
    return {
        "schema": CONDUCTOR_SELECTION_FEED_SCHEMA,
        "selection_record": binding.as_record(),
        "succession": conductor_succession_affordance(selection),
        # WHERE the badge's slug came from — the same block the launch ticket carries.
        "model_probe": {k: v for k, v in resolution.items() if k != "record"},
        "conductor_descriptor": desc.as_dict() if desc is not None else None,
    }


def main(argv: list[str]) -> int:
    """CLI: `--emit-conductor-selection` prints the feed as one JSON line and exits 0. Any other
    invocation prints usage to stderr and exits 2 (fail-closed — the shell source treats a non-zero
    exit as "unavailable" and renders the honest unknown badge, never a fabricated selection)."""
    if "--emit-conductor-selection" in argv:
        sys.stdout.write(json.dumps(build_conductor_selection_feed(
            descriptor=load_runtime_conductor_descriptor())) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_conductor_selection.py --emit-conductor-selection\n"
        "  prints the authoritative conductor_selection_feed@1.0 JSON the shell renders (U65).\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
