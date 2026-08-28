"""Subscription concurrency governor (I-X3; Plan §18.2).

One active terminal per subscription/account by default. The supervisor consults this
before spawning a frontier (subscription-backed) node: a spawn against a subscription
already at its allowance is refused with a visible reason. Local-model terminals are not
subscription-bounded and are never governed here. Succession must release the predecessor
terminal before the successor claims it (release() then acquire()).

Deterministic and fail-closed: the recorded allowance defaults to 1 and is only raised on
an EXPLICIT operator-authorized value passed by the caller — never on inference or silence.
The caller (the supervised spawn path) reads that value from the enforced
`LiveAuthorization.terminals_for(provider)` — the PER-PROVIDER allowance, which is the
narrower of the operator's config value and that provider's own code-pinned cap; it is
never a governor default.

OP-6 (2026-07-19, register OP-6): the operator raised the per-subscription allowance to at
most **2 terminals**. The governor enforces that as a HARD CAP here (`MAX_ALLOWANCE`): a
`register_subscription` call requesting more than 2 is REFUSED — a defense-in-depth so no
caller can widen concurrency past the operator ruling even by accident. The cap is
governor-owned and reversible; raising it again requires a new operator authorization and a
code change here, never a config value.

OP-12 (2026-07-31, register OP-12; operator directive s12): two FURTHER subscriptions —
`grok_build_subscription` and `google_antigravity_subscription` — at allowance **1 each**,
never merged with each other or with the OP-6 pair. That ceiling is read from the single
authority that records it (`live_authorization.provider_terminal_cap`) and is enforced here
together with a ref-to-provider binding, because a per-provider cap that a second ref
spelling can sidestep is not a cap.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from control_plane.profiles.live_authorization import (
    ANTIGRAVITY_PROVIDER,
    GROK_PROVIDER,
    provider_terminal_cap,
)

# OP-6 hard cap: the governor never grants more than 2 terminals on one subscription,
# regardless of the allowance a caller passes (I-X3; operator-ordered raise, reversible).
MAX_ALLOWANCE = 2


def provider_allowance_cap(provider: str) -> int:
    """The hardest ceiling this provider can be registered at, in the governor's own terms.

    ONE table, not two. The first version of this function kept its own `PROVIDER_MAX_ALLOWANCE`
    map "as defense in depth" — but the two tables had OPPOSITE fail directions (the authorization
    table answers 0 for an unrecorded provider, this one answered 2), so a future provider added to
    the live scope and to the authorization cap while being forgotten here would have inherited a
    governor ceiling of 2 and the second layer would have defended nothing. Duplication that can
    disagree is not depth, it is drift (invariant 30; spec-audit MEDIUM-4 / MAJOR-3).

    So the per-provider ceiling is read from the single authority that records it, and the layering
    that IS real stays: this function still clamps to the governor-owned `MAX_ALLOWANCE`, and the
    check happens again at the durable ledger. A provider with NO recorded per-provider cap
    (`mock`, local adapters, anything not subscription-scoped) falls back to the global cap — those
    are not subscription-backed and never reach an I-X3 refusal by this route."""
    recorded = provider_terminal_cap(provider)
    return min(MAX_ALLOWANCE, recorded) if recorded else MAX_ALLOWANCE


class SubscriptionLimitExceeded(Exception):
    pass


# The subscription resources OP-12 §12 named literally. Every other provider keeps the derived
# `sub-<provider>` spelling; these two carry the operator's own resource ids because the operator
# directive binds verbatim on governor naming. Distinct keys ⇒ distinct buckets ⇒ never merged.
_OPERATOR_NAMED_SUBSCRIPTION_RESOURCES: dict[str, str] = {
    GROK_PROVIDER: "grok_build_subscription",
    ANTIGRAVITY_PROVIDER: "google_antigravity_subscription",
}


def canonical_subscription_ref(provider: str) -> str:
    """The ONE ref every product path counts a provider's subscription under (U76, Phase 17A `.pty`).

    The cap is enforced PER REF, so two spellings of one real subscription are two independent
    buckets, each "at allowance" — the operator's single Anthropic subscription could hold 2 + 2 —
    and the always-visible n/2 bar would read a different bucket than the one a live session
    actually holds. One deterministic spelling, derived from the adapter/provider id, is the whole
    fix; it is a naming rule, not an authority (the allowance still comes from `LiveAuthorization`).

    OP-12 §12 named its two resources literally (`grok_build_subscription`,
    `google_antigravity_subscription`), so those spellings are honoured verbatim; every other
    provider keeps the derived form, and the existing pair's refs are unchanged."""
    return _OPERATOR_NAMED_SUBSCRIPTION_RESOURCES.get(provider, f"sub-{provider}")


# The inverse: which provider OWNS an operator-named resource. Used to REFUSE a registration whose
# (ref, provider) pair disagrees — see `assert_resource_binding`.
_PROVIDER_OWNING_RESOURCE: dict[str, str] = {
    ref: provider for provider, ref in _OPERATOR_NAMED_SUBSCRIPTION_RESOURCES.items()}


