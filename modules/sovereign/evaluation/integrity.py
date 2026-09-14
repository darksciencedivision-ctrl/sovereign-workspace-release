"""Runtime integrity enforcement for protected SOVEREIGN paths and state files."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


class IntegrityGuardError(RuntimeError):
    """Raised when the integrity guard cannot produce a reliable snapshot."""


class IntegrityViolation(RuntimeError):
    """Raised when a runtime integrity rule is violated and execution must abort."""

    def __init__(
        self,
        *,
        session_id: str = "",
        violations: list[dict[str, Any]] | None = None,
        state_drifted: bool = False,
        message: str = "Integrity violation detected.",
        report: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.session_id = str(session_id or "").strip()
        self.violations = [dict(item) for item in (violations or []) if isinstance(item, dict)]
        self.state_drifted = bool(state_drifted)
        self.message = str(message or "Integrity violation detected.").strip() or "Integrity violation detected."
        self.report = dict(report) if isinstance(report, dict) else None

    def to_report(self) -> dict[str, Any]:
        """Return a structured report payload for the violation."""

        if self.report is not None:
            return dict(self.report)

        integrity_violations = [
            dict(item)
            for item in self.violations
            if str(item.get("violation_type", "")).strip().upper() != "STATE_DRIFT"
        ]
        protected_state_drift = [
            dict(item)
            for item in self.violations
            if str(item.get("violation_type", "")).strip().upper() == "STATE_DRIFT"
        ]
        contract_violations = [self.message]
        contract_violations.extend(
            str((item.get("details") or {}).get("summary", "")).strip() or str(item.get("path", "")).strip()
            for item in self.violations
            if isinstance(item, dict)
        )
        contract_violations = [item for item in contract_violations if item]
        return {
            "contract_status": "CRITICAL_VIOLATION",
            "contract_message": self.message,
            "contract_violations": list(dict.fromkeys(contract_violations)),
            "integrity_violations": integrity_violations,
            "protected_state_drift": protected_state_drift,
            "state_drift": bool(self.state_drifted or protected_state_drift),
            "integrity_summary": {
                "status": "CRITICAL_VIOLATION",
                "manifest_changed": bool(integrity_violations),
                "protected_state_stable": not bool(self.state_drifted or protected_state_drift),
                "integrity_violation_count": len(integrity_violations),
                "protected_state_drift_count": len(protected_state_drift),
            },
            "session_id": self.session_id,
        }


class IntegrityGuard:
    """Detect protected-path drift and critical state-file races during validation."""

    DEFAULT_PROTECTED_ROOTS: tuple[str, ...] = ("broker_v21", "evaluation", "optimization")
    HASH_CHUNK_SIZE = 1024 * 1024
    VIOLATION_SEVERITY: dict[str, str] = {
        "CREATION": "HIGH",
        "MODIFICATION": "CRITICAL",
        "DELETION": "CRITICAL",
        "STATE_DRIFT": "CRITICAL",
        "UNSAFE_WRITE_PATH": "CRITICAL",
        "INTEGRITY_ERROR": "CRITICAL",
    }
    _REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)

    def __init__(
        self,
        base_dir: Path | None = None,
        protected_roots: list[str | Path] | None = None,
        excluded_subpaths: list[str | Path] | None = None,
    ) -> None:
        """Initialize the guard with protected roots relative to a base directory."""

        resolved_base = Path(base_dir).expanduser() if base_dir is not None else Path(__file__).resolve().parents[1]
        self.base_dir = resolved_base.resolve(strict=False)
        configured_roots = protected_roots if protected_roots is not None else list(self.DEFAULT_PROTECTED_ROOTS)
        self._configured_protected_roots = self._coerce_paths(configured_roots)
        self._excluded_subpaths = self._coerce_paths(excluded_subpaths or [])

    def generate_manifest(self) -> dict[str, str]:
        """Build a deterministic SHA-256 manifest across all protected roots."""

        manifest: dict[str, str] = {}
        for root in self.get_protected_roots():
            try:
                if not root.exists():
                    continue
                if root.is_file():
                    digest = self.hash_file(root)
                    if digest is not None:
                        manifest[self._normalize_manifest_key(root)] = digest
                    continue
                if not root.is_dir():
                    continue
            except OSError as exc:
                raise IntegrityGuardError(f"Unable to inspect protected root {root}: {exc}") from exc

            for file_path in self._iter_files(root):
                digest = self.hash_file(file_path)
                if digest is None:
                    continue
                manifest[self._normalize_manifest_key(file_path)] = digest

        return {key: manifest[key] for key in sorted(manifest)}

    def hash_file(self, path: Path) -> str | None:
        """Return a SHA-256 hex digest for a file, or ``None`` when it is absent."""

        file_path = self._resolve_path(path)
        try:
            if not file_path.exists() or not file_path.is_file():
                return None
        except OSError as exc:
            raise IntegrityGuardError(f"Unable to inspect file {file_path}: {exc}") from exc

        hasher = hashlib.sha256()
        try:
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(self.HASH_CHUNK_SIZE), b""):
                    hasher.update(chunk)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise IntegrityGuardError(f"Unable to hash file {file_path}: {exc}") from exc
        return hasher.hexdigest()

    def verify_state_atomic(self, initial_hash: str | None, path: Path) -> bool:
        """Re-hash a critical state file and return ``False`` when unexpected drift occurred."""

        try:
            current_hash = self.hash_file(path)
        except IntegrityGuardError:
            return False
        return current_hash == initial_hash

    def detect_violations(self, pre: dict[str, str], post: dict[str, str]) -> list[dict[str, Any]]:
        """Compare two manifests and return structured protected-path violations."""

        violations: list[dict[str, Any]] = []
        timestamp = self._timestamp_utc()

        all_paths = sorted(set(pre) | set(post))
        for path_key in all_paths:
            pre_hash = pre.get(path_key)
            post_hash = post.get(path_key)
            if pre_hash == post_hash:
                continue

            if pre_hash is None and post_hash is not None:
                violation_type = "CREATION"
            elif pre_hash is not None and post_hash is None:
                violation_type = "DELETION"
            else:
                violation_type = "MODIFICATION"

            protected_root = self._protected_root_for_key(path_key)
            violations.append(
                {
                    "violation_type": violation_type,
                    "path": path_key,
                    "protected_root": protected_root,
                    "severity": self.VIOLATION_SEVERITY[violation_type],
                    "timestamp_utc": timestamp,
                    "details": {
                        "summary": self._violation_summary(violation_type),
                        "pre_hash": pre_hash,
                        "post_hash": post_hash,
                        "expected_stable": True,
                    },
                }
            )

        return violations

    def validate_write_path(
        self,
        path: str | Path,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        session_id: str = "",
    ) -> Path:
        """Validate a write destination before any filesystem mutation occurs."""

        target = self._resolve_path(path)
        candidate_roots = list(allowed_roots) if allowed_roots is not None else [self.base_dir]
        normalized_roots = self._coerce_paths(candidate_roots)
        matched_root: Path | None = None
        for root in sorted(normalized_roots, key=lambda item: len(item.as_posix()), reverse=True):
            if self._is_relative_to(target, root):
                matched_root = root
                break

        if matched_root is None:
            raise self._unsafe_write_violation(
                session_id=session_id,
                path=target,
                protected_root="WRITE_BOUNDARY",
                summary="Write target escapes the allowed write roots.",
                details={
                    "candidate_path": target.as_posix(),
                    "allowed_roots": [root.as_posix() for root in normalized_roots],
                },
            )

        self._assert_no_reparse_points(target, matched_root, session_id=session_id)
        return target

    def safe_write_json(
        self,
        path: str | Path,
        data: Any,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        session_id: str = "",
    ) -> None:
        """Atomically write JSON after validating the destination path."""

        target = self.validate_write_path(path, allowed_roots=allowed_roots, session_id=session_id)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self._write_text_atomic(target, payload, append_newline=True)

    def safe_write_text(
        self,
        path: str | Path,
        text: str,
        *,
        allowed_roots: Iterable[str | Path] | None = None,
        session_id: str = "",
        ensure_trailing_newline: bool = True,
    ) -> None:
        """Atomically write text after validating the destination path."""

        target = self.validate_write_path(path, allowed_roots=allowed_roots, session_id=session_id)
        self._write_text_atomic(target, text, append_newline=ensure_trailing_newline)

    def get_protected_roots(self) -> list[Path]:
        """Return the normalized, de-duplicated protected roots after exclusions."""

        roots: list[Path] = []
        seen: set[str] = set()
        for root in self._configured_protected_roots:
            if self._is_excluded(root):
                continue
            identity = self._path_identity(root)
            if identity in seen:
                continue
            seen.add(identity)
            roots.append(root)
        return sorted(roots, key=self._sort_key_for_path)

    def _write_text_atomic(self, target: Path, text: str, *, append_newline: bool) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                if append_newline and text and not text.endswith("\n"):
                    handle.write("\n")
            os.replace(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _coerce_paths(self, values: Sequence[str | Path]) -> tuple[Path, ...]:
        """Resolve constructor path inputs into normalized absolute paths."""

        resolved_paths: list[Path] = []
        seen: set[str] = set()
        for value in values:
            resolved = self._resolve_path(Path(value))
            identity = self._path_identity(resolved)
            if identity in seen:
                continue
            seen.add(identity)
            resolved_paths.append(resolved)
        return tuple(resolved_paths)

    def _iter_files(self, directory: Path) -> Iterator[Path]:
        """Yield files beneath a protected directory in deterministic order."""

        try:
            entries = sorted(directory.iterdir(), key=self._sort_key_for_path)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise IntegrityGuardError(f"Unable to enumerate protected directory {directory}: {exc}") from exc

        for entry in entries:
            if self._is_excluded(entry):
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    yield from self._iter_files(entry)
                    continue
                if entry.is_file():
                    yield entry.resolve(strict=False)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise IntegrityGuardError(f"Unable to inspect protected path {entry}: {exc}") from exc

    def _resolve_path(self, path: str | Path) -> Path:
        """Resolve a path against the base directory without requiring existence."""

        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.base_dir / candidate
        return candidate.resolve(strict=False)

    def _normalize_manifest_key(self, path: Path) -> str:
        """Return a stable manifest key relative to the base directory when possible."""

        resolved = self._resolve_path(path)
        try:
            return resolved.relative_to(self.base_dir).as_posix()
        except ValueError:
            return resolved.as_posix()

    def _is_excluded(self, path: Path) -> bool:
        """Return ``True`` when a path falls beneath an excluded subpath."""

        candidate = self._resolve_path(path)
        for excluded in self._excluded_subpaths:
            if candidate == excluded:
                return True
            try:
                candidate.relative_to(excluded)
                return True
            except ValueError:
                continue
        return False

    def _path_identity(self, path: Path) -> str:
        """Return a case-normalized identity key for Windows-safe comparisons."""

        return self._resolve_path(path).as_posix().casefold()

    def _protected_root_for_key(self, manifest_key: str) -> str:
        """Return the protected root label that owns a manifest key."""

        normalized_key = manifest_key.casefold()
        root_keys = [self._normalize_manifest_key(root) for root in self.get_protected_roots()]
        for root_key in sorted(root_keys, key=lambda item: (-len(item), item.casefold())):
            folded_root = root_key.casefold()
            if normalized_key == folded_root or normalized_key.startswith(folded_root + "/"):
                return root_key
        return "UNKNOWN"

    def _sort_key_for_path(self, path: Path) -> tuple[str, str]:
        """Return a stable ordering key for directory walking and root sorting."""

        normalized = self._normalize_manifest_key(path)
        return normalized.casefold(), normalized

    def _violation_summary(self, violation_type: str) -> str:
        """Return a human-readable summary for a manifest violation."""

        if violation_type == "CREATION":
            return "Protected file was created after the baseline snapshot."
        if violation_type == "DELETION":
            return "Protected file was deleted after the baseline snapshot."
        return "Protected file content changed between snapshots."

    def _assert_no_reparse_points(self, target: Path, matched_root: Path, *, session_id: str) -> None:
        current = target if target.exists() else target.parent
        while True:
            if self._path_has_reparse_point(current):
                raise self._unsafe_write_violation(
                    session_id=session_id,
                    path=target,
                    protected_root=self._normalize_manifest_key(matched_root),
                    summary="Write path contains a symlink or Windows reparse point.",
                    details={
                        "candidate_path": target.as_posix(),
                        "matched_root": matched_root.as_posix(),
                        "reparse_path": current.as_posix(),
                    },
                )
            if current == matched_root or current.parent == current:
                break
            if not self._is_relative_to(current.parent, matched_root):
                break
            current = current.parent

    def _path_has_reparse_point(self, path: Path) -> bool:
        try:
            info = os.lstat(path)
        except (FileNotFoundError, OSError):
            return False
        attributes = getattr(info, "st_file_attributes", 0)
        if attributes and attributes & self._REPARSE_ATTRIBUTE:
            return True
        try:
            return path.is_symlink()
        except OSError:
            return False

    def _unsafe_write_violation(
        self,
        *,
        session_id: str,
        path: Path,
        protected_root: str,
        summary: str,
        details: dict[str, Any],
    ) -> IntegrityViolation:
        violation = {
            "violation_type": "UNSAFE_WRITE_PATH",
            "path": self._normalize_manifest_key(path),
            "protected_root": protected_root,
            "severity": self.VIOLATION_SEVERITY["UNSAFE_WRITE_PATH"],
            "timestamp_utc": self._timestamp_utc(),
            "details": {
                "summary": summary,
                **details,
            },
        }
        message = f"Integrity enforcement blocked unsafe write path: {violation['path']}"
        report = IntegrityViolation(
            session_id=session_id,
            violations=[violation],
            state_drifted=False,
            message=message,
        ).to_report()
        report["failure_reason"] = message
        report["artifact_type"] = "integrity_violation"
        report["status"] = "invalid"
        report["timestamp_utc"] = violation["timestamp_utc"]
        report["session_id"] = str(session_id or "").strip()
        report["path"] = violation["path"]
        return IntegrityViolation(
            session_id=session_id,
            violations=[violation],
            state_drifted=False,
            message=message,
            report=report,
        )

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _timestamp_utc() -> str:
        """Return an ISO-8601 UTC timestamp with second precision."""

        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
