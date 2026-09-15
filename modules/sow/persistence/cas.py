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
from pathlib import Path

_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContentAddressedStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

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

    def put(self, content: bytes) -> str:
        ref = self.ref_for(content)
        path = self._path_for(ref)
        if path.exists():
            return ref  # idempotent: identical content already stored
        path.parent.mkdir(parents=True, exist_ok=True)
        # CR-001: a per-PROCESS temp name (the old `.tmp-<pid>`) still collided between THREADS of
        # one process — the MCP server handles requests on threads, so two threads publishing the
        # same content shared one .tmp path and the second failed the first's rename (Windows
        # sharing violation; reproduced in test_cas_concurrent_publish_no_collision). mkstemp gives
        # every writer a unique same-directory temp file, so writers never contend for a name.
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp-")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
                fh.flush()
                # fsync the BYTES before the rename. os.replace is atomic for the NAME only;
                # without this a crash can leave a published ref whose bytes were never durable.
                os.fsync(fh.fileno())
            if path.exists():
                # A concurrent writer of identical content already published the final ref while we
                # were writing. Content addressing makes the bytes identical, so treat the existing
                # blob as success and drop only our own temp file — never another writer's.
                os.unlink(tmp)
                return ref
            os.replace(tmp, path)  # atomic publish of our own uniquely-named temp
        except BaseException:
            # Clean up only the caller's own temp file on any failure; never touch the final path
            # or another writer's temp.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            if path.exists():
                # Lost the race but the content is durably published by the winner: still success.
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
