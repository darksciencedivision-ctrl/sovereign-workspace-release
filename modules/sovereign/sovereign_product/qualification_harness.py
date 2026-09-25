"""SW-27 measurement harness: drive a RUNNING SOVEREIGN product end-to-end and record what happened.

Every measurement goes through the product's own HTTP API (``/v1/sessions``, ``/v1/message``,
``/v1/jobs/<id>``, ``/v1/jobs/<id>/cancel``) - routing, evidence, the model client, the job workers
and the store all included - never a direct model call. Scenarios, per profile ladder:

* ``quick_cold``   QUICK right after the profile's models are unloaded (Ollama keep_alive=0); for
                   other backends the first request of the run is recorded as cold.
* ``quick_warm``   QUICK with varied prompts, ``repetitions`` times.
* ``context``      QUICK over an increasing input context (profile ladder), ``repetitions`` each.
* ``concurrency``  N sessions submitting at once, per ladder level.
* ``cancel``       a job cancelled mid-flight; records cancel-to-terminal latency.
* ``deep``         DEEP runs (the adversarial slate: several models, i.e. model swaps).
* ``long_plan`` / ``long_input``  (LONG profiles, ``run_long_qualification``) sharded-inference
                   jobs on the profile's big model: plan steps, then map/reduce over each
                   ``ladder.input_tokens`` size via the ``long_inputs`` inbox; records shards,
                   chunks per hour and cold vs warm model load.

A background sampler records peak GPU memory (nvidia-smi, when present) and peak system RAM in use
(GlobalMemoryStatusEx). Stdlib only. Token counts are approximate (4 characters per token) for the
input ladder; output tokens come from the product's own job metrics.
"""

from __future__ import annotations

import ctypes
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .qualification import RESULTS_SCHEMA

