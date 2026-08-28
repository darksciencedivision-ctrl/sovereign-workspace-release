"""Live model-availability PROBE for the `claude` CLI — Phase 17A `.roundtrip`.

**The defect this closes.** Phase 17A `.pty` made the shell run the real interactive `claude` session
in pane 1's ConPTY with the operator's conductor selection as its `--model` slug (`fable-5`). The
session was born, supervised, counted and bound — and every prompt typed into it came back with

    There's an issue with the selected model (fable-5). It may not exist or you may not have
    access to it. Run /model to pick a different model.

A live session that cannot answer is the black pane with extra steps. The whole build has said, since
Phase 15B, that an operator model LABEL is *not* a CLI slug and that the accepted id "is only
confirmed by a live smoke" — with `bind_conductor_selection(model_available=...)` already wired for
"the live probe that the first live smoke supplies". This module is that probe.

**What it establishes, and what it refuses to.** A slug is ACCEPTED only when the host CLI ran a real
one-shot call on it. Three things are deliberately NOT evidence:

  * a 0 exit — the CLI delivers "no such model" as an ordinary assistant reply, so the reply TEXT is
    checked against the CLI's own wording as well as the error path;
  * an auth/rate/usage-limit condition — it says nothing about the slug, so the probe stops and
    records INCONCLUSIVE rather than demoting the operator's selection on unrelated evidence;
  * a backend that is not the exact vendor CLI class — a mock spends no subscription call and can
    never mint an accepted slug (the same `is_live_cli_backend` rule the rest of the build uses).

**Candidates are derived, never invented.** For a label the vendor's own id namespace supplies one
alternative spelling: `claude-<label>` (the CLI's release notes name its ids that way — e.g.
`claude-opus-5`). Both forms are *candidates*; only a successful call promotes one. Exhausting them
with model-unavailable answers is the CLI-DEFAULT FALLBACK — recorded and surfaced in the ticket,
the chrome and the receipt, never silent (directive §11 15B / §16 17A).

**Fail-closed direction for a CACHE.** The record is a cache of a live observation, so an unreadable
or shape-drifted ledger reads as *unprobed* (carry the label verbatim, exactly as before this
module existed) — never as *unavailable*, which would silently strip the operator's selection.

Pure except for `probe_claude_model`'s injected `backend_factory`: the live call is the caller's, so
every rule here is tested with zero live calls.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from adapters.frontier.claude_code import (
    ClaudeCliBackend,
    ClaudeCodeAuthError,
    bind_calls_snapshot,
    is_live_cli_backend,
    verify_reported_checkpoint,
)

#: Pinned so a consumer (the launch emitter, the shell, a receipt) validates the shape it reads.
MODEL_PROBE_SCHEMA = "claude_model_probe@1.0"

#: NAMED in every record (invariant 11 — a record that cannot say how it was verified is asking to
#: be trusted rather than read).
PROBE_RULE = ("claude_model_probe@1: a slug is ACCEPTED only when the exact vendor CLI class ran a "
              "real one-shot call on it and the reply was not the CLI's own model-unavailable "
              "message; auth/rate conditions are inconclusive, never a demotion")

#: The smallest useful live exchange (§16 live-budget discipline: probes are real tokens).
PROBE_PROMPT = "Reply with the single word: ok"

#: The vendor id namespace the CLI documents for its own models (`claude-opus-5`, …). Used to derive
#: ONE alternative spelling of an operator label — not to invent arbitrary ids.
_VENDOR_PREFIX = "claude-"

#: The CLI's own wording for "that model is not available to you", in both the error path and the
#: assistant-reply path. Matched case-insensitively on either.
_MODEL_UNAVAILABLE_MARKERS = (
    "issue with the selected model",
    "may not exist or you may not have access",
    "run /model to pick a different model",
    "not_found_error",
    "model not found",
    "unknown model",
    "invalid model",
)


def candidate_slugs_for(label: str | None) -> tuple[str, ...]:
    """The ordered `--model` slugs to try for an operator LABEL. Deterministic, deduplicated, and
    empty for a blank label (the CLI default needs no slug, so there is nothing to probe)."""
    if not isinstance(label, str) or not label.strip():
        return ()
    base = label.strip()
    out = [base]
    if not base.lower().startswith(_VENDOR_PREFIX):
        out.append(f"{_VENDOR_PREFIX}{base}")
    return tuple(dict.fromkeys(out))


def classify_probe_failure(detail: str | None) -> str:
    """`model_unavailable` when the text carries the CLI's own "no such model" wording, else
    `cli_error`. Auth/rate is classified by its EXCEPTION TYPE, not by text — the CLI's own
    fail-closed pause signal is a stronger fact than a marker match."""
    text = (detail or "").lower()
    if any(marker in text for marker in _MODEL_UNAVAILABLE_MARKERS):
        return "model_unavailable"
    return "cli_error"


def _looks_unavailable(text: str | None) -> bool:
    return classify_probe_failure(text) == "model_unavailable"


@dataclass(frozen=True)
class ProbeAttempt:
    """One candidate slug, one live call, one honest outcome."""

    slug: str
    accepted: bool
    classification: str          # accepted | model_unavailable | auth_or_rate | cli_error |
    #                              not_a_live_backend
    checkpoint: str | None = None
    detail: str = ""             # truncated; never a credential (the CLI's own message)

    def as_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "accepted": self.accepted,
                "classification": self.classification, "checkpoint": self.checkpoint,
                "detail": self.detail[:300]}


@dataclass(frozen=True)
class ModelProbeRecord:
    """What the probe learned about ONE operator label, with its provenance.

    `conclusive=False` means the probe could not decide (auth/rate, a non-live backend, nothing
    tried). Consumers MUST treat that as *unprobed*, not as unavailable — see
    `launch_model_resolution`."""

    label: str
    candidates: tuple[str, ...]
    accepted_slug: str | None
    checkpoint: str | None
    conclusive: bool
    is_fallback: bool
    attempts: tuple[ProbeAttempt, ...]
    probed_at: str
    note: str
    schema: str = MODEL_PROBE_SCHEMA
    rule: str = PROBE_RULE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "rule": self.rule, "label": self.label,
            "candidates": list(self.candidates), "accepted_slug": self.accepted_slug,
            "checkpoint": self.checkpoint, "conclusive": self.conclusive,
            "is_fallback": self.is_fallback, "probed_at": self.probed_at, "note": self.note,
            "attempts": [a.as_dict() for a in self.attempts],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "ModelProbeRecord | None":
        """Parse a stored record, or None on ANY shape drift (fail closed to unprobed)."""
        if not isinstance(raw, dict) or raw.get("schema") != MODEL_PROBE_SCHEMA:
            return None
        label = raw.get("label")
        conclusive = raw.get("conclusive")
        is_fallback = raw.get("is_fallback")
        accepted = raw.get("accepted_slug")
        checkpoint = raw.get("checkpoint")
        probed_at = raw.get("probed_at")
        if not isinstance(label, str) or not label.strip():
            return None
        if not isinstance(conclusive, bool) or not isinstance(is_fallback, bool):
            return None
        if accepted is not None and (not isinstance(accepted, str) or not accepted.strip()):
            return None
        if checkpoint is not None and not isinstance(checkpoint, str):
            return None
        if not isinstance(probed_at, str) or not probed_at:
            return None
        cands = raw.get("candidates")
        if not isinstance(cands, list) or any(not isinstance(c, str) for c in cands):
            return None
        attempts: list[ProbeAttempt] = []
        for a in raw.get("attempts") or []:
            if not isinstance(a, dict) or not isinstance(a.get("slug"), str):
                return None
            attempts.append(ProbeAttempt(
                slug=a["slug"], accepted=bool(a.get("accepted")),
                classification=str(a.get("classification") or "cli_error"),
                checkpoint=a.get("checkpoint") if isinstance(a.get("checkpoint"), str) else None,
                detail=str(a.get("detail") or "")))
        # A record cannot be both "the CLI default is the answer" and "this slug is the answer".
        if is_fallback and accepted is not None:
            return None
        return cls(label=label, candidates=tuple(cands), accepted_slug=accepted,
                   checkpoint=checkpoint, conclusive=conclusive, is_fallback=is_fallback,
                   attempts=tuple(attempts), probed_at=probed_at,
                   note=str(raw.get("note") or ""), rule=str(raw.get("rule") or PROBE_RULE))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_backend_factory(slug: str) -> ClaudeCliBackend:
    """The real one-shot vendor backend for one candidate slug. Short timeout: a probe that hangs is
    a startup that hangs, and an unanswered probe is honestly inconclusive."""
    return ClaudeCliBackend(model=slug, timeout_s=90.0)


def probe_claude_model(
    label: str,
    *,
    backend_factory: Callable[[str], Any] = default_backend_factory,
    prompt: str = PROBE_PROMPT,
    now: Callable[[], str] = _utc_now,
) -> ModelProbeRecord:
    """Find the `--model` slug the host CLI actually accepts for an operator LABEL.

    ONE minimal live call per candidate, stopping at the first acceptance (§16 live-budget
    discipline) and at the first auth/rate condition (a throttled host is not asked twice)."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("probe_claude_model needs an operator model label to resolve")
    label = label.strip()
    candidates = candidate_slugs_for(label)
    attempts: list[ProbeAttempt] = []
    accepted_slug: str | None = None
    checkpoint: str | None = None
    inconclusive_reason: str | None = None

    for slug in candidates:
        backend = backend_factory(slug)
        if not is_live_cli_backend(backend):
            # A mock cannot spend a subscription call, so it can neither accept nor rule out a slug.
            attempts.append(ProbeAttempt(slug=slug, accepted=False,
                                         classification="not_a_live_backend",
                                         detail="backend is not the exact vendor CLI class"))
            inconclusive_reason = "no live backend was available to probe with"
            break
        calls_before = bind_calls_snapshot(backend)
        try:
            # No `max_tokens`: the CLI backend emits no such flag, so passing one would imply a cap
            # that does not exist. The PROMPT is the only bound on this exchange, and it asks for one
            # word.
            reply = backend.generate(prompt)
        except ClaudeCodeAuthError as exc:
            attempts.append(ProbeAttempt(slug=slug, accepted=False, classification="auth_or_rate",
                                         detail=str(exc)))
            inconclusive_reason = f"auth/rate condition, not a model verdict: {exc}"
            break
        except Exception as exc:  # noqa: BLE001 — every other failure is classified, never swallowed
            cls = classify_probe_failure(str(exc))
            attempts.append(ProbeAttempt(slug=slug, accepted=False, classification=cls,
                                         detail=str(exc)))
            if cls == "model_unavailable":
                continue
            inconclusive_reason = f"the CLI failed for an unrelated reason: {exc}"
            break
        if _looks_unavailable(reply):
            # 0 exit, parsed JSON — and the CLI's own "no such model" text inside the reply.
            attempts.append(ProbeAttempt(slug=slug, accepted=False,
                                         classification="model_unavailable", detail=str(reply)))
            continue
        evidence = verify_reported_checkpoint(backend, calls_before=calls_before)
        checkpoint = evidence["model"] if evidence else None
        accepted_slug = slug
        attempts.append(ProbeAttempt(slug=slug, accepted=True, classification="accepted",
                                     checkpoint=checkpoint, detail=str(reply)))
        break

    if accepted_slug is not None:
        note = (f"the host `claude` CLI accepted --model {accepted_slug!r} for the selection "
                f"{label!r}"
                + (f"; it reported executing checkpoint {checkpoint!r} on the probe call"
                   if checkpoint else
                   "; it reported no checkpoint on the probe call, so the executing model stays "
                   "unverified"))
        return ModelProbeRecord(label=label, candidates=candidates, accepted_slug=accepted_slug,
                                checkpoint=checkpoint, conclusive=True, is_fallback=False,
                                attempts=tuple(attempts), probed_at=now(), note=note)
    if inconclusive_reason is None and attempts and all(
            a.classification == "model_unavailable" for a in attempts):
        note = (f"the host `claude` CLI rejected every candidate slug for {label!r} "
                f"({', '.join(candidates)}) — recorded CLI-default FALLBACK, surfaced in the "
                f"chrome and the ticket, never silent (directive §11 15B)")
        return ModelProbeRecord(label=label, candidates=candidates, accepted_slug=None,
                                checkpoint=None, conclusive=True, is_fallback=True,
                                attempts=tuple(attempts), probed_at=now(), note=note)
    note = (f"INCONCLUSIVE for {label!r} — {inconclusive_reason or 'nothing was probed'}; the "
            f"selection is carried verbatim exactly as before the probe existed (a cache that "
            f"cannot decide must not demote the operator's selection)")
    return ModelProbeRecord(label=label, candidates=candidates, accepted_slug=None, checkpoint=None,
                            conclusive=False, is_fallback=False, attempts=tuple(attempts),
                            probed_at=now(), note=note)


