"""The conductor asks for another terminal. EPC-03 Layer 6.

The operator's ask, in his words:

    "I should be able to tell the conductor to open up two more terminals, and then it
     automatically open them up... it's gotta be able to communicate with those extra workers."

THE SHAPE THIS TAKES, AND WHY. A model does not spawn anything here. It emits a REQUEST, and the
request goes through the SAME `emit_worker_launch` chain the operator's own click goes through -
every gate, the residency fence, the node record (directive D-3). The conductor never gets a
private spawn route, because a second path to the same capability is how one of them ends up
missing a gate the other has, and the gate that goes missing is discovered by an incident.

So this module produces `SpawnRequest` objects and nothing else. It cannot open a terminal. The
type it returns is the whole of its authority.

MEASURED, on this host, 2026-08-31, before any of it was written - because "the model can call a
tool" is a claim about a specific model and this build has been burned by assuming model
behaviour. `qwen3:8b` (D-2's conductor) against `/api/chat` with one tool declared:

  * an objective needing three parallel reviewers -> `done_reason=length`, ONE tool call:
    `open_worker_pane({"model": "llama3.2:3b", "reason": "Reviewing the auth module"})`
  * an objective needing none, with three panes already idle -> `done_reason=stop`, NO tool call,
    and the content said why: *"No additional workers are required for this task."*

Both directions, which is the part that matters: a model that always calls the tool is not
deciding anything. The `length` finish on the first leg is recorded rather than tidied away - the
thinking tokens consumed the budget before it could request the second and third worker, which is
why `TOOL_TURN_MAX_TOKENS` below is larger than the decomposition budget and why a truncated turn
is reported as truncated instead of read as "it only wanted one".
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

OLLAMA_HOST = "http://127.0.0.1:11434"

#: Bigger than `LOCAL_CONDUCTOR_MAX_TOKENS`, and the measurement above is the reason: a thinking
#: model spends tokens reasoning before it emits its first tool call, and a budget sized for the
#: answer alone truncates the request list. Still bounded - an unbounded turn is how a conductor
#: spends a minute deciding to open one terminal.
TOOL_TURN_MAX_TOKENS = 1_024

SPAWN_TOOL_NAME = "open_worker_pane"

#: The tool as the model sees it. Deliberately narrow: a model may ask for A worker running A
#: model, and may not choose the role, the permission profile, the workspace, or anything else the
#: spawn chain governs. Widening this schema is how a model would acquire authority by parameter.
SPAWN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SPAWN_TOOL_NAME,
        "description": (
            "Request an additional Sovereign worker terminal running a local model. "
            "The request is subject to the operator's gates and may be refused. "
            "Only ask when the objective needs more parallel workers than are already up."),
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string",
                          "description": "The local model tag for the new worker."},
                "reason": {"type": "string",
                           "description": "Why another worker is needed for this objective."},
            },
            "required": ["model", "reason"],
        },
    },
}


@dataclass(frozen=True)
class SpawnRequest:
    """One request for one terminal. Carries no authority; it is an ASK.

    `admissible` is False when the request failed a check this module can make on its own - an
    unknown model tag, a duplicate. That is NOT the gate decision: `emit_worker_launch` decides,
    and a request marked admissible here can still be refused there. Refusing early only avoids
    sending the spawn chain a request that cannot possibly succeed.
    """

    model: str
    reason: str
    admissible: bool = True
    refusal: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"model": self.model, "reason": self.reason,
                "admissible": self.admissible, "refusal": self.refusal}


@dataclass(frozen=True)
class ToolTurn:
    """What one conductor tool turn produced. Everything the operator needs to see it happen."""

    requests: list[SpawnRequest] = field(default_factory=list)
    content: str = ""
    truncated: bool = False
    model_reported: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requests": [r.as_dict() for r in self.requests],
            "content": self.content,
            "truncated": self.truncated,
            "model_reported": self.model_reported,
            "error": self.error,
        }


def _system_prompt(live_panes: Sequence[str], installed: Sequence[str],
                   max_panes: int, bound_reason: str) -> str:
    """What the conductor is told about its own situation.

    The pane bound is stated to the MODEL as well as enforced below it. Enforcing silently would
    produce a conductor that keeps asking for terminals it can never have, and a refusal it cannot
    learn from is a refusal it will repeat every turn.
    """
    return "\n".join([
        "You are the Sovereign conductor.",
        f"Worker panes currently up: {', '.join(live_panes) if live_panes else 'none'}.",
        f"Local models installed on this host: {', '.join(installed) if installed else 'none'}.",
        f"This host can hold at most {max_panes} worker pane(s) at once ({bound_reason}).",
        f"You may request another worker with the {SPAWN_TOOL_NAME} tool. The request goes to the "
        "operator's gates and may be refused. Ask only when the objective needs more parallel "
        "workers than are already up.",
    ])


def _parse_tool_calls(message: Mapping[str, Any], installed: Sequence[str],
                      already: Sequence[str]) -> list[SpawnRequest]:
    """Turn the model's tool calls into requests, refusing what cannot be honoured.

    A model naming a model tag that is not installed is a common and harmless mistake - it is
    working from the list in its prompt and can transpose it. It is refused with the reason rather
    than passed to a spawn chain that would fetch a multi-gigabyte model mid-dispatch.
    """
    requests: list[SpawnRequest] = []
    known = {str(m) for m in installed}
    seen = {str(p) for p in already}
    for call in (message.get("tool_calls") or []):
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping) or function.get("name") != SPAWN_TOOL_NAME:
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, Mapping):
            arguments = {}
        model = str(arguments.get("model") or "").strip()
        reason = str(arguments.get("reason") or "").strip()
        if not model:
            requests.append(SpawnRequest("", reason, admissible=False,
                                         refusal="the request named no model"))
            continue
        if known and model not in known:
            requests.append(SpawnRequest(
                model, reason, admissible=False,
                refusal=f"{model!r} is not installed on this host; a spawn would have to fetch it "
                        f"mid-dispatch"))
            continue
        if model in seen:
            requests.append(SpawnRequest(
                model, reason, admissible=False,
                refusal=f"a worker on {model!r} was already requested in this turn"))
            continue
        seen.add(model)
        requests.append(SpawnRequest(model, reason))
    return requests


def request_worker_panes(
    *,
    objective: str,
    live_panes: Sequence[str],
    installed_models: Sequence[str],
    max_panes: int,
    bound_reason: str = "measured from this host's VRAM",
    model: str = "qwen3:8b",
    host: str = OLLAMA_HOST,
    transport: Any = None,
) -> ToolTurn:
    """Ask the local conductor whether it wants more workers. Returns REQUESTS, never terminals.

    `transport` is injected by tests and takes the request payload, returning the daemon's decoded
    response. The default posts to the loopback daemon. Never raises: a conductor turn that cannot
    reach its model produces a turn with an error, not an exception that takes the dispatch.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(live_panes, installed_models,
                                                         max_panes, bound_reason)},
            {"role": "user", "content": f"Objective: {objective}\nDo what is needed."},
        ],
        "tools": [SPAWN_TOOL],
        "stream": False,
        "options": {"num_predict": TOOL_TURN_MAX_TOKENS, "temperature": 0.0},
    }
    try:
        if transport is not None:
            data = transport(payload)
        else:
            request = urllib.request.Request(
                f"{host}/api/chat", data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return ToolTurn(error=f"{type(exc).__name__}: {exc}")
    if not isinstance(data, Mapping):
        return ToolTurn(error="the conductor daemon returned a non-object response")

    message = data.get("message") if isinstance(data.get("message"), Mapping) else {}
    requests = _parse_tool_calls(message, installed_models, ())
    reported = data.get("model")

    # A turn that ran out of tokens mid-request-list asked for FEWER workers than it wanted, and
    # reporting that as its considered answer is how a truncation becomes a decision. Measured:
    # the first live probe of this path finished on `length` with one of three workers requested.
    truncated = data.get("done_reason") == "length"

    # The bound, enforced. The model was told it in the system prompt above; being told is not
    # being stopped, and a model is not a gate.
    room = max(0, int(max_panes) - len(live_panes))
    if len(requests) > room:
        kept = requests[:room]
        for extra in requests[room:]:
            kept.append(SpawnRequest(
                extra.model, extra.reason, admissible=False,
                refusal=(f"this host holds at most {max_panes} worker pane(s) "
                         f"({bound_reason}) and {len(live_panes)} are already up")))
        requests = kept

    return ToolTurn(
        requests=requests,
        content=str(message.get("content") or ""),
        truncated=truncated,
        model_reported=reported if isinstance(reported, str) and reported.strip() else None,
    )
