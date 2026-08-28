"""Deployment-profile loader — fail-closed adapter eligibility (Plan §9.10; I-D1/I-D2, TB-6).

Deployment modes (offline_airgapped / hybrid / cloud) share one identical Sovereign
contract; only adapter/client eligibility and the `network` setting differ (D-ARCH-01).
The loader's one job: under the offline/air-gapped profile, refuse to instantiate any
adapter that requires network or is not offline-eligible (Codex, cloud frontier models,
CoWork, and — today — the frontier conductor path). It aborts BEFORE the node spawns and
logs the violation; startup fails closed (T11).
"""
from __future__ import annotations

from dataclasses import dataclass

from adapters.base.contract import AdapterCapability
from control_plane.profiles.live_authorization import LiveAuthorization, LiveAuthorizationError

_PROFILES = {
    "offline_airgapped": "none",
    "hybrid": "egress_controlled",
    "cloud": "open",
}


class ProfileViolation(Exception):
    pass


@dataclass(frozen=True)
class DeploymentProfile:
    profile_id: str

    @property
    def network(self) -> str:
        if self.profile_id not in _PROFILES:
            raise ProfileViolation(f"unknown deployment profile {self.profile_id!r}")
        return _PROFILES[self.profile_id]

    @property
    def is_airgapped(self) -> bool:
        return self.profile_id == "offline_airgapped"


class ProfileLoader:
    def __init__(self, profile: DeploymentProfile) -> None:
        self._profile = profile
        _ = profile.network  # validate the id eagerly, fail closed on unknown

    @property
    def profile(self) -> DeploymentProfile:
        return self._profile

    def check_eligible(self, cap: AdapterCapability) -> None:
        """Raise ProfileViolation if this adapter may not run under the active profile."""
        if self._profile.is_airgapped and (cap.requires_network or not cap.offline_profile_eligible):
            raise ProfileViolation(
                f"adapter {cap.adapter!r} (requires_network={cap.requires_network}, "
                f"offline_profile_eligible={cap.offline_profile_eligible}) is excluded from the "
                f"offline/air-gapped profile — startup fails closed (I-D2)")

    # The reserved mock-backend sentinel — the sole `adapter` enum value in node.schema.json
    # (Plan §9.1) that names no real provider. Keying the live gate on a DENYLIST of this one
    # sentinel is deliberately fail-closed: ANY other subscription-backed adapter — including a
    # provider added to the enum later — is treated as a real live path and requires
    # authorization. (`subscription_backed` alone cannot be the signal: the mock conductor is
    # subscription-backed by node class yet has no live backend — adapters/conductor/adapter.py.)
    _MOCK_ADAPTER = "mock"

    @classmethod
    def _is_live_subscription(cls, cap: AdapterCapability) -> bool:
        """A REAL live frontier adapter: subscription-backed and not the reserved mock sentinel.
        Mock backends carry no live provider call and need no live authorization."""
        return cap.subscription_backed and cap.adapter != cls._MOCK_ADAPTER

    def check_live_authorized(
        self, cap: AdapterCapability, live_auth: LiveAuthorization | None
    ) -> None:
        """Refuse to start a REAL subscription-backed frontier adapter unless live operation
        is authorized for its provider (directive §10.1/§11; register OP-6, superseding
        OP-4/OP-5). Fail closed: a missing authorization is a denial, never a permit."""
        if not self._is_live_subscription(cap):
            return
        if live_auth is None:
            raise ProfileViolation(
                f"live subscription adapter {cap.adapter!r} requested with no LIVE_OPERATION_"
                f"AUTHORIZED gate supplied — startup fails closed (directive §10.1/§11, OP-6)")
        try:
            live_auth.assert_provider_live(cap.adapter)
        except LiveAuthorizationError as exc:
            raise ProfileViolation(str(exc)) from exc

    def assert_startup(
        self, caps: list[AdapterCapability], live_auth: LiveAuthorization | None = None
    ) -> None:
        """Validate the whole requested roster before any node spawns: profile eligibility
        for every adapter, and live authorization for any real subscription-backed frontier."""
        for cap in caps:
            self.check_eligible(cap)
            self.check_live_authorized(cap, live_auth)
