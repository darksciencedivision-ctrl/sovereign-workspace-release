"""Live-gate ingredients for the two OP-12 frontier providers — Phase 18B `.picker`.

The `claude_code` and `openai_codex_cli` panes get theirs from `frontier_spawn` / `codex_spawn`,
each of which also owns a HEADLESS terminal-spawn function. These two providers have no headless
spawn function to own (`FrontierProviderCliBackend.generate` refuses while `_LIVE_SPAWN_PATH_WIRED`
is False — U268), so this module carries only what the INTERACTIVE pane authorization needs:

  * the `AdapterCapability` the profile/live gate evaluates — the same object shape, so
    `ProfileLoader.assert_startup` treats these as real live paths with no per-provider branch;
  * a presence exception PER PROVIDER, because operator directive §14 says provider-specific
    failure messages must identify the ACTUAL provider and one provider's error text must never be
    printed for another. A shared `FrontierCliUnavailable` would have made that a convention held by
    whoever wrote the message; two types make it a property of the code.

Deliberately NOT here: a `spawn_grok_terminal` / `spawn_antigravity_terminal`. Through 18B/18C the
reason was categorical — a headless terminal for these providers needs a Sovereign node record, and
`NodeRegistry.register` refused both adapter ids while U227 was unruled. **OP-12.1 (2026-08-01)
ruled it: `node@1.1` admits both, so the registry no longer refuses.** The functions are still not
here, and the reason is now narrower and worth stating exactly: nothing has been WIRED to create
those records yet — that is phase 18D `.close`, together with the 18C legs that were skipped on the
old fence. Adding the spawn functions ahead of the wiring would be a path that looks live and is
not, which is the same mistake in a different place.
"""
from __future__ import annotations

from adapters.base.contract import AdapterCapability
from adapters.frontier.antigravity import (
    ANTIGRAVITY_ADAPTER,
    ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS,
    AntigravityCliBackend,
)
from adapters.frontier.grok_build import (
    GROK_ADAPTER,
    GROK_REASONING_CAPABILITY_DESCRIPTORS,
    GrokCliBackend,
)


class GrokCliUnavailable(Exception):
    """The `grok` CLI is not present on this host. Grok's own message, never Antigravity's (§14)."""


class AntigravityCliUnavailable(Exception):
    """The `agy` CLI is not present on this host. Antigravity's own message, never Grok's (§14)."""


def capability_for_grok() -> AdapterCapability:
    """The live frontier capability the profile/live gate evaluates for a `grok_build` node.

    `adapter="grok_build"` (not the `mock` sentinel) is what makes `ProfileLoader` treat this as a
    REAL live path requiring `LIVE_OPERATION_AUTHORIZED` — the fail-closed default. The node class,
    roles and capability list are read from the adapter, never re-declared, so the gate evaluates
    the same facts the adapter would run under."""
    return AdapterCapability(
        adapter=GROK_ADAPTER, node_class=GrokCliBackend.node_class, locality="frontier",
        offline_profile_eligible=False, requires_network=True, local_runtime=False,
        capabilities=tuple(c["capability"] for c in GROK_REASONING_CAPABILITY_DESCRIPTORS),
        subscription_backed=True)


def capability_for_antigravity() -> AdapterCapability:
    """The live frontier capability the profile/live gate evaluates for a `google_antigravity`
    node. Same shape and same fail-closed reasoning as `capability_for_grok`."""
    return AdapterCapability(
        adapter=ANTIGRAVITY_ADAPTER, node_class=AntigravityCliBackend.node_class,
        locality="frontier", offline_profile_eligible=False, requires_network=True,
        local_runtime=False,
        capabilities=tuple(c["capability"] for c in ANTIGRAVITY_REASONING_CAPABILITY_DESCRIPTORS),
        subscription_backed=True)
