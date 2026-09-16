"""Phase 15E `.picker` — operator-run enumeration driver (Phase-1 spike substitution pattern).

The per-pane picker's DATA MODEL (`control_plane/nodes/pane_picker.build_pane_picker`) and the
VRAM residency planner (`scheduler/residency_planner`) are pure and covered by the headless
suite. What THIS session cannot verify is the *live host enumeration* that feeds them: the real
`ollama list` result and each running model's real VRAM footprint. This driver is the
operator-run metric that captures those real inputs and prints the exact picker JSON the shell
selector would render — like `tools/spike_compositor` for the Phase-1 window, it is NOT part of
pytest and makes no assertion; it records what the host actually reports.

In local-only mode it performs no frontier probe, model call, credential read, or network access to
commercial providers. It enumerates Ollama over its loopback API and llama.cpp over its configured
loopback OpenAI-compatible API, recording an empty list when either runtime is unreachable.

Run (Windows host, operator):  py -3.12 tools/live/enumerate_pane_picker.py
  --emit-picker      the picker dict only (the shell's stable contract)
  --emit-residency   the VRAM budget + planner snapshot only (deterministic-arithmetic contract)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# F-016. Loopback backend only; force a direct connection past any configured proxy.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters import detect
from adapters.detect import OLLAMA_HOST
from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER, probe_antigravity
from adapters.frontier.codex import probe_codex
from adapters.frontier.grok_build import GROK_ADAPTER, probe_grok
from adapters.frontier.provider_cli_common import (
    AUTH_AUTHENTICATED,
    AUTH_REQUIRED,
    AUTH_UNVERIFIED,
    ProviderCliProbe,
)
from adapters.local.model_ceiling import (
    CEILING_NAMEPLATE_B,
    classify_local_models,
    reasons_by_name,
)
from control_plane.nodes.pane_picker import ProviderCliInventory, build_pane_picker, local_only_authorization
from control_plane.local_only import LOCAL_ONLY_MODE, LOCAL_ONLY_REASON
from control_plane.profiles.live_authorization import (
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
from scheduler.residency_planner.residency_planner import ResidencyPlanner

# Bytes → MiB, integer, at least 1 (a real model is never 0MB; guards a rounding-to-zero).
def _mb(size_bytes: object) -> int | None:
    if not isinstance(size_bytes, (int, float)) or isinstance(size_bytes, bool) or size_bytes <= 0:
        return None
    return max(1, int(size_bytes // (1024 * 1024)))


def _daemon_json(path: str, timeout: float = 3.0) -> dict | None:
    try:
        with _NO_PROXY_OPENER.open(f"{OLLAMA_HOST}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


#: The stand-in VRAM budget used when the operator has not supplied a real one. A CONSTANT, deliberately
#: independent of what is resident: any rule that derives the budget from the running set (the old
#: `max(running, floor)`) puts the same models on both sides of the arithmetic — they define the budget
#: and then consume it — so free VRAM collapses to 0 for a reason that is an artifact of the heuristic
#: (gate-validator BLOCKING-1, 2026-07-26).
STAND_IN_VRAM_BUDGET_MB = 12 * 1024

#: Pinned shape of the `--emit-residency` payload (the self-check parses it fail-closed).
HOST_RESIDENCY_SCHEMA = "host_residency@1.0"

#: The budget shape returned when the daemon is unreachable — no planner, and it says so.
_NO_BUDGET = {"vram_budget_mb": None, "budget_source": "ollama daemon unreachable — no planner",
              "estimate": True, "established": False, "running_vram_mb": 0}


def _operator_vram_budget_mb() -> int | None:
    """The operator's real GPU VRAM budget in MB from `SOW_VRAM_BUDGET_MB`, or None.

    Fail-closed parsing: anything that is not a positive integer is ignored (the stand-in floor is
    used and recorded as an estimate) rather than becoming a budget of 0, which would refuse every
    local model for a reason the operator never chose."""
    raw = os.environ.get("SOW_VRAM_BUDGET_MB", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _host_residency() -> tuple[ResidencyPlanner | None, dict[str, str] | None, list[dict]]:
    """Build a ResidencyPlanner seeded from the REAL daemon: footprints from on-disk `/api/tags`,
    marks currently-running models (`/api/ps`) as resident with their live VRAM footprint. Returns
    (planner_or_None, residency_map, provenance_rows). Never fabricates — a model with no size
    signal is skipped from residency (still offered by the picker as not_loaded)."""
    tags = _daemon_json("/api/tags")
    ps = _daemon_json("/api/ps")
    prov: list[dict] = []
    if not isinstance(tags, dict):
        # `is None` alone was not enough: a daemon answering `/api/tags` with a JSON ARRAY parsed
        # fine and then raised `AttributeError` on `.get` below — outside the seeding try/except,
        # so it escaped into `build_host_picker` → `main()` and took the whole picker down, frontier
        # options included. That is the BLOCKING-1b failure shape via a different exception class
        # (spec-audit MINOR-5, 2026-07-26). An unusable payload is "no residency view", fail-closed.
        note = ("ollama daemon unreachable" if tags is None
                else f"ollama daemon answered /api/tags with {type(tags).__name__}, not an object")
        return None, None, [{"note": f"{note} — no residency view",
                             **dict(_NO_BUDGET, budget_source=f"{note} — no planner")}]

    # The TOTAL VRAM budget. TWO sources, and the choice is RECORDED, because 17B promoted this
    # planner from a display chip into an authorization gate (gate-validator B1/BLOCKING-1, 2026-07-26):
    #   1. `SOW_VRAM_BUDGET_MB` — a budget supplied out of band (normally the operator's real GPU
    #      capacity). Still `estimate:true`: nothing here verifies it against the card, so no
    #      authorization may claim the fit was proven.
    #   2. otherwise the STAND-IN CONSTANT. Neither source may be derived from the resident set: the
    #      first fix attempt used `max(running, floor)`, which still let the running models define the
    #      budget once they exceeded the floor — and since those same models are then registered
    #      resident, free VRAM was again structurally 0 (a 24GB card serving 16GB refused every local
    #      pane with 8GB genuinely free). The budget is now fixed BEFORE the host's residency is read.
    # Nothing here queries real GPU capacity, so case 2 stays `estimate:true` and every consumer must
    # disclose that (the worker ticket carries this dict verbatim) — never "proven to fit".
    running = (ps or {}).get("models", []) if isinstance(ps, dict) else []
    running_vram = sum(_mb(m.get("size_vram")) or 0 for m in running if isinstance(m, dict))
    override = _operator_vram_budget_mb()
    if override is not None:
        # `estimate` stays TRUE: an env var is a value some process supplied, not a queried GPU
        # capacity, and nothing here verifies it against the real card (validator FINDING 5).
        total_vram = override
        budget_source = "env SOW_VRAM_BUDGET_MB (unverified against real GPU capacity)"
    else:
        total_vram = STAND_IN_VRAM_BUDGET_MB
        budget_source = (
            f"STAND-IN {STAND_IN_VRAM_BUDGET_MB}MB constant — NOT a GPU query and NOT derived from "
            f"what is resident; set SOW_VRAM_BUDGET_MB to this host's real VRAM")
    budget = {"vram_budget_mb": total_vram, "budget_source": budget_source, "estimate": True,
              "established": True, "running_vram_mb": running_vram}

    disk_size = {m["name"]: _mb(m.get("size")) for m in tags.get("models", [])
                 if isinstance(m, dict) and isinstance(m.get("name"), str)}
    vram_size = {m["name"]: _mb(m.get("size_vram")) for m in running
                 if isinstance(m, dict) and isinstance(m.get("name"), str)}

    # Every model the host reports RUNNING occupies VRAM, whether or not `/api/tags` also lists it: a
    # model present in `/api/ps` but absent from `/api/tags` used to be silently uncounted, so the
    # planner reported the whole budget free while the daemon was really serving it (validator
    # MINOR-3). Footprints merge tags-first (on-disk estimate) and are overridden by the live
    # `size_vram` where the daemon supplies one.
    footprints: dict[str, int] = {n: mb for n, mb in disk_size.items() if mb is not None}
    for name, mb in vram_size.items():
        if mb is not None:
            footprints[name] = mb
    resident = sorted(n for n in vram_size if n in footprints)
    resident_vram = sum(footprints[n] for n in resident)

    # FALSIFICATION. The budget above is an assumption; the host has just contradicted it if it is
    # already serving more than that. An assumption a measurement has falsified is not a budget to
    # gate on, and manufacturing one produces exactly the structural refusal BLOCKING-1 named. Fail
    # closed and SAY which assumption broke, with the one-line fix, instead of inventing capacity.
    if resident_vram > total_vram:
        falsified = dict(
            budget, vram_budget_mb=None, established=False, running_vram_mb=resident_vram,
            budget_source=(
                f"{budget_source} — FALSIFIED by the host: {resident_vram}MB is already resident "
                f"({', '.join(resident)}), more than the {total_vram}MB budget, so no fit can be "
                f"admitted against it. Set SOW_VRAM_BUDGET_MB to this host's real VRAM in MB"))
        prov.append(falsified)
        return None, None, prov

    # Seeding rows are staged, not appended: on a fault the ONLY budget row the provenance carries
    # must be the failed one, or `host_residency_planner` would hand the authorization site a
    # healthy-looking budget for a planner that does not exist.
    staged: list[dict] = []
    try:
        planner = ResidencyPlanner(total_vram)
        for name, fp in sorted(footprints.items()):
            planner.register_model(name, fp)
            staged.append({"model": name, "footprint_mb": fp,
                           "footprint_source": ("api/ps size_vram" if vram_size.get(name)
                                                else "api/tags size (disk estimate)")})
        for name in resident:                       # registered above; now mark it resident
            planner.request_load(name)
            planner.complete_load(name)
    except Exception as exc:   # noqa: BLE001 - deliberate: see below
        # Belt-and-braces: the falsification check above makes an over-budget seed unreachable, but a
        # residency fault must NEVER escape this enumeration — it would take the whole picker down
        # (frontier options included) over one local model (validator BLOCKING-1b).
        # Catching `ResidencyError` alone did not deliver that: a daemon answering `/api/tags` with a
        # JSON array instead of an object raised `AttributeError` straight through `build_host_picker`
        # into `main()` — the SAME whole-picker failure, one exception class over (spec-audit MINOR-5,
        # 2026-07-26). The claim above is absolute, so the catch is too; the fault is still fail-closed
        # (no planner, `established:false`) and is NAMED in the provenance, never swallowed.
        prov.append(dict(budget, vram_budget_mb=None, established=False,
                         budget_source=(f"{budget_source} — residency seeding failed "
                                        f"({type(exc).__name__}: {exc}); no planner")))
        return None, None, prov
    prov.append(dict(budget))
    prov.extend(staged)

    for name in disk_size:
        if name not in footprints:
            prov.append({"model": name, "footprint_source": "none — skipped from residency"})

    return planner, planner.residency_map(), prov


def _budget_from(prov: list[dict]) -> dict:
    """The ONE budget row in a provenance list (the seeding rows carry no `vram_budget_mb` key), or
    the no-budget shape. One helper so the picker and the authorization site cannot read the
    provenance differently."""
    return next((dict(row) for row in prov if "vram_budget_mb" in row), dict(_NO_BUDGET))


def local_admission_reason(budget: dict, runtime_present: bool) -> str | None:
    """Why NO local option can be authorized on this host right now — or None, which means only
    that none of the host-wide conditions THIS FUNCTION COVERS refuses them.

    Deliberately NOT covered, and why (an exhaustive "or None if they can be" would be false —
    validator MINOR-1, round 3):
      * the per-model fit gate (`_assert_fits_without_displacing`) — a model can be too large for
        this host's budget while its neighbours fit, so it is not a fact about the LIST;
      * `role_deferred` — a local CODING pane is the worktree-isolated OpenCode path, so every
        local option is refused for that ROLE while the same options are launchable for
        `reasoning`. The picker offers roles per option, not per list, and greying the whole list
        would be wrong for the role the operator is actually choosing (U95 owns the coding path);
      * `vram_budget_mismatch` — host-wide in principle, but the enumeration produces the planner
        and the budget from one call with one total, so the two cannot disagree on this path; it is
        defence in depth against a future caller, not a state to render.

    17B turned the residency planner into an authorization gate: with no established budget,
    `worker_pane_spawn._authorize_local` refuses EVERY local selection. Offering them all as
    `available:true` shows the operator something the gate will not honour — the picker's own
    greyed-with-reason contract, never extended to the condition 17B introduced (spec-audit
    MAJOR-2, 2026-07-26).

    The FIRST fix covered only the budget condition, and the refusal set is wider: the picker's
    model list comes from the daemon over HTTP (`detect.ollama_models`) while the pane needs the
    `ollama` BINARY on PATH (`detect.ollama_executable`) — two independent facts, and
    `worker_pane_spawn`'s own refusal text already said so. A reachable daemon with no launchable
    CLI offered every model as available while the gate refused all of them: the same defect, in a
    second documented state (independent gate-validator MAJOR-A, 2026-07-26). Both host-wide
    conditions are covered here; each names itself, so the operator gets the right fix."""
    missing: list[str] = []
    if budget.get("established") is not True:
        missing.append(f"this host's VRAM admission budget could not be established — "
                       f"{budget.get('budget_source')}")
    if not runtime_present:
        missing.append("the local `ollama` runtime is not on this host's PATH, so no local pane can "
                       "be launched (the daemon this list came from is reachable over HTTP; the CLI "
                       "is a separate fact)")
    if not missing:
        return None
    return "no local pane can be authorized: " + "; ".join(missing)


def host_residency_planner() -> tuple[ResidencyPlanner | None, dict]:
    """The REAL host's VRAM residency planner + the PROVENANCE of the budget it enforces.

    Returns `(planner_or_None, budget)` where `budget` is `{vram_budget_mb, budget_source, estimate,
    established, running_vram_mb}`. A `None` planner is always accompanied by `established:false` and a
    `budget_source` naming what broke (daemon unreachable, or a budget the host's own residency
    falsified) — the local authorization gate refuses on it and repeats that reason, so "could not
    establish a budget" is never silently rendered as "does not fit".

    The budget travels WITH the planner deliberately: 17B turned this planner into
    an authorization gate, and an authorization made against an estimated budget must say so at the
    authorization site, not only in this module's provenance rows (gate-validator R2, 2026-07-26).

    Public because the worker launch ticket must route a local selection through the same
    ENUMERATION the picker's residency chips came from (invariant 22): a planner built from
    different inputs could refuse a model the operator was shown as loadable, or accept one it was
    not. HONEST PRECISION (spec-audit MINOR-13): it is the same BUILDER, not the same planner
    object or the same observation — the ticket path queries the daemon again, so a model that
    became resident between the two reads is seen by the second and not the first. What the rule
    buys is that both reads apply identical arithmetic to whatever the daemon reports; a live
    daemon is not a snapshot and this module cannot make it one.

    HONEST LIMITS (U96): (a) this planner is in-process and dies with the emitter, so a reservation
    it makes is not durable the way a terminal LEASE is — the authoritative VRAM allocator on the
    host is the Ollama daemon itself; (b) unless `SOW_VRAM_BUDGET_MB` is set, the budget is a
    stand-in CONSTANT, never a GPU query — so on a card larger than the stand-in the operator may be
    refused a pane that would really fit, and on a smaller one admitted to one that would not. What
    the rule guarantees is only that the budget is never derived from the resident set. What it
    enforces is a fail-closed ADMISSION rule (an unsized
    or over-budget model is refused, and the worker path additionally refuses anything that would
    only fit by displacing a model the daemon is already serving) plus the visible residency STATE
    — not cross-process arbitration."""
    planner, _residency, prov = _host_residency()
    return planner, _budget_from(prov)


#: Metadata-probe budget per OP-12 CLI call. The shell gives the whole enumeration 20 s
#: (`apps/desktop/picker/source.js`), and this driver now makes up to four extra child calls
#: (`--version` + `models`, twice). A slow or wedged CLI must cost the picker a bounded amount and
#: then fail closed to "no models enumerated", never the whole option list.
OP12_PROBE_TIMEOUT_S = 6.0


def _op12_inventory(probe: ProviderCliProbe) -> ProviderCliInventory:
    """One host probe → the picker's inventory, with nothing added and nothing collapsed.

    `selectable_models()` is the authority for what may be OFFERED — it already withholds the list
    when the CLI is absent, below the supported version, or reporting that a login is required — so
    this function must not offer `probe.models` instead. The three refusal CAUSES are carried
    separately (`present`, `authenticated`, `blocked_reason`) so the picker's greyed-out reason names
    the one that actually applies rather than a generic 'unavailable'."""
    authenticated: bool | None = None
    if probe.auth_state == AUTH_AUTHENTICATED:
        authenticated = True
    elif probe.auth_state == AUTH_REQUIRED:
        authenticated = False
    blocked = None
    if probe.present and not probe.meets_minimum:
        # Present but unusable: the version could not be parsed, or is below the floor. Say which
        # the probe reported instead of an install hint the operator does not need.
        blocked = (f"`{probe.provider}` CLI version not usable "
                   f"({probe.version or 'no parseable --version output'}) — {probe.detail}")
    return ProviderCliInventory(
        present=probe.present,
        authenticated=authenticated,
        models=tuple(probe.selectable_models()),
        blocked_reason=blocked,
        note=probe.model_note or probe.detail,
    )


def _probe_op12_providers() -> tuple[ProviderCliProbe, ProviderCliProbe]:
    """Probe both OP-12 CLIs with a BOUNDED metadata runner. Read-only and token-free: `--version`
    and `models` only, stdin closed, no prompt, no credential read (§13). A CLI that is absent is
    not spawned at all — `probe_provider_cli` short-circuits on a null executable.

    This is a REAL host call and the deterministic suite must never make it (`tests/live_call_guard`
    refuses it, correctly — `grok models` reaches grok.com to report the session). Tests pass
    `op12_probes=no_op12_probes()` to `build_host_picker` instead of monkeypatching this."""
    return (_probe_one_op12_provider(GROK_ADAPTER), _probe_one_op12_provider(ANTIGRAVITY_ADAPTER))


def _probe_one_op12_provider(provider: str) -> ProviderCliProbe:
    """The single-CLI half of the probe above, so a caller that needs ONE provider's listing pays
    for one provider's metadata call. See `only_op12_probe`."""
    from tools.providers.frontier_provider_recon import subprocess_runner  # noqa: PLC0415

    runner = subprocess_runner(timeout_s=OP12_PROBE_TIMEOUT_S)
    if provider == GROK_ADAPTER:
        return probe_grok(runner=runner, executable=detect.grok_executable())
    return probe_antigravity(runner=runner, executable=detect.antigravity_executable())


