from __future__ import annotations

"""Human-governed promotion router with the strongest portable file durability posture.

The router writes and fsyncs a complete temporary file on the same volume before
``os.replace`` and verifies the replaced file by reading it back. POSIX systems may
additionally fsync a directory descriptor, but Python/Windows does not expose an
equivalent portable directory-fsync primitive. This module therefore makes no POSIX
directory-durability claim on Windows; it provides file flush/fsync, same-volume
replacement, read-back verification, and explicit recoverable failure states.
"""

import json
import os
from pathlib import Path
from typing import Any

from distillery.common import ContractError, canonical_bytes, utc_now
from ops.bundle import verify_bundle


TERMINAL_STATES = {"PROMOTED", "ROLLED_BACK", "ROLLBACK_FAILED", "PROMOTION_WRITE_FAILED"}


class PromotionRouter:
    def __init__(self, router_path: str | Path) -> None:
        self.router_path = Path(router_path)

    def current(self) -> dict:
        if not self.router_path.is_file():
            raise ContractError("router has no verified prior bundle")
        try:
            value = json.loads(self.router_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"current router is unreadable or corrupted: {type(exc).__name__}: {exc}") from exc
        if not isinstance(value, dict) or "bundle" not in value:
            raise ContractError("current router is missing its bundle record")
        return value

    def promote(self, candidate: dict, *, hg7_evidence: dict, human_decision: dict, readiness_check) -> dict:
        prior = self.current()
        verify_bundle(prior["bundle"])
        verify_bundle(candidate)
        if not hg7_evidence.get("finalized") or not hg7_evidence.get("passed") or hg7_evidence.get("bundle_hash") != candidate["bundle_hash"]:
            raise ContractError("HG-7 must be finalized for the exact candidate bundle")
        if human_decision.get("decision") != "PROMOTE" or not human_decision.get("authority"):
            raise ContractError("explicit human PROMOTE authority is mandatory")
        next_state = {"bundle": candidate, "promoted_at": utc_now(), "authority": human_decision["authority"]}
        try:
            self._atomic_write(next_state)
        except Exception as exc:
            return self._write_failure("PROMOTION_WRITE_FAILED", candidate, prior, exc)

        readiness_exception: Exception | None = None
        try:
            ready = bool(readiness_check(next_state))
        except Exception as exc:
            ready = False
            readiness_exception = exc
        if not ready:
            try:
                self._atomic_write(prior)
            except Exception as exc:
                result = self._write_failure("ROLLBACK_FAILED", candidate, prior, exc)
                if readiness_exception:
                    result["readiness_exception"] = self._exception_record(readiness_exception)
                return result
            result = {
                "status": "ROLLED_BACK",
                "active_bundle_hash": prior["bundle"]["bundle_hash"],
                "candidate_bundle_hash": candidate["bundle_hash"],
                "prior_bundle_hash": prior["bundle"]["bundle_hash"],
            }
            if readiness_exception:
                result["readiness_exception"] = self._exception_record(readiness_exception)
            return result
        return {
            "status": "PROMOTED",
            "active_bundle_hash": candidate["bundle_hash"],
            "prior_bundle_hash": prior["bundle"]["bundle_hash"],
        }

    def rollback(self, prior: dict) -> dict:
        verify_bundle(prior["bundle"])
        try:
            self._atomic_write(prior)
        except Exception as exc:
            return self._write_failure("ROLLBACK_FAILED", self._router_state_if_readable(), prior, exc)
        return {"status": "ROLLED_BACK", "active_bundle_hash": prior["bundle"]["bundle_hash"]}

    def _atomic_write(self, state: dict) -> None:
        self.router_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.router_path.with_suffix(self.router_path.suffix + ".next")
        encoded = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.router_path)
        observed = self.current()
        if canonical_bytes(observed) != canonical_bytes(state):
            raise ContractError("router read-back verification failed after replacement")

    def _write_failure(self, status: str, candidate: Any, prior: dict, exception: Exception) -> dict:
        if status not in {"ROLLBACK_FAILED", "PROMOTION_WRITE_FAILED"}:
            raise ContractError("invalid router write-failure status")
        return {
            "status": status,
            "candidate": candidate,
            "prior": prior,
            "exception": self._exception_record(exception),
            "router_state_if_readable": self._router_state_if_readable(),
            "recovery_instructions": [
                "Stop automatic routing changes.",
                "Verify every file referenced by the preserved prior bundle.",
                "Call PromotionRouter.rollback(preserved_prior) after storage/router health is restored.",
                "Verify the active bundle hash before resuming traffic.",
            ],
        }

    def _router_state_if_readable(self) -> dict | None:
        try:
            return self.current()
        except ContractError:
            return None

    @staticmethod
    def _exception_record(exception: Exception) -> dict:
        return {"type": type(exception).__name__, "message": str(exception)}


class ShadowPlanner:
    """Read-only shadow surface: intentionally exposes no tool-execution method."""

    def plan_diff(self, incumbent_plan: list[dict], candidate_plan: list[dict]) -> dict:
        return {"incumbent": incumbent_plan, "candidate": candidate_plan, "mutating_execution_available": False}
