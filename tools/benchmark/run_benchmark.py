#!/usr/bin/env python
"""SWS-BENCH-01 runner - does the DEEP orchestration beat one model call?

SWS-CORRECTIVE-01 workstream 5. Read `PROTOCOL.md` first: the task set, the grading rule, the
primary outcome, the benefit threshold and the regression tolerance are all frozen there, and
none of them may be changed after seeing a result.

Every condition runs the PRODUCT'S OWN executors - `QuickExecutor` and `SemanticDeepExecutor`
from `sovereign_product` - against a real `OllamaClient` and real `EvidencePacket`s. Only the
HTTP service around them is absent. There is no benchmark-only reimplementation of the
orchestration, because measuring a copy would measure the copy.

Run it with the SOVEREIGN venv, from the repository root:

    modules\\sovereign\\.venv\\Scripts\\python.exe tools\\benchmark\\run_benchmark.py --runs 3

Results are written as JSON Lines to --out. Every attempted execution produces a record,
including failures and timeouts; nothing is dropped for being inconvenient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOVEREIGN = REPO / "modules" / "sovereign"
sys.path.insert(0, str(SOVEREIGN))

from sovereign_product.evidence import EvidencePacket, EvidenceSource  # noqa: E402
from sovereign_product.quality import assess_quick_response, build_quick_prompt  # noqa: E402

CONDITIONS = ("A_single", "B_full", "C1_no_critic", "C2_no_verifier")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- environment
def ollama_digests(tags):
    """Immutable digest per model tag where obtainable; unknown stays unknown."""
    out = {}
    for tag in tags:
        out[tag] = None
        try:
            proc = subprocess.run(["ollama", "show", "--json", tag],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode == 0:
                doc = json.loads(proc.stdout)
                out[tag] = {
                    "digest": doc.get("digest"),
                    "quantization": (doc.get("details") or {}).get("quantization_level"),
                    "parameter_size": (doc.get("details") or {}).get("parameter_size"),
                    "context_length": (doc.get("model_info") or {}).get(
                        "general.context_length"),
                }
        except Exception:
            pass
    return out


class VramSampler:
    """Sample total used VRAM every `interval` seconds.

    LIMITATION, recorded with the number: this is a SAMPLE, not an integral, so a peak between
    samples is missed; and it reads the whole device, so anything else on the GPU is included.
    It is reported as an upper-bounded observation, never as this process's consumption.
    """

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._stop = threading.Event()
        self.samples: list[int] = []
        self._thread = None
        self.available = False

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10)
                if proc.returncode == 0:
                    for line in proc.stdout.split():
                        if line.strip().isdigit():
                            self.samples.append(int(line.strip()))
                            break
            except Exception:
                pass

    def __enter__(self):
        try:
            probe = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                                    "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=10)
            self.available = probe.returncode == 0
        except Exception:
            self.available = False
        if self.available:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        return False

    @property
    def peak(self):
        return max(self.samples) if self.samples else None


# --------------------------------------------------------------------------- packets
def build_packet(session_id: str, dataset: dict, task: dict) -> EvidencePacket:
    """The identical packet every condition sees for this task."""
    sources = []
    for sid in task["sources"]:
        text = dataset["sources"][sid]
        sources.append(EvidenceSource(
            source_id=sid,
            kind="project_file",
            locator=f"benchmark/{sid}.txt",
            content_sha256=sha(text),
            snippet_sha256=sha(text),
            snippet=text,
            content_bytes=len(text.encode("utf-8")),
            snippet_bytes=len(text.encode("utf-8")),
            snippet_tokens=max(1, len(text.split())),
            truncated=False,
            metadata={},
        ))
    body = "\n\n".join(f"[source:{s.source_id}]\n{s.snippet}" for s in sources)

    # packet_sha256 is computed with the PRODUCT'S OWN functions over the product's own hash
    # input. `SemanticDeepExecutor` re-derives and re-checks this digest before it will run, so
    # a benchmark that hashed the packet its own way would simply be refused - and a benchmark
    # that loosened the check would no longer be measuring the product.
    from sovereign_product.semantic_deep import _canonical_json, _sha256_bytes, _sha256_text

    max_bytes, max_tokens = 64_000, 16_000
    method = "whitespace (benchmark fixture)"
    hash_input = {
        "session_id": session_id,
        "query_sha256": _sha256_text(task["query"]),
        "sources": [
            {
                "source_id": s.source_id,
                "kind": s.kind,
                "locator": s.locator,
                "content_sha256": s.content_sha256,
                "snippet_sha256": s.snippet_sha256,
            }
            for s in sources
        ],
        "omissions": [],
        "text": body,
        "bounds": {
            "max_bytes": max_bytes,
            "max_tokens": max_tokens,
            "token_count_method": method,
        },
    }
    return EvidencePacket(
        session_id=session_id,
        query_sha256=_sha256_text(task["query"]),
        created_at=utc(),
        sources=tuple(sources),
        omissions=(),
        text=body,
        total_bytes=len(body.encode("utf-8")),
        total_tokens=max(1, len(body.split())),
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        token_count_method=method,
        packet_sha256=_sha256_bytes(_canonical_json(hash_input)),
    )


_NEGATION = re.compile(
    r"\b(not|never|no|n't|cannot|can't|isn't|wasn't|aren't|weren't)\b",
    re.IGNORECASE,
)


def token_is_negated(text: str, token: str) -> bool:
    """True when `token` appears in a window that also contains a negation marker."""
    low = text.lower()
    needle = token.lower()
    start = 0
    while True:
        idx = low.find(needle, start)
        if idx < 0:
            return False
        window = low[max(0, idx - 48): idx + len(needle) + 48]
        if _NEGATION.search(window):
            return True
        start = idx + max(1, len(needle))


def independent_unsupported(task: dict, answer: str, packet) -> int:
    """Source-support / known-answer unsupportedness. Not citation-token presence.

    Counts: forbidden facts even when they carry a real citation; required facts asserted
    under negation; required facts whose cited source text does not contain them.
    """
    count = 0
    text = answer or ""
    low = text.lower()
    packet_text = (getattr(packet, "text", None) or "") if packet is not None else ""
    sources = list(getattr(packet, "sources", ()) or ()) if packet is not None else []
    source_text = {
        s.source_id: (s.snippet or "").lower()
        for s in sources
    }
    for forbidden in task.get("must_not_contain") or []:
        if forbidden.lower() in low:
            count += 1
    if not task.get("expect_abstention"):
        for required in task.get("must_contain") or []:
            if required.lower() not in low:
                continue
            if token_is_negated(text, required):
                count += 1
                continue
            # F-090. The packet body and the product prompt cite sources as [source:<sid>], so the
            # support check must look for that exact token. Matching a bare [<sid>] never hit
            # (`[gf-01]` is not a substring of `[source:gf-01]`), leaving citation-support errors
            # structurally uncounted -- the metric the protocol requires.
            cited_ok = False
            for sid, snippet in source_text.items():
                if required.lower() in snippet and f"[source:{sid}]".lower() in low:
                    cited_ok = True
                    break
            if sources and required.lower() in packet_text.lower() and not cited_ok:
                # Present in the packet but the answer did not cite a source that
                # actually contains it — still a support miss if a citation is present
                # pointing at a different source.
                if re.search(r"\[source:[^\]]+\]", text):
                    for sid, snippet in source_text.items():
                        if f"[source:{sid}]".lower() in low and required.lower() not in snippet:
                            count += 1
                            break
    return count


def grade(task: dict, answer: str, dataset: dict, packet) -> dict:
    """Known-answer grading. No model judges another model's output."""
    low = (answer or "").lower()
    abstained = any(m in low for m in dataset["abstention_markers"])

    missing = [s for s in task["must_contain"] if s.lower() not in low]
    forbidden = [s for s in task["must_not_contain"] if s.lower() in low]
    negated = [
        s for s in task["must_contain"]
        if s.lower() in low and token_is_negated(answer or "", s)
    ]

    if task["expect_abstention"]:
        correct = bool(abstained) and not forbidden
    else:
        correct = not missing and not forbidden and not negated and bool(low.strip())

    assessment = assess_quick_response(answer, packet, query=task["query"])
    return {
        "correct": correct,
        "abstained": abstained,
        "missing_required": missing,
        "found_forbidden": forbidden,
        "negated_required": negated,
        "unattributed_claims": len(assessment.unattributed_claims),
        "unsupported_claims": independent_unsupported(task, answer, packet),
        "citation_errors": len(assessment.unknown_citations),
        "acceptance_accepted": assessment.accepted,
        "answer_chars": len(answer or ""),
    }


