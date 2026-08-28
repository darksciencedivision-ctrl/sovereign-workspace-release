"""Conductor voice-IN feed — Phase 16E `.engine` (directive §15 track 16E; OP-8 §13.5; closes the
READ half of U67).

OP-10 first-use finding (3): *"voice unusable"*. Phase-15E `.voice` shipped the routing AUTHORITY
(`voice_bridge/conductor_voice.ConductorVoiceBridge` over the real `CommandBroker`) and the pure JS
render model, but the shell's `voice:propose` only RECORDED a push-to-talk hold — no engine was
selected, no transcript produced, nothing routed (**U67**). Track 16E closes that end-to-end. This
`.engine` sub-step delivers the honest, engine-SELECTED read half: pick the STT engine (real Parakeet
only when the host stack is present AND a real adapter exists — track 14D; otherwise the mock behind
the same `STTEngine` contract, ALWAYS surfaced as a VISIBLE mock engine, never a silent
pretend-to-hear), route ONE captured utterance through the REAL bridge over a REAL broker, and fold the
`ConductorInputOutcome` into the stable `conductor_voice_feed@1.0` JSON the shell renders — the SAME
bounded `py -3.12` read-source pattern the 16B picker and the 16C/16D feeds use.

The `.wire` sub-step then connects the shell talk button to this feed and DELIVERS a CHAT outcome into
the conductor's ConPTY input (the operator-run write, D-P16-0 in-Electron self-check). Here the
`ConductorChatSink` is a recording sink — the headless stand-in for that write.

MOCK-FIRST, no live call (directive §6 / §10.4): the bridge runs the mock STT + a mock/local broker,
so `--emit-conductor-voice` NEVER spawns a `claude`/`codex` process (§2.2/§2.4). NO speech-OUT
(I-V2/D-VOICE-02): the bridge exposes no synthesis method by construction; `tts:False` is carried
through the feed. Audio is transcribe-then-discard (invariant 26); the `audio_ref` is a capture
stand-in (no real PCM), discarded by the adapter's policy.

Fail-closed (invariant 3 / invariant 20 spirit): any fault ⇒ the UNAVAILABLE feed (`sourced:false`,
`reason`, a CLARIFY outcome, `mock` engine) — a 0-exit JSON line the shell renders as "voice
unavailable", never a fabricated "delivered to the conductor".
"""
from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Any

from adapters.voice_parakeet.engine import (
    MockSTT,
    STTEngine,
    detect_voice_stack,
    real_parakeet_available,
)
from adapters.voice_parakeet.wsl_parakeet import PARAKEET_WSL_NAME, build_real_engine
from control_plane.orchestration.operator_surface import ApprovalQueue, mirror_broker_outcome
from voice_bridge.command_broker import BrokerOutcome, CommandBroker, ProposedCommand
from voice_bridge.conductor_voice import (
    ConductorInputKind,
    ConductorInputOutcome,
    ConductorVoiceBridge,
)

#: Pinned so the shell source validates the shape it parses (a drifted producer is refused).
CONDUCTOR_VOICE_FEED_SCHEMA = "conductor_voice_feed@1.0"

#: A representative captured utterance (a scripted `MockSTT` ref stand-in). "show status" is a SAFE
#: verb, so the bridge delivers it as ordinary CHAT — the delivery half of the voice-IN path.
DEFAULT_AUDIO_REF = "audio:show-status"

#: The honest U67/16F record carried on the STAND-IN feed: with a PCM-less `audio:` ref, real mic
#: capture and the interactive conductor ConPTY write are both operator-run surfaces.
LIVE_CAPTURE_OWED: dict[str, Any] = {
    "owed": True,
    "issue": "16F",
    "note": ("the ROUTING is real (bridge + broker) and the transcript is engine-selected, but real "
             "microphone capture and the write of a CHAT transcript into the interactive conductor "
             "ConPTY are the operator-run surfaces (a real PCM stream, an admitted live conductor "
             "session) — the assembled-run evidence is owed to 16F."),
}

