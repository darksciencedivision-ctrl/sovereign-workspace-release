"""LIVE_OPERATION_AUTHORIZED — the enforced, fail-closed gate that must exist BEFORE any
live frontier path (directive §10.1 / §11; register OP-4/OP-5 → **OP-6**; Phase 15A `.liveauth`).

Rationale (directive §10.1): for the entire staged build the frontier adapters ran in mock
mode, so "live operation" was impossible simply because no live path existed —
enforcement-by-absence. The moment a live adapter is wired that natural barrier is gone, so
an EXPLICIT authorization must already fence it. This module is that fence: no live call is
made here.

Phase-15 rewrite (register **OP-6**, 2026-07-19): the operator authorized live multi-model
orchestration across **two** providers under their existing subscriptions and raised the
concurrency allowance to **2 terminals per subscription** by explicit direction (I-X3 was
formally verified-at-1; the raise is operator-ordered, governor-capped, reversible). The
scope this module pins therefore moves from `{provider: claude_code, terminals: 1}` (OP-4)
to `{providers: [claude_code, openai_codex_cli], terminals_per_subscription: 2}` (OP-6).

Phase-18B extension (register **OP-12**, 2026-07-31; directive §17): the operator authorized
two FURTHER live frontier providers — `grok_build` (CLI `grok`) and `google_antigravity`
(CLI `agy`) — each with its own subscription resource at **allowance 1**, never merged with
the other and never merged with the OP-6 pair (operator directive §12). Because the scope is
code-pinned, that authorization had to be written HERE before the operator's own live switch
could name either provider: U237 recorded that the previously-published instruction ("extend
`config/live_operation.json`") was impossible against the OP-6-pinned loader, which raised on
any other id and would have denied `claude_code` too. This module is that missing extension.

Provider identity for the OP-6 pair is the **frozen `node.schema.json` adapter enum**
(schemas/ is the single source of truth): `claude_code` and `openai_codex_cli`. The
operator/directive shorthand "codex" is accepted as an alias and normalized to the canonical
schema id, so `assert_provider_live(cap.adapter)` — called by the profile loader and the
supervised spawn path with the schema enum value — works directly.

**U227, and its resolution — stated rather than papered over.** Through 18B/18C: node@1.0's
`adapter` enum had NO member for either OP-12 provider, the enum is frozen (Phase-0 manifest)
*and* pinned by Architecture Plan §9.1, so neither this module nor any other could add one, and
a schema-valid node RECORD naming either provider was impossible. **The operator ruled on
2026-08-01 (OP-12.1, directive §17.1): by SUCCESSOR SCHEMA** — `schemas/node.schema@1.1.json`
admits both ids (and `ollama_local`, U254) while `@1.0` and Plan §9.1 stay untouched, which is
why directive §17's untouchable set is honoured rather than routed around. Nothing here ever
fabricated a false member, and nothing here changes with the ruling: **the ids in this module are
still product-layer authorization scope, and admitting a vocabulary is not authorizing a call.**
Live scope is what this file decides, and only the operator's config plus the pinned rows below
decide it.

Scope is fixed by the operator ruling, not by the config file. The config names ONE
authorizing register row and gets exactly that row's provider set:
  - **OP-6**  -> {claude_code, openai_codex_cli}          (unchanged, operator-reaffirmed)
  - **OP-12** -> the OP-6 pair PLUS {grok_build, google_antigravity}
A provider outside the cited row's set is refused — a config can neither widen a row nor
borrow another row's scope, and a provider no row authorizes needs a NEW operator ruling.
Terminals: at most **2** per subscription globally (a config may narrow to 1, never widen),
and each provider is further capped by its own code-pinned allowance — 1 for both OP-12
providers, so an operator config that says 2 still yields 1 for those two.

Fail-closed everywhere: absence -> DENIED (not authorized); malformed / out-of-scope ->
raise (never silently authorize, never silently downgrade to permit; never WIDEN beyond the
code-pinned scope). Deterministic permission logic — never model output (Buildout Directive §4).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_CONFIG_VERSION = "1.1"                   # scope shape changed at OP-6 (multi-provider); 1.0 configs fail closed

# The OP-12 product-layer provider ids (operator directive §§1, 8, 12). NOT node@1.0 adapter enum
# members — see the U227 paragraph in the module docstring; exported so no other module has to
# spell them as literals (a literal in two places is how `ollama_local`-class drift starts).
GROK_PROVIDER = "grok_build"
ANTIGRAVITY_PROVIDER = "google_antigravity"

# The authorizing register row -> the provider set THAT ROW authorizes. A config cites exactly one
# row and receives exactly that row's set: rows do not lend each other scope, and a row this table
# does not know is refused. OP-12 is ADDITIVE (directive §17: "existing providers' allowances
# unchanged … operator-reaffirmed"), which is why it repeats the OP-6 pair rather than replacing it.
_PROVIDER_SCOPE_BY_ROW: dict[str, frozenset[str]] = {
    "OP-6": frozenset({"claude_code", "openai_codex_cli"}),
    "OP-12": frozenset({"claude_code", "openai_codex_cli", GROK_PROVIDER, ANTIGRAVITY_PROVIDER}),
}
# Every id ANY row can authorize (never itself a permit — membership here only means "some
# operator ruling covers this"; `is_provider_live` still requires the loaded config's row).
_AUTHORIZED_PROVIDERS = frozenset().union(*_PROVIDER_SCOPE_BY_ROW.values())
# operator/directive shorthand -> canonical schema id (deterministic normalization, not a widening).
# Deliberately NOT extended for the OP-12 providers: "gemini" is ambiguous (node@1.0 carries a
# different member spelled `gemini_cli` — the retired personal-account CLI operator directive
# §4.2/§14 forbids falling back to) and "grok" is a runner PARAMETER spelling, not an identity.
# Ambiguity in permission logic fails closed here by having no alias at all.
_PROVIDER_ALIASES = {"codex": "openai_codex_cli"}
_MAX_TERMINALS_PER_SUBSCRIPTION = 2       # OP-6 (was 1 under OP-4/I-X3); governor-capped, reversible
# Per-provider terminal allowance, code-pinned (operator directive §12: "Default allowance: 1
# active terminal per provider subscription. Do not combine Grok and Google into one lease. Do not
# raise concurrency because the user has a paid plan."). A provider absent from this map has NO
# allowance — fail closed, so a new id cannot inherit somebody else's concurrency by omission.
_PROVIDER_TERMINAL_CAP: dict[str, int] = {
    "claude_code": _MAX_TERMINALS_PER_SUBSCRIPTION,          # OP-6, operator-reaffirmed at OP-12
    "openai_codex_cli": _MAX_TERMINALS_PER_SUBSCRIPTION,     # OP-6, operator-reaffirmed at OP-12
    GROK_PROVIDER: 1,                                        # OP-12 §12 — a separate amendment to raise
    ANTIGRAVITY_PROVIDER: 1,                                 # OP-12 §12 — never merged with Grok's
}
_ENV_OVERRIDE = "SOVEREIGN_LIVE_OPERATION_CONFIG"
# repo-root default; the real file is gitignored, so a fresh clone is DENIED-by-absence.
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "live_operation.json"


class LiveAuthorizationError(Exception):
    """Live operation was requested but is not authorized (fail closed)."""


def authorizing_register_rows() -> tuple[str, ...]:
    """The register rows that authorize a live scope, deterministically ordered. Public because
    U230 found the recon engine reading `_AUTHORIZED_PROVIDERS` through a private name: a rename
    degraded closed, but the coupling was undeclared. This and `authorized_providers` are the
    declared surface."""
    return tuple(sorted(_PROVIDER_SCOPE_BY_ROW))


def authorized_providers(register_row: str | None = None) -> frozenset[str]:
    """The providers a given operator ruling authorizes; with no argument, the union over every
    row (i.e. "some recorded ruling covers this id" — NOT a permit; only a loaded
    `LiveAuthorization` grants one). An unknown row RAISES rather than answering "none", because
    a silent empty set reads as a scope answer when it is really a lookup failure."""
    if register_row is None:
        return _AUTHORIZED_PROVIDERS
    scope = _PROVIDER_SCOPE_BY_ROW.get(register_row) if isinstance(register_row, str) else None
    if scope is None:
        raise LiveAuthorizationError(
            f"register row {register_row!r} authorizes no live scope; known rows are "
            f"{list(authorizing_register_rows())} — fail closed")
    return scope


def provider_terminal_cap(provider: str) -> int:
    """The code-pinned maximum terminals this provider may EVER hold on one subscription,
    independent of any config (operator directive §12). An id with no recorded allowance gets 0 —
    a new provider cannot inherit another's concurrency by omission."""
    return _PROVIDER_TERMINAL_CAP.get(_canonical_provider(provider), 0)  # type: ignore[arg-type]


