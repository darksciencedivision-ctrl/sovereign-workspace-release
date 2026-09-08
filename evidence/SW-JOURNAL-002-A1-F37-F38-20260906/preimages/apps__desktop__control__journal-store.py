"""SW-JOURNAL-001: local shell adapter to EXISTING project artifact operations.
No MCP transport, node creation, task mutation, model call, or new registered operation.
The publisher is explicitly a shell observer under the least-privileged existing worker role,
never the target node. Delegation task ids are observations, not operational-task foreign keys.
"""
from __future__ import annotations
import base64
import json
import sqlite3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from control_plane.policy import Identity, SovereignPolicy
from mcp_server.memory_service import MemoryService, MemoryServiceError
from persistence import ContentAddressedStore, SovereignStore
from control_plane.orchestration.pane_observation import observation_budget, recommended_num_ctx, MAX_OBSERVATION_CHARS
from control_plane.orchestration.pane_capacity import WORKER_NUM_CTX
from adapters.local.model_ceiling import hardware_profile
MEDIA = "application/vnd.sovereign.workspace-journal+json"

def budget(profile=None):
    if isinstance(profile, dict) and profile.get("worker") is True:
        ctx = profile.get("num_ctx")
        if not isinstance(ctx, int) or isinstance(ctx, bool) or ctx <= 0:
            ctx = WORKER_NUM_CTX
        vram = profile.get("vram_mib")
        vram_arg = vram if isinstance(vram, int) and not isinstance(vram, bool) and vram > 0 else None
        result = observation_budget(vram_arg, ctx)
        return {"available": True, **result, "max_observation_chars": MAX_OBSERVATION_CHARS}
    if profile is None:
        profile = hardware_profile()
        if profile.get("source") != "nvidia-smi":
            return {"available": False, "reason": "budget_unmeasurable: host VRAM was not measured"}
    vram = profile.get("vram_mib")
    if not isinstance(vram, int) or isinstance(vram, bool) or vram <= 0:
        return {"available": False, "reason": "budget_unmeasurable: host VRAM unavailable"}
    ctx, reason = recommended_num_ctx(vram)
    return {"available": True, **observation_budget(vram, ctx), "num_ctx_reason": reason,
            "max_observation_chars": MAX_OBSERVATION_CHARS}

class JournalStoreUnavailable(ValueError):
    """Only fixed, path-free diagnostics may cross the journal CLI boundary."""


def handle(request):
    try:
        return _handle(request)
    except (OSError, sqlite3.Error):
        raise JournalStoreUnavailable("journal store could not be opened") from None


