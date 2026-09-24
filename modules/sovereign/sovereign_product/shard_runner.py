"""Fresh-context shard execution with a bounded carried ledger (sharded inference P3).

Big workloads run as a sequence of SHARDS. Every shard is a brand-new model session - no chat
history, no carried KV state - built from exactly four things: a fixed role, the shard's
instruction, the current LEDGER, and the shard's own content. What carries from one shard to the
next is the ledger: a small, structured, token-budgeted record (facts, decisions, open questions,
per-shard result summaries), never a transcript. When the ledger outgrows its budget, a separate
fresh session condenses it. This keeps every call inside the model's window no matter how large the
whole workload is, and it is what lets a slow, big model (GPU + RAM split) do long agentic work.

Durability generalizes the RESEARCH executor's approach: every event (run start, task result,
ledger version, failure, completion) is appended to a hash-chained checkpoint log under the run
directory, and full shard outputs are stored beside it by content hash. A crash, cancel or reboot
resumes at the next unfinished task; completed shards are never re-run. A shard whose output is
not valid is retried in a fresh session a bounded number of times, then recorded as FAILED - never
silently dropped.

The model and the token counter are injected (``ModelPort``), so this core is engine-agnostic and
tested with a fake model; production wires it to the llama.cpp client with exact token counts.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

LEDGER_SCHEMA = 1
CHECKPOINT_SCHEMA = 1
LEDGER_LISTS = ("facts", "decisions", "open_questions")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "budget_exhausted")
# A cancelled or budget-exhausted run can be resumed later; completed/failed runs are final.
FINAL_STATUSES = ("completed", "failed")

SYSTEM_ROLE = (
    "You are one step of a long, multi-step job. You see only this step's instruction, the job "
    "LEDGER (what earlier steps established) and this step's input. Earlier conversation does not "
    "exist. Work only from what is given. Reply with ONE JSON object and nothing else."
)
REPLY_CONTRACT = (
    'Reply format: {"result": "<your answer for this step>", "ledger_update": '
    '{"add_facts": [..], "add_decisions": [..], "add_open_questions": [..], '
    '"resolve_open_questions": [..]}}. Keep ledger entries short and self-contained; add only '
    "what later steps need."
)


class ShardRunError(RuntimeError):
    """The run cannot proceed (corrupt checkpoint, impossible budget, ...)."""


class ModelPort(Protocol):
    def generate(self, *, system: str, prompt: str, max_tokens: int,
                 should_stop: Callable[[], bool]) -> str: ...

    def count_tokens(self, text: str) -> int: ...


# --- ledger ---------------------------------------------------------------------------------------

@dataclass
class Ledger:
    """The only state carried between fresh sessions."""

    facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    results: list[dict[str, str]] = field(default_factory=list)
    version: int = 0

    def render(self) -> str:
        return json.dumps({"facts": self.facts, "decisions": self.decisions,
                           "open_questions": self.open_questions, "results": self.results},
                          ensure_ascii=False, separators=(",", ":"))

    def apply(self, update: Mapping[str, Any], *, task_id: str, summary: str | None) -> None:
        for key, target in (("add_facts", self.facts), ("add_decisions", self.decisions),
                            ("add_open_questions", self.open_questions)):
            for item in update.get(key) or []:
                text = str(item).strip()
                if text and text not in target:
                    target.append(text)
        resolved = {str(q).strip() for q in update.get("resolve_open_questions") or []}
        self.open_questions = [q for q in self.open_questions if q not in resolved]
        if summary is not None:
            self.results.append({"task": task_id, "summary": summary})
        self.version += 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Ledger":
        ledger = cls()
        for key in (*LEDGER_LISTS,):
            values = data.get(key) or []
            if not isinstance(values, list):
                raise ShardRunError(f"ledger.{key} must be a list")
            setattr(ledger, key, [str(v) for v in values])
        results = data.get("results") or []
        if not isinstance(results, list):
            raise ShardRunError("ledger.results must be a list")
        ledger.results = [{"task": str(r.get("task", "")), "summary": str(r.get("summary", ""))}
                          for r in results if isinstance(r, Mapping)]
        ledger.version = int(data.get("version") or 0)
        return ledger


# --- tasks and budgets ----------------------------------------------------------------------------

@dataclass(frozen=True)
class ShardTask:
    task_id: str
    kind: str                       # map | reduce | plan | step | synthesize (mode-defined)
    instruction: str
    content: str = ""
    max_output_tokens: int = 2048

    def __post_init__(self) -> None:
        if not self.task_id or not self.kind or not self.instruction:
            raise ShardRunError("task_id, kind and instruction are required")
        if self.max_output_tokens <= 0:
            raise ShardRunError("max_output_tokens must be positive")


@dataclass(frozen=True)
class RunLimits:
    context_tokens: int              # the model window every fresh session must fit
    ledger_budget_tokens: int = 4096  # condense the ledger above this
    margin_tokens: int = 512          # chat template + reply-contract slack
    max_attempts: int = 3             # per task, each in a fresh session
    max_model_calls: int = 10_000
    max_wall_seconds: float = 7 * 24 * 3600.0

    def __post_init__(self) -> None:
        if self.context_tokens < 4096:
            raise ShardRunError("context_tokens must be at least 4096")
        if not (0 < self.ledger_budget_tokens < self.context_tokens // 2):
            raise ShardRunError("ledger_budget_tokens must be positive and under half the window")
        if self.max_attempts < 1 or self.max_model_calls < 1:
            raise ShardRunError("max_attempts and max_model_calls must be positive")

    def content_budget(self, fixed_tokens: int, max_output: int) -> int:
        """Tokens left for a shard's content after instruction, ledger and the reply."""
        return self.context_tokens - fixed_tokens - max_output - self.margin_tokens


