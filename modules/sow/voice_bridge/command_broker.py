"""Command safety broker — the single control-command bus (Plan §2.4, §9.9; invariants 25, 1).

Typed input and voice-transcribed input BOTH flow through this broker, so voice is a second
input surface over the same command bus, never a privileged one. A proposed command is
classified deterministically (never model output):
  - low-confidence / unrecognized  -> CLARIFY (ambiguous commands require clarification);
  - destructive or protected verb  -> APPROVAL_QUEUED (operator must approve; never auto-run);
  - safe                           -> EXECUTED as a logged control event.
Voice can neither instantiate nodes nor expand permissions: those verbs are PROTECTED, so a
voice (or typed) request for them is queued for the operator, never executed inline. Typed and
voice forms of the same command produce EQUIVALENT control events (same verb/target/args).
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from control_plane.policy import Identity

# verbs that mutate/kill and must never run without operator approval
DESTRUCTIVE_VERBS = frozenset({"terminate", "kill", "delete", "remove", "merge", "shutdown", "purge"})
# verbs that would expand authority / instantiate — voice must never do these inline (invariant 25)
PROTECTED_VERBS = frozenset({"spawn", "spawn_node", "grant", "grant_permission", "approve", "promote",
                             "elevate", "authorize"})
# safe, read-only / UI-navigation verbs
SAFE_VERBS = frozenset({"focus", "status", "list", "show", "pin", "minimize", "maximize", "scroll", "select"})

DEFAULT_CONFIDENCE_THRESHOLD = 0.6


class Disposition(str, Enum):
    EXECUTED = "EXECUTED"
    CLARIFY = "CLARIFY"
    APPROVAL_QUEUED = "APPROVAL_QUEUED"


@dataclass(frozen=True)
class ProposedCommand:
    source: str                      # "voice" | "typed"
    verb: str
    target: str
    args: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float | None = None  # STT confidence for voice; None for typed


@dataclass(frozen=True)
class ControlEvent:
    event_id: str
    verb: str
    target: str
    args: dict[str, Any]
    source: str
    ts: str

    def semantic_key(self) -> tuple[str, str, tuple]:
        """The part that must be identical for typed/voice equivalence — not the id/ts/source."""
        return (self.verb, self.target, tuple(sorted(self.args.items())))


def canonicalize(verb: str, target: str) -> tuple[str, str]:
    """Canonical form applied to BOTH typed and voice at the broker, so the same command from
    either surface produces the same semantic key (F3/§9.9) — not left to each caller."""
    v = verb.strip().lower()
    t = " ".join(re.findall(r"[a-z0-9_-]+", target.lower()))
    return v, t


@runtime_checkable
class Proposer(Protocol):
    """Submit-only capability handed to input surfaces (voice/typed) so a transducer cannot
    reach approve()/execution (least privilege — invariant 25)."""
    def submit(self, cmd: "ProposedCommand") -> "BrokerOutcome": ...


@dataclass(frozen=True)
class BrokerOutcome:
    disposition: Disposition
    reason: str
    control_event: ControlEvent | None = None
    pending_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommandBroker:
    def __init__(self, *, confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
                 on_event: Any = None) -> None:
        self._threshold = confidence_threshold
        self._on_event = on_event
        self._log: list[dict[str, Any]] = []
        self._pending: dict[str, ProposedCommand] = {}

    @property
    def confidence_threshold(self) -> float:
        """The confidence below which a VOICE command is CLARIFIED rather than acted on (rule 1).

        Readable (Phase 17D `.events`) so a caller that intends to route an utterance it has already
        judged too uncertain can check, BEFORE submitting, that this broker agrees — a caller whose own
        threshold sat above this one would otherwise hand over a command the broker considers confident
        enough to execute. Read-only: nothing may lower this broker's bar from outside."""
        return self._threshold

    def _emit(self, kind: str, **data: Any) -> None:
        self._log.append({"ts": _now(), "kind": kind, **data})
        if self._on_event is not None:
            self._on_event(kind, **data)

    def submit(self, cmd: ProposedCommand) -> BrokerOutcome:
        # canonicalize both surfaces at the broker so typed/voice forms match (F5) and
        # case/whitespace variants of dangerous verbs classify correctly, not fail to unknown
        verb, target = canonicalize(cmd.verb, cmd.target)
        cmd = ProposedCommand(source=cmd.source, verb=verb, target=target, args=cmd.args,
                              raw_text=cmd.raw_text, confidence=cmd.confidence)
        # 1) ambiguity: a low-confidence voice transcript is never executed — clarify (I-V3).
        # A voice command with NO confidence is treated as ambiguous too (fail closed, F3).
        # W-78b: this keyed on the single literal source == "voice", so any other spelling
        # of a voice-derived source ("voice_recorded", a future id, a typo) sailed past the
        # threshold. The gate now exempts only the one KNOWN non-voice surface (`typed`) and
        # gates EVERYTHING else - an unknown source fails closed into clarify, never executes
        # ungated.
        if cmd.source != "typed" and (cmd.confidence is None or cmd.confidence < self._threshold):
            self._emit("clarify", source=cmd.source, raw_text=cmd.raw_text, confidence=cmd.confidence)
            return BrokerOutcome(Disposition.CLARIFY, f"low/absent STT confidence {cmd.confidence} < {self._threshold}")
        # 2) unrecognized verb -> clarify
        if cmd.verb not in (SAFE_VERBS | DESTRUCTIVE_VERBS | PROTECTED_VERBS):
            self._emit("clarify", source=cmd.source, verb=cmd.verb, raw_text=cmd.raw_text)
            return BrokerOutcome(Disposition.CLARIFY, f"unrecognized verb {cmd.verb!r}")
        # 3) protected/destructive -> operator approval queue (never auto-execute, incl. from voice)
        if cmd.verb in PROTECTED_VERBS or cmd.verb in DESTRUCTIVE_VERBS:
            pending_id = "q-" + secrets.token_hex(6)
            self._pending[pending_id] = cmd
            category = "protected" if cmd.verb in PROTECTED_VERBS else "destructive"
            self._emit("approval_queued", source=cmd.source, verb=cmd.verb, target=cmd.target,
                       pending_id=pending_id, category=category)
            return BrokerOutcome(Disposition.APPROVAL_QUEUED,
                                 f"{category} verb requires operator approval", pending_id=pending_id)
        # 4) safe -> execute as a logged control event
        return BrokerOutcome(Disposition.EXECUTED, "safe command executed",
                             control_event=self._execute(cmd))

    def _execute(self, cmd: ProposedCommand) -> ControlEvent:
        ev = ControlEvent(event_id="ce-" + secrets.token_hex(6), verb=cmd.verb, target=cmd.target,
                          args=dict(cmd.args), source=cmd.source, ts=_now())
        self._emit("control_event", event_id=ev.event_id, verb=ev.verb, target=ev.target, source=ev.source)
        return ev

    def approve(self, pending_id: str, operator: Identity) -> ControlEvent:
        """The OPERATOR approves a queued protected/destructive command -> it executes (logged).
        Operator authority is a code invariant here, not a convention: a non-operator identity
        is refused (invariant 1)."""
        if operator.role != "operator":
            self._emit("approval_refused", pending_id=pending_id, by=operator.role)
            raise PermissionError(f"only the operator may approve a queued command (got role {operator.role!r})")
        cmd = self._pending.pop(pending_id, None)
        if cmd is None:
            raise KeyError(f"no pending command {pending_id}")
        self._emit("operator_approved", pending_id=pending_id, verb=cmd.verb, target=cmd.target)
        return self._execute(cmd)

    def reject(self, pending_id: str, operator: Identity, *, reason: str = "") -> None:
        """The operator declines a queued command — the other exit from the approval queue, so
        a destructive proposal is not stuck-or-execute (F6)."""
        if operator.role != "operator":
            raise PermissionError(f"only the operator may reject a queued command (got role {operator.role!r})")
        cmd = self._pending.pop(pending_id, None)
        if cmd is None:
            raise KeyError(f"no pending command {pending_id}")
        self._emit("operator_rejected", pending_id=pending_id, verb=cmd.verb, target=cmd.target, reason=reason)

    def pending(self) -> dict[str, ProposedCommand]:
        return dict(self._pending)

    def log(self) -> list[dict[str, Any]]:
        return list(self._log)

    def as_proposer(self) -> "SubmitOnly":
        """A submit-only handle for input surfaces — carries no approve/execute capability."""
        return SubmitOnly(self)


class SubmitOnly:
    """Wraps a broker exposing ONLY submit(): what a voice/typed transducer is handed so it
    cannot reach approve()/execution (least privilege)."""
    def __init__(self, broker: CommandBroker) -> None:
        self._submit = broker.submit

    def submit(self, cmd: ProposedCommand) -> BrokerOutcome:
        return self._submit(cmd)