def only_op12_probe(provider: str, *, probe=None
                    ) -> tuple[ProviderCliProbe, ProviderCliProbe]:
    """Probe EXACTLY ONE OP-12 CLI; the other is reported as not-probed, spawning nothing for it.

    Why this exists (18C `.close`, U290). `emit_worker_launch._host_offered_options` verifies a
    selection against a fresh host enumeration, and for an OP-12 selection it asked for the REAL
    probe — which, until now, meant `_probe_op12_providers`, i.e. BOTH CLIs unconditionally. So
    authorizing a Gemini/Antigravity pane emitted `grok --version` + `grok models` to grok.com under
    the operator's SuperGrok session, and vice versa. That is the same cross-provider egress class
    U276 closed for a LOCAL selection at the 18B close; it was left open between the two frontier
    providers, and the 18C acceptance receipt's cost disclosure was wrong because of it
    (spec-audit MAJOR-1).

    An option's identity carries its own provider, so the other group rendering as not-probed cannot
    affect the match — exactly the argument `_host_offered_options` already makes for a non-OP-12
    selection. `probe` is the injectable seam so the deterministic suite exercises the scoping rule
    without touching a host."""
    if provider not in (GROK_ADAPTER, ANTIGRAVITY_ADAPTER):
        raise ValueError(f"only_op12_probe is for the OP-12 providers, not {provider!r}")
    run = probe if probe is not None else _probe_one_op12_provider
    return (run(GROK_ADAPTER) if provider == GROK_ADAPTER else _absent_probe(GROK_ADAPTER),
            run(ANTIGRAVITY_ADAPTER) if provider == ANTIGRAVITY_ADAPTER
            else _absent_probe(ANTIGRAVITY_ADAPTER))


