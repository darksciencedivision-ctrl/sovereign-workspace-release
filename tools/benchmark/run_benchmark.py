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
class OutputLock:
    """Exclusive ownership of a benchmark output, backed by an OS file lock.

    Windows: CreateFileW with dwShareMode=0. The open handle IS the lock; the OS
    releases it on crash. This process never unlinks a lock file (OPEN_ALWAYS
    reuses the sibling) and never closes a handle it does not own.

    PID text in the lock file is diagnostic only and is never used to decide
    reclaim — check-then-unlink races and PID reuse are therefore not part of
    the protocol.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fd = None
        self.owner_pid = os.getpid()

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> bool:
        if self._fd is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            return self._acquire_windows()
        return self._acquire_posix()

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"another benchmark holds {self.path}")
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def _write_owner(self, fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, f"{self.owner_pid} {utc()}\n".encode("utf-8"))
        os.fsync(fd)

    def _acquire_windows(self) -> bool:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        generic_read = 0x80000000
        generic_write = 0x40000000
        file_share_none = 0
        open_always = 4
        file_attribute_normal = 0x80
        invalid_handle = ctypes.c_void_p(-1).value

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file_w = k32.CreateFileW
        create_file_w.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        create_file_w.restype = wintypes.HANDLE
        close_handle = k32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        k32.SetLastError(0)
        handle = create_file_w(
            str(self.path),
            generic_read | generic_write,
            file_share_none,
            None,
            open_always,
            file_attribute_normal,
            None,
        )
        hid = int(handle) if handle is not None else invalid_handle
        if handle is None or hid in (invalid_handle, -1):
            return False
        try:
            fd = msvcrt.open_osfhandle(hid, os.O_RDWR)
        except OSError:
            close_handle(handle)
            return False
        try:
            self._write_owner(fd)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def _acquire_posix(self) -> bool:
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            os.close(fd)
            return False
        try:
            self._write_owner(fd)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True


def _git(repo: Path, args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, proc.stdout


def collect_candidate_identity(repo: Path, manifest_path: Path, models) -> dict:
    """Exact candidate identity: HEAD bytes, dirty tree contents, effective models.

    A dirty boolean alone is not identity. A failed git command does not imply a
    clean candidate — identity_uncertain is set and worktree_dirty is True.
    """
    head_rc, head_out = _git(repo, ["rev-parse", "HEAD"])
    status_rc, status_out = _git(repo, ["status", "--porcelain"])
    git_head_ok = head_rc == 0 and bool(head_out.strip())
    git_status_ok = status_rc == 0
    porcelain = status_out if git_status_ok else ""
    dirty = True if not git_status_ok else bool(porcelain.strip())
    manifest_bytes = manifest_path.read_bytes()
    status_sha = sha(porcelain) if git_status_ok else None
    dirty_paths = []
    if git_status_ok:
        for line in porcelain.splitlines():
            if line.strip():
                dirty_paths.append(line[3:] if len(line) >= 3 else line.strip())
    return {
        "git_head": head_out.strip() if git_head_ok else None,
        "git_head_ok": git_head_ok,
        "worktree_dirty": dirty,
        "git_status_ok": git_status_ok,
        "worktree_status_sha256": status_sha,
        "dirty_paths": dirty_paths if git_status_ok else None,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "models": models,
        "identity_uncertain": not (git_head_ok and git_status_ok),
    }


RESUME_IDENTITY_KEYS = (
    "dataset_sha256", "sources_sha256", "harness_sha256", "protocol_sha256",
    "candidate_sha", "worktree_status_sha256", "manifest_sha256",
    "runs_per_cell", "protocol",
)


def load_existing_output(out_path: Path) -> tuple[dict | None, set, str | None]:
    """Parse an existing jsonl. Returns (env, cells, error_reason)."""
    try:
        text = out_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, set(), f"resume refused: cannot read output ({exc})"
    if not text.strip():
        return None, set(), "resume refused: existing output is empty"
    env = None
    cells: set[tuple[str, str, int]] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return None, set(), f"resume refused: malformed JSON on line {lineno}"
        if not isinstance(rec, dict):
            return None, set(), f"resume refused: non-object record on line {lineno}"
        kind = rec.get("record_kind")
        if kind == "environment":
            env = rec
        elif kind == "run":
            try:
                cells.add((rec["task_id"], rec["condition"], int(rec["run_index"])))
            except (KeyError, TypeError, ValueError):
                return None, set(), f"resume refused: incomplete run record on line {lineno}"
        elif kind == "aborted":
            return None, set(), "resume refused: prior run aborted; use a new --out path"
        else:
            return None, set(), f"resume refused: unknown record_kind on line {lineno}"
    if env is None:
        return None, set(), "resume refused: no environment record"
    return env, cells, None


def resume_incompatible(existing_env: dict, env: dict, conditions: list[str]) -> str | None:
    for key in RESUME_IDENTITY_KEYS:
        if existing_env.get(key) != env.get(key):
            return f"resume refused: {key} changed"
    if list(existing_env.get("conditions") or []) != conditions:
        return "resume refused: conditions changed"
    if existing_env.get("models") != env.get("models"):
        return "resume refused: models changed"
    if existing_env.get("runtime_options") != env.get("runtime_options"):
        return "resume refused: runtime_options changed"
    return None


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
    lock_path = out_path.with_name(out_path.name + ".lock")
    lock = OutputLock(lock_path)
    if not lock.acquire():
        print(f"another benchmark holds {lock_path}", file=sys.stderr)
        return 2

    try:
        return _run_with_lock(args, out_path, created_empty_holder := [])
    finally:
        if created_empty_holder:
            leftover = created_empty_holder[0]
            try:
                if leftover.exists() and leftover.stat().st_size == 0:
                    leftover.unlink()
            except OSError:
                pass
        lock.release()


def _run_with_lock(args, out_path: Path, created_empty_holder: list) -> int:
    if out_path.exists() and not args.resume:
        print(f"refusing to overwrite existing output: {out_path}", file=sys.stderr)
        print("pass --resume for a compatible continuation, or a new --out path",
              file=sys.stderr)
        return 2

    existing_env = None
    existing_cells: set[tuple[str, str, int]] = set()
    if out_path.exists():
        existing_env, existing_cells, err = load_existing_output(out_path)
        if err:
            print(err, file=sys.stderr)
            return 2
    else:
        try:
            fd = os.open(str(out_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            print(f"refusing to race on existing output: {out_path}", file=sys.stderr)
            return 2
        created_empty_holder.append(out_path)

    try:
        dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"setup failed: dataset ({exc})", file=sys.stderr)
        return 2
    tasks = dataset["tasks"]
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",")}
        tasks = [t for t in tasks if t["id"] in wanted]
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    partial = bool(args.tasks) or len(conditions) != len(CONDITIONS) or args.runs < 3

    manifest_path = SOVEREIGN / "SYSTEM_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        models = manifest["MODELS"]
        runtime = manifest.get("RUNTIME") or {}
        runtime_options = {
            "num_ctx": runtime["CONTEXT_WINDOW"],
            "num_predict": runtime["MAX_OUTPUT_TOKENS"],
        }
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"setup failed: manifest ({exc})", file=sys.stderr)
        return 2

    identity = collect_candidate_identity(REPO, manifest_path, models)
    candidate = identity["git_head"] if identity["git_head_ok"] else "UNKNOWN"
    run_id = args.run_id or ("run-" + uuid.uuid4().hex[:12])
    tags = sorted({models[k] for k in
                   ("PRIMARY_REASONER", "SYNTHESIZER", "CRITIC", "ADVERSARIAL_CHALLENGER")})

    env = {
        "record_kind": "environment",
        "protocol": "SWS-BENCH-02",
        "run_id": run_id,
        "partial": partial,
        "utc": utc(),
        "candidate_sha": candidate,
        "worktree_dirty": identity["worktree_dirty"],
        "worktree_status_sha256": identity["worktree_status_sha256"],
        "manifest_sha256": identity["manifest_sha256"],
        "identity_uncertain": identity["identity_uncertain"],
        "dirty_paths": identity["dirty_paths"],
        "git_head_ok": identity["git_head_ok"],
        "git_status_ok": identity["git_status_ok"],
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

    if existing_env is not None:
        reason = resume_incompatible(existing_env, env, conditions)
        if reason:
            print(reason, file=sys.stderr)
            return 2
        run_id = existing_env.get("run_id") or run_id
        env["run_id"] = run_id
    else:
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(env) + "\n")
        created_empty_holder.clear()

    artifact_root = out_path.parent / run_id / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    from sovereign_product.model_client import OllamaClient
    client = OllamaClient()

    print(json.dumps({k: env[k] for k in
                      ("run_id", "candidate_sha", "worktree_dirty", "manifest_sha256",
                       "dataset_sha256", "task_count", "runs_per_cell", "partial",
                       "identity_uncertain")}, indent=2))

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
                    "worktree_dirty": identity["worktree_dirty"],
                    "worktree_status_sha256": identity["worktree_status_sha256"],
                    "manifest_sha256": identity["manifest_sha256"],
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
