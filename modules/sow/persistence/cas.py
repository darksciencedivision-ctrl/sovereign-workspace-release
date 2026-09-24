"""Content-addressed artifact store (Plan sections 4.5, 9.6; D-PERSIST-01).

Blobs are named by sha256 of their bytes and stored under a sharded directory. Content
addressing makes writes idempotent and tamper-evident: the same bytes always map to the
same ref, and a ref always verifies against its bytes. Blobs are immutable — there is no
overwrite or delete API (invariant 12).
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
import time
from pathlib import Path

_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# CR-001: bounded retry for the atomic publish rename. Windows can transiently refuse os.replace
# (AV/indexer/concurrent identical publisher holding the target); a few short retries absorb it.
_PUBLISH_ATTEMPTS = 8
_PUBLISH_BACKOFF_S = 0.01


class ContentAddressedStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        # CR-001: a per-ref publication lock serializes SAME-content publication within this process
        # so only one thread ever writes+renames a given digest (others short-circuit on exists()).
        # Distinct content (different refs) still publishes concurrently. This removes the
        # concurrent-rename / read-during-rename Windows sharing violations the 100+ thread
        # acceptance exposes; cross-process safety still rests on the unique temp + atomic replace.
        self._publish_locks: dict[str, threading.Lock] = {}
        self._publish_locks_guard = threading.Lock()

    def _lock_for(self, ref: str) -> threading.Lock:
        with self._publish_locks_guard:
            lock = self._publish_locks.get(ref)
            if lock is None:
                lock = threading.Lock()
                self._publish_locks[ref] = lock
            return lock

    @staticmethod
    def ref_for(content: bytes) -> str:
        return "sha256:" + hashlib.sha256(content).hexdigest()

    def _path_for(self, ref: str) -> Path:
        # strict hex validation prevents path traversal via a crafted ref (spec-audit F3):
        # a 64-char digest containing "../" or "/" would otherwise escape the store root.
        if not _REF_RE.match(ref):
            raise ValueError(f"not a valid artifact ref: {ref!r}")
        digest = ref.split(":", 1)[1]
        return self._root / digest[:2] / digest[2:]

    def _blob_ok(self, path: Path, ref: str) -> bool:
        """True only when the stored blob's bytes hash to `ref`. False if absent/unreadable/corrupt."""
        try:
            return self.ref_for(path.read_bytes()) == ref
        except OSError:
            return False

    def put(self, content: bytes) -> str:
        ref = self.ref_for(content)
        path = self._path_for(ref)
        # SW-22: the idempotent fast path must VERIFY, not assume. A present-and-correct blob returns
        # success without a lock; a present-but-CORRUPT (or unreadable) blob falls through to the
        # locked (re)publish below, which repairs it — content addressing means we hold the exact
        # correct bytes, so a present-but-wrong blob must never be reported as a successful publish.
        if self._blob_ok(path, ref):
            return ref
        try:
            with self._lock_for(ref):  # CR-001: one publisher per ref within this process
                return self._put_locked(content, ref, path)
        finally:
            self._release_lock(ref)

    def _release_lock(self, ref: str) -> None:
        # SW-22: bound the per-ref lock dict. Once the blob exists, every future put() hits the
        # verified fast path and never re-acquires this lock, so it is safe to drop.
        try:
            exists = self._path_for(ref).exists()
        except ValueError:
            exists = False
        if exists:
            with self._publish_locks_guard:
                self._publish_locks.pop(ref, None)

    def _put_locked(self, content: bytes, ref: str, path: Path) -> str:
        # Re-check under the lock: a sibling thread may have published the correct bytes while we
        # waited. A present-but-corrupt blob is NOT accepted here — it is overwritten (repaired) by
        # the atomic replace below, which os.replace performs regardless of the target's prior state.
        if self._blob_ok(path, ref):
            return ref
        path.parent.mkdir(parents=True, exist_ok=True)
        # CR-001: mkstemp gives every writer a unique same-directory temp, so concurrent writers of
        # the same ref never contend for a name (the per-ref lock already serializes them in-process).
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp-")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
                fh.flush()
                # fsync the BYTES before the rename. os.replace is atomic for the NAME only;
                # without this a crash can leave a published ref whose bytes were never durable.
                os.fsync(fh.fileno())
            # CR-001: atomic publish (and SW-22 repair) of our uniquely-named temp. os.replace
            # overwrites the target whether it is absent, correct, or corrupt, so this both publishes
            # a new blob and repairs a bad one. On Windows it can transiently raise PermissionError
            # (AV/indexer/concurrent identical publisher briefly holds the target); retry, and treat
            # "the final blob is now correct" (a concurrent identical publish won) as success.
            for attempt in range(_PUBLISH_ATTEMPTS):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if self._blob_ok(path, ref):
                        os.unlink(tmp)
                        return ref
                    if attempt == _PUBLISH_ATTEMPTS - 1:
                        raise
                    time.sleep(_PUBLISH_BACKOFF_S)
        except BaseException:
            # Clean up only the caller's own temp file on any failure; never touch the final path
            # or another writer's temp.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            if self._blob_ok(path, ref):
                # Lost the race but the correct content is durably published: still success.
                return ref
            raise
        return ref

    def get(self, ref: str) -> bytes:
        content = self._path_for(ref).read_bytes()
        if self.ref_for(content) != ref:  # tamper check on read
            raise ValueError(f"content-address mismatch for {ref}")
        return content

    def exists(self, ref: str) -> bool:
        return self._path_for(ref).exists()

    def classify(self, ref: str) -> str:
        """CR-035 building block: classify a ref against its stored bytes without raising.
        Returns 'missing' (no blob), 'corrupt' (blob present but bytes do not hash to ref), or
        'ok'. Used by referential integrity checks over metadata that names CAS content."""
        path = self._path_for(ref)  # validates ref shape; raises only on a malformed ref
        if not path.exists():
            return "missing"
        try:
            content = path.read_bytes()
        except OSError:
            return "missing"
        return "ok" if self.ref_for(content) == ref else "corrupt"

    def iter_refs(self):
        """Yield every stored blob ref (sha256:...) by walking the sharded layout. Temp files
        written by concurrent put() calls carry a '.tmp-' infix and a non-hex name, so they are
        skipped. Used by the offline integrity command to detect orphaned blobs."""
        if not self._root.exists():
            return
        for shard in self._root.iterdir():
            if not shard.is_dir() or len(shard.name) != 2:
                continue
            for blob in shard.iterdir():
                if not blob.is_file():
                    continue
                name = shard.name + blob.name
                if len(name) == 64 and all(c in "0123456789abcdef" for c in name):
                    yield "sha256:" + name