def no_op12_probes() -> tuple[ProviderCliProbe, ProviderCliProbe]:
    """The host-free stand-in: both OP-12 CLIs reported ABSENT, spawning nothing.

    Not a mock of a signed-in provider — an honest "this run did not look at the host", which
    renders as zero options with the CLI-not-detected reason. Used by the deterministic suite and by
    any caller that must not touch the host; a run that wants the real answer omits it and pays for
    four bounded child calls."""
    return (_absent_probe(GROK_ADAPTER), _absent_probe(ANTIGRAVITY_ADAPTER))


def _absent_probe(provider: str) -> ProviderCliProbe:
    return ProviderCliProbe(provider, False, None, None, None, False, AUTH_UNVERIFIED,
                            "not probed on this run", (), None,
                            "not enumerated: CLI not probed", "no host probe performed")


def build_host_picker(*, op12_probes: tuple[ProviderCliProbe, ProviderCliProbe] | None = None
                      ) -> tuple[dict, dict]:
    """Enumerate the REAL host and build the per-pane picker option set + provenance meta.

    Extracted so BOTH this operator-run CLI metric AND the Phase-16B shell wiring
    (`apps/desktop/picker/source.js`, invoked via `--emit-picker`) build the picker from ONE
    place — the shell never re-implements or fabricates the option list; it renders exactly what
    this host enumeration produced. Read-only and benign: it reads the fail-closed
    `LiveAuthorization` gate, the local `codex`/`claude` presence probes, the OP-12 CLIs' own
    `--version`/`models` metadata calls (bounded, token-free, and `grok models` reaches grok.com —
    see the module docstring), and the operator's live `ollama list` + residency. It performs NO
    frontier model call and touches NO credential (§2.2).

    Returns `(picker, meta)` where `picker` is `build_pane_picker(...)` and `meta` carries the
    probe/enumeration provenance the full operator report prints.
    """
    # Local-only mode intentionally does not load the commercial authorization file or probe any
    # cloud CLI.  This keeps the picker read-only and air-gapped even when those binaries happen to
    # be installed on the host.
    live = LiveAuthorization.denied(LOCAL_ONLY_REASON) if LOCAL_ONLY_MODE else load_live_authorization()
    codex = None if LOCAL_ONLY_MODE else probe_codex()
    # ONE enumeration, classified ONCE (S-20). The records carry each model's parameter count,
    # capability list and on-disk size, which is what the operator's 8B ceiling needs to refuse a
    # model *and say why*. Every other local surface — the Conductor, Debate, SOVEREIGN — reads the
    # same `adapters.local.model_ceiling` verdicts rather than re-deriving a second, drifting set.
    ollama_records = detect.ollama_model_records()
    ceiling_verdicts = classify_local_models(ollama_records)
    ollama_models = [v.name for v in ceiling_verdicts]
    ceiling_reasons = reasons_by_name(ceiling_verdicts)
    planner, residency, prov = _host_residency()
    budget = _budget_from(prov)
    claude_present = False if LOCAL_ONLY_MODE else detect.claude_code_available()
    grok_probe, antigravity_probe = ((no_op12_probes()) if LOCAL_ONLY_MODE
                                     else (op12_probes or _probe_op12_providers()))
    # the LAUNCHABLE runtime, not the reachable daemon — see `local_admission_reason`
    ollama_runtime = detect.ollama_executable() is not None
    # Embedding endpoints are registered on the same router but cannot back an
    # interactive chat pane.  Keep them in the product registry while excluding
    # them from this chat-only picker.
    llamacpp_models = [
        model for model in detect.llamacpp_models()
        if "embed" not in model.casefold()
    ]
    llamacpp_runtime = bool(llamacpp_models)
    llamacpp_client = detect.llamacpp_executable() is not None
    llamacpp_reason = None if llamacpp_runtime and llamacpp_client else (
        "the supervised local llama.cpp router is unreachable or has no registered models"
        if not llamacpp_runtime else
        "the workspace Python executable for the llama.cpp endpoint client is unavailable")
    picker = build_pane_picker(
        live,
        ollama_models=ollama_models,
        residency=residency,
        claude_available=claude_present,
        codex_available=False if codex is None else codex.present,
        codex_authenticated=False if codex is None else codex.authenticated,
        # What the operator is SHOWN must agree with what the admission gate will do (spec-audit
        # MAJOR-2 + validator MAJOR-A): with no established budget, or no launchable `ollama`
        # binary, every local pane is refused — so every local option is greyed with that reason
        # instead of being offered as launchable.
        local_unavailable_reason=local_admission_reason(budget, ollama_runtime),
        # The operator's 8B ceiling (ENTRY 017), per model, with the sentence the operator
        # reads when a model is refused. Over-ceiling models stay VISIBLE and greyed - they
        # are "excluded from selection with a stated reason, not silently hidden".
        local_ceiling_reasons=ceiling_reasons,
        # OP-12: the option set for these two IS their own `models` listing — enumerated here on the
        # real host, never composed. An absent, stale-version or signed-out CLI yields zero options
        # with the reason attached to the group (operator directive §8/§14).
        grok=_op12_inventory(grok_probe),
        antigravity=_op12_inventory(antigravity_probe),
        llamacpp_models=llamacpp_models,
        llamacpp_unavailable_reason=llamacpp_reason,
        llamacpp_runtime_present=llamacpp_runtime and llamacpp_client,
    )
    meta = {
        "authorization": (local_only_authorization() if LOCAL_ONLY_MODE else live.as_dict()),
        "claude_probe": {"present": claude_present},
        "ollama_probe": {"runtime_on_path": ollama_runtime},
        "codex_probe": ({"skipped": LOCAL_ONLY_REASON} if LOCAL_ONLY_MODE else
                        {"present": codex.present, "authenticated": codex.authenticated}),
        GROK_ADAPTER + "_probe": grok_probe.as_dict(),
        ANTIGRAVITY_ADAPTER + "_probe": antigravity_probe.as_dict(),
        "ollama_enumerated": ollama_models,
        "llamacpp_enumerated": llamacpp_models,
        "llamacpp_probe": {"server_reachable": llamacpp_runtime,
                           "endpoint_client_available": llamacpp_client,
                           "llama_cli_required": False},
        "local_ceiling": {
            "nameplate_b": CEILING_NAMEPLATE_B,
            "authority": "OPERATOR-INSTRUCTIONS.log ENTRY 017",
            "classified": len(ceiling_verdicts),
            "admitted": [v.name for v in ceiling_verdicts if v.admitted],
            "excluded": {v.name: v.reason for v in ceiling_verdicts if not v.admitted},
        },
        "residency_snapshot": planner.snapshot() if planner else None,
        "residency_budget": budget,
        "residency_provenance": prov,
    }
    return picker, meta