def _canonical_provider(name: object) -> object:
    """Normalize an operator/directive shorthand to the canonical schema adapter id.
    Non-strings pass through unchanged so the caller's isinstance/membership guard fails closed."""
    if isinstance(name, str):
        return _PROVIDER_ALIASES.get(name, name)
    return name


@dataclass(frozen=True)
class LiveAuthorization:
    """The resolved, immutable authorization state. Constructed only by the loader (valid
    config) or `denied()` (fail-closed default); its scope cannot be widened after load."""

    authorized: bool
    providers: frozenset[str]
    terminals_per_subscription: int
    register_row: str | None
    source: str
    reason: str

    @classmethod
    def denied(cls, reason: str) -> "LiveAuthorization":
        return cls(authorized=False, providers=frozenset(), terminals_per_subscription=0,
                   register_row=None, source="(none)", reason=reason)

    def is_provider_live(self, provider: str) -> bool:
        """True only if live operation is authorized AND this is one of the scoped providers.
        Accepts the canonical schema id or the "codex" shorthand alias."""
        return self.authorized and _canonical_provider(provider) in self.providers

    def assert_provider_live(self, provider: str) -> None:
        """The gate every live-spawn path MUST call before invoking a live provider.
        Raises unless live operation is authorized for this provider."""
        if not self.is_provider_live(provider):
            raise LiveAuthorizationError(
                f"live operation not authorized for provider {provider!r}: {self.reason} "
                f"(register {self.register_row!r}, scoped providers {sorted(self.providers)!r}) — "
                f"fail closed (directive §10.1/§11/§17; authorizing row "
                f"{self.register_row or 'none'})")

    def terminals_for(self, provider: str) -> int:
        """The allowance the governor must be registered with FOR THIS PROVIDER — the narrower of
        the operator's config value and the provider's own code-pinned cap (operator directive
        §12). Zero when this provider is not live, so a caller that skipped the gate cannot
        register an uncounted subscription: the governor refuses allowance < 1."""
        if not self.is_provider_live(provider):
            return 0
        return min(self.terminals_per_subscription, provider_terminal_cap(provider))

    def as_dict(self) -> dict[str, object]:
        return {"authorized": self.authorized, "providers": sorted(self.providers),
                "terminals_per_subscription": self.terminals_per_subscription,
                # the per-provider view, because a single global number stopped being the whole
                # truth at OP-12 (grok/antigravity are capped at 1 under a config that says 2)
                "terminals_by_provider": {p: self.terminals_for(p) for p in sorted(self.providers)},
                "register_row": self.register_row, "source": self.source, "reason": self.reason}


