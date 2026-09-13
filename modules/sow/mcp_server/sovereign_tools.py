"""Standard stdio MCP adapter for live Sovereign conductor and worker nodes.

The Electron supervisor issues one opaque loopback capability per admitted node.  This
process resolves that capability to the real node identity, exposes the application tools,
and stores collaboration state in the existing Sovereign SQLite/CAS substrate.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
from collections import deque
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

# F-016. This client only ever talks to a loopback app-control server (and carries a bearer
# token). A configured environment/registry proxy does NOT bypass dotted loopback, so a default
# urlopen would route the request -- and the token -- through the proxy. This opener has an empty
# ProxyHandler, forcing a direct connection.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _resolve_store_root() -> Path:
    """F-131. The governed node store root. Honour the shell-declared SOVEREIGN_STORE_ROOT; else
    the state root's store; else a per-user location -- never a CWD-relative `.sovereign_store`,
    which put durable records wherever the process happened to be launched from."""
    declared = (os.environ.get("SOVEREIGN_STORE_ROOT") or "").strip()
    if declared:
        return Path(declared).resolve()
    state = (os.environ.get("SOVEREIGN_WORKSPACE_STATE") or "").strip()
    if state:
        return (Path(state) / "store").resolve()
    local = (os.environ.get("LOCALAPPDATA") or "").strip() or str(
        Path.home() / "AppData" / "Local")
    return (Path(local) / "SovereignWorkspace" / "sow" / "store").resolve()

from control_plane.policy import Identity, SovereignPolicy, Verdict
from mcp_server.collaboration_service import CollaborationService
from mcp_server.memory_service import MemoryService
from persistence import ContentAddressedStore, SovereignStore


PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "sovereign"
INSTRUCTIONS = (
    "Sovereign is the authoritative application-control and node-collaboration server. "
    "Worker creation, termination, task assignment, status, node messages, artifacts, and debates "
    "must use these tools. Never launch provider workers with shell commands or external terminals. "
    "Wait for spawn_worker to report ready before claiming a worker exists. Workers should publish "
    "progress and candidate results through these tools, not only terminal output."
)


# --- W-34: three ceilings on surfaces a MODEL drives ---------------------------------------------
# None of these is authorization (invariant 7): they bound a surface this process already serves.
# They are not interchangeable, which is why there are three rather than one.
#
# The stdio frame is the only PRE-AUTH one — the read loop buffers before anything is parsed. The
# donor is the sibling transport at `mcp_server/server.py:86`, which already bounds its pre-auth
# buffering at 8 MiB and answers "request too large" (spec-audit F6). Same number, deliberately: two
# transports into the same server that disagree about how much they will hold is a difference a
# caller would have to discover by hitting it.
MAX_STDIO_LINE_BYTES = 8 * 1024 * 1024

# The artifact ceiling is DELIBERATELY below the frame ceiling. An artifact travels inside a frame
# as a JSON string, so a limit at or above `MAX_STDIO_LINE_BYTES` would be unreachable — the frame
# bound would always refuse first, and the artifact rule would be a constant nobody could trip. The
# gap also leaves room for the envelope and for JSON escaping, which can multiply a byte into six.
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024

# Neither size bound stops a node that LOOPS: each call is small. Measured on this host before the
# repair, 2000 consecutive `get_worker_status` calls completed in 0.01 s and none was refused.
RATE_LIMIT_WINDOW_S = 10.0
MAX_CALLS_PER_WINDOW = 240


class ToolError(RuntimeError):
    pass


class AppControlClient:
    def __init__(self, port: int, token: str, *, timeout: float = 180.0) -> None:
        if port <= 0 or not token:
            raise ToolError("Sovereign app-control capability is unavailable")
        self._base = f"http://127.0.0.1:{port}/v1"
        self._token = token
        self._timeout = timeout

    def call(self, operation: str, arguments: dict[str, Any] | None = None, *,
             timeout: float | None = None) -> Any:
        # W-62 / U434: `timeout` lets a caller bound ONE call below the client's 180 s ceiling.
        # The only caller that does is the node heartbeat: a liveness probe that could itself block
        # for the full ceiling would defeat the bounded liveness it exists to provide.
        body = json.dumps({"operation": operation, "arguments": arguments or {}}).encode("utf-8")
        req = urllib.request.Request(
            self._base + "/tools/call", data=body, method="POST",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            with _NO_PROXY_OPENER.open(req, timeout=self._timeout if timeout is None else timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ToolError(f"Sovereign app-control channel failed: {exc}") from exc
        if not payload.get("ok"):
            raise ToolError(str(payload.get("error") or "application operation failed"))
        return payload.get("result")

    def identity(self) -> Identity:
        result = self.identity_details()
        try:
            return Identity(result["node_id"], result["role"], result["project_id"])
        except (KeyError, TypeError) as exc:
            raise ToolError("application returned a malformed node identity") from exc

    def identity_details(self) -> dict[str, Any]:
        result = self.call("identity")
        if not isinstance(result, dict):
            raise ToolError("application returned a malformed node identity")
        return result


# W-62 / U434: the node heartbeat — bounded authoritative liveness.
#
# The gateway's liveness model (`apps/desktop/control/sovereign-control-server.js`) stamps
# `_lastSeen` when a request ARRIVES, and reads it back as `connected` only inside a 180 s window
# (`DEFAULT_STALE_AFTER_MS`); past it the node is `stale`, which means UNVERIFIED. Before this
# class existed there was no server->node ping and no node heartbeat, so two true things about a
# node could never be told apart from silence: an idle-but-healthy worker (the conductor decomposes
# for minutes before assigning) and a node doing store-only MCP work — `read_messages`,
# `close_debate`, `publish_synthesis`, artifact reads — which is WORKING and yet never reaches the
# gateway, so it goes stale while working. U434 named the closure: "A heartbeat the node makes on a
# cadence shorter than the staleness window closes both." This is it.
#
# THE OPERATION, and why it is `identity`: the gateway stamps `_lastSeen` for ANY authenticated
# request before it dispatches, and `identity` is the one operation that answers without a handler
# and WITHOUT an `_recordOperation` entry — a liveness beat is not work, so it must not appear in
# the node's operation history. No new gateway operation exists for this on purpose: the protocol
# addition is the node's cadence, not a second surface to govern.
#
# BOUNDED, three ways: the beat's HTTP call carries its own short timeout (never the client's
# 180 s ceiling — a liveness probe that could block for the ceiling defeats itself); the loop waits
# on a stop EVENT, so `stop()` ends it at once, with a join budget it reports rather than exceeds;
# and the thread is a daemon, so a heartbeat can never hold the process open at shutdown.
#
# NOT AUTHORIZATION: a beat proves the node can reach the gateway with its own credential, nothing
# about what it may do there (invariant 7). A failed beat is swallowed and returns False — a
# heartbeat that could break a tool call, or crash the node, would be worse than the silence it
# exists to remove; the next beat retries, and a node whose beats keep failing goes stale, which is
# the gateway's honest word for it.
DEFAULT_HEARTBEAT_INTERVAL_S = 60.0   # comfortably inside the gateway's 180 s window, and a missed
                                      # beat still leaves the next one inside it (2 x 60 < 180)
DEFAULT_HEARTBEAT_TIMEOUT_S = 5.0


class NodeHeartbeat:
    """U434: keep an established node verifiably alive across idleness and store-only work."""

    def __init__(self, app: AppControlClient, *, interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
                 call_timeout_s: float = DEFAULT_HEARTBEAT_TIMEOUT_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if interval_s <= 0:
            raise ToolError("heartbeat interval must be positive")
        self._app = app
        self._interval_s = interval_s
        self._call_timeout_s = call_timeout_s
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_beat_at: float | None = None
        self.beats = 0                    # successful liveness calls (tests read it; it is cheap)

    def beat(self) -> bool:
        """One liveness call. Returns True only if the gateway answered THIS beat."""
        try:
            self._app.call("identity", timeout=self._call_timeout_s)
        except Exception:
            return False
        self._last_beat_at = self._clock()
        self.beats += 1
        return True

    def maybe_beat(self, now: float | None = None) -> bool:
        """Beat only when the interval has elapsed — the cadence, separate from the waiting. Tests
        drive this with a stated clock; the loop below drives it with the real one."""
        now = self._clock() if now is None else now
        if self._last_beat_at is not None and now - self._last_beat_at < self._interval_s:
            return False
        return self.beat()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return                        # idempotent: a second start is not a second heartbeat
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sovereign-node-heartbeat",
                                        daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.beat()
            self._stop.wait(self._interval_s)

    def stop(self, timeout_s: float = 2.0) -> bool:
        """Stop inside a stated budget; report whether the thread is gone. Never raises."""
        self._stop.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout_s)
        return not thread.is_alive()


class SovereignToolRuntime:
    def __init__(self, app: AppControlClient, store_root: Path, *,
                 policy: SovereignPolicy) -> None:
        # `policy` is a REQUIRED keyword, not a manufactured default (the U292(a) closure): the
        # authority is supplied by the caller, so it can be replaced with one that disagrees and
        # the delegation is falsifiable behaviourally rather than by reading the source.
        self.app = app
        self.identity_details = app.identity_details()
        self.identity = Identity(self.identity_details["node_id"], self.identity_details["role"],
                                 self.identity_details["project_id"])
        self.store = SovereignStore(store_root / "sovereign.db")
        self.cas = ContentAddressedStore(store_root / "cas")
        self.policy = policy
        self.memory = MemoryService(self.store, self.cas, self.policy)
        self.collaboration = CollaborationService(self.store, self.policy)
        # W-34 rate limiter state. One runtime serves ONE node, so "per-node" is per-instance.
        # `_clock` is an attribute rather than a direct `monotonic()` call so a test can state the
        # window property instead of sleeping through it — a test that sleeps to observe a rolling
        # window is a slow test that still only samples one point.
        self._clock = time.monotonic
        self._call_times: deque[float] = deque()
        # W-62 / U434: absent until started. `_DeferredRuntime._build` starts it in production (a
        # node whose capability resolved is an ESTABLISHED node, the only kind a heartbeat serves);
        # tests construct runtimes directly and opt in explicitly, so unrelated suites grow no
        # threads they did not ask for.
        self.heartbeat: NodeHeartbeat | None = None

    def start_heartbeat(self, **kwargs: Any) -> NodeHeartbeat:
        """W-62: begin the liveness cadence. Idempotent — a runtime heartbeats once or not at all.
        kwargs reach `NodeHeartbeat` (interval_s, call_timeout_s, clock) so a test can state a
        cadence instead of sleeping through the production one."""
        if self.heartbeat is None:
            self.heartbeat = NodeHeartbeat(self.app, **kwargs)
        self.heartbeat.start()
        return self.heartbeat

    def close(self) -> None:
        # W-62: the heartbeat goes FIRST: it calls the gateway, and nothing else in `close` should
        # race a beat in flight while the store shuts underneath the runtime. Its stop is bounded
        # and reports rather than raises; a beat that outlived the join dies with the daemon thread.
        if self.heartbeat is not None:
            self.heartbeat.stop()
        self.store.close()

    def call(self, name: str, args: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "list_models": lambda a: self.app.call("list_models", a),
            "spawn_worker": lambda a: self.app.call("spawn_worker", a),
            "stop_worker": lambda a: self.app.call("stop_worker", a),
            "get_worker_status": lambda a: self._worker_status(a),
            "assign_task": self._assign_task,
            "send_message": self._send_message,
            "read_messages": self._read_messages,
            "publish_progress": self._publish_progress,
            "open_debate": self._open_debate,
            "post_debate_turn": self._post_debate_turn,
            "close_debate": self._close_debate,
            "abort_debate": self._abort_debate,
            "publish_artifact": self._publish_artifact,
            "read_artifact": self._read_artifact,
            "publish_candidate": self._publish_candidate,
            "publish_synthesis": self._publish_synthesis,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"unknown Sovereign tool {name!r}")
        if not isinstance(args, dict):
            raise ToolError("tool arguments must be an object")
        # W-34: the rate ceiling is checked FIRST, before shape validation and before dispatch. A
        # node looping on malformed calls is still a node looping, and a limiter that only counted
        # well-formed work would not bound it.
        self._enforce_rate_limit()
        # W-33: BEFORE dispatch, deliberately. A handler that receives unvalidated arguments defends
        # itself with `args.get(name, default)`, and the default is the dangerous half — see
        # `validate_tool_arguments`.
        validate_tool_arguments(name, args)
        return handler(args)

    def _enforce_rate_limit(self) -> None:
        """W-34: bound the CALL RATE for this node. Raises ToolError naming the ceiling.

        A rolling window rather than a fixed bucket, so a caller cannot burst the full allowance at
        the end of one bucket and again at the start of the next.
        """
        now = self._clock()
        cutoff = now - RATE_LIMIT_WINDOW_S
        while self._call_times and self._call_times[0] <= cutoff:
            self._call_times.popleft()
        if len(self._call_times) >= MAX_CALLS_PER_WINDOW:
            raise ToolError(
                f"rate limit: this node has made {len(self._call_times)} tool calls in the last "
                f"{RATE_LIMIT_WINDOW_S:g}s and the ceiling is {MAX_CALLS_PER_WINDOW} — retry after "
                "the window rolls")
        self._call_times.append(now)

    def _worker_status(self, args: dict[str, Any]) -> dict[str, Any]:
        live = self.app.call("get_worker_status", args)
        return {"nodes": live, "tasks": self.collaboration.list_tasks(self.identity)}

    def _assign_task(self, args: dict[str, Any]) -> dict[str, Any]:
        # Refuse stale/missing owners before appending a task. The application repeats this check
        # immediately before delivery, closing both U436 costs: no routine BLOCKED row and no first
        # owner half-delivered when a later owner is unavailable.
        self.app.call("preflight_assignment", {
            "worker_node_ids": args.get("worker_node_ids", []),
        })
        task = self.collaboration.create_task(
            self.identity, objective=args.get("objective", ""),
            owner_node_ids=args.get("worker_node_ids", []), scope=args.get("scope"),
            constraints=args.get("constraints"), expected_output=args.get("expected_output"),
            acceptance_criteria=args.get("acceptance_criteria"), peer_nodes=args.get("peer_nodes"),
        )
        try:
            delivery = self.app.call("assign_task", {"task": task})
        except Exception as exc:
            task = self.collaboration.update_task(
                self.identity, task_id=task["task_id"], status="BLOCKED",
                progress={"blockers": [str(exc)], "what_remains": "deliver assignment to live pane"},
            )
            raise ToolError(f"task persisted but pane delivery failed: {exc}") from exc
        return {"task": task, "delivery": delivery}

    def _send_message(self, args: dict[str, Any]) -> dict[str, Any]:
        message = self.collaboration.send_message(
            self.identity, task_id=args.get("task_id", ""), thread_id=args.get("thread_id"),
            recipient_node_ids=args.get("recipient_node_ids", []),
            message_kind=args.get("message_kind", "question"), body=args.get("body", ""),
            evidence_refs=args.get("evidence_refs"), artifact_refs=args.get("artifact_refs"),
            reply_to=args.get("reply_to"),
        )
        notification = self.app.call("notify_message", {"message": message})
        return {"message": message, "notification": notification}

    def _read_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        messages = self.collaboration.read_messages(
            self.identity, task_id=args.get("task_id", ""),
            include_all=bool(args.get("include_all", False)),
        )
        return {"messages": messages, "count": len(messages)}

    def _publish_progress(self, args: dict[str, Any]) -> dict[str, Any]:
        status = args.get("status", "IN_PROGRESS")
        progress = {
            "completed": args.get("completed", ""), "working_on": args.get("working_on", ""),
            "what_remains": args.get("what_remains", ""), "blockers": args.get("blockers", []),
            "questions": args.get("questions", []), "evidence_refs": args.get("evidence_refs", []),
            "artifact_refs": args.get("artifact_refs", []), "estimated_next_action": args.get("estimated_next_action", ""),
        }
        task = self.collaboration.update_task(
            self.identity, task_id=args.get("task_id", ""), status=status, progress=progress,
        )
        kind = "blocker" if status == "BLOCKED" else "completion" if status in ("CANDIDATE_READY", "COMPLETED") else "progress"
        body = args.get("body") or progress["completed"] or progress["working_on"] or status
        recipients = args.get("recipient_node_ids") or [task["created_by_node_id"]]
        message = self.collaboration.send_message(
            self.identity, task_id=task["task_id"], thread_id=task["thread_id"],
            recipient_node_ids=recipients, message_kind=kind, body=body,
            evidence_refs=progress["evidence_refs"], artifact_refs=progress["artifact_refs"],
        )
        self.app.call("notify_message", {"message": message, "task": task})
        return {"task": task, "message": message}

    def _open_debate(self, args: dict[str, Any]) -> dict[str, Any]:
        debate = self.collaboration.open_debate(
            self.identity, task_id=args.get("task_id", ""), proposition=args.get("proposition", ""),
            participant_node_ids=args.get("participant_node_ids", []),
            evidence_refs=args.get("evidence_refs"), artifact_refs=args.get("artifact_refs"),
            max_rounds=args.get("max_rounds", 2), budget_units=args.get("budget_units", 1000),
        )
        self.app.call("notify_debate", {"debate": debate})
        return debate

    def _post_debate_turn(self, args: dict[str, Any]) -> dict[str, Any]:
        debate = self.collaboration.get_debate(self.identity, args.get("debate_id", ""))
        turn = self.collaboration.post_debate_turn(
            self.identity, debate_id=args.get("debate_id", ""), body=args.get("body", ""),
            evidence_refs=args.get("evidence_refs"), reply_to=args.get("reply_to"),
        )
        self.app.call("notify_debate_turn", {"debate_id": args.get("debate_id"), "turn": turn,
                      "participant_node_ids": debate["participant_node_ids"]})
        return turn

    def _abort_debate(self, args: dict[str, Any]) -> dict[str, Any]:
        """U416: the terminal state for a debate whose participant can no longer answer. Reachable
        as a tool because the node that notices a dead peer is a live node, not a test."""
        return self.collaboration.abort_debate(
            self.identity, debate_id=args.get("debate_id", ""), reason=args.get("reason", ""))

    def _close_debate(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.collaboration.close_debate(
            self.identity, debate_id=args.get("debate_id", ""), decision=args.get("decision", ""),
            agreements=args.get("agreements"), dissent=args.get("dissent"),
            disagreements=args.get("disagreements"),
            unresolved_points=args.get("unresolved_points"),
            closure_reason=args.get("closure_reason"),
        )

    def _authorize(self, verdict: Verdict) -> None:
        """U326: the tool layer asks `control_plane.policy` too. It used to carry its own copies
        of the candidate/synthesis role rules — a third place authority could drift to."""
        if not verdict.allow:
            raise ToolError(verdict.reason)

    def _publish_candidate(self, args: dict[str, Any]) -> dict[str, Any]:
        # ask the authority BEFORE writing the candidate artifact into CAS, using the real rule
        # (assigned worker), not a coarse approximation of it
        self._authorize(self.policy.authorize_publish_candidate(
            self.identity, self.collaboration.get_task(self.identity, args.get("task_id", ""))))
        provider = str(self.identity_details.get("provider_id") or "")
        model = str(self.identity_details.get("model_id") or "")
        if args.get("provider") and args["provider"] != provider:
            raise ToolError("candidate provider does not match authenticated node identity")
        if args.get("model") and args["model"] != model:
            raise ToolError("candidate model does not match authenticated node identity")
        task_id = args.get("task_id", "")
        candidate = {
            "task_id": task_id, "worker_node_id": self.identity.node_id,
            "provider": provider, "model": model, "summary": args.get("summary", "").strip(),
            "claims": _nonempty_strings(args.get("claims"), "claims"),
            "evidence_refs": _nonempty_strings(args.get("evidence_refs"), "evidence_refs"),
            "peer_messages_considered": _string_list(args.get("peer_messages_considered"),
                                                        "peer_messages_considered"),
            "debates_considered": _string_list(args.get("debates_considered"), "debates_considered"),
            "limitations": _string_list(args.get("limitations"), "limitations"),
            "status": "CANDIDATE", "published_at": _iso_now(),
        }
        artifact = self.memory.put_artifact(
            self.identity, content=json.dumps(candidate, sort_keys=True).encode("utf-8"),
            media_type="application/vnd.sovereign.candidate+json", task_id=task_id,
        )
        candidate["artifact_ref"] = artifact["artifact_id"]
        candidate["content_hash"] = artifact["artifact_id"]
        task = self.collaboration.record_candidate(
            self.identity, task_id=task_id, candidate=candidate)
        message = self.collaboration.send_message(
            self.identity, task_id=task_id, thread_id=task["thread_id"],
            recipient_node_ids=[task["created_by_node_id"]], message_kind="completion",
            body=f"CANDIDATE published by {self.identity.node_id}: {candidate['summary']}",
            evidence_refs=candidate["evidence_refs"], artifact_refs=[artifact["artifact_id"]],
        )
        self.app.call("notify_message", {"message": message, "task": task})
        return {"candidate": candidate, "artifact": artifact, "task": task, "message": message}

    def _publish_synthesis(self, args: dict[str, Any]) -> dict[str, Any]:
        self._authorize(self.policy.authorize_publish_synthesis(self.identity))
        task_id = args.get("task_id", "")
        task = self.collaboration.get_task(self.identity, task_id)
        debate_ids, aborted_ids = self._considered_debates(task_id, args.get("debate_ids"))
        synthesis = {
            "task_id": task_id, "conductor_node_id": self.identity.node_id,
            "provider": self.identity_details.get("provider_id"),
            "model": self.identity_details.get("model_id"),
            "operator_objective": task["objective"],
            "contributions": self._contributions(task, args.get("contributions")),
            "points_of_agreement": _string_list(args.get("points_of_agreement"), "points_of_agreement"),
            "points_of_disagreement": _string_list(args.get("points_of_disagreement"), "points_of_disagreement"),
            "debate_outcome": args.get("debate_outcome", "").strip(),
            "evidence_used": _nonempty_strings(args.get("evidence_used"), "evidence_used"),
            "limitations": _string_list(args.get("limitations"), "limitations"),
            "conductor_judgment": args.get("conductor_judgment", "").strip(),
            "recommended_next_action": args.get("recommended_next_action", "").strip(),
            "candidate_node_ids": sorted((task.get("candidates") or {}).keys()),
            "debate_ids": debate_ids, "aborted_debate_ids": aborted_ids,
            "status": "SYNTHESIS", "published_at": _iso_now(),
        }
        required_text = ("debate_outcome", "conductor_judgment", "recommended_next_action")
        if any(not synthesis[key] for key in required_text):
            raise ToolError("synthesis is missing a required narrative field")
        artifact = self.memory.put_artifact(
            self.identity, content=json.dumps(synthesis, sort_keys=True).encode("utf-8"),
            media_type="application/vnd.sovereign.synthesis+json", task_id=task_id,
        )
        synthesis["artifact_ref"] = artifact["artifact_id"]
        synthesis["content_hash"] = artifact["artifact_id"]
        task = self.collaboration.record_synthesis(
            self.identity, task_id=task_id, synthesis=synthesis,
            contribution_bindings=synthesis["contributions"])
        return {"synthesis": synthesis, "artifact": artifact, "task": task,
                "operator_instruction": "Present this synthesis in the conductor pane now."}

    def _contributions(self, task: dict[str, Any], raw: Any) -> list[dict[str, str]]:
        """Every worker's contribution, keyed by NODE ID and cross-checked against the task (U333).

        What this replaces: two hardcoded fields, `gemini_contribution` and `grok_contribution`,
        both required. A task worked by any other set of nodes — two Codex workers, a Claude worker
        beside a local Ollama one, one worker, three — could not be synthesised, and the only way
        to comply was to file a node's work under a vendor name that was not its own. Work is
        dispatched by capability descriptor and reported by node identity (I-SC1); a fixed pair of
        vendor slots is neither.

        The cross-check runs in both directions, mirroring the closed-debate gate above, because
        the two-slot form could fail in neither: a contribution naming a node that published no
        candidate is refused (invented work), and a candidate node the caller left out is refused
        (dropped work). Both refusals name the node, because a conductor that must guess which one
        it got wrong will guess.

        Returned in candidate order, so the record is stable for the CAS hash regardless of the
        order the conductor listed them in.
        """
        if not isinstance(raw, list) or not raw:
            raise ToolError(
                "synthesis requires a contributions list naming every candidate node on the task")
        stated: dict[str, str] = {}
        for entry in raw:
            if not isinstance(entry, dict):
                raise ToolError("each contribution must be an object with node_id and contribution")
            node_id = entry.get("node_id")
            text = entry.get("contribution")
            if not isinstance(node_id, str) or not node_id.strip():
                raise ToolError("each contribution must name the node_id whose work it reports")
            if not isinstance(text, str) or not text.strip():
                raise ToolError(f"the contribution for {node_id.strip()} is empty")
            if node_id.strip() in stated:
                raise ToolError(f"node {node_id.strip()} is named twice in contributions")
            stated[node_id.strip()] = text.strip()
        candidate_records = task.get("candidates") or {}
        candidates = sorted(candidate_records.keys())
        unknown = sorted(n for n in stated if n not in candidates)
        if unknown:
            raise ToolError(
                "synthesis names contributions from nodes that published no candidate on this "
                f"task: {', '.join(unknown)}")
        missing = [n for n in candidates if n not in stated]
        if missing:
            raise ToolError(
                "synthesis must report a contribution for every candidate node; missing: "
                f"{', '.join(missing)}")
        return [{"node_id": n,
                 "candidate_content_hash": candidate_records[n]["content_hash"],
                 "contribution": stated[n]} for n in candidates]

    def _considered_debates(self, task_id: str, raw: Any) -> tuple[list[str], list[str]]:
        """The closed-debate gate, computed from the TASK's debates rather than from the caller's
        list (U332).

        The gate used to be `for debate_id in debate_ids: ...` — a loop over an argument, so an
        empty list satisfied it vacuously and a conductor could publish a synthesis over a debate
        that was still being argued simply by not mentioning it. Naming a CLOSED debate from a
        different task passed too, because `get_debate` is project-scoped. Four rules replace it,
        and the first is the one U332 is about:

          * no debate on this task may still be OPEN — named or not;
          * every id the caller names must belong to this task, and be CLOSED;
          * every CLOSED debate on this task must be named — omission was the bypass;
          * ABORTED debates (U416) are reported separately, from the store, so a deliberation that
            never concluded cannot be presented as one that did, and cannot block the task forever.

        `_nonempty_strings` therefore applies exactly when there is something to skip. A task that
        never needed a debate stays synthesisable; nothing is being waived, because the
        cross-check — not the list's length — is what closes the hole.

        One coupling, recorded rather than hidden (U411): the debates are read through
        `list_debates`, which filters by `authorize_debate_read`. That is correct — the tool layer
        must not read past the authority — and today it is exhaustive, because only the directing
        roles reach here and `_SCOPED_ROLES` does not contain them. If debate-read scoping ever
        narrows for a directing role, an unreadable debate becomes an invisible one, and this gate
        weakens silently.
        """
        known = {d["debate_id"]: d for d in self.collaboration.list_debates(self.identity, task_id)}
        still_open = sorted(d for d, rec in known.items() if rec.get("state") == "OPEN")
        if still_open:
            raise ToolError("synthesis requires every debate on this task to be concluded; "
                            "still open: " + ", ".join(still_open))
        closed_ids = sorted(d for d, rec in known.items() if rec.get("state") == "CLOSED")
        aborted_ids = sorted(d for d, rec in known.items()
                             if rec.get("state") not in ("OPEN", "CLOSED"))
        debate_ids = (_nonempty_strings(raw, "debate_ids") if closed_ids
                      else _string_list(raw, "debate_ids"))
        foreign = [d for d in debate_ids if d not in known]
        if foreign:
            raise ToolError("synthesis names a debate that does not belong to this task: "
                            + ", ".join(sorted(foreign)))
        not_closed = [d for d in debate_ids if known[d].get("state") != "CLOSED"]
        if not_closed:
            raise ToolError("synthesis requires every considered debate to be closed; not closed: "
                            + ", ".join(sorted(not_closed)))
        unnamed = [d for d in closed_ids if d not in debate_ids]
        if unnamed:
            raise ToolError("synthesis must name every closed debate on this task; missing: "
                            + ", ".join(unnamed))
        return debate_ids, aborted_ids

    def _publish_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        content = args.get("content")
        if not isinstance(content, str):
            raise ToolError("artifact content must be text")
        # W-34: measured on the ENCODED bytes, not on `len(content)`. The stored object is UTF-8 and
        # one character can be four bytes, so a character-count ceiling would admit an object
        # several times the limit — the bound being wrong in the direction that matters. There is no
        # frame to discard here either: an artifact is persisted into CAS and addressed by the hash
        # of its content, so an oversized one is a durable object nobody chose to keep.
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise ToolError(
                f"artifact too large: {len(encoded)} bytes exceeds the {MAX_ARTIFACT_BYTES}-byte "
                "ceiling — publish a summary and reference the source, or split it")
        return self.memory.put_artifact(
            self.identity, content=encoded,
            media_type=args.get("media_type", "text/plain; charset=utf-8"), task_id=args.get("task_id"),
        )

    def _read_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        result = self.memory.get_artifact(self.identity, args.get("artifact_id", ""))
        raw = base64.b64decode(result.pop("content_b64"))
        try:
            result["content"] = raw.decode("utf-8")
        except UnicodeDecodeError:
            result["content_b64"] = base64.b64encode(raw).decode("ascii")
        return result


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


S = {"type": "string"}
SA = {"type": "array", "items": S}
# U333: one entry per candidate node, keyed by node id. The schema a live CLI reads is where the
# vendor shape was most contagious — a required `gemini_contribution` teaches every conductor that
# contributions ARE vendors, whatever the runtime then checks.
CONTRIBUTIONS = {"type": "array", "minItems": 1, "items": {
    "type": "object",
    "properties": {"node_id": S, "contribution": S},
    "required": ["node_id", "contribution"],
}}

def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ToolError(f"{field} must be a list of non-empty strings")
    return list(dict.fromkeys(item.strip() for item in value))


def _nonempty_strings(value: Any, field: str) -> list[str]:
    result = _string_list(value, field)
    if not result:
        raise ToolError(f"{field} must not be empty")
    return result


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

TOOLS = [
    {"name": "list_models", "description": "List registered, available conductor/worker models from the live Sovereign picker.", "inputSchema": _schema({}), "annotations": {"readOnlyHint": True}},
    {"name": "spawn_worker", "description": "Create one governed provider worker inside Electron. Never use shell commands for this. provider and model_id must be the exact identifiers returned by list_models; the runtime has no hidden vendor aliases or model defaults.", "inputSchema": _schema({"provider": S, "model_id": S, "role": S}, ["provider", "model_id", "role"])},
    {"name": "stop_worker", "description": "Stop a governed worker and release its process tree and subscription lease.", "inputSchema": _schema({"node_id": S, "provider": S})},
    {"name": "assign_task", "description": "Create a scoped shared task and deliver it to live worker panes.", "inputSchema": _schema({"objective": S, "worker_node_ids": SA, "scope": {"type": "object"}, "constraints": SA, "expected_output": S, "acceptance_criteria": SA, "peer_nodes": SA}, ["objective", "worker_node_ids"])},
    {"name": "get_worker_status", "description": "Read live node/process/MCP/lease state and task progress.", "inputSchema": _schema({"node_id": S, "provider": S}), "annotations": {"readOnlyHint": True}},
    {"name": "send_message", "description": "Persist and deliver a task-scoped node-to-node message.", "inputSchema": _schema({"task_id": S, "thread_id": S, "recipient_node_ids": SA, "message_kind": {"type": "string", "enum": ["assignment", "question", "answer", "progress", "blocker", "challenge", "debate_turn", "decision", "artifact_notice", "completion"]}, "body": S, "evidence_refs": SA, "artifact_refs": SA, "reply_to": S}, ["task_id", "recipient_node_ids", "message_kind", "body"])},
    {"name": "read_messages", "description": "Read messages visible to this node within one task.", "inputSchema": _schema({"task_id": S, "include_all": {"type": "boolean"}}, ["task_id"]), "annotations": {"readOnlyHint": True}},
    {"name": "publish_progress", "description": "Update task lifecycle and publish structured progress/blocker/completion to peers.", "inputSchema": _schema({"task_id": S, "status": {"type": "string", "enum": ["ACCEPTED", "IN_PROGRESS", "WAITING_FOR_PEER", "BLOCKED", "CANDIDATE_READY", "UNDER_REVIEW", "COMPLETED", "FAILED", "CANCELLED"]}, "completed": S, "working_on": S, "what_remains": S, "blockers": SA, "questions": SA, "evidence_refs": SA, "artifact_refs": SA, "estimated_next_action": S, "body": S, "recipient_node_ids": SA}, ["task_id", "status"])},
    {"name": "open_debate", "description": "Open a persisted, bounded task debate. For live acceptance use max_rounds=2 (two turns per worker). budget_units is recorded but NOT enforced on this path (no cost governor; max_rounds is the only bound).", "inputSchema": _schema({"task_id": S, "proposition": S, "participant_node_ids": SA, "evidence_refs": SA, "artifact_refs": SA, "max_rounds": {"type": "integer", "minimum": 1, "maximum": 5}, "budget_units": {"type": "integer", "minimum": 1}}, ["task_id", "proposition", "participant_node_ids"])},
    {"name": "post_debate_turn", "description": "Post one evidence-bearing turn to an open bounded debate.", "inputSchema": _schema({"debate_id": S, "body": S, "evidence_refs": SA, "reply_to": S}, ["debate_id", "body"])},
    {"name": "close_debate", "description": "Close a debate only after every participant has posted; preserve agreements, disagreements, unresolved points, evidence, and closure reason.", "inputSchema": _schema({"debate_id": S, "decision": S, "agreements": SA, "dissent": SA, "disagreements": SA, "unresolved_points": SA, "closure_reason": S}, ["debate_id", "decision"])},
    {"name": "abort_debate", "description": "End a debate that can no longer reach a decision — a participant's pane died, or its budget is spent. Preserves the turns already posted, records no decision, and states the reason. Conductor/operator only.", "inputSchema": _schema({"debate_id": S, "reason": S}, ["debate_id", "reason"])},
    {"name": "publish_artifact", "description": "Publish a task artifact into Sovereign CAS with node provenance.", "inputSchema": _schema({"task_id": S, "content": S, "media_type": S}, ["task_id", "content"])},
    {"name": "read_artifact", "description": "Read a project-scoped artifact by reference.", "inputSchema": _schema({"artifact_id": S}, ["artifact_id"]), "annotations": {"readOnlyHint": True}},
    {"name": "publish_candidate", "description": "Publish a validated final CANDIDATE artifact. Raw terminal text or IN_PROGRESS messages do not qualify.", "inputSchema": _schema({"task_id": S, "provider": S, "model": S, "summary": S, "claims": SA, "evidence_refs": SA, "peer_messages_considered": SA, "debates_considered": SA, "limitations": SA}, ["task_id", "summary", "claims", "evidence_refs", "peer_messages_considered", "debates_considered", "limitations"])},
    {"name": "publish_synthesis", "description": "Publish the conductor synthesis only after every assigned worker candidate exists and every debate on the task has concluded, then present it visibly to the operator. contributions must carry one entry per candidate node, keyed by that node's id — not by provider or model name. debate_ids must name every CLOSED debate on the task; a debate still open blocks publication, and an aborted one is reported separately.", "inputSchema": _schema({"task_id": S, "contributions": CONTRIBUTIONS, "points_of_agreement": SA, "points_of_disagreement": SA, "debate_outcome": S, "evidence_used": SA, "limitations": SA, "conductor_judgment": S, "recommended_next_action": S, "debate_ids": SA}, ["task_id", "contributions", "points_of_agreement", "points_of_disagreement", "debate_outcome", "evidence_used", "limitations", "conductor_judgment", "recommended_next_action", "debate_ids"])},
]

# --- W-33: the declared inputSchema, enforced ---------------------------------------------------
# R-11 measured `spawn_worker {"bogus":"x","cmd":"rm -rf /"}` reaching the application verbatim with
# `isError:false`. Every schema above already carries `required` and `additionalProperties: False`;
# the contract was published to every client and enforced against none.
#
# This is SHAPE validation, not authorization — nothing here decides who may call what, so
# invariant 7 ("MCP is access, not authority") is untouched. The schemas already live in this module;
# what was missing is that they were documentation rather than a gate.
#
# A hand-written subset rather than a dependency, per the stdlib-first rule. The risk of a
# hand-written validator is that it silently ignores a keyword it does not implement, so the set it
# understands is declared and `tests/unit/test_mcp_argument_validation.py` walks every declared tool
# and FAILS on any keyword outside it. A schema that grows a new construct breaks the test rather
# than being waved through at runtime.
_UNDERSTOOD_SCHEMA_KEYWORDS: frozenset[str] = frozenset({
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "minimum", "maximum", "minItems",
})

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
    "boolean": bool,
}


def _walk_schema_keywords(schema: Any) -> set[str]:
    """Every schema keyword used anywhere in `schema`, including nested items/properties."""
    found: set[str] = set()
    if not isinstance(schema, dict):
        return found
    for key, value in schema.items():
        found.add(key)
        if key == "properties" and isinstance(value, dict):
            for sub in value.values():
                found |= _walk_schema_keywords(sub)
        elif key == "items":
            found |= _walk_schema_keywords(value)
    return found


def _validate_value(value: Any, schema: dict[str, Any], path: str) -> None:
    declared = schema.get("type")
    if declared:
        expected = _JSON_TYPES.get(declared)
        # `bool` is a subclass of `int` in Python; an integer field must not accept True.
        wrong = expected is not None and (
            not isinstance(value, expected)
            or (declared in ("integer", "number") and isinstance(value, bool))
        )
        if wrong:
            raise ToolError(f"{path} must be of type {declared}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolError(f"{path} must be one of {sorted(map(str, schema['enum']))}")
    if declared in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            raise ToolError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ToolError(f"{path} must be <= {schema['maximum']}")
    if declared == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ToolError(f"{path} must carry at least {schema['minItems']} item(s)")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, f"{path}[{index}]")
    if declared == "object":
        _validate_object(value, schema, path)


def _validate_object(value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
    properties = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name not in value:
            # NAME the field. A refusal that does not say what is missing sends the caller back to
            # guessing, and `publish_progress` without `status` must be refused rather than
            # DEFAULTED — a defaulted lifecycle transition is a durable record of a state change
            # nobody requested.
            raise ToolError(f"{path}: required argument {name!r} is missing")
    if schema.get("additionalProperties") is False:
        undeclared = sorted(set(value) - set(properties))
        if undeclared:
            raise ToolError(f"{path}: undeclared argument(s) {', '.join(repr(u) for u in undeclared)}")
    for name, sub_schema in properties.items():
        if name in value and isinstance(sub_schema, dict):
            _validate_value(value[name], sub_schema, f"{path}.{name}" if path != "arguments" else name)


_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {t["name"]: t["inputSchema"] for t in TOOLS}


def validate_tool_arguments(name: str, args: dict[str, Any]) -> None:
    """Refuse arguments that do not match the tool's DECLARED schema. Raises ToolError."""
    schema = _SCHEMA_BY_NAME.get(name)
    if schema is None:
        return
    _validate_object(args, schema, "arguments")


