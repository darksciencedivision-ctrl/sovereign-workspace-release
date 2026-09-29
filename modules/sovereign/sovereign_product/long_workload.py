"""The LONG route: big-model, big-workload runs through the product (sharded inference P6).

Ties the pieces together:

* ``long_workload.json`` (shipped) names the models the LONG route may run and the context each is
  served at; ``apply_hybrid_plans`` makes the llama.cpp supervisor serve them with the GPU/RAM split
  ``memory_planner`` computes (within the operator's RAM budget) instead of the CPU-only default.
* ``LlamaModelPort`` adapts the llama.cpp client to the shard runner: one fresh chat per call, exact
  token counts from the model's own tokenizer, cancellation passed straight through.
* ``LongWorkloadExecutor`` runs a job: the message is the OBJECTIVE; material after a line ``---``
  is sharded map/reduce (``InputShardMode``); no material means agentic plan steps
  (``PlanStepMode``). Large inputs are referenced as ``@input: <file name>`` and read ONLY from the
  state home's ``long_inputs`` inbox. An optional first line ``@model: <name>`` picks one of the
  configured models (default: ``default_model``). The run lives under ``evidence/long/<job id>/``, so a product
  restart resumes it instead of starting over.

LONG requires the llama.cpp backend: exact token counts and the hybrid split are llama.cpp
features, and the operator chose llama.cpp for this path.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .exact_counting import (STATE_FILE as EXACT_STATE_FILE, ExactCancelled, ExactCounter,
                             is_countable_objective)
from .gguf_meta import GGUFError, read_gguf
from .memory_planner import GIB, KV_TYPE_BYTES, MemoryBudget, PlanRefused, plan_serving
from .paths import resolve_state_home
from .runtime_registry import RuntimeRegistry, hybrid_profile
from .shard_modes import InputShardMode, PlanStepMode
from .shard_runner import (ModelConfigurationError, ModelUnavailable, ReplyTruncated, RunLimits,
                           ShardRunner)

CONFIG_FILE = "long_workload.json"
INBOX_DIRNAME = "long_inputs"
MAX_INPUT_BYTES = 64 * 1024 * 1024
_MATERIAL_SPLIT = re.compile(r"^---[ \t]*$", re.MULTILINE)
_INPUT_REF = re.compile(r"^\s*@input:\s*(?P<name>[A-Za-z0-9._ -]{1,128})\s*$")
_MODEL_REF = re.compile(r"\A\s*@model:[ \t]*(?P<name>[^\r\n]*?)[ \t]*(?:\r?\n|\Z)")


def split_model_directive(text: str) -> tuple[str | None, str]:
    """``(model or None, rest)``: an optional first line ``@model: <name>`` picks the LONG model.

    Only models configured in long_workload.json can be chosen (LongConfig.model refuses others),
    so the choice never reaches a model the supervisor was not planned to serve. The directive is
    part of the stored job text, so a resumed run re-reads the same choice.
    """
    # A byte-order mark (Windows tools write one) is not whitespace to the regex: it silently
    # disabled the directive, ran the default model, and left "@model: ..." in the objective.
    text = text.lstrip("﻿")
    match = _MODEL_REF.match(text)
    if match is None:
        return None, text
    name = match.group("name").strip()
    if not name:
        raise LongWorkloadError("@model: needs a model name, e.g. '@model: qwen3:30b-a3b'")
    return name, text[match.end():]


class LongWorkloadError(ValueError):
    """The LONG request or configuration cannot run (reported to the operator)."""


@dataclass(frozen=True)
class LongModel:
    model: str
    context: int
    thinking: str = "off"
    # Tokens a reasoning model may spend thinking before it answers, added to every task's
    # output budget. Required with thinking "on": a thinking-only model (e.g. Qwen3 Thinking
    # 2507) reasons whatever enable_thinking says, and without room it never reaches its answer.
    reasoning_tokens: int = 0
    # KV cache type the planner serves this model with. q8_0 halves the f16 cache at no visible
    # cost; q4_0 quarters it, which frees GPU layers at long contexts, at some risk to accuracy.
    cache_type: str = "q8_0"


@dataclass(frozen=True)
class LongConfig:
    default_model: str
    ram_budget_gib: int
    prompt_cache_mib: int
    ledger_budget_tokens: int
    max_output_tokens: int
    models: tuple[LongModel, ...]

    def model(self, model_id: str | None = None) -> LongModel:
        wanted = model_id or self.default_model
        for entry in self.models:
            if entry.model == wanted:
                return entry
        raise LongWorkloadError(f"{wanted!r} is not configured for the LONG route")


def load_config(root: str | Path) -> LongConfig:
    path = Path(root) / CONFIG_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise LongWorkloadError(f"no {CONFIG_FILE} in {root}") from exc
    except (OSError, ValueError) as exc:
        raise LongWorkloadError(f"{path} is unreadable: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema") != 1:
        raise LongWorkloadError(f"{CONFIG_FILE} must declare schema 1")
    models = []
    for item in doc.get("models") or []:
        if not isinstance(item, dict) or not isinstance(item.get("model"), str):
            raise LongWorkloadError(f"{CONFIG_FILE} models[] entries need a model name")
        context = item.get("context")
        if isinstance(context, bool) or not isinstance(context, int) or context < 4096:
            raise LongWorkloadError(f"{item['model']}: context must be an integer >= 4096")
        thinking = item.get("thinking", "off")
        if thinking not in ("off", "on"):
            raise LongWorkloadError(f"{item['model']}: thinking must be 'off' or 'on'")
        reasoning = item.get("reasoning_tokens", 0)
        if isinstance(reasoning, bool) or not isinstance(reasoning, int) or reasoning < 0:
            raise LongWorkloadError(f"{item['model']}: reasoning_tokens must be an integer >= 0")
        if thinking == "on" and reasoning < 512:
            raise LongWorkloadError(f"{item['model']}: thinking 'on' needs reasoning_tokens >= 512 "
                                    "(room to reason before the answer)")
        if reasoning > context // 4:
            raise LongWorkloadError(f"{item['model']}: reasoning_tokens above a quarter of the "
                                    f"{context}-token context leaves no room for the work")
        cache_type = item.get("cache_type", "q8_0")
        if cache_type not in KV_TYPE_BYTES:
            raise LongWorkloadError(f"{item['model']}: cache_type must be one of "
                                    f"{', '.join(sorted(KV_TYPE_BYTES))}")
        models.append(LongModel(item["model"], context, thinking, reasoning, cache_type))
    if not models:
        raise LongWorkloadError(f"{CONFIG_FILE} configures no models")
    ints = {}
    for key, low in (("ram_budget_gib", 4), ("prompt_cache_mib", 0),
                     ("ledger_budget_tokens", 512), ("max_output_tokens", 128)):
        value = doc.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < low:
            raise LongWorkloadError(f"{CONFIG_FILE} {key} must be an integer >= {low}")
        ints[key] = value
    config = LongConfig(default_model=str(doc.get("default_model") or models[0].model),
                        models=tuple(models), **ints)
    config.model()  # the default must be one of the configured models
    return config


# --- serving: planned GPU/RAM split in the supervisor's registry ----------------------------------

def apply_hybrid_plans(registry: RuntimeRegistry, config: LongConfig, *,
                       vram_bytes: int | None,
                       reader: Callable[[str], Any] = read_gguf) -> dict[str, dict[str, Any]]:
    """Serve each LONG model with its planned split. Returns a per-model report.

    A model that is not installed, whose file cannot be read, or whose plan is refused keeps
    its existing profile and the reason is reported - the supervisor still starts.
    """
    if vram_bytes is None:
        return {m.model: {"applied": False, "reason": "free VRAM unknown (no nvidia-smi)"}
                for m in config.models}
    budget = MemoryBudget(vram_bytes=int(vram_bytes), ram_bytes=config.ram_budget_gib * GIB,
                          prompt_cache_mib=config.prompt_cache_mib)
    return {entry.model: plan_model(registry, entry.model, entry.context, budget,
                                    thinking_policy=entry.thinking, cache_type=entry.cache_type,
                                    reader=reader)
            for entry in config.models}


def plan_model(registry: RuntimeRegistry, model: str, context: int, budget: MemoryBudget, *,
               thinking_policy: str | None = None, cache_type: str = "q8_0",
               reader: Callable[[str], Any] = read_gguf) -> dict[str, Any]:
    """Replace ``model``'s profile in ``registry`` with its planned GPU/RAM split; the report.

    ``thinking_policy=None`` keeps the model's current one. The registry is untouched when the
    model is not installed, its file cannot be read, or the plan is refused.
    """
    existing = [p for p in registry.profiles.values() if p.model_id == model]
    if not existing:
        return {"applied": False, "reason": "model not installed"}
    try:
        plan = plan_serving(reader(existing[0].model_path), context=context, budget=budget,
                            cache_type=cache_type)
    except (GGUFError, PlanRefused, OSError, ValueError) as exc:
        return {"applied": False, "reason": str(exc)}
    profile = hybrid_profile(model, plan, thinking_policy=thinking_policy
                             or existing[0].thinking_policy)
    replaced = {p.profile_id for p in existing}
    for profile_id in replaced:
        registry.profiles.pop(profile_id, None)
    registry.add_profile(profile)
    for role_name, role in list(registry.roles.items()):
        if getattr(role, "profile_id", None) in replaced:
            registry.roles[role_name] = type(role)(**{**role.__dict__,
                                                      "profile_id": profile.profile_id})
    return {"applied": True, "profile": profile.profile_id,
            **{k: v for k, v in plan.as_dict().items()
               if k in ("n_gpu_layers", "n_cpu_moe", "context", "cache_type", "est_vram_gib",
                        "est_ram_gib", "kv_gib", "notes")}}


# --- the model port -------------------------------------------------------------------------------

class LlamaModelPort:
    """The shard runner's view of a llama.cpp model: fresh chats and exact token counts."""

    def __init__(self, client: Any, model: str, context: int, *, thinking: str = "off",
                 cancel_requested: Callable[[], bool] = lambda: False):
        self.client, self.model, self.context = client, model, context
        self.thinking = thinking
        self.cancel_requested = cancel_requested

    def generate(self, *, system: str, prompt: str, max_tokens: int,
                 should_stop: Callable[[], bool]) -> str:
        from .runtime_contracts import InferenceAuthError

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                options={"num_ctx": self.context, "num_predict": max_tokens, "temperature": 0.2},
                think=self.thinking == "on",
                cancel_requested=lambda: should_stop() or self.cancel_requested())
        except InferenceAuthError as exc:
            # A refused key fails every call the same way: stop the run and say why.
            raise ModelConfigurationError(str(exc)) from exc
        except Exception as exc:
            # A server that went away shows up as many different errors (connection refused,
            # a cut stream, 503 while it reloads, or an over-limit error once exact counting
            # fails). One cheap probe tells an outage from a real failure of this call.
            if not (should_stop() or self.cancel_requested()) and not self._answers():
                raise ModelUnavailable(f"the llama.cpp server is not answering ({exc})") from exc
            raise
        text = str(getattr(response, "text", "") or "")
        if self.thinking == "off" and not text.strip() and str(
                getattr(response, "reasoning", "") or "").strip():
            raise ModelConfigurationError(
                f"{self.model} reasoned although thinking is off and left no answer: it is a "
                "thinking-only model. Set \"thinking\": \"on\" with a \"reasoning_tokens\" "
                "budget for it in long_workload.json.")
        if str(getattr(response, "finish_reason", "") or "") == "length":
            raise ReplyTruncated(f"the reply was cut off at the {max_tokens}-token limit")
        return text

    def count_tokens(self, text: str) -> int:
        if self.cancel_requested():
            # Sizing a large @input takes thousands of /tokenize calls before any chunk runs;
            # a cancel must not wait for all of them (the job then ends cancelled).
            from .model_client import GenerationCancelled

            raise GenerationCancelled("cancelled while sizing the input")
        counted = self.client.count_text_tokens(self.model, text)
        if counted is None:
            # The client returns None when /tokenize fails. Mid-run, the old fallback (one token
            # per byte) sized a restarting server's chunks four times too big and failed the run
            # with a misleading "does not fit the window". An exact count is a LONG requirement.
            raise ModelUnavailable("the llama.cpp server did not count tokens (it is down, "
                                   "restarting or loading the model)")
        return counted

    def _answers(self) -> bool:
        try:
            return self.client.count_text_tokens(self.model, "ok") is not None
        except Exception:
            return False


