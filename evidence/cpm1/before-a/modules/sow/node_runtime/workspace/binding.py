"""Workspace binding: every node file operation resolves through here (Plan section 7-P3).

Enforcement layer at this phase (recorded honestly, U10):
  ENFORCED  - runtime-API path containment: any path a node asks for is resolved
              (absolute, symlink-real) and refused unless it lands inside the workspace
              root; every refusal is an auditable event.
  ENFORCED  - process-tree containment via Windows Job Objects (supervisor module).
  NOT YET   - OS-level denial for a process that bypasses this API with raw syscalls;
              that is Phase 10 hardening (NTFS ACLs / restricted tokens, U10).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

# Windows reserved device basenames: resolving "NUL"/"CON"/"COM1" lands lexically inside
# the workspace but the OS redirects the write to a device — a fail-open persistence hole
# (spec-audit MEDIUM). Screened per path component, case-insensitive, extension-stripped.
_RESERVED_DEVICES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


class EscapeLogger(Protocol):
    def __call__(self, kind: str, **data: object) -> object: ...


class WorkspaceEscape(Exception):
    def __init__(self, requested: str, reason: str) -> None:
        super().__init__(f"workspace escape refused: {requested!r} ({reason})")
        self.requested = requested
        self.reason = reason


class WorkspaceBinding:
    def __init__(self, root: Path, node_id: str, on_refusal: EscapeLogger | None = None) -> None:
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"workspace root does not exist: {root}")
        self._node_id = node_id
        self._on_refusal = on_refusal

    @property
    def root(self) -> Path:
        return self._root

    def _refuse(self, requested: str, reason: str) -> WorkspaceEscape:
        if self._on_refusal is not None:
            self._on_refusal("workspace_escape_refused", node_id=self._node_id, requested=requested, reason=reason)
        return WorkspaceEscape(requested, reason)

    def resolve(self, relative: str | Path) -> Path:
        """Resolve a node-supplied path; raise WorkspaceEscape unless inside the root
        AND free of Windows name hazards (device names, ADS, trailing dot/space)."""
        requested = str(relative)
        candidate = Path(relative)
        if candidate.is_absolute():
            raise self._refuse(requested, "absolute paths are not accepted from nodes")
        for part in candidate.parts:
            if ":" in part:  # NTFS alternate data stream or drive-relative smuggling
                raise self._refuse(requested, "':' in a path component (ADS/drive-relative) is refused")
            if part != part.rstrip(" .") or re.search(r"[<>\"|?*]", part):
                raise self._refuse(requested, "trailing space/dot or reserved character in a path component")
            if part.split(".")[0].lower() in _RESERVED_DEVICES:
                raise self._refuse(requested, f"reserved device name in path component: {part!r}")
        resolved = (self._root / candidate).resolve()  # collapses .. and symlinks
        if resolved != self._root and self._root not in resolved.parents:
            raise self._refuse(requested, "resolves outside the workspace root")
        return resolved

    def write_text(self, relative: str | Path, content: str) -> Path:
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_text(self, relative: str | Path) -> str:
        return self.resolve(relative).read_text(encoding="utf-8")

    def exists(self, relative: str | Path) -> bool:
        return self.resolve(relative).exists()
