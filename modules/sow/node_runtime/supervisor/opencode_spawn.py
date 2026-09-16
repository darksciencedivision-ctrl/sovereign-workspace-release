"""Governed OpenCode spawn path — the ONE place a supervised OpenCode coding harness is born.
Phase 14C `.harness` (directive §9 table 14C; §10.2).

The local-harness analogue of node_runtime/supervisor/frontier_spawn.py. It enforces, at the
actual spawn site and fail-closed (Buildout Directive §4 — deterministic, never model output),
every entry condition for a supervised OpenCode terminal:

  1. **Presence gate** — the `opencode` CLI is present/spawnable (probe.present). Absent ⇒ refuse
     (`OpenCodeUnavailable`), no naked fallback.
  2. **Version gate** — the probed version parses AND meets the minimum. Unparseable/too-old ⇒
     refuse (`OpenCodeVersionError`). This is the directive's "presence/version gate".
  3. **Supervised identity (invariant 2 — no naked session)** — a supervisor-issued permission
     profile is required; a missing profile ⇒ `NakedLaunchRefused`. Only then is a
     supervisor-issued `AdapterContext(spawned_by_supervisor=True)` constructed. The eventual
     coding adapter (`.worktree`) is a `ModelWorkerAdapter`, whose base contract independently
     refuses any non-supervisor context.

Deliberately ABSENT here, and why (recorded honesty, not an omission):
  - **No `LIVE_OPERATION_AUTHORIZED` gate.** That gate governs live *frontier/subscription*
    providers (directive §10.1); OpenCode + Ollama are local, credential-free, and authorized by
    §10.2 directly — so the frontier live-flag does not apply.
  - **No `SubscriptionGovernor`.** Local-model terminals are never subscription-bounded
    (subscription_governor.py) — I-X3 governs frontier subscriptions only.
  - **No credential handling (§2.2)** and **no paid path (§2.3)** — enforced in the harness's
    `build_env` (scrubs every provider key) + the `ollama/*`-pinned run command.
"""
from __future__ import annotations

from dataclasses import dataclass

from adapters.base.contract import AdapterContext, NakedLaunchRefused
from adapters.coding.opencode.harness import (
    MIN_OPENCODE_VERSION,
    OPENCODE_CODER_MODELS,
    CodingHarness,
    HarnessProbe,
    OpenCodeCliHarness,
    OpenCodeUnavailable,
    OpenCodeVersionError,
    parse_semver,
)


def probe_opencode(
    harness: CodingHarness | None = None,
    *,
    available_models: list[str] | None = None,
) -> HarnessProbe:
    """Probe a coding harness for the presence/version gate. `available_models` is injected by the
    deterministic suite (no network); when None the local Ollama daemon is queried (live path).
    Never raises — every failure is captured in the returned probe so the caller gates on data."""
    from adapters import detect

    if harness is None:
        harness = OpenCodeCliHarness()
    executable = getattr(harness, "executable", None)

    try:
        raw = harness.version()
    except OpenCodeUnavailable as exc:
        return HarnessProbe(present=False, version=None, version_tuple=None, meets_minimum=False,
                            executable=executable, coder_model=None, detail=f"absent: {exc}")

    try:
        vt = parse_semver(raw)
    except OpenCodeVersionError as exc:
        return HarnessProbe(present=True, version=raw, version_tuple=None, meets_minimum=False,
                            executable=executable, coder_model=None, detail=f"unparseable: {exc}")

    meets = vt >= MIN_OPENCODE_VERSION
    # The models this harness can drive are the ones the supervised llama.cpp router advertises.
    # `detect.ollama_models()` is not consulted: an OpenCode harness reaches its model over the
    # workspace's loopback endpoint, so the daemon on 11434 being down is not a fact about whether
    # this harness has anything to drive.
    models = detect.llamacpp_models() if available_models is None else available_models
    coder_model = detect.pick_model(models, OPENCODE_CODER_MODELS) if models else None
    detail = "ok" if meets else f"below minimum {MIN_OPENCODE_VERSION}"
    return HarnessProbe(present=True, version=raw, version_tuple=vt, meets_minimum=meets,
                        executable=executable, coder_model=coder_model, detail=detail)


@dataclass(frozen=True)
class SupervisedOpenCode:
    """A supervisor-admitted OpenCode harness: a supervisor-issued identity + the harness + the
    probe evidence that admitted it. Proof there is no naked session (invariant 2)."""

    context: AdapterContext
    harness: CodingHarness
    probe: HarnessProbe


def spawn_opencode_harness(
    *,
    mcp_client: object,
    node_id: str,
    permission_profile_id: str,
    workspace_root: str,
    harness: CodingHarness | None = None,
    probe: HarnessProbe | None = None,
    available_models: list[str] | None = None,
    require_min_version: bool = True,
    require_coder_model: bool = True,
    project_id: str = "proj",
) -> SupervisedOpenCode:
    """Spawn the supervised OpenCode harness, or refuse (fail closed). `harness`/`probe` are
    injected by the mock-first proof; when omitted the real CLI harness is probed live.

    `mcp_client` and `workspace_root` are bound now (the harness reads scoped context from MCP and
    edits an isolated worktree in `.worktree`); this sub-step gates presence/version + identity.
    """
    # (0) supervised identity FIRST — no naked session (invariant 2); mirrors BaseAdapter's guard.
    # It is a property of the request, not of the host, so it is decided before anything is probed:
    # a launch with no permission profile or node identity is refused even when OpenCode is present
    # and whatever local models exist. It used to run last, so on a host with OpenCode but no local
    # coder model the coder gate answered first and a naked launch was refused for the wrong reason.
    if not permission_profile_id:
        raise NakedLaunchRefused(
            "OpenCode harness has no supervisor-issued permission profile (I-C1 / invariant 2)")
    if not node_id:
        raise NakedLaunchRefused("OpenCode harness has no node identity (I-C1 / invariant 2)")

    if harness is None:
        harness = OpenCodeCliHarness()
    if probe is None:
        probe = probe_opencode(harness, available_models=available_models)

    # (1) presence gate — fail closed, no naked fallback
    if not probe.present:
        raise OpenCodeUnavailable(
            f"`opencode` not present/spawnable (probe: {probe.detail}) — refuse to spawn (fail closed)")
    # (2) version gate — parseable AND at/above the minimum
    if require_min_version and not probe.meets_minimum:
        raise OpenCodeVersionError(
            f"`opencode` version {probe.version!r} does not meet minimum {MIN_OPENCODE_VERSION} "
            f"({probe.detail}) — refuse to spawn (fail closed)")
    # (2b) local-model gate — a coding harness with NO local model to drive would tempt a non-local
    # (paid/cloud) fallback; refuse fail-closed (§2.3). Overridable only for an explicit mock drive.
    if require_coder_model and probe.coder_model is None:
        raise OpenCodeUnavailable(
            "no runnable local model is registered on the supervised llama.cpp endpoint — refuse to "
            "spawn a coding harness with no local model to drive (fail closed §2.3; pass "
            "require_coder_model=False for a mock drive)")

    context = AdapterContext(
        node_id=node_id, role="worker", project_id=project_id,
        permission_profile_id=permission_profile_id, mcp_credential_id="mcp-ref",
        subscription_ref=None,  # local: NOT subscription-backed, NOT governed by I-X3
        spawned_by_supervisor=True)
    return SupervisedOpenCode(context=context, harness=harness, probe=probe)
