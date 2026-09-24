"""Portable, fail-closed paths for the SOVEREIGN product surface.

The install root is authoritative only when it contains the canonical
``.sovereign-root`` marker.

SW-25: mutable state lives under a STATE HOME, which is separate from the
install tree whenever the install declares it (``STATE_LAYOUT.json`` with
``"state": "external"``) or the launcher passes ``SOVEREIGN_STATE_HOME``:

* ``<home>/runtime``            (``SOVEREIGN_STATE_DIR`` overrides this one dir)
* ``<home>/runtime/sovereign.db``
* ``<home>/runtime/evidence``
* ``<home>/published``
* ``<home>/library/queues``

The external home defaults to ``%LOCALAPPDATA%\\SovereignWorkspace\\sovereign``
(the shell's per-module state root).  With no layout file and no env the home
is the install root itself, which keeps a bare checkout/test root working as
before.  Every state reader and writer resolves through this module; nothing
else may build ``root / "runtime"`` directly.

Artifact references are portable pointers: ``sovereign://`` under the install
root and ``sovereign-state://`` under the runtime state dir.  Absolute legacy
paths are deliberately rejected during normal resolution; migration requires
an explicit legacy root.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Mapping
from urllib.parse import quote, unquote


ROOT_MARKER = ".sovereign-root"
ROOT_MARKER_CONTENT = "SOVEREIGN_ROOT_MARKER=1"
POINTER_PREFIX = "sovereign://"
STATE_POINTER_PREFIX = "sovereign-state://"

STATE_LAYOUT_FILE = "STATE_LAYOUT.json"
STATE_HOME_ENV = "SOVEREIGN_STATE_HOME"
STATE_DIR_ENV = "SOVEREIGN_STATE_DIR"
WORKSPACE_STATE_ENV = "SOVEREIGN_WORKSPACE_STATE"
WORKSPACE_STATE_DIRNAME = "SovereignWorkspace"
MODULE_STATE_NAME = "sovereign"
RUNTIME_DIRNAME = "runtime"
# Service directories holding supervisor secrets (api_key, consumer.env). No
# artifact pointer may resolve into them, whichever namespace it uses.
SECRET_RUNTIME_DIRS = ("llamacpp_supervisor", "freetoken_supervisor")


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


def _reject_unsupported_state_path(value: str, label: str) -> None:
    """Refuse device-namespace and UNC state locations (mirrors the shell's CR-019 rule)."""

    text = str(value).replace("/", "\\")
    if text.startswith("\\\\?\\") or text.startswith("\\\\.\\"):
        raise PathResolutionError(f"{label} may not be a device-namespace path: {value}")
    if text.startswith("\\\\"):
        raise PathResolutionError(f"{label} may not be a UNC path: {value}")


def _local_appdata(environment: Mapping[str, str]) -> Path:
    local = str(environment.get("LOCALAPPDATA", "")).strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return _resolved(local)


def workspace_state_bases(env: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """The per-user locations an external state home may live under.

    ``%LOCALAPPDATA%\\SovereignWorkspace`` always; plus ``SOVEREIGN_WORKSPACE_STATE``
    when set (the shell passes each module its own state root there; an operator
    may set it to relocate the whole workspace).  A relative value is anchored to
    ``%LOCALAPPDATA%`` and must stay inside it.
    """

    environment = os.environ if env is None else env
    local = _local_appdata(environment)
    bases = [local / WORKSPACE_STATE_DIRNAME]
    configured = str(environment.get(WORKSPACE_STATE_ENV, "")).strip()
    if configured:
        _reject_unsupported_state_path(configured, WORKSPACE_STATE_ENV)
        raw = Path(configured).expanduser()
        if raw.is_absolute():
            bases.append(raw.resolve(strict=False))
        else:
            anchored = (local / raw).resolve(strict=False)
            if not _is_within(anchored, local):
                raise PathResolutionError(
                    f"relative {WORKSPACE_STATE_ENV} escapes %LOCALAPPDATA%: {configured}"
                )
            bases.append(anchored)
    return tuple(bases)


def default_external_state_home(env: Mapping[str, str] | None = None) -> Path:
    """``<workspace state root>\\sovereign`` - the shell's state root for this module."""

    environment = os.environ if env is None else env
    configured = str(environment.get(WORKSPACE_STATE_ENV, "")).strip()
    bases = workspace_state_bases(environment)
    base = bases[-1] if configured else bases[0]
    return base / MODULE_STATE_NAME


def read_state_layout(root: str | os.PathLike[str] | Path) -> str:
    """The install's declared state layout: ``"external"`` or ``"install"`` (absent file).

    A present but unreadable or unknown layout fails closed rather than silently
    falling back to writing inside the install tree.
    """

    path = _resolved(root) / STATE_LAYOUT_FILE
    if not path.is_file():
        return "install"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PathResolutionError(f"{STATE_LAYOUT_FILE} is unreadable: {exc}") from exc
    layout = payload.get("state") if isinstance(payload, dict) else None
    if layout not in ("external", "install"):
        raise PathResolutionError(
            f"{STATE_LAYOUT_FILE} must declare state 'external' or 'install', got {layout!r}"
        )
    return layout


def _trusted_state_location(
    value: str,
    *,
    root: Path,
    trusted: Iterable[Path],
    label: str,
) -> Path:
    _reject_unsupported_state_path(value, label)
    raw = Path(value).expanduser()
    candidate = (root / raw if not raw.is_absolute() else raw).resolve(strict=False)
    if not any(_is_within(candidate, base) for base in (root, *trusted)):
        raise PathResolutionError(
            f"{label} is outside the install root and the workspace state root: {candidate}"
        )
    return candidate


def resolve_state_home(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Where this install's mutable state lives (SW-25).

    ``SOVEREIGN_STATE_HOME`` -> external default when ``STATE_LAYOUT.json`` says
    ``external`` -> the install root itself (legacy / bare test roots).  Does not
    require the root marker, so service helpers handed a plain directory keep
    working.
    """

    environment = os.environ if env is None else env
    product_root = _resolved(root)
    configured = str(environment.get(STATE_HOME_ENV, "")).strip()
    if configured:
        return _trusted_state_location(
            configured,
            root=product_root,
            trusted=workspace_state_bases(environment),
            label=STATE_HOME_ENV,
        )
    if read_state_layout(product_root) == "external":
        return default_external_state_home(environment)
    return product_root


def state_trust_roots(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Every location a state/evidence/db override may resolve under, besides the root."""

    environment = os.environ if env is None else env
    return (resolve_state_home(root, env=environment), *workspace_state_bases(environment))


def resolve_runtime_dir(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """The runtime state dir: ``SOVEREIGN_STATE_DIR`` or ``<state home>/runtime``.

    This is the single answer to "where is runtime state" for every service
    helper (supervisor, GPU occupancy, backend selection, introspection).
    """

    environment = os.environ if env is None else env
    product_root = _resolved(root)
    configured = str(environment.get(STATE_DIR_ENV, "")).strip()
    if configured:
        return _trusted_state_location(
            configured,
            root=product_root,
            trusted=state_trust_roots(product_root, env=environment),
            label="Runtime state directory",
        )
    return resolve_state_home(product_root, env=environment) / RUNTIME_DIRNAME


def resolve_published_dir(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    return resolve_state_home(root, env=env) / "published"


def resolve_queue_dir(
    root: str | os.PathLike[str] | Path,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    return resolve_state_home(root, env=env) / "library" / "queues"


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
        _reject_unsupported_state_path(str(value), label)
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
        configured = str(environment.get(STATE_DIR_ENV, "")).strip() or None
    state = _resolve_override(
        configured,
        default=resolve_runtime_dir(product_root, env=environment),
        root=product_root,
        approved_roots=(*approved_roots, *state_trust_roots(product_root, env=environment)),
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
        approved_roots=(*approved_roots, *state_trust_roots(product_root, env=environment)),
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
        approved_roots=(*approved_roots, *state_trust_roots(product_root, env=environment)),
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
        """A portable pointer: ``sovereign://`` inside the install root, else
        ``sovereign-state://`` inside the runtime state dir (SW-25)."""

        raw = Path(path).expanduser()
        candidate = (self.root / raw if not raw.is_absolute() else raw).resolve(strict=False)
        if _is_within(candidate, self.root):
            return artifact_pointer(candidate, root=self.root)
        return state_artifact_pointer(candidate, state_dir=self.state_dir)

    def resolve_pointer(self, pointer: str, *, must_exist: bool = False) -> Path:
        if isinstance(pointer, str) and pointer.startswith(STATE_POINTER_PREFIX):
            return resolve_state_pointer(pointer, state_dir=self.state_dir, must_exist=must_exist)
        parts = _pointer_parts(pointer)
        state = self.state_dir.resolve(strict=False)
        if parts[0] == RUNTIME_DIRNAME and not _is_within(state, self.root):
            # A pointer minted before SW-25 moved runtime state out of the install tree
            # (e.g. stored in a job row). It names state, so it resolves in the state dir;
            # the migrated copy is authoritative over any stale legacy tree.
            remapped = state.joinpath(*parts[1:]).resolve(strict=False)
            if not _is_within(remapped, state):
                raise UnsafeArtifactPointer("Artifact pointer escapes the SOVEREIGN state dir")
            _refuse_secret_path(remapped, state)
            if must_exist and not remapped.exists():
                raise PathResolutionError(f"Artifact does not exist: {pointer}")
            return remapped
        resolved = resolve_artifact_pointer(pointer, root=self.root, must_exist=must_exist)
        _refuse_secret_path(resolved, self.root / RUNTIME_DIRNAME)
        _refuse_secret_path(resolved, state)
        return resolved


def _refuse_secret_path(path: Path, runtime_dir: Path) -> None:
    base = runtime_dir.resolve(strict=False)
    for name in SECRET_RUNTIME_DIRS:
        if _is_within(path, base / name):
            raise UnsafeArtifactPointer("Artifact pointer names a supervisor secret directory")


def state_artifact_pointer(
    path: str | os.PathLike[str] | Path,
    *,
    state_dir: str | os.PathLike[str] | Path,
) -> str:
    """A ``sovereign-state://`` pointer for a path under the runtime state dir."""

    base = _resolved(state_dir)
    candidate = _resolved(path)
    if not _is_within(candidate, base):
        raise UnsafeArtifactPointer(
            f"Artifact path is outside the install root and the state dir: {candidate}"
        )
    relative = candidate.relative_to(base)
    if not relative.parts:
        raise UnsafeArtifactPointer("The state dir itself is not an artifact")
    pointer = STATE_POINTER_PREFIX + quote(PurePosixPath(*relative.parts).as_posix(), safe="/-._~")
    resolve_state_pointer(pointer, state_dir=base)
    return pointer


def resolve_state_pointer(
    pointer: str,
    *,
    state_dir: str | os.PathLike[str] | Path,
    must_exist: bool = False,
) -> Path:
    """Resolve one ``sovereign-state://`` pointer under the runtime state dir."""

    if not isinstance(pointer, str) or not pointer.startswith(STATE_POINTER_PREFIX):
        raise UnsafeArtifactPointer(f"State pointer must use the {STATE_POINTER_PREFIX} scheme")
    parts = _pointer_parts(POINTER_PREFIX + pointer[len(STATE_POINTER_PREFIX):])
    base = _resolved(state_dir)
    candidate = base.joinpath(*parts).resolve(strict=False)
    if not _is_within(candidate, base):
        raise UnsafeArtifactPointer("Artifact pointer escapes the SOVEREIGN state dir")
    _refuse_secret_path(candidate, base)
    if must_exist and not candidate.exists():
        raise PathResolutionError(f"Artifact does not exist: {pointer}")
    return candidate


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