def handle_request(runtime: SovereignToolRuntime, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    rid = request.get("id")
    if method and method.startswith("notifications/"):
        return None
    if rid is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"}, "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "resources/list":
        # W-56 / R-09b: the live conductor's first substantive call was `resources/list`, and this
        # server answered -32601 "method not found", so the call could never succeed even once
        # startup worked. The honest answer today is an EMPTY inventory: the canonical Phase 3A
        # resource registry (conductor-file / artifact / task / evidence resources, canonical Build
        # Handoff §9.5) is not implemented on this tree — `mcp_server/resources/` holds a scaffold
        # `.gitkeep` — and building it is a subsystem, not a surgical unit. Like `tools/list` this
        # needs no app-control capability, so a dead gateway cannot withhold it (W-55's property).
        # DECLARED BOUND: the capabilities block still advertises TOOLS ONLY, and `resources/read`
        # and `resources/templates/list` remain method-not-found — nothing is observed calling
        # them, and there is nothing to read or template. A future registry must declare the
        # capability and grade those methods, not inherit this tolerance.
        return {"jsonrpc": "2.0", "id": rid, "result": {"resources": []}}
    if method == "tools/call":
        params = request.get("params") or {}
        try:
            result = runtime.call(params.get("name", ""), params.get("arguments") or {})
            payload = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                       "structuredContent": result, "isError": False}
        except Exception as exc:  # fail closed and keep the MCP process alive for later calls
            payload = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                       "isError": True}
        return {"jsonrpc": "2.0", "id": rid, "result": payload}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


