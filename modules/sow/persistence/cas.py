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
        # W-69 (donor: terminal_lease.py:285): the temp name carries this process's PID, so two
        # publishers of the same content never share one .tmp file (the shared name made a second
        # publisher fail the first one's rename - Windows sharing violation, deterministically
        # reproduced in test_cas_concurrent_publish_of_same_content_cannot_collide).
        tmp = path.with_suffix(f".tmp-{os.getpid()}")
        with open(tmp, "wb") as fh:
            fh.write(content)
            fh.flush()
            # W-69 (donor: terminal_lease.py:290-294): fsync the BYTES before the rename.
            # os.replace is atomic for the NAME only; without this a crash can leave a published
            # ref whose bytes were never durable.
            os.fsync(fh.fileno())
        tmp.replace(path)  # atomic publish
        return ref

    def get(self, ref: str) -> bytes:
        content = self._path_for(ref).read_bytes()
        if self.ref_for(content) != ref:  # tamper check on read
            raise ValueError(f"content-address mismatch for {ref}")
        return content

    def exists(self, ref: str) -> bool:
        return self._path_for(ref).exists()
