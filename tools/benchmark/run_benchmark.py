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
import subprocess
import sys
import threading
import time
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


# --------------------------------------------------------------------------- grading
def grade(task: dict, answer: str, dataset: dict, packet) -> dict:
    """Known-answer grading. No model judges another model's output."""
    low = (answer or "").lower()
    abstained = any(m in low for m in dataset["abstention_markers"])

    missing = [s for s in task["must_contain"] if s.lower() not in low]
    forbidden = [s for s in task["must_not_contain"] if s.lower() in low]

    if task["expect_abstention"]:
        correct = bool(abstained) and not forbidden
    else:
        correct = not missing and not forbidden and bool(low.strip())

    assessment = assess_quick_response(answer, packet, query=task["query"])
    return {
        "correct": correct,
        "abstained": abstained,
        "missing_required": missing,
        "found_forbidden": forbidden,
        "unsupported_claims": len(assessment.unattributed_claims),
        "citation_errors": len(assessment.unknown_citations),
        "acceptance_accepted": assessment.accepted,
        "answer_chars": len(answer or ""),
    }


# --------------------------------------------------------------------------- conditions
def session_for(task_id: str) -> str:
    """One session id per TASK, shared by every condition - the packet is paired."""
    return "bench" + hashlib.sha256(task_id.encode()).hexdigest()[:12]


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
                            evidence=packet, overall_timeout=timeout)
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
    """Neutralise one stage of the DEEP pipeline for an ablation condition."""
    executor._benchmark_disabled_stage = stage


def _harvest(result, calls):
    answer = getattr(result, "answer", None) or ""
    status = getattr(result, "status", None)
    meta = {
        "status": str(getattr(status, "value", status)),
        "reason": getattr(result, "reason", None),
        "model_calls": calls,
        "prompt_tokens": None,
        "completion_tokens": None,
    }
    raw = getattr(result, "raw_records", None) or getattr(result, "raw", None)
    if isinstance(raw, (list, tuple)):
        meta["model_calls"] = len(raw)
        p = c = 0
        seen = False
        for item in raw:
            if not isinstance(item, dict):
                continue
            if "prompt_eval_count" in item:
                p += int(item.get("prompt_eval_count") or 0)
                seen = True
            if "eval_count" in item:
                c += int(item.get("eval_count") or 0)
                seen = True
        if seen:
            meta["prompt_tokens"] = p
            meta["completion_tokens"] = c
    return answer, meta


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
    args = ap.parse_args(argv)

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

    artifact_root = Path(args.out).resolve().parent / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    candidate = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
    tags = sorted({models[k] for k in
                   ("PRIMARY_REASONER", "SYNTHESIZER", "CRITIC", "ADVERSARIAL_CHALLENGER")})

    env = {
        "record_kind": "environment",
        "protocol": "SWS-BENCH-01",
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
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(env) + "\n")
    print(json.dumps({k: env[k] for k in
                      ("candidate_sha", "dataset_sha256", "task_count", "runs_per_cell",
                       "partial")}, indent=2))

    rng = random.Random(args.seed)
    total = len(tasks) * len(conditions) * args.runs
    done = 0

    for run_index in range(args.runs):
        for task in tasks:
            session = session_for(task["id"])
            packet = build_packet(session, dataset, task)
            order = list(conditions)
            rng.shuffle(order)  # counterbalancing: no condition always runs warm
            for condition in order:
                done += 1
                started = time.monotonic()
                record = {
                    "record_kind": "run",
                    "protocol": "SWS-BENCH-01",
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
                answer, meta, error = "", {}, None
                with VramSampler() as vram:
                    try:
                        answer, meta = run_condition(
                            condition, task, dataset, packet, models, client,
                            artifact_root, args.timeout, session, runtime_options)
                    except Exception as exc:  # noqa: BLE001 - recorded, never dropped
                        error = f"{type(exc).__name__}: {exc}"
                    record["peak_vram_mib"] = vram.peak
                    record["vram_method"] = (
                        "nvidia-smi memory.used sampled every 500ms; whole-device, sampled not "
                        "integrated, so a peak between samples is missed"
                        if vram.available else "unavailable on this host")
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                record["error"] = error
                record.update(meta)
                record["grade"] = (grade(task, answer, dataset, packet)
                                   if error is None else None)
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
        print("PARTIAL RUN: this does not satisfy SWS-BENCH-01 and is labelled so in every record.")
    return 0


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