def assert_resource_binding(subscription_ref: str, provider: str) -> None:
    """For the OP-12 resources ONLY: the ref and the provider must be each other's.

    Without this, "capped per provider" was a claim the code did not keep. Two ways to get two
    Grok terminals past the per-provider cap, both found by review and both closed here:
      * register `sub-grok_build` (a second spelling of the same real subscription) alongside
        `grok_build_subscription` — two buckets, each "at allowance" — the U76 defect exactly;
      * re-register `grok_build_subscription` naming `claude_code`, whose cap is 2, which raised
        the Grok bucket's allowance to 2 AND left the status row reporting the wrong provider.
    Scoped deliberately to the operator-NAMED resources: the pre-OP-12 refs are free-form by long
    standing (`sub-anthropic`, `sub-anthropic-01`, …) and tightening them is a separate change with
    its own blast radius, recorded rather than smuggled in here."""
    expected_ref = _OPERATOR_NAMED_SUBSCRIPTION_RESOURCES.get(provider)
    if expected_ref is not None and subscription_ref != expected_ref:
        raise ValueError(
            f"provider {provider!r} may only be counted under its operator-named subscription "
            f"resource {expected_ref!r}, not {subscription_ref!r} (OP-12 §12) — a second ref "
            f"spelling is a second bucket, i.e. a second terminal past the cap (I-X3, U76)")
    owner = _PROVIDER_OWNING_RESOURCE.get(subscription_ref)
    if owner is not None and owner != provider:
        raise ValueError(
            f"subscription resource {subscription_ref!r} belongs to {owner!r} and cannot be "
            f"registered for {provider!r} (OP-12 §12: never merged) — refuse to lend one "
            f"subscription's terminals to another provider (I-X3)")


@dataclass
class _Sub:
    provider: str
    allowance: int = 1
    active: set[str] = field(default_factory=set)  # node_ids currently holding a terminal


class SubscriptionGovernor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, _Sub] = {}

    def register_subscription(self, subscription_ref: str, provider: str, allowance: int = 1) -> None:
        if allowance < 1:
            raise ValueError("allowance must be >= 1")
        if allowance > MAX_ALLOWANCE:
            # fail closed: the governor never grants beyond the operator-ordered OP-6 cap,
            # so a mis-wired or widened caller cannot raise concurrency on inference.
            # (Cross-check: LiveAuthorization._validate_terminals clamps to the same [1, 2];
            # this is the second, independent layer of the same OP-6 bound.)
            raise ValueError(
                f"allowance {allowance} exceeds the governor cap of {MAX_ALLOWANCE} "
                f"(OP-6) — refuse to widen concurrency past the operator ruling (I-X3)")
        provider_cap = provider_allowance_cap(provider)
        if allowance > provider_cap:
            # OP-12 §12: the two new subscriptions are 1 each and are never merged. Refused on the
            # same fail-closed footing as the global cap. The ceiling is enforced per PROVIDER; the
            # ref a caller supplies is bound to that provider separately, below — the two together
            # are what make "cannot buy a second terminal" true rather than merely intended.
            raise ValueError(
                f"allowance {allowance} exceeds the per-provider cap of {provider_cap} for "
                f"{provider!r} (OP-12 §12) — a second terminal on this subscription needs a "
                f"separate operator amendment, never a caller-supplied number (I-X3)")
        assert_resource_binding(subscription_ref, provider)
        with self._lock:
            sub = self._subs.get(subscription_ref)
            if sub is None:
                self._subs[subscription_ref] = _Sub(provider=provider, allowance=allowance)
            elif sub.provider != provider:
                # A ref names ONE subscription. Re-registering it under a different provider used to
                # silently keep the old `provider` in the status row while adopting the new
                # allowance — an observability lie (invariant 27) on top of a concurrency change.
                raise ValueError(
                    f"subscription {subscription_ref!r} is already registered for "
                    f"{sub.provider!r} and cannot be re-registered for {provider!r} — one ref is "
                    f"one subscription (I-X3, invariant 27)")
            else:
                # Re-registration reconciles the allowance to the currently-authorized value
                # (bounded above by MAX_ALLOWANCE) so a mid-session operator NARROWING binds the
                # supervised spawn — a config narrowed to 1 refuses the next acquire. It never
                # evicts a mid-generation holder: if len(active) already exceeds the new
                # allowance, held terminals stay and only FUTURE acquires are refused (fail
                # closed, no mid-generation eviction).
                sub.allowance = allowance

    def acquire(self, subscription_ref: str, node_id: str) -> None:
        """Reserve a terminal for node_id on this subscription, or refuse (fail closed)."""
        with self._lock:
            sub = self._subs.get(subscription_ref)
            if sub is None:
                raise SubscriptionLimitExceeded(
                    f"subscription {subscription_ref!r} not registered — refuse to spawn uncounted (I-X3)")
            if node_id in sub.active:
                return
            if len(sub.active) >= sub.allowance:
                raise SubscriptionLimitExceeded(
                    f"subscription {subscription_ref!r} at allowance {sub.allowance} "
                    f"(active: {sorted(sub.active)}) — one terminal per subscription by default (I-X3)")
            sub.active.add(node_id)

    def release(self, subscription_ref: str, node_id: str) -> None:
        with self._lock:
            sub = self._subs.get(subscription_ref)
            if sub is not None:
                sub.active.discard(node_id)

    def active_count(self, subscription_ref: str) -> int:
        with self._lock:
            sub = self._subs.get(subscription_ref)
            return len(sub.active) if sub else 0

    def status(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {ref: {"provider": s.provider, "allowance": s.allowance,
                          "active": sorted(s.active), "in_use": len(s.active)}
                    for ref, s in self._subs.items()}
