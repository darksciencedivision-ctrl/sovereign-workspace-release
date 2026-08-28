"""Phase 14C `.harness` (integration): the REAL OpenCode presence/version probe driven through
the supervised spawn path (node_runtime/supervisor/opencode_spawn).

This is the honest LIVE proof for `.harness`: it actually spawns `opencode --version` (a benign,
local, credential-free subprocess) and admits a supervised harness ONLY if the real presence +
version gate passes. When OpenCode is absent it SKIPS-WITH-RECORD (directive §10.4) — never faked.
OpenCode + Ollama are local (no subscription, no credential), so this live probe is permitted
outright (unlike a frontier live call).
"""
from __future__ import annotations

import pytest
from node_runtime.supervisor.opencode_spawn import OpenCodeUnavailable

from adapters import detect
from adapters.coding.opencode.harness import (
    MIN_OPENCODE_VERSION,
    OpenCodeCliHarness,
)
from node_runtime.supervisor.opencode_spawn import probe_opencode, spawn_opencode_harness

_HARNESS = OpenCodeCliHarness()
_PRESENT = detect.opencode_available() and _HARNESS.executable is not None

pytestmark = pytest.mark.skipif(
    not _PRESENT,
    reason="opencode CLI not present on host — .harness live probe SKIPPED-WITH-RECORD (§10.4)")


def test_live_opencode_version_meets_gate() -> None:
    """A REAL `opencode --version` spawn: present, a parseable version, at/above the minimum."""
    probe = probe_opencode(_HARNESS)  # queries the real CLI + the local Ollama daemon
    assert probe.present is True, probe.detail
    assert probe.version_tuple is not None, f"unparseable live version: {probe.version!r}"
    assert probe.version_tuple >= MIN_OPENCODE_VERSION, probe.version
    assert probe.meets_minimum is True
    assert probe.executable and probe.executable.lower().endswith(("opencode", "opencode.cmd",
                                                                   "opencode.ps1"))


def test_live_supervised_spawn_admits_harness_with_real_version() -> None:
    """The real supervised path admits a harness only after the live presence/version gate passes,
    and issues a supervisor-owned identity (no naked session, invariant 2). Robust to whether a
    local coder model is present: with one, the default gate admits; without, the default gate
    fails closed (§2.3) and only an explicit mock-drive override admits."""
    probe = probe_opencode(_HARNESS)
    require_coder = probe.coder_model is not None
    if not require_coder:
        with pytest.raises(OpenCodeUnavailable):  # no local coder ⇒ default require_coder_model fails closed
            spawn_opencode_harness(
                mcp_client=object(), node_id="oc-live", permission_profile_id="pp-coding",
                workspace_root=".", harness=_HARNESS)
    sup = spawn_opencode_harness(
        mcp_client=object(), node_id="oc-live", permission_profile_id="pp-coding",
        workspace_root=".", harness=_HARNESS, require_coder_model=require_coder)
    assert sup.context.spawned_by_supervisor is True
    assert sup.context.subscription_ref is None  # local: not subscription-governed (no I-X3)
    assert sup.probe.present and sup.probe.meets_minimum
    # the admitted version is the REAL CLI version, not a mock
    assert sup.harness is _HARNESS and "mock" not in (sup.probe.version or "").lower()


def test_live_naked_launch_still_refused_even_when_present() -> None:
    """Presence does not relax the no-naked-session gate: a missing profile is still refused."""
    from adapters.base.contract import NakedLaunchRefused
    with pytest.raises(NakedLaunchRefused):
        spawn_opencode_harness(
            mcp_client=object(), node_id="oc-live", permission_profile_id="",
            workspace_root=".", harness=_HARNESS)