# --- W-55: startup diagnosability -----------------------------------------------------------------
# The capability round-trip used to run BEFORE a single frame of stdin was read, and any failure
# exited 2 to a stderr the launching CLI discards — the operator saw "MCP server 'sovereign' was
# not ready for this step" and nothing anywhere explained why. The round-trip now runs AFTER the
# first frame is answered, and a failure is a degraded state, not a dead process: the fault is
# recorded under the store root, and every tool call answers with a structured error and retries
# the resolution, so a gateway that comes up later is recovered by the next call.
#
# The EAGER attempt is kept deliberately, after the first answered frame: the worker admission
# chain reads this process's first gateway arrival as evidence of life — the MCP_CONNECTING loop
# in `apps/desktop/control/worker-readiness.js` stalls a worker whose session never establishes,
# and `apps/desktop/control/assignment-gate.js` refuses to assign to one. The defect was the
# FATAL failure mode, not the round-trip.
STARTUP_FAULT_LOG_NAME = "mcp_startup_faults.log"
# Capped: a gateway that stays down while a node keeps calling must not grow a file forever (the
# W-35/W-63 class). The lines already written carry the diagnosis; at the cap the log stops.
STARTUP_FAULT_LOG_CAP_BYTES = 1024 * 1024


def _log_startup_fault(store_root: Path, exc: Exception) -> None:
    """W-55: record a capability-resolution fault somewhere the operator can find it.

    stderr still gets a copy, but the launching CLI discards it, so the durable line under the
    store root is the point. Best effort: a fault log that cannot be written must not mask the
    fault itself.
    """
    message = f"{type(exc).__name__}: {exc}"
    print(f"sovereign MCP capability unavailable: {message}", file=sys.stderr, flush=True)
    try:
        store_root.mkdir(parents=True, exist_ok=True)
        log_path = store_root / STARTUP_FAULT_LOG_NAME
        if log_path.exists() and log_path.stat().st_size >= STARTUP_FAULT_LOG_CAP_BYTES:
            return
        from datetime import datetime, timezone
        line = json.dumps({"recorded_at": datetime.now(timezone.utc).isoformat(),
                           "fault": message}) + "\n"
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        pass


