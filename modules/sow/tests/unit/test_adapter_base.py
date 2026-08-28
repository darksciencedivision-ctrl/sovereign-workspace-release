"""Phase 4: base adapter contract, subscription governor, profile loader (pure/unit)."""
from __future__ import annotations

import pytest

from adapters.base import AdapterCapability, AdapterContext, BaseAdapter, NakedLaunchRefused
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader, ProfileViolation
from node_runtime.supervisor.subscription_governor import (
    SubscriptionGovernor,
    SubscriptionLimitExceeded,
)


class _Dummy(BaseAdapter):
    def capability(self) -> AdapterCapability:
        return AdapterCapability("dummy", "worker_reasoning", "local", True, False, True)

    def export_session_state(self) -> dict:
        return {"ok": True}

    def get_context_status(self) -> dict:
        return {"ready": True}


def _ctx(**kw) -> AdapterContext:
    base = dict(node_id="n1", role="worker", project_id="proj", permission_profile_id="pp-1",
                mcp_credential_id="tok-ref", spawned_by_supervisor=True)
    base.update(kw)
    return AdapterContext(**base)


# ---------- naked-launch refusal (I-C1) ----------

def test_naked_launch_refused_without_supervisor() -> None:
    with pytest.raises(NakedLaunchRefused, match="supervisor"):
        _Dummy(_ctx(spawned_by_supervisor=False))


def test_naked_launch_refused_without_permission_profile() -> None:
    with pytest.raises(NakedLaunchRefused, match="permission profile"):
        _Dummy(_ctx(permission_profile_id=""))


def test_adapter_holds_no_provider_credential_by_default() -> None:
    assert _Dummy(_ctx()).holds_provider_credential() is False


# ---------- subscription governor (I-X3) ----------
# Fixture-sweep note (U530): these governor exercises use "claude_code" because W-65/U505
# made the cap table fail closed - an id with no recorded per-provider cap answers 0 and
# refuses every allowance >= 1. The former "anthropic" spelling was never a recorded
# provider; under the current semantics it is itself a refusal fixture, not a neutral
# stand-in. claude_code carries the recorded OP-6 cap of 2, which is the arithmetic these
# tests assume. The fail-closed absence semantics are pinned where they were repaired
# (tests/unit/test_op12_provider_scope.py, register U505).

def test_one_terminal_per_subscription_by_default() -> None:
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code")
    g.acquire("sub-a", "n1")
    with pytest.raises(SubscriptionLimitExceeded, match="one terminal per subscription"):
        g.acquire("sub-a", "n2")


def test_unregistered_subscription_refused_fail_closed() -> None:
    g = SubscriptionGovernor()
    with pytest.raises(SubscriptionLimitExceeded, match="not registered"):
        g.acquire("sub-x", "n1")


def test_succession_release_then_acquire() -> None:
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code")
    g.acquire("sub-a", "predecessor")
    g.release("sub-a", "predecessor")  # succession releases first
    g.acquire("sub-a", "successor")    # then the successor may claim it
    assert g.active_count("sub-a") == 1


def test_raised_allowance_permits_more() -> None:
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code", allowance=2)  # OP-6 operator-ordered raise
    g.acquire("sub-a", "n1")
    g.acquire("sub-a", "n2")
    with pytest.raises(SubscriptionLimitExceeded):
        g.acquire("sub-a", "n3")


# ---------- subscription governor: OP-6 deep re-inspection (Phase 15A .governor) ----------

def test_governor_hard_caps_allowance_at_two() -> None:
    """OP-6 defense-in-depth: even if a caller passes an allowance above 2, the governor
    REFUSES to register it — concurrency can never be widened past the operator ruling."""
    from node_runtime.supervisor.subscription_governor import MAX_ALLOWANCE
    assert MAX_ALLOWANCE == 2
    g = SubscriptionGovernor()
    with pytest.raises(ValueError, match="exceeds the governor cap"):
        g.register_subscription("sub-a", "claude_code", allowance=3)
    with pytest.raises(ValueError, match="exceeds the governor cap"):
        g.register_subscription("sub-a", "claude_code", allowance=99)
    # nothing was registered on the refused path — fail closed
    assert g.status() == {}


