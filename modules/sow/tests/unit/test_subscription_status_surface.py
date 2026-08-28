"""phase-15a.statusbar — the READ-ONLY IPC surface that reports the subscription governor's
`n/allowance` count to the shell status bar (directive §11 track 15A).

The surface must (1) report the governor's real count over the read-only `subscription_status` op,
(2) hold NO authorization of its own (I-M2 — it cannot register/acquire/release or raise an
allowance; the governor owns every concurrency decision), and (3) fail closed — a provider fault
surfaces as `{ok: False}` the shell renders as an unknown, never a fabricated count.
"""
from __future__ import annotations

import pytest

from control_plane.ipc.gateway import SubscriptionStatusControlSurface
from control_plane.policy import Identity
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

# role "shell", NOT "operator" — the shell must not self-mint the highest role (invariant 1),
# matching apps/desktop/main.js. The surface ignores identity.role entirely (it holds no
# authorization), so this is for fidelity with the product credential, not a policy dependency.
SHELL = Identity("shell", "shell", "proj")


def _seeded_governor() -> SubscriptionGovernor:
    g = SubscriptionGovernor()
    g.register_subscription("sub-anthropic", provider="claude_code", allowance=2)
    g.acquire("sub-anthropic", node_id="frontier-A")  # 1/2
    g.register_subscription("sub-openai", provider="openai_codex_cli", allowance=2)  # 0/2
    return g


def test_subscription_status_reports_the_real_governor_count() -> None:
    surface = SubscriptionStatusControlSurface(_seeded_governor().status)
    resp = surface.handle(SHELL, {"op": "subscription_status"})
    assert resp["ok"] is True and resp["op"] == "subscription_status"
    result = resp["result"]
    assert result["sub-anthropic"] == {
        "provider": "claude_code", "allowance": 2, "active": ["frontier-A"], "in_use": 1,
    }
    assert result["sub-openai"]["in_use"] == 0 and result["sub-openai"]["allowance"] == 2


def test_health_is_a_universal_liveness_op() -> None:
    surface = SubscriptionStatusControlSurface(_seeded_governor().status)
    resp = surface.handle(SHELL, {"op": "health"})
    assert resp["ok"] is True and resp["result"]["surface"] == "subscription"


def test_unsupported_op_is_refused_read_only_surface() -> None:
    # The surface exposes ONLY {health, subscription_status}. Any write-shaped op is refused —
    # it cannot register/acquire/release or raise an allowance (holds no authorization, I-M2).
    surface = SubscriptionStatusControlSurface(_seeded_governor().status)
    for op in ("acquire", "register_subscription", "release", "raise_allowance", "read_status"):
        resp = surface.handle(SHELL, {"op": op})
        assert resp["ok"] is False
        assert "unsupported op" in resp["error"]


def test_provider_fault_fails_closed_never_fabricates_a_count() -> None:
    def boom() -> dict:
        raise RuntimeError("governor unreachable")

    surface = SubscriptionStatusControlSurface(boom)
    resp = surface.handle(SHELL, {"op": "subscription_status"})
    assert resp["ok"] is False
    assert "RuntimeError: governor unreachable" in resp["error"]
    assert "result" not in resp  # no half-built or fabricated count on a fault


def test_surface_cannot_mutate_the_governor_only_reads() -> None:
    # Prove read-only at the governor level: calling the surface many times never changes the count,
    # and the surface has no method to acquire/register (the only ops are the two read ops above).
    gov = _seeded_governor()
    surface = SubscriptionStatusControlSurface(gov.status)
    before = surface.handle(SHELL, {"op": "subscription_status"})["result"]
    for _ in range(5):
        surface.handle(SHELL, {"op": "subscription_status"})
    after = surface.handle(SHELL, {"op": "subscription_status"})["result"]
    assert before == after
    assert gov.active_count("sub-anthropic") == 1  # unchanged by any number of reads
    assert not hasattr(surface, "acquire") and not hasattr(surface, "register_subscription")
