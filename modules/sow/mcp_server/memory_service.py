"""Memory service: the server-enforced memory lifecycle over the store (Plan section 9.4).

Ties together three separated concerns without absorbing any of them:
  - persistence (SovereignStore + CAS): immutable versions, CAS heads, conflict records;
  - lifecycle legality (lifecycle.py): which status edges are legal at all;
  - authorization (control_plane.policy): who may publish/promote — the AUTHORITY.

Every write path asks the policy first (I-M2 delegation) and advances the head by CAS
(D-MCP-03), so a losing concurrent writer gets a conflict record, never a silent overwrite.
The logical key for a fact is its entry_id; versions are entry_id@N; the head points at the
current version.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from control_plane.policy import Identity, SovereignPolicy
from mcp_server import lifecycle
from persistence import ContentAddressedStore, SovereignStore


class MemoryServiceError(Exception):
    pass


#: CR-035: cap on how many CAS refs the bounded quick health pass hash-verifies. The deep offline
#: integrity() pass ignores this and verifies every reference.
_QUICK_INTEGRITY_CAP = 512


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


class MemoryService:
    def __init__(self, store: SovereignStore, cas: ContentAddressedStore, policy: SovereignPolicy) -> None:
        self._store = store
        self._cas = cas
        self._policy = policy

    # -- reads (policy-scoped) -------------------------------------------------
    def read_status(self, identity: Identity, project_id: str, status: str) -> list[dict[str, Any]]:
        verdict = self._policy.authorize_read(identity, "memory", project_id, status)
        if not verdict.allow:
            raise MemoryServiceError(verdict.reason)
        return self._store.list_by_status(project_id, status)

    def get_entry_content(self, identity: Identity, entry_id: str) -> dict[str, Any]:
        """Return the head entry's stored content (from CAS) for a project-scoped read.
        Used by nodes that need the actual bytes of a memory entry (e.g. the conductor
        loading its conductor files), not just the metadata."""
        ref = self._store.get_head(entry_id)
        if not ref:
            raise MemoryServiceError(f"no such entry {entry_id}")
        entry = self._store.get_entry(ref)
        assert entry is not None
        v = self._policy.authorize_read_entry(identity, entry)  # enforces tier ownership (F1)
        if not v.allow:
            raise MemoryServiceError(v.reason)
        return {"entry_id": entry_id, "kind": entry["kind"], "status": entry["status"],
                "content_b64": _b64(self._cas.get(entry["content_hash"]))}

    def get_head_entry(self, identity: Identity, entry_id: str) -> dict[str, Any] | None:
        ref = self._store.get_head(entry_id)
        if not ref:
            return None
        entry = self._store.get_entry(ref)
        if entry is not None:
            v = self._policy.authorize_read_entry(identity, entry)  # enforces tier ownership (F1)
            if not v.allow:
                raise MemoryServiceError(v.reason)
        return entry

    # -- publish a new fact (version 1) ---------------------------------------
    def publish(self, identity: Identity, *, kind: str, tier: str, content: bytes,
                provenance: dict[str, Any], status: str = "CANDIDATE") -> dict[str, Any]:
        entry_id = _new_id("m")
        # CR-002: authorize and shape-validate BEFORE any durable byte is written. The old order
        # called cas.put() first, so an authenticated caller could burn durable CAS disk on every
        # rejected/malformed request. ref_for() derives the content hash without writing, so the
        # entry can be fully authorized and validated; the blob is only put() once the write is
        # certain to be accepted.
        content_ref = self._cas.ref_for(content)
        prov = dict(provenance)
        prov.setdefault("author_node", identity.node_id)
        prov.setdefault("ts", _now())
        entry = {
            "entry_id": entry_id, "project_id": identity.project_id, "tier": tier, "kind": kind,
            "status": status, "provenance": prov, "content_hash": content_ref, "version": 1,
            "prev_version_ref": None, "schema": "memory@1.0",
        }
        verdict = self._policy.authorize_publish(identity, entry)
        if not verdict.allow:
            raise MemoryServiceError(verdict.reason)
        # Blob first, then metadata (CR-005 ordering): the durable version row must never reference
        # bytes that are not yet in CAS.
        self._cas.put(content)
        cas = self._store.commit_version(entry, entry_id, "", conflict_id=_new_id("c"))
        if not cas.ok:  # a fresh random id cannot normally collide; fail closed if it does
            raise MemoryServiceError(f"head init conflict for {entry_id}")
        return {"entry_id": entry_id, "ref": cas.head_ref, "status": status}

    # -- transition an existing fact (new immutable version, CAS head) ---------
    def transition(self, identity: Identity, *, entry_id: str, requested_status: str,
                   successor_ref: str | None = None, reviewer_note: str | None = None) -> dict[str, Any]:
        head_ref = self._store.get_head(entry_id)
        if not head_ref:
            raise MemoryServiceError(f"no such entry {entry_id}")
        current = self._store.get_entry(head_ref)
        assert current is not None
        lifecycle.validate_status_transition(current["status"], requested_status, successor_ref=successor_ref)
        if requested_status == lifecycle.SUPERSEDED and not self._store.has_entry(successor_ref or ""):
            raise MemoryServiceError(f"SUPERSEDED successor {successor_ref!r} does not reference a real version")
        verdict = self._policy.authorize_transition(identity, current, requested_status)
        if not verdict.allow:
            raise MemoryServiceError(verdict.reason)
        prov = dict(current["provenance"])
        prov["ts"] = _now()
        if identity.node_id not in prov.get("reviewers", []):
            prov["reviewers"] = [*prov.get("reviewers", []), identity.node_id]
        if requested_status in lifecycle.PROMOTED:
            prov["gate_result"] = reviewer_note or f"{requested_status} by {identity.role}:{identity.node_id}"
        if requested_status == lifecycle.SUPERSEDED:
            prov["supersedes"] = successor_ref
        new_entry = {**current, "status": requested_status, "provenance": prov}
        cas = self._store.commit_version(new_entry, entry_id, head_ref, conflict_id=_new_id("c"))
        if not cas.ok:
            # a concurrent writer advanced the head first: our version IS preserved as a fork
            # (cas.head_ref), the head stayed on the winner, and a conflict record exists —
            # never a silent overwrite. We report the loss with the parked fork ref.
            return {"entry_id": entry_id, "ref": cas.head_ref, "status": current["status"],
                    "conflict": cas.conflict, "applied": False}
        return {"entry_id": entry_id, "ref": cas.head_ref, "status": requested_status, "applied": True}

    # -- artifacts -------------------------------------------------------------
    def put_artifact(self, identity: Identity, *, content: bytes, media_type: str,
                     task_id: str | None = None) -> dict[str, Any]:
        verdict = self._policy.authorize_put_artifact(identity, identity.project_id)
        if not verdict.allow:
            raise MemoryServiceError(verdict.reason)
        # W-69: a task reference is validated BEFORE anything durable happens; publishing into
        # the void under a nonexistent task_id is refused at the service boundary shared by all
        # three callers (server put_artifact, record_candidate, synthesis).
        if task_id is not None and self._store.get_operational_task(identity.project_id, task_id) is None:
            raise MemoryServiceError(
                f"unknown task {task_id!r} in project {identity.project_id!r}")
        # CR-005: publish the blob to CAS BEFORE committing its metadata. The old order committed
        # metadata first, so a disk/write failure between the two left an authorized artifact_meta
        # record whose CAS bytes never existed — a durable dangling reference that health() did not
        # detect. Authorization already happened above, so writing the blob first cannot let an
        # unauthorized caller consume storage. CAS is immutable and content-addressed: if the
        # metadata commit later fails, the orphaned blob is harmless (identical bytes de-duplicate)
        # and is reported by the offline integrity check, never surfaced as a broken reference.
        ref = self._cas.ref_for(content)
        self._cas.put(content)
        meta = {
            "artifact_id": ref, "media_type": media_type, "size_bytes": len(content),
            "created_by_node": identity.node_id, "task_id": task_id, "ts": _now(),
            "storage": {"store": "cas"}, "schema": "artifact@1.0",
        }
        self._store.put_artifact_meta(meta, identity.project_id)
        return meta

    def get_artifact(self, identity: Identity, artifact_id: str) -> dict[str, Any]:
        v = self._policy.authorize_read(identity, "artifact", identity.project_id, None)
        if not v.allow:
            raise MemoryServiceError(v.reason)
        # blob access is gated by project-scoped metadata: knowing a content hash is not
        # enough to read another project's artifact (spec-audit F4)
        meta = self._store.get_artifact_meta(artifact_id, identity.project_id)
        if meta is None:
            raise MemoryServiceError("no such artifact in this project")
        return {"artifact_id": artifact_id, "content_b64": _b64(self._cas.get(artifact_id)), "meta": meta}

    def list_conflicts(self, identity: Identity, key: str | None = None) -> list[dict[str, Any]]:
        v = self._policy.authorize_read(identity, "conflict", identity.project_id, None)
        if not v.allow:
            raise MemoryServiceError(v.reason)
        return self._store.list_conflicts(identity.project_id, key)

    def health(self, identity: Identity) -> dict[str, Any]:
        v = self._policy.authorize_health(identity)
        if not v.allow:
            raise MemoryServiceError(v.reason)
        # CR-035: health now also confirms that referenced CAS content exists and hashes
        # correctly (bounded quick pass), not just that the store's head/version chains are
        # consistent. Still returns only a boolean; never leak cross-project entry ids over the
        # wire (F8).
        return {"ok": bool(self._referential_integrity(deep=False)["ok"])}

    def integrity(self, identity: Identity, *, deep: bool = True) -> dict[str, Any]:
        """CR-035/CR-005: complete offline referential integrity report classifying every
        metadata-to-CAS reference as missing / corrupt, plus orphaned CAS blobs (deep only).
        Operator/CLI command — returns detail, unlike the boolean health() wire response."""
        v = self._policy.authorize_health(identity)
        if not v.allow:
            raise MemoryServiceError(v.reason)
        return self._referential_integrity(deep=deep)

    def _referential_integrity(self, *, deep: bool) -> dict[str, Any]:
        store_res = self._store.verify()
        refs: list[tuple[str, str]] = [(aid, "artifact") for aid, _ in self._store.all_artifact_refs()]
        refs += [(h, "memory") for h in self._store.all_memory_content_hashes()]
        # Bounded quick pass caps how many refs are hash-verified so health() stays cheap on large
        # stores; the deep offline pass verifies everything.
        checked = refs if deep else refs[:_QUICK_INTEGRITY_CAP]
        missing: list[dict[str, str]] = []
        corrupt: list[dict[str, str]] = []
        for ref, kind in checked:
            verdict = self._cas.classify(ref)
            if verdict == "missing":
                missing.append({"ref": ref, "kind": kind})
            elif verdict == "corrupt":
                corrupt.append({"ref": ref, "kind": kind})
        orphans: list[str] = []
        if deep:
            referenced = {r for r, _ in refs}
            orphans = [ref for ref in self._cas.iter_refs() if ref not in referenced]
        ok = bool(store_res["ok"]) and not missing and not corrupt
        return {"ok": ok, "store": store_res, "missing": missing,
                "corrupt": corrupt, "orphans": orphans, "deep": deep}


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")