# --- run timing (O4/O5) ---------------------------------------------------------------------------

def _endpoint_stats(client: Any) -> dict[str, list[float]]:
    """A snapshot of the client's per-endpoint call counts and seconds (none for fakes)."""
    stats = getattr(client, "endpoint_stats", None)
    return {k: list(v) for k, v in stats.items()} if isinstance(stats, Mapping) else {}


def _timing_telemetry(client: Any, before: Mapping[str, list[float]], started: float,
                      plan_seconds: float, now: float) -> dict[str, Any]:
    """Where a run's time went: sizing the input (planning) and the tokenizer endpoints."""
    after = _endpoint_stats(client)
    tokenizer = {}
    for path, (calls, seconds) in after.items():
        was_calls, was_seconds = before.get(path, [0, 0.0])
        tokenizer[path] = {"calls": int(calls - was_calls),
                           "seconds": round(seconds - was_seconds, 2)}
    return {"wall_seconds": round(now - started, 1), "plan_seconds": round(plan_seconds, 1),
            "tokenizer_endpoints": tokenizer,
            "tokenizer_seconds": round(sum(v["seconds"] for v in tokenizer.values()), 2)}


# --- the executor ---------------------------------------------------------------------------------

def parse_request(text: str, root: str | Path, *,
                  read_input: bool = True) -> tuple[str, str | None]:
    """(objective, material or None). Material may be an ``@input: <name>`` inbox reference.

    With ``read_input=False`` an inbox reference is returned as written, unread: a resumed run
    already holds its chunks in its checkpoints and must not depend on the file still existing.
    """
    parts = _MATERIAL_SPLIT.split(text, maxsplit=1)
    objective = parts[0].strip()
    if not objective:
        raise LongWorkloadError("a LONG request needs an objective before any '---' material")
    if len(parts) == 1:
        return objective, None
    material = parts[1].strip("\n")
    reference = _INPUT_REF.match(material)
    if reference is None and material.lstrip().lower().startswith("@input:"):
        # An inbox reference that is not a plain file name (a path, "..", a drive) is refused
        # outright rather than silently treated as literal text.
        raise LongWorkloadError("@input must name a plain file in the long_inputs inbox "
                                "(letters, digits, space, . _ -)")
    if reference and read_input:
        name = reference.group("name").strip()
        inbox = (resolve_state_home(root) / INBOX_DIRNAME).resolve()
        target = (inbox / name).resolve()
        if target.parent != inbox or not target.is_file():
            raise LongWorkloadError(f"@input {name!r} is not a file in {inbox}")
        if target.stat().st_size > MAX_INPUT_BYTES:
            raise LongWorkloadError(f"@input {name!r} exceeds {MAX_INPUT_BYTES // 2**20} MiB")
        material = target.read_text(encoding="utf-8", errors="replace")
    if not material.strip():
        raise LongWorkloadError("the material after '---' is empty")
    return objective, material