# --------------------------------------------------------------------------- conditions
def session_for(run_id: str, task_id: str, condition: str, run_index: int) -> str:
    """Unique per (run, task, condition, repeat). Evidence *content* stays paired by task."""
    raw = f"{run_id}:{task_id}:{condition}:{run_index}"
    return "bench" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def run_condition(condition, task, dataset, packet, models, client, artifact_root, timeout,
                  session, runtime_options):
    """Execute one condition. Returns (answer, meta). Never raises to the caller."""
    from sovereign_product.executors import QuickExecutor
    from sovereign_product.semantic_deep import SemanticDeepExecutor

    if condition == "A_single":
        ex = QuickExecutor(
            client, artifact_root / "quick",
            prompt_builder=build_quick_prompt,
        )
        result = ex.execute(session, task["query"], model=models["PRIMARY_REASONER"],
                            evidence=packet, overall_timeout=timeout,
                            options=runtime_options)
        return _harvest(result, calls=1)

    kwargs = dict(
        member_models=(models["PRIMARY_REASONER"], models["SYNTHESIZER"], models["CRITIC"]),
        critic_model=models["CRITIC"],
        synthesizer_model=models["SYNTHESIZER"],
        verifier_model=models["ADVERSARIAL_CHALLENGER"],
        artifact_root=artifact_root / condition,
        trusted_roots=(artifact_root,),
        # The product's own runtime options, read from the same manifest keys
        # `ProductService._runtime_model_options` reads. Inventing benchmark-specific
        # sampling or context settings would measure something the product does not run.
        base_options=runtime_options,
    )
    ex = SemanticDeepExecutor(SOVEREIGN, client, **kwargs)

    # The ablations disable a stage by making it a no-op, which is what an off-by-default flag
    # would do in the product. Nothing else about the run changes.
    if condition == "C1_no_critic":
        _disable_stage(ex, "critic")
    elif condition == "C2_no_verifier":
        _disable_stage(ex, "verifier")

    result = ex.execute(session, task["query"], evidence=packet, timeout_seconds=timeout)
    return _harvest(result, calls=None)


