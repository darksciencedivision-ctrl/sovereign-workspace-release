"""Conductor SELECTION state — Phase 15D `.selection` (directive §11 track 15D).

The conductor is an INTERFACE plus a runtime selection (invariant 3 / I-CN1): "conductor" is never a
vendor default and never the name of a model. The operator's current selection is **fable-5**
(`reason: operator_selected`, OP-6). This module is the single deterministic source of that record
and of the one distinction 15D turns on:

    SELECTION  = what the operator chose      (fable-5 — an interface label, stable)
    REQUESTED  = what was asked of the CLI    (the `--model` slug, or none ⇒ CLI default)
    EXECUTING  = what actually ran            (the checkpoint id a LIVE reply reported)

All three are recorded SEPARATELY and none is inferred from the others. `executing.model` is
**None until a live reply reports a checkpoint id** — a conductor that was refused at a gate, or a
mock run, executed nothing, and this record says so rather than echoing the requested slug back as
though it had run.

Vendor neutrality (invariants 3, 4, 20): this module imports NO adapter. Slug resolution is a
provider-neutral default that any adapter-specific resolver may replace via `resolver=`, so a
successor conductor on a different backend (codex, a local Ollama model) binds through the same
path. The pinned selection's `adapter` field is a plain recorded string; a test pins it structurally
to the adapter constant so the two cannot drift without a failing test.

Fail-closed rules (Buildout §4): the reason enum and the record's key set are read from the FROZEN
`checkpoint@1.0` `current_conductor` definition (never a local copy that could disagree); a blank
model, an unknown reason, a non-date-time timestamp, a non-mapping record, or a smuggled extra key
all RAISE; `executing_verified` is True only when a live reply actually reported a checkpoint id; an
unavailable model resolves to the CLI-default **recorded** fallback (directive §11 15B — never
silent). No clock is read here — every timestamp is injected, so records are deterministic.

`executing_verified` is True ONLY when the caller supplies an `ExecutingEvidence` (U45, discharged
at `phase-15d.gate`). A bare `reported_model` string — which any caller could produce, with no type
and no freshness scoping — is recorded as an UNVERIFIED claim and never becomes a checkpoint.

This module holds NO authority: it labels and records; it does not spawn, authorize, or select on
the operator's behalf (invariant 1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "checkpoint.schema.json")
    .read_text(encoding="utf-8"))
_CURRENT_CONDUCTOR = _SCHEMA["definitions"]["current_conductor"]

#: The authorized `reason` values, read from the frozen schema rather than restated here, so this
#: module cannot silently disagree with checkpoint@1.0. (The schema file's own integrity is the
#: freeze manifest's job — `tools/manifest/compute_manifest.py --check` — not this import.)
CONDUCTOR_SELECTION_REASONS: tuple[str, ...] = tuple(_CURRENT_CONDUCTOR["properties"]["reason"]["enum"])

#: The keys checkpoint@1.0 allows (`additionalProperties: false`). Exported so the succession path
#: reads ONE key set instead of keeping a drift-capable copy.
CONDUCTOR_RECORD_KEYS: tuple[str, ...] = tuple(_CURRENT_CONDUCTOR["properties"])
_REQUIRED_KEYS: frozenset[str] = frozenset(_CURRENT_CONDUCTOR["required"])


class ConductorSelectionError(ValueError):
    """A selection record that cannot be trusted — refused, never coerced into a default."""


def _require_datetime(value: Any, field: str) -> str:
    """Accept only a full date-time (schema `format: date-time`). `datetime.fromisoformat` alone
    would also accept a bare date (`2026-07-19`), which the frozen definition does not."""
    if not isinstance(value, str) or not value.strip():
        raise ConductorSelectionError(f"{field} must be a non-empty ISO-8601 date-time")
    if "T" not in value:
        raise ConductorSelectionError(
            f"{field} must be a date-TIME (schema format: date-time), got {value!r}")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConductorSelectionError(f"{field} is not an ISO-8601 date-time: {value!r}") from exc
    return value


@dataclass(frozen=True)
class ConductorSelection:
    """The `current_conductor` record (canonical handoff §2.14.1 / Plan §9.11), validated on
    construction. Immutable: a change of selection produces a NEW record (with its own `since`), so
    the history of who conducted when is never overwritten.

    `directive_version` defaults to None: a provenance field is CARRIED or ABSENT, never inferred
    onto a record that did not state it (invariant 11).
    """

    model: str
    reason: str
    since: str
    adapter: str | None = None
    directive_version: str | None = None
    subscription_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConductorSelectionError("conductor selection `model` must be a non-empty string")
        # normalize once, at the boundary, so the recorded label and the slug that reaches argv
        # cannot differ by stray whitespace
        object.__setattr__(self, "model", self.model.strip())
        if self.reason not in CONDUCTOR_SELECTION_REASONS:
            raise ConductorSelectionError(
                f"reason {self.reason!r} is not one of {CONDUCTOR_SELECTION_REASONS} "
                "(frozen checkpoint@1.0 enum)")
        _require_datetime(self.since, "since")

    def as_current_conductor(self) -> dict[str, Any]:
        """The checkpoint@1.0 `current_conductor` record. Only schema-declared keys are emitted, so
        it validates under `additionalProperties: false` without a caller-side filter."""
        return {key: getattr(self, key) for key in CONDUCTOR_RECORD_KEYS}


def selection_from_record(record: Any) -> ConductorSelection:
    """Parse a `current_conductor` record back into a selection, fail closed. An unknown key is a
    refusal (not a tolerated extra): the record is the operator's authority statement, so anything
    the schema does not declare must not ride along silently."""
    if not isinstance(record, Mapping):
        raise ConductorSelectionError(f"conductor record must be a mapping, got {type(record).__name__}")
    unknown = set(record) - set(CONDUCTOR_RECORD_KEYS)
    if unknown:
        raise ConductorSelectionError(f"unknown key(s) in conductor record: {sorted(unknown)}")
    missing = _REQUIRED_KEYS - set(record)
    if missing:
        raise ConductorSelectionError(f"missing required key(s) in conductor record: {sorted(missing)}")
    return ConductorSelection(**{key: record[key] for key in record})


#: The provider the operator's selection currently runs on. A plain recorded string — this module
#: imports no adapter (vendor neutrality, invariant 4/20). `tests/unit/test_conductor_selection.py`
#: pins it structurally to `adapters.frontier.claude_code.CLAUDE_CODE_ADAPTER` so it cannot drift.
_SELECTION_ADAPTER = "claude_code"

#: The operator's current runtime selection (OP-6, directive §11 15D). NOTE on the two dates in the
#: repo: `2026-07-16` (freeze manifest, `conductor/IDENTITY.md`, the schema's $comment) records when
#: the operator first selected fable-5; `2026-07-19` is when that selection became the LIVE conductor
#: under OP-6, which is the date directive §11 15D pins for this record. Same selection, two events.
OPERATOR_SELECTED_CONDUCTOR = ConductorSelection(
    model="fable-5",
    reason="operator_selected",
    since="2026-07-19T00:00:00+00:00",
    adapter=_SELECTION_ADAPTER,
    directive_version="v2.4",
)


def default_model_resolver(requested: str | None) -> tuple[str | None, str]:
    """Provider-neutral slug resolution: a requested slug is carried VERBATIM (still unverified —
    only a live reply confirms a CLI accepts it); `None` means "use the backend default and RECORD
    the fallback" (directive §11 15B — never silent). Nothing is fabricated.

    Adapter-specific resolvers (e.g. `claude_code.resolve_claude_model_ref`) are drop-in
    replacements via `bind_conductor_selection(resolver=...)`."""
    if requested and requested.strip():
        return requested.strip(), f"requested model {requested.strip()!r} (accepted id unverified until a live reply)"
    return None, "no model requested — backend default (recorded fallback, directive §11 15B)"


@dataclass(frozen=True)
class ExecutingEvidence:
    """Provider-neutral PROOF that a checkpoint id came from a real call in THIS binding.

    U45, discharged at `phase-15d.gate`. The pre-fix rule verified an executing checkpoint from
    `isinstance(reported_model, str) and reported_model.strip()` — so any caller holding a string
    could mint a verified checkpoint, with no type check and no freshness scoping. A bare string is
    now inert; constructing this object is the caller's explicit assertion that it applied the
    vendor-side rule (`claude_code.verify_reported_checkpoint`: exact CLI class + a call spent since
    a bind-time snapshot + a checkpoint the CLI itself reported + stamped by a call made AFTER that
    snapshot).

    This module stays vendor-neutral (invariants 4/20): it imports no adapter and knows nothing
    about how the evidence was obtained — it records that a caller who could see the backend
    asserted it. That is a narrower claim than "this module verified it", and it is the true one.
    The falsification limit of the underlying rule (U43) is inherited unchanged.

    `rule` NAMES the verification the caller applied, and is carried into the durable record
    (invariant 11 — provenance on every shared entry). Without it the artifact stated a flat
    `verified: true` whose only account of ITSELF lived in a code comment, while the packet gate
    read that boolean as sufficient authority for a `live` leg. A record that cannot say how it was
    verified is asking to be trusted rather than read.
    """

    checkpoint: str
    rule: str = "claude_code.verify_reported_checkpoint@1"

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint, str) or isinstance(self.checkpoint, bool) \
                or not self.checkpoint.strip():
            raise ConductorSelectionError(
                "executing evidence needs a non-blank checkpoint string reported by the backend")
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise ConductorSelectionError("executing evidence must name the rule that verified it")
        object.__setattr__(self, "checkpoint", self.checkpoint.strip())
        object.__setattr__(self, "rule", self.rule.strip())


@dataclass(frozen=True)
class ConductorBinding:
    """A selection bound to a concrete backend: what was CHOSEN, what was REQUESTED, and what
    actually RAN — three separate facts, none inferred from the others.

    `executing_model` is None unless a live reply reported a checkpoint id. `resolved_slug` is the
    `--model` value that would reach (or reached) argv; a fallback records None there.
    """

    selection: ConductorSelection
    requested_model: str | None
    resolved_slug: str | None
    executing_model: str | None
    executing_verified: bool
    is_fallback: bool
    note: str
    #: A checkpoint a caller CLAIMED without evidence. Recorded rather than dropped: an operator
    #: reading the record must be able to see that a claim was made and was not backed (U45).
    reported_unverified: str | None = None
    #: The rule that verified `executing_model`, or None when nothing was verified (invariant 11).
    verified_by: str | None = None

    def label_mismatch(self) -> bool:
        """True when a VERIFIED executing checkpoint id is not identical to the selection label.

        Expect this to be True on a normal live run: the selection is an operator LABEL
        ("fable-5") while a CLI reports a full checkpoint id ("claude-fable-5-<date>"). No
        label→checkpoint mapping is established yet — that is a fact the FIRST live smoke supplies
        (owed item), so this flag surfaces the pair for the operator rather than adjudicating it.
        An unverified value proves nothing and is never reported as a mismatch."""
        return bool(self.executing_verified and self.executing_model != self.selection.model)

    def as_record(self) -> dict[str, Any]:
        return {
            "selection": self.selection.as_current_conductor(),
            "executing": {
                # None until a live reply reports one — a refused or mock run executed NOTHING
                "model": self.executing_model,
                "requested": self.requested_model,
                "resolved_slug": self.resolved_slug,   # None => backend default (recorded fallback)
                "verified": self.executing_verified,
                "is_fallback": self.is_fallback,
                "note": self.note,
                # an unbacked claim, surfaced not silently dropped (U45); None on every honest path
                "reported_unverified": self.reported_unverified,
                # how `verified` was established — a boolean that cannot say why is not provenance
                "verified_by": self.verified_by,
            },
            # see label_mismatch(): a label/checkpoint-id pair, not an adjudicated conflict
            "label_mismatch": self.label_mismatch(),
        }


def bind_conductor_selection(
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
    *,
    requested_model: str | None = None,
    reported_model: Any = None,
    executing_evidence: ExecutingEvidence | None = None,
    model_available: bool | None = None,
    resolver: Callable[[str | None], tuple[str | None, str]] = default_model_resolver,
) -> ConductorBinding:
    """Bind the conductor selection to a backend, honestly.

    `requested_model` defaults to the selection's own model, so the conductor asks for **fable-5**
    rather than silently accepting whatever the CLI defaults to (directive §11 15D: "model_ref =
    fable-5 if available else recorded fallback").

    `model_available=False` records the fallback branch of that requirement (backend default +
    RECORDED note). `None` means "not probed", and is still the honest state for any backend with no
    probe behind it. For `claude_code` that probe now EXISTS and is in the production path
    (`adapters.frontier.claude_model_probe` + `tools/live/probe_conductor_model.py`, Phase 17A
    `.roundtrip`): the launch ticket and the badge feed pass True/False through this parameter from a
    recorded live observation, and an undecidable probe deliberately passes None so the operator's
    selection is carried verbatim rather than demoted.

    `executing_evidence` is the ONLY route to a verified executing checkpoint (U45, discharged at
    `phase-15d.gate`). It carries a checkpoint whose caller applied the vendor-side rule — exact CLI
    class, a call spent, a checkpoint the CLI itself reported, stamped by a call made after the
    caller's bind-time snapshot.

    `reported_model` is a RAW, UNBACKED claim and can no longer verify anything. It is retained
    because dropping it would hide that a claim was made: it is recorded verbatim under
    `reported_unverified` and named in the note, while `executing.model` stays None. Passing BOTH a
    bare claim and evidence that disagree RAISES — a record must not present one as the other.
    """
    requested = requested_model if requested_model is not None else selection.model
    if model_available is False:
        slug, base_note = resolver(None)  # backend default + its recorded-fallback note
        note = f"requested model {requested!r} unavailable — {base_note}"
    else:
        slug, note = resolver(requested)

    claimed = reported_model.strip() if isinstance(reported_model, str) and reported_model.strip() \
        else None
    if executing_evidence is not None and claimed is not None \
            and claimed != executing_evidence.checkpoint:
        raise ConductorSelectionError(
            f"conflicting executing checkpoints: unbacked claim {claimed!r} vs evidence "
            f"{executing_evidence.checkpoint!r} — refusing to record one as the other")

    if executing_evidence is not None:
        # Replace (not append) the resolver's "unverified" text — the two must not both appear. The
        # FALLBACK reason is preserved separately, because it is a different fact: erasing it here
        # dropped "why the CLI default was used" on exactly the runs that reached a provider
        # (directive §11 15B — a fallback is RECORDED, never silent).
        fallback_note = f" [{note}]" if model_available is False else ""
        note = (f"executing checkpoint {executing_evidence.checkpoint!r} reported by the live "
                f"backend and verified for this binding by {executing_evidence.rule} "
                f"(requested {requested!r}){fallback_note}")
    elif claimed is not None:
        note = (f"{note}; a checkpoint {claimed!r} was claimed with NO verification evidence and is "
                f"recorded UNVERIFIED (executing model stays unknown)")
    return ConductorBinding(
        selection=selection,
        requested_model=requested,
        resolved_slug=slug,
        executing_model=executing_evidence.checkpoint if executing_evidence else None,
        executing_verified=executing_evidence is not None,
        is_fallback=slug is None,
        note=note,
        reported_unverified=claimed if executing_evidence is None else None,
        verified_by=executing_evidence.rule if executing_evidence else None,
    )


def succession_selection(model: str, *, since: str, adapter: str | None = None,
                         subscription_ref: str | None = None,
                         directive_version: str | None = None) -> ConductorSelection:
    """The selection a SUCCESSOR conductor adopts after the predecessor is lost (invariant 28).
    `reason` is `succession` — distinguishable from an operator choice forever after, so the register
    can tell "the operator picked this" from "the system recovered onto this"."""
    return ConductorSelection(model=model, reason="succession",
                              since=_require_datetime(since, "since"), adapter=adapter,
                              directive_version=directive_version, subscription_ref=subscription_ref)


def restore_operator_selection(
    current: ConductorSelection | Mapping[str, Any],
    *,
    since: str,
    selection: ConductorSelection = OPERATOR_SELECTED_CONDUCTOR,
) -> ConductorSelection:
    """Restore the operator's selection after a succession (15D: "then restore selection").

    Returns the pinned operator selection stamped with the RESTORE moment, not the original pin —
    the record must say when THIS conductor started conducting. `current` is parsed fail-closed and
    must actually be a succession state: restoring something that was never succeeded would write an
    unfounded `operator_selected` record, so it is refused rather than silently accepted.
    """
    if not isinstance(current, ConductorSelection):
        current = selection_from_record(current)
    if current.reason != "succession":
        raise ConductorSelectionError(
            f"restore applies to a succession state; current reason is {current.reason!r} "
            "(refusing to write an unfounded operator_selected record)")
    return replace(selection, since=_require_datetime(since, "since"))
