"""Emit the OP-12 provider NODE-REGISTRATION report — Phase 18D `.close`.

**What this measures, and the one substitution it makes.** OP-12.1 authorized the successor schema
`node@1.1`; 18D `.amendment` shipped it and wired nothing to it; `.close` wired
`provider_probe_session` → `ProviderNodeRegistrar`. The leg that would prove the wiring end to end
on the operator's own host is a LIVE probe, and its entry condition is the operator's (their CLI
logins, and their own edit to the never-committed `config/live_operation.json`, which on this host
still cites OP-6 — so both OP-12 providers are DENIED). Directive §17 says an unmet entry condition
is skip-with-record; directive §6 says substitute the nearest faithful equivalent and RUN THE FULL
GOVERNANCE PATH around it.

**What is injected, ALL of it, because the first version of this note said "exactly one thing" and
that was false** (spec-audit MAJOR-1 — a claim about the gate chain that concealed which gates the
report had answered for itself):

  1. the **live-operation switch** — a FIXTURE config written into a scratch directory and read by
     the REAL loader, so it goes through the same parsing and the same code-pinned scope check the
     operator's file does. This is the substitution §17/§6 permit;
  2. **CLI presence** (`cli_present=True`) and the executable — a scratch path that is never
     spawned. Nothing is executed, so nothing is detected;
  3. the **I-X3 ledger** — a scratch `TerminalLeaseLedger`, so the operator's durable one is never
     written. The allowance still comes from the code-pinned map (1 per OP-12 subscription, never
     the fixture's `terminals_per_subscription`), and the report asserts that;
  4. the **holder pid**, which is this process.

What is NOT injected, and is the reason this report means anything: the **deployment profile** comes
from the host through `profile_loader_from_host()` — so on an `offline_airgapped` host this report
REFUSES exactly as the product path would (invariant 20's air-gap half, which a self-manufactured
`cloud` loader made structurally unreachable — U91's shape, and this file had it) — and the
**operator's R8 §6 terms determination** is the recorded one at directive §17, cited at the call
site, not a default. Everything else is the product: the real `governed_probe_session` and the rest
of its gate chain, the real `NodeRegistry`, the real hash-chained append-only log, the real schema
files, the real jsonschema validator. No credential is read (§2.2). The operator's real ledger and
real node log are never opened: this report MEASURES that by content hash, before and after.

The real switch is read too, read-only, and reported beside the fixture one — so a reader can see
both that the wiring works and that the operator's world still refuses these providers.

Contract (stdout, one JSON document, exit 0 unless the report itself could not be produced):
`{schema, generated_at, vocabulary, real_switch, fixture_scope, registrations{provider→…},
refusals{…}, durable_store{…}, ok, notes}`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER  # noqa: E402
from adapters.frontier.grok_build import GROK_ADAPTER  # noqa: E402
from control_plane.nodes.event_log import verify_file  # noqa: E402
from control_plane.nodes.registry import (  # noqa: E402
    NODE_SCHEMA_VERSIONS,
    RegistrationRefused,
    adapter_version_map,
)
from control_plane.profiles.live_authorization import (  # noqa: E402
    LiveAuthorizationError,
    load_live_authorization,
)
from node_runtime.supervisor.provider_node_registration import (  # noqa: E402
    ProviderNodeRegistrar,
    ProviderNodeRegistrationRefused,
    default_node_event_log_path,
)
from node_runtime.supervisor.provider_probe_session import (  # noqa: E402
    PROFILE_ENV,
    governed_probe_session,
    profile_loader_from_host,
)
from node_runtime.supervisor.terminal_lease import (  # noqa: E402
    TerminalLeaseLedger,
    default_ledger_path,
)

SCHEMA = "provider_node_registration@1.0"
PROVIDERS = (GROK_ADAPTER, ANTIGRAVITY_ADAPTER)

#: An id no node schema version admits, used as the fence's live example. `kimi_k3` is the spelling
#: an adapter for the operator's OP-10 Kimi K3 request WOULD plausibly take; the request itself is
#: for a MODEL (Ollama-first), so no adapter id has ever been decided and this string is a stand-in,
#: not a pending decision (spec-audit NIT-10 — the first version of this note claimed otherwise).
#: What matters for the fence is only that no node schema version contains it, and the report
#: MEASURES that rather than assuming it.
UNADMITTED_ID = "kimi_k3"

#: The one substitution, in one place. Written to a scratch file and read by the REAL loader, so the
#: fixture goes through the same parsing and the same code-pinned scope check the operator's file
#: does — a dict handed straight to the gate would be a second, weaker path.
FIXTURE_SCOPE = {
    "config_version": "1.1",
    "live_operation_authorized": True,
    "register_row": "OP-12",
    "scope": {"providers": ["claude_code", "openai_codex_cli", GROK_ADAPTER, ANTIGRAVITY_ADAPTER],
              "terminals_per_subscription": 2},
}


def _real_switch() -> dict[str, Any]:
    """The OPERATOR's live switch, read-only. Absent/denying is the expected state and is reported
    as a fact, never as an error.

    The PATH is reported, and so is whether it came from `SOVEREIGN_LIVE_OPERATION_CONFIG`. The
    loader honours that variable ahead of the repo default, and this report inherits its parent's
    environment, so "the operator's switch" was a claim about a file this document did not name —
    the validator demonstrated it by pointing the variable at a fixture and getting a receipt that
    said `register_row: OP-12` (gate-validator MEDIUM-3). The receipt's verdict refuses an
    env-overridden read outright: this document's central negative claim is about the operator's
    own file, and nothing else may stand in for it.
    """
    from control_plane.profiles import live_authorization as _la  # noqa: PLC0415

    env_override = os.environ.get(_la._ENV_OVERRIDE) or None
    path = str(_la._resolve_path(None))
    try:
        auth = load_live_authorization()
    except Exception as exc:      # noqa: BLE001 — an unreadable switch is a reported world, not a crash
        return {"readable": False, "reason": f"{type(exc).__name__}: {exc}", "path": path,
                "env_override": bool(env_override), "env_var": _la._ENV_OVERRIDE,
                "op12_authorized": [], "providers": [], "register_row": None}
    providers = sorted(getattr(auth, "providers", ()) or ())
    op12 = [p for p in PROVIDERS if p in providers]
    denied = {}
    for provider in PROVIDERS:
        try:
            auth.assert_provider_live(provider)
            denied[provider] = None
        except LiveAuthorizationError as exc:
            denied[provider] = str(exc)
    return {"readable": True, "providers": providers, "op12_authorized": op12,
            "register_row": getattr(auth, "register_row", None),
            "path": path, "env_override": bool(env_override), "env_var": _la._ENV_OVERRIDE,
            "denial_reason": denied,
            "fail_closed_for_op12": all(denied[p] for p in PROVIDERS)}


def _vocabulary() -> dict[str, Any]:
    """The node vocabulary, derived from the real schema files — the amendment, measured."""
    version_map = adapter_version_map()
    return {
        "versions_consulted": [v for v, _ in NODE_SCHEMA_VERSIONS],
        "admits": {p: version_map.get(p) for p in PROVIDERS},
        "unadmitted_example": {UNADMITTED_ID: version_map.get(UNADMITTED_ID)},
        "frozen_member_example": {"claude_code": version_map.get("claude_code")},
        "size": len(version_map),
    }


def _register_one(provider: str, scratch: Path) -> dict[str, Any]:
    """Open ONE real governed session for `provider` under the fixture switch and report the node
    record it registered — then report its teardown, measured after the context closes."""
    cfg = scratch / f"{provider}_live_operation.json"
    cfg.write_text(json.dumps(FIXTURE_SCOPE), encoding="utf-8")
    ledger_path = scratch / f"{provider}_leases.json"
    log_path = scratch / "nodes" / f"{provider}_node_events.jsonl"
    ledger = TerminalLeaseLedger(ledger_path, pid_alive=lambda _p: True)
    registrar = ProviderNodeRegistrar(log_path)
    fake_cli = scratch / f"{provider}-cli-never-executed"

    out: dict[str, Any] = {"provider": provider, "registered": False, "error": None}
    with governed_probe_session(
            provider, probe_id=f"{provider}-18d", workspace=str(scratch),
            # (1) the substitution: a fixture switch, read by the REAL loader.
            live_auth=load_live_authorization(path=cfg),
            # (3) a scratch ledger — the operator's durable one is never written.
            ledger=ledger,
            # NOT injected: the deployment profile is the HOST's. On an air-gapped host this
            # refuses at gate 1 exactly as the product path does, which is the only thing that
            # makes "the gate chain ran" a statement rather than a description (invariant 20).
            profile_loader=profile_loader_from_host(),
            # NOT injected either: the OPERATOR's recorded R8 §6 determination, cited here as the
            # product call site cites it — AUTONOMOUS_BUILD_DIRECTIVE.md §17 (OP-12), "the operator
            # confirms both subscriptions permit supervised first-party-CLI use, same R8 class as
            # OP-9". Never this build's judgement (invariant 1).
            operator_terms_confirmed=True, registrar=registrar,
            # (2) presence and the executable — a scratch path that is never spawned.
            cli_present=True, executable=str(fake_cli),
            # (4) the holder pid: this process.
            holder_pid=os.getpid(), session_id="s18d") as session:
        doc = session.as_dict()
        out.update({
            "registered": doc["node_registered"],
            "node_record": doc["node_record"],
            "node_key": doc["node_id"],
            "subscription_ref": doc["subscription_ref"],
            "allowance": doc["allowance"],
            "lease_in_use_during": ledger.in_use(doc["subscription_ref"]),
            "node_state_during": registrar.registry.get(doc["node_id"]).state.value,
            # the full validated document, so a reader sees WHAT was written, not a summary of it
            "record_document": registrar.registry.get(doc["node_id"]).meta.get("node_record"),
        })
    # AFTER the session: read the state from the LOG, not from the registry. The session hands the
    # log and its cross-process lock back on exit (D-LOOP-1), so the registry object is gone by
    # design — and the log is the record anyway. Asking the registrar again would silently re-open
    # and re-lock the file, which is exactly the leak the close exists to prevent.
    out["teardown"] = dict(session.teardown_record)
    out["lease_in_use_after"] = ledger.in_use(out["subscription_ref"])
    chain = verify_file(log_path)
    rows = [json.loads(ln) for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    transitions = [r for r in rows if r["kind"] == "transition"]
    exits = [r for r in rows if r["kind"] == "exit"]
    out["node_state_after"] = transitions[-1]["data"]["to"] if transitions else None
    out["node_exit_row"] = ({"exit_code": exits[-1]["data"].get("exit_code"),
                             "expected": exits[-1]["data"].get("expected")} if exits else None)
    out["log"] = {"path_is_scratch": str(log_path).startswith(str(scratch)),
                  "chain_ok": chain.ok, "rows": chain.rows,
                  "kinds": [r["kind"] for r in rows],
                  "lock_released": not log_path.with_suffix(log_path.suffix + ".lock").exists(),
                  "adapter_schema_version": rows[0]["data"].get("adapter_schema_version")}
    return out


def _refusals(scratch: Path) -> dict[str, Any]:
    """The fence, exercised. Two refusals that must still happen after the amendment."""
    from node_runtime.supervisor.provider_probe_session import GovernedProbeSession

    log_path = scratch / "nodes" / "refusals.jsonl"
    registrar = ProviderNodeRegistrar(log_path)
    result: dict[str, Any] = {}

    # 1. an adapter id NO node schema version admits — the registry's own fence, with its
    #    append-only refusal event. This is the guard that would matter if a third provider ever
    #    arrived without an operator ruling behind it.
    try:
        registrar.registry.register("n-unadmitted", "worker_reasoning", UNADMITTED_ID,
                                    spawned_by_supervisor=True)
        result["unadmitted_adapter"] = {"refused": False, "reason": None}
    except RegistrationRefused as exc:
        result["unadmitted_adapter"] = {"refused": True, "reason": str(exc)[:400],
                                        "id": UNADMITTED_ID}

    # 2. a session that does not claim supervision — I-C1, refused before anything is written.
    unsupervised = GovernedProbeSession(
        provider=GROK_ADAPTER, display="Grok Build", node_id="probe-naked", session_id="s",
        permission_profile_id="pp-probe-reasoning", role="reasoning",
        subscription_ref="grok_build_subscription", allowance=1, in_use=0, lease_id="none",
        executable="none", workspace=str(scratch), env_scrub_names=(), supervised=False)
    try:
        registrar.register_session(unsupervised)
        result["unsupervised_session"] = {"refused": False, "gate": None}
    except ProviderNodeRegistrationRefused as exc:
        result["unsupervised_session"] = {"refused": True, "gate": exc.gate,
                                          "reason": str(exc)[:400]}

    # 3. the naked-spawn guard beneath it, asserted at the registry itself (invariant 2 / I-C1).
    try:
        registrar.registry.register("n-naked", "worker_reasoning", GROK_ADAPTER,
                                    spawned_by_supervisor=False)
        result["not_spawned_by_supervisor"] = {"refused": False}
    except RegistrationRefused as exc:
        result["not_spawned_by_supervisor"] = {"refused": True, "reason": str(exc)[:200]}

    # 4. the log is held EXCLUSIVELY while a registrar owns it: a second process appending to a
    #    hash-chained file would break the chain permanently, and an append-only log has no repair
    #    (spec-audit MEDIUM-5). Measured against the same file this function just used.
    second = ProviderNodeRegistrar(log_path)
    try:
        second.registry
        result["concurrent_log_holder"] = {"refused": False, "gate": None}
    except ProviderNodeRegistrationRefused as exc:
        result["concurrent_log_holder"] = {"refused": True, "gate": exc.gate,
                                           "reason": str(exc)[:300]}
    finally:
        second.close()

    rows = [json.loads(ln) for ln in log_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()] if log_path.exists() else []
    result["refusals_are_auditable"] = bool(rows) and all(r["kind"] == "registration_refused"
                                                          for r in rows)
    result["refusal_rows"] = len(rows)
    registrar.close()      # hand the log and its lock back (D-LOOP-1)
    result["lock_released"] = not log_path.with_suffix(log_path.suffix + ".lock").exists()
    return result


def _durable_store() -> dict[str, Any]:
    """The operator's OWN durable state, reported so a reader can see this run never wrote to it.

    By CONTENT HASH, not by size: `exists` + `size` misses any edit that preserves byte length,
    and the docstring's claim is "never opened" (spec-audit MINOR-8). The JS side already compares
    the lease ledger byte for byte; this is the same standard on this side of the boundary."""
    node_log = default_node_event_log_path(REPO_ROOT)
    ledger = default_ledger_path()

    def stat(p: Path) -> dict[str, Any]:
        try:
            if not p.exists():
                return {"path": str(p), "exists": False, "sha256": None}
            return {"path": str(p), "exists": True,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        except OSError as exc:
            return {"path": str(p), "exists": None, "error": f"{type(exc).__name__}: {exc}"}
    return {"node_event_log": stat(node_log), "terminal_lease_ledger": stat(ledger)}


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "authorization": "OP-12.1 (operator, 2026-08-01; AUTONOMOUS_BUILD_DIRECTIVE.md §17.1)",
        "substitution": (
            "FOUR inputs are injected and they are all named here, because the first version of "
            "this sentence said 'exactly one' and that concealed which gates the report answered "
            "for itself (spec-audit MAJOR-1): (1) the live-operation switch, a FIXTURE config in "
            "a scratch directory read by the REAL loader through the same code-pinned scope check "
            "- this is the substitution directive s17/s6 permit, because the operator's own file "
            "cites OP-6 and DENIES both OP-12 providers; (2) CLI presence and the executable, a "
            "scratch path that is never spawned; (3) a scratch lease ledger, so the operator's "
            "durable one is never written - the allowance still comes from the code-pinned map, 1 "
            "per OP-12 subscription, and this report asserts it; (4) the holder pid, this process. "
            "NOT injected: the deployment profile is the HOST's (so an air-gapped host refuses at "
            "gate 1 exactly as the product path would - invariant 20), and the operator's R8 s6 "
            "terms determination is the recorded one at directive s17, cited at the call site. "
            "Everything else is the product path: the real governed session and the rest of its "
            "gate chain, the real NodeRegistry, the real append-only hash-chained log, the real "
            "schema files and the real jsonschema validator. NO CLI IS EXECUTED, no live model "
            "call is made, and no credential is read."),
        "injected": ["live_operation_switch (fixture config, scratch dir)",
                     "cli_present + executable (never spawned)",
                     "terminal lease ledger (scratch)", "holder_pid (this process)"],
        "not_injected": ["deployment profile (read from the host)",
                         "operator R8 s6 terms determination (recorded, directive s17)",
                         "the code-pinned live-authorization scope",
                         "the per-provider I-X3 allowance (1, code-pinned)"],
        "deployment_profile": (os.environ.get(PROFILE_ENV) or "cloud").strip() or "cloud",
        "cli_executed": False,
        "live_model_call": False,
    }
    report["vocabulary"] = _vocabulary()
    report["real_switch"] = _real_switch()
    report["fixture_scope"] = FIXTURE_SCOPE["scope"]
    before = _durable_store()
    with tempfile.TemporaryDirectory(prefix="sow-18d-registration-") as tmp:
        scratch = Path(tmp)
        report["registrations"] = {p: _register_one(p, scratch) for p in PROVIDERS}
        report["refusals"] = _refusals(scratch)
    after = _durable_store()
    report["durable_store"] = {"before": before, "after": after, "unchanged": before == after}
    report["ok"] = bool(
        all(report["vocabulary"]["admits"][p] == "node@1.1" for p in PROVIDERS)
        and report["vocabulary"]["unadmitted_example"][UNADMITTED_ID] is None
        and all(r.get("registered") is True for r in report["registrations"].values())
        and all(r.get("error") is None for r in report["registrations"].values())
        # I-X3, asserted rather than merely displayed: the fixture says 2 terminals/subscription
        # and the code-pinned per-provider cap says 1. A regression that merged or widened the
        # OP-12 allowance must turn this report red, not just change a number nobody reads
        # (spec-audit MINOR-9).
        and all(r.get("allowance") == 1 for r in report["registrations"].values())
        and all((r.get("log") or {}).get("path_is_scratch") is True
                for r in report["registrations"].values())
        and report["refusals"]["unadmitted_adapter"]["refused"] is True
        and report["refusals"]["unsupervised_session"]["refused"] is True
        and report["refusals"]["not_spawned_by_supervisor"]["refused"] is True
        and report["refusals"]["concurrent_log_holder"]["refused"] is True
        and report["refusals"]["refusals_are_auditable"] is True
        and report["refusals"]["lock_released"] is True
        and all((r.get("log") or {}).get("lock_released") is True
                for r in report["registrations"].values())
        and report["durable_store"]["unchanged"] is True)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-provider-node-registration", action="store_true",
                    help="emit the report (default action)")
    ap.parse_args(argv)
    json.dump(build_report(), sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":      # pragma: no cover — process entry point
    raise SystemExit(main())