def launch_model_resolution(label: str, *, record: ModelProbeRecord | None) -> dict[str, Any]:
    """Translate a probe record into the two arguments the governed launch path already understands
    (`model`, `model_available` on `spawn_conductor_pane` / `bind_conductor_selection`).

    Three states, three honest answers:
      * ACCEPTED  ⇒ `model=<accepted slug>`, `model_available=True` — the conductor asks for the
        model the CLI really takes, even when its spelling differs from the operator's label;
      * FALLBACK  ⇒ `model=None`, `model_available=False` — the binding records "requested …
        unavailable" and the chrome carries `is_fallback` (never silent);
      * anything else ⇒ `model=None`, `model_available=None` — unprobed, so the selection's own
        label is used exactly as before.
    """
    if record is None:
        return {"label": label, "model": None, "model_available": None, "source": "unprobed",
                "record": None}
    if not record.conclusive:
        return {"label": label, "model": None, "model_available": None, "source": "inconclusive",
                "record": record.as_dict()}
    if record.accepted_slug:
        return {"label": label, "model": record.accepted_slug, "model_available": True,
                "source": "probe-ledger", "record": record.as_dict()}
    return {"label": label, "model": None, "model_available": False, "source": "probe-ledger",
            "record": record.as_dict()}


def default_ledger_path() -> Path:
    """`SOW_MODEL_PROBE_LEDGER` if set (the override self-checks use), else the host-local
    `.sovereign_store/` runtime state inside the repo (gitignored — a probe result is an observation
    about THIS host, never a committed claim)."""
    override = os.environ.get("SOW_MODEL_PROBE_LEDGER")
    if override and override.strip():
        return Path(override.strip())
    root = Path(__file__).resolve().parents[2]
    return root / ".sovereign_store" / "model_probe" / "claude_code.json"


