"""CR-001, CR-002, CR-003, CR-005, CR-035, CR-036 — CAS/persistence correctness.

Each test is a deterministic reproduction of a punch-list finding plus its fix assertion.
"""
from __future__ import annotations

import threading

import pytest

from conftest import StubPolicy, sample_identity, sample_provenance  # type: ignore

from mcp_server.memory_service import MemoryService, MemoryServiceError
from persistence import ContentAddressedStore, SovereignStore, StoreError


def _service(tmp_path, *, allow=True):
    store = SovereignStore(tmp_path / "sow.db")
    cas = ContentAddressedStore(tmp_path / "cas")
    return MemoryService(store, cas, StubPolicy(allow=allow)), store, cas


def _cas_temp_files(cas_root):
    return [p for p in cas_root.rglob("*") if p.is_file() and ".tmp-" in p.name]


def _cas_blob_count(cas_root):
    return sum(1 for p in cas_root.rglob("*")
               if p.is_file() and ".tmp-" not in p.name and len(p.parent.name) == 2)


# -- CR-001 ----------------------------------------------------------------
def test_cr001_concurrent_publish_of_same_and_distinct_content_no_collision(tmp_path):
    cas = ContentAddressedStore(tmp_path / "cas")
    n = 128
    same = b"identical-payload"
    errors: list[BaseException] = []
    refs: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(n)

    def worker(i: int) -> None:
        start.wait()  # maximize the collision window
        try:
            payload = same if i % 2 == 0 else f"distinct-{i}".encode()
            ref = cas.put(payload)
            with lock:
                refs.append(ref)
                assert cas.get(ref) == payload  # bytes valid + tamper-checked
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent CAS put raised: {errors[:3]}"
    assert len(refs) == n
    assert ContentAddressedStore.ref_for(same) in refs
    assert not _cas_temp_files(tmp_path / "cas"), "orphan .tmp files left behind"


# -- CR-002 ----------------------------------------------------------------
def test_cr002_unauthorized_publish_writes_no_bytes(tmp_path):
    svc, store, cas = _service(tmp_path, allow=False)
    before = _cas_blob_count(tmp_path / "cas")
    with pytest.raises(MemoryServiceError):
        svc.publish(sample_identity(), kind="finding", tier="shared_project",
                    content=b"unauthorized bytes", provenance=sample_provenance())
    after = _cas_blob_count(tmp_path / "cas")
    assert before == after == 0, "rejected publish must not create durable CAS bytes"
    assert not _cas_temp_files(tmp_path / "cas")


def test_cr002_authorized_publish_does_write_bytes(tmp_path):
    svc, store, cas = _service(tmp_path, allow=True)
    res = svc.publish(sample_identity(), kind="finding", tier="shared_project",
                      content=b"authorized bytes", provenance=sample_provenance())
    assert res["status"] == "CANDIDATE"
    assert _cas_blob_count(tmp_path / "cas") == 1


# -- CR-003 ----------------------------------------------------------------
def test_cr003_commit_version_rejects_bad_datetime(tmp_path):
    store = SovereignStore(tmp_path / "sow.db")
    entry = {
        "entry_id": "m-badts", "project_id": "proj-1", "tier": "shared_project",
        "kind": "finding", "status": "CANDIDATE",
        "provenance": sample_provenance(ts="not-a-date"),
        "content_hash": "sha256:" + "0" * 64,
    }
    with pytest.raises(StoreError):
        store.commit_version(entry, "m-badts", "", conflict_id="c-x")
    # and the append path must reject it too (parity)
    with pytest.raises(StoreError):
        store.append_memory_version({**entry, "version": 1})


# -- CR-005 ----------------------------------------------------------------
def test_cr005_artifact_blob_exists_before_metadata_and_no_dangling(tmp_path):
    svc, store, cas = _service(tmp_path, allow=True)
    content = b"artifact-bytes"
    meta = svc.put_artifact(sample_identity(), content=content, media_type="text/plain")
    # metadata visible => blob must be retrievable (no dangling reference)
    got = svc.get_artifact(sample_identity(), meta["artifact_id"])
    assert got["meta"]["artifact_id"] == meta["artifact_id"]
    assert cas.exists(meta["artifact_id"])


def test_cr005_cas_failure_leaves_no_visible_dangling_metadata(tmp_path):
    svc, store, cas = _service(tmp_path, allow=True)

    class BoomCas(ContentAddressedStore):
        def put(self, content):  # fail the blob write
            raise OSError("disk full")

    svc._cas = BoomCas(tmp_path / "cas")
    with pytest.raises(OSError):
        svc.put_artifact(sample_identity(), content=b"x", media_type="text/plain")
    # because the blob write precedes the metadata commit, no artifact_meta row was created
    assert store.all_artifact_refs() == []


# -- CR-035 ----------------------------------------------------------------
def test_cr035_health_and_integrity_detect_missing_truncated_swapped(tmp_path):
    svc, store, cas = _service(tmp_path, allow=True)
    meta = svc.put_artifact(sample_identity(), content=b"good-artifact", media_type="text/plain")
    ident = sample_identity()
    assert svc.health(ident)["ok"] is True
    assert svc.integrity(ident, deep=True)["ok"] is True

    blob = cas._path_for(meta["artifact_id"])
    # swap bytes (present file, wrong content) — must be classified 'corrupt'
    blob.write_bytes(b"tampered")
    assert svc.health(ident)["ok"] is False
    rep = svc.integrity(ident, deep=True)
    assert rep["ok"] is False and any(c["ref"] == meta["artifact_id"] for c in rep["corrupt"])

    # truncate to empty — still corrupt (bytes no longer hash to ref)
    blob.write_bytes(b"")
    assert svc.integrity(ident, deep=True)["corrupt"], "truncated blob not detected"

    # delete — must be classified 'missing'
    blob.unlink()
    rep = svc.integrity(ident, deep=True)
    assert svc.health(ident)["ok"] is False
    assert any(m["ref"] == meta["artifact_id"] for m in rep["missing"])


def test_cr035_orphan_blob_detected_in_deep_pass(tmp_path):
    svc, store, cas = _service(tmp_path, allow=True)
    orphan_ref = cas.put(b"unreferenced-orphan-bytes")
    rep = svc.integrity(sample_identity(), deep=True)
    assert orphan_ref in rep["orphans"]
    # orphans do not by themselves make the store unhealthy (immutable CAS de-dupes safely)
    assert rep["ok"] is True


# -- CR-036 ----------------------------------------------------------------
def test_cr036_cas_advance_head_to_missing_ref_fails_without_changing_head(tmp_path):
    store = SovereignStore(tmp_path / "sow.db")
    # seed a real head at m-k@1 via commit_version
    entry = {
        "entry_id": "m-k", "project_id": "proj-1", "tier": "shared_project",
        "kind": "finding", "status": "CANDIDATE", "provenance": sample_provenance(),
        "content_hash": "sha256:" + "a" * 64,
    }
    res = store.commit_version(entry, "m-k", "", conflict_id="c-1")
    assert res.ok
    head_before = store.get_head("m-k")

    with pytest.raises(StoreError):
        store.cas_advance_head("m-k", head_before, "m-k@999", conflict_id="c-2")
    assert store.get_head("m-k") == head_before, "head must be unchanged after a failed advance"
