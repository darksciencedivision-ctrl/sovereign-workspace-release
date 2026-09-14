"""Honest QUICK and DEEP execution adapters.

The executors never turn transport output or rejected engine artifacts into an
accepted answer.  Every accepted result is tied to an immutable, session-scoped
artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Mapping, Sequence
import uuid

from .evidence import EvidencePacket
from .model_client import (
    GenerationCancelled,
    GenerationResponse,
    GenerationTimeout,
    OllamaClient,
)


_SESSION_ID_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_STAGE_LINE_RE = re.compile(
    r"\b(?:stage|phase)\s*[:=]\s*([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)


class ExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REJECTED = "rejected"
    CONCURRENCE_NOT_REACHED = "concurrence_not_reached"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class ExecutionResult:
    """Typed, serializable result shared by QUICK and DEEP routes."""

    route: str
    status: ExecutionStatus
    session_id: str
    answer: str | None = None
    reason: str | None = None
    model: str | None = None
    record_status: str | None = None
    exit_code: int | None = None
    escalation_requested: bool = False
    escalation_reason: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    telemetry: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    latency_seconds: float = 0.0

    @property
    def accepted(self) -> bool:
        return self.status is ExecutionStatus.ACCEPTED

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["accepted"] = self.accepted
        return result


AcceptanceValidator = Callable[
    [GenerationResponse, EvidencePacket | None],
    bool | tuple[bool, str | None],
]
EscalationPolicy = Callable[
    [GenerationResponse, EvidencePacket | None],
    bool | str | tuple[bool, str | None],
]
ProgressCallback = Callable[[dict[str, Any]], None]
CancelCallback = Callable[[], bool]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError(
            "session_id must be 1-96 characters, start alphanumeric, contain only "
            "letters, digits, dot, underscore, or hyphen, and must not contain '..'"
        )
    return session_id


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=str,
    ).encode("utf-8")
    _atomic_write_bytes(path, encoded)


def _relative_artifact(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()


def _execution_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{prefix}-{timestamp}-{uuid.uuid4().hex[:8]}"


def _build_quick_prompt(prompt: str, evidence: EvidencePacket | None) -> str:
    # Grounding rules sit at the tail, after the evidence and the request: ahead
    # of a multi-kilobyte packet they were reliably ignored.
    evidence_text = evidence.text if evidence is not None else ""
    packet_label = evidence.packet_sha256 if evidence is not None else "none"
    rendered_evidence = evidence_text if evidence_text else "(no evidence supplied)"
    citations = (
        tuple(f"[source:{source.source_id}]" for source in evidence.sources)
        if evidence is not None
        else ()
    )
    if citations:
        citation_rule = (
            "- These are the only citations that exist. Copy one exactly:\n"
            + "".join(f"    {token}\n" for token in citations)
            + "- Put the citation immediately after each claim it supports, and "
            "do not cite the request above.\n"
        )
    else:
        citation_rule = (
            "- The evidence packet is empty, so no citation exists and none may "
            "be written.\n"
        )
    return (
        f"EVIDENCE PACKET SHA256: {packet_label}\n"
        f"{rendered_evidence}\n\n"
        "USER REQUEST:\n"
        f"{prompt}\n\n"
        "GROUNDING RULES:\n"
        "- Use the evidence packet for claims about supplied files or session history.\n"
        "- If evidence is missing or insufficient, say so explicitly.\n"
        "- Do not invent sources, citations, system state, or prior decisions.\n"
        f"{citation_rule}"
    )


def _parse_validation(
    value: bool | tuple[bool, str | None],
) -> tuple[bool, str | None]:
    if isinstance(value, tuple):
        accepted, reason = value
        return bool(accepted), reason
    return bool(value), None


def _parse_escalation(
    value: bool | str | tuple[bool, str | None],
) -> tuple[bool, str | None]:
    if isinstance(value, tuple):
        requested, reason = value
        return bool(requested), reason
    if isinstance(value, str):
        return bool(value), value or None
    return bool(value), None


class QuickExecutor:
    """Single-model, bounded-evidence executor with complete raw provenance."""

    def __init__(
        self,
        client: OllamaClient,
        artifact_root: str | Path,
        *,
        acceptance_validator: AcceptanceValidator | None = None,
        escalation_policy: EscalationPolicy | None = None,
        prompt_builder: Callable[[str, EvidencePacket | None], str] = _build_quick_prompt,
        now: Callable[[], str] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.artifact_root = Path(artifact_root).resolve()
        self.acceptance_validator = acceptance_validator
        self.escalation_policy = escalation_policy
        self.prompt_builder = prompt_builder
        self._now = now
        self._monotonic = monotonic

    def execute(
        self,
        session_id: str,
        prompt: str,
        *,
        model: str,
        evidence: EvidencePacket | None = None,
        options: Mapping[str, Any] | None = None,
        cancel_requested: CancelCallback | None = None,
        overall_timeout: float | None = None,
    ) -> ExecutionResult:
        session_id = _validate_session_id(session_id)
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        if evidence is not None and evidence.session_id != session_id:
            raise ValueError("evidence packet session_id does not match execution")
        execution_dir = (
            self.artifact_root / "quick" / session_id / _execution_id("quick")
        )
        prompt_path = execution_dir / "prompt.txt"
        evidence_path = execution_dir / "evidence.json"
        raw_path = execution_dir / "raw_generation.json"
        accepted_path = execution_dir / "accepted.txt"
        result_path = execution_dir / "result.json"

        started_at = self._now()
        started = self._monotonic()
        actual_prompt = self.prompt_builder(prompt, evidence)
        artifact_paths = {
            "prompt": _relative_artifact(prompt_path, self.artifact_root),
            "evidence": _relative_artifact(evidence_path, self.artifact_root),
            "raw": _relative_artifact(raw_path, self.artifact_root),
            "result": _relative_artifact(result_path, self.artifact_root),
        }
        _atomic_write_text(prompt_path, actual_prompt)
        _atomic_write_json(
            evidence_path,
            evidence.to_dict()
            if evidence is not None
            else {
                "session_id": session_id,
                "packet_sha256": None,
                "sources": [],
                "text": "",
                "total_bytes": 0,
                "total_tokens": 0,
            },
        )

        response: GenerationResponse | None = None
        status = ExecutionStatus.FAILED
        answer: str | None = None
        reason: str | None = None
        escalation_requested = False
        escalation_reason: str | None = None
        raw_record: dict[str, Any]
        try:
            response = self.client.generate(
                model=model,
                prompt=actual_prompt,
                options=dict(options or {}),
                think=False,
                cancel_requested=cancel_requested,
                overall_timeout=overall_timeout,
            )
            raw_record = {
                "ok": True,
                "response": response.to_dict(),
            }
            if not response.text.strip():
                status = ExecutionStatus.EMPTY
                reason = "Ollama completed without a non-whitespace response"
            else:
                accepted = True
                validation_reason: str | None = None
                if self.acceptance_validator is not None:
                    accepted, validation_reason = _parse_validation(
                        self.acceptance_validator(response, evidence)
                    )
                if self.escalation_policy is not None:
                    escalation_requested, escalation_reason = _parse_escalation(
                        self.escalation_policy(response, evidence)
                    )
                if accepted:
                    artifact_paths["accepted"] = _relative_artifact(
                        accepted_path,
                        self.artifact_root,
                    )
                    _atomic_write_text(accepted_path, response.text)
                    status = ExecutionStatus.ACCEPTED
                    answer = response.text
                else:
                    status = ExecutionStatus.REJECTED
                    reason = validation_reason or "QUICK acceptance validator rejected output"
        except GenerationCancelled as exc:
            status = ExecutionStatus.CANCELLED
            reason = str(exc)
            raw_record = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        except GenerationTimeout as exc:
            status = ExecutionStatus.TIMEOUT
            reason = str(exc)
            raw_record = {
                "ok": False,
                "error_type": type(exc).__name__,
                "timeout_kind": exc.timeout_kind,
                "error": str(exc),
            }
        except KeyboardInterrupt:
            status = ExecutionStatus.INTERRUPTED
            reason = "QUICK execution interrupted"
            raw_record = {
                "ok": False,
                "error_type": "KeyboardInterrupt",
                "error": reason,
            }
        except Exception as exc:
            status = ExecutionStatus.FAILED
            answer = None
            artifact_paths.pop("accepted", None)
            reason = f"{type(exc).__name__}: {exc}"
            raw_record = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

        _atomic_write_json(raw_path, raw_record)
        completed = self._monotonic()
        completed_at = self._now()
        telemetry = {
            "requested_model": model,
            "options": dict(options or {}),
            "evidence_packet_sha256": (
                evidence.packet_sha256 if evidence is not None else None
            ),
            "prompt_sha256": hashlib.sha256(actual_prompt.encode("utf-8")).hexdigest(),
        }
        if response is not None:
            telemetry.update(response.telemetry)
            telemetry["reported_model"] = response.model
            telemetry["raw_event_count"] = len(response.raw_events)
        result = ExecutionResult(
            route="quick",
            status=status,
            session_id=session_id,
            answer=answer,
            reason=reason,
            model=response.model if response is not None else model,
            escalation_requested=escalation_requested,
            escalation_reason=escalation_reason,
            artifacts=artifact_paths,
            telemetry=telemetry,
            started_at=started_at,
            completed_at=completed_at,
            latency_seconds=max(0.0, completed - started),
        )
        _atomic_write_json(result_path, result.to_dict())
        return result


def _path_within_root(root: Path, raw_path: str | Path) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("session artifact resolves outside the engine root") from exc
    if not resolved.is_file():
        raise ValueError("session artifact is not a regular file")
    return resolved


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact {path.name}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"JSON artifact {path.name} must contain an object")
    return parsed


def _record_snapshot(path: Path) -> tuple[int, int, str] | None:
    try:
        data = path.read_bytes()
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_mtime_ns, stat.st_size, hashlib.sha256(data).hexdigest()


def _progress_from_line(stream_name: str, line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("stage"), str):
            return {
                "stage": payload["stage"],
                "status": payload.get("status"),
                "stream": stream_name,
                "raw": stripped,
            }
    match = _STAGE_LINE_RE.search(stripped)
    if match:
        return {
            "stage": match.group(1),
            "status": None,
            "stream": stream_name,
            "raw": stripped,
        }
    return None


def _deep_artifact_progress(
    root: Path,
    session_id: str,
) -> tuple[tuple[Any, ...], dict[str, Any]] | None:
    """Infer honest live progress only from this session's engine artifacts."""

    live_dir = root / "output" / "live_runtime" / session_id
    if not live_dir.is_dir():
        return None
    turns_dir = live_dir / "turns"
    turn_count = (
        sum(1 for path in turns_dir.glob("*.json") if path.is_file())
        if turns_dir.is_dir()
        else 0
    )
    role_map = (live_dir / "role_model_mapping.json").is_file()
    turn_manifest = (live_dir / "turn_manifest.json").is_file()
    variance = (live_dir / "structural_variance_telemetry.json").is_file()
    signature = (role_map, turn_count, turn_manifest, variance)

    if variance:
        return signature, {
            "stage": "synthesis_review",
            "status": "running",
            "percent": 82,
            "detail": "Session synthesis exists; downstream acceptance gates are running.",
            "source": "session_artifacts",
        }
    if turn_manifest:
        return signature, {
            "stage": "debate_complete",
            "status": "running",
            "percent": 74,
            "detail": f"{turn_count} raw model-turn artifact(s) preserved.",
            "source": "session_artifacts",
        }
    if turn_count:
        return signature, {
            "stage": "debate",
            "status": "running",
            "percent": min(70, 8 + (turn_count * 4)),
            "detail": f"{turn_count} raw model-turn artifact(s) preserved.",
            "source": "session_artifacts",
        }
    if role_map:
        return signature, {
            "stage": "model_slate_ready",
            "status": "running",
            "percent": 5,
            "detail": "Session-scoped model-role mapping was preserved.",
            "source": "session_artifacts",
        }
    return None