class _DeferredRuntime:
    """W-55: the capability round-trip, deferred past the first answered frame and never fatal.

    `handle_request` needs only `.call` and `main()` only `.close`, so the holder exposes exactly
    those. Resolution is attempted eagerly once (`.warm`, after the first answered frame) and
    retried on every tool call until it succeeds.
    """

    def __init__(self, port_text: str, token: str, store_root: Path) -> None:
        self._port_text = port_text
        self._token = token
        self._store_root = store_root
        self._runtime: SovereignToolRuntime | None = None

    def warm(self) -> None:
        try:
            self._ensure()
        except ToolError:
            pass  # diagnosed and durably logged in _build; the next tool call retries

    def call(self, name: str, args: dict[str, Any]) -> Any:
        return self._ensure().call(name, args)

    def close(self) -> None:
        if self._runtime is not None:
            self._runtime.close()

    def _ensure(self) -> SovereignToolRuntime:
        if self._runtime is None:
            self._runtime = self._build()
        return self._runtime

    def _build(self) -> SovereignToolRuntime:
        try:
            app = AppControlClient(int(self._port_text), self._token)
            runtime = SovereignToolRuntime(app, self._store_root, policy=SovereignPolicy())
        except Exception as exc:
            _log_startup_fault(self._store_root, exc)
            raise ToolError(
                "sovereign MCP capability is unavailable: the control gateway could not be "
                f"resolved ({type(exc).__name__}: {exc}). The fault is recorded under "
                f"{self._store_root / STARTUP_FAULT_LOG_NAME}; this call will be retried.") from exc
        # W-62 / U434: a node whose capability RESOLVED is an established node, and from this moment
        # it keeps itself verifiably alive on its own cadence — idle health and store-only work no
        # longer read as silence (the gateway stamps `_lastSeen` on every beat). Started here, not
        # in the runtime's constructor, so a runtime a test constructs directly grows no thread it
        # did not ask for. The interval honours an env override so a test can state a cadence in
        # real time without sleeping through the production one (60 s).
        try:
            interval = float(os.environ.get("SOVEREIGN_HEARTBEAT_INTERVAL_S",
                                             DEFAULT_HEARTBEAT_INTERVAL_S))
        except ValueError:
            interval = DEFAULT_HEARTBEAT_INTERVAL_S
        if interval > 0:
            runtime.start_heartbeat(interval_s=interval)
        return runtime