def _disable_stage(executor, stage: str) -> None:
    """Measurement-only skip of one named DEEP stage. Production defaults stay enabled."""
    executor.set_measurement_skip(stage)


def _harvest(result, calls):
    answer = getattr(result, "answer", None) or ""
    status = getattr(result, "status", None)
    status_value = str(getattr(status, "value", status) or "")
    reason = getattr(result, "reason", None)
    tel = getattr(result, "telemetry", None) or {}
    internal = tel.get("internal_cost") if isinstance(tel, dict) else None
    if not isinstance(internal, dict):
        internal = {}
    model_calls = internal.get("model_calls")
    if model_calls is None:
        model_calls = tel.get("turn_count") if isinstance(tel, dict) else None
    if model_calls is None:
        model_calls = calls
    prompt_tokens = None
    completion_tokens = None
    if isinstance(tel, dict):
        if tel.get("prompt_eval_count") is not None:
            prompt_tokens = tel.get("prompt_eval_count")
        if tel.get("eval_count") is not None:
            completion_tokens = tel.get("eval_count")
    if prompt_tokens is None and internal.get("prompt_eval_count") is not None:
        prompt_tokens = internal.get("prompt_eval_count")
    if completion_tokens is None and internal.get("eval_count") is not None:
        completion_tokens = internal.get("eval_count")
    # R10. A transport/runtime timeout is a STRUCTURED terminal status, not a substring of the
    # reason prose. The old `"timeout" in reason.lower()` mis-classified a normal rejection whose
    # task/critique merely discussed timeout configuration as an execution timeout.
    timed_out = status_value in {"timeout", "TIMEOUT"}
    error = (reason or "timeout") if timed_out else None
    meta = {
        "status": status_value,
        "reason": reason,
        # R09. A structured flag the analyzer can count independently of grade availability.
        "timed_out": timed_out,
        "model_calls": model_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    if not answer:
        artifacts = getattr(result, "artifacts", None) or {}
        result_rel = artifacts.get("result")
        if result_rel:
            try:
                path = Path(result_rel)
                if path.is_file():
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    answer = doc.get("answer") or doc.get("candidate") or answer
            except (OSError, json.JSONDecodeError, TypeError):
                pass
    return answer, meta, error


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=3,
                    help="runs per task per condition (protocol says 3)")
    ap.add_argument("--out", default=str(HERE / "results" / "runs.jsonl"))
    ap.add_argument("--tasks", default=None,
                    help="comma-separated task ids, for a smoke run. A partial run is labelled "
                         "PARTIAL in its own records and cannot be reported as the protocol.")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--seed", type=int, default=20260908)
    ap.add_argument("--run-id", default=None,
                    help="unique id for this run set; generated if omitted")
    ap.add_argument("--resume", action="store_true",
                    help="append to an existing compatible --out; refuse overwrite otherwise")
    args = ap.parse_args(argv)

    out_path = Path(args.out).resolve()
    if out_path.exists() and not args.resume:
        print(f"refusing to overwrite existing output: {out_path}", file=sys.stderr)
        print("pass --resume for a compatible continuation, or a new --out path",
              file=sys.stderr)
        return 2

    dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    tasks = dataset["tasks"]
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",")}
        tasks = [t for t in tasks if t["id"] in wanted]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    partial = bool(args.tasks) or len(conditions) != len(CONDITIONS) or args.runs < 3

    manifest = json.loads((SOVEREIGN / "SYSTEM_MANIFEST.json").read_text(encoding="utf-8"))
    models = manifest["MODELS"]
    runtime = manifest.get("RUNTIME") or {}
    runtime_options = {
        "num_ctx": runtime["CONTEXT_WINDOW"],
        "num_predict": runtime["MAX_OUTPUT_TOKENS"],
    }

    from sovereign_product.model_client import OllamaClient
    client = OllamaClient()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or ("run-" + uuid.uuid4().hex[:12])
    lock_path = out_path.with_name(out_path.name + ".lock")
    existing_cells: set[tuple[str, str, int]] = set()
    existing_env = None
    if out_path.exists():
        if not args.resume:
            print(f"refusing to overwrite existing output: {out_path}", file=sys.stderr)
            print("pass --resume for a compatible continuation, or a new --out path",
                  file=sys.stderr)
            return 2
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("record_kind") == "environment":
                existing_env = rec
            elif rec.get("record_kind") == "run":
                existing_cells.add((rec["task_id"], rec["condition"], rec["run_index"]))
    else:
        try:
            fd = os.open(str(out_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            print(f"refusing to race on existing output: {out_path}", file=sys.stderr)
            return 2
    if lock_path.exists():
        print(f"another benchmark holds {lock_path}", file=sys.stderr)
        return 2
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, f"{os.getpid()} {utc()}\n".encode("utf-8"))
        finally:
            os.close(fd)
    except FileExistsError:
        print(f"another benchmark holds {lock_path}", file=sys.stderr)
        return 2
    artifact_root = out_path.parent / run_id / "artifacts"

    candidate = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
    tags = sorted({models[k] for k in
                   ("PRIMARY_REASONER", "SYNTHESIZER", "CRITIC", "ADVERSARIAL_CHALLENGER")})

    env = {
        "record_kind": "environment",
        "protocol": "SWS-BENCH-02",
        "run_id": run_id,
        "partial": partial,
        "utc": utc(),
        "candidate_sha": candidate,
        "dataset_sha256": dataset["dataset_sha256"],
        "sources_sha256": dataset["sources_sha256"],
        "harness_sha256": sha(Path(__file__).read_text(encoding="utf-8")),
        "protocol_sha256": sha((HERE / "PROTOCOL.md").read_text(encoding="utf-8")),
        "runs_per_cell": args.runs,
        "conditions": conditions,
        "task_count": len(tasks),
        "timeout_s": args.timeout,
        "models": models,
        "model_details": ollama_digests(tags),
        "sampling": "product defaults from SYSTEM_MANIFEST RUNTIME; no benchmark override",
        "runtime_options": runtime_options,
        "tool_access": "none - these routes call models over evidence text and execute nothing",
        "hardware": {
            "os": f"{os.name} {sys.platform}",
            "cpu_count": os.cpu_count(),
            "gpu": _gpu_name(),
        },
        "cache_policy": ("ollama keeps a model resident after use; condition order is permuted "
                         "per (task, run) as the control, and residency is reported as a "
                         "limitation rather than eliminated"),
        "seed": args.seed,
    }
    try:
        if existing_env is not None:
            for key in ("dataset_sha256", "sources_sha256", "harness_sha256", "protocol_sha256",
                        "candidate_sha", "runs_per_cell"):
                if existing_env.get(key) != env.get(key):
                    print(f"resume refused: {key} changed", file=sys.stderr)
                    return 2
            if list(existing_env.get("conditions") or []) != conditions:
                print("resume refused: conditions changed", file=sys.stderr)
                return 2
            run_id = existing_env.get("run_id") or run_id
            env["run_id"] = run_id
            artifact_root = out_path.parent / run_id / "artifacts"
        else:
            with out_path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(env) + "\n")
        artifact_root.mkdir(parents=True, exist_ok=True)
        print(json.dumps({k: env[k] for k in
                          ("run_id", "candidate_sha", "dataset_sha256", "task_count",
                           "runs_per_cell", "partial")}, indent=2))

        rng = random.Random(args.seed)
        total = len(tasks) * len(conditions) * args.runs
        done = 0
        for run_index in range(args.runs):
            for task in tasks:
                order = list(conditions)
                rng.shuffle(order)
                for condition in order:
                    done += 1
                    cell = (task["id"], condition, run_index)
                    if cell in existing_cells:
                        print(f"[{done:>4}/{total}] skip {task['id']:<6} {condition:<14} "
                              f"(already recorded)")
                        continue
                    session = session_for(run_id, task["id"], condition, run_index)
                    packet = build_packet(session, dataset, task)
                    started = time.monotonic()
                    record = {
                        "record_kind": "run",
                        "protocol": "SWS-BENCH-02",
                        "run_id": run_id,
                        "partial": partial,
                        "utc": utc(),
                        "run_index": run_index,
                        "task_id": task["id"],
                        "category": task["category"],
                        "condition": condition,
                        "order_position": order.index(condition),
                        "candidate_sha": candidate,
                        "dataset_sha256": dataset["dataset_sha256"],
                    }
                    answer, meta, harvested_error = "", {}, None
                    error = None
                    with VramSampler() as vram:
                        try:
                            harvested = run_condition(
                                condition, task, dataset, packet, models, client,
                                artifact_root, args.timeout, session, runtime_options)
                            if len(harvested) == 3:
                                answer, meta, harvested_error = harvested
                            else:
                                answer, meta = harvested
                        except Exception as exc:  # noqa: BLE001 - recorded, never dropped
                            error = f"{type(exc).__name__}: {exc}"
                        record["peak_vram_mib"] = vram.peak
                        record["vram_method"] = (
                            "nvidia-smi memory.used sampled every 500ms; whole-device, sampled not "
                            "integrated, so a peak between samples is missed"
                            if vram.available else "unavailable on this host")
                    if error is None:
                        error = harvested_error
                    record["elapsed_s"] = round(time.monotonic() - started, 3)
                    record["error"] = error
                    record.update(meta)
                    record["grade"] = grade(task, answer, dataset, packet)
                    record["answer_sha256"] = sha(answer) if answer else None
                    record["answer"] = answer[:4000]

                    with out_path.open("a", encoding="utf-8", newline="\n") as fh:
                        fh.write(json.dumps(record) + "\n")

                    verdict = "ERR" if error else ("OK " if record["grade"]["correct"] else "no ")
                    print(f"[{done:>4}/{total}] {verdict} {task['id']:<6} {condition:<14} "
                          f"{record['elapsed_s']:>7.1f}s"
                          + (f"  {error[:80]}" if error else ""))

        print(f"\nwrote {out_path}")
        if partial:
            print("PARTIAL RUN: this does not satisfy SWS-BENCH-02 and is labelled so in every record.")
        return 0
    finally:
        try:
            if lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass


def _gpu_name():
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                               "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


if __name__ == "__main__":
    sys.exit(main())
