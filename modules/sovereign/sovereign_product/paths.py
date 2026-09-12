"""Portable, fail-closed paths for the SOVEREIGN product surface.

The install root is authoritative only when it contains the canonical
``.sovereign-root`` marker.  Runtime state ships root-relative by default:

* ``<root>/runtime``
* ``<root>/runtime/sovereign.db``
* ``<root>/runtime/evidence``

Artifact references are portable ``sovereign://`` pointers.  Absolute legacy
paths are deliberately rejected during normal resolution; migration requires
an explicit legacy root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Mapping
from urllib.parse import quote, unquote


ROOT_MARKER = ".sovereign-root"
ROOT_MARKER_CONTENT = "SOVEREIGN_ROOT_MARKER=1"
POINTER_PREFIX = "sovereign://"

#: EPC-02 B-1. A path expressed relative to the per-module STATE root rather than the install
#: root. EPC-01 P4-4 moved runtime state out of the install tree so an installation can be
#: verified against its manifest and replaced cleanly; the database and the evidence tree went
#: with it, and neither can be named by the install-root scheme.
#:
#: The scheme is DELIBERATELY distinct rather than an extension of `sovereign://`. A consumer
#: that can only resolve install-root pointers must be able to tell it has been handed
#: something else, instead of resolving it against the wrong base and reading the wrong file.
STATE_POINTER_PREFIX = "sovereign-state://"


class PathResolutionError(RuntimeError):
    """A trusted product path could not be resolved."""


class UnsafeArtifactPointer(ValueError):
    """An artifact pointer escaped, or could escape, its trusted root."""


def _resolved(path: str | os.PathLike[str] | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _marker_is_valid(candidate: Path) -> bool:
    marker = candidate / ROOT_MARKER
    try:
        return marker.is_file() and marker.read_text(encoding="utf-8").strip() == ROOT_MARKER_CONTENT
    except OSError:
        return False


def validate_root(root: str | os.PathLike[str] | Path) -> Path:
    """Resolve and validate one explicit SOVEREIGN install root."""

    candidate = _resolved(root)
    if not candidate.is_dir():
        raise PathResolutionError(f"SOVEREIGN root is not a directory: {candidate}")
    if not _marker_is_valid(candidate):
        raise PathResolutionError(
            f"SOVEREIGN root lacks a valid {ROOT_MARKER} marker: {candidate}"
        )
    return candidate


def resolve_root(
    root: str | os.PathLike[str] | Path | None = None,
    *,
    start: str | os.PathLike[str] | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the install root by explicit value, environment, then marker walk.

    ``SOVEREIGN_ROOT`` is authoritative when present and is validated rather
    than silently falling back.  The marker walk starts from ``start`` or this
    module, never from a hard-coded drive or repository name.
    """

    environment = os.environ if env is None else env
    if root is not None:
        return validate_root(root)

    configured = str(environment.get("SOVEREIGN_ROOT", "")).strip()
    if configured:
        return validate_root(configured)

    origin = _resolved(start if start is not None else __file__)
    if origin.is_file() or (not origin.exists() and origin.suffix):
        origin = origin.parent
    for candidate in (origin, *origin.parents):
        if _marker_is_valid(candidate):
            return candidate
    raise PathResolutionError(
        f"Unable to locate {ROOT_MARKER} while walking upward from {origin}"
    )