def main() -> int:
    # W-04/A-5: pin the transport codec in BOTH directions before a single frame moves.
    #
    # Inbound, `for line in sys.stdin` decoded with the host ANSI codepage (cp1252 on this host), so
    # non-ASCII task/message/artifact content was persisted as mojibake WITH THE CONTENT HASHES
    # COMPUTED OVER THE MOJIBAKE -- `artifact_id` is `sha256:<hash of the content>`, so the stored
    # id did not describe the bytes the caller sent. Outbound, `ensure_ascii=False` written to a
    # locale-encoded stdout raises UnicodeEncodeError on the first non-ASCII response character,
    # which is a hard failure that can kill the server mid-session rather than a corruption.
    #
    # DELIBERATE DIVERGENCE FROM THE SIBLING, and do not "correct" it back: `mcp_server/server.py`
    # decodes with `errors="replace"`, which is right for a transport that DISCARDS its frame. Here
    # the input becomes persisted content with hashes over it, so a silent U+FFFD substitution is
    # exactly the corruption this repair exists to remove. Input is therefore STRICT, and a frame
    # that is not UTF-8 is REPORTED as a JSON-RPC parse error rather than absorbed.
    #
    # The bytes are read from `sys.stdin.buffer` rather than reconfiguring the text wrapper,
    # because a decode failure on the wrapper raises from the `for` itself -- outside any per-frame
    # handler -- and would end the loop instead of answering. Per-frame decoding is what makes
    # "reported, not persisted" reachable at all.
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    # W-55: the capability is resolved by `_DeferredRuntime` — never before the first frame is
    # answered, and never fatally. No `return 2` path remains: a failed resolution degrades.
    holder = _DeferredRuntime(os.environ.get("SOVEREIGN_CONTROL_PORT", "0"),
                              os.environ.get("SOVEREIGN_CONTROL_TOKEN", ""),
                              _resolve_store_root())
    warmed = False
    try:
        # W-34: BOUNDED. `for raw_line in sys.stdin.buffer` buffers a line with no ceiling, so a
        # single frame with no newline was unbounded memory in this process before anything was
        # parsed or authorized — the one PRE-AUTH surface here. Donor: `mcp_server/server.py:86`.
        stdin = sys.stdin.buffer
        while True:
            raw_line = stdin.readline(MAX_STDIO_LINE_BYTES + 1)
            if not raw_line:
                break
            if not raw_line.strip():
                continue
            if len(raw_line) > MAX_STDIO_LINE_BYTES:
                # The rest of the oversized frame must be DRAINED, not left in the buffer: its tail
                # would otherwise be read as the next frame(s) and parsed as garbage, turning one
                # refusal into a stream of them. Drained in bounded chunks so draining is not itself
                # an unbounded read.
                while True:
                    chunk = stdin.readline(MAX_STDIO_LINE_BYTES + 1)
                    if not chunk or chunk.endswith(b"\n") and len(chunk) <= MAX_STDIO_LINE_BYTES:
                        break
                response = {"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32600,
                                      "message": f"request too large: a frame may not exceed "
                                                 f"{MAX_STDIO_LINE_BYTES} bytes"}}
            else:
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    response = {"jsonrpc": "2.0", "id": None,
                                "error": {"code": -32700,
                                          "message": f"UnicodeDecodeError: {exc}"}}
                else:
                    try:
                        request = json.loads(line)
                        response = handle_request(holder, request)
                    except Exception as exc:
                        response = {"jsonrpc": "2.0", "id": None,
                                    "error": {"code": -32700,
                                              "message": f"{type(exc).__name__}: {exc}"}}
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                if not warmed:
                    # W-55: the round-trip AFTER the first answered frame, never before it. Its
                    # failure is already logged durably inside the holder; the loop keeps serving.
                    holder.warm()
                    warmed = True
    finally:
        holder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