# --- checkpoints ----------------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CheckpointLog:
    """Append-only, hash-chained event log (one JSON file per event)."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._tail: tuple[int, str] | None = None  # (sequence, hash) once verified

    def _files(self) -> list[Path]:
        return sorted(p for p in self.directory.glob("*.json") if p.name[:8].isdigit())

    def events(self) -> list[dict[str, Any]]:
        """Every event, verified: sequence, hash and chain. Fails closed on any break."""
        previous = "0" * 64
        events = []
        for index, path in enumerate(self._files(), 1):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ShardRunError(f"checkpoint {path.name} is unreadable: {exc}") from exc
            body = {k: v for k, v in record.items() if k != "hash"}
            if (record.get("sequence") != index or record.get("previous") != previous
                    or record.get("hash") != _sha256(json.dumps(body, sort_keys=True).encode())):
                raise ShardRunError(f"checkpoint chain is broken at {path.name}")
            previous = record["hash"]
            events.append(record)
        self._tail = (len(events), previous)
        return events

    def append(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._tail is None:
            self.events()  # verify the whole chain once; appends then extend the known tail
        sequence, previous = self._tail
        body = {"schema": CHECKPOINT_SCHEMA, "sequence": sequence + 1, "previous": previous,
                "event": event, "utc": _utc_now(), "payload": dict(payload)}
        record = {**body, "hash": _sha256(json.dumps(body, sort_keys=True).encode())}
        target = self.directory / f"{body['sequence']:08d}_{event}.json"
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        self._tail = (body["sequence"], record["hash"])
        return record


# --- the runner -----------------------------------------------------------------------------------

@dataclass
class RunState:
    run_id: str
    objective: str
    mode: str
    tasks: list[ShardTask]
    ledger: Ledger
    completed: dict[str, dict[str, Any]]       # task_id -> {"output_sha256", "summary", ...}
    failed: dict[str, str]
    status: str
    model_calls: int
    started_monotonic: float


def _parse_reply(text: str) -> tuple[str, dict[str, Any]]:
    """The model's JSON reply -> (result, ledger_update). Raises ValueError when invalid."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate[candidate.find("{"):] if "{" in candidate else candidate
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("reply contains no JSON object")
    data = json.loads(candidate[start:end + 1])
    if not isinstance(data, dict) or not isinstance(data.get("result"), str):
        raise ValueError('reply must be an object with a string "result"')
    update = data.get("ledger_update") or {}
    if not isinstance(update, dict):
        raise ValueError('"ledger_update" must be an object')
    for key in ("add_facts", "add_decisions", "add_open_questions", "resolve_open_questions"):
        if key in update and not isinstance(update[key], list):
            raise ValueError(f'"ledger_update.{key}" must be a list')
    return data["result"], update


