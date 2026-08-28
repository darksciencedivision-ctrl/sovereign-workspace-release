"""C-4 - the heartbeat cadence is derived from the gateway's staleness window,
and until now that dependency lived only in a comment.

`mcp_server/sovereign_tools.py` sets ``DEFAULT_HEARTBEAT_INTERVAL_S = 60.0`` with the note
*"comfortably inside the gateway's 180 s window ... (2 x 60 < 180)"*. The 180 s window it cites
is ``DEFAULT_STALE_AFTER_MS`` (``apps/desktop/control/sovereign-control-server.js``) - a DIFFERENT
language's constant. Nothing in the tree compared them: retune either number and the other keeps
pointing at a window that may no longer exist. This is U460's repaired defect mirrored one pair of
constants over; that unit's mechanical freshness-window pin
(``test_the_freshness_WINDOW_is_the_same_number_on_both_sides``, in
``test_envelope_cross_language_parity.py``) is the donor for this test's shape - read each side's
constant, never trust the comment.

The property is the MARGIN, not either literal: the beat period must fit AT LEAST TWICE inside the
window, so a single missed beat still leaves the next beat inside it. Neither constant is asserted
equal to a magic number here. Retuning either deliberately is allowed; retuning either out of
relationship with its peer across the language boundary is not.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONTROL_SERVER_JS = REPO / "apps" / "desktop" / "control" / "sovereign-control-server.js"


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("host prerequisite missing: node on PATH - install Node.js")
    return node


def _gateway_stale_after_ms() -> int:
    """Ask the PRODUCTION Node module for its constant. Reimplements nothing: the value comes
    from requiring the real module, the same way the shell itself obtains it."""
    probe = "process.stdout.write(String(require(process.argv[1]).DEFAULT_STALE_AFTER_MS));"
    out = subprocess.run(
        [_node(), "-e", probe, str(CONTROL_SERVER_JS)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert out.returncode == 0, (
        f"could not read DEFAULT_STALE_AFTER_MS from {CONTROL_SERVER_JS.name}: {out.stderr.strip()}"
    )
    return int(out.stdout.strip())


def test_the_heartbeat_beat_fits_twice_inside_the_gateway_staleness_window() -> None:
    """C-4: the cross-language margin the interval constant's own comment claims."""
    from mcp_server.sovereign_tools import DEFAULT_HEARTBEAT_INTERVAL_S

    window_ms = _gateway_stale_after_ms()
    interval_ms = DEFAULT_HEARTBEAT_INTERVAL_S * 1000.0
    assert interval_ms * 2 <= window_ms, (
        f"DEFAULT_HEARTBEAT_INTERVAL_S ({DEFAULT_HEARTBEAT_INTERVAL_S}s) no longer fits twice "
        f"inside DEFAULT_STALE_AFTER_MS ({window_ms} ms): a missed heartbeat can now fall outside "
        f"the staleness window, which is exactly the drift the comment beside the constant "
        f"claims cannot happen"
    )


def test_the_js_side_still_exports_the_constant_this_pin_depends_on() -> None:
    """A pin whose input silently vanishes reads as green forever. If the export is renamed this
    must fail LOUDLY rather than let the margin test above pass unasked."""
    assert _gateway_stale_after_ms() > 0