def main(argv: list[str] | None = None, *,
         op12_probes: tuple[ProviderCliProbe, ProviderCliProbe] | None = None) -> int:
    """The CLI entrypoint. `op12_probes` carries the same host-free seam as `build_host_picker` so a
    test can exercise THIS function — the one the shell actually invokes — without any test reaching
    a provider CLI. Omitted on a real run ⇒ the host is probed."""
    argv = sys.argv[1:] if argv is None else argv
    # W-15/R-10: the enumeration reads the fail-closed live gate first, and a malformed
    # config raised straight out of `main()` -- a traceback on stdout. The shell already
    # treats non-JSON as an unavailable picker, so it failed closed, but with no reason to
    # report. It now gets JSON that NAMES the gate, and deliberately carries no
    # `providers` key, so a refusal can never be read as a picker with zero options.
    try:
        picker, meta = build_host_picker(op12_probes=op12_probes)
    except LiveAuthorizationError as exc:
        json.dump({"error": f"{type(exc).__name__}: {exc}",
                   "refused_by": "live_operation"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    # `--emit-picker` (Phase 16B): print ONLY the picker dict — the minimal, stable contract the
    # shell parses (apps/desktop/picker/source.js). Fail-closed on the shell side: any non-JSON or
    # missing `providers` is treated as an unavailable picker, never a fabricated option.
    if "--emit-picker" in argv:
        json.dump(picker, sys.stdout)
        sys.stdout.write("\n")
        return 0
    # `--emit-residency` (17B `.ticket-revalidate2`): the budget + the planner's own snapshot, so a
    # caller can make its VRAM arithmetic DETERMINISTIC instead of depending on what the daemon
    # happens to be serving. The in-Electron self-check needs exactly this: its "does not fit"
    # refusal leg used a 1MB budget, which on a busy host falsified the budget and fired a
    # DIFFERENT gate (provenance, not fit) while the leg's name claimed the fit gate — the
    # intra-family version of the borrowed-evidence defect the gate ids fixed (spec-audit MAJOR-1).
    if "--emit-residency" in argv:
        json.dump({"schema": HOST_RESIDENCY_SCHEMA,
                   "budget": meta["residency_budget"],
                   "snapshot": meta["residency_snapshot"]}, sys.stdout)
        sys.stdout.write("\n")
        return 0
    report = {"phase": "15E.picker / 16B (operator-run enumeration metric)", **meta, "picker": picker}
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
