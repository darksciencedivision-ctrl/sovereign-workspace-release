"""Phase 15D `.debate` — ONE bounded debate driven through the LIVE-capable model binding.

Directive §11 15D: "one bounded live debate (budgets enforced — real tokens now)". The Debate
Service itself already exists and is gated (Phase 7, `gate/phase-7`): ≤5 rounds, evidence-cited
assertions, dissent preserved verbatim, per-debate budget + per-caller quota + global concurrent
cap, clean budget-exhaustion cutoff, any authorized (non-conductor) node may call. This module
adds ONLY what 15D needs on top of it:

  1. `BackendDebater` — a `Debater` backed by any `Backend`, so the SAME governed debate runs on
     a mock backend or on the live `claude_code` CLI with no branch in the service.
  2. A FAIL-CLOSED statement parse: a model reply that is not well-formed becomes a recorded
     refusal with NO citations (hence UNSUPPORTED), never a fabricated evidence ref.
  3. Per-debater leg classification and a report that REFUSES an unbacked `live` claim.

The leg vocabulary (`live` / `attempted` / `mock` / `skipped`) and the operator-disposition pin
are IMPORTED from `live_flow` rather than redefined — one honesty vocabulary for the phase.

MOCK-FIRST (§10.4), stated precisely: this module contains no `subprocess` call of its own, but it
is not inert — with `DebaterSpec.backend=None` and every live gate passed, `BackendDebater.argue`
reaches `ClaudeCliBackend.generate`, which DOES spawn `claude`. What the module guarantees is not
"no process ever runs" but "a run that was not live cannot be REPORTED as live":
`attempt_live_debate` runs the identical governed path with whatever backend the gates admit, and
classifies each leg from counted-call evidence.

Where that guarantee lives, stated exactly (it is split, and an earlier header got this wrong):
`verification_for` / `debater_leg` hold the load-bearing rules — exact CLI class, a checkpoint the
CLI reported, and a call spent since this debate bound the backend. `build_debate_report` is the
narrower guard: it checks that the `legs` and the checkpoint records AGREE in both directions, and
refuses a mismatch. On the `attempt_live_debate` path the two compose; a caller invoking
`build_debate_report` directly gets only the agreement check, over whatever it supplies.

Vendor coupling, stated honestly (invariants 4/20): this module defers its OWN vendor import to
function scope (`ClaudeCliBackend` is needed to classify a real CLI backend by TYPE, since an
attribute check would be spoofable). That is NOT the same as being vendor-free: it imports
`live_flow`, which imports `adapters.frontier.claude_code` at module scope, so importing this
module transitively loads the vendor adapter. The lazy import buys locality, not air-gap
eligibility — recorded as U36, not claimed away.

Cost, stated honestly: the per-round charge is a fixed governed UNIT (`round_cost`), not measured
provider tokens, so the request declares `usage_units` rather than `tokens` — an immutable
record saying `cost_actual: {"tokens": 100}` would misstate what the number is. `cost_actual`
bounds the debate deterministically; it is not a metered spend figure. Real provider-token
metering is OWED (it needs the CLI to report usage and the backend to surface it), as is the fact
that `max_tokens` is accepted and IGNORED by `ClaudeCliBackend` (it emits no output-length flag).
"""
from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from control_plane.orchestration.live_flow import (
    ATTEMPTED_LEG,
    OPERATOR_DISPOSITION_PENDING,
    VALID_LEGS,
)
from control_plane.policy import Identity, SovereignPolicy
from debate_service.cost_governor.governor import CostGovernor
from debate_service.evidence_manager.manager import EvidenceManager, mcp_resolver
from debate_service.service import DebateAuthorizationError, DebateService
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

DEBATE_REPORT_SCHEMA = "debate_report@1.0"
DEBATE_REPORT_KEYS: tuple[str, ...] = (
    "schema", "ts", "debate_id", "topic", "caller_node", "outcome", "rounds_used", "positions",
    "dissent", "evidence_map", "cost_actual", "budget", "max_rounds", "legs", "debater_models",
    "debater_notes", "operator_disposition", "mcp_entry",
)

#: How many trailing transcript rounds a debater is shown. Invariant 8: context is SCOPED, never
#: blanket-forwarded — a round-5 prompt does not carry rounds 1..4 verbatim. One round is what a
#: rebuttal actually needs, and it keeps a live debate at smoke scale (§11 budget discipline).
SCOPED_TRANSCRIPT_ROUNDS = 1

#: A refusal must be recognizable as "no position was produced" and must never read as an
#: argument. It carries no citations, so the EvidenceManager classifies it UNSUPPORTED.
REFUSAL_PREFIX = "[no position: "

_DEFAULT_EXCERPT_CHARS = 240

#: Roles a debate node may hold. The MCP credential is minted from this string, and `gate` /
#: `operator` carry transition authority the debate path has no need of.
#:
#: DEFENCE IN DEPTH, honestly labelled: an earlier comment here justified the whitelist by claiming
#: a `gate`-role debater could promote its own debate output. It could not — `SovereignPolicy`
#: already refuses a gate promoting an entry it authored (invariant 18) and refuses gate
#: self-publication into a promoted state. The whitelist is still worth keeping, because minting an
#: authority-bearing credential for a node that needs none is the wrong default and the guard is one
#: line; but it closes no gap that was open, and reasoning about it later as if it did would be
#: wrong. Fail closed on an unknown role.
_ALLOWED_DEBATE_ROLES = frozenset({"worker", "conductor"})

