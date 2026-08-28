"""phase-15a.statusbar — pin the status-bar view model's JS constants to their Python authorities.

The status-bar view model (terminal/statusbar/statusbar-model.js) necessarily re-declares two
values in JS that are authoritatively owned in Python:
  * LIVE_PROVIDERS   ← control_plane/nodes/pane_picker.py `registered_frontier_providers()`
  * SUBSCRIPTION_CAP ← node_runtime/supervisor/subscription_governor.py `MAX_ALLOWANCE` (OP-6)

A comment linking them is not enough: if a future operator ruling changes the authorized provider
set or raises the governor cap (both code changes), a stale JS mirror would MISREPRESENT the
authorized scope in the shell status bar — for the cap, an UNDERSTATEMENT of the real ceiling. These
tests parse the literals out of the JS source and assert they equal the Python authorities, so the
mirror cannot silently drift (spec-audit MINOR M1/M2). This is a structural pin, not a runtime dep.

**Which authority (18B `.scope`).** The provider pin used to read
`live_authorization._AUTHORIZED_PROVIDERS`. OP-12 made those two sets differ: four ids are now
covered by a recorded operator ruling, but only two can be SELECTED in a pane and therefore only
two have a subscription counter to render. Pinning the bar to the wider set would have demanded a
`grok_build` counter for a provider no pane can spawn — advertising a lease the product cannot
take. The pin now tracks the picker's frontier registration set, so it goes red exactly when the
18B picker sub-step wires the new providers and the JS mirror is not updated with it.
"""
from __future__ import annotations

import re
from pathlib import Path

from control_plane.nodes.pane_picker import registered_frontier_providers
from control_plane.profiles.live_authorization import (
    authorized_providers,
    provider_terminal_cap,
)
from node_runtime.supervisor.subscription_governor import (
    MAX_ALLOWANCE,
    canonical_subscription_ref,
)

_REPO = Path(__file__).resolve().parents[2]
_MODEL_JS = _REPO / "terminal" / "statusbar" / "statusbar-model.js"


def _js_source() -> str:
    return _MODEL_JS.read_text(encoding="utf-8")


def test_js_subscription_cap_matches_governor_max_allowance() -> None:
    m = re.search(r"const SUBSCRIPTION_CAP\s*=\s*(\d+)\s*;", _js_source())
    assert m is not None, "SUBSCRIPTION_CAP literal not found in statusbar-model.js"
    assert int(m.group(1)) == MAX_ALLOWANCE, (
        f"status-bar display cap {m.group(1)} != governor MAX_ALLOWANCE {MAX_ALLOWANCE}; "
        "update terminal/statusbar/statusbar-model.js when the OP-6 cap changes")


def test_js_live_providers_match_the_selectable_frontier_set() -> None:
    m = re.search(r"const LIVE_PROVIDERS\s*=\s*\[([^\]]*)\]", _js_source())
    assert m is not None, "LIVE_PROVIDERS array not found in statusbar-model.js"
    js_providers = set(re.findall(r'"([^"]+)"', m.group(1)))
    expected = set(registered_frontier_providers())
    assert js_providers == expected, (
        f"status-bar LIVE_PROVIDERS {sorted(js_providers)} != selectable frontier providers "
        f"{sorted(expected)}; update statusbar-model.js when the picker's provider set changes")


def test_the_bar_shows_no_counter_for_a_provider_no_pane_can_spawn() -> None:
    """The narrower authority is a claim about the product, so it is asserted as one: every id the
    bar renders must be BOTH covered by an operator ruling AND selectable. Since 18B `.picker` the
    OP-12 pair IS selectable, so the assertion is the same shape with a different expected answer —
    the bar tracks selectability, whichever way that goes."""
    selectable = set(registered_frontier_providers())
    assert selectable <= set(authorized_providers()), (
        "the picker offers a frontier provider no operator ruling authorizes — fail closed")
    js_providers = set(re.findall(r'"([^"]+)"',
                                  re.search(r"const LIVE_PROVIDERS\s*=\s*\[([^\]]*)\]",
                                            _js_source()).group(1)))
    for provider in ("grok_build", "google_antigravity"):
        assert (provider in js_providers) == (provider in selectable)


def test_js_per_provider_display_ceiling_matches_the_python_caps() -> None:
    """U255. The bar's idle/unknown rows show a ceiling for a subscription the governor has not
    registered yet. A single global 2 overstated both OP-12 subscriptions (real cap 1 each, never
    merged — operator directive §12) in exactly the surface §14 governs. The JS map must equal the
    Python authority for every provider the bar renders."""
    src = _js_source()
    block = re.search(r"const PROVIDER_ALLOWANCE\s*=\s*\{([^}]*)\}", src)
    assert block is not None, "PROVIDER_ALLOWANCE map not found in statusbar-model.js"
    js_caps = {m.group(1): int(m.group(2))
               for m in re.finditer(r"(\w+)\s*:\s*(\d+)", block.group(1))}
    expected = {p: provider_terminal_cap(p) for p in registered_frontier_providers()}
    assert js_caps == expected, (
        f"status-bar PROVIDER_ALLOWANCE {js_caps} != per-provider caps {expected}; update "
        "terminal/statusbar/statusbar-model.js when an operator amendment changes an allowance")
    assert all(v >= 1 for v in js_caps.values()), "a display ceiling below 1 hides a real terminal"


def test_js_subscription_ref_map_matches_the_canonical_python_spelling() -> None:
    """The shell's ticket validator refuses a frontier ticket counted against the wrong ref. OP-12
    §12 named its two resources literally, so the derived `sub-<adapter>` form is no longer true for
    every provider — and a wrong ref here would refuse every well-formed ticket for that provider
    (or, worse in the other direction, accept one counted in a bucket nothing else reads: U76)."""
    src = (_REPO / "apps" / "desktop" / "picker" / "launch-source.js").read_text(encoding="utf-8")
    block = re.search(r"const ADAPTER_SUBSCRIPTION_REF\s*=\s*\{([^}]*)\}", src)
    assert block is not None, "ADAPTER_SUBSCRIPTION_REF map not found in launch-source.js"
    js_refs = {m.group(1): m.group(2)
               for m in re.finditer(r'(\w+)\s*:\s*"([^"]+)"', block.group(1))}
    expected = {p: canonical_subscription_ref(p) for p in registered_frontier_providers()}
    assert js_refs == expected, (
        f"launch-source ADAPTER_SUBSCRIPTION_REF {js_refs} != canonical refs {expected}")