def _handle(request):
    op = request.get("op")
    if op == "budget":
        return budget(request.get("profile"))
    root = Path(request["store_root"]).resolve()
    db = root / "sovereign.db"
    # An absent store is NOT an invitation to construct an empty source of truth.
    try:
        with db.open("rb") as source:
            source.read(1)  # Verify actual readability before the schema-writing constructor.
    except FileNotFoundError:
        raise JournalStoreUnavailable("no journal store (sovereign.db absent)") from None
    # CAS is self-creating; the existing ContentAddressedStore constructor owns that work.
    identity = Identity("shell-journal-observer", "worker", request["project_id"])
    policy = SovereignPolicy()
    if op == "append":
        entry = request["entry"]
        if (entry.get("schema") != "workspace_journal@1.0"
                or entry.get("self_published") is not False
                or entry.get("source") != "observed_pane_output"):
            raise ValueError("journal provenance missing")
        content = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if len(content) > 131072:
            raise ValueError("journal entry exceeds storage bound")
        store = SovereignStore(db)
        try:
            service = MemoryService(store, ContentAddressedStore(root / "cas"), policy)
            return service.put_artifact(identity, content=content,
                media_type=MEDIA + ";session=" + entry["session_id"], task_id=None)
        finally:
            store.close()
    if op == "append_private":
        entry = request["entry"]
        if (entry.get("schema") != "workspace_journal@1.0"
                or entry.get("self_published") is not False
                or entry.get("source") != "observed_pane_output"):
            raise ValueError("journal provenance missing")
        node_id = entry.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("private journal needs the worker node identity")
        content = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if len(content) > 131072:
            raise ValueError("journal entry exceeds storage bound")
        worker = Identity(node_id, "worker", request["project_id"])
        store = SovereignStore(db)
        try:
            service = MemoryService(store, ContentAddressedStore(root / "cas"), policy)
            return service.publish(worker, kind="evidence", tier="private_node",
                content=content, provenance={
                    "author_node": node_id, "task_id": entry.get("task_id") or None,
                    "ts": entry.get("utc") or "", "directive_version": "workspace_journal@1.0",
                    "confidence": "low"})
        finally:
            store.close()
    if op == "private_get":
        reader = Identity(request["reader_id"], "worker", request["project_id"])
        store = SovereignStore(db)
        try:
            service = MemoryService(store, ContentAddressedStore(root / "cas"), policy)
            return service.get_entry_content(reader, request["entry_id"])
        except MemoryServiceError as exc:
            raise ValueError(str(exc)) from None
        finally:
            store.close()
    if op == "private_entries":
        node_id = request.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("private journal needs the worker node identity")
        worker = Identity(node_id, "worker", request["project_id"])
        limit = request.get("limit", 128)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 257:
            raise ValueError("invalid journal read bound")
        session = request.get("session_id")
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT me.entry_id, me.entry_json, me.content_hash FROM memory_entries me "
                "JOIN heads h ON h.head_ref = me.ref "
                "WHERE me.project_id=? AND me.tier=? "
                "ORDER BY me.inserted_ts ASC, me.rowid ASC LIMIT ?",
                (worker.project_id, "private_node", limit)).fetchall()
            cas = ContentAddressedStore(root / "cas")
            entries = []
            for _ref, entry_json, content_hash in rows:
                try:
                    meta = json.loads(entry_json)
                    if not policy.authorize_read_entry(worker, meta).allow:
                        continue
                    raw = json.loads(cas.get(content_hash))
                    if session and raw.get("session_id") != session:
                        continue
                    entries.append(raw)
                except Exception:
                    entries.append({"pane_id": "(unavailable)", "unreadable": True,
                                    "reason": "private journal entry unreadable",
                                    "node_id": node_id})
            return entries
        finally:
            connection.close()
    if op != "entries":
        raise ValueError("unsupported journal operation")
    verdict = policy.authorize_read(identity, "artifact", identity.project_id, None)
    if not verdict.allow:
        raise ValueError(verdict.reason)
    limit = request.get("limit", 128)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 257:
        raise ValueError("invalid journal read bound")
    session = request.get("session_id")
    # Read-only projection query over existing metadata, no schema or store write.
    connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    try:
        match = (MEDIA + ";session=" + session) if session else MEDIA + ";session=%"
        compare = "=" if session else "LIKE"
        order = "ASC" if session else "DESC"
        rows = connection.execute(
            "SELECT artifact_id, meta_json FROM artifact_meta WHERE project_id=? "
            "AND json_extract(meta_json, '$.created_by_node') = 'shell-journal-observer' "
            "AND json_extract(meta_json, '$.media_type') " + compare + " ? "
            "ORDER BY inserted_ts " + order + ", rowid " + order + " LIMIT ?",
            (identity.project_id, match, limit)).fetchall()
        # Reuse artifact service READ without running SovereignStore's schema-writing constructor.
        class ReadMetadata:
            def get_artifact_meta(self, artifact_id, project_id):
                row = connection.execute(
                    "SELECT meta_json FROM artifact_meta WHERE artifact_id=? AND project_id=?",
                    (artifact_id, project_id)).fetchone()
                return json.loads(row[0]) if row else None
        service = MemoryService(ReadMetadata(), ContentAddressedStore(root / "cas"), policy)
        entries = []
        for ref, meta in rows:
            try:
                result = service.get_artifact(identity, ref)
                entries.append(json.loads(base64.b64decode(result["content_b64"])))
            except Exception:
                # Do not invent empty worker output when metadata points at unreadable bytes.
                entries.append({"pane_id": "(unavailable)", "unreadable": True,
                                "reason": "journal artifact unreadable", "artifact_id": ref})
        return entries
    finally:
        connection.close()

if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.buffer.read(1048577))
        answer = {"ok": True, "result": handle(request)}
    except JournalStoreUnavailable as exc:
        answer = {"ok": False, "error": str(exc)}
    except Exception as exc:
        answer = {"ok": False, "error": type(exc).__name__ + ": journal operation unavailable"}
    sys.stdout.buffer.write((json.dumps(answer, ensure_ascii=False) + "\n").encode("utf-8"))