#: Bound for DIAGNOSTIC text — backend exception messages (which carry CLI stderr) and
#: dropped-citation notes. `frontier_spawn` sets the precedent in this codebase ("bounded,
#: structured reason — never echo the raw result dict"). Today `ClaudeCliBackend` happens to
#: truncate its own messages, so relying on that would be an inherited accident.
_MAX_RECORDED_DETAIL_CHARS = 200

#: Bound for the debate POSITION — the largest model-controlled field, and the one that lands in
#: the frozen `debate@1.0` record. Far more generous than the diagnostic bound because this is the
#: argument itself, not a note about it: the prompt asks for one or two sentences, so a position
#: approaching this size is already anomalous. Bounded all the same, because "the model was asked
#: to be brief" is not a length guarantee, and an unbounded field writes straight into an immutable
#: artifact. Truncation is MARKED, so a cut position can never be read as a complete argument.
_MAX_POSITION_CHARS = 2_000


class DebateReportError(ValueError):
    """The report could not be built honestly — refused rather than emitted with a false claim."""


# --------------------------------------------------------------------------------------
# 1. scoped prompt + fail-closed parse
# --------------------------------------------------------------------------------------

def build_debate_prompt(*, topic: str, round_no: int, transcript: Sequence[Mapping[str, Any]],
                        allowed_evidence: Sequence[str],
                        excerpt_chars: int = _DEFAULT_EXCERPT_CHARS) -> str:
    """Assemble the SCOPED prompt for one debate round. Pure and bounded.

    Only the last `SCOPED_TRANSCRIPT_ROUNDS` rounds are forwarded, each position excerpted to
    `excerpt_chars` (invariant 8; §11 budget discipline — a live call spends real provider tokens
    even though the governor's accounting unit is synthetic, see the header). The debater is
    told exactly which evidence refs it may cite; anything else it returns is dropped by
    `parse_statement`, so the scope is enforced on the way OUT as well as stated on the way in.
    """
    tail = list(transcript)[-SCOPED_TRANSCRIPT_ROUNDS:] if SCOPED_TRANSCRIPT_ROUNDS else []
    lines = [
        "You are one participant in a bounded, evidence-based debate.",
        f"Topic: {topic}",
        f"Round: {round_no}",
        "",
        "You may cite ONLY these evidence refs (any other ref is discarded):",
        *(f"  - {ref}" for ref in allowed_evidence),
        "",
    ]
    if tail:
        lines.append("Positions from the previous round:")
        for rnd in tail:
            for pos in rnd.get("positions", []):
                text = str(pos.get("position", ""))[:excerpt_chars]
                lines.append(f"  - {pos.get('node')}: {text}")
        lines.append("")
    lines += [
        "Reply with ONE JSON object and nothing else:",
        '{"position": "<your position, one or two sentences>", "evidence_refs": ["<ref>", ...]}',
        "If you have no evidence-backed position, say so in `position` and return an empty "
        "`evidence_refs` list. Do NOT invent refs.",
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class ParsedStatement:
    """One debater's round statement after fail-closed parsing."""

    position: str
    evidence_refs: tuple[str, ...]
    notes: tuple[str, ...] = ()
    refused: bool = False


def _extract_json_object(raw: str) -> Any:
    """Best-effort JSON object extraction: whole string, fenced block, then first{..last}.

    Deliberately a local copy rather than an import of `adapters.frontier.claude_code`'s private
    `_extract_json_object`: depending on another layer's PRIVATE function is bad layering. (The
    original justification — "a control-plane module must not take a vendor dependency" — was
    FALSE and is retracted; see the module header. This module already has a transitive vendor
    dependency, so the duplication stands on layering grounds only.)

    Known hazard, recorded not glossed: the two copies have already DIVERGED — the adapter's
    strips a leading ``json`` language tag explicitly, this one splits on the first newline.
    Promoting one to a shared vendor-neutral helper is the durable fix (owed).

    Returns the parsed value or None; it never raises.
    """
    text = raw.strip()
    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    out = [text]
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            body = part.split("\n", 1)[1] if "\n" in part else part
            out.append(body.strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        out.append(text[start:end + 1])
    return out


def parse_statement(raw: Any, *, allowed_evidence: Sequence[str]) -> ParsedStatement:
    """Turn a raw model reply into a statement, FAIL CLOSED.

    The load-bearing rule: an unusable reply becomes a REFUSAL with no citations. It is never
    coerced into an assertion, and a citation is never invented — a model vote is not evidence
    (Plan §19.3 prohibited drift). Refs outside `allowed_evidence` are dropped WITH A NOTE, so a
    debate record never cites evidence the node had no scoped access to, and never drops one
    silently.
    """
    if not isinstance(raw, str) or not raw.strip():
        return _refusal("the backend returned no text")
    parsed = _extract_json_object(raw)
    if not isinstance(parsed, Mapping):
        return _refusal("the reply was not a JSON object")

    position = parsed.get("position")
    if not isinstance(position, str) or not position.strip():
        return _refusal("the reply carried no non-empty `position`")

    notes: list[str] = []
    raw_refs = parsed.get("evidence_refs")
    refs: list[str] = []
    if raw_refs is None:
        pass
    elif isinstance(raw_refs, (str, bytes, Mapping)) or not isinstance(raw_refs, Sequence):
        notes.append("`evidence_refs` was not a list — no citation taken from it")
    else:
        allowed = set(allowed_evidence)
        for item in raw_refs:
            if not isinstance(item, str) or not item.strip():
                notes.append(_bounded(f"discarded a non-string evidence ref: {item!r}"))
                continue
            ref = item.strip()
            if ref not in allowed:
                notes.append(_bounded(f"discarded out-of-scope evidence ref {ref!r} (invariant 8)"))
                continue
            if ref not in refs:
                refs.append(ref)
    if raw_refs is not None and not refs and not notes:
        notes.append("the reply cited no evidence")
    bounded_position = _bounded(position.strip(), _MAX_POSITION_CHARS)
    if bounded_position != position.strip():
        notes.append(f"position truncated at {_MAX_POSITION_CHARS} chars")
    return ParsedStatement(position=bounded_position, evidence_refs=tuple(refs),
                           notes=tuple(notes), refused=False)


def _refusal(reason: str) -> ParsedStatement:
    reason = _bounded(reason)
    return ParsedStatement(position=f"{REFUSAL_PREFIX}{reason}]", evidence_refs=(),
                           notes=(reason,), refused=True)


def _bounded(text: str, limit: int = _MAX_RECORDED_DETAIL_CHARS) -> str:
    """Excerpt untrusted text before it reaches an immutable record.

    Truncation is MARKED, never silent: a reader must be able to tell a short message from a long
    one that was cut, or the record misstates what the backend said.
    """
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "… [truncated]"


# --------------------------------------------------------------------------------------
# 2. the debater
# --------------------------------------------------------------------------------------

class BackendDebater:
    """A `Debater` (see `debate_service.round_manager`) backed by any `Backend`.

    One bounded `generate` per round. The backend counts its own calls, which is the evidence the
    leg classification rests on. A backend EXCEPTION becomes a recorded refusal rather than an
    aborted debate: the round manager must still close the debate cleanly and the governor must
    still reconcile the reservation.

    This class asserts no authority: it produces a position, and the gate/evidence machinery
    decides what that is worth (invariants 10/16).
    """

    def __init__(self, node_id: str, backend: Any, *, allowed_evidence: Sequence[str] = (),
                 max_tokens: int = 192, excerpt_chars: int = _DEFAULT_EXCERPT_CHARS) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("a debater must have a node id")
        self.node_id = node_id
        self.backend = backend
        self.allowed_evidence = tuple(allowed_evidence)
        self._max_tokens = max_tokens
        self._excerpt_chars = excerpt_chars
        #: every parse/transport deviation, per round — observable, never silent (Buildout §4)
        self.notes: list[dict[str, Any]] = []

    def argue(self, topic: str, round_no: int, transcript: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = build_debate_prompt(topic=topic, round_no=round_no, transcript=transcript,
                                     allowed_evidence=self.allowed_evidence,
                                     excerpt_chars=self._excerpt_chars)
        try:
            raw = self.backend.generate(prompt, max_tokens=self._max_tokens)
        except Exception as exc:  # noqa: BLE001 — a dead backend refuses, it does not abort
            statement = _refusal(f"backend error {type(exc).__name__}: {exc}")
        else:
            statement = parse_statement(raw, allowed_evidence=self.allowed_evidence)
        for note in statement.notes:
            self.notes.append({"node": self.node_id, "round": round_no, "note": note})
        return {"position": statement.position, "evidence_refs": list(statement.evidence_refs)}


# --------------------------------------------------------------------------------------
# 3. leg classification — what each debater can be PROVEN to be
# --------------------------------------------------------------------------------------

def _is_vendor_cli_backend(backend: Any) -> bool:
    """True only for the real vendor CLI backend, decided by EXACT TYPE.

    The rule itself now lives beside the class it names (`claude_code.is_live_cli_backend`) because
    `phase-15d.gate` had to apply it at three further sites (U45) and two copies of a honesty rule
    is one copy too many (the U42 shape).

    It resolves a conductor WRAPPER to the CLI backend it holds, exactly as `verification_for`
    does. That agreement is load-bearing, not cosmetic: when only verification unwrapped, a
    wrapper-backed party was classified `leg="mock"` while carrying a populated verification
    record, so one durable artifact stated both the weaker claim and the stronger one about the
    same debater. A reviewer found that contradiction; the two now read the same object.

    The import is function-scoped for LOCALITY only — it does NOT make this module vendor-free at
    module scope (the header records why: `live_flow` pulls the vendor adapter in transitively, U36).
    """
    from adapters.frontier.claude_code import _wrapped_cli_backend
    return _wrapped_cli_backend(backend) is not None


def verification_for(backend: Any, *, calls_before: int | None = None) -> dict[str, Any] | None:
    """The verification record backing a `live` claim, or None.

    FOUR conditions, ALL required — anything less has been observed to package a non-live run as
    `live`:

    1. the backend IS (or, for a conductor wrapper, directly holds) EXACTLY the real CLI class —
       not a subclass, not a duck type (see `_is_vendor_cli_backend`);
    2. a call was SPENT since `calls_before` — a checkpoint with no counted call is contradictory
       evidence, and an unreadable counter is no evidence at all; both fail closed;
    3. it carries a non-blank checkpoint STRING that its own `generate` read back out of the CLI's
       JSON response (`extract_reported_model`) — a requested `--model` slug never reaches it;
    4. that checkpoint is datable to a call made AFTER `calls_before`, the call count snapshotted
       when this debate bound the backend. `reported_model` is never cleared and `calls` is a
       LIFETIME counter, so without (4) a backend reused from an earlier debate — every call in
       THIS one having failed — still presented a verified checkpoint for a debate in which
       nothing succeeded.

    `calls_before=None` means "no snapshot was taken", which cannot satisfy (4) and therefore
    cannot yield a verification record. Fail closed: the absence of evidence is not evidence.

    STATED LIMIT, not claimed away (U43). These are instrumentation attributes on an object the
    CALLER supplies, and exact-type checking constrains the object's class, NOT its behaviour.
    Three deliberate-falsification routes remain and no in-process check can close them:
      - forging `reported_model` + `reported_model_at_call` on a genuine backend;
      - reassigning `__class__` so a mock reports the real type;
      - replacing `generate` on a genuine instance (the type still matches).
    What this rules out is every ACCIDENTAL and every mock-SHAPED path — a subclass, a duck type, a
    renamed class, a stale checkpoint, an unstamped one. It is NOT a defence against a caller that
    sets out to falsify its own evidence. `live` is trustworthy exactly as far as the caller is.

    IMPLEMENTATION (`phase-15d.gate`, U45): the rule now has ONE definition,
    `claude_code.verify_reported_checkpoint`, because it had to be applied at three further sites
    and a duplicated honesty rule drifts (U42). The conditions above are that function's, in that
    order; this module's own suite is the equivalence proof.
    """
    from adapters.frontier.claude_code import verify_reported_checkpoint
    return verify_reported_checkpoint(backend, calls_before=calls_before)


def _spent_since(backend: Any, calls_before: int | None) -> bool:
    """True when a call was spent since the bind-time snapshot — or when that is UNKNOWABLE.

    An unreadable counter fails closed to "spent": under-reporting spend is the dishonest
    direction (§6). With no snapshot, any counted call at all counts as spend.
    """
    calls = _calls_or_none(backend)
    if calls is None:
        return True
    return calls > calls_before if calls_before is not None else calls > 0


def _calls_or_none(backend: Any) -> int | None:
    """Counted calls, or None when the counter is UNREADABLE — which is not the same as zero.

    Delegates to the single definition (`phase-15d.gate`): three verbatim copies of this read had
    accumulated across `live_debate`, `live_succession` and the adapter, which is the U42 shape the
    U45 discharge exists to remove."""
    from adapters.frontier.claude_code import calls_or_none
    return calls_or_none(backend)


def debater_leg(backend: Any, *, calls_before: int | None = None) -> str:
    """Classify one debater's leg into the shared `live_flow` vocabulary.

    `calls_before` is the call count snapshotted when this debate bound the backend, so every
    judgement below is about THIS debate rather than the object's lifetime.

    - real CLI + checkpoint verified for a call in THIS debate -> `live`
    - real CLI + a call spent here (or an unreadable counter)  -> `attempted` (never under-reported)
    - real CLI, no call spent here                             -> `skipped`
    - anything else, called                                    -> `mock`
    - anything else, never called                              -> `skipped` (`mock` would overstate)

    A `live` leg additionally requires that a call was actually SPENT here — a verified checkpoint
    with no counted call is contradictory evidence (nothing ran, yet something reported), and the
    fail-closed reading of a contradiction is the weaker claim.

    That `spent and` looks redundant — `verification_for` applies the same check internally — and an
    earlier version of this docstring asserted it WAS redundant, an equivalent mutant. That was
    wrong, and a reviewer refuted it: the two functions read the counter SEPARATELY, so a counter
    that advances between the two reads (a concurrent call landing mid-classification) makes them
    disagree. The `and` takes the EARLIER, lower reading, which is the fail-closed one. It is
    load-bearing, not decorative.
    """
    from adapters.frontier.claude_code import _wrapped_cli_backend
    cli = _wrapped_cli_backend(backend)
    if cli is not None:
        # Spend is measured on the SAME object `verification_for` reads (the wrapper tallies
        # `propose_plan` calls, the inner backend tallies CLI calls — comparing across the two
        # compares unrelated numbers, which is the U45 defect shape).
        spent = _spent_since(cli, calls_before)
        if spent and verification_for(backend, calls_before=calls_before) is not None:
            return "live"
        return ATTEMPTED_LEG if spent else "skipped"
    return "mock" if _spent_since(backend, calls_before) else "skipped"


# --------------------------------------------------------------------------------------
# 4. the report
# --------------------------------------------------------------------------------------

def build_debate_report(*, record: Mapping[str, Any], legs: Mapping[str, str],
                        verification: Mapping[str, Mapping[str, Any]], ts: str,
                        debater_notes: Sequence[Mapping[str, Any]] = (),
                        mcp_entry: str | None = None) -> dict[str, Any]:
    """Wrap a `debate@1.0` record with the honest record of WHAT RAN.

    `ts` is INJECTED (no clock read) so the report is replayable. The load-bearing refusal: a leg
    declared `live` must be backed by a VERIFIED executing checkpoint for THAT debater, so a mock
    debate can never be packaged as a real-provider result (§6, §10.4). Unlike the acceptance
    packet — where only the conductor leg had a verification record and `live` was therefore
    unrepresentable for every other leg — each debater here carries its own record, so the claim
    is checked per leg rather than forbidden outright.
    """
    if not isinstance(record, Mapping) or not str(record.get("debate_id") or "").strip():
        raise DebateReportError("a debate report needs the debate@1.0 record it reports on")
    if not isinstance(ts, str) or not ts.strip():
        raise DebateReportError("a debate report needs an injected timestamp")
    if not isinstance(legs, Mapping) or not legs:
        raise DebateReportError("legs must declare what actually ran for every debater")
    if not isinstance(verification, Mapping):
        raise DebateReportError("verification must map a debater to its checkpoint record")
    # Resolved ONCE, then both the guard and the emit read this snapshot. Two independent lookups
    # let a mapping whose `get` is stateful (or whose `get` and `__contains__` disagree) show the
    # guard one thing and the report another — the guard would pass on a checkpoint the artifact
    # never carried, or the artifact would carry one the guard never saw. One lookup, one truth.
    resolved = {node: verification.get(node) for node in legs}
    _assert_debate_legs_honest(legs, resolved)

    rec = copy.deepcopy(dict(record))
    request = rec.get("request") or {}
    result = rec.get("result") or {}
    # Resolved with the SAME lookup the honesty guard uses (`.get`, once per node). An earlier
    # draft guarded with `verification.get(node)` but emitted from `node in verification` /
    # `verification[node]`: a mapping whose `get` and `__contains__` disagree passed the guard and
    # then emitted a `live` leg with an EMPTY checkpoint map — a live claim carrying no evidence.
    # One lookup, one truth.
    models: dict[str, Any] = {node: dict(rec) for node, rec in resolved.items() if rec is not None}
    report = {
        "schema": DEBATE_REPORT_SCHEMA,
        "ts": ts,
        "debate_id": rec["debate_id"],
        "topic": request.get("topic"),
        "caller_node": request.get("caller_node"),
        "outcome": result.get("outcome"),
        "rounds_used": result.get("rounds_used"),
        "positions": result.get("positions", []),
        # dissent is carried VERBATIM out of the round manager (invariant 15) — never summarized
        "dissent": result.get("dissent"),
        "evidence_map": result.get("evidence_map", {}),
        "cost_actual": result.get("cost_actual", {}),
        "budget": request.get("budget"),
        "max_rounds": request.get("max_rounds"),
        "legs": dict(legs),
        "debater_models": models,
        "debater_notes": [dict(n) for n in debater_notes],
        # a debate record is CANDIDATE evidence for a gate, never an operator decision (invariant 1)
        "operator_disposition": OPERATOR_DISPOSITION_PENDING,
        "mcp_entry": mcp_entry if mcp_entry is not None else rec.get("mcp_entry"),
    }
    # The key set is PINNED, not decorative: a field added to the report without being declared
    # here (or one silently dropped) would change what an operator-facing artifact carries with
    # nothing failing. Same discipline as ACCEPTANCE_PACKET_KEYS.
    if tuple(report) != DEBATE_REPORT_KEYS:
        raise DebateReportError(
            f"debate report keys {tuple(report)} do not match the declared "
            f"DEBATE_REPORT_KEYS {DEBATE_REPORT_KEYS}")
    return report


def _assert_debate_legs_honest(legs: Mapping[str, str],
                               resolved: Mapping[str, Any]) -> None:
    """Both directions of the live/checkpoint correspondence, over an already-resolved snapshot.

    `live` ⇒ a verified checkpoint is the obvious one. The REVERSE direction matters just as much:
    a checkpoint record attached to a non-`live` leg would publish `{"verified": true}` for a
    debater the report simultaneously says did not run live. Checking one direction only is how the
    contradictory-evidence case leaked into `debater_models` while the leg read `skipped`.
    """
    for node, value in legs.items():
        if value not in VALID_LEGS:
            raise DebateReportError(f"leg {node!r}={value!r} is not one of {VALID_LEGS}")
        record = resolved.get(node)
        if value != "live":
            if record is not None:
                raise DebateReportError(
                    f"debater {node!r} has leg {value!r} but carries a checkpoint record "
                    f"{record!r}. A verified executing checkpoint asserts a live run; attaching "
                    f"one to a non-live leg publishes the stronger claim beside the weaker (§6, "
                    f"§10.4). Contradictory evidence fails closed.")
            continue
        # `model` must be a non-blank STRING, not merely something that survives `str(...)`:
        # `str(123).strip()` is truthy, so a non-string checkpoint used to reach an operator-facing
        # artifact as a verified model id. A checkpoint that is not text is not a checkpoint.
        model = record.get("model") if isinstance(record, Mapping) else None
        if (not isinstance(record, Mapping) or record.get("verified") is not True
                or not isinstance(model, str) or not model.strip()):
            raise DebateReportError(
                f"debater {node!r} cannot be declared live: a LIVE leg requires a VERIFIED "
                f"executing checkpoint reported by the CLI itself. An unverified run is "
                f"attempted/mock (§6, §10.4 — never present a substituted result as the "
                f"real-provider result)")


# --------------------------------------------------------------------------------------
# 5. the governed live-capable debate
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DebaterSpec:
    """One debate participant to bind. `backend=None` means the REAL CLI backend, which is built
    only after every live gate in `spawn_claude_code_terminal` has passed."""

    node_id: str
    permission_profile_id: str = "pp-worker"
    model: str | None = None
    backend: Any = None
    role: str = "worker"
    #: The debate request names participants by CAPABILITY DESCRIPTOR, never by node or vendor
    #: name — the frozen debate@1.0 schema enforces the shape (invariant 4 / I-SC1).
    #:
    #: HONESTY LIMIT: this descriptor is DECLARED by the caller, not resolved by the Scheduler.
    #: Every debater here is bound to the same `claude_code` reasoning terminal, so a descriptor
    #: saying `coding` records what was ASKED FOR, not a capability-matched selection. Descriptor-
    #: based *selection* (as `live_flow` does through the Scheduler) is owed — recorded, not
    #: implied by the field's presence.
    capability: str = "reasoning"
    requirements: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({"structured_output": True}))

    def descriptor(self) -> dict[str, Any]:
        return {"capability": self.capability, "requirements": dict(self.requirements)}


@dataclass(frozen=True)
class DebateOutcome:
    """Result of ONE governed debate attempt. `ran=False, skipped_with_record=True` is the honest
    non-interactive outcome (§10.4): the live path is built and gated, but a gate was unmet so no
    live call was made."""

    ran: bool
    published: bool
    skipped_with_record: bool
    reason: str
    debate_id: str | None = None
    #: the frozen debate@1.0 record
    mcp_entry: str | None = None
    report: dict[str, Any] | None = None
    #: the debate_report entry — legs, dropped citations and backend refusals, durably
    report_entry: str | None = None
    legs: dict[str, str] = field(default_factory=dict)


def attempt_live_debate(
    *,
    topic: str,
    server: MCPServer,
    governor: SubscriptionGovernor,
    subscription_ref: str,
    live_auth: Any,
    profile_loader: Any,
    operator_terms_confirmed: bool,
    debaters: Sequence[DebaterSpec],
    caller_node_id: str = "worker-A",
    caller_role: str = "worker",
    project_id: str = "proj",
    max_rounds: int = 3,
    budget_units: int = 300,
    round_cost: int = 100,
    cost_governor: CostGovernor | None = None,
    per_caller_quota: int = 100_000,
    global_concurrent_cap: int = 4,
    evidence_refs: Sequence[str] = (),
    cli_present: bool | None = None,
    clock: Callable[[], str] | None = None,
) -> DebateOutcome:
    """Run EXACTLY ONE governed debate on the live-capable binding, spawning and tearing down
    inside this call (no live process outlives the work unit — loop constraint D-LOOP-1).

    Every participant is spawned through `spawn_claude_code_terminal`, so all five live gates
    apply (profile+live auth, provider gate re-asserted, R8 §6 operator terms, CLI presence, I-X3
    concurrency). Any unmet gate is skip-with-record and makes NO live call.

    The CALLER is a non-conductor node by default (§2.8 acceptance test: any authorized node may
    request a debate — the service is not conductor-coupled).
    """
    from node_runtime.supervisor.frontier_spawn import spawn_claude_code_terminal

    clock = clock or _now
    if len(debaters) < 2:
        raise ValueError("a debate needs at least two participants (invariant 18)")
    # Duplicate node ids would COLLAPSE the per-debater leg/verification maps onto the last spec,
    # erasing a real subscription-spending call from the report; `governor.acquire` is idempotent
    # per node id, so they would also under-count the I-X3 terminals actually spawned; and two
    # specs sharing the caller's id would satisfy DebateService's invariant-18 check while being
    # one node arguing with itself. Refused up front, fail closed.
    node_ids = [spec.node_id for spec in debaters]
    if len(set(node_ids)) != len(node_ids):
        raise ValueError(f"debater node ids must be unique (got {node_ids}) — duplicates collapse "
                         f"the leg map and under-count I-X3 terminals")
    # A node id ALREADY active on this subscription belongs to someone else: `governor.acquire` is
    # idempotent per id, so we would silently piggyback on their terminal and then RELEASE THEIR
    # SLOT at teardown — under-counting live terminals, the dishonest I-X3 direction. The
    # injectable shared governor makes concurrent callers likelier, so this is refused up front.
    held = set(governor.status().get(subscription_ref, {}).get("active", ()))
    if held & set(node_ids):
        raise ValueError(
            f"node id(s) {sorted(held & set(node_ids))} already hold a terminal on subscription "
            f"{subscription_ref!r} — refusing rather than sharing and then releasing another "
            f"holder's slot (I-X3)")
    # Invariant 18 in SUBSTANCE, not just in labels: two distinct node ids sharing ONE backend
    # object is one model agreeing with itself under two names — it would converge trivially at
    # round 1 and satisfy a node-id-based check on a technicality. Distinctness of BINDING is what
    # the invariant is about. (This catches the identical-object case only; two separate instances
    # of the same model remain indistinguishable here — recorded as owed, not claimed away.)
    bound_backends = [spec.backend for spec in debaters if spec.backend is not None]
    if len({id(b) for b in bound_backends}) != len(bound_backends):
        raise ValueError("two debaters share one backend instance — that is one node judging its "
                         "own work under two labels (invariant 18)")
    # Invariant 18 itself is enforced authoritatively by DebateService (`participants - {caller}`
    # must be non-empty), not duplicated here: with unique ids and >=2 participants, a set that
    # reduces to the caller alone is unconstructible, so a second check here would be dead code
    # asserting a guarantee it cannot make (invariant 30 — minimal necessary control).
    # A role is authority-bearing: the MCP credential is minted from it, and `gate`/`operator`
    # roles carry transition powers a supervisor-spawned worker must not receive. Whitelisted.
    for role in {*(spec.role for spec in debaters), caller_role}:
        if role not in _ALLOWED_DEBATE_ROLES:
            raise ValueError(f"role {role!r} is not permitted for a debate node "
                             f"(allowed: {sorted(_ALLOWED_DEBATE_ROLES)}) — fail closed")

    clients: list[McpClient] = []
    adapters: list[Any] = []
    #: (spec, backend, calls_before) — the call count SNAPSHOTTED at bind time, before any round.
    #: Every leg judgement is made relative to it, so a backend carrying a checkpoint or a call
    #: count from an EARLIER debate cannot lend this one evidence it did not produce.
    bound: list[tuple[DebaterSpec, Any, int | None]] = []
    acquired: list[str] = []
    legs: dict[str, str] = {spec.node_id: "skipped" for spec in debaters}

    def _teardown() -> None:
        """Release EVERY resource this call acquired, inside the call (loop constraint D-LOOP-1).

        The subscription terminal is released explicitly: `spawn_claude_code_terminal` acquires an
        I-X3 slot per debater, and nothing else releases it. Leaving it held would leave the
        subscription permanently at allowance after one debate — the exact wedge D-LOOP-1 forbids
        — and would make the governor's count describe terminals that no longer exist.
        """
        for node_id in acquired:
            try:
                governor.release(subscription_ref, node_id)
            except Exception:  # noqa: BLE001 — teardown must not mask the result
                pass
        for adapter in adapters:
            close = getattr(adapter, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
        for client in clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    try:
        caller_client = McpClient("127.0.0.1", server.port,
                                  server.credentials.issue(caller_node_id, caller_role, project_id))
        caller_client.connect()
        clients.append(caller_client)
    except Exception as exc:  # noqa: BLE001
        return DebateOutcome(ran=False, published=False, skipped_with_record=True,
                             reason=f"{type(exc).__name__}: {exc}", legs=dict(legs))

    try:
        for spec in debaters:
            client = McpClient("127.0.0.1", server.port,
                               server.credentials.issue(spec.node_id, spec.role, project_id))
            client.connect()
            clients.append(client)
            adapter = spawn_claude_code_terminal(
                mcp_client=client, governor=governor, subscription_ref=subscription_ref,
                node_id=spec.node_id, permission_profile_id=spec.permission_profile_id,
                live_auth=live_auth, profile_loader=profile_loader,
                operator_terms_confirmed=operator_terms_confirmed, model=spec.model,
                project_id=project_id, cli_present=cli_present, backend=spec.backend)
            # recorded only AFTER the spawn returned: a spawn that raised past the governor's
            # acquire released its own slot, and releasing twice would corrupt the count
            acquired.append(spec.node_id)
            adapters.append(adapter)
            bound.append((spec, adapter.backend, _calls_or_none(adapter.backend)))
    except Exception as exc:  # noqa: BLE001 — every gate failure is skip-with-record
        spawned = {s.node_id: debater_leg(be, calls_before=cb) for s, be, cb in bound}
        legs = {spec.node_id: spawned.get(spec.node_id, "skipped") for spec in debaters}
        _teardown()
        return DebateOutcome(ran=False, published=False, skipped_with_record=True,
                             reason=f"{type(exc).__name__}: {exc}", legs=legs)

    participants = [BackendDebater(spec.node_id, backend, allowed_evidence=evidence_refs)
                    for spec, backend, _ in bound]
    # The governor is INJECTABLE. A fresh one per call would make two of invariant 17's three
    # limits unreachable through this entrypoint: a per-caller quota that resets every call binds
    # nothing across debates, and a global concurrent-debate cap over a governor that never holds
    # more than one debate can never fire. An operator-scale caller passes one shared governor.
    cost = cost_governor if cost_governor is not None else CostGovernor(
        per_caller_quota=per_caller_quota, global_concurrent_cap=global_concurrent_cap)
    service = DebateService(
        SovereignPolicy(), cost,
        EvidenceManager(mcp_resolver(caller_client)), caller_client, round_cost=round_cost)
    request = {
        "topic": topic, "max_rounds": max_rounds,
        # `usage_units`, NOT `tokens`. The charge is a fixed governed unit (`round_cost`), not
        # provider metering, and debate@1.0 is an IMMUTABLE artifact: an operator reading
        # `cost_actual: {"tokens": 100}` would read "100 tokens consumed", which is a
        # misstatement of what the number is. The frozen schema and `DebateService` already carry
        # the `usage_units` shape, so the durable record can say exactly what it means. Real
        # provider-token metering is OWED (it needs the CLI to report usage).
        "budget": {"usage_units": budget_units},
        "participants": [spec.descriptor() for spec in debaters],
        "artifact_refs": list(evidence_refs),
    }
    caller = Identity(node_id=caller_node_id, role=caller_role, project_id=project_id)

    try:
        record = service.request_debate(caller, request, participants)
    except DebateAuthorizationError as exc:
        # On the FAILURE paths `ran` is DERIVED from counted-call evidence rather than from which
        # branch we exited: a refusal normally precedes any call, but asserting that structurally
        # would be the assumption the rule exists to remove.
        #
        # Scope of that claim, stated because an earlier comment overstated it: on the COMPLETED
        # paths below, `ran=True` is a branch constant, and correctly so — the governed debate
        # executed and produced a durable record even in the reachable case where the budget
        # allowed zero rounds and no backend was called. `ran` means "the debate ran", not "a
        # provider was billed"; spend lives in `legs`, which is always evidence-derived.
        legs = {spec.node_id: debater_leg(backend, calls_before=cb) for spec, backend, cb in bound}
        _teardown()
        return DebateOutcome(ran=_any_spend(legs), published=False, skipped_with_record=True,
                             reason=f"debate refused: {exc}", legs=legs)
    except Exception as exc:  # noqa: BLE001 — never a false PASS
        legs = {spec.node_id: debater_leg(backend, calls_before=cb) for spec, backend, cb in bound}
        _teardown()
        return DebateOutcome(ran=_any_spend(legs), published=False, skipped_with_record=True,
                             reason=f"{type(exc).__name__}: {exc}", legs=legs)

    # legs are read AFTER the rounds ran, so a verified checkpoint reported mid-debate is seen
    legs = {spec.node_id: debater_leg(backend, calls_before=cb) for spec, backend, cb in bound}
    verification = {spec.node_id: v for spec, backend, cb in bound
                    if (v := verification_for(backend, calls_before=cb)) is not None}
    notes = [n for p in participants for n in p.notes]

    # The post-round tail runs under try/FINALLY. `clock()`, `build_debate_report` and above all
    # `_publish_report` (a real MCP round-trip on the live path) can each raise, and an escape
    # here would leave every I-X3 terminal held and every client open — the SAME wedge the release
    # fix closed on the paths above, relocated. It is not enough that "a refused or completed
    # debate" releases: every exit must.
    #
    # A tail failure DEGRADES rather than discarding the run: the debate@1.0 record is ALREADY
    # durable in MCP at this point, so returning nothing would destroy a governed record over a
    # reporting failure. Report less, never destroy the evidence.
    report: dict[str, Any] | None = None
    report_entry: str | None = None
    tail_error: str | None = None
    try:
        ts = clock()
        report = build_debate_report(record=record, legs=legs, verification=verification,
                                     ts=ts, debater_notes=notes,
                                     mcp_entry=record.get("mcp_entry"))
        # Published as its own CANDIDATE entry, not merely returned in-process: the frozen
        # debate@1.0 record carries positions and FILTERED evidence_refs, with no field for which
        # citations were dropped, which backend refused, or what each leg actually was. An
        # operator reading only that record would see a clean debate with no sign a node cited
        # out-of-scope evidence or that a backend died (the lesson live_flow recorded — conflicts
        # and refusals belong in the DURABLE artifact, not just the trace).
        #
        # The report object is NOT mutated with its own entry id afterwards: that would add a key
        # the pinned DEBATE_REPORT_KEYS guard has already passed on, and would make the returned
        # object differ from the published bytes. The id lives on `DebateOutcome.report_entry`.
        report_entry = _publish_report(caller_client, caller_node_id, report, ts)
    except Exception as exc:  # noqa: BLE001 — never leak the terminals, never lose the record
        tail_error = f"{type(exc).__name__}: {exc}"
    finally:
        _teardown()   # spawn -> exercise -> TEAR DOWN inside the unit (D-LOOP-1)

    if tail_error is not None:
        return DebateOutcome(
            ran=True, published=True, skipped_with_record=False,
            reason=(f"bounded debate ran and its debate@1.0 record is durable, but the report "
                    f"could not be built or published: {tail_error}"),
            debate_id=record["debate_id"], mcp_entry=record.get("mcp_entry"), report=report,
            report_entry=None, legs=legs)
    return DebateOutcome(
        ran=True, published=True, skipped_with_record=False,
        reason=(f"bounded debate ran {report['rounds_used']} round(s) -> {report['outcome']}; "
                f"record and report published CANDIDATE to MCP"),
        debate_id=record["debate_id"], mcp_entry=record.get("mcp_entry"), report=report,
        report_entry=report_entry, legs=legs)


def _publish_report(client: Any, author_node: str, report: Mapping[str, Any], ts: str) -> str:
    """Publish the report as a CANDIDATE, provenance-stamped shared entry (invariants 10/11)."""
    return client.call(
        "publish", kind="evidence", tier="shared_project",
        content_b64=base64.b64encode(
            json.dumps(dict(report), sort_keys=True).encode()).decode("ascii"),
        provenance={"author_node": author_node, "task_id": None, "ts": ts,
                    "directive_version": "v2.4", "confidence": "high"},
        status="CANDIDATE")["entry_id"]


def _any_spend(legs: Mapping[str, str]) -> bool:
    """True when ANY leg shows a backend was actually reached — the counted-call evidence."""
    return any(v in ("live", ATTEMPTED_LEG, "mock") for v in legs.values())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