def _summarize(result: str, limit: int = 400) -> str:
    text = " ".join(result.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class ShardRunner:
    """Runs a task list shard by shard, each in a fresh session, with a checkpointed ledger."""

    def __init__(self, run_dir: Path, model: ModelPort, limits: RunLimits, *,
                 should_stop: Callable[[], bool] = lambda: False,
                 progress: Callable[[dict[str, Any]], None] = lambda event: None,
                 on_task_done: Callable[["ShardRunner", "RunState", ShardTask], None]
                 | None = None,
                 validators: Mapping[str, Callable[[str], None]] | None = None,
                 summary_kinds: Iterable[str] | None = None,
                 monotonic: Callable[[], float] = time.monotonic):
        self.run_dir = Path(run_dir)
        self.model = model
        self.limits = limits
        self.should_stop = should_stop
        self.progress = progress
        self.monotonic = monotonic
        # A MODE (input shards, plan steps) reacts to finished tasks by adding more - reduce
        # rounds, next plan steps. It must be idempotent: on resume it sees the same tasks again.
        self.on_task_done = on_task_done
        # Per task-kind result validators (e.g. "a plan must be a JSON list"). A validator raises
        # ValueError; the reply is then treated as invalid and retried in a fresh session.
        self.validators = dict(validators or {})
        # Which task kinds leave a result summary in the ledger (None = all). Map/reduce needs
        # none - reduce sessions read the map outputs directly - so its ledger stays facts-only
        # instead of growing by one line per chunk.
        self.summary_kinds = None if summary_kinds is None else frozenset(summary_kinds)
        self.state: RunState | None = None
        self.log = CheckpointLog(self.run_dir / "checkpoints")
        self.outputs = self.run_dir / "outputs"
        self.outputs.mkdir(parents=True, exist_ok=True)

    # -- lifecycle ---------------------------------------------------------------------------------
    def start(self, objective: str, mode: str, tasks: Sequence[ShardTask]) -> RunState:
        if self.log.events():
            raise ShardRunError(f"{self.run_dir} already holds a run; use resume()")
        ids = [t.task_id for t in tasks]
        if len(set(ids)) != len(ids):
            raise ShardRunError("task ids must be unique")
        self.log.append("run_started", {"run_id": uuid.uuid4().hex, "objective": objective,
                                        "mode": mode, "tasks": [asdict(t) for t in tasks],
                                        "limits": asdict(self.limits)})
        return self.resume()

    def load(self) -> RunState:
        events = self.log.events()
        if not events or events[0]["event"] != "run_started":
            raise ShardRunError(f"{self.run_dir} holds no run")
        head = events[0]["payload"]
        state = RunState(run_id=head["run_id"], objective=head["objective"], mode=head["mode"],
                         tasks=[ShardTask(**t) for t in head["tasks"]], ledger=Ledger(),
                         completed={}, failed={}, status="running", model_calls=0,
                         started_monotonic=self.monotonic())
        for event in events[1:]:
            payload = event["payload"]
            state.model_calls = int(payload.get("model_calls", state.model_calls))
            if event["event"] in ("task_completed", "ledger_compacted", "tasks_added"):
                if "ledger" in payload:
                    state.ledger = Ledger.from_dict(payload["ledger"])
            if event["event"] == "task_completed":
                output = self.outputs / f"{payload['output_sha256']}.txt"
                if not output.is_file() or _sha256(output.read_bytes()) != payload["output_sha256"]:
                    raise ShardRunError(f"stored output for {payload['task_id']} is missing or "
                                        "altered")
                state.completed[payload["task_id"]] = payload
                state.failed.pop(payload["task_id"], None)
            elif event["event"] == "task_failed":
                state.failed[payload["task_id"]] = payload["error"]
            elif event["event"] == "tasks_added":
                state.tasks.extend(ShardTask(**t) for t in payload["tasks"])
            elif event["event"] == "run_finished":
                state.status = payload["status"]
            elif event["event"] == "run_resumed":
                state.status = "running"
        return state

    def resume(self) -> RunState:
        """Continue (or start) executing unfinished tasks. Returns the final state."""
        state = self.state = self.load()
        if state.status in FINAL_STATUSES:
            return state
        if state.status in TERMINAL_STATUSES:
            self.log.append("run_resumed", {"after": state.status,
                                            "model_calls": state.model_calls})
            state.status = "running"
        if self.on_task_done is not None:
            # Replay the mode over finished work so a resumed run regains any tasks it had
            # not yet added before the interruption (add_tasks ignores duplicates).
            for task in list(state.tasks):
                if task.task_id in state.completed or task.task_id in state.failed:
                    self.on_task_done(self, state, task)
        while True:
            task = next((t for t in state.tasks if t.task_id not in state.completed
                         and t.task_id not in state.failed), None)
            if task is None:
                break
            stop = self._stop_reason(state)
            if stop:
                return self._finish(state, stop)
            self._run_task(state, task)
            if self.on_task_done is not None and (task.task_id in state.completed
                                                  or task.task_id in state.failed):
                self.on_task_done(self, state, task)
        return self._finish(state, "failed" if state.failed else "completed")

    def add_tasks(self, tasks: Iterable[ShardTask]) -> list[ShardTask]:
        """Append tasks to the running plan (checkpointed); returns those actually added."""
        state = self.state if self.state is not None else self.load()
        known = {t.task_id for t in state.tasks}
        new = []
        for task in tasks:
            if task.task_id not in known:
                known.add(task.task_id)
                new.append(task)
        if new:
            self.log.append("tasks_added", {"tasks": [asdict(t) for t in new],
                                            "model_calls": state.model_calls})
            state.tasks.extend(new)
        return new

    def output_of(self, state: RunState, task_id: str) -> str:
        record = state.completed[task_id]
        return (self.outputs / f"{record['output_sha256']}.txt").read_text(encoding="utf-8")

    # -- internals ---------------------------------------------------------------------------------
    def _stop_reason(self, state: RunState) -> str | None:
        if self.should_stop():
            return "cancelled"
        if state.model_calls >= self.limits.max_model_calls:
            return "budget_exhausted"
        if self.monotonic() - state.started_monotonic > self.limits.max_wall_seconds:
            return "budget_exhausted"
        return None

    def _finish(self, state: RunState, status: str) -> RunState:
        self.log.append("run_finished", {"status": status, "model_calls": state.model_calls,
                                         "completed": len(state.completed),
                                         "failed": sorted(state.failed)})
        state.status = status
        self.progress({"event": "run_finished", "status": status})
        return state

    def fixed_prompt(self, task: ShardTask, ledger: Ledger) -> str:
        return (f"INSTRUCTION ({task.kind}):\n{task.instruction}\n\n"
                f"LEDGER (from earlier steps):\n{ledger.render()}\n\n{REPLY_CONTRACT}\n\n"
                "INPUT:\n")

    def _prompt(self, task: ShardTask, ledger: Ledger, retry_note: str = "") -> str:
        prompt = self.fixed_prompt(task, ledger) + task.content
        if retry_note:
            prompt += f"\n\nNOTE: a previous attempt at this step was rejected: {retry_note}"
        return prompt

    def _ensure_fits(self, task: ShardTask, ledger: Ledger) -> None:
        used = self.model.count_tokens(SYSTEM_ROLE) + self.model.count_tokens(
            self._prompt(task, ledger, retry_note="x" * 200))
        room = self.limits.context_tokens - used - task.max_output_tokens - self.limits.margin_tokens
        if room < 0:
            raise ShardRunError(
                f"task {task.task_id} does not fit the {self.limits.context_tokens}-token window "
                f"({used} prompt + {task.max_output_tokens} reply + margin); shard it smaller")

    def _run_task(self, state: RunState, task: ShardTask) -> None:
        if self.model.count_tokens(state.ledger.render()) > self.limits.ledger_budget_tokens:
            self._compact(state)
        self._ensure_fits(task, state.ledger)
        note, last_error = "", ""
        for attempt in range(1, self.limits.max_attempts + 1):
            if self._stop_reason(state):
                return
            self.progress({"event": "task_started", "task": task.task_id, "attempt": attempt,
                           "done": len(state.completed), "total": len(state.tasks)})
            state.model_calls += 1
            try:
                text = self.model.generate(system=SYSTEM_ROLE,
                                           prompt=self._prompt(task, state.ledger, note),
                                           max_tokens=task.max_output_tokens,
                                           should_stop=self.should_stop)
                result, update = _parse_reply(text)
                validator = self.validators.get(task.kind)
                if validator is not None:
                    validator(result)
            except ValueError as exc:
                last_error = str(exc)
                note = f"{last_error}. Reply with ONE valid JSON object only."
                continue
            except Exception as exc:  # the model call itself failed; fresh retry
                last_error = f"{type(exc).__name__}: {exc}"
                note = ""
                continue
            data = result.encode("utf-8")
            digest = _sha256(data)
            (self.outputs / f"{digest}.txt").write_bytes(data)
            summary = _summarize(result)
            carried = (summary if self.summary_kinds is None or task.kind in self.summary_kinds
                       else None)
            state.ledger.apply(update, task_id=task.task_id, summary=carried)
            record = {"task_id": task.task_id, "kind": task.kind, "attempts": attempt,
                      "output_sha256": digest, "summary": summary,
                      "ledger": state.ledger.to_dict(), "model_calls": state.model_calls}
            self.log.append("task_completed", record)
            state.completed[task.task_id] = record
            self.progress({"event": "task_completed", "task": task.task_id,
                           "done": len(state.completed), "total": len(state.tasks)})
            return
        self.log.append("task_failed", {"task_id": task.task_id, "error": last_error,
                                        "attempts": self.limits.max_attempts,
                                        "model_calls": state.model_calls})
        state.failed[task.task_id] = last_error
        self.progress({"event": "task_failed", "task": task.task_id, "error": last_error})

    def _compact(self, state: RunState) -> None:
        """Condense the ledger in its own fresh session (never truncate it silently)."""
        budget = self.limits.ledger_budget_tokens
        task = ShardTask(
            task_id=f"compact-{state.ledger.version}", kind="compact",
            instruction=(f"Condense the LEDGER so that the new ledger is under {budget // 2} "
                         "tokens. Keep every decision and every unresolved open question; merge "
                         "overlapping facts; replace per-step results with one short line each. "
                         'Reply {"result": "<one-line note>", "ledger": {"facts": [..], '
                         '"decisions": [..], "open_questions": [..], "results": [{"task": .., '
                         '"summary": ..}]}}.'),
            max_output_tokens=min(budget, 4096))
        for _attempt in range(self.limits.max_attempts):
            state.model_calls += 1
            try:
                text = self.model.generate(system=SYSTEM_ROLE,
                                           prompt=f"INSTRUCTION:\n{task.instruction}\n\n"
                                                  f"LEDGER:\n{state.ledger.render()}",
                                           max_tokens=task.max_output_tokens,
                                           should_stop=self.should_stop)
                start, end = text.find("{"), text.rfind("}")
                data = json.loads(text[start:end + 1])
                condensed = Ledger.from_dict(data["ledger"])
            except Exception:
                continue
            condensed.version = state.ledger.version + 1
            if self.model.count_tokens(condensed.render()) > budget:
                continue
            state.ledger = condensed
            self.log.append("ledger_compacted", {"ledger": condensed.to_dict(),
                                                 "model_calls": state.model_calls})
            self.progress({"event": "ledger_compacted", "version": condensed.version})
            return
        raise ShardRunError("the ledger outgrew its budget and could not be condensed; "
                            "raise ledger_budget_tokens or shorten per-step ledger updates")