def _resolve_path(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(_ENV_OVERRIDE)
    if env:
        return Path(env)
    return _DEFAULT_PATH


def load_live_authorization(path: Path | str | None = None) -> LiveAuthorization:
    """Read and validate the live-operation config, fail-closed.

    Resolution order: explicit `path` > env `SOVEREIGN_LIVE_OPERATION_CONFIG` > repo default
    `config/live_operation.json`. Absence -> DENIED (enforcement-by-absence). A present file
    that is malformed or out of the OP-6 scope RAISES — it is never coerced into a permit,
    never silently downgraded, and never allowed to WIDEN beyond the code-pinned scope.
    """
    resolved = _resolve_path(path)
    if not resolved.exists():
        return LiveAuthorization.denied(
            f"no live-operation config at {resolved} (enforcement-by-absence)")

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise LiveAuthorizationError(
            f"live-operation config {resolved} is unreadable/malformed: {exc} — fail closed") from exc

    if not isinstance(raw, dict):
        raise LiveAuthorizationError(f"live-operation config {resolved} is not a JSON object — fail closed")

    version = raw.get("config_version")
    if version != _CONFIG_VERSION:
        raise LiveAuthorizationError(
            f"live-operation config version {version!r} != required {_CONFIG_VERSION!r} — fail closed")

    if "live_operation_authorized" not in raw:
        raise LiveAuthorizationError("live-operation config missing 'live_operation_authorized' — fail closed")
    flag = raw["live_operation_authorized"]
    if not isinstance(flag, bool):
        raise LiveAuthorizationError(
            f"'live_operation_authorized' must be a bool, got {type(flag).__name__} — fail closed")

    if flag is False:
        return LiveAuthorization.denied(f"live operation explicitly disabled in {resolved}")

    # flag is True: every scope field must be present AND lie within the cited operator ruling.
    # The row is looked up EXPLICITLY, never by delegating to `authorized_providers(None)` — that
    # spelling answers "the union over every row" for a missing/None row, which is a fail-OPEN
    # answer to a fail-closed question (a config with `"register_row": null` would have been read
    # as citing every operator ruling at once). Caught by
    # `test_an_unknown_register_row_raises`; the row must be a known string or nothing at all.
    register_row = raw.get("register_row")
    if not isinstance(register_row, str) or register_row not in _PROVIDER_SCOPE_BY_ROW:
        raise LiveAuthorizationError(
            f"live-operation config cites register row {register_row!r}, which authorizes no live "
            f"scope; only {list(authorizing_register_rows())} do — fail closed")
    row_scope = authorized_providers(register_row)

    scope = raw.get("scope")
    if not isinstance(scope, dict):
        raise LiveAuthorizationError("live-operation config missing/invalid 'scope' object — fail closed")

    providers = _validate_providers(scope.get("providers"), resolved, register_row, row_scope)
    terminals = _validate_terminals(scope.get("terminals_per_subscription"))

    return LiveAuthorization(
        authorized=True, providers=providers, terminals_per_subscription=terminals,
        register_row=str(register_row), source=str(resolved),
        reason=f"live operation authorized for {sorted(providers)} (register "
               f"{register_row}, {terminals} terminals/subscription)")


def _validate_providers(raw_providers: object, resolved: Path, register_row: object,
                        row_scope: frozenset[str]) -> frozenset[str]:
    """The config's provider list must be a non-empty list of providers, each within the scope the
    CITED register row authorizes. A provider outside that set RAISES — the config can never widen
    a row, and one row can never borrow another's scope."""
    if not isinstance(raw_providers, list) or not raw_providers:
        raise LiveAuthorizationError(
            f"live-operation scope 'providers' must be a non-empty list in {resolved} — fail closed")
    canonical: set[str] = set()
    for entry in raw_providers:
        if not isinstance(entry, str):
            raise LiveAuthorizationError(
                f"live-operation scope provider {entry!r} is not a string — fail closed")
        norm = _canonical_provider(entry)
        if norm not in row_scope:
            covered_elsewhere = norm in _AUTHORIZED_PROVIDERS
            raise LiveAuthorizationError(
                f"live-operation scope names provider {entry!r} under register row {register_row!r}, "
                f"which authorizes only {sorted(row_scope)} — "
                + (f"{entry!r} is authorized by another recorded ruling, so cite THAT row"
                   if covered_elsewhere else
                   "a further provider needs a NEW operator authorization, not a wider config")
                + " — fail closed")
        canonical.add(norm)  # type: ignore[arg-type]
    return frozenset(canonical)


def _validate_terminals(terminals: object) -> int:
    """Terminals-per-subscription must be an int in [1, 2]. A config may NARROW to 1 but never
    widen past the OP-6 cap of 2; True must not masquerade as 1 (isinstance-bool guard)."""
    if not isinstance(terminals, int) or isinstance(terminals, bool):
        raise LiveAuthorizationError(
            "live-operation 'terminals_per_subscription' must be an integer 1 or 2 — fail closed")
    if terminals < 1 or terminals > _MAX_TERMINALS_PER_SUBSCRIPTION:
        raise LiveAuthorizationError(
            f"live-operation scope requests {terminals} terminals/subscription; 1.."
            f"{_MAX_TERMINALS_PER_SUBSCRIPTION} is allowed (OP-6) — fail closed")
    return terminals