def test_governor_default_allowance_is_one_never_raised_on_inference() -> None:
    """The governor never raises concurrency on its own: the default allowance is 1, and a
    raise to 2 must be an EXPLICIT authorized value the caller passes — never inferred."""
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code")  # no allowance arg -> default 1
    g.acquire("sub-a", "n1")
    with pytest.raises(SubscriptionLimitExceeded, match="one terminal per subscription"):
        g.acquire("sub-a", "n2")


def test_governor_release_before_acquire_at_allowance_two() -> None:
    """Succession at allowance=2 still requires release-before-acquire for the reclaimed slot:
    with both slots held, a third is refused until a predecessor releases one."""
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code", allowance=2)
    g.acquire("sub-a", "a"); g.acquire("sub-a", "b")
    with pytest.raises(SubscriptionLimitExceeded):
        g.acquire("sub-a", "c")
    g.release("sub-a", "a")          # succession releases the predecessor's slot first
    g.acquire("sub-a", "c")          # then the successor may claim it
    assert g.active_count("sub-a") == 2


def test_governor_reregistration_narrowing_binds_no_eviction() -> None:
    """A mid-session operator NARROWING must bind on a long-lived governor (not just a fresh
    one): re-registering the same subscription at a lower allowance refuses the next acquire,
    but never evicts a terminal already held (no mid-generation eviction)."""
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code", allowance=2)
    g.acquire("sub-a", "n1"); g.acquire("sub-a", "n2")
    assert g.active_count("sub-a") == 2
    # operator narrows the authorization to 1 and a re-spawn re-registers
    g.register_subscription("sub-a", "claude_code", allowance=1)
    assert g.status()["sub-a"]["allowance"] == 1  # reconciled, not pinned at 2
    assert g.active_count("sub-a") == 2            # existing holders NOT evicted
    g.release("sub-a", "n1")
    with pytest.raises(SubscriptionLimitExceeded):  # narrowed allowance now binds
        g.acquire("sub-a", "n3")
    assert g.active_count("sub-a") == 1


def test_governor_status_exposes_n_of_allowance_for_status_bar() -> None:
    """status() yields in_use + allowance per subscription — the data the shell status bar
    renders as n/2 (the JS wiring itself is .statusbar, not here)."""
    g = SubscriptionGovernor()
    g.register_subscription("sub-a", "claude_code", allowance=2)
    g.acquire("sub-a", "n1")
    st = g.status()["sub-a"]
    assert st["in_use"] == 1 and st["allowance"] == 2 and st["provider"] == "claude_code"


# ---------- profile loader (I-D2) ----------

FRONTIER = AdapterCapability("conductor_fable5", "conductor", "frontier", False, True, False)
LOCAL = AdapterCapability("opencode_local", "worker_coding_specialist", "local", True, False, True)


def test_offline_profile_excludes_frontier_adapter() -> None:
    loader = ProfileLoader(DeploymentProfile("offline_airgapped"))
    with pytest.raises(ProfileViolation, match="excluded from the offline"):
        loader.check_eligible(FRONTIER)


def test_offline_profile_admits_local_adapter() -> None:
    ProfileLoader(DeploymentProfile("offline_airgapped")).check_eligible(LOCAL)


def test_hybrid_profile_admits_frontier() -> None:
    ProfileLoader(DeploymentProfile("hybrid")).check_eligible(FRONTIER)


def test_unknown_profile_fails_closed() -> None:
    with pytest.raises(ProfileViolation, match="unknown deployment profile"):
        ProfileLoader(DeploymentProfile("banana"))


def test_assert_startup_checks_whole_roster() -> None:
    loader = ProfileLoader(DeploymentProfile("offline_airgapped"))
    with pytest.raises(ProfileViolation):
        loader.assert_startup([LOCAL, FRONTIER])  # one ineligible member aborts startup