CHARS_PER_TOKEN = 4
TERMINAL = {"completed", "failed", "rejected", "cancelled", "interrupted"}
VARIED_PROMPTS = (
    "In two sentences, what is the difference between latency and throughput?",
    "List three practical ways to reduce memory use in a Python service.",
    "Explain what a write-ahead log is to a new engineer, briefly.",
    "Give a one-paragraph summary of why load testing should use realistic data.",
    "What are two risks of running a local model with too large a context window?",
)
_FILLER = ("Operations note {i}: the batch finished at step {i} with {j} records processed, "
           "{k} warnings, and a checksum ending in {h:04x}. ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def context_prompt(target_tokens: int) -> str:
    """A deterministic prompt of roughly ``target_tokens`` input tokens plus a question about it."""
    question = ("\n\nUsing only the notes above, state the step with the most warnings and "
                "its record count, in one sentence.")
    budget = max(0, target_tokens * CHARS_PER_TOKEN - len(question))
    parts, size, i = [], 0, 0
    while size < budget:
        line = _FILLER.format(i=i, j=(i * 37) % 1000, k=(i * 11) % 17, h=(i * 2654435761) % 65536)
        parts.append(line)
        size += len(line)
        i += 1
    return "".join(parts)[:budget] + question


class ProductClient:
    """Minimal JSON client for the product API (loopback only)."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: Mapping[str, Any] | None = None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read() or b"{}")
            except ValueError:
                payload = {}
            return exc.code, payload

    def health(self) -> dict[str, Any]:
        return self._call("GET", "/v1/health")[1]

    def new_session(self, title: str) -> str:
        status, payload = self._call("POST", "/v1/sessions", {"title": title[:200]})
        if status != 201:
            raise RuntimeError(f"session create failed ({status}): {payload}")
        return payload["session"]["session_id"]

    def submit(self, session_id: str, text: str, route: str) -> tuple[int, dict[str, Any]]:
        return self._call("POST", "/v1/message",
                          {"session_id": session_id, "input": text, "route_override": route})

    def job(self, job_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v1/jobs/{job_id}")[1]

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/jobs/{job_id}/cancel", {})[1]


def _job_id(payload: Mapping[str, Any]) -> str | None:
    for key in ("job_id",):
        if isinstance(payload.get(key), str):
            return payload[key]
    job = payload.get("job")
    if isinstance(job, Mapping) and isinstance(job.get("job_id"), str):
        return job["job_id"]
    return None


def run_job(client: ProductClient, text: str, route: str, *, timeout: float,
            cancel_after: float | None = None, clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep, poll: float = 0.5,
            on_job: Callable[[Mapping[str, Any]], None] | None = None) -> dict[str, Any]:
    """Submit one message end-to-end and wait for its job to finish (or cancel it)."""
    session = client.new_session(f"qualification {route}")
    started = clock()
    status_code, payload = client.submit(session, text, route)
    record: dict[str, Any] = {"route": route, "input_chars": len(text),
                              "submitted_utc": _utc_now(), "http_status": status_code}
    job_id = _job_id(payload)
    if status_code >= 400 or job_id is None:
        record.update(status="failed", error=str(payload.get("error") or payload)[:500],
                      latency_seconds=clock() - started)
        return record
    record["job_id"] = job_id
    cancel_sent = None
    job: dict[str, Any] = payload if payload.get("status") in TERMINAL else {}
    while str(job.get("status")) not in TERMINAL:
        if clock() - started > timeout:
            client.cancel(job_id)
            record.update(status="timeout", latency_seconds=clock() - started)
            return record
        if cancel_after is not None and cancel_sent is None and clock() - started >= cancel_after:
            client.cancel(job_id)
            cancel_sent = clock()
        sleep(poll)
        job = client.job(job_id)
        if on_job is not None:
            on_job(job)
    finished = clock()
    record["status"] = str(job.get("status"))
    record["latency_seconds"] = finished - started
    metrics = job.get("metrics") if isinstance(job.get("metrics"), Mapping) else {}
    if isinstance(metrics.get("tokens"), int):
        record["tokens"] = metrics["tokens"]
    if isinstance(metrics.get("elapsed_seconds"), (int, float)):
        record["job_elapsed_seconds"] = metrics["elapsed_seconds"]
    if job.get("error"):
        record["error"] = str(job["error"])[:500]
    if cancel_sent is not None:
        record["cancel_latency_seconds"] = finished - cancel_sent
    return record


class ResourceSampler:
    """Peak GPU memory (nvidia-smi) and peak system RAM in use, sampled once a second."""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.peak_vram_mib: int | None = None
        self.peak_ram_used_mib: int | None = None
        self.gpu: dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="qual-sampler")
        self._nvsmi = shutil.which("nvidia-smi")

    def _sample_gpu(self) -> None:
        if not self._nvsmi:
            return
        try:
            out = subprocess.run([self._nvsmi, "--query-gpu=name,memory.total,memory.used",
                                  "--format=csv,noheader,nounits"], capture_output=True,
                                 text=True, timeout=5).stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError):
            return
        if out:
            name, total, used = [p.strip() for p in out[0].split(",")[:3]]
            self.gpu = {"name": name, "memory_total_mib": int(float(total))}
            self.peak_vram_mib = max(self.peak_vram_mib or 0, int(float(used)))

    def _sample_ram(self) -> None:
        if sys.platform != "win32":
            return

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            used = (status.ullTotalPhys - status.ullAvailPhys) // (1024 * 1024)
            self.peak_ram_used_mib = max(self.peak_ram_used_mib or 0, int(used))
            self.ram_total_mib = int(status.ullTotalPhys // (1024 * 1024))

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample_gpu()
            self._sample_ram()
            self._stop.wait(self.interval)

    def __enter__(self) -> "ResourceSampler":
        self._sample_gpu()
        self._sample_ram()
        self.baseline = {"vram_mib": self.peak_vram_mib, "ram_used_mib": self.peak_ram_used_mib}
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def report(self) -> dict[str, Any]:
        return {"peak_vram_mib": self.peak_vram_mib,
                "peak_system_ram_used_mib": self.peak_ram_used_mib,
                "baseline": getattr(self, "baseline", {}),
                "ram_total_mib": getattr(self, "ram_total_mib", None),
                "note": "system-wide peaks sampled once a second during the run"}


LONG_OBJECTIVE_PLAN = ("Write a short, practical checklist (at most 6 items) for verifying that a "
                       "nightly batch job finished correctly. Use at most 3 plan steps.")
LONG_OBJECTIVE_INPUT = ("Using only the notes, state the step with the most warnings and its "
                        "record count, and how many notes report 16 warnings.")


def llama_loaded_models(client: ProductClient) -> list[str] | None:
    """Models the product reports resident in llama.cpp (``/v1/self-state``), or None if unknown."""
    try:
        state = client._call("GET", "/v1/self-state")[1]
    except OSError:
        return None
    stack = [state]
    while stack:
        node = stack.pop()
        if isinstance(node, Mapping):
            if node.get("service") == "llama.cpp" and isinstance(node.get("loaded_models"), list):
                return [str(m) for m in node["loaded_models"]]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def run_long_job(client: ProductClient, text: str, *, timeout: float,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, poll: float = 5.0) -> dict[str, Any]:
    """One LONG job end-to-end; also records the shard count from the job's progress."""
    shards: dict[str, int | None] = {"total": None, "done": None}

    def watch(job: Mapping[str, Any]) -> None:
        progress = job.get("progress") if isinstance(job.get("progress"), Mapping) else {}
        for key, field in (("total", "total"), ("done", "current")):
            value = progress.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                shards[key] = max(shards[key] or 0, value)

    record = run_job(client, text, "LONG", timeout=timeout, clock=clock, sleep=sleep, poll=poll,
                     on_job=watch)
    record["shards"] = shards["total"]
    if record.get("status") == "completed" and shards["total"]:
        record["shards_done"] = shards["total"]  # a completed run finished every shard
    else:
        record["shards_done"] = shards["done"]
    latency = record.get("latency_seconds")
    if record.get("status") == "completed" and shards["total"] and latency:
        record["chunks_per_hour"] = shards["total"] * 3600.0 / latency
    return record


def run_long_qualification(profile: Mapping[str, Any], *, base_url: str, inbox_dir: Any,
                           repetitions: int | None = None, job_timeout: float = 4 * 3600.0,
                           poll: float = 5.0,
                           log: Callable[[str], None] = lambda m: print(m, file=sys.stderr,
                                                                        flush=True)
                           ) -> dict[str, Any]:
    """Qualify a LONG (sharded inference) profile end-to-end through the product.

    Per rung of ``ladder.input_tokens``: 0 = agentic plan steps (objective only); N = map/reduce
    over ~N tokens of material, placed in the state home's ``long_inputs`` inbox (the message
    size cap is far below a LONG input) and referenced with ``@input:``. Every job names the
    profile's model with ``@model:``. Records end-to-end time, shards and chunks per hour, peak
    VRAM/RAM, and whether the model was resident when the job was submitted (cold vs warm load).
    """
    from pathlib import Path

    client = ProductClient(base_url)
    health = client.health()
    reps = repetitions or int(profile["ladder"]["repetitions"])
    model = str(profile["primary_model"])
    inbox = Path(inbox_dir)
    runs: list[dict[str, Any]] = []
    started = _utc_now()
    with ResourceSampler() as sampler:
        for step in profile["ladder"]["input_tokens"]:
            text = f"@model: {model}\n"
            if step == 0:
                text += LONG_OBJECTIVE_PLAN
                scenario = "long_plan"
            else:
                name = f"qualification-{int(step)}.txt"
                inbox.mkdir(parents=True, exist_ok=True)
                (inbox / name).write_text(context_prompt(int(step)), encoding="utf-8")
                text += f"{LONG_OBJECTIVE_INPUT}\n---\n@input: {name}"
                scenario = "long_input"
            for _ in range(reps):
                loaded = llama_loaded_models(client)
                result = run_long_job(client, text, timeout=job_timeout, poll=poll)
                result.update(scenario=scenario, input_tokens=int(step), model=model,
                              cold=None if loaded is None else model not in loaded)
                runs.append(result)
                log(f"[{scenario}] input~{step} cold={result['cold']} -> "
                    f"{result.get('status')} {result.get('latency_seconds', 0):.0f}s "
                    f"shards={result.get('shards')} chunks/h={result.get('chunks_per_hour')}")
    return {
        "schema": RESULTS_SCHEMA,
        "profile": profile["id"],
        "kind": "long",
        "started_utc": started,
        "finished_utc": _utc_now(),
        "base_url": base_url,
        "hardware": {"platform": platform.platform(), "machine": platform.machine(),
                     "processor": platform.processor(), "gpu": sampler.gpu},
        "runtime": {"backend": profile["backend"], "primary_model": model,
                    "product_version": health.get("product_version"),
                    "worker_count": health.get("worker_count"),
                    "long_route_ready": (health.get("routes") or {}).get("LONG")},
        "repetitions": reps,
        "resources": sampler.report(),
        "runs": runs,
    }


def slate_models(slate: Any) -> set[str]:
    """Every model named in the product's DEEP slate (critic/synthesizer/verifier/members)."""
    if not isinstance(slate, Mapping):
        return set()
    names = {slate.get(key) for key in ("critic", "synthesizer", "verifier")}
    for member in slate.get("members") or []:
        if isinstance(member, Mapping):
            names.add(member.get("model"))
    return {name for name in names if isinstance(name, str) and name.strip()}


def unload_ollama_models(ollama_url: str, models: list[str]) -> list[str]:
    unloaded = []
    for model in models:
        body = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
        request = urllib.request.Request(ollama_url.rstrip("/") + "/api/generate", data=body,
                                         method="POST")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=60):
                unloaded.append(model)
        except OSError:
            continue
    return unloaded


