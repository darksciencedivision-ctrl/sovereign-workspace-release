"""Local gate: deterministic pre-publication checks on a node's structured output
(Plan sections 7-P3, 9.3). Runs BEFORE anything leaves the node — a failed artifact
cannot advance (invariant 16), and the gate has no override path.

Gate criteria are declarative names bound to deterministic checks (never model output,
Buildout Directive section 4). Unknown criterion names fail closed. The verdict carries
per-criterion reasons so failures are traceable end-to-end.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

import jsonschema

from pathlib import Path

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_ARTIFACT_SCHEMA = json.loads((_SCHEMA_DIR / "artifact.schema.json").read_text(encoding="utf-8"))

PLACEHOLDER_MARKERS = ("TODO", "TBD", "FIXME", "lorem ipsum", "<placeholder>")


@dataclass(frozen=True)
class CheckResult:
    criterion: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class GateVerdict:
    verdict: str  # "PASS" | "FAIL"
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    def reasons(self) -> list[str]:
        return [f"{c.criterion}: {c.reason}" for c in self.checks if not c.passed]


class GateConfigError(Exception):
    """Unknown criterion or malformed gate definition — fail closed, never skip."""


def _check_output_parses(doc: dict[str, Any], _: bytes) -> CheckResult:
    ok = isinstance(doc, dict) and bool(doc)
    return CheckResult("output_parses", ok, "structured output is a non-empty object" if ok else "output is not a non-empty JSON object")


def _check_required_fields(doc: dict[str, Any], _: bytes) -> CheckResult:
    missing = [f for f in ("summary", "claims", "artifact") if f not in doc]
    return CheckResult("required_fields", not missing, "all required fields present" if not missing else f"missing fields: {missing}")


def _check_claims_cite_evidence(doc: dict[str, Any], _: bytes) -> CheckResult:
    claims = doc.get("claims")
    if not isinstance(claims, list) or not claims:
        return CheckResult("claims_cite_evidence", False, "no claims list")
    bad = [i for i, c in enumerate(claims) if not (isinstance(c, dict) and c.get("evidence_refs"))]
    return CheckResult("claims_cite_evidence", not bad,
                       "every claim carries evidence_refs" if not bad else f"claims without evidence_refs at indexes {bad}")


def _check_no_placeholders(doc: dict[str, Any], content: bytes) -> CheckResult:
    text = (json.dumps(doc) + content.decode("utf-8", errors="replace")).lower()
    hits = [m for m in PLACEHOLDER_MARKERS if m.lower() in text]
    return CheckResult("no_placeholders", not hits, "no placeholder markers" if not hits else f"placeholder markers found: {hits}")


def _check_artifact_metadata_valid(doc: dict[str, Any], content: bytes) -> CheckResult:
    meta = doc.get("artifact")
    if not isinstance(meta, dict):
        return CheckResult("artifact_metadata_valid", False, "artifact metadata missing")
    try:
        jsonschema.validate(meta, _ARTIFACT_SCHEMA)
    except jsonschema.ValidationError as exc:
        return CheckResult("artifact_metadata_valid", False, f"artifact@1.0 violation: {exc.message}")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if meta.get("artifact_id") != digest:
        return CheckResult("artifact_metadata_valid", False,
                           f"content hash mismatch: metadata says {meta.get('artifact_id')}, content is {digest}")
    if meta.get("size_bytes") != len(content):
        return CheckResult("artifact_metadata_valid", False, "size_bytes does not match content")
    return CheckResult("artifact_metadata_valid", True, "schema-valid and content-addressed correctly")


_CHECKS: dict[str, Callable[[dict[str, Any], bytes], CheckResult]] = {
    "output_parses": _check_output_parses,
    "required_fields": _check_required_fields,
    "claims_cite_evidence": _check_claims_cite_evidence,
    "no_placeholders": _check_no_placeholders,
    "artifact_metadata_valid": _check_artifact_metadata_valid,
}

DEFAULT_CRITERIA = tuple(_CHECKS)


class LocalGate:
    def __init__(self, criteria: tuple[str, ...] = DEFAULT_CRITERIA) -> None:
        unknown = [c for c in criteria if c not in _CHECKS]
        if unknown:
            raise GateConfigError(f"unknown gate criteria (fail closed): {unknown}")
        if not criteria:
            raise GateConfigError("a gate with no criteria cannot pass anything (fail closed)")
        self._criteria = criteria

    def evaluate(self, structured_output: dict[str, Any], artifact_content: bytes) -> GateVerdict:
        checks = tuple(_CHECKS[name](structured_output, artifact_content) for name in self._criteria)
        return GateVerdict("PASS" if all(c.passed for c in checks) else "FAIL", checks)