#: Phase 17C `.mic`: what is ACTUALLY still owed once a real WAV has been transcribed. Repeating the
#: stand-in record on a feed that just ran real PCM through real WSL Parakeet would be a false OWED.
#:
#: But an OWED record that UNDERSTATES is the more dangerous error, because nobody re-checks a debt
#: that has been declared paid — it is how a gate gets closed over incomplete work. An earlier revision
#: of this constant said the microphone was the ONLY remaining debt, on the same feed whose `note`
#: reported the conductor ConPTY write as owed: one object asserting both. TWO things remain, and both
#: are named here. Directive §16 track 17C requires *"→ the LIVE 17A conductor session"*, and that leg
#: is not discharged by delivering into an admitted stand-in pane.
#:
#: Phase 17C `.close` discharges the SECOND of those two debts and says exactly how. What is left is the
#: operator's own microphone — and it stays `owed: True` for that reason, because the debt that remains
#: is the one no automated check can ever reach.
REAL_CAPTURE_OWED: dict[str, Any] = {
    "owed": True,
    "issue": "17C.mic",
    "note": ("real PCM was transcribed by the selected engine and routed by the real bridge — the "
             "capture, the engine selection and the routing WIRING are no longer owed. What remains: "
             "(1) the operator physically speaking into a microphone, which no automated check can "
             "reach (directive §16 track 17C — the spoken-mic half is operator first use); and (2) the "
             "routing is WIRED, not CALIBRATED — see `routing_limits` below. Neither is discharged by "
             "any receipt."),
    #: Phase 17C `.close` (spec-audit MAJOR-6). Saying "the routing is no longer owed" without this
    #: would be the understatement that matters: the two deterministic barriers in front of a LIVE
    #: conductor that can act are (a) an STT confidence that is derived from recognition rather than
    #: measured, so the bridge's low-confidence CLARIFY branch cannot fire on the real engine, and
    #: (b) a deterministic full-utterance lexicon, not semantic intent classification. Both are
    #: registered, and this record — the
    #: one carried on every real capture feed — has to name them, because a debt that only appears in
    #: an evidence report is a debt the running system never mentions.
    "routing_limits": (
        "U140: on the real engine confidence is 1.0 for any non-empty transcript (NeMo emits a "
        "log-probability, not a 0..1 score), so the bridge's low-confidence CLARIFY branch protects "
        "against silence, not against mishearing. U144 (NARROWED by phase-17c.close-revalidate): "
        "protected/destructive verbs, synonyms and common inflections are scanned across the WHOLE "
        "utterance, so polite prefixes no longer evade the broker; arbitrary semantic paraphrases "
        "outside that deterministic lexicon are not intent-classified. Production direct CHAT is "
        "therefore marked as a supervisor-owned non-executing voice turn: the launch-bound hook denies "
        "every tool call and permission escalation until that turn stops. Vendor mode chrome is "
        "interaction state only and never authority (invariants 25/29)."
    ),
    #: The delivery destination is a PER-CAPTURE fact this producer cannot observe: it emits the routing
    #: verdict, and the shell then writes (or honestly cannot write) into pane 1's ConPTY. So this field
    #: records the CAPABILITY and its evidence, and names the field that answers for the current
    #: utterance — never a blanket claim that this capture reached a live conductor.
    "live_conductor_write": (
        "the supervisor-owned non-executing voice-turn boundary is wired into the governed conductor "
        "launch and each direct CHAT delivery. The prior Phase 17C `.close` receipt proved an older "
        "tree and is NOT current-tree evidence; a fresh "
        "(docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json) packaged receipt must prove the exact "
        "re-enabled tree before this debt can close."
    ),
}


class _RecordingSink:
    """A submit-only `ConductorChatSink` that RECORDS deliveries instead of writing them into a live
    ConPTY. It is the headless stand-in for the interactive conductor write (operator-run, `.wire` +
    16F): least privilege — it cannot approve or execute, only record what CHAT would be delivered."""

    def __init__(self) -> None:
        self.delivered: list[dict[str, Any]] = []

    def deliver(self, message: Any) -> dict[str, Any]:
        record = {
            "text": message.text,
            "source": message.source,
            "semantic_key": message.semantic_key(),
        }
        self.delivered.append(record)
        # NOT the live write — a recorded stand-in. Honest about what is owed (invariant 3).
        return {"delivered_to": "conductor-input (recorded; live ConPTY write owed to .wire/16F)",
                "recorded": True}