def run_qualification(profile: Mapping[str, Any], *, base_url: str, ollama_url: str,
                      repetitions: int | None = None, job_timeout: float = 1800.0,
                      include_deep: bool = True, max_context: int | None = None,
                      log: Callable[[str], None] = lambda m: print(m, file=sys.stderr, flush=True)
                      ) -> dict[str, Any]:
    client = ProductClient(base_url)
    health = client.health()
    reps = repetitions or int(profile["ladder"]["repetitions"])
    runs: list[dict[str, Any]] = []
    started = _utc_now()

    def record(scenario: str, result: dict[str, Any], **extra: Any) -> None:
        result.update(scenario=scenario, **extra)
        runs.append(result)
        log(f"[{scenario}] {extra} -> {result.get('status')} "
            f"{result.get('latency_seconds', 0):.1f}s tokens={result.get('tokens')}")

    with ResourceSampler() as sampler:
        backend = str(profile["backend"]).lower()
        models = sorted(slate_models(health.get("deep_model_slate")) | {profile["primary_model"]})
        cold_note = "first request of the run"
        if backend == "ollama":
            unload_ollama_models(ollama_url, models)
            cold_note = "after unloading the profile's models (keep_alive=0)"
        record("quick_cold", run_job(client, VARIED_PROMPTS[0], "QUICK", timeout=job_timeout),
               cold=True, note=cold_note)
        for i in range(reps):
            record("quick_warm", run_job(client, VARIED_PROMPTS[i % len(VARIED_PROMPTS)],
                                         "QUICK", timeout=job_timeout), cold=False)
        for step in profile["ladder"]["context_tokens"]:
            if max_context is not None and step > max_context:
                log(f"[context] {step} skipped (above --max-context {max_context})")
                break
            failures = 0
            for _ in range(reps):
                result = run_job(client, context_prompt(int(step * 0.8)), "QUICK",
                                 timeout=job_timeout)
                failures += result.get("status") != "completed"
                record("context", result, context_tokens=step)
            if failures == reps:
                log(f"[context] every run at {step} failed; ladder stops")
                break
        for level in profile["ladder"]["concurrency"]:
            for _ in range(max(1, reps // level)):
                with ThreadPoolExecutor(max_workers=level) as pool:
                    futures = [pool.submit(run_job, ProductClient(base_url),
                                           VARIED_PROMPTS[(k + level) % len(VARIED_PROMPTS)],
                                           "QUICK", timeout=job_timeout) for k in range(level)]
                    for future in futures:
                        record("concurrency", future.result(), concurrency=level)
        for _ in range(max(1, reps // 2)):
            record("cancel", run_job(client, context_prompt(2000), "QUICK",
                                     timeout=job_timeout, cancel_after=3.0))
        if include_deep:
            for i in range(max(1, reps // 3)):
                record("deep", run_job(client, VARIED_PROMPTS[(i + 2) % len(VARIED_PROMPTS)],
                                       "DEEP", timeout=job_timeout))

    return {
        "schema": RESULTS_SCHEMA,
        "profile": profile["id"],
        "started_utc": started,
        "finished_utc": _utc_now(),
        "base_url": base_url,
        "hardware": {"platform": platform.platform(), "machine": platform.machine(),
                     "processor": platform.processor(), "gpu": sampler.gpu},
        "runtime": {"backend": profile["backend"], "primary_model": profile["primary_model"],
                    "num_ctx": ((health.get("qualification") or {}).get("config") or {}).get(
                        "num_ctx"),
                    "num_predict": ((health.get("qualification") or {}).get("config") or {}).get(
                        "num_predict"),
                    "deep_model_slate": health.get("deep_model_slate"),
                    "product_version": health.get("product_version"),
                    "worker_count": health.get("worker_count"),
                    "qualification_at_start": health.get("qualification")},
        "repetitions": reps,
        "resources": sampler.report(),
        "runs": runs,
    }