def find_root(
    start: str | os.PathLike[str] | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Compatibility alias for marker-based root discovery."""

    return resolve_root(start=start, env=env)


def _resolve_override(
    value: str | os.PathLike[str] | Path | None,
    *,
    default: Path,
    root: Path,
    approved_roots: Iterable[str | os.PathLike[str] | Path] = (),
    label: str,
) -> Path:
    if value is None or not str(value).strip():
        candidate = default.resolve(strict=False)
    else:
        raw = Path(value).expanduser()
        candidate = (root / raw if not raw.is_absolute() else raw).resolve(strict=False)

    trusted = [root, *(_resolved(path) for path in approved_roots)]
    if not any(_is_within(candidate, base) for base in trusted):
        raise PathResolutionError(
            f"{label} is outside the install root and caller-approved roots: {candidate}"
        )
    return candidate


def resolve_state_dir(
    root: str | os.PathLike[str] | Path | None = None,
    *,
    override: str | os.PathLike[str] | Path | None = None,
    env: Mapping[str, str] | None = None,
    approved_roots: Iterable[str | os.PathLike[str] | Path] = (),
    create: bool = False,
) -> Path:
    product_root = resolve_root(root, env=env)
    environment = os.environ if env is None else env
    configured = override
    if configured is None:
        configured = str(environment.get("SOVEREIGN_STATE_DIR", "")).strip() or None
    state = _resolve_override(
        configured,
        default=product_root / "runtime",
        root=product_root,
        approved_roots=approved_roots,
        label="Runtime state directory",
    )
    if create:
        state.mkdir(parents=True, exist_ok=True)
    return state


def resolve_evidence_dir(
    root: str | os.PathLike[str] | Path | None = None,
    *,
    state_dir: str | os.PathLike[str] | Path | None = None,
    override: str | os.PathLike[str] | Path | None = None,
    env: Mapping[str, str] | None = None,
    approved_roots: Iterable[str | os.PathLike[str] | Path] = (),
    create: bool = False,
) -> Path:
    product_root = resolve_root(root, env=env)
    environment = os.environ if env is None else env
    state = (
        _resolved(state_dir)
        if state_dir is not None
        else resolve_state_dir(
            product_root,
            env=environment,
            approved_roots=approved_roots,
            create=create,
        )
    )
    configured = override
    if configured is None:
        configured = str(environment.get("SOVEREIGN_EVIDENCE_DIR", "")).strip() or None
    evidence = _resolve_override(
        configured,
        default=state / "evidence",
        root=product_root,
        approved_roots=approved_roots,
        label="Evidence directory",
    )
    if create:
        evidence.mkdir(parents=True, exist_ok=True)
    return evidence


def resolve_db_path(
    root: str | os.PathLike[str] | Path | None = None,
    *,
    state_dir: str | os.PathLike[str] | Path | None = None,
    override: str | os.PathLike[str] | Path | None = None,
    env: Mapping[str, str] | None = None,
    approved_roots: Iterable[str | os.PathLike[str] | Path] = (),
) -> Path:
    product_root = resolve_root(root, env=env)
    environment = os.environ if env is None else env
    state = (
        _resolved(state_dir)
        if state_dir is not None
        else resolve_state_dir(
            product_root,
            env=environment,
            approved_roots=approved_roots,
        )
    )
    configured = override
    if configured is None:
        configured = str(environment.get("SOVEREIGN_DB_PATH", "")).strip() or None
    return _resolve_override(
        configured,
        default=state / "sovereign.db",
        root=product_root,
        approved_roots=approved_roots,
        label="Product database path",
    )


@dataclass(frozen=True)
class ProductPaths:
    """Resolved locations shared by the adapter, store, and introspection."""

    root: Path
    state_dir: Path
    db_path: Path
    evidence_dir: Path

    def pointer(self, path: str | os.PathLike[str] | Path) -> str:
        return artifact_pointer(path, root=self.root)

    def resolve_pointer(self, pointer: str, *, must_exist: bool = False) -> Path:
        """Resolve either scheme against the base it names.

        The containment discipline is identical for both: the resolved path must sit inside
        the base the scheme names, checked after resolution so a `..` or a symlink cannot walk
        out. Only the base differs.
        """
        if isinstance(pointer, str) and pointer.startswith(STATE_POINTER_PREFIX):
            return _resolve_under(
                pointer[len(STATE_POINTER_PREFIX):],
                base=Path(self.state_dir),
                must_exist=must_exist,
                label="state",
            )
        return resolve_artifact_pointer(pointer, root=self.root, must_exist=must_exist)

    def make_pointer(self, path: str | os.PathLike[str] | Path) -> str:
        """Produce a typed, round-trip-validated pointer for a path under either trusted root.

        The one producer-side contract shared by every runtime pointer site (R35/F-119). A path
        inside the install root becomes a ``sovereign://`` pointer; a path inside the state root
        (where P4-4 put the database and the evidence tree) becomes a ``sovereign-state://``
        pointer. The install root is preferred when a path is inside both (the legacy layout, where
        state is ``<root>/runtime``), matching the descriptor behaviour the rest of the product
        already relies on. The result is validated by resolving it back through
        :meth:`resolve_pointer`, so an un-resolvable pointer is never emitted -- a producer that
        cannot express its artifact fails loudly here instead of publishing a dead reference (the
        ``approved-evidence://`` class of defect). A path under neither root raises
        :class:`UnsafeArtifactPointer`."""
        resolved = _resolved(path)
        root_base = _resolved(self.root)
        if _is_within(resolved, root_base):
            return artifact_pointer(resolved, root=root_base)
        state_base = _resolved(self.state_dir)
        if _is_within(resolved, state_base):
            relative = resolved.relative_to(state_base)
            if not relative.parts:
                raise UnsafeArtifactPointer("the state root itself is not an artifact")
            payload = quote(PurePosixPath(*relative.parts).as_posix(), safe="/-._~")
            pointer = STATE_POINTER_PREFIX + payload
            # Round-trip: the pointer must resolve back to the path it names (this also catches a
            # symlink escape, since resolve_pointer re-checks containment after resolution).
            if self.resolve_pointer(pointer).resolve(strict=False) != resolved:
                raise UnsafeArtifactPointer(
                    f"state pointer does not round-trip to its source: {pointer}")
            return pointer
        raise UnsafeArtifactPointer(
            f"path is under neither the install root nor the state root: {resolved}")

    def resolve_evidence_pointer(self, pointer: str, *, must_exist: bool = False) -> Path:
        """Resolve a pointer for the ``/v1/evidence`` endpoint and refuse anything that lands
        outside the evidence directory (R31/F-102).

        The general resolver accepts both the install-root (``sovereign://``) and state-root
        (``sovereign-state://``) schemes, each contained to its own base. That is correct for
        internal resolution, but the evidence endpoint serves ONE thing -- evidence artifacts --
        and must not become a reader for the rest of either tree. A well-formed
        ``sovereign-state://sovereign.db`` or ``sovereign://.venv/...`` resolves inside its base
        yet has no business being downloaded, so the resolved path is re-checked for containment
        in ``evidence_dir`` after resolution (so a symlink cannot walk out either)."""
        resolved = self.resolve_pointer(pointer, must_exist=must_exist)
        evidence_base = Path(self.evidence_dir).resolve(strict=False)
        if not _is_within(resolved, evidence_base):
            raise UnsafeArtifactPointer(
                "evidence pointer resolves outside the evidence directory")
        return resolved


def resolve_product_paths(
    root: str | os.PathLike[str] | Path | None = None,
    *,
    start: str | os.PathLike[str] | Path | None = None,
    state_dir: str | os.PathLike[str] | Path | None = None,
    db_path: str | os.PathLike[str] | Path | None = None,
    evidence_dir: str | os.PathLike[str] | Path | None = None,
    env: Mapping[str, str] | None = None,
    approved_roots: Iterable[str | os.PathLike[str] | Path] = (),
    create: bool = False,
) -> ProductPaths:
    product_root = resolve_root(root, start=start, env=env)

    # EPC-01 P4-4. The workspace state root the SHELL declares is a caller-approved root,
    # because the shell IS the caller.
    #
    # `SOVEREIGN_STATE_DIR` alone was never sufficient: `_resolve_override` refuses any state
    # directory outside the install root and the caller's approved roots, and `approved_roots`
    # is a Python parameter that a spawned process cannot be passed. So pointing the env var
    # at %LOCALAPPDATA% produced "Runtime state directory is outside the install root and
    # caller-approved roots" and the server would not start — which is the check doing exactly
    # what it should, given it had not been told about the new root.
    #
    # The containment property is unchanged: state must still sit inside the install root or
    # inside a root the caller named. What changes is that the caller can now name one across
    # a process boundary. `SOVEREIGN_WORKSPACE_STATE` is set by the shell for every module it
    # launches; nothing else sets it.
    environment = os.environ if env is None else env
    workspace_state = str(environment.get("SOVEREIGN_WORKSPACE_STATE", "")).strip()
    if workspace_state:
        approved_roots = [*approved_roots, workspace_state]

    state = resolve_state_dir(
        product_root,
        override=state_dir,
        env=env,
        approved_roots=approved_roots,
        create=create,
    )
    evidence = resolve_evidence_dir(
        product_root,
        state_dir=state,
        override=evidence_dir,
        env=env,
        approved_roots=approved_roots,
        create=create,
    )
    database = resolve_db_path(
        product_root,
        state_dir=state,
        override=db_path,
        env=env,
        approved_roots=approved_roots,
    )
    return ProductPaths(product_root, state, database, evidence)


def _pointer_parts(pointer: str) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith(POINTER_PREFIX):
        raise UnsafeArtifactPointer(
            f"Artifact pointer must use the {POINTER_PREFIX} scheme"
        )
    payload = pointer[len(POINTER_PREFIX) :]
    if not payload or "\x00" in payload or "?" in payload or "#" in payload:
        raise UnsafeArtifactPointer("Artifact pointer is empty or contains URL metadata")
    if "\\" in payload:
        raise UnsafeArtifactPointer("Artifact pointers must use POSIX separators")

    decoded = unquote(payload)
    raw_parts = decoded.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise UnsafeArtifactPointer("Artifact pointer contains empty or traversal segments")
    if PurePosixPath(decoded).is_absolute() or PureWindowsPath(decoded).is_absolute():
        raise UnsafeArtifactPointer("Absolute artifact pointers are not portable")
    if PureWindowsPath(decoded).drive:
        raise UnsafeArtifactPointer("Drive-qualified artifact pointers are not portable")
    return tuple(raw_parts)


def _resolve_under(payload: str, *, base: Path, must_exist: bool, label: str) -> Path:
    """Resolve a pointer payload under `base`, refusing anything that escapes it.

    Shares the payload validation of `_pointer_parts` (no NUL, no URL metadata, no backslash,
    no absolute or parent segments) and then re-checks containment AFTER resolution, so a
    symlink cannot be used to walk out of the base the scheme named.
    """
    parts = _pointer_parts(POINTER_PREFIX + payload)
    resolved = base.joinpath(*parts).resolve(strict=False)
    if not _is_within(resolved, Path(base).resolve(strict=False)):
        raise UnsafeArtifactPointer(
            f"Artifact pointer escapes the SOVEREIGN {label} root")
    if must_exist and not resolved.exists():
        raise UnsafeArtifactPointer(f"Artifact does not exist: {resolved.name}")
    return resolved


def resolve_artifact_pointer(
    pointer: str,
    *,
    root: str | os.PathLike[str] | Path | None = None,
    must_exist: bool = False,
) -> Path:
    """Resolve one portable pointer under the current marker-validated root."""

    product_root = resolve_root(root)
    parts = _pointer_parts(pointer)
    candidate = product_root.joinpath(*parts).resolve(strict=False)
    if not _is_within(candidate, product_root):
        raise UnsafeArtifactPointer("Artifact pointer escapes the SOVEREIGN root")
    if must_exist and not candidate.exists():
        raise PathResolutionError(f"Artifact does not exist: {pointer}")
    return candidate


def artifact_pointer(
    path: str | os.PathLike[str] | Path,
    *,
    root: str | os.PathLike[str] | Path | None = None,
) -> str:
    """Return a relocation-safe pointer for a path under the product root."""

    product_root = resolve_root(root)
    raw = Path(path).expanduser()
    candidate = (product_root / raw if not raw.is_absolute() else raw).resolve(strict=False)
    if not _is_within(candidate, product_root):
        raise UnsafeArtifactPointer(f"Artifact path escapes the SOVEREIGN root: {candidate}")
    relative = candidate.relative_to(product_root)
    if not relative.parts:
        raise UnsafeArtifactPointer("The install root itself is not an artifact")
    payload = quote(PurePosixPath(*relative.parts).as_posix(), safe="/-._~")
    pointer = POINTER_PREFIX + payload
    # Round-trip validation also catches symlink escapes.
    resolve_artifact_pointer(pointer, root=product_root)
    return pointer


def migrate_legacy_pointer(
    pointer: str | os.PathLike[str] | Path,
    *,
    legacy_root: str | os.PathLike[str] | Path,
    new_root: str | os.PathLike[str] | Path,
) -> str:
    """Explicitly migrate one trusted absolute pointer from an old install.

    Normal pointer resolution never accepts absolute paths.  Migration is
    intentionally separate and requires both the old trusted root and the new
    marker-validated root.
    """

    raw_text = str(pointer)
    if raw_text.startswith(POINTER_PREFIX):
        # Already portable: validate it against the destination and normalize.
        target = resolve_artifact_pointer(raw_text, root=new_root)
        return artifact_pointer(target, root=new_root)
    if "\x00" in raw_text:
        raise UnsafeArtifactPointer("Legacy pointer contains a NUL byte")
    if any(part == ".." for part in raw_text.replace("\\", "/").split("/")):
        raise UnsafeArtifactPointer("Legacy pointer contains traversal")

    old_base = _resolved(legacy_root)
    legacy_path = Path(pointer).expanduser()
    if not legacy_path.is_absolute():
        raise UnsafeArtifactPointer("Legacy migration requires an absolute path")
    legacy_path = legacy_path.resolve(strict=False)
    if not _is_within(legacy_path, old_base):
        raise UnsafeArtifactPointer("Legacy pointer is outside the explicitly trusted root")

    relative = legacy_path.relative_to(old_base)
    destination_root = validate_root(new_root)
    return artifact_pointer(destination_root / relative, root=destination_root)


# Small compatibility aliases for call sites that prefer explicit safety names.
safe_artifact_pointer = artifact_pointer
resolve_pointer = resolve_artifact_pointer