@dataclass
class ModelProbeLedger:
    """Host-local cache of probe records, keyed by operator label.

    Reads fail CLOSED TO UNPROBED: a missing file, unreadable JSON, a shape drift or a
    self-contradictory record all yield None, so the launch path behaves exactly as it did before
    this cache existed. Writes are atomic (temp + replace) so a crash mid-write cannot leave a
    half-record that reads as a verdict."""

    path: Path = field(default_factory=default_ledger_path)

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
            return {}
        return raw

    def read(self, label: str) -> ModelProbeRecord | None:
        entry = (self._load().get("entries") or {}).get(str(label))
        record = ModelProbeRecord.from_dict(entry)
        if record is None or record.label != str(label):
            return None
        return record

    def write(self, record: ModelProbeRecord) -> None:
        data = self._load()
        entries = dict(data.get("entries") or {})
        entries[record.label] = record.as_dict()
        payload = {"schema": MODEL_PROBE_SCHEMA, "entries": entries, "updated_at": _utc_now()}
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.write("\n")
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def resolve_launch_model(label: str, *, ledger: ModelProbeLedger | None = None) -> dict[str, Any]:
    """`launch_model_resolution` against the host ledger. OFFLINE — the launch emitter must never
    make a live call inside the shell's bounded ticket request."""
    led = ledger if ledger is not None else ModelProbeLedger()
    return launch_model_resolution(label, record=led.read(label))
