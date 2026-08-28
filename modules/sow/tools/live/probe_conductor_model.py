"""Governed live PROBE of the conductor's `--model` slug — Phase 17A `.roundtrip`.

`emit_conductor_launch` must stay offline: the shell requests its ticket on a bounded timeout and a
launch path that makes a live call inside it is a launch path that hangs. So the live half lives
here, in its own bounded tool, and the ticket emitter only READS what this recorded.

What it does, in order, refusing rather than improvising at every step:

  1. the SAME live-gate chain the conductor launch runs — live-operation switch → provider-live →
     R8 §6 operator terms (OP-9) → `claude` present on the host;
  2. takes ONE durable I-X3 terminal for the duration of the probe, owned by THIS process, and hands
     it back in a `finally` (D-LOOP-1: nothing this tool spends outlives it). Both terminals already
     in use ⇒ a governed refusal, not a third session;
  3. runs `probe_claude_model` — at most one minimal live call per candidate slug, stopping at the
     first acceptance;
  4. writes the result to the host-local probe ledger so the next launch is offline and instant.

A conclusive record already in the ledger short-circuits the whole thing (no gate mutation, no live
call) unless `--reprobe` is passed — the operator's lever for "the CLI changed, ask again".

Modes (a governed refusal is still a 0-exit JSON payload; usage errors exit 2 with no JSON):
  --emit-model-probe [--label <label>] [--reprobe] [--ledger-only]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

# Run as a script ⇒ bootstrap the repo root exactly as the sibling emitters do.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.frontier.claude_code import CLAUDE_CODE_ADAPTER  # noqa: E402
from adapters.frontier.claude_model_probe import (  # noqa: E402
    ModelProbeLedger,
    ModelProbeRecord,
    launch_model_resolution,
    probe_claude_model,
)
from control_plane.conductor.selection import OPERATOR_SELECTED_CONDUCTOR  # noqa: E402
from control_plane.profiles.live_authorization import (  # noqa: E402
    LiveAuthorization,
    LiveAuthorizationError,
    load_live_authorization,
)
from node_runtime.supervisor.frontier_spawn import (  # noqa: E402
    ClaudeCliUnavailable,
    LiveTermsNotConfirmed,
    _detect_cli,
)
from node_runtime.supervisor.subscription_governor import (  # noqa: E402
    SubscriptionLimitExceeded,
    canonical_subscription_ref,
)
from node_runtime.supervisor.terminal_lease import (  # noqa: E402
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
    TerminalLeaseLedger,
)

#: Pinned envelope so the shell source refuses a drifted producer.
MODEL_PROBE_EMIT_SCHEMA = "conductor_model_probe@1.0"

PROBE_NODE_ID = "conductor-model-probe"
PROBE_SUBSCRIPTION_REF = canonical_subscription_ref(CLAUDE_CODE_ADAPTER)
PROBE_PURPOSE = "conductor --model availability probe (17A .roundtrip)"

_GOVERNANCE_REFUSALS = (
    LiveAuthorizationError,
    LiveTermsNotConfirmed,
    ClaudeCliUnavailable,
    SubscriptionLimitExceeded,
    LeaseLedgerCorrupt,
    LeaseLedgerLocked,
)


def _payload(*, source: str, label: str, record: ModelProbeRecord | None, refused: bool = False,
             reason: str | None = None, spent_live_call: bool = False) -> dict[str, Any]:
    resolution = launch_model_resolution(label, record=record)
    return {
        "schema": MODEL_PROBE_EMIT_SCHEMA,
        "ok": not refused,
        "refused": refused,
        "reason": reason,
        "label": label,
        "source": source,                    # ledger | probed | refused | unavailable
        # whether THIS invocation spent subscription calls (§16 live-budget discipline, observable)
        "spent_live_call": spent_live_call,
        "resolution": {k: v for k, v in resolution.items() if k != "record"},
        "record": record.as_dict() if record is not None else None,
    }


def build_model_probe(
    *,
    label: str | None = None,
    reprobe: bool = False,
    ledger_only: bool = False,
    live_auth: LiveAuthorization | None = None,
    probe_ledger: ModelProbeLedger | None = None,
    lease_ledger: TerminalLeaseLedger | None = None,
    operator_terms_confirmed: bool = True,   # OP-9 recorded basis (invariant 1) — not a credential
    cli_present: bool | None = None,         # None ⇒ real host detection
    probe: Callable[..., ModelProbeRecord] = probe_claude_model,
    holder_pid: int | None = None,
) -> dict[str, Any]:
    """Return the probe payload: a cached record, a fresh live probe, or a governed refusal."""
    lbl = (label or OPERATOR_SELECTED_CONDUCTOR.model or "").strip()
    if not lbl:
        return _payload(source="unavailable", label="", record=None, refused=True,
                        reason="no conductor model label to resolve")
    probes = probe_ledger if probe_ledger is not None else ModelProbeLedger()

    cached = probes.read(lbl)
    if cached is not None and cached.conclusive and not reprobe:
        return _payload(source="ledger", label=lbl, record=cached)
    if ledger_only:
        # The offline contract: report what is recorded, spend nothing. An absent/inconclusive
        # record is NOT a verdict — the resolution says "unprobed" and the launch is unchanged.
        return _payload(source="ledger", label=lbl, record=cached)

    auth = live_auth if live_auth is not None else load_live_authorization()
    led = lease_ledger if lease_ledger is not None else TerminalLeaseLedger()
    lease = None
    try:
        # (1) the same live gates the conductor launch runs — a probe is a live call like any other.
        auth.assert_provider_live(CLAUDE_CODE_ADAPTER)
        if not operator_terms_confirmed:
            raise LiveTermsNotConfirmed(
                "R8 §6 [OPERATOR] live-terms confirmation not recorded — fail closed, no live probe")
        present = _detect_cli() if cli_present is None else bool(cli_present)
        if not present:
            raise ClaudeCliUnavailable(
                "`claude` CLI not detected on host PATH — cannot probe model availability")
        # (2) I-X3: the probe's own call occupies a terminal while it runs.
        lease = led.acquire(subscription_ref=PROBE_SUBSCRIPTION_REF, provider=CLAUDE_CODE_ADAPTER,
                            node_id=PROBE_NODE_ID,
                            allowance=auth.terminals_for(CLAUDE_CODE_ADAPTER),
                            holder_pid=int(holder_pid if holder_pid is not None else os.getpid()),
                            purpose=PROBE_PURPOSE, session_id=f"model-probe#{os.getpid()}")
        # (3) the live probe itself.
        record = probe(lbl)
    except _GOVERNANCE_REFUSALS as exc:
        return _payload(source="refused", label=lbl, record=cached, refused=True,
                        reason=f"{type(exc).__name__}: {exc}")
    finally:
        # (D-LOOP-1) the terminal this tool spent never outlives it — released even on refusal.
        if lease is not None:
            try:
                led.release(lease.lease_id)
            except (LeaseLedgerCorrupt, LeaseLedgerLocked):
                pass  # reaped by holder-pid death; reported by --emit-lease-status either way

    # Only a CONCLUSIVE record is worth caching: an inconclusive one would freeze an auth/rate
    # accident into the launch path for the life of the host.
    if record.conclusive:
        try:
            probes.write(record)
        except OSError:
            pass  # an uncacheable result is still a usable one; the next launch simply re-probes
    return _payload(source="probed", label=lbl, record=record, spent_live_call=bool(record.attempts))


def _arg_after(argv: list[str], flag: str) -> str | None:
    try:
        i = argv.index(flag)
    except ValueError:
        return None
    return argv[i + 1] if i + 1 < len(argv) else None


def main(argv: list[str]) -> int:
    if "--emit-model-probe" in argv:
        payload = build_model_probe(
            label=_arg_after(argv, "--label"),
            reprobe="--reprobe" in argv,
            ledger_only="--ledger-only" in argv)
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: probe_conductor_model.py --emit-model-probe [--label <label>] [--reprobe] "
        "[--ledger-only]\n"
        "  resolves the `--model` slug the host `claude` CLI actually accepts for the conductor\n"
        "  selection, through the live gates + one durable I-X3 terminal, and caches the verdict\n"
        "  (Phase 17A .roundtrip).\n")
    return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main(sys.argv[1:]))
