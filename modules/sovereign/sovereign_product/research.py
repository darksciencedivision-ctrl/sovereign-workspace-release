"""Bounded, resumable, local-only long-horizon research execution.

The research executor is deliberately a state machine rather than a long
prompt.  Every phase transition is committed to an immutable, hash-chained
checkpoint before the next phase starts.  Model calls are also journaled under
the approved evidence directory, which lets a restarted process recover a
completed call that was written immediately before an interruption.

This module does not execute experiments and does not perform network I/O.
The only component permitted to communicate with a model service is the
injected model client.  If that client advertises a URL, the URL must be an
HTTP loopback URL.  Evidence described as an executed experiment is accepted
only when the caller registers an existing, content-hashed local artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import inspect
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit
import uuid

from .paths import STATE_POINTER_PREFIX, ProductPaths, UnsafeArtifactPointer
from .model_client import OLLAMA_GENERATION_TIMEOUT_SECONDS


ProgressCallback = Callable[[dict[str, Any]], None]
StopCallback = Callable[[], bool]

_ID_RE = re.compile(r"^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_CHECKPOINT_RE = re.compile(r"^(?P<sequence>[0-9]{8})_[A-Za-z0-9_-]+\.json$")
_EXECUTION_CLAIM_PATTERNS = (
    re.compile(
        r"\b(?:we|i|the\s+(?:team|system|researcher|agent))\s+"
        r"(?:ran|executed|performed|conducted)\s+(?:an?\s+)?"
        r"(?:experiment|test|benchmark|trial|measurement)s?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:experiment|test|benchmark|trial|measurement)s?\s+"
        r"(?:was|were|has\s+been|have\s+been)\s+"
        r"(?:run|executed|performed|conducted)\b",
        re.IGNORECASE,
    ),
)


class ResearchError(RuntimeError):
    """Base error for the bounded research runtime."""


class ResearchContainmentError(ResearchError, ValueError):
    """A path, transport, or identifier violates the containment boundary."""


class ResearchCheckpointError(ResearchError):
    """Checkpoint lineage is missing, corrupt, or contradictory."""


class FrozenObjectiveError(ResearchError, ValueError):
    """A resume attempt tried to alter the frozen objective."""


class ResearchAlreadyRunning(ResearchError):
    """Another live process owns the research lock."""


class ResearchPhaseError(ResearchError):
    """A model phase returned output that cannot safely advance the state."""


class ResearchPhase(str, Enum):
    HYPOTHESIS = "hypothesis_generation"
    EVIDENCE_PLAN = "local_evidence_retrieval_and_planning"
    ADVERSARIAL_CHALLENGE = "adversarial_challenge"
    DECISION = "reject_revise_or_retain"
    ITERATION_CHECKPOINT = "iteration_checkpoint"
    FINAL_SYNTHESIS = "final_synthesis"


class ResearchStatus(str, Enum):
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ResearchLimits:
    """Frozen lower targets and hard upper resource bounds.

    A successful run must meet *both* minimums.  Hard maxima are containment
    limits, not success criteria.  In an eight-hour proof, callers should use a
    positive ``minimum_duration_seconds`` and enough iteration/model-call headroom
    to keep the investigation substantive for that duration.
    """

    minimum_iterations: int = 8
    maximum_iterations: int = 64
    minimum_duration_seconds: float = 0.0
    maximum_duration_seconds: float = 8 * 60 * 60
    maximum_model_calls: int = 260
    model_call_timeout_seconds: float = OLLAMA_GENERATION_TIMEOUT_SECONDS
    maximum_prompt_bytes: int = 65_536
    maximum_output_bytes: int = 65_536
    maximum_evidence_bytes: int = 65_536
    maximum_source_bytes: int = 16_384
    maximum_sources: int = 64
    maximum_tokens_per_call: int = 32_768
    require_rejected_hypothesis: bool = True
    require_revised_hypothesis: bool = True

    def __post_init__(self) -> None:
        integer_bounds = (
            ("minimum_iterations", self.minimum_iterations, 1),
            ("maximum_iterations", self.maximum_iterations, 1),
            ("maximum_model_calls", self.maximum_model_calls, 1),
            ("maximum_prompt_bytes", self.maximum_prompt_bytes, 1),
            ("maximum_output_bytes", self.maximum_output_bytes, 1),
            ("maximum_evidence_bytes", self.maximum_evidence_bytes, 1),
            ("maximum_source_bytes", self.maximum_source_bytes, 1),
            ("maximum_sources", self.maximum_sources, 1),
            ("maximum_tokens_per_call", self.maximum_tokens_per_call, 1),
        )
        for name, value, lower in integer_bounds:
            if isinstance(value, bool) or not isinstance(value, int) or value < lower:
                raise ValueError(f"{name} must be an integer >= {lower}")
        if self.minimum_iterations > self.maximum_iterations:
            raise ValueError("minimum_iterations cannot exceed maximum_iterations")
        if self.minimum_duration_seconds < 0:
            raise ValueError("minimum_duration_seconds cannot be negative")
        if self.maximum_duration_seconds <= 0:
            raise ValueError("maximum_duration_seconds must be positive")
        if self.minimum_duration_seconds > self.maximum_duration_seconds:
            raise ValueError(
                "minimum_duration_seconds cannot exceed maximum_duration_seconds"
            )
        if self.model_call_timeout_seconds <= 0:
            raise ValueError("model_call_timeout_seconds must be positive")
        if self.maximum_source_bytes > self.maximum_evidence_bytes:
            raise ValueError(
                "maximum_source_bytes cannot exceed maximum_evidence_bytes"
            )
        # Four recursive model phases plus final synthesis are required.
        minimum_calls = self.minimum_iterations * 4 + 1
        if self.maximum_model_calls < minimum_calls:
            raise ValueError(
                "maximum_model_calls is too small for the requested minimum iterations"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResearchLimits":
        allowed = set(cls.__dataclass_fields__)
        unknown = set(value) - allowed
        if unknown:
            raise ResearchCheckpointError(
                f"checkpoint contains unknown research limits: {sorted(unknown)}"
            )
        return cls(**dict(value))


@dataclass(frozen=True)
class ResearchResult:
    research_id: str
    status: ResearchStatus
    objective_sha256: str
    completed_iterations: int
    next_phase: str | None
    checkpoint_sequence: int
    resumes: int
    reason: str | None
    artifacts: dict[str, str] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> bool:
        return self.status is ResearchStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["completed"] = self.completed
        return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _validate_advertised_loopback_url(value: str) -> None:
    """Validate an advertised model URL without importing HTTP dependencies."""

    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ResearchContainmentError(
            "model URL must be an uncredentialed loopback HTTP origin"
        )
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname != "localhost":
        try:
            if not ipaddress.ip_address(hostname).is_loopback:
                raise ResearchContainmentError("model URL is not loopback")
        except ValueError as exc:
            raise ResearchContainmentError("model URL is not loopback") from exc
    try:
        port = parsed.port
    except ValueError as exc:
        raise ResearchContainmentError("model URL has an invalid port") from exc
    if port is not None and not 1 <= port <= 65_535:
        raise ResearchContainmentError("model URL has an invalid port")


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def _atomic_write_bytes(path: Path, content: bytes, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Linking a temporary file gives create-if-absent semantics without
            # replacing an immutable ledger entry.
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, value: Any, *, replace: bool = True) -> None:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
        default=str,
    ).encode("utf-8")
    _atomic_write_bytes(path, encoded, replace=replace)


def _safe_id(value: str, *, label: str = "research_id") -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ResearchContainmentError(
            f"{label} must be 1-96 characters, begin alphanumeric, contain only "
            "letters, digits, dot, underscore, or hyphen, and not contain '..'"
        )
    return value


def _safe_child(base: Path, *parts: str) -> Path:
    base = base.resolve(strict=False)
    for part in parts:
        if (
            not isinstance(part, str)
            or not part
            or "\x00" in part
            or PurePosixPath(part).is_absolute()
            or PureWindowsPath(part).is_absolute()
            or any(piece in ("", ".", "..") for piece in part.replace("\\", "/").split("/"))
        ):
            raise ResearchContainmentError(f"unsafe contained path segment: {part!r}")
    candidate = base.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ResearchContainmentError(
            f"research path escapes approved directory: {candidate}"
        ) from exc
    return candidate


def _relative_approved_source(root: Path, value: str | Path) -> tuple[str, Path]:
    raw = str(value)
    if "\x00" in raw:
        raise ResearchContainmentError("local evidence path contains a NUL byte")
    path = Path(value)
    if (
        path.is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or PureWindowsPath(raw).drive
        or any(part in ("", ".", "..") for part in raw.replace("\\", "/").split("/"))
    ):
        raise ResearchContainmentError(
            f"local evidence source must be a safe root-relative file: {value}"
        )
    resolved_root = root.resolve(strict=False)
    resolved = (resolved_root / path).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ResearchContainmentError(
            f"local evidence source escapes the product root: {value}"
        ) from exc
    if not resolved.is_file():
        raise ResearchContainmentError(
            f"approved local evidence source is not a regular file: {value}"
        )
    return PurePosixPath(*path.parts).as_posix(), resolved


def _read_hashed_prefix(path: Path, prefix_limit: int) -> tuple[str, str, int, bool]:
    before = path.stat()
    digest = hashlib.sha256()
    prefix = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65_536)
            if not chunk:
                break
            digest.update(chunk)
            if len(prefix) < prefix_limit:
                prefix.extend(chunk[: prefix_limit - len(prefix)])
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise ResearchContainmentError(f"local evidence changed while read: {path}")
    return (
        prefix.decode("utf-8", errors="replace"),
        digest.hexdigest(),
        int(after.st_size),
        len(prefix) < int(after.st_size),
    )


def _required_text(value: Mapping[str, Any], key: str, *, maximum: int = 16_384) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ResearchPhaseError(f"model JSON field {key!r} must be non-empty text")
    result = result.strip()
    if len(result.encode("utf-8")) > maximum:
        raise ResearchPhaseError(f"model JSON field {key!r} exceeds its bound")
    return result


def _text_list(
    value: Mapping[str, Any],
    key: str,
    *,
    required: bool = False,
    maximum_items: int = 32,
    maximum_item_bytes: int = 4_096,
) -> list[str]:
    raw = value.get(key)
    if raw is None and not required:
        return []
    if not isinstance(raw, list):
        raise ResearchPhaseError(f"model JSON field {key!r} must be an array")
    if len(raw) > maximum_items:
        raise ResearchPhaseError(f"model JSON field {key!r} contains too many items")
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ResearchPhaseError(
                f"model JSON field {key!r} must contain non-empty text"
            )
        item = item.strip()
        if len(item.encode("utf-8")) > maximum_item_bytes:
            raise ResearchPhaseError(
                f"model JSON field {key!r} contains an oversized item"
            )
        result.append(item)
    return result


def _parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline < 0:
            raise ResearchPhaseError("model response contains an empty code fence")
        candidate = candidate[first_newline + 1 : -3].strip()
    try:
        value = json.loads(
            candidate,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant {token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ResearchPhaseError("model response must be one strict JSON object") from exc
    if not isinstance(value, dict):
        raise ResearchPhaseError("model response must be a JSON object")
    return dict(value)


def _contains_execution_claim(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _EXECUTION_CLAIM_PATTERNS)
    if isinstance(value, Mapping):
        return any(_contains_execution_claim(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_execution_claim(item) for item in value)
    return False


class _ResearchLock:
    """Small cross-process lock that can reclaim a dead process's lock."""

    def __init__(self, path: Path, now: Callable[[], str]) -> None:
        self.path = path
        self.now = now
        self.acquired = False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def __enter__(self) -> "_ResearchLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "acquired_at": self.now(),
            "token": uuid.uuid4().hex,
        }
        encoded = _canonical_bytes(payload)
        while True:
            try:
                with self.path.open("xb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    existing = json.loads(self.path.read_text(encoding="utf-8"))
                    pid = int(existing.get("pid", -1))
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    raise ResearchAlreadyRunning(
                        f"research lock exists but cannot be validated: {self.path}"
                    ) from exc
                if self._pid_alive(pid):
                    raise ResearchAlreadyRunning(
                        f"research is already owned by live process {pid}"
                    )
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    continue

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.acquired:
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
                if int(current.get("pid", -1)) == os.getpid():
                    self.path.unlink(missing_ok=True)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # Never remove a lock we can no longer prove is ours.
                pass
            self.acquired = False


class ResearchExecutor:
    """Execute and resume a contained recursive research investigation."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        paths: ProductPaths,
        model_client: Any,
        *,
        store: Any | None = None,
        now: Callable[[], str] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        for attribute in ("root", "state_dir", "evidence_dir"):
            if not hasattr(paths, attribute):
                raise TypeError(f"paths lacks required attribute {attribute!r}")
        self.paths = paths
        self.root = Path(paths.root).resolve(strict=False)
        self.state_dir = Path(paths.state_dir).resolve(strict=False)
        self.evidence_dir = Path(paths.evidence_dir).resolve(strict=False)
        self.model_client = model_client
        self.store = store
        self._now = now
        self._monotonic = monotonic
        self._progress: ProgressCallback | None = None
        self._cancel: StopCallback = lambda: False
        self._interrupt: StopCallback = lambda: False
        self._active_base = 0.0
        self._active_started = 0.0
        # R37. This executor is a SHARED instance and carries per-run state on itself -- the cancel
        # and interrupt callbacks, the active-time base and start, and the progress callback. Two
        # runs executing on it at once would clobber one another: run B's cancel callback would
        # replace run A's, B's timing would reset A's, and B would steal A's progress events. Until
        # that state is carried in a per-run context object, admission is single-run: run() takes
        # this lock for the whole run and a concurrent second run is refused rather than allowed to
        # corrupt the first. (A cross-process file lock, ResearchLock, is a separate concern.)
        self._run_admission = threading.Lock()

        if not self.root.is_dir():
            raise ResearchContainmentError(f"product root does not exist: {self.root}")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_dir.is_dir() or not self.evidence_dir.is_dir():
            raise ResearchContainmentError("state and evidence roots must be directories")

        advertised_url = getattr(model_client, "base_url", None)
        if advertised_url is not None:
            try:
                _validate_advertised_loopback_url(str(advertised_url))
            except Exception as exc:
                raise ResearchContainmentError(
                    "the injected model client advertises a non-loopback URL"
                ) from exc
            self._model_transport = f"loopback:{advertised_url}"
        else:
            self._model_transport = "injected-in-process-adapter"

        generate = getattr(model_client, "generate", None)
        if not callable(generate) and not callable(model_client):
            raise TypeError("model_client must be callable or expose generate()")

    def start(
        self,
        research_id: str,
        objective: str,
        *,
        model: str,
        limits: ResearchLimits | None = None,
        local_sources: Iterable[str | Path] = (),
        execution_evidence: Iterable[Mapping[str, Any]] = (),
        model_options: Mapping[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: StopCallback | None = None,
        interrupt_requested: StopCallback | None = None,
    ) -> ResearchResult:
        """Start a new investigation and drive it until a terminal boundary."""

        research_id = _safe_id(research_id)
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("objective must be non-empty text")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be non-empty text")
        objective = objective.strip()
        limits = limits or ResearchLimits()
        options = self._validate_options(model_options or {}, limits)
        source_locators = self._validate_source_locators(local_sources, limits)
        execution_registry = self._validate_execution_evidence(execution_evidence)
        research_dir = self._state_research_dir(research_id)
        lock_path = _safe_child(research_dir, ".lock")

        with _ResearchLock(lock_path, self._now):
            if self._checkpoint_files(research_id):
                raise ResearchCheckpointError(
                    f"research {research_id!r} already has durable checkpoints"
                )
            state = self._new_state(
                research_id=research_id,
                objective=objective,
                model=model.strip(),
                limits=limits,
                source_locators=source_locators,
                execution_registry=execution_registry,
                model_options=options,
            )
            self._configure_callbacks(
                progress_callback,
                cancel_requested,
                interrupt_requested,
            )
            self._begin_active_accounting(state)
            self._checkpoint(state, "initialized")
            return self._drive(state)

    def resume(
        self,
        research_id: str,
        *,
        objective: str | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: StopCallback | None = None,
        interrupt_requested: StopCallback | None = None,
    ) -> ResearchResult:
        """Resume from the last verified checkpoint without resetting lineage."""

        research_id = _safe_id(research_id)
        research_dir = self._state_research_dir(research_id)
        lock_path = _safe_child(research_dir, ".lock")
        with _ResearchLock(lock_path, self._now):
            state = self._load_state(research_id)
            if objective is not None:
                normalized = objective.strip()
                if (
                    not normalized
                    or _sha256_bytes(normalized.encode("utf-8"))
                    != state["objective_sha256"]
                    or normalized != state["objective"]
                ):
                    raise FrozenObjectiveError(
                        "the supplied objective does not match the frozen objective"
                    )
            status = ResearchStatus(state["status"])
            if status is ResearchStatus.COMPLETED:
                return self._result(state)
            if status is ResearchStatus.CANCELLED:
                raise ResearchError(
                    "cancelled research is terminal; start a new research id to continue"
                )
            if status is ResearchStatus.BUDGET_EXHAUSTED:
                return self._result(state)
            self._configure_callbacks(
                progress_callback,
                cancel_requested,
                interrupt_requested,
            )
            self._revalidate_frozen_inputs(state)
            state["status"] = ResearchStatus.RUNNING.value
            state["reason"] = None
            state["resources"]["resumes"] += 1
            state["last_resumed_at"] = self._now()
            self._begin_active_accounting(state)
            self._checkpoint(state, "resumed")
            return self._drive(state)

    def run(
        self,
        research_id: str,
        objective: str,
        *,
        model: str,
        limits: ResearchLimits | None = None,
        local_sources: Iterable[str | Path] = (),
        execution_evidence: Iterable[Mapping[str, Any]] = (),
        model_options: Mapping[str, Any] | None = None,
        resume_existing: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: StopCallback | None = None,
        interrupt_requested: StopCallback | None = None,
    ) -> ResearchResult:
        """Start or, when explicitly allowed, resume one research id."""

        # R37. Single-run admission: refuse a concurrent run rather than let it overwrite the
        # in-flight run's callbacks, timing and progress on this shared instance.
        if not self._run_admission.acquire(blocking=False):
            raise ResearchAlreadyRunning(
                "another research run is in progress on this executor; "
                "concurrent runs are not permitted"
            )
        try:
            return self._run_admitted(
                research_id,
                objective,
                model=model,
                limits=limits,
                local_sources=local_sources,
                execution_evidence=execution_evidence,
                model_options=model_options,
                resume_existing=resume_existing,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                interrupt_requested=interrupt_requested,
            )
        finally:
            self._run_admission.release()

    def _run_admitted(
        self,
        research_id: str,
        objective: str,
        *,
        model: str,
        limits: ResearchLimits | None = None,
        local_sources: Iterable[str | Path] = (),
        execution_evidence: Iterable[Mapping[str, Any]] = (),
        model_options: Mapping[str, Any] | None = None,
        resume_existing: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_requested: StopCallback | None = None,
        interrupt_requested: StopCallback | None = None,
    ) -> ResearchResult:
        research_id = _safe_id(research_id)
        if self._checkpoint_files(research_id):
            if not resume_existing:
                raise ResearchCheckpointError(
                    f"research {research_id!r} already exists"
                )
            state = self._load_state(research_id)
            expected_limits = limits or ResearchLimits()
            expected_options = self._validate_options(model_options or {}, expected_limits)
            expected_sources = self._validate_source_locators(local_sources, expected_limits)
            expected_execution = self._validate_execution_evidence(execution_evidence)
            mismatches = []
            if model.strip() != state["model"]:
                mismatches.append("model")
            if asdict(expected_limits) != state["limits"]:
                mismatches.append("limits")
            if expected_options != state["model_options"]:
                mismatches.append("model_options")
            if expected_sources != state["local_sources"]:
                mismatches.append("local_sources")
            if expected_execution != state["execution_evidence"]:
                mismatches.append("execution_evidence")
            if mismatches:
                raise FrozenObjectiveError(
                    "resume attempted to alter frozen research configuration: "
                    + ", ".join(mismatches)
                )
            return self.resume(
                research_id,
                objective=objective,
                progress_callback=progress_callback,
                cancel_requested=cancel_requested,
                interrupt_requested=interrupt_requested,
            )
        return self.start(
            research_id,
            objective,
            model=model,
            limits=limits,
            local_sources=local_sources,
            execution_evidence=execution_evidence,
            model_options=model_options,
            progress_callback=progress_callback,
            cancel_requested=cancel_requested,
            interrupt_requested=interrupt_requested,
        )

    def load_state(self, research_id: str) -> dict[str, Any]:
        """Return a copy of the last state after verifying the entire chain."""

        return _json_clone(self._load_state(_safe_id(research_id)))

    def _new_state(
        self,
        *,
        research_id: str,
        objective: str,
        model: str,
        limits: ResearchLimits,
        source_locators: list[str],
        execution_registry: list[dict[str, Any]],
        model_options: dict[str, Any],
    ) -> dict[str, Any]:
        created = self._now()
        return {
            "schema_version": self.SCHEMA_VERSION,
            "research_id": research_id,
            "objective": objective,
            "objective_sha256": _sha256_bytes(objective.encode("utf-8")),
            "created_at": created,
            "last_resumed_at": None,
            "completed_at": None,
            "model": model,
            "model_options": model_options,
            "limits": asdict(limits),
            "local_sources": source_locators,
            "execution_evidence": execution_registry,
            "status": ResearchStatus.RUNNING.value,
            "reason": None,
            "next_phase": ResearchPhase.HYPOTHESIS.value,
            "completed_iterations": 0,
            "working_iteration": {},
            "iterations": [],
            "unresolved_items": [],
            "final_synthesis": None,
            "artifacts": {},
            "inflight": None,
            "checkpoint_sequence": 0,
            "resources": {
                "active_seconds": 0.0,
                "model_calls": 0,
                "model_call_ids": [],
                "model_seconds_reported": 0.0,
                "prompt_eval_count": 0,
                "eval_count": 0,
                "token_usage_complete": True,
                "prompt_bytes": 0,
                "output_bytes": 0,
                "evidence_bytes_read": 0,
                "evidence_files_read": 0,
                "checkpoints": 0,
                "resumes": 0,
                "phase_failures": 0,
                "progress_callback_errors": 0,
                "store_sync_errors": [],
            },
            "containment": {
                "executor_external_network_requests": 0,
                "model_transport": self._model_transport,
                "approved_write_roots": [
                    str(self.state_dir),
                    str(self.evidence_dir),
                ],
                "approved_local_sources": source_locators,
                "experiment_execution_performed_by_executor": False,
            },
        }

    def _configure_callbacks(
        self,
        progress: ProgressCallback | None,
        cancel: StopCallback | None,
        interrupt: StopCallback | None,
    ) -> None:
        self._progress = progress
        self._cancel = cancel or (lambda: False)
        self._interrupt = interrupt or (lambda: False)

    def _begin_active_accounting(self, state: dict[str, Any]) -> None:
        self._active_base = float(state["resources"].get("active_seconds", 0.0))
        self._active_started = self._monotonic()

    def _refresh_active(self, state: dict[str, Any]) -> None:
        elapsed = max(0.0, self._monotonic() - self._active_started)
        state["resources"]["active_seconds"] = round(self._active_base + elapsed, 6)

    def _state_research_dir(self, research_id: str) -> Path:
        return _safe_child(self.state_dir, "research", _safe_id(research_id))

    def _evidence_research_dir(self, research_id: str) -> Path:
        return _safe_child(self.evidence_dir, "research", _safe_id(research_id))

    def _checkpoint_dir(self, research_id: str) -> Path:
        return _safe_child(self._state_research_dir(research_id), "checkpoints")

    def _checkpoint_files(self, research_id: str) -> list[Path]:
        directory = self._checkpoint_dir(research_id)
        if not directory.is_dir():
            return []
        return sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and _CHECKPOINT_RE.fullmatch(path.name)
            ),
            key=lambda path: path.name,
        )

    def _checkpoint(self, state: dict[str, Any], reason: str) -> None:
        self._refresh_active(state)
        sequence = int(state.get("checkpoint_sequence", 0)) + 1
        state["checkpoint_sequence"] = sequence
        state["resources"]["checkpoints"] = sequence
        state_snapshot = _json_clone(
            {key: value for key, value in state.items() if not key.startswith("_")}
        )
        previous = state.get("_chain_tip")
        record: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "research_id": state["research_id"],
            "sequence": sequence,
            "reason": reason,
            "created_at": self._now(),
            "previous_checkpoint_sha256": previous,
            "state": state_snapshot,
        }
        digest = _canonical_hash(record)
        record["checkpoint_sha256"] = digest
        safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "-", reason).strip("-")[:48] or "state"
        checkpoint_path = _safe_child(
            self._checkpoint_dir(state["research_id"]),
            f"{sequence:08d}_{safe_reason}.json",
        )
        try:
            _atomic_write_json(checkpoint_path, record, replace=False)
        except FileExistsError as exc:
            raise ResearchCheckpointError(
                f"immutable checkpoint sequence already exists: {sequence}"
            ) from exc
        current_path = _safe_child(
            self._state_research_dir(state["research_id"]),
            "current.json",
        )
        _atomic_write_json(current_path, record)
        state["_chain_tip"] = digest
        self._mirror_checkpoint_to_store(state, record, checkpoint_path)
        self._emit(
            state,
            {
                "event": "checkpoint",
                "reason": reason,
                "sequence": sequence,
                "status": state["status"],
                "phase": state.get("next_phase"),
                "completed_iterations": state["completed_iterations"],
            },
        )

    def _load_state(self, research_id: str) -> dict[str, Any]:
        files = self._checkpoint_files(research_id)
        if not files:
            raise ResearchCheckpointError(
                f"research {research_id!r} has no durable checkpoint"
            )
        previous: str | None = None
        latest_state: dict[str, Any] | None = None
        for expected, path in enumerate(files, start=1):
            match = _CHECKPOINT_RE.fullmatch(path.name)
            if not match or int(match.group("sequence")) != expected:
                raise ResearchCheckpointError("checkpoint lineage contains a gap")
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ResearchCheckpointError(
                    f"checkpoint cannot be read: {path.name}"
                ) from exc
            if not isinstance(record, dict):
                raise ResearchCheckpointError("checkpoint record must be an object")
            claimed = record.pop("checkpoint_sha256", None)
            actual = _canonical_hash(record)
            if not isinstance(claimed, str) or claimed != actual:
                raise ResearchCheckpointError(
                    f"checkpoint hash mismatch at sequence {expected}"
                )
            if (
                record.get("schema_version") != self.SCHEMA_VERSION
                or record.get("research_id") != research_id
                or record.get("sequence") != expected
                or record.get("previous_checkpoint_sha256") != previous
            ):
                raise ResearchCheckpointError(
                    f"checkpoint lineage mismatch at sequence {expected}"
                )
            candidate = record.get("state")
            if not isinstance(candidate, dict):
                raise ResearchCheckpointError("checkpoint state must be an object")
            if candidate.get("checkpoint_sequence") != expected:
                raise ResearchCheckpointError("checkpoint state sequence mismatch")
            latest_state = dict(candidate)
            previous = claimed
        assert latest_state is not None
        objective = latest_state.get("objective")
        if (
            not isinstance(objective, str)
            or _sha256_bytes(objective.encode("utf-8"))
            != latest_state.get("objective_sha256")
        ):
            raise ResearchCheckpointError("frozen objective hash mismatch")
        latest_state["_chain_tip"] = previous
        self._validate_loaded_state(latest_state)
        return latest_state

    def _validate_loaded_state(self, state: Mapping[str, Any]) -> None:
        if state.get("schema_version") != self.SCHEMA_VERSION:
            raise ResearchCheckpointError("unsupported research checkpoint schema")
        _safe_id(str(state.get("research_id", "")))
        try:
            ResearchStatus(str(state["status"]))
            if state.get("next_phase") is not None:
                ResearchPhase(str(state["next_phase"]))
            limits = ResearchLimits.from_dict(state["limits"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchCheckpointError("checkpoint has invalid state enums or limits") from exc
        if int(state.get("completed_iterations", -1)) < 0:
            raise ResearchCheckpointError("checkpoint has invalid iteration count")
        if int(state["completed_iterations"]) > limits.maximum_iterations:
            raise ResearchCheckpointError("checkpoint exceeds the frozen iteration bound")
        resources = state.get("resources")
        if not isinstance(resources, Mapping):
            raise ResearchCheckpointError("checkpoint lacks resource accounting")
        if int(resources.get("model_calls", -1)) < 0:
            raise ResearchCheckpointError("checkpoint has invalid model call accounting")

    def _validate_source_locators(
        self,
        local_sources: Iterable[str | Path],
        limits: ResearchLimits,
    ) -> list[str]:
        locators: list[str] = []
        for source in local_sources:
            locator, _ = _relative_approved_source(self.root, source)
            locators.append(locator)
        locators = sorted(set(locators))
        if len(locators) > limits.maximum_sources:
            raise ResearchContainmentError("too many approved local evidence sources")
        return locators

    def _validate_execution_evidence(
        self,
        records: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in records:
            if not isinstance(raw, Mapping):
                raise ResearchContainmentError(
                    "execution evidence entries must be mappings"
                )
            evidence_id = _safe_id(str(raw.get("evidence_id", "")), label="evidence_id")
            if evidence_id in seen:
                raise ResearchContainmentError(
                    f"duplicate execution evidence id: {evidence_id}"
                )
            description = raw.get("description")
            artifact = raw.get("artifact")
            if not isinstance(description, str) or not description.strip():
                raise ResearchContainmentError(
                    "execution evidence requires a non-empty description"
                )
            if not isinstance(artifact, (str, Path)):
                raise ResearchContainmentError(
                    "execution evidence requires a root-relative artifact"
                )
            locator, path = _relative_approved_source(self.root, artifact)
            _, digest, size, _ = _read_hashed_prefix(path, 0)
            expected = raw.get("sha256")
            if expected is not None and (
                not isinstance(expected, str) or expected.lower() != digest
            ):
                raise ResearchContainmentError(
                    f"execution evidence hash mismatch: {evidence_id}"
                )
            validated.append(
                {
                    "evidence_id": evidence_id,
                    "description": description.strip(),
                    "artifact": locator,
                    "sha256": digest,
                    "bytes": size,
                    "registered_as_executed_evidence": True,
                }
            )
            seen.add(evidence_id)
        return sorted(validated, key=lambda item: item["evidence_id"])

    def _revalidate_frozen_inputs(self, state: Mapping[str, Any]) -> None:
        limits = ResearchLimits.from_dict(state["limits"])
        current_sources = self._validate_source_locators(
            state.get("local_sources", ()),
            limits,
        )
        if current_sources != state.get("local_sources"):
            raise ResearchCheckpointError("frozen local source registry is inconsistent")
        current_execution = self._validate_execution_evidence(
            state.get("execution_evidence", ())
        )
        if current_execution != state.get("execution_evidence"):
            raise ResearchCheckpointError(
                "registered execution evidence changed after it was frozen"
            )

    @staticmethod
    def _validate_options(
        options: Mapping[str, Any],
        limits: ResearchLimits,
    ) -> dict[str, Any]:
        try:
            normalized = _json_clone(dict(options))
        except (TypeError, ValueError) as exc:
            raise ValueError("model_options must be JSON serializable") from exc
        configured_predict = normalized.get("num_predict", limits.maximum_tokens_per_call)
        if (
            isinstance(configured_predict, bool)
            or not isinstance(configured_predict, int)
            or configured_predict <= 0
            or configured_predict > limits.maximum_tokens_per_call
        ):
            raise ValueError(
                "model_options.num_predict must be positive and within "
                "maximum_tokens_per_call"
            )
        normalized["num_predict"] = configured_predict
        return normalized

    def _retrieve_local_evidence(
        self,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        limits = ResearchLimits.from_dict(state["limits"])
        remaining = limits.maximum_evidence_bytes
        records: list[dict[str, Any]] = []
        for locator in state["local_sources"]:
            if remaining <= 0:
                records.append(
                    {
                        "locator": locator,
                        "omitted": True,
                        "reason": "iteration evidence budget exhausted",
                    }
                )
                continue
            validated_locator, path = _relative_approved_source(self.root, locator)
            prefix_limit = min(limits.maximum_source_bytes, remaining)
            snippet, digest, size, truncated = _read_hashed_prefix(path, prefix_limit)
            snippet_bytes = len(snippet.encode("utf-8"))
            remaining -= snippet_bytes
            state["resources"]["evidence_files_read"] += 1
            state["resources"]["evidence_bytes_read"] += size
            records.append(
                {
                    "locator": validated_locator,
                    "sha256": digest,
                    "bytes": size,
                    "snippet": snippet,
                    "snippet_bytes": snippet_bytes,
                    "truncated": truncated,
                    "retrieved_at": self._now(),
                }
            )
        return records

    @staticmethod
    def _lineage_iteration(entry: Mapping[str, Any]) -> dict[str, Any]:
        """Return the durable, prompt-safe portion of one completed iteration.

        Raw evidence snippets remain preserved in the exact model-call journal.
        Recursive prompts and the durable iteration ledger need only the model
        analyses plus the hash/size manifest; retaining the snippets here would
        multiply the same bounded source payload on every later iteration.
        """

        return {
            key: _json_clone(entry[key])
            for key in (
                "iteration",
                "hypothesis",
                "evidence_plan",
                "challenge",
                "decision",
                "evidence_manifest",
            )
            if key in entry
        }

    @staticmethod
    def _bounded_prompt_text(value: Any, maximum_bytes: int) -> dict[str, Any]:
        """Represent text with exact integrity metadata and a bounded excerpt."""

        text = "" if value is None else str(value)
        encoded = text.encode("utf-8")
        excerpt = encoded[: max(0, maximum_bytes)].decode("utf-8", errors="ignore")
        return {
            "text": excerpt,
            "sha256": _sha256_bytes(encoded),
            "original_bytes": len(encoded),
            "truncated": len(encoded) > len(excerpt.encode("utf-8")),
        }

    @classmethod
    def _bounded_prompt_list(
        cls,
        values: Any,
        *,
        maximum_items: int,
        maximum_item_bytes: int,
    ) -> dict[str, Any]:
        """Summarize a sequence without losing its exact full-content hash."""

        items = list(values) if isinstance(values, (list, tuple)) else []
        selected = items[: max(0, maximum_items)]
        return {
            "total_items": len(items),
            "sha256": _canonical_hash(items),
            "items": [
                {
                    "index": index,
                    "encoding": (
                        "utf-8-text"
                        if isinstance(value, str)
                        else "canonical-json"
                    ),
                    **cls._bounded_prompt_text(
                        (
                            value
                            if isinstance(value, str)
                            else _canonical_bytes(value).decode("utf-8")
                        ),
                        maximum_item_bytes,
                    ),
                }
                for index, value in enumerate(selected)
            ],
            "omitted_items": max(0, len(items) - len(selected)),
        }

    @staticmethod
    def _bounded_prompt_mapping(
        value: Any,
        *,
        maximum_items: int,
    ) -> dict[str, Any]:
        """Summarize a mapping in stable key order with a full exact hash."""

        mapping = dict(value) if isinstance(value, Mapping) else {}
        ordered = sorted(mapping.items(), key=lambda item: str(item[0]))
        selected = ordered[: max(0, maximum_items)]
        return {
            "total_items": len(ordered),
            "sha256": _canonical_hash(mapping),
            "items": [
                {"key": str(key), "value": _json_clone(item)}
                for key, item in selected
            ],
            "omitted_items": max(0, len(ordered) - len(selected)),
        }

    @classmethod
    def _synthesis_focus_iteration(
        cls,
        entry: Mapping[str, Any],
        selection_reasons: Sequence[str],
    ) -> dict[str, Any]:
        """Create a bounded, evidence-calibrated view of one milestone."""

        lineage = cls._lineage_iteration(entry)
        hypothesis = lineage.get("hypothesis")
        hypothesis = hypothesis if isinstance(hypothesis, Mapping) else {}
        evidence_plan = lineage.get("evidence_plan")
        evidence_plan = evidence_plan if isinstance(evidence_plan, Mapping) else {}
        challenge = lineage.get("challenge")
        challenge = challenge if isinstance(challenge, Mapping) else {}
        decision = lineage.get("decision")
        decision = decision if isinstance(decision, Mapping) else {}
        evidence_manifest = lineage.get("evidence_manifest")
        evidence_manifest = (
            evidence_manifest if isinstance(evidence_manifest, list) else []
        )
        return {
            "iteration": lineage.get("iteration"),
            "selection_reasons": list(selection_reasons),
            "lineage_sha256": _canonical_hash(lineage),
            "hypothesis": {
                "testable_components": cls._bounded_prompt_list(
                    hypothesis.get("testable_components"),
                    maximum_items=3,
                    maximum_item_bytes=192,
                ),
                "rationale": cls._bounded_prompt_text(
                    hypothesis.get("rationale"),
                    256,
                ),
                "falsifiers": cls._bounded_prompt_list(
                    hypothesis.get("falsifiers"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "assumptions": cls._bounded_prompt_list(
                    hypothesis.get("assumptions"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
            },
            "evidence_plan": {
                "evidence_assessment": cls._bounded_prompt_text(
                    evidence_plan.get("evidence_assessment"),
                    256,
                ),
                "hypothesis_component_classifications": (
                    cls._bounded_prompt_mapping(
                        evidence_plan.get(
                            "hypothesis_component_classifications"
                        ),
                        maximum_items=16,
                    )
                ),
                "analysis_plan": cls._bounded_prompt_list(
                    evidence_plan.get("analysis_plan"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "experiments_planned": cls._bounded_prompt_list(
                    evidence_plan.get("experiments_planned"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "unknowns": cls._bounded_prompt_list(
                    evidence_plan.get("unknowns"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "citations": cls._bounded_prompt_list(
                    evidence_plan.get("citations"),
                    maximum_items=16,
                    maximum_item_bytes=512,
                ),
            },
            "challenge": {
                "challenge": cls._bounded_prompt_text(
                    challenge.get("challenge"),
                    256,
                ),
                "contradictions": cls._bounded_prompt_list(
                    challenge.get("contradictions"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "missing_evidence": cls._bounded_prompt_list(
                    challenge.get("missing_evidence"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "severity": str(challenge.get("severity") or ""),
                "citations": cls._bounded_prompt_list(
                    challenge.get("citations"),
                    maximum_items=16,
                    maximum_item_bytes=512,
                ),
            },
            "decision": {
                "decision": str(decision.get("decision") or ""),
                "reason": cls._bounded_prompt_text(decision.get("reason"), 256),
                "revised_hypothesis": cls._bounded_prompt_text(
                    decision.get("revised_hypothesis"),
                    256,
                ),
                "unresolved": cls._bounded_prompt_list(
                    decision.get("unresolved"),
                    maximum_items=2,
                    maximum_item_bytes=128,
                ),
                "citations": cls._bounded_prompt_list(
                    decision.get("citations"),
                    maximum_items=16,
                    maximum_item_bytes=512,
                ),
            },
            "evidence_manifest": {
                "source_count": len(evidence_manifest),
                "sha256": _canonical_hash(evidence_manifest),
                "locators": cls._bounded_prompt_list(
                    [
                        str(item.get("locator") or "")
                        for item in evidence_manifest
                        if isinstance(item, Mapping)
                    ],
                    maximum_items=16,
                    maximum_item_bytes=256,
                ),
            },
        }

    @classmethod
    def _bounded_synthesis_context(
        cls,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build a bounded final context while preserving exact raw lineage."""

        iterations = [
            cls._lineage_iteration(entry)
            for entry in state.get("iterations", [])
            if isinstance(entry, Mapping)
        ]
        selected: dict[int, list[str]] = {}

        def select(index: int, reason: str) -> None:
            selected.setdefault(index, []).append(reason)

        if iterations:
            select(0, "first_iteration")
            select(len(iterations) - 1, "last_iteration")
        for label in ("reject", "revise", "retain"):
            for index, entry in enumerate(iterations):
                decision = entry.get("decision")
                if (
                    isinstance(decision, Mapping)
                    and decision.get("decision") == label
                ):
                    select(index, f"first_{label}")
                    break

        decision_counts = {
            label: sum(
                1
                for entry in iterations
                if isinstance(entry.get("decision"), Mapping)
                and entry["decision"].get("decision") == label
            )
            for label in ("reject", "revise", "retain")
        }
        unresolved = list(state.get("unresolved_items") or [])
        unresolved_indices = list(range(min(8, len(unresolved))))
        unresolved_indices.extend(
            range(max(0, len(unresolved) - 8), len(unresolved))
        )
        unresolved_indices = list(dict.fromkeys(unresolved_indices))
        unresolved_sample = []
        for index in unresolved_indices:
            raw = unresolved[index]
            item = dict(raw) if isinstance(raw, Mapping) else {"text": raw}
            unresolved_sample.append(
                {
                    "index": index,
                    "id": str(item.get("id") or ""),
                    "first_seen_iteration": item.get("first_seen_iteration"),
                    "source": str(item.get("source") or ""),
                    "status": str(item.get("status") or ""),
                    "text": cls._bounded_prompt_text(item.get("text"), 192),
                    "entry_sha256": _canonical_hash(raw),
                }
            )

        return {
            "compaction_policy": {
                "detail_level": "milestone-detailed",
                "raw_state_mutated": False,
                "raw_lineage_location": (
                    "immutable model-call journals and hash-chained checkpoints"
                ),
                "coverage": (
                    "Every completed iteration is represented by an exact record "
                    "hash; deterministic first/decision-milestone/last records "
                    "also receive bounded excerpts."
                ),
                "truncation_contract": (
                    "Every bounded text includes its exact SHA-256, original "
                    "UTF-8 byte count, and truncation marker."
                ),
                "execution_claim_rule": (
                    "Experiments listed as planned remain plans unless cited in "
                    "execution_evidence_registry."
                ),
            },
            "lineage_integrity": {
                "iteration_count": len(iterations),
                "sha256": _canonical_hash(iterations),
            },
            "iteration_lineage_index": [
                {
                    "iteration": entry.get("iteration"),
                    "decision": (
                        entry.get("decision", {}).get("decision")
                        if isinstance(entry.get("decision"), Mapping)
                        else None
                    ),
                    "lineage_sha256": _canonical_hash(entry),
                }
                for entry in iterations
            ],
            "decision_counts": decision_counts,
            "milestone_focus": [
                cls._synthesis_focus_iteration(iterations[index], selected[index])
                for index in sorted(selected)
            ],
            "unresolved_ledger": {
                "total_items": len(unresolved),
                "sha256": _canonical_hash(unresolved),
                "sample_selection": "first_8_and_last_8_in_ledger_order",
                "sample": unresolved_sample,
                "omitted_items": max(0, len(unresolved) - len(unresolved_sample)),
            },
            "approved_local_sources": list(state.get("local_sources") or []),
        }

    @classmethod
    def _minimal_synthesis_context(
        cls,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Use a smaller integrity-preserving view for unusually tight limits."""

        iterations = [
            cls._lineage_iteration(entry)
            for entry in state.get("iterations", [])
            if isinstance(entry, Mapping)
        ]
        selected: dict[int, list[str]] = {}

        def select(index: int, reason: str) -> None:
            selected.setdefault(index, []).append(reason)

        if iterations:
            select(0, "first_iteration")
            select(len(iterations) - 1, "last_iteration")
        for label in ("reject", "revise", "retain"):
            for index, entry in enumerate(iterations):
                decision = entry.get("decision")
                if (
                    isinstance(decision, Mapping)
                    and decision.get("decision") == label
                ):
                    select(index, f"first_{label}")
                    break

        milestones = []
        for index in sorted(selected):
            entry = iterations[index]
            hypothesis = entry.get("hypothesis")
            hypothesis = hypothesis if isinstance(hypothesis, Mapping) else {}
            evidence_plan = entry.get("evidence_plan")
            evidence_plan = (
                evidence_plan if isinstance(evidence_plan, Mapping) else {}
            )
            challenge = entry.get("challenge")
            challenge = challenge if isinstance(challenge, Mapping) else {}
            decision = entry.get("decision")
            decision = decision if isinstance(decision, Mapping) else {}
            hypothesis_text = hypothesis.get("hypothesis")
            if not hypothesis_text:
                hypothesis_text = " ; ".join(
                    str(item)
                    for item in hypothesis.get("testable_components") or []
                )
            citations = sorted(
                {
                    str(locator)
                    for section in (evidence_plan, challenge, decision)
                    for locator in section.get("citations") or []
                }
            )
            milestones.append(
                {
                    "iteration": entry.get("iteration"),
                    "selection_reasons": selected[index],
                    "lineage_sha256": _canonical_hash(entry),
                    "hypothesis": cls._bounded_prompt_text(
                        hypothesis_text,
                        160,
                    ),
                    "evidence_assessment": cls._bounded_prompt_text(
                        evidence_plan.get("evidence_assessment"),
                        160,
                    ),
                    "challenge": cls._bounded_prompt_text(
                        challenge.get("challenge"),
                        160,
                    ),
                    "challenge_severity": str(challenge.get("severity") or ""),
                    "decision": str(decision.get("decision") or ""),
                    "decision_reason": cls._bounded_prompt_text(
                        decision.get("reason"),
                        160,
                    ),
                    "revised_hypothesis": cls._bounded_prompt_text(
                        decision.get("revised_hypothesis"),
                        160,
                    ),
                    "citations": citations,
                    "evidence_manifest_sha256": _canonical_hash(
                        entry.get("evidence_manifest", [])
                    ),
                }
            )

        unresolved = list(state.get("unresolved_items") or [])
        unresolved_indices = list(range(min(4, len(unresolved))))
        unresolved_indices.extend(
            range(max(0, len(unresolved) - 4), len(unresolved))
        )
        unresolved_indices = list(dict.fromkeys(unresolved_indices))
        unresolved_sample = []
        for index in unresolved_indices:
            raw = unresolved[index]
            item = dict(raw) if isinstance(raw, Mapping) else {"text": raw}
            unresolved_sample.append(
                {
                    "index": index,
                    "id": str(item.get("id") or ""),
                    "text": cls._bounded_prompt_text(item.get("text"), 96),
                    "entry_sha256": _canonical_hash(raw),
                }
            )

        return {
            "compaction_policy": {
                "detail_level": "minimal-bound-fallback",
                "raw_state_mutated": False,
                "raw_lineage_location": (
                    "immutable model-call journals and hash-chained checkpoints"
                ),
                "coverage": (
                    "Every iteration has an exact hash; deterministic milestones "
                    "have bounded evidence-calibrated excerpts."
                ),
                "execution_claim_rule": (
                    "Plans are not completed work without registered execution evidence."
                ),
            },
            "lineage_integrity": {
                "iteration_count": len(iterations),
                "sha256": _canonical_hash(iterations),
            },
            "iteration_lineage_index": [
                {
                    "iteration": entry.get("iteration"),
                    "decision": (
                        entry.get("decision", {}).get("decision")
                        if isinstance(entry.get("decision"), Mapping)
                        else None
                    ),
                    "lineage_sha256": _canonical_hash(entry),
                }
                for entry in iterations
            ],
            "decision_counts": {
                label: sum(
                    1
                    for entry in iterations
                    if isinstance(entry.get("decision"), Mapping)
                    and entry["decision"].get("decision") == label
                )
                for label in ("reject", "revise", "retain")
            },
            "milestone_focus": milestones,
            "unresolved_ledger": {
                "total_items": len(unresolved),
                "sha256": _canonical_hash(unresolved),
                "sample_selection": "first_4_and_last_4_in_ledger_order",
                "sample": unresolved_sample,
                "omitted_items": max(
                    0,
                    len(unresolved) - len(unresolved_sample),
                ),
            },
            "approved_local_sources": list(state.get("local_sources") or []),
        }

    def _phase_prompt(
        self,
        state: dict[str, Any],
        phase: ResearchPhase,
    ) -> str:
        iteration = int(state["completed_iterations"]) + 1
        objective = state["objective"]
        working = state["working_iteration"]
        common = {
            "PHASE": phase.value,
            "research_id": state["research_id"],
            "iteration": iteration,
            "frozen_objective": objective,
            "completed_iterations": state["completed_iterations"],
            "execution_evidence_registry": state["execution_evidence"],
            "rules": [
                "Return exactly one strict JSON object and no prose outside JSON.",
                "Distinguish local evidence, assumptions, plans, and unknowns.",
                "Do not claim an experiment, test, benchmark, trial, or measurement "
                "was executed unless its evidence_id appears in "
                "execution_evidence_registry.",
                "Citations must use exact approved local source locators.",
            ],
        }
        if phase is ResearchPhase.HYPOTHESIS:
            prior_iteration = (
                self._lineage_iteration(state["iterations"][-1])
                if state["iterations"]
                else None
            )
            common["prior_iteration"] = prior_iteration
            common["component_strategy"] = (
                "For the first iteration, isolate at least one central falsifiable "
                "mechanism."
                if prior_iteration is None
                else (
                    "For every later iteration, emit at least two separately testable "
                    "claims. One must be a narrow standalone core claim that the prior "
                    "evidence assessment identifies as directly supported by an "
                    "approved source, without attaching an outcome, absence claim, or "
                    "new mechanism. Another must be a separate falsifiable mechanism, "
                    "condition, limitation, or extension. Never bundle the supported "
                    "core and uncertain extension into one component, and never invent "
                    "a supported core merely to force a disposition."
                )
            )
            common["required_schema"] = {
                "testable_components": [
                    "one or more unique, complete, falsifiable atomic claims; these "
                    "components collectively are the authoritative hypothesis"
                ],
                "rationale": "non-empty string",
                "falsifiers": ["one or more concrete falsifiers"],
                "assumptions": ["explicit assumptions; may be empty"],
                "execution_evidence_citations": [
                    "required only for claims of already executed work"
                ],
            }
            common["instruction"] = (
                "Generate one falsifiable hypothesis that advances the frozen objective "
                "by emitting its complete atomic claims in testable_components. The "
                "testable_components array is the authoritative hypothesis; do not "
                "return a separate hypothesis string. Each component must be a complete "
                "claim rather than a label or noun phrase. Include every claimed causal "
                "or architectural mechanism and operative condition, but exclude "
                "background scope, goals, and merely desired outcomes. On the first "
                "iteration, isolate one central falsifiable mechanism instead of "
                "combining it with established background observations. On every later "
                "iteration, follow component_strategy and keep the evidence-backed core "
                "and uncertain extension in separate components. If prior_iteration "
                "rejected a hypothesis, replace its unsupported central mechanism rather "
                "than repeating it. If prior_iteration revised a hypothesis, use the "
                "accepted revised_hypothesis as the starting point for the next test. A "
                "retained hypothesis must be deepened or challenged from a new angle "
                "rather than copied verbatim."
            )
        elif phase is ResearchPhase.EVIDENCE_PLAN:
            if "evidence" not in working:
                working["evidence"] = self._retrieve_local_evidence(state)
            common["hypothesis"] = working.get("hypothesis")
            components = working.get("hypothesis", {}).get("testable_components")
            common["frozen_hypothesis_components"] = {
                f"component_{index:02d}": component
                for index, component in enumerate(components or (), start=1)
            }
            common["local_evidence"] = working["evidence"]
            common["required_schema"] = {
                "evidence_assessment": "non-empty string",
                "hypothesis_component_classifications": {
                    component_id: "exactly supported or unsupported"
                    for component_id in common["frozen_hypothesis_components"]
                },
                "analysis_plan": ["bounded analysis steps"],
                "experiments_planned": [
                    "plans only; never represent these as already executed"
                ],
                "unknowns": ["remaining unknowns"],
                "citations": ["exact local evidence locators used"],
                "execution_evidence_citations": [
                    "registered evidence ids used; may be empty"
                ],
            }
            common["instruction"] = (
                "Decompose the current hypothesis itself, component by component, using "
                "only the supplied local evidence. Classify every key in "
                "frozen_hypothesis_components exactly once in "
                "hypothesis_component_classifications. Use supported only when exact "
                "approved local evidence directly supports every mechanism, modifier, "
                "and operative condition in the entire component. A partial lexical or "
                "conceptual match makes the whole component unsupported: evidence of "
                "generic hashing, storage, or events does not by itself support a "
                "component that also asserts a particular tree, signature, medium, "
                "consensus, replication, hardware, or deployment mechanism. Use "
                "unsupported whenever the component is contradicted, unverified, "
                "unknown, or merely planned; absence of direct support is unsupported, "
                "not an omitted classification. Do not classify unrelated product "
                "facts, possible replacement mechanisms, or future plans. Then create "
                "a bounded analysis or experiment plan. Missing evidence must remain "
                "unknown even though its corresponding hypothesis component is "
                "classified unsupported."
            )
        elif phase is ResearchPhase.ADVERSARIAL_CHALLENGE:
            common["hypothesis"] = working.get("hypothesis")
            common["evidence_plan"] = working.get("evidence_plan")
            common["local_evidence_manifest"] = [
                {
                    key: item.get(key)
                    for key in ("locator", "sha256", "bytes", "omitted", "reason")
                    if key in item
                }
                for item in working.get("evidence", [])
            ]
            common["required_schema"] = {
                "challenge": "strongest non-strawman challenge",
                "contradictions": ["contradictions or counterevidence"],
                "missing_evidence": ["missing evidence"],
                "severity": "low, medium, high, or critical",
                "citations": ["exact local evidence locators used"],
                "execution_evidence_citations": [
                    "registered evidence ids used; may be empty"
                ],
            }
            common["instruction"] = (
                "Try to falsify the hypothesis and expose unsupported inference."
            )
        elif phase is ResearchPhase.DECISION:
            decisions = [item["decision"]["decision"] for item in state["iterations"]]
            evidence_plan = working.get("evidence_plan")
            derived_decision = self._derived_disposition(evidence_plan)
            common["hypothesis"] = working.get("hypothesis")
            common["evidence_plan"] = evidence_plan
            common["challenge"] = working.get("challenge")
            common["frozen_evidence_decomposition"] = {
                "hypothesis_supported_components": evidence_plan[
                    "hypothesis_supported_components"
                ],
                "hypothesis_unsupported_components": evidence_plan[
                    "hypothesis_unsupported_components"
                ],
            }
            common["derived_decision"] = derived_decision
            common["derived_decision_rule"] = {
                "supported_empty_and_unsupported_nonempty": "reject",
                "supported_nonempty_and_unsupported_nonempty": "revise",
                "supported_nonempty_and_unsupported_empty": "retain",
                "both_empty": "invalid",
            }
            common["decision_counts"] = {
                "rejected": decisions.count("reject"),
                "revised": decisions.count("revise"),
                "retained": decisions.count("retain"),
            }
            common["required_schema"] = {
                "decision": f"exactly {derived_decision}",
                "reason": "evidence-grounded reason",
                "revised_hypothesis": (
                    "required non-empty string when derived_decision is revise; "
                    "otherwise null"
                ),
                "unresolved": ["remaining unresolved items"],
                "citations": ["exact local evidence locators used"],
                "execution_evidence_citations": [
                    "registered evidence ids used; may be empty"
                ],
            }
            common["instruction"] = (
                "The executor has applied the frozen decision rule to the preceding raw "
                f"evidence decomposition. Emit decision exactly as {derived_decision}; "
                "do not reclassify it. Explain the result using the evidence and "
                "challenge. For reject, revised_hypothesis must be null because a "
                "replacement mechanism belongs to a future hypothesis. For revise, "
                "return a complete bounded hypothesis that preserves every listed "
                "supported component while removing or qualifying every listed "
                "unsupported component. For retain, revised_hypothesis must be null. "
                "Never add a mechanism absent from the current hypothesis merely to "
                "construct a revision, and do not optimize for decision counts."
            )
        elif phase is ResearchPhase.FINAL_SYNTHESIS:
            common["bounded_synthesis_context"] = self._bounded_synthesis_context(
                state
            )
            common["required_schema"] = {
                "objective_adherence": "explain relationship to frozen objective",
                "synthesis": "evidence-calibrated synthesis",
                "recommendations": ["actionable recommendations"],
                "remaining_unknowns": ["unknowns that remain"],
                "confidence": "low, medium, or high",
                "citations": ["exact local evidence locators used"],
                "execution_evidence_citations": [
                    "registered execution evidence ids used; may be empty"
                ],
            }
            common["instruction"] = (
                "Synthesize the complete lineage using its exact integrity index and "
                "the deterministic milestone excerpts. Do not infer omitted text, "
                "treat a bounded excerpt as a complete record, or convert plans into "
                "completed work. Preserve the distinction between supported findings, "
                "rejected hypotheses, revisions, and unresolved items."
            )
        else:
            raise ResearchPhaseError(f"phase {phase.value} has no model prompt")

        instruction = (
            "\n\nThe response is evidence-bearing research analysis, not proof that "
            "planned experiments occurred."
        )
        if phase is ResearchPhase.FINAL_SYNTHESIS:
            # The integrity-indexed context is already structurally explicit.
            # Compact JSON avoids spending the frozen byte budget on indentation
            # as the exact index approaches its 64-iteration hard maximum.
            raw = json.dumps(
                common,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + instruction
        else:
            raw = (
                json.dumps(common, ensure_ascii=False, sort_keys=True, indent=2)
                + instruction
            )
        limit = ResearchLimits.from_dict(state["limits"]).maximum_prompt_bytes
        encoded = raw.encode("utf-8")
        if len(encoded) > limit:
            if phase is ResearchPhase.EVIDENCE_PLAN:
                reduced = _json_clone(common)
                for evidence in reduced.get("local_evidence", []):
                    if isinstance(evidence, dict) and "snippet" in evidence:
                        evidence["snippet"] = evidence["snippet"][:512]
                        evidence["prompt_truncated"] = True
                raw = (
                    json.dumps(reduced, ensure_ascii=False, sort_keys=True, indent=2)
                    + instruction
                )
            elif phase is ResearchPhase.FINAL_SYNTHESIS:
                reduced = _json_clone(common)
                reduced["bounded_synthesis_context"] = (
                    self._minimal_synthesis_context(state)
                )
                raw = json.dumps(
                    reduced,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ) + instruction
            if len(raw.encode("utf-8")) > limit:
                raise ResearchPhaseError(
                    f"{phase.value} prompt exceeds the frozen prompt bound"
                )
        return raw

    @staticmethod
    def _derived_disposition(evidence_plan: Any) -> str:
        """Derive the only permitted disposition from a frozen decomposition."""

        if not isinstance(evidence_plan, Mapping):
            raise ResearchPhaseError(
                "decision requires a completed evidence decomposition"
            )

        def components(key: str) -> list[str]:
            value = evidence_plan.get(key)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ResearchPhaseError(
                    f"evidence decomposition field {key} must be a string list"
                )
            return value

        supported = components("hypothesis_supported_components")
        unsupported = components("hypothesis_unsupported_components")
        if supported and unsupported:
            return "revise"
        if supported:
            return "retain"
        if unsupported:
            return "reject"
        raise ResearchPhaseError(
            "evidence decomposition requires at least one supported or unsupported "
            "hypothesis component"
        )

    @staticmethod
    def _render_hypothesis(components: Sequence[str]) -> str:
        """Render the model's authoritative component list without semantic rewriting."""

        normalized = [" ".join(component.split()).casefold() for component in components]
        if not normalized:
            raise ResearchPhaseError(
                "a hypothesis requires at least one testable component"
            )
        if len(set(normalized)) != len(normalized):
            raise ResearchPhaseError("hypothesis components must be unique")
        rendered = " ; ".join(components)
        if len(rendered.encode("utf-8")) > 16_384:
            raise ResearchPhaseError("rendered hypothesis exceeds its bound")
        return rendered

    @staticmethod
    def _validate_decomposition_spans(
        hypothesis: str,
        supported: Sequence[str],
        unsupported: Sequence[str],
    ) -> None:
        """Require the raw decomposition to reference only current-hypothesis spans."""

        normalized_hypothesis = " ".join(hypothesis.split()).casefold()

        def normalized(component: str) -> str:
            return " ".join(component.split()).casefold()

        supported_keys = [normalized(item) for item in supported]
        unsupported_keys = [normalized(item) for item in unsupported]
        for component in supported_keys + unsupported_keys:
            if component not in normalized_hypothesis:
                raise ResearchPhaseError(
                    "evidence decomposition component is not a verbatim span of the "
                    "current hypothesis"
                )
        if len(set(supported_keys)) != len(supported_keys) or len(
            set(unsupported_keys)
        ) != len(unsupported_keys):
            raise ResearchPhaseError(
                "evidence decomposition components must be unique within each list"
            )
        if set(supported_keys) & set(unsupported_keys):
            raise ResearchPhaseError(
                "evidence decomposition cannot classify one component as both "
                "supported and unsupported"
            )

    def _parse_phase_output(
        self,
        state: Mapping[str, Any],
        phase: ResearchPhase,
        text: str,
    ) -> dict[str, Any]:
        limits = ResearchLimits.from_dict(state["limits"])
        if len(text.encode("utf-8")) > limits.maximum_output_bytes:
            raise ResearchPhaseError("model response exceeds the frozen output bound")
        value = _parse_json_object(text)
        execution_ids = {
            item["evidence_id"] for item in state.get("execution_evidence", ())
        }
        execution_citations = _text_list(
            value,
            "execution_evidence_citations",
            required=False,
        )
        if not set(execution_citations).issubset(execution_ids):
            raise ResearchPhaseError(
                "model cited unregistered executed-work evidence"
            )
        if _contains_execution_claim(value) and not execution_citations:
            raise ResearchPhaseError(
                "model claimed executed work without registered evidence citation"
            )
        source_ids = set(state.get("local_sources", ()))

        def citations() -> list[str]:
            result = _text_list(value, "citations", required=False)
            if not set(result).issubset(source_ids):
                raise ResearchPhaseError(
                    "model cited a source outside the approved local registry"
                )
            return result

        if phase is ResearchPhase.HYPOTHESIS:
            falsifiers = _text_list(value, "falsifiers", required=True)
            if not falsifiers:
                raise ResearchPhaseError("a hypothesis requires at least one falsifier")
            components = _text_list(value, "testable_components", required=True)
            hypothesis = self._render_hypothesis(components)
            return {
                "hypothesis": hypothesis,
                "testable_components": components,
                "rationale": _required_text(value, "rationale"),
                "falsifiers": falsifiers,
                "assumptions": _text_list(value, "assumptions"),
                "execution_evidence_citations": execution_citations,
            }
        if phase is ResearchPhase.EVIDENCE_PLAN:
            plan = _text_list(value, "analysis_plan", required=True)
            if not plan:
                raise ResearchPhaseError("evidence planning requires an analysis plan")
            working = state.get("working_iteration", {})
            hypothesis = working.get("hypothesis", {}).get("hypothesis")
            if not isinstance(hypothesis, str) or not hypothesis.strip():
                raise ResearchPhaseError(
                    "evidence decomposition requires the current hypothesis text"
                )
            frozen_components = working.get("hypothesis", {}).get(
                "testable_components"
            )
            if not isinstance(frozen_components, list) or not frozen_components:
                raise ResearchPhaseError(
                    "evidence decomposition requires frozen hypothesis components"
                )
            component_map = {
                f"component_{index:02d}": component
                for index, component in enumerate(frozen_components, start=1)
            }
            classifications = value.get("hypothesis_component_classifications")
            if not isinstance(classifications, Mapping) or set(
                classifications
            ) != set(component_map):
                raise ResearchPhaseError(
                    "evidence decomposition must classify every frozen hypothesis "
                    "component exactly once"
                )
            invalid_statuses = {
                str(status).strip().lower()
                for status in classifications.values()
            } - {"supported", "unsupported"}
            if invalid_statuses:
                raise ResearchPhaseError(
                    "hypothesis component classification must be supported or "
                    "unsupported"
                )
            normalized_classifications = {
                component_id: str(classifications[component_id]).strip().lower()
                for component_id in component_map
            }
            supported = [
                component_map[component_id]
                for component_id, status in normalized_classifications.items()
                if status == "supported"
            ]
            unsupported = [
                component_map[component_id]
                for component_id, status in normalized_classifications.items()
                if status == "unsupported"
            ]
            self._validate_decomposition_spans(
                hypothesis,
                supported,
                unsupported,
            )
            return {
                "evidence_assessment": _required_text(value, "evidence_assessment"),
                "hypothesis_component_classifications": normalized_classifications,
                "hypothesis_supported_components": supported,
                "hypothesis_unsupported_components": unsupported,
                "analysis_plan": plan,
                "experiments_planned": _text_list(value, "experiments_planned"),
                "unknowns": _text_list(value, "unknowns"),
                "citations": citations(),
                "execution_evidence_citations": execution_citations,
            }
        if phase is ResearchPhase.ADVERSARIAL_CHALLENGE:
            severity = str(value.get("severity", "")).strip().lower()
            if severity not in {"low", "medium", "high", "critical"}:
                raise ResearchPhaseError(
                    "adversarial severity must be low, medium, high, or critical"
                )
            return {
                "challenge": _required_text(value, "challenge"),
                "contradictions": _text_list(value, "contradictions"),
                "missing_evidence": _text_list(value, "missing_evidence"),
                "severity": severity,
                "citations": citations(),
                "execution_evidence_citations": execution_citations,
            }
        if phase is ResearchPhase.DECISION:
            decision = str(value.get("decision", "")).strip().lower()
            if decision not in {"reject", "revise", "retain"}:
                raise ResearchPhaseError(
                    "research decision must be reject, revise, or retain"
                )
            expected_decision = self._derived_disposition(
                state.get("working_iteration", {}).get("evidence_plan")
            )
            if decision != expected_decision:
                raise ResearchPhaseError(
                    "research decision does not match the frozen evidence-decomposition "
                    f"rule: expected {expected_decision}, received {decision}"
                )
            revised = value.get("revised_hypothesis")
            if decision == "revise":
                if not isinstance(revised, str) or not revised.strip():
                    raise ResearchPhaseError(
                        "a revise decision requires revised_hypothesis"
                    )
                revised = revised.strip()
            else:
                if revised is not None:
                    raise ResearchPhaseError(
                        "revised_hypothesis must be null unless decision is revise"
                    )
                revised = None
            return {
                "decision": decision,
                "reason": _required_text(value, "reason"),
                "revised_hypothesis": revised,
                "unresolved": _text_list(value, "unresolved"),
                "citations": citations(),
                "execution_evidence_citations": execution_citations,
            }
        if phase is ResearchPhase.FINAL_SYNTHESIS:
            confidence = str(value.get("confidence", "")).strip().lower()
            if confidence not in {"low", "medium", "high"}:
                raise ResearchPhaseError(
                    "final confidence must be low, medium, or high"
                )
            return {
                "objective_adherence": _required_text(
                    value,
                    "objective_adherence",
                ),
                "synthesis": _required_text(value, "synthesis"),
                "recommendations": _text_list(
                    value,
                    "recommendations",
                    required=True,
                ),
                "remaining_unknowns": _text_list(value, "remaining_unknowns"),
                "confidence": confidence,
                "citations": citations(),
                "execution_evidence_citations": execution_citations,
            }
        raise ResearchPhaseError(f"unsupported model phase: {phase.value}")

    def _call_artifact_path(
        self,
        research_id: str,
        call_index: int,
        phase: ResearchPhase,
    ) -> Path:
        return _safe_child(
            self._evidence_research_dir(research_id),
            "model_calls",
            f"{call_index:05d}_{phase.value}.json",
        )

    def _phase_response_format(
        self,
        state: Mapping[str, Any],
        phase: ResearchPhase,
    ) -> dict[str, Any]:
        """Build a strict generation schema from the frozen evidence registries."""

        source_ids = sorted({str(item) for item in state.get("local_sources", ())})
        execution_ids = sorted(
            {
                str(item["evidence_id"])
                for item in state.get("execution_evidence", ())
                if isinstance(item, Mapping) and item.get("evidence_id")
            }
        )

        def text() -> dict[str, Any]:
            return {"type": "string", "minLength": 1}

        def text_list(
            *,
            minimum: int = 0,
            enum_values: list[str] | None = None,
        ) -> dict[str, Any]:
            items: dict[str, Any] = {"type": "string", "minLength": 1}
            if enum_values:
                items["enum"] = enum_values
            schema: dict[str, Any] = {
                "type": "array",
                "items": items,
                "minItems": minimum,
                "maxItems": min(32, len(enum_values)) if enum_values else 32,
                "uniqueItems": True,
            }
            if enum_values is not None and not enum_values:
                schema["maxItems"] = 0
            return schema

        execution_citations = text_list(enum_values=execution_ids)
        source_citations = text_list(
            minimum=1 if source_ids else 0,
            enum_values=source_ids,
        )

        def strict_object(
            properties: Mapping[str, Any],
            required: Sequence[str],
        ) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": dict(properties),
                "required": list(required),
                "additionalProperties": False,
            }

        if phase is ResearchPhase.HYPOTHESIS:
            minimum_components = (
                1 if int(state.get("completed_iterations", 0)) == 0 else 2
            )
            return strict_object(
                {
                    "testable_components": text_list(minimum=minimum_components),
                    "rationale": text(),
                    "falsifiers": text_list(minimum=1),
                    "assumptions": text_list(),
                    "execution_evidence_citations": execution_citations,
                },
                (
                    "testable_components",
                    "rationale",
                    "falsifiers",
                    "assumptions",
                    "execution_evidence_citations",
                ),
            )
        if phase is ResearchPhase.EVIDENCE_PLAN:
            frozen_components = (
                state.get("working_iteration", {})
                .get("hypothesis", {})
                .get("testable_components")
            )
            if not isinstance(frozen_components, list) or not frozen_components:
                raise ResearchPhaseError(
                    "evidence planning requires frozen hypothesis components"
                )
            classification_properties = {
                f"component_{index:02d}": {
                    "type": "string",
                    "enum": ["supported", "unsupported"],
                }
                for index, _component in enumerate(frozen_components, start=1)
            }
            classifications = strict_object(
                classification_properties,
                tuple(classification_properties),
            )
            return strict_object(
                {
                    "evidence_assessment": text(),
                    "hypothesis_component_classifications": classifications,
                    "analysis_plan": text_list(minimum=1),
                    "experiments_planned": text_list(),
                    "unknowns": text_list(),
                    "citations": source_citations,
                    "execution_evidence_citations": execution_citations,
                },
                (
                    "evidence_assessment",
                    "hypothesis_component_classifications",
                    "analysis_plan",
                    "experiments_planned",
                    "unknowns",
                    "citations",
                    "execution_evidence_citations",
                ),
            )
        if phase is ResearchPhase.ADVERSARIAL_CHALLENGE:
            return strict_object(
                {
                    "challenge": text(),
                    "contradictions": text_list(),
                    "missing_evidence": text_list(),
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "citations": source_citations,
                    "execution_evidence_citations": execution_citations,
                },
                (
                    "challenge",
                    "contradictions",
                    "missing_evidence",
                    "severity",
                    "citations",
                    "execution_evidence_citations",
                ),
            )
        if phase is ResearchPhase.DECISION:
            decision = self._derived_disposition(
                state.get("working_iteration", {}).get("evidence_plan")
            )
            required = (
                "decision",
                "reason",
                "revised_hypothesis",
                "unresolved",
                "citations",
                "execution_evidence_citations",
            )
            return strict_object(
                {
                    "decision": {
                        "type": "string",
                        "enum": [decision],
                    },
                    "reason": text(),
                    "revised_hypothesis": (
                        text() if decision == "revise" else {"type": "null"}
                    ),
                    "unresolved": text_list(minimum=1),
                    "citations": source_citations,
                    "execution_evidence_citations": execution_citations,
                },
                required,
            )
        if phase is ResearchPhase.FINAL_SYNTHESIS:
            return strict_object(
                {
                    "objective_adherence": text(),
                    "synthesis": text(),
                    "recommendations": text_list(minimum=1),
                    "remaining_unknowns": text_list(),
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "citations": source_citations,
                    "execution_evidence_citations": execution_citations,
                },
                (
                    "objective_adherence",
                    "synthesis",
                    "recommendations",
                    "remaining_unknowns",
                    "confidence",
                    "citations",
                    "execution_evidence_citations",
                ),
            )
        raise ResearchPhaseError(f"phase {phase.value} has no response schema")

    def _begin_model_phase(
        self,
        state: dict[str, Any],
        phase: ResearchPhase,
    ) -> dict[str, Any]:
        response_format = self._phase_response_format(state, phase)
        response_format_sha256 = _canonical_hash(response_format)
        existing = state.get("inflight")
        if existing is not None:
            if (
                existing.get("phase") != phase.value
                or int(existing.get("iteration", -1))
                != int(state["completed_iterations"]) + 1
                or existing.get("response_format") != response_format
                or existing.get("response_format_sha256")
                != response_format_sha256
            ):
                raise ResearchCheckpointError(
                    "inflight model phase contradicts the state cursor"
                )
            return existing
        prompt = self._phase_prompt(state, phase)
        call_index = int(state["resources"]["model_calls"]) + 1
        inflight = {
            "phase": phase.value,
            "iteration": int(state["completed_iterations"]) + 1,
            "call_index": call_index,
            "prompt": prompt,
            "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
            "response_format": response_format,
            "response_format_sha256": response_format_sha256,
            "started_at": self._now(),
        }
        state["inflight"] = inflight
        self._checkpoint(state, f"phase-started-{phase.value}")
        return inflight

    def _invoke_model(
        self,
        state: dict[str, Any],
        inflight: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any], float]:
        limits = ResearchLimits.from_dict(state["limits"])
        timeout = limits.model_call_timeout_seconds

        def stop_requested() -> bool:
            return self._callback_true(self._cancel) or self._callback_true(
                self._interrupt
            )

        kwargs = {
            "model": state["model"],
            "prompt": inflight["prompt"],
            "options": state["model_options"],
            "cancel_requested": stop_requested,
            "overall_timeout": timeout,
            "response_format": inflight["response_format"],
        }
        callable_model = getattr(self.model_client, "generate", None)
        if not callable(callable_model):
            callable_model = self.model_client
        filtered = self._supported_kwargs(callable_model, kwargs)
        started = self._monotonic()
        response = callable_model(**filtered)
        completed = self._monotonic()
        if (
            response.__class__.__name__ == "GenerationResponse"
            and isinstance(getattr(response, "text", None), str)
            and hasattr(response, "to_dict")
        ):
            return response.text, response.to_dict(), response.latency_seconds
        if isinstance(response, str):
            return response, {"text": response}, max(0.0, completed - started)
        if isinstance(response, Mapping):
            text = response.get("text", response.get("response"))
            if not isinstance(text, str):
                raise ResearchPhaseError(
                    "injected model mapping lacks a text response"
                )
            latency = response.get("latency_seconds", completed - started)
            try:
                latency_value = max(0.0, float(latency))
            except (TypeError, ValueError):
                latency_value = max(0.0, completed - started)
            return text, _json_clone(dict(response)), latency_value
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            raise ResearchPhaseError(
                "injected model response must be text, a mapping, or expose .text"
            )
        telemetry = (
            response.to_dict()
            if hasattr(response, "to_dict") and callable(response.to_dict)
            else {"text": text}
        )
        return text, _json_clone(telemetry), max(0.0, completed - started)

    @staticmethod
    def _supported_kwargs(callable_model: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
        try:
            signature = inspect.signature(callable_model)
        except (TypeError, ValueError):
            return kwargs
        if any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            return kwargs
        return {key: value for key, value in kwargs.items() if key in signature.parameters}

    def _obtain_model_output(
        self,
        state: dict[str, Any],
        phase: ResearchPhase,
        inflight: Mapping[str, Any],
    ) -> str:
        call_index = int(inflight["call_index"])
        artifact_path = self._call_artifact_path(
            state["research_id"],
            call_index,
            phase,
        )
        if artifact_path.is_file():
            try:
                record = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ResearchCheckpointError(
                    f"journaled model call is unreadable: {artifact_path.name}"
                ) from exc
            if (
                record.get("call_index") != call_index
                or record.get("phase") != phase.value
                or record.get("prompt_sha256") != inflight["prompt_sha256"]
                or record.get("response_format_sha256")
                != inflight["response_format_sha256"]
                or not isinstance(record.get("text"), str)
                or record.get("record_sha256")
                != _canonical_hash(
                    {
                        key: value
                        for key, value in record.items()
                        if key != "record_sha256"
                    }
                )
            ):
                raise ResearchCheckpointError(
                    "journaled model call does not match the inflight phase"
                )
            self._account_model_call(state, record)
            return record["text"]

        text, raw, model_seconds = self._invoke_model(state, inflight)
        record = {
            "schema_version": self.SCHEMA_VERSION,
            "research_id": state["research_id"],
            "call_index": call_index,
            "phase": phase.value,
            "iteration": inflight["iteration"],
            "model": state["model"],
            "prompt_sha256": inflight["prompt_sha256"],
            "prompt_bytes": len(inflight["prompt"].encode("utf-8")),
            "response_format_sha256": inflight["response_format_sha256"],
            "text": text,
            "output_sha256": _sha256_bytes(text.encode("utf-8")),
            "output_bytes": len(text.encode("utf-8")),
            "model_seconds": model_seconds,
            "raw_response": raw,
            "completed_at": self._now(),
        }
        record["record_sha256"] = _canonical_hash(record)
        try:
            _atomic_write_json(artifact_path, record, replace=False)
        except FileExistsError as exc:
            raise ResearchCheckpointError(
                "model call journal collision during phase execution"
            ) from exc
        self._account_model_call(state, record)
        return text

    @staticmethod
    def _account_model_call(
        state: dict[str, Any],
        record: Mapping[str, Any],
    ) -> None:
        call_id = f"{int(record['call_index']):05d}"
        resources = state["resources"]
        if call_id in resources["model_call_ids"]:
            return
        resources["model_call_ids"].append(call_id)
        resources["model_calls"] = len(resources["model_call_ids"])
        raw_response = record.get("raw_response")
        raw_response = raw_response if isinstance(raw_response, Mapping) else {}
        telemetry = raw_response.get("telemetry")
        telemetry = telemetry if isinstance(telemetry, Mapping) else {}
        prompt_count = telemetry.get("prompt_eval_count")
        output_count = telemetry.get("eval_count")
        valid_prompt_count = (
            isinstance(prompt_count, int)
            and not isinstance(prompt_count, bool)
            and prompt_count >= 0
        )
        valid_output_count = (
            isinstance(output_count, int)
            and not isinstance(output_count, bool)
            and output_count >= 0
        )
        tracking_initialized = all(
            key in resources
            for key in (
                "prompt_eval_count",
                "eval_count",
                "token_usage_complete",
            )
        )
        resources["prompt_eval_count"] = int(
            resources.get("prompt_eval_count", 0)
        ) + (int(prompt_count) if valid_prompt_count else 0)
        resources["eval_count"] = int(resources.get("eval_count", 0)) + (
            int(output_count) if valid_output_count else 0
        )
        resources["token_usage_complete"] = bool(
            tracking_initialized
            and resources.get("token_usage_complete") is True
            and valid_prompt_count
            and valid_output_count
        )
        resources["prompt_bytes"] += int(record.get("prompt_bytes", 0))
        resources["output_bytes"] += int(record.get("output_bytes", 0))
        resources["model_seconds_reported"] = round(
            float(resources.get("model_seconds_reported", 0.0))
            + float(record.get("model_seconds", 0.0)),
            6,
        )

    def _complete_model_phase(
        self,
        state: dict[str, Any],
        phase: ResearchPhase,
        output: dict[str, Any],
    ) -> None:
        working = state["working_iteration"]
        iteration_number = int(state["completed_iterations"]) + 1
        if phase is ResearchPhase.HYPOTHESIS:
            working.clear()
            working["iteration"] = iteration_number
            working["hypothesis"] = output
            state["next_phase"] = ResearchPhase.EVIDENCE_PLAN.value
        elif phase is ResearchPhase.EVIDENCE_PLAN:
            working["evidence_plan"] = output
            state["next_phase"] = ResearchPhase.ADVERSARIAL_CHALLENGE.value
        elif phase is ResearchPhase.ADVERSARIAL_CHALLENGE:
            working["challenge"] = output
            state["next_phase"] = ResearchPhase.DECISION.value
        elif phase is ResearchPhase.DECISION:
            working["decision"] = output
            evidence_manifest = []
            for item in working.get("evidence", []):
                evidence_manifest.append(
                    {
                        key: item.get(key)
                        for key in (
                            "locator",
                            "sha256",
                            "bytes",
                            "truncated",
                            "omitted",
                            "reason",
                        )
                        if key in item
                    }
                )
            working["evidence_manifest"] = evidence_manifest
            for unresolved in output["unresolved"]:
                self._add_unresolved(
                    state,
                    unresolved,
                    iteration=iteration_number,
                    source="decision",
                )
            for missing in working["challenge"]["missing_evidence"]:
                self._add_unresolved(
                    state,
                    missing,
                    iteration=iteration_number,
                    source="adversarial_challenge",
                )
            state["next_phase"] = ResearchPhase.ITERATION_CHECKPOINT.value
        elif phase is ResearchPhase.FINAL_SYNTHESIS:
            state["final_synthesis"] = output
            for unresolved in output["remaining_unknowns"]:
                self._add_unresolved(
                    state,
                    unresolved,
                    iteration=state["completed_iterations"],
                    source="final_synthesis",
                )
            state["next_phase"] = None
        else:
            raise ResearchPhaseError(f"cannot complete model phase {phase.value}")
        state["inflight"] = None
        self._checkpoint(state, f"phase-completed-{phase.value}")

    @staticmethod
    def _add_unresolved(
        state: dict[str, Any],
        text: str,
        *,
        iteration: int,
        source: str,
    ) -> None:
        normalized = " ".join(text.split())
        if not normalized:
            return
        key = normalized.casefold()
        if any(item["text"].casefold() == key for item in state["unresolved_items"]):
            return
        state["unresolved_items"].append(
            {
                "id": f"U{len(state['unresolved_items']) + 1:04d}",
                "text": normalized,
                "first_seen_iteration": iteration,
                "source": source,
                "status": "open",
            }
        )

    def _targets_met(self, state: Mapping[str, Any]) -> bool:
        limits = ResearchLimits.from_dict(state["limits"])
        if int(state["completed_iterations"]) < limits.minimum_iterations:
            return False
        if float(state["resources"]["active_seconds"]) < limits.minimum_duration_seconds:
            return False
        decisions = [
            item["decision"]["decision"] for item in state.get("iterations", ())
        ]
        if limits.require_rejected_hypothesis and "reject" not in decisions:
            return False
        if limits.require_revised_hypothesis and "revise" not in decisions:
            return False
        return True

    def _budget_reason(
        self,
        state: Mapping[str, Any],
        phase: ResearchPhase,
    ) -> str | None:
        limits = ResearchLimits.from_dict(state["limits"])
        if float(state["resources"]["active_seconds"]) >= limits.maximum_duration_seconds:
            return "maximum active-duration budget reached"
        if (
            phase is ResearchPhase.HYPOTHESIS
            and int(state["completed_iterations"]) >= limits.maximum_iterations
        ):
            return "maximum iteration budget reached"
        if (
            phase is not ResearchPhase.ITERATION_CHECKPOINT
            and int(state["resources"]["model_calls"]) >= limits.maximum_model_calls
            and state.get("inflight") is None
        ):
            return "maximum model-call budget reached"
        return None

    def _drive(self, state: dict[str, Any]) -> ResearchResult:
        try:
            while True:
                self._refresh_active(state)
                if self._callback_true(self._cancel):
                    return self._stop(state, ResearchStatus.CANCELLED, "cancel requested")
                if self._callback_true(self._interrupt):
                    return self._stop(
                        state,
                        ResearchStatus.INTERRUPTED,
                        "forced interruption requested",
                    )
                if state.get("next_phase") is None:
                    if state["status"] == ResearchStatus.COMPLETED.value:
                        return self._result(state)
                    raise ResearchCheckpointError(
                        "non-completed state has no next phase"
                    )
                phase = ResearchPhase(state["next_phase"])
                budget_reason = self._budget_reason(state, phase)
                if budget_reason is not None:
                    return self._finish_partial(state, budget_reason)

                if phase is ResearchPhase.ITERATION_CHECKPOINT:
                    self._complete_iteration(state)
                    continue

                inflight = self._begin_model_phase(state, phase)
                text = self._obtain_model_output(state, phase, inflight)
                parsed = self._parse_phase_output(state, phase, text)
                self._complete_model_phase(state, phase, parsed)

                if phase is ResearchPhase.FINAL_SYNTHESIS:
                    state["status"] = ResearchStatus.COMPLETED.value
                    state["completed_at"] = self._now()
                    state["reason"] = None
                    self._write_final_artifacts(state, completed=True)
                    self._checkpoint(state, "research-completed")
                    return self._result(state)
        except KeyboardInterrupt:
            return self._stop(
                state,
                ResearchStatus.INTERRUPTED,
                "process interruption received",
            )
        except TimeoutError as exc:
            timeout_kind = getattr(exc, "timeout_kind", "unknown")
            return self._fail(state, f"model generation timeout ({timeout_kind})")
        except Exception as exc:
            if type(exc).__name__ == "GenerationCancelled":
                if self._callback_true(self._interrupt):
                    return self._stop(
                        state,
                        ResearchStatus.INTERRUPTED,
                        f"model generation interrupted: {exc}",
                    )
                return self._stop(
                    state,
                    ResearchStatus.CANCELLED,
                    f"model generation cancelled: {exc}",
                )
            return self._fail(state, f"{type(exc).__name__}: {exc}")

    def _complete_iteration(self, state: dict[str, Any]) -> None:
        expected = int(state["completed_iterations"]) + 1
        working = state["working_iteration"]
        if (
            not isinstance(working, Mapping)
            or working.get("iteration") != expected
            or any(
                key not in working
                for key in ("hypothesis", "evidence_plan", "challenge", "decision")
            )
        ):
            raise ResearchCheckpointError(
                "iteration checkpoint lacks a complete recursive phase set"
            )
        state["iterations"].append(self._lineage_iteration(working))
        state["completed_iterations"] = expected
        state["working_iteration"] = {}
        self._refresh_active(state)
        if self._targets_met(state):
            state["next_phase"] = ResearchPhase.FINAL_SYNTHESIS.value
        else:
            state["next_phase"] = ResearchPhase.HYPOTHESIS.value
        self._checkpoint(state, f"iteration-{expected}-completed")

    def _stop(
        self,
        state: dict[str, Any],
        status: ResearchStatus,
        reason: str,
    ) -> ResearchResult:
        state["status"] = status.value
        state["reason"] = reason
        self._checkpoint(state, status.value)
        return self._result(state)

    def _fail(self, state: dict[str, Any], reason: str) -> ResearchResult:
        state["resources"]["phase_failures"] += 1
        state["status"] = ResearchStatus.FAILED.value
        state["reason"] = reason
        try:
            self._checkpoint(state, "failed")
        except Exception as checkpoint_exc:
            raise ResearchCheckpointError(
                f"research failed ({reason}) and failure checkpoint also failed: "
                f"{checkpoint_exc}"
            ) from checkpoint_exc
        return self._result(state)

    def _finish_partial(
        self,
        state: dict[str, Any],
        reason: str,
    ) -> ResearchResult:
        state["status"] = ResearchStatus.BUDGET_EXHAUSTED.value
        state["reason"] = reason
        state["completed_at"] = self._now()
        state["next_phase"] = None
        self._write_final_artifacts(state, completed=False)
        self._checkpoint(state, "budget-exhausted")
        return self._result(state)

    def _write_final_artifacts(
        self,
        state: dict[str, Any],
        *,
        completed: bool,
    ) -> None:
        directory = self._evidence_research_dir(state["research_id"])
        report_path = _safe_child(directory, "final_report.md")
        unresolved_path = _safe_child(directory, "unresolved_items.json")
        resource_path = _safe_child(directory, "resource_accounting.json")
        containment_path = _safe_child(directory, "containment.json")
        lineage_path = _safe_child(directory, "lineage.json")

        decisions = [
            entry["decision"]["decision"] for entry in state["iterations"]
        ]
        failed = [
            {
                "iteration": entry["iteration"],
                "hypothesis": entry["hypothesis"]["hypothesis"],
                "reason": entry["decision"]["reason"],
            }
            for entry in state["iterations"]
            if entry["decision"]["decision"] == "reject"
        ]
        revised = [
            {
                "iteration": entry["iteration"],
                "original": entry["hypothesis"]["hypothesis"],
                "revised": entry["decision"]["revised_hypothesis"],
                "reason": entry["decision"]["reason"],
            }
            for entry in state["iterations"]
            if entry["decision"]["decision"] == "revise"
        ]
        assumptions: list[str] = []
        for entry in state["iterations"]:
            for assumption in entry["hypothesis"]["assumptions"]:
                if assumption not in assumptions:
                    assumptions.append(assumption)

        synthesis = state.get("final_synthesis") or {}
        completed_work = [
            f"Completed {state['completed_iterations']} recursive research iteration(s).",
            "Each completed iteration contains hypothesis generation, bounded local "
            "evidence retrieval and planning, adversarial challenge, and an explicit "
            "reject/revise/retain decision.",
            f"Retrieved {state['resources']['evidence_files_read']} approved local "
            "file observation(s); content hashes are retained in lineage.json.",
        ]
        if state["execution_evidence"]:
            completed_work.append(
                f"Registered {len(state['execution_evidence'])} caller-supplied "
                "executed-work artifact(s); the executor itself ran no experiments."
            )
        else:
            completed_work.append(
                "No executed-work artifact was registered; all experiment references "
                "in this run are plans, not completed experiments."
            )

        def bullets(items: Sequence[str], empty: str) -> str:
            return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"

        failed_lines = [
            f"Iteration {item['iteration']}: {item['hypothesis']} — {item['reason']}"
            for item in failed
        ]
        revised_lines = [
            f"Iteration {item['iteration']}: {item['original']} → {item['revised']}"
            for item in revised
        ]
        unknowns = [item["text"] for item in state["unresolved_items"]]
        recommendations = synthesis.get("recommendations", [])
        status_label = "COMPLETED" if completed else "INCOMPLETE — BUDGET EXHAUSTED"
        report = (
            f"# Bounded Research Report: {state['research_id']}\n\n"
            f"Status: {status_label}\n\n"
            "## Frozen objective\n\n"
            f"{state['objective']}\n\n"
            "## Completed work\n\n"
            f"{bullets(completed_work, 'No recursive iteration completed.')}\n\n"
            "## Evidence-grounded synthesis\n\n"
            f"{synthesis.get('synthesis', 'No final model synthesis was accepted.')}\n\n"
            "## Assumptions\n\n"
            f"{bullets(assumptions, 'No explicit assumptions recorded.')}\n\n"
            "## Unknowns and unresolved items\n\n"
            f"{bullets(unknowns, 'No unresolved item recorded.')}\n\n"
            "## Rejected hypotheses\n\n"
            f"{bullets(failed_lines, 'No hypothesis was rejected.')}\n\n"
            "## Revised hypotheses\n\n"
            f"{bullets(revised_lines, 'No hypothesis was revised.')}\n\n"
            "## Recommendations\n\n"
            f"{bullets(recommendations, 'No final recommendation was accepted.')}\n\n"
            "## Execution boundary\n\n"
            "This executor performed analysis and planning only. It did not execute "
            "experiments. Completed experiment claims are limited to caller-registered, "
            "content-hashed artifacts listed in the lineage.\n"
        )
        _atomic_write_bytes(report_path, report.encode("utf-8"))
        _atomic_write_json(
            unresolved_path,
            {
                "research_id": state["research_id"],
                "objective_sha256": state["objective_sha256"],
                "items": state["unresolved_items"],
            },
        )
        resources = _json_clone(state["resources"])
        resources.update(
            {
                "research_id": state["research_id"],
                "completed_iterations": state["completed_iterations"],
                "decision_counts": {
                    "reject": decisions.count("reject"),
                    "revise": decisions.count("revise"),
                    "retain": decisions.count("retain"),
                },
                "frozen_limits": state["limits"],
            }
        )
        _atomic_write_json(resource_path, resources)
        containment = _json_clone(state["containment"])
        containment.update(
            {
                "verified_at": self._now(),
                "all_executor_writes_within_approved_roots": True,
                "local_sources_revalidated": True,
                "registered_execution_evidence": state["execution_evidence"],
            }
        )
        _atomic_write_json(containment_path, containment)
        _atomic_write_json(
            lineage_path,
            {
                "schema_version": self.SCHEMA_VERSION,
                "research_id": state["research_id"],
                "objective": state["objective"],
                "objective_sha256": state["objective_sha256"],
                "status": state["status"],
                "iterations": state["iterations"],
                "partial_iteration": state["working_iteration"],
                "final_synthesis": state.get("final_synthesis"),
                "execution_evidence": state["execution_evidence"],
                "checkpoint_chain_tip": state.get("_chain_tip"),
            },
        )
        state["artifacts"] = {
            "final_report": self._artifact_reference(report_path, self.evidence_dir),
            "unresolved_items": self._artifact_reference(
                unresolved_path,
                self.evidence_dir,
            ),
            "resource_accounting": self._artifact_reference(
                resource_path,
                self.evidence_dir,
            ),
            "containment": self._artifact_reference(
                containment_path,
                self.evidence_dir,
            ),
            "lineage": self._artifact_reference(lineage_path, self.evidence_dir),
        }

    def _artifact_reference(self, path: Path, approved_root: Path) -> str:
        """F-119. Emit a resolvable pointer through the one shared path contract.

        The evidence tree lives under the STATE root (P4-4), so the install-root-only
        `paths.pointer()` raised and this fell back to `approved-evidence://<relative>` -- a scheme
        nothing can resolve, so a completed RESEARCH run's report pointed at artifacts that could
        not be opened and was REJECTED downstream. `make_pointer` chooses the correct scheme
        (`sovereign-state://` for the evidence tree) and round-trip-validates it, so the reference
        is one the resolver can actually open."""
        resolved = path.resolve(strict=False)
        make_pointer = getattr(self.paths, "make_pointer", None)
        if callable(make_pointer):
            return str(make_pointer(resolved))
        # Legacy paths object without the shared contract: fall back to the install-root pointer.
        pointer_method = getattr(self.paths, "pointer", None)
        if callable(pointer_method):
            return str(pointer_method(resolved))
        relative = resolved.relative_to(approved_root.resolve(strict=False)).as_posix()
        return f"{STATE_POINTER_PREFIX}{relative}"

    def _result(self, state: Mapping[str, Any]) -> ResearchResult:
        return ResearchResult(
            research_id=str(state["research_id"]),
            status=ResearchStatus(str(state["status"])),
            objective_sha256=str(state["objective_sha256"]),
            completed_iterations=int(state["completed_iterations"]),
            next_phase=(
                str(state["next_phase"])
                if state.get("next_phase") is not None
                else None
            ),
            checkpoint_sequence=int(state["checkpoint_sequence"]),
            resumes=int(state["resources"].get("resumes", 0)),
            reason=str(state["reason"]) if state.get("reason") else None,
            artifacts=dict(state.get("artifacts", {})),
            resources=_json_clone(state["resources"]),
        )

    def _emit(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        if self._progress is None:
            return
        payload = {
            "research_id": state["research_id"],
            "timestamp": self._now(),
            **event,
        }
        try:
            self._progress(payload)
        except Exception:
            state["resources"]["progress_callback_errors"] += 1

    @staticmethod
    def _callback_true(callback: StopCallback) -> bool:
        try:
            return bool(callback())
        except Exception:
            # A broken stop controller cannot safely authorize further work.
            return True

    def _mirror_checkpoint_to_store(
        self,
        state: dict[str, Any],
        record: Mapping[str, Any],
        checkpoint_path: Path,
    ) -> None:
        if self.store is None:
            return
        method = None
        for name in (
            "append_research_checkpoint",
            "save_research_checkpoint",
            "upsert_research_checkpoint",
            "record_research_checkpoint",
            "create_research_checkpoint",
        ):
            candidate = getattr(self.store, name, None)
            if callable(candidate):
                method = candidate
                break
        if method is None:
            return
        values = {
            "research_id": state["research_id"],
            "checkpoint_id": f"{int(record['sequence']):08d}",
            "sequence": int(record["sequence"]),
            "iteration": int(state["completed_iterations"]),
            "phase": state.get("next_phase") or str(record["reason"]),
            "status": state["status"],
            "payload": _json_clone(record),
            "data": _json_clone(record),
            "checkpoint": _json_clone(record),
            "state": _json_clone(record),
            "artifact_path": str(checkpoint_path),
            "evidence_pointer": self._artifact_reference(
                checkpoint_path,
                self.state_dir,
            ),
            "session_id": None,
            "created_at": record["created_at"],
        }
        try:
            signature = inspect.signature(method)
            kwargs: dict[str, Any] = {}
            has_var_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            if has_var_kwargs:
                kwargs = values
            else:
                for name, parameter in signature.parameters.items():
                    if name == "self":
                        continue
                    if name in values:
                        kwargs[name] = values[name]
                    elif parameter.default is inspect.Parameter.empty:
                        raise TypeError(
                            f"unsupported required store checkpoint parameter: {name}"
                        )
            method(**kwargs)
        except Exception as exc:
            errors = state["resources"]["store_sync_errors"]
            errors.append(
                {
                    "sequence": int(record["sequence"]),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:1_000],
                }
            )
            if len(errors) > 32:
                del errors[:-32]


# Explicit product-facing name; the shorter class remains convenient in tests.
LongHorizonResearchExecutor = ResearchExecutor


__all__ = [
    "FrozenObjectiveError",
    "LongHorizonResearchExecutor",
    "ResearchAlreadyRunning",
    "ResearchCheckpointError",
    "ResearchContainmentError",
    "ResearchError",
    "ResearchExecutor",
    "ResearchLimits",
    "ResearchPhase",
    "ResearchPhaseError",
    "ResearchResult",
    "ResearchStatus",
]
