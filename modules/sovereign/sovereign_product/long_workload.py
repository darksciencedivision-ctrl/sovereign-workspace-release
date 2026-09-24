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
  state home's ``long_inputs`` inbox. The run lives under ``evidence/long/<job id>/``, so a product
  restart resumes it instead of starting over.

LONG requires the llama.cpp backend: exact token counts and the hybrid split are llama.cpp
features, and the operator chose llama.cpp for this path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .gguf_meta import GGUFError, read_gguf
from .memory_planner import GIB, MemoryBudget, PlanRefused, plan_serving
from .paths import resolve_state_home
from .runtime_registry import RuntimeRegistry, hybrid_profile
from .shard_modes import InputShardMode, PlanStepMode
from .shard_runner import RunLimits, ShardRunner

CONFIG_FILE = "long_workload.json"
INBOX_DIRNAME = "long_inputs"
MAX_INPUT_BYTES = 64 * 1024 * 1024
_MATERIAL_SPLIT = re.compile(r"^---[ \t]*$", re.MULTILINE)
_INPUT_REF = re.compile(r"^\s*@input:\s*(?P<name>[A-Za-z0-9._ -]{1,128})\s*$")


class LongWorkloadError(ValueError):
    """The LONG request or configuration cannot run (reported to the operator)."""


@dataclass(frozen=True)
class LongModel:
    model: str
    context: int
    thinking: str = "off"


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
        if item.get("thinking", "off") not in ("off", "on"):
            raise LongWorkloadError(f"{item['model']}: thinking must be 'off' or 'on'")
        models.append(LongModel(item["model"], context, item.get("thinking", "off")))
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
    report: dict[str, dict[str, Any]] = {}
    if vram_bytes is None:
        return {m.model: {"applied": False, "reason": "free VRAM unknown (no nvidia-smi)"}
                for m in config.models}
    budget = MemoryBudget(vram_bytes=int(vram_bytes), ram_bytes=config.ram_budget_gib * GIB,
                          prompt_cache_mib=config.prompt_cache_mib)
    for entry in config.models:
        existing = [p for p in registry.profiles.values() if p.model_id == entry.model]
        if not existing:
            report[entry.model] = {"applied": False, "reason": "model not installed"}
            continue
        try:
            plan = plan_serving(reader(existing[0].model_path), context=entry.context,
                                budget=budget)
        except (GGUFError, PlanRefused, OSError, ValueError) as exc:
            report[entry.model] = {"applied": False, "reason": str(exc)}
            continue
        profile = hybrid_profile(entry.model, plan, thinking_policy=entry.thinking)
        replaced = {p.profile_id for p in existing}
        for profile_id in replaced:
            registry.profiles.pop(profile_id, None)
        registry.add_profile(profile)
        for role_name, role in list(registry.roles.items()):
            if getattr(role, "profile_id", None) in replaced:
                registry.roles[role_name] = type(role)(**{**role.__dict__,
                                                          "profile_id": profile.profile_id})
        report[entry.model] = {"applied": True, "profile": profile.profile_id,
                               **{k: v for k, v in plan.as_dict().items()
                                  if k in ("n_gpu_layers", "n_cpu_moe", "context", "est_vram_gib",
                                           "est_ram_gib", "kv_gib", "notes")}}
    return report


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
        response = self.client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            options={"num_ctx": self.context, "num_predict": max_tokens, "temperature": 0.2},
            think=self.thinking == "on",
            cancel_requested=lambda: should_stop() or self.cancel_requested())
        return str(getattr(response, "text", "") or "")

    def count_tokens(self, text: str) -> int:
        counted = self.client.count_text_tokens(self.model, text)
        # Conservative fallback (one token per byte) - never optimistic.
        return counted if counted is not None else len(text.encode("utf-8"))


# --- the executor ---------------------------------------------------------------------------------

def parse_request(text: str, root: str | Path) -> tuple[str, str | None]:
    """(objective, material or None). Material may be an ``@input: <name>`` inbox reference."""
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
    if reference:
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


class LongWorkloadExecutor:
    """Runs one LONG job with the shard runner; resumable across product restarts."""

    def __init__(self, *, root: str | Path, evidence_dir: Path, client: Any,
                 config: LongConfig):
        if not callable(getattr(client, "count_text_tokens", None)):
            raise LongWorkloadError("the LONG route requires the llama.cpp backend (exact token "
                                    "counts and the GPU/RAM split); select llama.cpp")
        self.root, self.evidence_dir, self.client, self.config = root, evidence_dir, client, config

    def run(self, job_id: str, text: str, *, cancel_requested: Callable[[], bool],
            progress_callback: Callable[[dict[str, Any]], None],
            model: str | None = None) -> dict[str, Any]:
        objective, material = parse_request(text, self.root)
        entry = self.config.model(model)
        context = int(self.client.native_context_length(entry.model))
        port = LlamaModelPort(self.client, entry.model, context, thinking=entry.thinking,
                              cancel_requested=cancel_requested)
        limits = RunLimits(context_tokens=context,
                           ledger_budget_tokens=min(self.config.ledger_budget_tokens,
                                                    context // 4))
        output_tokens = min(self.config.max_output_tokens, context // 4)
        if material is not None:
            mode: Any = InputShardMode(
                objective=objective, max_output_tokens=output_tokens,
                map_instruction=("Work on the objective using ONLY this part of the input. Report "
                                 "everything in it that bears on the objective."),
                reduce_instruction="Combine the partial results faithfully; do not invent.")
            kind = "input_shards"
        else:
            mode = PlanStepMode(objective=objective, max_output_tokens=output_tokens)
            kind = "plan_steps"

        def progress(event: Mapping[str, Any]) -> None:
            done, total = event.get("done"), event.get("total")
            update: dict[str, Any] = {"stage": str(event.get("event") or "running")}
            if isinstance(done, int) and isinstance(total, int) and total > 0:
                update.update(current=done, total=total,
                              percent=max(1, min(99, int(done * 100 / total))))
            try:
                progress_callback(update)
            except Exception:
                pass

        runner = ShardRunner(self.evidence_dir / "long" / job_id, port, limits,
                             should_stop=cancel_requested, progress=progress,
                             on_task_done=mode.on_task_done,
                             validators=getattr(mode, "validators", None),
                             summary_kinds=mode.summary_kinds)
        if runner.log.events():
            state = runner.resume()
        else:
            tasks = mode.plan(runner, material) if material is not None else mode.plan(runner)
            state = runner.start(objective, kind, tasks)
        final = mode.final_output(runner, state)
        if state.status == "cancelled":
            status = "cancelled"
        elif final:
            status = "completed"
        else:
            status = "failed"
        return {
            "status": status,
            "answer": final or "",
            "model": entry.model,
            "reason": (None if final else
                       f"run ended {state.status}; failed shards: {sorted(state.failed)}"),
            "telemetry": {"mode": kind, "context": context, "shards": len(state.tasks),
                          "completed": len(state.completed), "failed": sorted(state.failed),
                          "model_calls": state.model_calls, "run_status": state.status},
        }
