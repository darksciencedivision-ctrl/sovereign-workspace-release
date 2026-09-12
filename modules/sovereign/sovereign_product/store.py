"""Crash-safe durable product state with tamper-evident event lineage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence


SCHEMA_VERSION = 2
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ROLES = {"user", "sovereign", "system"}
JOB_STATES = {
    "queued",
    "running",
    "completed",
    "rejected",
    "failed",
    "cancelled",
    "interrupted",
    "concurrence_not_reached",
    "timeout",
}
TERMINAL_JOB_STATES = JOB_STATES - {"queued", "running"}
LEGAL_TRANSITIONS = {
    "queued": {"running", "cancelled", "failed", "interrupted"},
    "running": TERMINAL_JOB_STATES,
    # Recovery/retry is explicit and remains visible in the event chain.
    "interrupted": {"queued"},
    "failed": {"queued"},
    "timeout": {"queued"},
}


class StoreError(RuntimeError):
    """Base durable-store failure."""


class StoreIntegrityError(StoreError):
    """SQLite or the material event lineage failed verification."""


class InvalidTransition(StoreError, ValueError):
    """A job transition would make lifecycle history ambiguous."""


class NotFound(StoreError, LookupError):
    """A requested durable entity does not exist."""


class ActiveJobExists(StoreError):
    """A session already has a queued or running job (R05/F-104).

    Carries the existing active job so the caller can report it without a second, racy read.
    """

    def __init__(self, active_job: Mapping[str, Any]) -> None:
        super().__init__("session already has an active job")
        self.active_job = dict(active_job)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _id(value: str | None, prefix: str) -> str:
    candidate = str(value or f"{prefix}_{uuid.uuid4().hex}").strip()
    if not ID_RE.fullmatch(candidate) or ".." in candidate:
        raise ValueError(
            f"{prefix} id must be 1-128 filename-safe ASCII characters"
        )
    return candidate


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _decode(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise StoreIntegrityError("stored JSON is corrupt") from exc


def _event_hash(
    *,
    previous_hash: str,
    timestamp: str,
    entity_type: str,
    entity_id: str,
    action: str,
    payload_json: str,
) -> str:
    canonical = _json(
        {
            "previous_hash": previous_hash,
            "timestamp": timestamp,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "payload_json": payload_json,
        }
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SovereignStore:
    """SQLite authority for sessions, messages, jobs, and continuity state.

    A fresh connection is used per operation so the object is safe to share
    across worker threads. Every material mutation and retention deletion is
    committed in the same transaction as an append-only SHA-256 chain event.
    """

    def __init__(self, db_path: str | Path, *, busy_timeout_ms: int = 8_000) -> None:
        self.db_path = Path(db_path).expanduser().resolve(strict=False)
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migration_lock = threading.RLock()
        self._initialize()
        self.quick_check()
        self.verify_event_chain()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._migration_lock:
            connection = self._connect()
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise StoreIntegrityError(
                        f"database schema {version} is newer than supported {SCHEMA_VERSION}"
                    )
                if version == 0:
                    connection.executescript(
                        """
                        BEGIN EXCLUSIVE;
                        CREATE TABLE IF NOT EXISTS sessions (
                            session_id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            active_model_profile TEXT NOT NULL DEFAULT 'default',
                            orchestration_mode TEXT NOT NULL DEFAULT 'AUTO',
                            metadata_json TEXT NOT NULL DEFAULT '{}',
                            deleted_at TEXT
                        );
                        CREATE TABLE IF NOT EXISTS messages (
                            message_id TEXT PRIMARY KEY,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id)
                                ON DELETE CASCADE,
                            role TEXT NOT NULL CHECK(role IN ('user','sovereign','system')),
                            content TEXT NOT NULL,
                            status TEXT NOT NULL,
                            route TEXT,
                            job_id TEXT,
                            evidence_pointer TEXT,
                            created_at TEXT NOT NULL,
                            metadata_json TEXT NOT NULL DEFAULT '{}'
                        );
                        CREATE INDEX IF NOT EXISTS idx_messages_session_created
                            ON messages(session_id, created_at);
                        CREATE TABLE IF NOT EXISTS jobs (
                            job_id TEXT PRIMARY KEY,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id)
                                ON DELETE CASCADE,
                            route TEXT NOT NULL,
                            status TEXT NOT NULL,
                            input_text TEXT NOT NULL,
                            input_message_id TEXT,
                            output_message_id TEXT,
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            finished_at TEXT,
                            updated_at TEXT NOT NULL,
                            progress_json TEXT NOT NULL DEFAULT '{}',
                            error TEXT,
                            evidence_pointer TEXT,
                            cancel_requested INTEGER NOT NULL DEFAULT 0,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            worker_id TEXT,
                            metadata_json TEXT NOT NULL DEFAULT '{}'
                        );
                        CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                            ON jobs(status, created_at);
                        CREATE INDEX IF NOT EXISTS idx_jobs_session_created
                            ON jobs(session_id, created_at);
                        CREATE TABLE IF NOT EXISTS research_checkpoints (
                            checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            research_id TEXT NOT NULL,
                            session_id TEXT,
                            iteration INTEGER NOT NULL,
                            phase TEXT NOT NULL,
                            state_json TEXT NOT NULL,
                            evidence_pointer TEXT,
                            created_at TEXT NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_research_checkpoint_order
                            ON research_checkpoints(research_id, iteration, checkpoint_id);
                        CREATE TABLE IF NOT EXISTS self_snapshots (
                            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            captured_at TEXT NOT NULL,
                            state_json TEXT NOT NULL,
                            state_sha256 TEXT NOT NULL,
                            evidence_pointer TEXT
                        );
                        CREATE TABLE IF NOT EXISTS meta (
                            key TEXT PRIMARY KEY,
                            value_json TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        );
                        CREATE TABLE IF NOT EXISTS event_log (
                            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            entity_type TEXT NOT NULL,
                            entity_id TEXT NOT NULL,
                            action TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            previous_hash TEXT NOT NULL,
                            event_hash TEXT NOT NULL UNIQUE
                        );
                        PRAGMA user_version=1;
                        COMMIT;
                        """
                    )
                    version = 1
                if version < 2:
                    self._migrate_to_v2(connection)
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()

    def _migrate_to_v2(self, connection: sqlite3.Connection) -> None:
        """R05/F-104. Enforce one active (queued|running) job per session at the DB level with a
        partial unique index. A pre-existing database written by the buggy admission path may
        already hold several active jobs for a session, which would make the index creation fail;
        demote all but the most recent active job per session to `failed` first, recording each in
        the event lineage so the cleanup is not silent."""
        connection.execute("BEGIN EXCLUSIVE")
        try:
            rows = connection.execute(
                """
                SELECT job_id, session_id, created_at, rowid AS rid
                FROM jobs
                WHERE status IN ('queued','running')
                ORDER BY session_id ASC, created_at ASC, rowid ASC
                """
            ).fetchall()
            # Keep the last (newest) active job per session; every earlier one is superseded.
            keep: dict[str, str] = {}
            for row in rows:
                keep[str(row["session_id"])] = str(row["job_id"])
            now = utc_now()
            for row in rows:
                job_id = str(row["job_id"])
                if keep.get(str(row["session_id"])) == job_id:
                    continue
                connection.execute(
                    """
                    UPDATE jobs SET status='failed', finished_at=?, updated_at=?,
                        error=? WHERE job_id=?
                    """,
                    (
                        now,
                        now,
                        "superseded during migration: a session may hold only one active "
                        "job (R05/F-104)",
                        job_id,
                    ),
                )
                self._append_event(
                    connection,
                    "job",
                    job_id,
                    "superseded_by_migration",
                    {"reason": "one_active_job_per_session", "schema_version": 2},
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_active_per_session
                    ON jobs(session_id) WHERE status IN ('queued','running')
                """
            )
            connection.execute("PRAGMA user_version=2")
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        action: str,
        payload: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> str:
        previous = connection.execute(
            "SELECT event_hash FROM event_log ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = str(previous["event_hash"]) if previous else "0" * 64
        timestamp = utc_now()
        payload_json = _json(payload or {})
        digest = _event_hash(
            previous_hash=previous_hash,
            timestamp=timestamp,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload_json=payload_json,
        )
        connection.execute(
            """
            INSERT INTO event_log(
                timestamp, entity_type, entity_id, action, payload_json,
                previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                entity_type,
                entity_id,
                action,
                payload_json,
                previous_hash,
                digest,
            ),
        )
        return digest

    @staticmethod
    def _session_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "active_model_profile": row["active_model_profile"],
            "orchestration_mode": row["orchestration_mode"],
            "metadata": _decode(row["metadata_json"], {}),
            "deleted_at": row["deleted_at"],
        }

    @staticmethod
    def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["message_id"],
            "message_id": row["message_id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "status": row["status"],
            "route": row["route"],
            "job_id": row["job_id"],
            "evidence_pointer": row["evidence_pointer"],
            "timestamp": row["created_at"],
            "created_at": row["created_at"],
            "metadata": _decode(row["metadata_json"], {}),
        }

    @staticmethod
    def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "session_id": row["session_id"],
            "route": row["route"],
            "status": row["status"],
            "input": row["input_text"],
            "input_text": row["input_text"],
            "input_message_id": row["input_message_id"],
            "output_message_id": row["output_message_id"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row["updated_at"],
            "progress": _decode(row["progress_json"], {}),
            "error": row["error"],
            "evidence_pointer": row["evidence_pointer"],
            "cancel_requested": bool(row["cancel_requested"]),
            "attempts": int(row["attempts"]),
            "worker_id": row["worker_id"],
            "metadata": _decode(row["metadata_json"], {}),
        }

    def create_session(
        self,
        session_id: str | None = None,
        *,
        title: str = "New chat",
        active_model_profile: str = "default",
        orchestration_mode: str = "AUTO",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        identifier = _id(session_id, "session")
        now = utc_now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    session_id, title, created_at, updated_at,
                    active_model_profile, orchestration_mode, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    str(title or "New chat")[:200],
                    now,
                    now,
                    str(active_model_profile or "default"),
                    str(orchestration_mode or "AUTO").upper(),
                    _json(dict(metadata or {})),
                ),
            )
            self._append_event(
                connection,
                "session",
                identifier,
                "created",
                {"title": str(title or "New chat")[:200]},
            )
        return self.get_session(identifier, include_messages=True)

    def get_session(
        self, session_id: str, *, include_messages: bool = True
    ) -> dict[str, Any]:
        identifier = _id(session_id, "session")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id=?", (identifier,)
            ).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise NotFound(f"session not found: {identifier}")
            result = self._session_dict(row)
        finally:
            connection.close()
        if include_messages:
            result["messages"] = self.list_messages(identifier)
        return result

    def list_sessions(
        self, *, include_deleted: bool = False, limit: int = 200
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5_000))
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM sessions {where} ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return [self._session_dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        identifier = _id(session_id, "session")
        now = utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET deleted_at=?, updated_at=?
                WHERE session_id=? AND deleted_at IS NULL
                """,
                (now, now, identifier),
            )
            if not cursor.rowcount:
                return False
            self._append_event(
                connection, "session", identifier, "soft_deleted", {"at": now}
            )
        return True

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        message_id: str | None = None,
        status: str = "accepted",
        route: str | None = None,
        job_id: str | None = None,
        evidence_pointer: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = _id(session_id, "session")
        identifier = _id(message_id, "message")
        normalized_role = str(role).lower()
        if normalized_role not in ROLES:
            raise ValueError(f"message role must be one of {sorted(ROLES)}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be non-empty text")
        now = utc_now()
        with self._transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id=? AND deleted_at IS NULL",
                (session,),
            ).fetchone()
            if not exists:
                raise NotFound(f"session not found: {session}")
            connection.execute(
                """
                INSERT INTO messages(
                    message_id, session_id, role, content, status, route, job_id,
                    evidence_pointer, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    session,
                    normalized_role,
                    content,
                    str(status),
                    str(route).upper() if route else None,
                    job_id,
                    evidence_pointer,
                    now,
                    _json(dict(metadata or {})),
                ),
            )
            title_row = connection.execute(
                "SELECT title FROM sessions WHERE session_id=?", (session,)
            ).fetchone()
            title = title_row["title"]
            if title == "New chat" and normalized_role == "user":
                title = " ".join(content.split())[:80]
            connection.execute(
                "UPDATE sessions SET updated_at=?, title=? WHERE session_id=?",
                (now, title, session),
            )
            self._append_event(
                connection,
                "message",
                identifier,
                "appended",
                {
                    "session_id": session,
                    "role": normalized_role,
                    "status": str(status),
                    "route": str(route).upper() if route else None,
                    "content_sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                },
            )
        return self.get_message(identifier)

    def get_message(self, message_id: str) -> dict[str, Any]:
        identifier = _id(message_id, "message")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM messages WHERE message_id=?", (identifier,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFound(f"message not found: {identifier}")
        return self._message_dict(row)

    def list_messages(
        self, session_id: str, *, limit: int = 2_000
    ) -> list[dict[str, Any]]:
        session = _id(session_id, "session")
        limit = max(1, min(int(limit), 20_000))
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM messages WHERE session_id=?
                ORDER BY created_at ASC, rowid ASC LIMIT ?
                """,
                (session, limit),
            ).fetchall()
        finally:
            connection.close()
        return [self._message_dict(row) for row in rows]

    # EvidenceBuilder compatibility alias.
    get_session_messages = list_messages

    def create_job(
        self,
        session_id: str,
        route: str,
        input_text: str,
        *,
        job_id: str | None = None,
        input_message_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        session = _id(session_id, "session")
        identifier = _id(job_id, "job")
        normalized_status = str(status).lower()
        if normalized_status not in JOB_STATES:
            raise ValueError(f"unknown job status: {status}")
        if normalized_status != "queued":
            raise ValueError("new jobs must begin queued")
        if not isinstance(input_text, str) or not input_text.strip():
            raise ValueError("job input must be non-empty text")
        now = utc_now()
        with self._transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM sessions WHERE session_id=? AND deleted_at IS NULL",
                (session,),
            ).fetchone()
            if not exists:
                raise NotFound(f"session not found: {session}")
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, session_id, route, status, input_text,
                    input_message_id, created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    session,
                    str(route).upper(),
                    normalized_status,
                    input_text,
                    input_message_id,
                    now,
                    now,
                    _json(dict(metadata or {})),
                ),
            )
            self._append_event(
                connection,
                "job",
                identifier,
                "created",
                {"session_id": session, "route": str(route).upper()},
            )
        return self.get_job(identifier)

    def admit_job(
        self,
        session_id: str,
        *,
        route: str,
        input_text: str,
        user_content: str,
        user_metadata: Mapping[str, Any] | None = None,
        job_metadata: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        user_message_id: str | None = None,
    ) -> dict[str, Any]:
        """R05/F-104. Admit one turn atomically: the active-job check, the user message insert and
        the job creation are ONE transaction, so two concurrent submissions can never both pass
        the check and leave two jobs (and two user messages) for one session.

        Raises `ActiveJobExists` (carrying the existing job) if the session already has a queued or
        running job; the partial unique index `idx_jobs_one_active_per_session` is the last-resort
        guard, so even a write that somehow raced the SELECT is caught and surfaced the same way
        rather than corrupting state. Returns `{"message": <user message>, "job": <job>}`.
        """
        session = _id(session_id, "session")
        message_identifier = _id(user_message_id, "message")
        job_identifier = _id(job_id, "job")
        normalized_role = "user"
        if not isinstance(user_content, str) or not user_content.strip():
            raise ValueError("message content must be non-empty text")
        if not isinstance(input_text, str) or not input_text.strip():
            raise ValueError("job input must be non-empty text")
        route_value = str(route).upper()
        now = utc_now()
        try:
            with self._transaction() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM sessions WHERE session_id=? AND deleted_at IS NULL",
                    (session,),
                ).fetchone()
                if not exists:
                    raise NotFound(f"session not found: {session}")
                active = connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE session_id=? AND status IN ('queued','running')
                    ORDER BY created_at DESC, rowid DESC LIMIT 1
                    """,
                    (session,),
                ).fetchone()
                if active is not None:
                    raise ActiveJobExists(self._job_dict(active))
                # User message.
                connection.execute(
                    """
                    INSERT INTO messages(
                        message_id, session_id, role, content, status, route, job_id,
                        evidence_pointer, created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_identifier,
                        session,
                        normalized_role,
                        user_content,
                        "accepted",
                        route_value,
                        None,
                        None,
                        now,
                        _json(dict(user_metadata or {})),
                    ),
                )
                title_row = connection.execute(
                    "SELECT title FROM sessions WHERE session_id=?", (session,)
                ).fetchone()
                title = title_row["title"]
                if title == "New chat":
                    title = " ".join(user_content.split())[:80]
                connection.execute(
                    "UPDATE sessions SET updated_at=?, title=? WHERE session_id=?",
                    (now, title, session),
                )
                self._append_event(
                    connection,
                    "message",
                    message_identifier,
                    "appended",
                    {
                        "session_id": session,
                        "role": normalized_role,
                        "status": "accepted",
                        "route": route_value,
                        "content_sha256": hashlib.sha256(
                            user_content.encode("utf-8")
                        ).hexdigest(),
                    },
                )
                # Job, referencing the message just inserted.
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, session_id, route, status, input_text,
                        input_message_id, created_at, updated_at, metadata_json
                    ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)
                    """,
                    (
                        job_identifier,
                        session,
                        route_value,
                        input_text,
                        message_identifier,
                        now,
                        now,
                        _json(dict(job_metadata or {})),
                    ),
                )
                self._append_event(
                    connection,
                    "job",
                    job_identifier,
                    "created",
                    {"session_id": session, "route": route_value},
                )
        except sqlite3.IntegrityError as exc:
            # The partial unique index fired: a concurrent admission won the race. Report the
            # existing active job rather than a raw DB error, and leave no orphan behind (the
            # whole transaction rolled back).
            if "idx_jobs_one_active_per_session" in str(exc):
                current = self.list_jobs(
                    status=("queued", "running"), session_id=session, limit=1
                )
                if current:
                    raise ActiveJobExists(current[0]) from exc
            raise
        return {
            "message": self.get_message(message_identifier),
            "job": self.get_job(job_identifier),
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        identifier = _id(job_id, "job")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (identifier,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFound(f"job not found: {identifier}")
        return self._job_dict(row)

    def list_jobs(
        self,
        *,
        status: str | Iterable[str] | None = None,
        session_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            statuses = [status] if isinstance(status, str) else list(status)
            normalized = [str(item).lower() for item in statuses]
            if any(item not in JOB_STATES for item in normalized):
                raise ValueError("unknown job status filter")
            placeholders = ",".join("?" for _ in normalized)
            clauses.append(f"status IN ({placeholders})")
            parameters.extend(normalized)
        if session_id is not None:
            clauses.append("session_id=?")
            parameters.append(_id(session_id, "session"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(int(limit), 10_000)))
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?",
                parameters,
            ).fetchall()
        finally:
            connection.close()
        return [self._job_dict(row) for row in rows]

    def transition_job(
        self,
        job_id: str,
        new_status: str,
        *,
        expected_status: str | Iterable[str] | None = None,
        error: str | None = None,
        evidence_pointer: str | None = None,
        output_message_id: str | None = None,
        worker_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        identifier = _id(job_id, "job")
        target = str(new_status).lower()
        if target not in JOB_STATES:
            raise ValueError(f"unknown job status: {new_status}")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise NotFound(f"job not found: {identifier}")
            current = str(row["status"])
            if expected_status is not None:
                expected = (
                    {str(expected_status).lower()}
                    if isinstance(expected_status, str)
                    else {str(value).lower() for value in expected_status}
                )
                if current not in expected:
                    raise InvalidTransition(
                        f"job {identifier} is {current}, expected {sorted(expected)}"
                    )
            if target == current:
                return self._job_dict(row)
            allowed = LEGAL_TRANSITIONS.get(current, set())
            if target not in allowed:
                raise InvalidTransition(
                    f"illegal job transition {current} -> {target}"
                )
            now = utc_now()
            started_at = row["started_at"]
            finished_at = row["finished_at"]
            attempts = int(row["attempts"])
            cancel_requested = int(row["cancel_requested"])
            if target == "running":
                started_at = now
                finished_at = None
                attempts += 1
            elif target in TERMINAL_JOB_STATES:
                finished_at = now
            elif target == "queued":
                started_at = None
                finished_at = None
                cancel_requested = 0
            merged_metadata = _decode(row["metadata_json"], {})
            merged_metadata.update(dict(metadata or {}))
            connection.execute(
                """
                UPDATE jobs SET
                    status=?, started_at=?, finished_at=?, updated_at=?,
                    error=?, evidence_pointer=?, output_message_id=?,
                    worker_id=?, attempts=?, cancel_requested=?, metadata_json=?
                WHERE job_id=?
                """,
                (
                    target,
                    started_at,
                    finished_at,
                    now,
                    error,
                    evidence_pointer or row["evidence_pointer"],
                    output_message_id or row["output_message_id"],
                    worker_id or row["worker_id"],
                    attempts,
                    cancel_requested,
                    _json(merged_metadata),
                    identifier,
                ),
            )
            self._append_event(
                connection,
                "job",
                identifier,
                "transitioned",
                {
                    "from": current,
                    "to": target,
                    "error": error,
                    "evidence_pointer": evidence_pointer,
                },
            )
        return self.get_job(identifier)

    def update_job_progress(
        self,
        job_id: str,
        progress: Mapping[str, Any],
    ) -> dict[str, Any]:
        identifier = _id(job_id, "job")
        if not isinstance(progress, Mapping):
            raise TypeError("progress must be a mapping")
        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status, progress_json FROM jobs WHERE job_id=?",
                (identifier,),
            ).fetchone()
            if row is None:
                raise NotFound(f"job not found: {identifier}")
            if row["status"] in TERMINAL_JOB_STATES:
                raise InvalidTransition("terminal job progress cannot change")
            incoming = dict(progress)
            incoming_job_id = incoming.get("job_id")
            if (
                incoming_job_id is not None
                and str(incoming_job_id) != identifier
            ):
                raise InvalidTransition("progress job_id does not match job")
            prior_value = _decode(row["progress_json"], {})
            prior = dict(prior_value) if isinstance(prior_value, Mapping) else {}
            prior_execution = prior.get("execution_id")
            incoming_execution = incoming.get("execution_id")
            if (
                isinstance(prior_execution, str)
                and prior_execution
                and isinstance(incoming_execution, str)
                and incoming_execution
                and incoming_execution != prior_execution
            ):
                raise InvalidTransition(
                    "progress execution_id cannot change within a job"
                )
            prior_sequence = prior.get("sequence")
            incoming_sequence = incoming.get("sequence")
            if incoming_sequence is not None:
                if (
                    isinstance(incoming_sequence, bool)
                    or not isinstance(incoming_sequence, int)
                    or incoming_sequence <= 0
                ):
                    raise ValueError("progress sequence must be a positive integer")
                if (
                    isinstance(prior_sequence, int)
                    and not isinstance(prior_sequence, bool)
                    and incoming_sequence <= prior_sequence
                ):
                    raise InvalidTransition("stale progress sequence")
            prior_percent = prior.get("percent")
            incoming_percent = incoming.get("percent")
            if incoming_percent is not None and (
                isinstance(incoming_percent, bool)
                or not isinstance(incoming_percent, (int, float))
                or not math.isfinite(float(incoming_percent))
                or not 0 <= float(incoming_percent) <= 100
            ):
                raise ValueError(
                    "progress percent must be finite and between 0 and 100"
                )
            if (
                isinstance(prior_percent, (int, float))
                and not isinstance(prior_percent, bool)
                and isinstance(incoming_percent, (int, float))
                and not isinstance(incoming_percent, bool)
                and float(incoming_percent) < float(prior_percent)
            ):
                raise InvalidTransition("progress percent cannot regress")
            merged = {**prior, **incoming}
            connection.execute(
                "UPDATE jobs SET progress_json=?, updated_at=? WHERE job_id=?",
                (_json(merged), now, identifier),
            )
            self._append_event(
                connection,
                "job",
                identifier,
                "progress",
                {"progress": merged},
            )
        return self.get_job(identifier)

    def complete_job_with_answer(
        self,
        job_id: str,
        *,
        content: str,
        evidence_pointer: str | None = None,
        message_metadata: Mapping[str, Any] | None = None,
        job_metadata: Mapping[str, Any] | None = None,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """R07. Finish a running job atomically: the cancel check, the accepted answer message, the
        progress bump and the running->completed transition are ONE transaction. It is therefore
        impossible to end with an `accepted` output message attached to a job that is not
        `completed` -- a crash before commit leaves the job running (to be recovered) with no
        answer; a cancel that arrived while the answer was being computed is honoured here and the
        answer is discarded.

        Returns `{"job": <job>, "outcome": "completed"|"cancelled", "message": <message?>}`.
        """
        identifier = _id(job_id, "job")
        message_identifier = _id(message_id, "message")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("answer content must be non-empty text")
        now = utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise NotFound(f"job not found: {identifier}")
            current = str(row["status"])
            if current != "running":
                raise InvalidTransition(
                    f"job {identifier} is {current}, expected running"
                )
            session = str(row["session_id"])
            # Cancel check, inside the transaction: a cancel requested while the answer was being
            # produced wins, and no accepted message is written.
            if int(row["cancel_requested"]):
                connection.execute(
                    """
                    UPDATE jobs SET status='cancelled', finished_at=?, updated_at=?
                    WHERE job_id=?
                    """,
                    (now, now, identifier),
                )
                self._append_event(
                    connection,
                    "job",
                    identifier,
                    "transitioned",
                    {"from": "running", "to": "cancelled", "reason": "cancel_requested"},
                )
                return {"job": self._job_dict_by_id(connection, identifier),
                        "outcome": "cancelled", "message": None}
            # Accepted answer message.
            connection.execute(
                """
                INSERT INTO messages(
                    message_id, session_id, role, content, status, route, job_id,
                    evidence_pointer, created_at, metadata_json
                ) VALUES (?, ?, 'sovereign', ?, 'accepted', ?, ?, ?, ?, ?)
                """,
                (
                    message_identifier,
                    session,
                    content,
                    str(row["route"]).upper() if row["route"] else None,
                    identifier,
                    evidence_pointer,
                    now,
                    _json(dict(message_metadata or {})),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at=? WHERE session_id=?", (now, session)
            )
            self._append_event(
                connection,
                "message",
                message_identifier,
                "appended",
                {
                    "session_id": session,
                    "role": "sovereign",
                    "status": "accepted",
                    "route": str(row["route"]).upper() if row["route"] else None,
                    "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                },
            )
            # Progress to 100 and the completion transition, same transaction.
            prior_progress = _decode(row["progress_json"], {})
            progress = dict(prior_progress) if isinstance(prior_progress, Mapping) else {}
            progress.update({"percent": 100, "stage": "completed"})
            merged_metadata = _decode(row["metadata_json"], {})
            merged_metadata.update(dict(job_metadata or {}))
            connection.execute(
                """
                UPDATE jobs SET status='completed', finished_at=?, updated_at=?,
                    progress_json=?, evidence_pointer=?, output_message_id=?, metadata_json=?
                WHERE job_id=?
                """,
                (
                    now,
                    now,
                    _json(progress),
                    evidence_pointer or row["evidence_pointer"],
                    message_identifier,
                    _json(merged_metadata),
                    identifier,
                ),
            )
            self._append_event(
                connection,
                "job",
                identifier,
                "transitioned",
                {
                    "from": "running",
                    "to": "completed",
                    "evidence_pointer": evidence_pointer,
                    "output_message_id": message_identifier,
                },
            )
            return {"job": self._job_dict_by_id(connection, identifier),
                    "outcome": "completed",
                    "message": self._message_dict(
                        connection.execute(
                            "SELECT * FROM messages WHERE message_id=?",
                            (message_identifier,),
                        ).fetchone()
                    )}

    @staticmethod
    def _job_dict_by_id(connection: sqlite3.Connection, job_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise NotFound(f"job not found: {job_id}")
        return SovereignStore._job_dict(row)

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        identifier = _id(job_id, "job")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise NotFound(f"job not found: {identifier}")
            status = str(row["status"])
            if status in TERMINAL_JOB_STATES:
                return self.get_job(identifier)
            now = utc_now()
            if status == "queued":
                connection.execute(
                    """
                    UPDATE jobs SET status='cancelled', cancel_requested=1,
                        finished_at=?, updated_at=?
                    WHERE job_id=?
                    """,
                    (now, now, identifier),
                )
                action = "cancelled_before_start"
            else:
                connection.execute(
                    "UPDATE jobs SET cancel_requested=1, updated_at=? WHERE job_id=?",
                    (now, identifier),
                )
                action = "cancel_requested"
            self._append_event(
                connection, "job", identifier, action, {"prior_status": status}
            )
        return self.get_job(identifier)

    def recover_incomplete_jobs(self) -> dict[str, list[str]]:
        interrupted: list[str] = []
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT job_id, progress_json, metadata_json
                FROM jobs
                WHERE status='running'
                ORDER BY created_at
                """
            ).fetchall()
            now = utc_now()
            for row in rows:
                identifier = str(row["job_id"])
                progress = _decode(row["progress_json"], {})
                metadata = _decode(row["metadata_json"], {})
                recovery_pointer = (
                    progress.get("evidence_pointer")
                    if isinstance(progress, Mapping)
                    else None
                )
                if not (
                    isinstance(recovery_pointer, str)
                    and recovery_pointer.startswith("sovereign://")
                    and ".." not in recovery_pointer
                ):
                    recovery_pointer = None
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["recovery"] = {
                    "classification": "interrupted_on_service_restart",
                    "execution_id": (
                        progress.get("execution_id")
                        if isinstance(progress, Mapping)
                        else None
                    ),
                    "job_id": identifier,
                    "evidence_pointer": recovery_pointer,
                }
                connection.execute(
                    """
                    UPDATE jobs SET status='interrupted', finished_at=?, updated_at=?,
                        error='service restarted while job was running',
                        evidence_pointer=COALESCE(?, evidence_pointer),
                        metadata_json=?
                    WHERE job_id=?
                    """,
                    (
                        now,
                        now,
                        recovery_pointer,
                        _json(metadata),
                        identifier,
                    ),
                )
                self._append_event(
                    connection,
                    "job",
                    identifier,
                    "recovered_as_interrupted",
                    {
                        "reason": "service restart; no safe execution checkpoint",
                        "execution_id": metadata["recovery"]["execution_id"],
                        "evidence_pointer": recovery_pointer,
                    },
                )
                interrupted.append(identifier)
            queued = [
                str(row["job_id"])
                for row in connection.execute(
                    "SELECT job_id FROM jobs WHERE status='queued' ORDER BY created_at"
                ).fetchall()
            ]
        return {"queued": queued, "interrupted": interrupted}

    def append_research_checkpoint(
        self,
        research_id: str,
        *,
        session_id: str | None,
        iteration: int,
        phase: str,
        state: Mapping[str, Any],
        evidence_pointer: str | None = None,
    ) -> dict[str, Any]:
        identifier = _id(research_id, "research")
        if int(iteration) < 0:
            raise ValueError("iteration must be non-negative")
        if not str(phase).strip():
            raise ValueError("phase must be non-empty")
        now = utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_checkpoints(
                    research_id, session_id, iteration, phase, state_json,
                    evidence_pointer, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    session_id,
                    int(iteration),
                    str(phase),
                    _json(dict(state)),
                    evidence_pointer,
                    now,
                ),
            )
            checkpoint_id = int(cursor.lastrowid)
            self._append_event(
                connection,
                "research",
                identifier,
                "checkpoint",
                {
                    "checkpoint_id": checkpoint_id,
                    "iteration": int(iteration),
                    "phase": str(phase),
                },
            )
        return self.list_research_checkpoints(identifier)[-1]

    def list_research_checkpoints(
        self, research_id: str, *, limit: int = 10_000
    ) -> list[dict[str, Any]]:
        identifier = _id(research_id, "research")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM research_checkpoints WHERE research_id=?
                ORDER BY checkpoint_id ASC LIMIT ?
                """,
                (identifier, max(1, min(int(limit), 100_000))),
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "checkpoint_id": int(row["checkpoint_id"]),
                "research_id": row["research_id"],
                "session_id": row["session_id"],
                "iteration": int(row["iteration"]),
                "phase": row["phase"],
                "state": _decode(row["state_json"], {}),
                "evidence_pointer": row["evidence_pointer"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_self_snapshot(
        self,
        state: Mapping[str, Any],
        *,
        evidence_pointer: str | None = None,
    ) -> dict[str, Any]:
        state_json = _json(dict(state))
        digest = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
        now = utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO self_snapshots(
                    captured_at, state_json, state_sha256, evidence_pointer
                ) VALUES (?, ?, ?, ?)
                """,
                (now, state_json, digest, evidence_pointer),
            )
            identifier = str(cursor.lastrowid)
            self._append_event(
                connection,
                "self_snapshot",
                identifier,
                "captured",
                {"state_sha256": digest},
            )
        return self.list_self_snapshots(limit=1)[0]

    def list_self_snapshots(self, *, limit: int = 100) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM self_snapshots
                ORDER BY snapshot_id DESC LIMIT ?
                """,
                (max(1, min(int(limit), 10_000)),),
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "snapshot_id": int(row["snapshot_id"]),
                "captured_at": row["captured_at"],
                "state": _decode(row["state_json"], {}),
                "state_sha256": row["state_sha256"],
                "evidence_pointer": row["evidence_pointer"],
            }
            for row in rows
        ]

    def set_meta(self, key: str, value: Any) -> Any:
        normalized = str(key).strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("meta key must be 1-200 characters")
        now = utc_now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO meta(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (normalized, _json(value), now),
            )
            self._append_event(
                connection,
                "meta",
                normalized,
                "set",
                {"value_sha256": hashlib.sha256(_json(value).encode()).hexdigest()},
            )
        return value

    def get_meta(self, key: str, default: Any = None) -> Any:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT value_json FROM meta WHERE key=?", (str(key),)
            ).fetchone()
        finally:
            connection.close()
        return default if row is None else _decode(row["value_json"], default)

    def get_meta_recovering(self, key: str, default: Any = None) -> Any:
        """Read metadata and atomically replace malformed JSON with a default.

        Recovery is explicit in the append-only event lineage and retains the
        corrupt byte digest without copying attacker-controlled content into
        logs or responses.
        """

        normalized = str(key).strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("meta key must be 1-200 characters")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT value_json FROM meta WHERE key=?",
                (normalized,),
            ).fetchone()
            if row is None:
                return default
            raw = str(row["value_json"])
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                replacement = _json(default)
                now = utc_now()
                connection.execute(
                    "UPDATE meta SET value_json=?, updated_at=? WHERE key=?",
                    (replacement, now, normalized),
                )
                self._append_event(
                    connection,
                    "meta",
                    normalized,
                    "corrupt_json_recovered",
                    {
                        "corrupt_value_sha256": hashlib.sha256(
                            raw.encode("utf-8")
                        ).hexdigest(),
                        "replacement_sha256": hashlib.sha256(
                            replacement.encode("utf-8")
                        ).hexdigest(),
                    },
                )
                return default

    def get_meta_validated_recovering(
        self,
        key: str,
        default: Any,
        validator: Callable[[Any], Any],
    ) -> Any:
        """Read, validate, normalize, and durably repair one metadata value."""

        if not callable(validator):
            raise TypeError("validator must be callable")
        normalized_key = str(key).strip()
        if not normalized_key or len(normalized_key) > 200:
            raise ValueError("meta key must be 1-200 characters")
        validated_default = validator(default)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT value_json FROM meta WHERE key=?",
                (normalized_key,),
            ).fetchone()
            if row is None:
                return validated_default
            raw = str(row["value_json"])
            reason: str | None = None
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                decoded = default
                reason = "malformed_json"
            try:
                normalized = validator(decoded)
            except (TypeError, ValueError):
                normalized = validated_default
                reason = "schema_validation_failed"
            decoded_canonical = (
                _json(decoded) if reason != "malformed_json" else raw
            )
            normalized_json = _json(normalized)
            if reason is None and decoded_canonical != normalized_json:
                reason = "normalized_to_enforced_schema"
            if reason is None:
                return normalized
            now = utc_now()
            connection.execute(
                "UPDATE meta SET value_json=?, updated_at=? WHERE key=?",
                (normalized_json, now, normalized_key),
            )
            self._append_event(
                connection,
                "meta",
                normalized_key,
                "invalid_value_recovered",
                {
                    "reason": reason,
                    "observed_value_sha256": hashlib.sha256(
                        raw.encode("utf-8")
                    ).hexdigest(),
                    "replacement_sha256": hashlib.sha256(
                        normalized_json.encode("utf-8")
                    ).hexdigest(),
                },
            )
            return normalized

    def list_meta(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM meta ORDER BY key").fetchall()
        finally:
            connection.close()
        return {str(row["key"]): _decode(row["value_json"], None) for row in rows}

    def status_summary(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            session_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE deleted_at IS NULL"
                ).fetchone()[0]
            )
            message_count = int(
                connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            )
            counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
                ).fetchall()
            }
            event = connection.execute(
                "SELECT sequence, event_hash FROM event_log ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
        return {
            "available": True,
            "schema_version": SCHEMA_VERSION,
            "database": str(self.db_path),
            "sessions": session_count,
            "messages": message_count,
            "jobs_by_status": counts,
            "running_jobs": counts.get("running", 0),
            "queued_jobs": counts.get("queued", 0),
            "event_count": int(event["sequence"]) if event else 0,
            "event_chain_head": str(event["event_hash"]) if event else "0" * 64,
        }

    # Introspection compatibility alias.
    summary = status_summary

    def quick_check(self) -> bool:
        connection = self._connect()
        try:
            rows = connection.execute("PRAGMA quick_check").fetchall()
        except sqlite3.DatabaseError as exc:
            raise StoreIntegrityError(f"SQLite quick_check failed: {exc}") from exc
        finally:
            connection.close()
        results = [str(row[0]) for row in rows]
        if results != ["ok"]:
            raise StoreIntegrityError("SQLite quick_check: " + "; ".join(results))
        return True

    def verify_event_chain(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM event_log ORDER BY sequence ASC"
            ).fetchall()
        finally:
            connection.close()
        previous = "0" * 64
        expected_sequence = 1
        for row in rows:
            sequence = int(row["sequence"])
            if sequence != expected_sequence:
                raise StoreIntegrityError(
                    f"event sequence gap: expected {expected_sequence}, found {sequence}"
                )
            if row["previous_hash"] != previous:
                raise StoreIntegrityError(
                    f"event {sequence} previous hash does not match chain head"
                )
            expected = _event_hash(
                previous_hash=previous,
                timestamp=str(row["timestamp"]),
                entity_type=str(row["entity_type"]),
                entity_id=str(row["entity_id"]),
                action=str(row["action"]),
                payload_json=str(row["payload_json"]),
            )
            if row["event_hash"] != expected:
                raise StoreIntegrityError(f"event {sequence} hash mismatch")
            previous = expected
            expected_sequence += 1
        return {
            "ok": True,
            "events": len(rows),
            "head": previous,
        }

    def apply_retention(
        self,
        *,
        deleted_session_days: int = 30,
        terminal_job_days: int = 90,
    ) -> dict[str, int]:
        """Purge only operator-deleted sessions and detached terminal jobs.

        Event lineage is retained, and every purge is itself appended. Jobs
        belonging to live sessions are never removed by time alone.
        """

        if deleted_session_days < 0 or terminal_job_days < 0:
            raise ValueError("retention days cannot be negative")
        now = datetime.now(timezone.utc)
        session_cutoff = (now - timedelta(days=deleted_session_days)).isoformat().replace(
            "+00:00", "Z"
        )
        job_cutoff = (now - timedelta(days=terminal_job_days)).isoformat().replace(
            "+00:00", "Z"
        )
        deleted_sessions = 0
        deleted_jobs = 0
        with self._transaction() as connection:
            sessions = connection.execute(
                """
                SELECT session_id FROM sessions
                WHERE deleted_at IS NOT NULL AND deleted_at <= ?
                """,
                (session_cutoff,),
            ).fetchall()
            for row in sessions:
                identifier = str(row["session_id"])
                self._append_event(
                    connection,
                    "session",
                    identifier,
                    "retention_purge",
                    {"deleted_before": session_cutoff},
                )
                connection.execute(
                    "DELETE FROM sessions WHERE session_id=?", (identifier,)
                )
                deleted_sessions += 1
            # Normally zero because jobs have a required session FK. This
            # branch supports future migrated rows only if they are detached.
            jobs = connection.execute(
                f"""
                SELECT job_id FROM jobs
                WHERE status IN ({','.join('?' for _ in TERMINAL_JOB_STATES)})
                  AND finished_at IS NOT NULL AND finished_at <= ?
                  AND session_id NOT IN (SELECT session_id FROM sessions)
                """,
                (*sorted(TERMINAL_JOB_STATES), job_cutoff),
            ).fetchall()
            for row in jobs:
                identifier = str(row["job_id"])
                self._append_event(
                    connection,
                    "job",
                    identifier,
                    "retention_purge",
                    {"finished_before": job_cutoff},
                )
                connection.execute("DELETE FROM jobs WHERE job_id=?", (identifier,))
                deleted_jobs += 1
        return {"sessions": deleted_sessions, "jobs": deleted_jobs}

    def close(self) -> None:
        """Compatibility no-op: operations own and close their connections."""