def select_engine(
    engine: STTEngine | None = None,
    *,
    for_capture: bool = False,
    detection: Mapping[str, Any] | None = None,
    real_engine_factory: Any = None,
    blocking: bool = True,
    force_probe: bool = False,
) -> tuple[STTEngine, dict[str, Any]]:
    """Choose the STT engine HONESTLY and describe it for the VISIBLE mock/real indicator (directive §15
    track 16E — *"never silently pretend to hear"*).

    Phase 16E `.real`: the real Parakeet adapter now EXISTS (`WslParakeetSTT`, WSL-routed). It is selected
    only for a REAL capture (`for_capture=True`) on a host where `real_parakeet_available()` holds —
    because the headless indicator poll routes a scripted `audio:` stand-in that carries no PCM and so has
    nothing for a real engine to transcribe. On the stand-in path we still report `real_available:True`
    truthfully (the indicator renders "real ready"), but the transcript is the mock's — `mock:True`,
    stated. We NEVER construct a fake "real" engine and NEVER claim `mock:False` without one, and a real
    adapter that fails to construct falls back to the visible mock (fail-closed).

    `detection`/`real_engine_factory` are test seams (the emitter injects neither): pass a detection dict
    to simulate a host, or a factory to stand in for `WslParakeetSTT`.
    """
    det = dict(detection) if detection is not None else detect_voice_stack(blocking=blocking, force=force_probe)
    real_available = real_parakeet_available(det)
    # U74/F1: "we have not asked yet" is NOT "there is no real engine". `probing` rides alongside
    # `real_available` so the chrome can say "probing…" instead of the lie the operator saw.
    nemo_state = det.get("nemo_state") or ("available" if det.get("nemo") else "unavailable")
    probing = bool(det.get("wsl")) and nemo_state == "unprobed"
    factory = real_engine_factory or build_real_engine
    if engine is not None:
        # A caller-injected engine is a test/programmatic affordance only (the emitter never injects). It
        # is trusted as real ONLY when it is not the mock AND `real_available` holds (the fold at
        # `mock = mock or not real_available` re-enforces this), so the default path can never
        # pretend-to-hear via injection.
        eng: STTEngine = engine
        mock = getattr(engine, "name", "") == MockSTT.name
        reason = "engine injected by caller"
    elif real_available and for_capture:
        try:
            eng = factory()
            mock = False
            reason = "real Parakeet/NeMo detected in WSL — using the real engine for live capture"
        except Exception as exc:  # noqa: BLE001 — adapter init fault ⇒ visible mock, fail-closed
            eng = MockSTT()
            mock = True
            reason = (f"real Parakeet detected but the WSL adapter failed to initialise ({type(exc).__name__}: "
                      f"{exc}) — falling back to the mock STT engine (visible)")
    else:
        eng = MockSTT()
        mock = True
        if not for_capture:
            # 17E `.close` (spec-audit m3): on a stand-in the OPERATIVE cause is the stand-in itself —
            # it carries no PCM, so no real engine could have transcribed it whatever the probe says.
            # Reporting the probe's state as the cause put "the real engine may still be available" into
            # a receipt whose own capture leg had transcribed real PCM on the real engine 90 s earlier
            # (a fresh child process re-probes from cold). Cause first; engine state after, as context.
            state = ("the real engine is present and ACTIVE for live mic capture (16F)" if real_available
                     else "the WSL NeMo probe has not answered in this process" if probing
                     else "no real engine is detected on this host")
            reason = ("this stand-in carries no PCM, so the mock STT produced the transcript (visible) — "
                      f"{state}, which did not decide this path")
        elif probing:
            # U74: the probe has not answered. Say so — an unfinished probe is not an absent engine.
            reason = ("the WSL NeMo probe has not answered yet — voice engine state is PROBING (the mock "
                      "STT produced this stand-in transcript; the real engine may still be available)")
        else:
            # Name the components actually absent (from the authoritative detection dict) — never assert a
            # cause the code did not verify.
            missing = ", ".join(k for k in ("nvidia_gpu", "wsl", "nemo") if not det.get(k)) or "unknown"
            probe_reason = (det.get("probe") or {}).get("reason") if isinstance(det.get("probe"), Mapping) else None
            reason = (f"real Parakeet/NeMo not present on host (missing: {missing}) — using the mock STT "
                      f"engine (visible){f'; probe: {probe_reason}' if probe_reason else ''}")
    return eng, {
        "name": getattr(eng, "name", "unknown"),
        "mock": mock,
        "real_available": real_available,
        # `probing` can never coexist with `real_available` (an answered probe is not unprobed), so the
        # indicator's four states stay mutually exclusive.
        "probing": probing and not real_available,
        "nemo_state": nemo_state,
        "probe": dict(det.get("probe")) if isinstance(det.get("probe"), Mapping) else None,
        "real_engine": PARAKEET_WSL_NAME if (real_available or probing) else None,
        "detection": dict(det),
        "reason": reason,
    }


def _mirror(queue: ApprovalQueue, outcome: BrokerOutcome, command: ProposedCommand) -> str | None:
    """The bridge's `Mirror` (partial-applied over the queue): reflect a broker outcome into the
    drawer so a spoken protected/destructive action surfaces for the operator and the feed can carry
    its queue item id. Never re-classifies — carries the broker's `pending_id` (invariant 25)."""
    return mirror_broker_outcome(queue, outcome, command)


