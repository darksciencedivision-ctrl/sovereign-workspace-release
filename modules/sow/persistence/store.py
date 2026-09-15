"""Sovereign durable store: SQLite (WAL) — data integrity only, no authorization
(Plan sections 3.2, 9.4, 9.6; D-PERSIST-01, D-MCP-03; invariants 11/12/13).

Enforces, at the storage boundary:
  - immutable append: memory versions are insert-only; no UPDATE/DELETE of a version.
  - provenance on every shared write (I-M5): rows without complete provenance are refused
    (schema-validated against memory@1.0 before insert).
  - CAS head pointers (D-MCP-03): a logical key's head advances only if the caller's
    expected head matches; otherwise an explicit conflict_record is written and BOTH
    versions are preserved — never a silent last-write-wins (invariant 13).
This module contains NO role/scope logic; authorization is the control plane's job (I-M2).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"
_MEMORY_SCHEMA = json.loads((_SCHEMA_DIR / "memory.schema.json").read_text(encoding="utf-8"))
_CONFLICT_SCHEMA = {**_MEMORY_SCHEMA["definitions"]["conflict_record"], "$schema": "http://json-schema.org/draft-07/schema#"}
_FMT = jsonschema.FormatChecker()  # actually enforce date-time etc. (spec-audit F12)


# CR-003 (dependent correction): jsonschema only registers a built-in "date-time" checker when the
# optional rfc3339-validator/fqdn package is installed. On this environment it is NOT, so _FMT
# silently skipped date-time entirely — meaning neither the append path nor commit_version actually
# rejected malformed timestamps despite passing format_checker=_FMT. Register a dependency-free
# checker so the memory@1.0 date-time contract (provenance.ts) is enforced deterministically on
# every write path.
@_FMT.checks("date-time", raises=ValueError)
def _is_iso_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True  # non-strings are rejected by the type keyword, not the format keyword
    from datetime import datetime
    candidate = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    datetime.fromisoformat(candidate)  # raises ValueError on a malformed timestamp
    return True

GENESIS_HEAD = ""  # a key with no prior head


@dataclass(frozen=True)
class CasResult:
    ok: bool
    head_ref: str
    conflict: dict[str, Any] | None = None


class StoreError(Exception):
    pass


class SovereignStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, isolation_level=None, timeout=30.0)
            # Conductor and worker MCP adapters may start concurrently.  Apply the wait policy
            # before WAL negotiation so startup waits for a sibling schema transaction instead of
            # spuriously failing with "database is locked".
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        with self._write_lock:
            conn = self._conn()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    ref TEXT PRIMARY KEY,            -- entry_id@version
                    entry_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    prev_version_ref TEXT,
                    provenance_json TEXT NOT NULL,
                    entry_json TEXT NOT NULL,
                    inserted_ts REAL NOT NULL,
                    UNIQUE(entry_id, version)
                );
                CREATE TABLE IF NOT EXISTS heads (
                    key TEXT PRIMARY KEY,
                    head_ref TEXT NOT NULL,
                    updated_ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    key TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    conflict_json TEXT NOT NULL,
                    created_ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_meta (
                    artifact_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    inserted_ts REAL NOT NULL,
                    PRIMARY KEY (artifact_id, project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_mem_status ON memory_entries(project_id, status);
                CREATE INDEX IF NOT EXISTS idx_mem_entry ON memory_entries(entry_id);
                CREATE TABLE IF NOT EXISTS operational_tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_node_ids_json TEXT NOT NULL,
                    task_json TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operational_messages (
                    message_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    sender_node_id TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    message_kind TEXT NOT NULL,
                    message_json TEXT NOT NULL,
                    created_ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operational_debates (
                    debate_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    debate_json TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    updated_ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ops_tasks_project ON operational_tasks(project_id, updated_ts);
                CREATE INDEX IF NOT EXISTS idx_ops_messages_scope ON operational_messages(project_id, task_id, created_ts);
                CREATE INDEX IF NOT EXISTS idx_ops_debates_scope ON operational_debates(project_id, task_id, updated_ts);
                -- CR-029: indexes matching the journal retrieval access patterns. Created here so
                -- legacy stores acquire them on the next write-open (idempotent, transactional).
                -- Private-journal read: WHERE project_id, tier, provenance.author_node ORDER BY
                -- inserted_ts (expression index because author lives in the JSON blob).
                CREATE INDEX IF NOT EXISTS idx_mem_private ON memory_entries(
                    project_id, tier, json_extract(entry_json, '$.provenance.author_node'), inserted_ts);
                -- The private/shared head join tests h.head_ref = me.ref; without this the heads
                -- side is a full scan per candidate row.
                CREATE INDEX IF NOT EXISTS idx_heads_head_ref ON heads(head_ref);
                -- Public journal read over artifact_meta: WHERE project_id AND created_by_node
                -- ORDER BY inserted_ts (created_by_node lives in the JSON blob).
                CREATE INDEX IF NOT EXISTS idx_artifact_journal ON artifact_meta(
                    project_id, json_extract(meta_json, '$.created_by_node'), inserted_ts);
                """
            )

    # -- memory versions (immutable append) -----------------------------------
    def append_memory_version(self, entry: dict[str, Any]) -> str:
        """Insert an immutable memory version. Provenance + shape are schema-enforced.
        Returns the version ref (entry_id@version). Never updates an existing version."""
        try:
            jsonschema.validate(entry, _MEMORY_SCHEMA, format_checker=_FMT)
        except jsonschema.ValidationError as exc:
            raise StoreError(f"memory entry violates memory@1.0 (provenance/shape): {exc.message}") from exc
        ref = f"{entry['entry_id']}@{entry['version']}"
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute(
                    "INSERT INTO memory_entries (ref, entry_id, version, project_id, tier, kind, status, "
                    "content_hash, prev_version_ref, provenance_json, entry_json, inserted_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ref, entry["entry_id"], entry["version"], entry["project_id"], entry["tier"],
                     entry["kind"], entry["status"], entry["content_hash"], entry.get("prev_version_ref"),
                     json.dumps(entry["provenance"], sort_keys=True), json.dumps(entry, sort_keys=True), time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"version {ref} already exists — versions are immutable") from exc
        return ref

    def get_entry(self, ref: str) -> dict[str, Any] | None:
        row = self._conn().execute("SELECT entry_json FROM memory_entries WHERE ref=?", (ref,)).fetchone()
        return json.loads(row["entry_json"]) if row else None

    def list_by_status(self, project_id: str, status: str) -> list[dict[str, Any]]:
        """Return only CURRENT-HEAD shared-project versions with this status. Joining on
        heads excludes stale prior versions and CAS-loser forks (which are appended but
        never become the head), so a race-losing or superseded version can never surface as
        current/accepted state (spec-audit F2). Private/local tiers are never returned by the
        shared read path (invariant 9 tier isolation)."""
        rows = self._conn().execute(
            "SELECT me.entry_json FROM memory_entries me JOIN heads h ON h.head_ref = me.ref "
            "WHERE me.project_id=? AND me.status=? AND me.tier='shared_project' ORDER BY me.inserted_ts",
            (project_id, status),
        ).fetchall()
        return [json.loads(r["entry_json"]) for r in rows]

    # -- CAS head pointers (D-MCP-03 fencing) ---------------------------------
    def cas_advance_head(self, key: str, expected_head: str, new_ref: str, *, conflict_id: str,
                         project_id: str = "unknown") -> CasResult:
        """Lower-level head-only CAS (used by unit tests; the service uses commit_version).
        Advance key's head to new_ref iff current head == expected_head, else write an
        explicit conflict_record and DO NOT overwrite. Atomic under BEGIN IMMEDIATE + the
        process write lock."""
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                # CR-036: refuse to point a head at a version that does not exist. Without this a
                # direct/future caller could create a dangling head that breaks every read of the
                # key. The existing head is left untouched on refusal (rollback below).
                if not conn.execute("SELECT 1 FROM memory_entries WHERE ref=?", (new_ref,)).fetchone():
                    conn.execute("ROLLBACK")
                    raise StoreError(f"cannot advance head {key!r} to nonexistent version {new_ref!r}")
                row = conn.execute("SELECT head_ref FROM heads WHERE key=?", (key,)).fetchone()
                current = row["head_ref"] if row else GENESIS_HEAD
                if current != expected_head:
                    conflict = _make_conflict(conflict_id, key, expected_head, current, new_ref)
                    conn.execute("INSERT OR IGNORE INTO conflicts VALUES (?,?,?,?,?)",
                                 (conflict_id, key, project_id, json.dumps(conflict, sort_keys=True), time.time()))
                    conn.execute("COMMIT")
                    return CasResult(ok=False, head_ref=current, conflict=conflict)
                if row:
                    conn.execute("UPDATE heads SET head_ref=?, updated_ts=? WHERE key=?", (new_ref, time.time(), key))
                else:
                    conn.execute("INSERT INTO heads (key, head_ref, updated_ts) VALUES (?,?,?)", (key, new_ref, time.time()))
                conn.execute("COMMIT")
                return CasResult(ok=True, head_ref=new_ref)
            except StoreError:
                raise  # already rolled back at the raise site; do not ROLLBACK a closed txn
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def commit_version(self, entry: dict[str, Any], key: str, expected_head: str, *, conflict_id: str) -> CasResult:
        """Atomically append an immutable version and (if the caller's expected head still
        holds) advance the head — both under one BEGIN IMMEDIATE + write lock. The version
        NUMBER is assigned here, not by the caller, so two concurrent writers can never mint
        the same ref. On a clean CAS the head advances to the new version. On a stale CAS the
        writer's version is STILL persisted (as a fork off its ancestor) so no work is lost,
        the head is left on the winner, and a conflict record lists both versions — never a
        silent last-write-wins (invariant 13). `entry` must omit entry_id-version/ref; they
        are assigned. Returns the committed ref in head_ref."""
        entry_id = entry["entry_id"]
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                mx = conn.execute("SELECT COALESCE(MAX(version), 0) mx FROM memory_entries WHERE entry_id=?",
                                  (entry_id,)).fetchone()["mx"]
                version = mx + 1
                ref = f"{entry_id}@{version}"
                row = conn.execute("SELECT head_ref FROM heads WHERE key=?", (key,)).fetchone()
                current = row["head_ref"] if row else GENESIS_HEAD
                clean = current == expected_head
                full = {**entry, "version": version,
                        "prev_version_ref": (expected_head or None), "schema": "memory@1.0"}
                try:
                    # CR-003: use the shared format checker here too. append_memory_version()
                    # validated with format_checker=_FMT, but this canonical commit path omitted it,
                    # so a malformed date-time (e.g. ts='not-a-date') was accepted by commit_version
                    # though the append path rejected it — an inconsistent provenance/timestamp
                    # contract across write paths.
                    jsonschema.validate(full, _MEMORY_SCHEMA, format_checker=_FMT)
                except jsonschema.ValidationError as exc:
                    conn.execute("ROLLBACK")
                    raise StoreError(f"memory entry violates memory@1.0 (provenance/shape): {exc.message}") from exc
                conn.execute(
                    "INSERT INTO memory_entries (ref, entry_id, version, project_id, tier, kind, status, "
                    "content_hash, prev_version_ref, provenance_json, entry_json, inserted_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ref, entry_id, version, full["project_id"], full["tier"], full["kind"], full["status"],
                     full["content_hash"], full["prev_version_ref"], json.dumps(full["provenance"], sort_keys=True),
                     json.dumps(full, sort_keys=True), time.time()),
                )
                if not clean:
                    conflict = _make_conflict(conflict_id, key, expected_head, current, ref)
                    conn.execute("INSERT OR IGNORE INTO conflicts VALUES (?,?,?,?,?)",
                                 (conflict_id, key, full["project_id"], json.dumps(conflict, sort_keys=True), time.time()))
                    conn.execute("COMMIT")  # loser's version preserved as a fork; head untouched
                    return CasResult(ok=False, head_ref=ref, conflict=conflict)
                if row:
                    conn.execute("UPDATE heads SET head_ref=?, updated_ts=? WHERE key=?", (ref, time.time(), key))
                else:
                    conn.execute("INSERT INTO heads (key, head_ref, updated_ts) VALUES (?,?,?)", (key, ref, time.time()))
                conn.execute("COMMIT")
                return CasResult(ok=True, head_ref=ref)
            except StoreError:
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_head(self, key: str) -> str:
        row = self._conn().execute("SELECT head_ref FROM heads WHERE key=?", (key,)).fetchone()
        return row["head_ref"] if row else GENESIS_HEAD

    def list_conflicts(self, project_id: str, key: str | None = None) -> list[dict[str, Any]]:
        """Project-scoped (spec-audit F4): a node never sees another project's conflicts."""
        if key is None:
            rows = self._conn().execute(
                "SELECT conflict_json FROM conflicts WHERE project_id=? ORDER BY created_ts", (project_id,)).fetchall()
        else:
            rows = self._conn().execute(
                "SELECT conflict_json FROM conflicts WHERE project_id=? AND key=? ORDER BY created_ts",
                (project_id, key)).fetchall()
        return [json.loads(r["conflict_json"]) for r in rows]

    # -- artifact metadata (project-scoped, spec-audit F4) ---------------------
    def put_artifact_meta(self, meta: dict[str, Any], project_id: str) -> None:
        with self._write_lock:
            self._conn().execute(
                "INSERT OR IGNORE INTO artifact_meta VALUES (?,?,?,?)",
                (meta["artifact_id"], project_id, json.dumps(meta, sort_keys=True), time.time()),
            )

    def get_artifact_meta(self, artifact_id: str, project_id: str) -> dict[str, Any] | None:
        row = self._conn().execute(
            "SELECT meta_json FROM artifact_meta WHERE artifact_id=? AND project_id=?",
            (artifact_id, project_id)).fetchone()
        return json.loads(row["meta_json"]) if row else None

    def has_entry(self, ref: str) -> bool:
        return self._conn().execute("SELECT 1 FROM memory_entries WHERE ref=?", (ref,)).fetchone() is not None

    def all_artifact_refs(self) -> list[tuple[str, str]]:
        """CR-035: (artifact_id/content_hash, project_id) for every artifact metadata row, so a
        referential integrity check can confirm each names a real CAS blob."""
        rows = self._conn().execute("SELECT artifact_id, project_id FROM artifact_meta").fetchall()
        return [(r["artifact_id"], r["project_id"]) for r in rows]

    def all_memory_content_hashes(self) -> list[str]:
        """CR-035: every distinct CAS content hash referenced by a memory version."""
        rows = self._conn().execute("SELECT DISTINCT content_hash FROM memory_entries").fetchall()
        return [r["content_hash"] for r in rows]

    # -- operational collaboration state ------------------------------------
    # Two entry points per record kind, and no third (U330): CREATE, which refuses to overwrite,
    # and MUTATE, which reads/modifies/writes inside one BEGIN IMMEDIATE. The blind
    # `put_operational_task`/`put_operational_debate` upserts they replace were how five of the
    # seven orchestration writers wrote a successor built from a stale snapshot — the silent
    # last-write-wins invariant 13 forbids. They are deleted rather than deprecated: a writer
    # cannot reach the unfenced path if the unfenced path does not exist.
    def create_operational_task(self, task: dict[str, Any]) -> None:
        """Insert one project-scoped task. An existing id is an error, never an overwrite."""
        now = time.time()
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                if conn.execute("SELECT 1 FROM operational_tasks WHERE task_id=?",
                                (task["task_id"],)).fetchone():
                    raise StoreError(f"operational task {task['task_id']} already exists")
                conn.execute(
                    "INSERT INTO operational_tasks "
                    "(task_id, project_id, thread_id, objective, status, owner_node_ids_json, task_json, created_ts, updated_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (task["task_id"], task["project_id"], task["thread_id"], task["objective"],
                     task["status"], json.dumps(task["owner_node_ids"], sort_keys=True),
                     json.dumps(task, sort_keys=True), now, now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_operational_task(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        row = self._conn().execute(
            "SELECT task_json FROM operational_tasks WHERE project_id=? AND task_id=?",
            (project_id, task_id),
        ).fetchone()
        return json.loads(row["task_json"]) if row else None

    def list_operational_tasks(self, project_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT task_json FROM operational_tasks WHERE project_id=? ORDER BY updated_ts",
            (project_id,),
        ).fetchall()
        return [json.loads(row["task_json"]) for row in rows]

    def mutate_operational_task(self, project_id: str, task_id: str, mutator: Any) -> dict[str, Any]:
        """Serialize a task-local read/modify/write across independent MCP processes.

        Gemini and Grok publish candidates concurrently.  A Python-process-local lock cannot stop
        one candidate from overwriting the other, so this uses SQLite's existing transaction boundary
        rather than adding another store or schema.
        """
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT task_json FROM operational_tasks WHERE project_id=? AND task_id=?",
                    (project_id, task_id),
                ).fetchone()
                if row is None:
                    raise StoreError("no such operational task in this project")
                current = json.loads(row["task_json"])
                updated = mutator(current)
                if not isinstance(updated, dict) or updated.get("task_id") != task_id \
                        or updated.get("project_id") != project_id:
                    raise StoreError("operational task mutation changed task identity")
                conn.execute(
                    "UPDATE operational_tasks SET status=?, owner_node_ids_json=?, task_json=?, "
                    "updated_ts=? WHERE project_id=? AND task_id=?",
                    (updated["status"], json.dumps(updated["owner_node_ids"], sort_keys=True),
                     json.dumps(updated, sort_keys=True), time.time(), project_id, task_id),
                )
                conn.execute("COMMIT")
                return updated
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def append_operational_message(self, message: dict[str, Any]) -> None:
        with self._write_lock:
            try:
                self._conn().execute(
                    "INSERT INTO operational_messages "
                    "(message_id, project_id, task_id, thread_id, sender_node_id, recipients_json, "
                    "message_kind, message_json, created_ts) VALUES (?,?,?,?,?,?,?,?,?)",
                    (message["message_id"], message["project_id"], message["task_id"],
                     message["thread_id"], message["sender_node_id"],
                     json.dumps(message["recipient_node_ids"], sort_keys=True),
                     message["message_kind"], json.dumps(message, sort_keys=True), time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError(f"message {message['message_id']} already exists") from exc

    def list_operational_messages(self, project_id: str, task_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT message_json FROM operational_messages WHERE project_id=? AND task_id=? "
            # rowid is the durable append order for timestamp ties.  A random message id is not a
            # chronology key and made a question/reply pair occasionally appear reversed on Windows.
            "ORDER BY created_ts, rowid", (project_id, task_id),
        ).fetchall()
        return [json.loads(row["message_json"]) for row in rows]

    def list_operational_messages_by_task(
        self, project_id: str, task_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """W-78d: ONE round trip for a whole project's feed. The Inspector emitter used to call
        `list_operational_messages` once per task - each call opening its own SQLite connection -
        so the feed's cost scaled with the task count. Same ordering contract as the per-task
        query (created_ts, then rowid as the durable append order for timestamp ties); the caller
        reassembles task order from its own task list."""
        by_task: dict[str, list[dict[str, Any]]] = {tid: [] for tid in task_ids}
        if not task_ids:
            return by_task
        placeholders = ",".join("?" * len(task_ids))
        rows = self._conn().execute(
            "SELECT task_id, message_json FROM operational_messages "
            f"WHERE project_id=? AND task_id IN ({placeholders}) "
            "ORDER BY created_ts, rowid",
            (project_id, *task_ids),
        ).fetchall()
        for row in rows:
            by_task[row["task_id"]].append(json.loads(row["message_json"]))
        return by_task

    def create_operational_debate(self, debate: dict[str, Any]) -> None:
        """Insert one debate. An existing id is an error, never an overwrite."""
        now = time.time()
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                if conn.execute("SELECT 1 FROM operational_debates WHERE debate_id=?",
                                (debate["debate_id"],)).fetchone():
                    raise StoreError(f"operational debate {debate['debate_id']} already exists")
                conn.execute(
                    "INSERT INTO operational_debates "
                    "(debate_id, project_id, task_id, thread_id, state, debate_json, created_ts, updated_ts) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (debate["debate_id"], debate["project_id"], debate["task_id"], debate["thread_id"],
                     debate["state"], json.dumps(debate, sort_keys=True), now, now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def mutate_operational_debate(self, project_id: str, debate_id: str, mutator: Any) -> dict[str, Any]:
        """The debate twin of `mutate_operational_task`, and for the same reason: two workers
        posting turns to one debate are two OS processes, so the successor record must be
        computed from the row read INSIDE the transaction, never from the caller's snapshot.

        `task_id` is part of the identity guard as well as `debate_id`: it is the scope every
        debate read and the synthesis gate filter by, so a mutation that moved a debate to
        another task would silently change which acceptance packet counts it.
        """
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT debate_json FROM operational_debates WHERE project_id=? AND debate_id=?",
                    (project_id, debate_id),
                ).fetchone()
                if row is None:
                    raise StoreError("no such operational debate in this project")
                current = json.loads(row["debate_json"])
                updated = mutator(current)
                if not isinstance(updated, dict) or updated.get("debate_id") != debate_id \
                        or updated.get("project_id") != project_id \
                        or updated.get("task_id") != current.get("task_id"):
                    raise StoreError("operational debate mutation changed debate identity")
                conn.execute(
                    "UPDATE operational_debates SET state=?, debate_json=?, updated_ts=? "
                    "WHERE project_id=? AND debate_id=?",
                    (updated["state"], json.dumps(updated, sort_keys=True), time.time(),
                     project_id, debate_id),
                )
                conn.execute("COMMIT")
                return updated
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_operational_debate(self, project_id: str, debate_id: str) -> dict[str, Any] | None:
        row = self._conn().execute(
            "SELECT debate_json FROM operational_debates WHERE project_id=? AND debate_id=?",
            (project_id, debate_id),
        ).fetchone()
        return json.loads(row["debate_json"]) if row else None

    def list_operational_debates(self, project_id: str, task_id: str | None = None) -> list[dict[str, Any]]:
        if task_id is None:
            rows = self._conn().execute(
                "SELECT debate_json FROM operational_debates WHERE project_id=? ORDER BY updated_ts",
                (project_id,),
            ).fetchall()
        else:
            rows = self._conn().execute(
                "SELECT debate_json FROM operational_debates WHERE project_id=? AND task_id=? ORDER BY updated_ts",
                (project_id, task_id),
            ).fetchall()
        return [json.loads(row["debate_json"]) for row in rows]

    # -- integrity -------------------------------------------------------------
    def verify(self) -> dict[str, Any]:
        """Cheap consistency check: every head points at a stored version; versions
        contiguous per entry_id from 1; no head references a missing entry."""
        conn = self._conn()
        problems: list[str] = []
        for row in conn.execute("SELECT key, head_ref FROM heads").fetchall():
            if not conn.execute("SELECT 1 FROM memory_entries WHERE ref=?", (row["head_ref"],)).fetchone():
                problems.append(f"head {row['key']} -> missing version {row['head_ref']}")
        for row in conn.execute("SELECT entry_id, COUNT(*) n, MIN(version) mn, MAX(version) mx "
                                "FROM memory_entries GROUP BY entry_id").fetchall():
            if row["mn"] != 1 or row["mx"] != row["n"]:
                problems.append(f"entry {row['entry_id']} versions not contiguous 1..n (min={row['mn']} max={row['mx']} n={row['n']})")
        return {"ok": not problems, "problems": problems}

    def close_thread_conn(self) -> None:
        """Close the calling thread's connection. The server calls this when a handler thread
        ends so per-client threads don't leak WAL connections (spec-audit F5)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def close(self) -> None:
        self.close_thread_conn()


def _make_conflict(conflict_id: str, key: str, expected_head: str, found_head: str, new_ref: str) -> dict[str, Any]:
    # conflict_record schema requires >=2 preserved version refs; guarantee it even at the
    # genesis-mismatch boundary by drawing from {new_ref, found_head, expected_head}.
    versions = sorted({r for r in (new_ref, found_head, expected_head) if r})
    if len(versions) < 2:
        versions = sorted({new_ref, found_head or expected_head or "(genesis)"})
    conflict = {
        "conflict_id": conflict_id, "key": key,
        "expected_head": expected_head or "(genesis)", "found_head": found_head or "(genesis)",
        "versions": versions, "created_ts": _iso_now(), "status": "OPEN", "review_gate_id": None,
    }
    jsonschema.validate(conflict, _CONFLICT_SCHEMA)
    return conflict


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
