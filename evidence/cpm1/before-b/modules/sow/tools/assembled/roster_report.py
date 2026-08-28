"""Phase 14E `.roster` — assembled-system roster + honest liveness matrix + item-7 Ollama smoke.

Phase 14E is product-level validation: one assembled run of a conductor + a frontier worker + an
OpenCode/local coder worker + a local reasoning worker over live shared MCP. This module is the
FIRST 14E sub-step. It does two things, both deterministic and fail-closed:

 1. Composes the four assembled ROLES from the existing governed roster (`adapters/roster.py`)
    plus the Phase-4 conductor path, and classifies each leg HONESTLY as LIVE, MOCK, or
    DETERMINISTIC_SUBSTITUTE with the exact reason. This is the "which legs proved live vs
    mock/deterministic" evidence the directive (§10.4) requires the assembled run to report —
    produced here once, up front, so `.run` cannot silently overclaim a leg.

 2. Re-runs the on-host Ollama smoke (STATUS_RECONCILIATION item 7) that was artifact-attested
    at the completion audit but explicitly deferred to 14E on-host: a real model list, a real
    tiny generate, and its measured latency — recorded, never faked. If the daemon is not
    reachable the smoke degrades honestly (available=False) rather than fabricating a result.

Prohibitions still bind: no live frontier call here (owed / skip-with-record at 14B); no
credential handling (§2.2) — a role carries only an MCP identity/subscription REFERENCE, never a
token; local Ollama is permitted (§2.4 allows a detected local model, no credentials involved).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from adapters import detect
from adapters.detect import OLLAMA_HOST
from adapters.roster import _CODER_MODELS, _REASONING_MODELS, build_roster
from control_plane.profiles.live_authorization import load_live_authorization

# Liveness of the backend that produces a role's GOVERNED output this session.
LIVE = "LIVE"                                    # a real model/process genuinely produced it
MOCK = "MOCK"                                     # deterministic mock backend, by design/prohibition
DETERMINISTIC_SUBSTITUTE = "DETERMINISTIC_SUBSTITUTE"  # real component driven, but accepted content
#                                                       was a scripted/seeded input (§6 substitution)

# A deterministic, self-verifying smoke prompt: cheap, no external facts, easy to see it answered.
SMOKE_PROMPT = "Reply with exactly one word and nothing else: SOVEREIGN"

# Smoke model preference: a clean non-thinking instruct model first (its answer lands in
# `response`), then the general reasoning tier. A "thinking" model (e.g. qwen3) emits its answer
# in a separate `thinking` field, so the smoke counts EITHER field as a real generation — the
# receipt proves the daemon+model ran, not one family's output-formatting quirk.
_SMOKE_MODELS = ("qwen2.5:7b-instruct", "qwen2.5:14b-instruct") + _REASONING_MODELS


@dataclass(frozen=True)
class AssembledRole:
    """One of the four assembled-run roles and the honest classification of its live-ness.

    `liveness` classifies the backend that produces this role's governed OUTPUT. `reason`
    carries every caveat in plain words so no downstream report can quietly upgrade a leg.
    """

    role: str            # conductor | frontier_worker | coding_worker | local_reasoning_worker
    node_class: str
    backend_kind: str    # "mock" | "ollama" | "opencode+ollama" | "claude_code(deferred)"
    model: str | None
    liveness: str
    reason: str
    owed: bool = False   # True when a real-provider proof is still owed (must not be claimed live)

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role, "node_class": self.node_class, "backend_kind": self.backend_kind,
            "model": self.model, "liveness": self.liveness, "reason": self.reason, "owed": self.owed,
        }


def assembled_roster(*, allow_live: bool = True) -> list[AssembledRole]:
    """Compose and honestly classify the four assembled-run roles.

    allow_live=False forces the all-mock deterministic view used by the test suite (no host
    detection, no Ollama, no OpenCode) so the classification logic is exercised without a daemon.
    """
    entries = {e.name: e for e in build_roster(allow_live=allow_live)}

    # --- conductor: Phase-4 deterministic mock reasoner (adapters/conductor uses MockReasoningBackend).
    # A live frontier conductor is out of scope — §2.4 was lifted for exactly one WORKER provider
    # (claude_code), not for the conductor runtime. Conductor succession is proven at Phase 11.
    conductor = AssembledRole(
        role="conductor", node_class="conductor", backend_kind="mock", model=None, liveness=MOCK,
        reason=("Phase-4 deterministic mock reasoner (adapters/conductor/adapter.py holds NO "
                "credential); a live frontier conductor is out of scope — prohibition §2.4 is "
                "lifted only for the two OP-6 live worker providers (claude_code, "
                "openai_codex_cli), not the conductor runtime. Conductor replacement/succession "
                "is proven live at Phase 11 (gate/phase-11)."),
        owed=False)

    # --- frontier worker: the live claude_code adapter EXISTS (14B) but the enforced runtime gate
    # LIVE_OPERATION_AUTHORIZED is consulted HERE (never asserted) so this record matches the real
    # host state. Under OP-6 (Phase 15A) the loop MAY create config/live_operation.json, so the gate
    # is now typically SATISFIED (config present & in-scope for claude_code); a fresh clone with the
    # gitignored config absent still reads DENIED-by-absence. Either way, in THIS assembled roster the
    # frontier backend stays mock and the single live `claude` smoke is still OWED (skip-with-record
    # pending [OPERATOR] R8 §6 dated live-terms + the 15B/15D live-adapter wiring): live is not claimed.
    front = entries["mock_frontier"]
    frontier_live_ok = load_live_authorization().is_provider_live("claude_code") if allow_live else False
    gate_state = ("SATISFIED (config present & in-scope, loop-created per OP-6)" if frontier_live_ok
                  else "DENIED-by-absence (config/live_operation.json absent — e.g. a fresh clone)")
    frontier = AssembledRole(
        role="frontier_worker", node_class=front.node_class, backend_kind="mock", model=None,
        liveness=MOCK,
        reason=("live claude_code adapter exists (adapters/frontier/claude_code.py, gate/phase-14b); "
                "operator authorization is recorded (OP-6, superseding OP-4/OP-5) and the enforced "
                "runtime gate LIVE_OPERATION_AUTHORIZED is " + gate_state + ". The single live `claude` "
                "smoke is still SKIP-WITH-RECORD (§10.4) pending [OPERATOR] R8 §6 dated live-terms and "
                "the 15B/15D live-adapter wiring, so this roster's frontier backend stays mock; live "
                "is OWED, not claimed."),
        owed=True)

    # --- coding worker: OpenCode is proven driven LIVE at 14C (real spawn, tool-execution, worktree
    # confinement) but NO live local-coder LANDED edit was producible (U31), so the CANDIDATE→gate→
    # merge chain was closed with a deterministic SEEDED edit. Honest classification: the produced/
    # accepted content is a DETERMINISTIC_SUBSTITUTE even though the harness spawn itself is live.
    coder = entries["coding_node"]
    have_opencode = detect.opencode_available() if allow_live else False
    coder_model = coder.model  # ollama/* coder if detected, else None (mock)
    if have_opencode and coder_model:
        coding = AssembledRole(
            role="coding_worker", node_class="worker_coding_specialist",
            backend_kind="opencode+ollama", model=coder_model, liveness=DETERMINISTIC_SUBSTITUTE,
            reason=("OpenCode harness proven driven LIVE at 14C (gate/phase-14c): real spawn, real "
                    "tool-execution, worktree confinement (escaped=False) against ollama/" +
                    str(coder_model) + ". But NO live local-coder LANDED edit was producible headlessly "
                    "(U31, model-quality limit), so the CANDIDATE→gate→merge chain was closed with a "
                    "deterministic SEEDED edit (from_live_model=False). Accepted content is substituted, "
                    "not model-authored — the governed path is the system under test (§6)."),
            owed=False)
    elif coder_model:
        # A real local coder is present but OpenCode is not: this is the DIRECT single-shot Ollama
        # coder (adapters/roster.py coding_node, F1) — a real local backend, NOT a mock, and NOT the
        # driven-harness path proven at 14C. Classify it honestly as LIVE-direct (no harness loop).
        coding = AssembledRole(
            role="coding_worker", node_class="worker_coding_specialist", backend_kind="ollama",
            model=coder_model, liveness=LIVE,
            reason=("OpenCode binary not detected; coding worker is the DIRECT single-shot Ollama "
                    "coder (ollama/" + str(coder_model) + ", roster F1) — a real local backend, no "
                    "driven coding-TUI harness (the 14C harness path needs the OpenCode binary)."),
            owed=False)
    else:
        coding = AssembledRole(
            role="coding_worker", node_class="worker_coding_specialist", backend_kind="mock",
            model=None, liveness=MOCK,
            reason=("no local coder model detected (allow_live=" + str(allow_live) + "); coding worker "
                    "stands in as a deterministic mock coder behind the same contract."),
            owed=False)

    # --- local reasoning worker: a detected local Ollama reasoning model is permitted (§2.4, no
    # credentials). This is the one leg that genuinely runs a real model end-to-end this session.
    lr = entries["local_reasoning"]
    if lr.backend_kind == "ollama" and lr.model:
        local_reasoning = AssembledRole(
            role="local_reasoning_worker", node_class="worker_reasoning", backend_kind="ollama",
            model=lr.model, liveness=LIVE,
            reason=("real local Ollama model (ollama/" + str(lr.model) + ") detected on 127.0.0.1 — "
                    "permitted under §2.4 (detected local model, no credentials); a real generate is "
                    "usable this session. The item-7 smoke (run below when run_smoke=True) is the "
                    "live receipt that a real generate succeeds on this host."),
            owed=False)
    else:
        local_reasoning = AssembledRole(
            role="local_reasoning_worker", node_class="worker_reasoning", backend_kind="mock",
            model=None, liveness=MOCK,
            reason=("no local Ollama reasoning model detected (allow_live=" + str(allow_live) + "); "
                    "stands in as a deterministic mock reasoner behind the same contract."),
            owed=False)

    return [conductor, frontier, coding, local_reasoning]


def run_ollama_smoke(model: str | None = None, *, timeout: float = 180.0) -> dict[str, Any]:
    """Item-7 receipt (STATUS_RECONCILIATION §3): on-host Ollama smoke re-run.

    Returns a fully honest record: whether the daemon was reachable, the real model list, the
    model chosen, whether a real generate produced non-empty output, and its measured latency.
    Never fabricates a result — if the daemon is down, available=False and nothing is generated.
    No credentials, loopback only.
    """
    if not detect.ollama_available():
        return {"available": False, "models": [], "model": None, "generated": False,
                "reason": "ollama daemon not reachable at 127.0.0.1:11434 — item-7 smoke "
                          "SKIP-WITH-RECORD (§10.4), not faked", "prompt": SMOKE_PROMPT}
    models = detect.ollama_models()
    chosen = model or detect.pick_model(models, _SMOKE_MODELS)
    if not chosen:
        return {"available": True, "models": models, "model": None, "generated": False,
                "reason": "daemon up but no reasoning-tier model present; no generate attempted",
                "prompt": SMOKE_PROMPT}
    body = json.dumps({"model": chosen, "prompt": SMOKE_PROMPT, "stream": False,
                       "options": {"num_predict": 128, "temperature": 0.0}}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        # Daemon answered /api/tags but the generate failed (model not resident, 500, timeout,
        # reset). Fail closed with an honest record — never fabricate output (§6/§10.4).
        return {"available": True, "models": models, "model": chosen, "generated": False,
                "latency_s": round(time.monotonic() - t0, 3),
                "reason": f"generate failed after a reachable daemon: {type(exc).__name__}",
                "prompt": SMOKE_PROMPT}
    latency_s = round(time.monotonic() - t0, 3)
    response = (data.get("response") or "").strip()
    thinking = (data.get("thinking") or "").strip()  # thinking-family models answer here
    return {"available": True, "models": models, "model": chosen,
            "generated": bool(response or thinking), "latency_s": latency_s,
            "response_preview": response[:200], "thinking_preview": thinking[:200],
            "done_reason": data.get("done_reason"), "eval_count": data.get("eval_count"),
            "prompt": SMOKE_PROMPT,
            "coder_models_present": [m for m in models if detect.pick_model([m], _CODER_MODELS) == m]}


def assembled_report(*, allow_live: bool = True, run_smoke: bool = True) -> dict[str, Any]:
    """One deterministic report object: the honest liveness matrix + the item-7 smoke receipt.

    `.run` and the phase evidence consume this; it is the single source of the "which legs are
    live" truth so no later step can quietly upgrade a leg.
    """
    roster = [r.as_dict() for r in assembled_roster(allow_live=allow_live)]
    live_roles = [r["role"] for r in roster if r["liveness"] == LIVE]
    owed_roles = [r["role"] for r in roster if r["owed"]]
    smoke = run_ollama_smoke() if (run_smoke and allow_live) else {"available": False,
            "reason": "smoke not run (allow_live/run_smoke disabled)", "models": [],
            "model": None, "generated": False, "prompt": SMOKE_PROMPT}
    return {
        "phase": "14E", "sub_step": "roster",
        "roles": roster,
        "role_count": len(roster),
        "live_roles": live_roles,
        "owed_roles": owed_roles,
        "item7_ollama_smoke": smoke,
        "honesty_note": ("Exactly the LIVE roles genuinely run a real model this session; MOCK legs "
                         "are deterministic by design/prohibition; DETERMINISTIC_SUBSTITUTE legs "
                         "drive the real component but accept a seeded/scripted input (§6). No leg's "
                         "liveness is upgraded beyond what is proven here."),
    }


def main() -> int:  # pragma: no cover - CLI entry for the evidence receipt
    print(json.dumps(assembled_report(allow_live=True, run_smoke=True), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