def _end_reason(state: Any) -> str:
    """Why a LONG run ended without an answer, in the operator's terms."""
    done, total = len(state.completed), len(state.tasks)
    if state.status == "cancelled":
        return f"cancelled after {done} of {total} chunks; the finished chunks stay in the ledger"
    failed = sorted(state.failed)
    if failed:
        return (f"run {state.status} after {done} of {total} chunks; failed: "
                f"{', '.join(failed)}")
    return f"run {state.status} after {done} of {total} chunks"


def _task_id_named(answer: str, task_id: str) -> bool:
    """True when ``task_id`` appears as its own token, not as a prefix of a longer id."""
    return re.search(rf"(?<![\w-]){re.escape(task_id)}(?![\w-])", answer) is not None


def _per_part_appendix(answer: str, state: Any) -> str:
    """One capped checkpoint-summary line per completed map, unless the answer already names them.

    The checkpoint summary is already collapsed and at most 400 characters. The appendix is
    omitted when the reduce answer contains every completed map's task id, so a model that
    already listed the parts is not repeated. Deterministic: a replay builds the same text.
    """
    maps = [task for task in state.tasks if task.kind == "map"]
    completed = [task for task in maps if task.task_id in state.completed]
    if len(maps) < 2 or not completed:
        return answer
    if all(_task_id_named(answer, task.task_id) for task in completed):
        return answer
    lines = []
    for task in completed:
        summary = " ".join(str(state.completed[task.task_id].get("summary") or "").split())
        if len(summary) > 400:
            summary = summary[:397] + "..."
        lines.append(f"- {task.task_id}: {summary}")
    return answer.rstrip() + "\n\nPer-part results:\n" + "\n".join(lines)