def fold_conductor_voice_feed(
    outcome: ConductorInputOutcome,
    *,
    engine_info: Mapping[str, Any],
    usage: Mapping[str, Any],
    deliveries: list[dict[str, Any]],
    audio_ref: str,
    real_capture: bool = False,
) -> dict[str, Any]:
    """Fold ONE `ConductorInputOutcome` into the stable `conductor_voice_feed@1.0` contract the shell
    renders. PURE (no I/O). Everything is DERIVED from the bridge's outcome — it invents nothing, and
    a CHAT outcome's `delivered_text` is only ever the text the bridge actually routed."""
    kind = outcome.kind.value
    delivered = kind == ConductorInputKind.CHAT.value
    return {
        "schema": CONDUCTOR_VOICE_FEED_SCHEMA,
        "sourced": True,
        "engine": {
            "name": str(engine_info.get("name") or "unknown"),
            # fail-closed: mock unless BOTH an explicit mock:False AND real_available:True
            "mock": bool(engine_info.get("mock", True)) or not bool(engine_info.get("real_available")),
            "real_available": bool(engine_info.get("real_available")),
            # U74: an unanswered probe is carried as its own state, never folded into "mock".
            "probing": bool(engine_info.get("probing")) and not bool(engine_info.get("real_available")),
            "nemo_state": str(engine_info.get("nemo_state") or "unavailable"),
            "probe": dict(engine_info["probe"]) if isinstance(engine_info.get("probe"), Mapping) else None,
            "real_engine": engine_info.get("real_engine"),
            "detection": dict(engine_info.get("detection") or {}),
            "reason": str(engine_info.get("reason") or ""),
        },
        "outcome": {
            "kind": kind,
            "source": outcome.source,
            "text": outcome.text,
            "confidence": outcome.confidence,
            "reason": outcome.reason,
            "queue_item_id": outcome.queue_item_id,
        },
        "delivered": delivered,
        "delivered_text": (outcome.chat_message.text if (delivered and outcome.chat_message) else None),
        "queued": kind == ConductorInputKind.PROPOSED_ACTION.value,
        "needs_clarification": kind == ConductorInputKind.CLARIFY.value,
        # what the recording sink saw — the stand-in for the live conductor write (never claimed live).
        "deliveries": list(deliveries),
        "tts": bool(usage.get("tts", False)),  # I-V2/D-VOICE-02: always False (STT-only, no synthesis)
        "transcribe_then_discard": int(usage.get("retained_now", 0)) == 0,
        # a stand-in ref (no real PCM), or — on the `.mic` path — the WAV the shell wrote and deletes
        "audio_ref": audio_ref,
        "live_capture_owed": dict(REAL_CAPTURE_OWED if real_capture else LIVE_CAPTURE_OWED),
        "torn_down": True,  # the bridge/adapter are closed before the feed is emitted
    }


#: Pinned so the shell validates the probe shape it parses (a drifted producer is refused).
VOICE_PROBE_FEED_SCHEMA = "voice_probe_feed@1.0"


def run_voice_probe(*, blocking: bool = True, force: bool = False) -> dict[str, Any]:
    """Emit `voice_probe_feed@1.0` — the ENGINE STATE ONLY (Phase 17C `.probe`, U74). No bridge, no
    broker, no transcript: the sole cost of this call is the WSL probe itself, so the shell can run it
    off the UI path and render "probing…" until it answers, instead of blocking its always-visible
    chrome for the probe budget or (as before U74) mislabelling an unanswered probe "mock engine".

    `blocking=False` reads the cached answer only and NEVER spawns WSL (`nemo_state:"unprobed"` when
    nothing is cached). `force=True` re-takes the probe now — the on-demand path (a talk press, an
    operator retry after finishing the install). Fail-closed: any fault yields `sourced:false` with the
    reason named and `real_available:false` — never a claimed real engine.
    """
    try:
        _eng, info = select_engine(for_capture=True, blocking=blocking, force_probe=force)
        return {
            "schema": VOICE_PROBE_FEED_SCHEMA,
            "sourced": True,
            "reason": str(info.get("reason") or ""),
            "engine": {
                "name": PARAKEET_WSL_NAME if info.get("real_available") else str(info.get("name") or "unknown"),
                # ALWAYS True: `mock` answers "did a mock engine produce the transcript?", and a probe
                # produces no transcript at all — nothing real has spoken. What the probe established
                # rides on `real_available`. Emitting `mock:false` here would make the shared render
                # model draw the REAL state ("parakeet-wsl"), asserting a transcription that never
                # happened; the honest render is READY ("parakeet-wsl ready"). The consumer used to
                # correct this on the way in, which put the honesty in the consumer rather than in the
                # contract — one new consumer away from an operator-visible false claim.
                "mock": True,
                "real_available": bool(info.get("real_available")),
                "probing": bool(info.get("probing")),
                "nemo_state": str(info.get("nemo_state") or "unavailable"),
                "probe": dict(info["probe"]) if isinstance(info.get("probe"), Mapping) else None,
                "real_engine": info.get("real_engine"),
                "detection": dict(info.get("detection") or {}),
                "reason": str(info.get("reason") or ""),
            },
            "blocking": bool(blocking),
            "forced": bool(force),
            "tts": False,   # I-V2/D-VOICE-02 — STT-only, carried on every voice surface
        }
    except Exception as exc:  # noqa: BLE001 — a probe fault is reported, never faked
        reason = f"{type(exc).__name__}: {exc}"
        return {
            "schema": VOICE_PROBE_FEED_SCHEMA,
            "sourced": False,
            "reason": reason,
            "engine": {"name": "unknown", "mock": True, "real_available": False, "probing": False,
                       "nemo_state": "unavailable", "probe": None, "real_engine": None,
                       "detection": {}, "reason": reason},
            "blocking": bool(blocking),
            "forced": bool(force),
            "tts": False,
        }