def _pipe_reader(
    stream: Any,
    stream_name: str,
    output_queue: "queue.Queue[tuple[str, str | None]]",
) -> None:
    if stream is None:
        output_queue.put((stream_name, None))
        return
    try:
        while True:
            line = stream.readline()
            if line in ("", b""):
                break
            if isinstance(line, bytes):
                rendered = line.decode("utf-8", errors="replace")
            else:
                rendered = str(line)
            output_queue.put((stream_name, rendered))
    finally:
        output_queue.put((stream_name, None))


LEGACY_DEEP_FLAG = "SOVEREIGN_ALLOW_LEGACY_DEEP"


class UnsupportedLegacy(RuntimeError):
    """DeepExecutor is quarantined from the product route (F-113)."""


class DeepExecutor:
    """Legacy subprocess adapter for cycle_runner_v3. Not on the product route.

    Product DEEP traffic uses SemanticDeepExecutor. This class remains for
    bounded drain tests (R34) and must not be wired as the default executor.
    execute() refuses unless SOVEREIGN_ALLOW_LEGACY_DEEP=1.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        python_executable: str | Path = sys.executable,
        runner_path: str | Path | None = None,
        artifact_root: str | Path | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        process_tree_terminator: Callable[[Any], None] | None = None,
        poll_interval: float = 0.05,
        now: Callable[[], str] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"engine root is not a directory: {self.root}")
        self.runner_path = (
            Path(runner_path).resolve()
            if runner_path is not None
            else (self.root / "cycle_runner_v3.py").resolve()
        )
        try:
            self.runner_path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("runner_path must resolve inside the engine root") from exc
        self.python_executable = str(python_executable)
        self.artifact_root = (
            Path(artifact_root).resolve()
            if artifact_root is not None
            else (self.root / "product_artifacts").resolve()
        )
        try:
            self.artifact_root.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact_root must resolve inside the engine root") from exc
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.poll_interval = float(poll_interval)
        self._popen_factory = popen_factory
        self._process_tree_terminator = (
            process_tree_terminator or self._default_terminate_process_tree
        )
        self._now = now
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._active: dict[str, Any] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    @staticmethod
    def _default_terminate_process_tree(process: Any) -> None:
        if process.poll() is not None:
            return
        pid = int(process.pid)
        if os.name == "nt":
            # The child is launched in its own process group. taskkill targets
            # only that owned PID and descendants; no image-name or wildcard
            # termination is used.
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    def active_process(self, session_id: str) -> Any | None:
        """Return the tracked handle for introspection, never a guessed PID."""

        with self._lock:
            return self._active.get(session_id)

    def cancel(self, session_id: str) -> bool:
        """Cancel only a process handle created and currently owned here."""

        _validate_session_id(session_id)
        with self._lock:
            event = self._cancel_events.get(session_id)
            process = self._active.get(session_id)
            if event is None:
                return False
            event.set()
        if process is not None and process.poll() is None:
            self._process_tree_terminator(process)
        return True

    def _launch(self, command: Sequence[str]) -> Any:
        kwargs: dict[str, Any] = {
            "cwd": str(self.root),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "stdin": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
            "shell": False,
            "env": {**os.environ, "PYTHONUNBUFFERED": "1"},
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            kwargs["start_new_session"] = True
        return self._popen_factory(list(command), **kwargs)

    def execute(
        self,
        session_id: str,
        topic: str,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: CancelCallback | None = None,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        if os.environ.get(LEGACY_DEEP_FLAG) != "1":
            raise UnsupportedLegacy(
                "DeepExecutor is unsupported legacy; set SOVEREIGN_ALLOW_LEGACY_DEEP=1 "
                "only for R34/legacy harnesses. Product DEEP uses SemanticDeepExecutor."
            )
        session_id = _validate_session_id(session_id)
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        execution_dir = (
            self.artifact_root / "deep" / session_id / _execution_id("deep")
        )
        topic_path = execution_dir / "topic.txt"
        command_path = execution_dir / "command.json"
        stdout_path = execution_dir / "stdout.txt"
        stderr_path = execution_dir / "stderr.txt"
        result_path = execution_dir / "result.json"
        artifacts = {
            "topic": _relative_artifact(topic_path, self.root),
            "command": _relative_artifact(command_path, self.root),
            "stdout": _relative_artifact(stdout_path, self.root),
            "stderr": _relative_artifact(stderr_path, self.root),
            "result": _relative_artifact(result_path, self.root),
        }
        _atomic_write_text(topic_path, topic)

        command = [
            self.python_executable,
            str(self.runner_path),
            "--root",
            str(self.root),
            "--topic",
            topic,
            "--once",
            "--session-id",
            session_id,
        ]
        _atomic_write_json(
            command_path,
            {
                "argv": command,
                "cwd": str(self.root),
                "shell": False,
                "session_id": session_id,
            },
        )

        run_record_path = self.root / "runs" / f"{session_id}.json"
        before_record = _record_snapshot(run_record_path)
        started_at = self._now()
        started = self._monotonic()
        cancellation = cancel_requested or (lambda: False)
        internal_cancel = threading.Event()
        process: Any | None = None
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        progress_events: list[dict[str, Any]] = []
        callback_errors: list[str] = []
        exit_code: int | None = None
        terminal_override: ExecutionStatus | None = None
        terminal_reason: str | None = None

        with self._lock:
            if session_id in self._cancel_events:
                completed_at = self._now()
                result = ExecutionResult(
                    route="deep",
                    status=ExecutionStatus.FAILED,
                    session_id=session_id,
                    reason="a DEEP execution is already active for this session",
                    artifacts=artifacts,
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_seconds=0.0,
                )
                _atomic_write_text(stdout_path, "")
                _atomic_write_text(stderr_path, "")
                _atomic_write_json(result_path, result.to_dict())
                return result
            self._cancel_events[session_id] = internal_cancel

        output_queue: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
        reader_threads: list[threading.Thread] = []
        artifact_progress_signature: tuple[Any, ...] | None = None
        next_artifact_probe = started
        try:
            process = self._launch(command)
            with self._lock:
                self._active[session_id] = process
            for stream_name, stream in (
                ("stdout", process.stdout),
                ("stderr", process.stderr),
            ):
                reader = threading.Thread(
                    target=_pipe_reader,
                    args=(stream, stream_name, output_queue),
                    daemon=True,
                    name=f"sovereign-{session_id}-{stream_name}",
                )
                reader.start()
                reader_threads.append(reader)

            open_streams = 2
            # R34. A descendant can keep the inherited stdout/stderr open after the parent exits, so
            # `open_streams` never reaches 0 and the drain waits for EOF forever -- past the
            # configured timeout, because the tree terminator was guarded by `process.poll() is
            # None` and so never fired once the parent had exited. Bound the post-exit drain: once
            # the parent is gone, wait at most POST_EXIT_DRAIN_GRACE for its streams to close, then
            # terminate the whole tree (releasing any descendant holding the handles) and stop.
            POST_EXIT_DRAIN_GRACE = 5.0
            exited_at: float | None = None
            forced_after_exit = False
            while process.poll() is None or open_streams:
                now_monotonic = self._monotonic()
                if process.poll() is not None and exited_at is None:
                    exited_at = now_monotonic
                if (
                    exited_at is not None
                    and open_streams
                    and not forced_after_exit
                    and now_monotonic - exited_at > POST_EXIT_DRAIN_GRACE
                ):
                    # The process is gone but a descendant still holds the pipes: reclaim the tree
                    # and abandon the drain rather than hang.
                    forced_after_exit = True
                    self._process_tree_terminator(process)
                    if terminal_override is None:
                        terminal_reason = (
                            "DEEP output streams stayed open after the process exited; "
                            "a descendant retained them and the drain was bounded")
                    break
                if now_monotonic >= next_artifact_probe:
                    next_artifact_probe = now_monotonic + 0.5
                    artifact_progress = _deep_artifact_progress(
                        self.root,
                        session_id,
                    )
                    if (
                        artifact_progress is not None
                        and artifact_progress[0] != artifact_progress_signature
                    ):
                        artifact_progress_signature, progress = artifact_progress
                        progress_events.append(progress)
                        if progress_callback is not None:
                            try:
                                progress_callback(dict(progress))
                            except Exception as exc:
                                callback_errors.append(
                                    f"{type(exc).__name__}: {exc}"
                                )
                if terminal_override is None:
                    if internal_cancel.is_set() or cancellation():
                        terminal_override = ExecutionStatus.CANCELLED
                        terminal_reason = "DEEP execution cancelled"
                        if process.poll() is None:
                            self._process_tree_terminator(process)
                    elif (
                        timeout_seconds is not None
                        and self._monotonic() - started > timeout_seconds
                    ):
                        terminal_override = ExecutionStatus.TIMEOUT
                        terminal_reason = (
                            f"DEEP execution exceeded {timeout_seconds:g} seconds"
                        )
                        if process.poll() is None:
                            self._process_tree_terminator(process)

                try:
                    stream_name, line = output_queue.get(
                        timeout=self.poll_interval,
                    )
                except queue.Empty:
                    if process.poll() is not None and all(
                        not thread.is_alive() for thread in reader_threads
                    ):
                        break
                    continue
                if line is None:
                    open_streams = max(0, open_streams - 1)
                    continue
                if stream_name == "stdout":
                    stdout_lines.append(line)
                else:
                    stderr_lines.append(line)
                progress = _progress_from_line(stream_name, line)
                if progress is not None:
                    progress_events.append(progress)
                    if progress_callback is not None:
                        try:
                            progress_callback(dict(progress))
                        except Exception as exc:
                            callback_errors.append(f"{type(exc).__name__}: {exc}")

            exit_code = process.wait()
        except KeyboardInterrupt:
            terminal_override = ExecutionStatus.INTERRUPTED
            terminal_reason = "DEEP execution interrupted"
            if process is not None and process.poll() is None:
                self._process_tree_terminator(process)
                exit_code = process.wait()
        except Exception as exc:
            terminal_override = ExecutionStatus.FAILED
            terminal_reason = f"{type(exc).__name__}: {exc}"
            if process is not None and process.poll() is None:
                self._process_tree_terminator(process)
                exit_code = process.wait()
        finally:
            for reader in reader_threads:
                reader.join(timeout=0.5)
            while True:
                try:
                    stream_name, line = output_queue.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    continue
                if stream_name == "stdout":
                    stdout_lines.append(line)
                else:
                    stderr_lines.append(line)
            with self._lock:
                self._active.pop(session_id, None)
                self._cancel_events.pop(session_id, None)

        _atomic_write_text(stdout_path, "".join(stdout_lines))
        _atomic_write_text(stderr_path, "".join(stderr_lines))

        status = terminal_override or ExecutionStatus.FAILED
        reason = terminal_reason
        answer: str | None = None
        record_status: str | None = None
        model: str | None = None

        if terminal_override is None:
            after_record = _record_snapshot(run_record_path)
            if after_record is None:
                status = ExecutionStatus.FAILED
                reason = f"missing exact run record runs/{session_id}.json"
            elif before_record is not None and after_record == before_record:
                status = ExecutionStatus.FAILED
                reason = f"exact run record runs/{session_id}.json was not updated"
            else:
                artifacts["run_record"] = _relative_artifact(
                    run_record_path,
                    self.root,
                )
                try:
                    record = _read_json_object(run_record_path)
                    if record.get("session_id") != session_id:
                        raise ValueError("run record session_id does not match request")
                    raw_record_status = record.get("status")
                    if not isinstance(raw_record_status, str):
                        raise ValueError("run record status is missing or non-text")
                    record_status = raw_record_status
                    failure_reason = record.get("failure_reason")
                    if isinstance(record.get("model"), str):
                        model = record["model"]

                    if raw_record_status == ExecutionStatus.REJECTED.value:
                        status = ExecutionStatus.REJECTED
                        reason = (
                            str(failure_reason)
                            if failure_reason
                            else "engine rejected the run"
                        )
                    elif raw_record_status == ExecutionStatus.CONCURRENCE_NOT_REACHED.value:
                        status = ExecutionStatus.CONCURRENCE_NOT_REACHED
                        reason = (
                            str(failure_reason)
                            if failure_reason
                            else "engine did not reach concurrence"
                        )
                    elif raw_record_status == ExecutionStatus.CANCELLED.value:
                        status = ExecutionStatus.CANCELLED
                        reason = str(failure_reason) if failure_reason else "engine cancelled"
                    elif raw_record_status == ExecutionStatus.INTERRUPTED.value:
                        status = ExecutionStatus.INTERRUPTED
                        reason = (
                            str(failure_reason)
                            if failure_reason
                            else "engine execution was interrupted"
                        )
                    elif raw_record_status == ExecutionStatus.FAILED.value:
                        status = ExecutionStatus.FAILED
                        reason = str(failure_reason) if failure_reason else "engine failed"
                    elif exit_code != 0:
                        status = ExecutionStatus.FAILED
                        reason = (
                            f"engine exited with code {exit_code} despite run status "
                            f"{raw_record_status!r}"
                        )
                    elif raw_record_status != "completed":
                        status = ExecutionStatus.FAILED
                        reason = (
                            "run record status must be exactly 'completed' for acceptance; "
                            f"observed {raw_record_status!r}"
                        )
                    else:
                        artifact_map = record.get("artifacts")
                        if not isinstance(artifact_map, Mapping):
                            raise ValueError("run record artifacts object is missing")
                        session_answer_ref = artifact_map.get(
                            "praxis_answer_session_path"
                        )
                        if not isinstance(session_answer_ref, str) or not session_answer_ref:
                            raise ValueError(
                                "run record lacks praxis_answer_session_path; "
                                "global answer fallbacks are forbidden"
                            )
                        answer_path = _path_within_root(
                            self.root,
                            session_answer_ref,
                        )
                        answer_artifact = _read_json_object(answer_path)
                        if answer_artifact.get("session_id") != session_id:
                            raise ValueError(
                                "answer artifact session_id does not match request"
                            )
                        final_synthesis = answer_artifact.get("final_synthesis")
                        if not isinstance(final_synthesis, str):
                            raise ValueError(
                                "answer artifact final_synthesis is missing or non-text"
                            )
                        if not final_synthesis.strip():
                            status = ExecutionStatus.EMPTY
                            reason = "completed answer artifact contains no answer text"
                        else:
                            status = ExecutionStatus.ACCEPTED
                            answer = final_synthesis
                            artifacts["accepted"] = _relative_artifact(
                                answer_path,
                                self.root,
                            )
                            reason = None
                except (OSError, ValueError) as exc:
                    status = ExecutionStatus.FAILED
                    reason = str(exc)

        completed = self._monotonic()
        completed_at = self._now()
        telemetry = {
            "command": command,
            "progress": progress_events,
            "progress_callback_errors": callback_errors,
            "stdout_line_count": len(stdout_lines),
            "stderr_line_count": len(stderr_lines),
            "exact_run_record": f"runs/{session_id}.json",
        }
        result = ExecutionResult(
            route="deep",
            status=status,
            session_id=session_id,
            answer=answer,
            reason=reason,
            model=model,
            record_status=record_status,
            exit_code=exit_code,
            artifacts=artifacts,
            telemetry=telemetry,
            started_at=started_at,
            completed_at=completed_at,
            latency_seconds=max(0.0, completed - started),
        )
        _atomic_write_json(result_path, result.to_dict())
        return result