def _coverage_note(state: Any, gaps: list[str]) -> str:
    """Deterministic disclosure appended to an answer produced while some chunks failed."""
    maps = [t.task_id for t in state.tasks if t.kind == "map"]
    failed_maps = [g for g in gaps if g in maps]
    if failed_maps:
        return (f"COVERAGE GAP: {len(failed_maps)} of {len(maps)} parts of the input could not be "
                f"processed ({', '.join(failed_maps)}), so this answer does not cover them; any "
                "count or total above is missing those parts.")
    return (f"INCOMPLETE: {len(gaps)} of {len(state.tasks)} chunks failed ({', '.join(gaps)}); "
            "this answer was produced without them.")


#: A LONG job is started at most this many times in all, counting restart resumes, so a job that
#: keeps taking the product down cannot restart it forever.
RESTART_ATTEMPTS = 3


def restart_decision(evidence_dir: Path, job: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Whether a LONG job left ``running`` by a product restart resumes: ``(resume, reason)``.

    Live (2026-09-27), a restart marked an hours-long LONG job ``interrupted`` although its
    checkpoints could resume it. A LONG job resumes when its run directory holds no run yet
    (nothing was lost: it starts again) or a run whose checkpoint chain and stored outputs verify
    (``ShardRunner.resume`` continues at the first unfinished task, and a run that had finished just
    reports its result). It does not resume when a cancel was requested, when it has already been
    started RESTART_ATTEMPTS times, or when its checkpoints are broken; the reason says which.
    Other routes return ``(False, None)`` and keep the default (interrupted). Read-only.
    """
    if str(job.get("route") or "").upper() != "LONG":
        return False, None
    if job.get("cancel_requested"):
        return False, "its cancellation had been requested"
    attempts = int(job.get("attempts") or 0)
    if attempts >= RESTART_ATTEMPTS:
        return False, (f"the LONG run was already started {attempts} times, so it is not resumed "
                       "again; resubmit it to run it again")
    problem = checkpoint_problem(evidence_dir, str(job["job_id"]))
    if problem:
        return False, problem
    return True, None


def checkpoint_problem(evidence_dir: Path, job_id: str) -> str | None:
    """Why a LONG job's stored run cannot be resumed, or None when it can (read-only)."""
    from .shard_runner import ShardRunError, verify_stored_run

    try:
        verify_stored_run(Path(evidence_dir) / "long" / job_id)
    except (ShardRunError, OSError, ValueError, KeyError, TypeError) as exc:
        return f"its LONG checkpoints cannot be resumed ({exc})"
    return None


def describe_run(evidence_dir: Path, job_id: str) -> dict[str, Any]:
    """Read-only view of a LONG run for the operator: its chunks and the carried ledger.

    Built only from the run's hash-verified checkpoints (a broken chain raises ShardRunError);
    nothing is written, and a job that has not started yet reports ``started: false``.
    """
    from .shard_runner import CheckpointLog

    directory = Path(evidence_dir) / "long" / job_id / "checkpoints"
    if not directory.is_dir():
        return {"job_id": job_id, "started": False, "tasks": [], "ledger": None}
    events = CheckpointLog(directory).events()
    if not events or events[0].get("event") != "run_started":
        return {"job_id": job_id, "started": False, "tasks": [], "ledger": None}
    head = events[0]["payload"]
    tasks: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def add(items: Any, after: str | None = None) -> None:
        at = order.index(after) + 1 if after in order else len(order)
        for item in items or []:
            if isinstance(item, Mapping) and item.get("task_id") not in tasks:
                order.insert(at, str(item["task_id"]))
                at += 1
                tasks[str(item["task_id"])] = {"task_id": str(item["task_id"]),
                                               "kind": str(item.get("kind") or ""),
                                               "status": "pending", "attempts": 0,
                                               "summary": None, "error": None, "utc": None}

    add(head.get("tasks"))
    ledger: Any = None
    status, model_calls = "running", 0
    for event in events[1:]:
        name, payload = event.get("event"), event.get("payload") or {}
        if name == "tasks_added":
            add(payload.get("tasks"))
        elif name == "task_split":
            parent = tasks.get(str(payload.get("task_id")))
            if parent is not None:
                parent.update(status="split", error=payload.get("reason"), utc=event.get("utc"))
            add(payload.get("tasks"), after=str(payload.get("task_id")))
        elif name in ("task_completed", "task_failed"):
            entry = tasks.get(str(payload.get("task_id")))
            if entry is not None:
                entry.update(status="completed" if name == "task_completed" else "failed",
                             attempts=int(payload.get("attempts") or 0),
                             summary=payload.get("summary"), error=payload.get("error"),
                             utc=event.get("utc"))
        elif name == "run_finished":
            status = str(payload.get("status") or "finished")
        if isinstance(payload.get("ledger"), Mapping):
            ledger = payload["ledger"]
        if isinstance(payload.get("model_calls"), int):
            model_calls = payload["model_calls"]
    ordered = [tasks[task_id] for task_id in order]
    work = [t for t in ordered if t["status"] != "split"]
    return {
        "job_id": job_id,
        "started": True,
        "mode": head.get("mode"),
        "objective": head.get("objective"),
        "run_status": status,
        "started_utc": events[0].get("utc"),
        "updated_utc": events[-1].get("utc"),
        "model_calls": model_calls,
        "completed": sum(1 for t in ordered if t["status"] == "completed"),
        "failed": sum(1 for t in ordered if t["status"] == "failed"),
        "total": len(work),
        "split": sum(1 for t in ordered if t["status"] == "split"),
        "tasks": ordered,
        "ledger": ledger if ledger is not None else {"facts": [], "decisions": [],
                                                     "open_questions": [], "results": []},
    }


def plan_reports(root: str | Path) -> Mapping[str, Any] | None:
    """The supervisor's per-model GPU/RAM plan report (hybrid_plans.json), or None."""
    from .paths import resolve_runtime_dir

    path = resolve_runtime_dir(root) / "llamacpp_supervisor" / "hybrid_plans.json"
    try:
        reports = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return reports if isinstance(reports, Mapping) else None


def model_status(reports: Mapping[str, Any] | None, entry: LongModel) -> tuple[str, str | None]:
    """``(status, reason)`` of a configured LONG model from the supervisor's plan report.

    ``degraded`` when its plan was refused or planned below the configured context (the executor
    would then refuse every run on it), ``unknown`` when the supervisor reported nothing for it,
    ``ready`` otherwise.
    """
    if reports is None:
        return "unknown", "no plan report from the supervisor (has it started?)"
    report = reports.get(entry.model)
    if not isinstance(report, Mapping):
        return "unknown", "the supervisor's plan report has no entry for this model"
    if report.get("applied") is False:
        return "degraded", f"plan refused: {report.get('reason') or 'no reason recorded'}"
    context = report.get("context")
    if isinstance(context, int) and not isinstance(context, bool) and context < entry.context:
        return "degraded", (f"planned at a {context}-token context, below the configured "
                            f"{entry.context}")
    return "ready", None


def _plan_refusal(root: str | Path, model: str) -> str:
    """Why the supervisor served ``model`` without its plan, from its hybrid_plans.json report."""
    reports = plan_reports(root)
    if reports is None:
        return "no plan report from the supervisor"
    report = reports.get(model)
    if not isinstance(report, Mapping):
        return "no plan for this model in the supervisor's report"
    if report.get("applied") is False:
        return f"plan refused: {report.get('reason') or 'no reason recorded'}"
    return f"plan applied at context {report.get('context')}; the served model differs"


def _done(runner: ShardRunner | None) -> int:
    return len(runner.state.completed) if runner is not None and runner.state else 0


def _interrupted(model: str, done: int, reason: str) -> dict[str, Any]:
    """A run stopped by its surroundings (no model server, no disk), not by its own work: the job
    ends ``interrupted`` with the reason, and POST /v1/jobs/<id>/resume continues it."""
    return {"status": "interrupted", "answer": "", "model": model, "reason": reason,
            "telemetry": {"run_status": "interrupted", "completed": done}}


class LongWorkloadExecutor:
    """Runs one LONG job with the shard runner; resumable across product restarts."""

    def __init__(self, *, root: str | Path, evidence_dir: Path, client: Any,
                 config: LongConfig, sleep: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic,
                 exact_counting: bool = True):
        if not callable(getattr(client, "count_text_tokens", None)):
            raise LongWorkloadError("the LONG route requires the llama.cpp backend (exact token "
                                    "counts and the GPU/RAM split); select llama.cpp")
        self.root, self.evidence_dir, self.client, self.config = root, evidence_dir, client, config
        self.sleep, self.monotonic = sleep, monotonic  # the runner's clock (a seam for tests)
        self.exact_counting = exact_counting

    def _exact_route(self, run_dir: Path, port: "LlamaModelPort", objective: str, material: str,
                     output_tokens: int, cancel_requested: Callable[[], bool],
                     progress_callback: Callable[[dict[str, Any]], None], model: str) -> Any:
        """Try the exact counting route (D6): an ExactOutcome, or a finished result dict when the
        run was cancelled or its surroundings failed."""
        from .model_client import GenerationCancelled

        def progress(stage: str, detail: str, percent: int) -> None:
            try:
                progress_callback({"stage": stage, "detail": detail, "percent": percent})
            except Exception:
                pass

        counter = ExactCounter(port, run_dir, max_output_tokens=output_tokens,
                               cancel_requested=cancel_requested, progress=progress)
        try:
            return counter.run(objective, material)
        except (GenerationCancelled, ExactCancelled):
            return {"status": "cancelled", "answer": "", "model": model,
                    "reason": "cancelled while counting",
                    "telemetry": {"mode": "exact_counting", "run_status": "cancelled"}}
        except ModelUnavailable as exc:
            return _interrupted(model, 0, (
                f"{exc}. The counting recorded so far is kept; resume the job once the llama.cpp "
                f"supervisor serves {model} again."))
        except OSError as exc:
            return _interrupted(model, 0, (
                f"the LONG run could not write in {run_dir} ({exc}). Free disk space or make the "
                "folder writable, then resume the job."))

    def run(self, job_id: str, text: str, *, cancel_requested: Callable[[], bool],
            progress_callback: Callable[[dict[str, Any]], None],
            model: str | None = None) -> dict[str, Any]:
        from .model_client import ModelClientError
        from .runtime_contracts import InferenceAuthError

        run_dir = self.evidence_dir / "long" / job_id
        run_started = self.monotonic()
        tokenizer_before = _endpoint_stats(self.client)
        checkpoints = run_dir / "checkpoints"
        resuming = checkpoints.is_dir() and any(checkpoints.glob("*.json"))
        requested, text = split_model_directive(text)
        # A resumed run has its chunks in its checkpoints: it must not need the @input file.
        objective, material = parse_request(text, self.root, read_input=not resuming)
        entry = self.config.model(model or requested)
        try:
            context = int(self.client.native_context_length(entry.model))
        except InferenceAuthError:
            raise
        except ModelClientError as exc:
            return _interrupted(entry.model, 0, (
                f"the llama.cpp server did not answer for {entry.model} ({exc}). Start the "
                "llama.cpp supervisor, then resume the job."))
        if context < entry.context:
            raise LongWorkloadError(
                f"{entry.model} is served with a {context}-token context, below the "
                f"{entry.context} the LONG route is configured for: the supervisor did not apply "
                f"its GPU/RAM plan ({_plan_refusal(self.root, entry.model)}). Restart the "
                "supervisor when enough VRAM is free, or lower this model's context in "
                f"{CONFIG_FILE}.")
        port = LlamaModelPort(self.client, entry.model, context, thinking=entry.thinking,
                              cancel_requested=cancel_requested)
        limits = RunLimits(context_tokens=context,
                           ledger_budget_tokens=min(self.config.ledger_budget_tokens,
                                                    context // 4))
        # The answer budget plus the model's reasoning budget: a reasoning model spends the
        # latter before its answer starts, and chunks are sized with the whole reply reserved.
        output_tokens = min(self.config.max_output_tokens, context // 4) + entry.reasoning_tokens
        exact_note = None
        exact_path = run_dir / EXACT_STATE_FILE
        if (self.exact_counting and material is not None and not resuming
                and (exact_path.is_file() or is_countable_objective(objective))):
            outcome = self._exact_route(run_dir, port, objective, material, output_tokens,
                                        cancel_requested, progress_callback, entry.model)
            if isinstance(outcome, dict):
                return outcome
            if outcome.answer is not None:
                return {"status": "completed", "answer": outcome.answer, "model": entry.model,
                        "reason": None,
                        "telemetry": {"mode": "exact_counting", "context": context,
                                      "run_status": "completed", **outcome.telemetry}}
            exact_note = outcome.note
        if material is not None:
            mode: Any = InputShardMode(
                objective=objective, max_output_tokens=output_tokens,
                map_instruction=("Work on the objective using ONLY this part of the input. Report "
                                 "everything in it that bears on the objective."),
                reduce_instruction=("Combine the partial results faithfully, using only the values "
                                    "they report; do not invent."))
            kind = "input_shards"
        else:
            mode = PlanStepMode(objective=objective, max_output_tokens=output_tokens)
            kind = "plan_steps"

        high_water = [1]

        def progress(event: Mapping[str, Any]) -> None:
            done, total = event.get("done"), event.get("total")
            update: dict[str, Any] = {"stage": str(event.get("event") or "running")}
            if isinstance(done, int) and isinstance(total, int) and total > 0:
                # The task list GROWS (plan -> steps, map -> reduce rounds) and the product drops
                # any update whose percent goes backwards, which froze "n of N" after the first
                # task. Reserve one unit for work not yet known and never go backwards, so every
                # current/total update is accepted.
                high_water[0] = max(high_water[0], min(99, int(done * 100 / (total + 1))))
                update.update(current=done, total=total, percent=high_water[0])
            try:
                progress_callback(update)
            except Exception:
                pass

        runner: ShardRunner | None = None
        plan_seconds = 0.0
        try:
            runner = ShardRunner(run_dir, port, limits,
                                 should_stop=cancel_requested, progress=progress,
                                 on_task_done=mode.on_task_done,
                                 validators=getattr(mode, "validators", None),
                                 summary_kinds=mode.summary_kinds,
                                 isolated_kinds=getattr(mode, "isolated_kinds", ()),
                                 split_task=getattr(mode, "split_task", None),
                                 sleep=self.sleep, monotonic=self.monotonic)
            if runner.log.events():
                state = runner.resume()
            else:
                planning = self.monotonic()
                tasks = (mode.plan(runner, material) if material is not None
                         else mode.plan(runner))
                plan_seconds = self.monotonic() - planning
                state = runner.start(objective, kind, tasks)
        except ModelUnavailable as exc:
            return _interrupted(entry.model, _done(runner), (
                f"{exc}. The chunks already done are kept; resume the job once the llama.cpp "
                f"supervisor serves {entry.model} again."))
        except OSError as exc:
            # A full disk or an unwritable evidence folder. The checkpoint chain is written
            # atomically, so everything recorded before the failure is still valid.
            return _interrupted(entry.model, _done(runner), (
                f"the LONG run could not write its checkpoints in {run_dir} ({exc}). Free disk "
                "space or make the folder writable, then resume the job; the chunks already "
                "done are kept."))
        final = mode.final_output(runner, state)
        if state.status == "cancelled":
            status = "cancelled"
        elif final:
            status = "completed"
        else:
            status = "failed"
        gaps = sorted(state.failed)
        if final and material is not None and status == "completed":
            # A live reduce summed correctly but ignored the requested per-part breakdown.
            # Attach the checkpoint summaries (already <= 400 characters), not the full outputs.
            final = _per_part_appendix(final, state)
        if final and exact_note and status == "completed":
            final = final.rstrip() + (
                f"\n\nNote: exact counting was not used ({exact_note}). This answer comes from "
                "map/reduce, so any counts in it are the model's estimate, not computed.")
        if final and gaps and status == "completed":
            # Live: the reduce was told "map-0004: FAILED - name it as a gap" and still answered
            # as if it had seen the whole input. The disclosure must not depend on the model.
            final = final.rstrip() + "\n\n" + _coverage_note(state, gaps)
        return {
            "status": status,
            "answer": final or "",
            "model": entry.model,
            "reason": (None if final else _end_reason(state)),
            "telemetry": {"mode": kind, "context": context, "shards": len(state.tasks),
                          "completed": len(state.completed), "failed": gaps,
                          "coverage_gaps": gaps,
                          "model_calls": state.model_calls, "run_status": state.status,
                          **_timing_telemetry(self.client, tokenizer_before, run_started,
                                              plan_seconds, self.monotonic())},
        }
