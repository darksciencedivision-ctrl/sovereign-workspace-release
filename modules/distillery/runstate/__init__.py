from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from distillery.common import ContractError, sha256_value, utc_now

STAGES = (
    "CREATED",
    "PREFLIGHT",
    "CORPUS_LOCKED",
    "TRAINER_LOCKED",
    "TRAINING",
    "EVALUATING",
    "ADJUDICATING",
    "PACKAGING",
    "PROMOTION_READY",
)
TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED", "BLOCKED")
DEFAULT_RETRY_BUDGET = 3
FAILURE_CLASSES = frozenset(
    {"HARDWARE", "ENVIRONMENT", "INPUT_MISMATCH", "TRAINER_FAILURE", "EVALUATION_FAILURE", "AUTHORIZATION", "UNKNOWN"}
)


def _validate_authorization(authorization: object) -> dict:
    if not isinstance(authorization, dict):
        raise ContractError("run authorization must be a mapping")
    for field in ("authority", "ref"):
        value = authorization.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"run authorization requires non-empty {field}")
    return authorization


def _atomic_write_json(path: Path, document: dict) -> None:
    """Write-once-replace JSON with flush and fsync; directory sync best-effort.

    Platform note: Windows supports fsync on the file handle; directory-handle
    synchronization is POSIX-only, so it is attempted opportunistically and its
    absence is NOT stronger durability than the platform provides.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    encoded = (json_dumps(document) + "\n").encode("utf-8")
    descriptor = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(tmp, path)
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, NotImplementedError):
        pass


def json_dumps(document: dict) -> str:
    import json

    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _integrity_hash(body: dict) -> str:
    return sha256_value({key: value for key, value in body.items() if key != "integrity_hash"})


class RunStateEngine:
    """Durable orchestration spine for governed training runs.

    Strict forward-only semantic boundaries; terminal states are immutable;
    every mutation rewrites one hash-chained record atomically.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ContractError("run_id is required")
        return self.root / run_id / "run_state.json"

    def create(
        self,
        run_id: str,
        *,
        input_hashes: dict,
        authorization: dict,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        experiment_spec_ref: str = "",
    ) -> dict:
        path = self._path(run_id)
        if path.exists():
            raise ContractError(f"run already exists: {run_id}")
        record = {
            "run_id": run_id,
            "stage": "CREATED",
            "status": "ACTIVE",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "input_hashes": dict(input_hashes),
            "experiment_spec_ref": experiment_spec_ref,
            "artifact_refs": [],
            "last_successful_boundary": None,
            "retry_count": 0,
            "retry_budget": retry_budget,
            "authorization": _validate_authorization(authorization),
            "failure_classification": None,
            "resume_pointer": None,
            "events": [{"event": "stage_entered", "stage": "CREATED", "at": utc_now()}],
        }
        record["integrity_hash"] = _integrity_hash(record)
        _atomic_write_json(path, record)
        return record

    def load(self, run_id: str) -> dict:
        path = self._path(run_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ContractError(f"missing run state: {run_id}") from None
        import json

        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContractError(f"corrupt run state {run_id}: {exc}") from None
        stored = record.get("integrity_hash")
        if not stored or stored != _integrity_hash(record):
            raise ContractError(f"run state integrity failure (tampered or partial write): {run_id}")
        return record

    def _mutate(self, run_id: str, mutator) -> dict:
        record = self.load(run_id)
        if record.get("status") == "TERMINAL":
            raise ContractError(f"terminal run cannot mutate: {run_id}")
        mutator(record)
        record["updated_at"] = utc_now()
        record["integrity_hash"] = _integrity_hash(record)
        _atomic_write_json(self._path(run_id), record)
        return record

    def advance(self, run_id: str, *, actor: str = "system") -> dict:
        def mutate(record: dict) -> None:
            current = record["stage"]
            if current not in STAGES:
                raise ContractError(f"unknown current stage: {current}")
            index = STAGES.index(current)
            if index == len(STAGES) - 1:
                raise ContractError("PROMOTION_READY is the final software boundary; promotion itself is human authority")
            target = STAGES[index + 1]
            record["stage"] = target
            record["last_successful_boundary"] = current
            record["events"].append({"event": "stage_entered", "stage": target, "at": utc_now(), "actor": actor})

        return self._mutate(run_id, mutate)

    def attach_artifact(self, run_id: str, artifact_ref: str, artifact_hash: str) -> dict:
        def mutate(record: dict) -> None:
            if not artifact_ref or not artifact_hash:
                raise ContractError("artifact attachment requires ref and hash")
            entry = {"ref": artifact_ref, "sha256": artifact_hash, "attached_at": utc_now()}
            if any(row["ref"] == artifact_ref for row in record["artifact_refs"]):
                raise ContractError(f"duplicate artifact ref: {artifact_ref}")
            record["artifact_refs"].append(entry)

        return self._mutate(run_id, mutate)

    def record_retry(self, run_id: str, *, reason: str) -> dict:
        def mutate(record: dict) -> None:
            if record["retry_count"] >= record["retry_budget"]:
                raise ContractError("retry budget exhausted")
            record["retry_count"] += 1
            record["events"].append({"event": "retry", "reason": reason, "attempt": record["retry_count"], "at": utc_now()})

        return self._mutate(run_id, mutate)

    def fail(self, run_id: str, *, classification: str, detail: str = "") -> dict:
        def mutate(record: dict) -> None:
            if classification not in FAILURE_CLASSES:
                raise ContractError(f"unknown failure classification: {classification}")
            record["status"] = "TERMINAL"
            record["terminal_state"] = "FAILED"
            record["failure_classification"] = classification
            record["resume_pointer"] = record["last_successful_boundary"]
            record["events"].append({"event": "failed", "classification": classification, "detail": detail, "at": utc_now()})

        return self._mutate(run_id, mutate)

    def block(self, run_id: str, *, reason: str) -> dict:
        def mutate(record: dict) -> None:
            record["status"] = "TERMINAL"
            record["terminal_state"] = "BLOCKED"
            record["resume_pointer"] = record["last_successful_boundary"]
            record["events"].append({"event": "blocked", "reason": reason, "at": utc_now()})

        return self._mutate(run_id, mutate)

    def cancel(self, run_id: str, *, actor: str) -> dict:
        def mutate(record: dict) -> None:
            if not actor:
                raise ContractError("cancellation requires an actor")
            record["status"] = "TERMINAL"
            record["terminal_state"] = "CANCELLED"
            record["events"].append({"event": "cancelled", "actor": actor, "at": utc_now()})

        return self._mutate(run_id, mutate)

    def complete(self, run_id: str) -> dict:
        def mutate(record: dict) -> None:
            if record["stage"] != "PROMOTION_READY":
                raise ContractError("only PROMOTION_READY runs can complete")
            record["status"] = "TERMINAL"
            record["terminal_state"] = "COMPLETED"
            record["events"].append({"event": "completed", "at": utc_now()})

        return self._mutate(run_id, mutate)

    def resume(
        self,
        run_id: str,
        *,
        expected_input_hashes: dict,
        required_artifacts: Iterable[str] = (),
    ) -> dict:
        """Fail-closed resume validation.

        Rejects: unknown/corrupt/tampered records, identity mismatch, input
        drift, missing declared artifacts, terminal states, exhausted retry
        budget after failure, or invalid/absent authorization.
        """
        record = self.load(run_id)
        if record["run_id"] != run_id:
            raise ContractError("run identity mismatch")
        if record["input_hashes"] != dict(expected_input_hashes):
            raise ContractError("sealed input hashes do not match run record")
        if record["status"] == "TERMINAL":
            raise ContractError(f"cannot resume terminal run ({record.get('terminal_state')})")
        for artifact_ref in required_artifacts:
            if not any(row["ref"] == artifact_ref for row in record["artifact_refs"]):
                raise ContractError(f"required artifact absent from run record: {artifact_ref}")
        _validate_authorization(record["authorization"])
        if record["stage"] == "TRAINING" and record["retry_count"] >= record["retry_budget"]:
            raise ContractError("cannot resume TRAINING: retry budget exhausted")
        return record


__all__ = [
    "STAGES",
    "TERMINAL_STATES",
    "FAILURE_CLASSES",
    "DEFAULT_RETRY_BUDGET",
    "RunStateEngine"
]
