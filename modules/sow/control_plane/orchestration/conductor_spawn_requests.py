"""A model asked for a terminal. The operator decides. EPC-03 L6-1/L6-3.

The operator's ask was *"I should be able to tell the conductor to open up two more terminals, and
then it automatically open them up"*, and the directive's D-3 answers the obvious question about
it: a model-triggered spawn goes through the EXISTING chain only. It never gets a private route.

WHY THERE IS ALMOST NO NEW MACHINERY HERE. `spawn` is ALREADY a protected verb -
`voice_bridge/command_broker.py:27` lists it beside `grant`, `promote` and `elevate` - and the
CommandBroker already refuses to auto-execute a protected verb from any source, voice included.
The approval drawer already has an `ApprovalKind.PROTECTED_ACTION` row for exactly this, and
`apply_protected_decision` already routes the operator's answer back to the broker.

So a conductor asking to open a terminal is given precisely the treatment the OPERATOR's own
spoken "spawn a worker" is given: queued, visible, never executed on the asker's say-so. Building
a separate approval path for model-initiated spawns would have been a second implementation of a
decision the broker already makes, and the two would eventually disagree about what "spawn" means.

WHY `confidence=1.0`. The broker's confidence gate exists for SPEECH: a transcript that might be
a misheard word must not execute. A tool call carries no transcription uncertainty - the arguments
arrive structured, and the model either emitted `open_worker_pane` or it did not. Certainty about
WHAT WAS ASKED is not certainty that it should happen, and nothing here grants the second: a
protected verb at confidence 1.0 still lands in the operator's queue, because the gate that stops
it is the protected-verb gate and not the confidence one.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from control_plane.orchestration.operator_surface import ApprovalQueue, mirror_broker_outcome
from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

#: The surface a conductor's request arrives on. Distinct from `voice` and `typed` so a drawer row
#: can say WHO asked - an operator reading "spawn llama3.2:3b" needs to know whether he asked for
#: it or a model did, and that is the whole difference between the two rows.
CONDUCTOR_SOURCE = "conductor"

SPAWN_VERB = "spawn"


def _request_fields(request: Any) -> tuple[str, str, bool, str | None]:
    if isinstance(request, Mapping):
        return (str(request.get("model") or ""), str(request.get("reason") or ""),
                request.get("admissible") is not False,
                request.get("refusal") if request.get("refusal") else None)
    return (str(getattr(request, "model", "") or ""),
            str(getattr(request, "reason", "") or ""),
            getattr(request, "admissible", True) is not False,
            getattr(request, "refusal", None))


def queue_spawn_requests(
    requests: Iterable[Any],
    *,
    queue: ApprovalQueue | None = None,
    broker: CommandBroker | None = None,
    objective: str = "",
    conductor_model: str = "",
    extra_detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Put a conductor's spawn requests in front of the operator. Spawns nothing.

    Returns `{queued, refused, items, note}`. `queued` rows are waiting for the operator; `refused`
    rows never reached the broker because this build already knows they cannot be honoured (an
    uninstalled model, a duplicate, the measured pane bound). A refusal is REPORTED rather than
    dropped: a conductor whose request vanished silently will ask again every turn, and an operator
    who never sees the ask cannot tell a bounded system from a broken one.
    """
    queue = queue if queue is not None else ApprovalQueue()
    broker = broker if broker is not None else CommandBroker()
    queued: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []

    for request in requests or ():
        model, reason, admissible, refusal = _request_fields(request)
        if not admissible or not model:
            refused.append({"model": model, "reason": reason,
                            "refusal": refusal or "the request named no model",
                            "reached_broker": False})
            continue
        command = ProposedCommand(
            source=CONDUCTOR_SOURCE, verb=SPAWN_VERB, target=model,
            args={"reason": reason, "objective": objective,
                  "requested_by": conductor_model or "local conductor"},
            raw_text=f"open a worker pane running {model}: {reason}".strip(),
            # See the module docstring: certainty about what was ASKED, never about whether it
            # should happen. The protected-verb gate is what stops it, and it still does.
            confidence=1.0)
        outcome = broker.submit(command)
        if outcome.disposition is Disposition.APPROVAL_QUEUED:
            item_id = mirror_broker_outcome(
                queue, outcome, command,
                extra_detail={**dict(extra_detail or {}),
                              "requested_by": conductor_model or "local conductor",
                              "objective": objective,
                              "model_initiated": True})
            queued.append({"model": model, "reason": reason, "item_id": item_id,
                           "pending_id": outcome.pending_id})
        else:
            # The broker declined to queue it at all. Recorded with the broker's own words: this
            # is the one place where something other than the operator refused, and attributing it
            # to the operator would be a lie about who said no.
            item_id = mirror_broker_outcome(queue, outcome, command,
                                            extra_detail=dict(extra_detail or {}))
            refused.append({"model": model, "reason": reason,
                            "refusal": outcome.reason, "reached_broker": True,
                            "disposition": outcome.disposition.value, "item_id": item_id})

    return {
        "queued": queued,
        "refused": refused,
        "queued_count": len(queued),
        "refused_count": len(refused),
        "items": [row["item_id"] for row in queued],
        "note": (
            "A conductor may ASK for a terminal. Nothing here opens one: every request is a "
            "protected action in the operator's drawer, and an approved one is then spawned by the "
            "existing emit_worker_launch chain with every gate intact (D-3). A gate that refuses "
            "the operator refuses the conductor."),
    }