def unavailable_feed(reason: str, *, audio_ref: str | None = None) -> dict[str, Any]:
    """The fail-closed feed: a fault means the utterance could not be routed. NEVER a fabricated
    "delivered" (invariant 3 / invariant 20 spirit) — the shell renders an honest "voice unavailable"
    with a CLARIFY (repeat) badge and a VISIBLE mock engine (never a claimed real engine)."""
    return {
        "schema": CONDUCTOR_VOICE_FEED_SCHEMA,
        "sourced": False,
        "reason": reason,
        "engine": {"name": "unknown", "mock": True, "real_available": False, "probing": False,
                   "nemo_state": "unavailable", "probe": None, "real_engine": None,
                   "detection": {}, "reason": "engine unavailable (fail-closed)"},
        "outcome": {"kind": ConductorInputKind.CLARIFY.value, "source": None, "text": "",
                    "confidence": None, "reason": reason, "queue_item_id": None},
        "delivered": False,
        "delivered_text": None,
        "queued": False,
        "needs_clarification": True,
        "deliveries": [],
        "tts": False,
        "transcribe_then_discard": True,
        "audio_ref": audio_ref,
        "live_capture_owed": dict(LIVE_CAPTURE_OWED),
        "torn_down": True,
    }


def run_conductor_voice(
    audio_ref: str = DEFAULT_AUDIO_REF,
    *,
    engine: STTEngine | None = None,
    for_capture: bool = False,
    confidence_threshold: float | None = None,
    blocking: bool = True,
    force_probe: bool = False,
) -> dict[str, Any]:
    """Route ONE captured utterance through the REAL `ConductorVoiceBridge` over a REAL `CommandBroker`
    (mock-first — no live model call), then fold the outcome into `conductor_voice_feed@1.0`. Wrapped
    fail-closed: ANY fault ⇒ `unavailable_feed` (invariant 3). The bridge/adapter are always closed
    (transcribe-then-discard on close), so nothing outlives the call (D-LOOP-1 spirit).

    `for_capture=True` selects the real WSL Parakeet engine when available (a REAL WAV `audio_ref`); the
    default (`False`, the headless indicator poll with a scripted stand-in) stays on the visible mock —
    see `select_engine`."""
    try:
        eng, engine_info = select_engine(engine, for_capture=for_capture, blocking=blocking,
                                         force_probe=force_probe)
        sink = _RecordingSink()
        broker = CommandBroker()
        queue = ApprovalQueue()
        mirror = functools.partial(_mirror, queue)
        kwargs: dict[str, Any] = {}
        if confidence_threshold is not None:
            kwargs["confidence_threshold"] = confidence_threshold
        bridge = ConductorVoiceBridge(chat_sink=sink, broker=broker, engine=eng, mirror=mirror, **kwargs)
        try:
            outcome = bridge.speak(audio_ref)
            usage = bridge.get_usage()
        finally:
            bridge.close()  # discard any retained audio; STT-only, no synthesis
        return fold_conductor_voice_feed(outcome, engine_info=engine_info, usage=usage,
                                         deliveries=sink.delivered, audio_ref=audio_ref,
                                         real_capture=for_capture)
    except Exception as exc:  # noqa: BLE001 — a fault is reported as unavailable, never faked
        return unavailable_feed(f"{type(exc).__name__}: {exc}", audio_ref=audio_ref)
