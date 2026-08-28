"""Gate criteria registry (Plan §9.3, §7-P8; invariant 16).

Declarative, deterministic checks (never model output) stated BEFORE evaluation. Each
criterion is CRITICAL (its failure forces a FAIL verdict) or ADVISORY (its failure only
lowers the verdict to PASS_WITH_RESERVATIONS). Unknown criteria fail closed. A criterion is
a pure function of the GateContext, so a verdict is reproducible and its reasons traceable.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import jsonschema
from pathlib import Path

_ARTIFACT_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "artifact.schema.json").read_text(encoding="utf-8"))

# word-boundary markers so "todo" doesn't fire inside "mastodon" (spec-audit F4)
PLACEHOLDER_MARKERS = ("todo", "tbd", "fixme", "xxx", "wip", "hack", "stub", "placeholder", "lorem ipsum")
_PLACEHOLDER_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(m) for m in PLACEHOLDER_MARKERS) + r")(?![a-z])")


class Severity(str, Enum):
    CRITICAL = "critical"
    ADVISORY = "advisory"


@dataclass
class GateContext:
    artifact_content: bytes | None = None
    structured_output: dict[str, Any] | None = None
    evidence_refs: list[str] = field(default_factory=list)
    debate_record: dict[str, Any] | None = None
    unresolved_critical: int = 0
    evidence_resolver: Callable[[str], bool] | None = None
    plan_tasks: list[dict[str, Any]] | None = None  # for plan gates: [{task_id, deps}]


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    severity: Severity
    reason: str


# -- individual checks: (ctx) -> (passed, reason) -----------------------------

def _artifact_present(ctx: GateContext) -> tuple[bool, str]:
    ok = bool(ctx.artifact_content)
    return ok, "artifact present" if ok else "no artifact produced"


def _structured_output_valid(ctx: GateContext) -> tuple[bool, str]:
    d = ctx.structured_output
    ok = isinstance(d, dict) and bool(d) and "summary" in d and "claims" in d
    return ok, "structured output well-formed" if ok else "structured output missing/invalid"


def _artifact_content_addressed(ctx: GateContext) -> tuple[bool, str]:
    d = (ctx.structured_output or {}).get("artifact")
    if not isinstance(d, dict) or ctx.artifact_content is None:
        return False, "artifact metadata missing"
    try:
        jsonschema.validate(d, _ARTIFACT_SCHEMA)
    except jsonschema.ValidationError as exc:
        return False, f"artifact@1.0 violation: {exc.message}"
    digest = "sha256:" + hashlib.sha256(ctx.artifact_content).hexdigest()
    if d.get("artifact_id") != digest:
        return False, "artifact hash does not match content"
    if d.get("size_bytes") != len(ctx.artifact_content):
        return False, "artifact size_bytes does not match content length"
    return True, "artifact content-addressed correctly"


def _claims_cite_evidence(ctx: GateContext) -> tuple[bool, str]:
    claims = (ctx.structured_output or {}).get("claims")
    if not isinstance(claims, list) or not claims:
        return False, "no claims"
    bad = [i for i, c in enumerate(claims) if not (isinstance(c, dict) and c.get("evidence_refs"))]
    return (not bad), "every claim cites evidence" if not bad else f"claims without evidence at {bad}"


def _evidence_refs_resolve(ctx: GateContext) -> tuple[bool, str]:
    # W-67/U13: this is CRITICAL, so an unconfigured resolver is a REFUSAL, not a skip - a
    # pass nobody verified is exactly what a gate must not emit (sibling shape: fail closed).
    if ctx.evidence_resolver is None:
        return False, "no evidence resolver configured (fail closed)"
    unresolved = [r for r in ctx.evidence_refs if not ctx.evidence_resolver(r)]
    return (not unresolved), "all evidence resolves" if not unresolved else f"unresolved evidence: {unresolved}"


def _no_placeholders(ctx: GateContext) -> tuple[bool, str]:
    # W-68: the scan reads the PUBLISHED ARTIFACT bytes only. The structured packet is
    # model/adapter-authored prose; folding its JSON into the scanned text let a claim's
    # wording trip a CRITICAL artifact rule (17E measured this live). Detection itself -
    # markers, word boundaries - is untouched.
    text = (ctx.artifact_content or b"").decode("utf-8", errors="replace").lower()
    hits = sorted(set(_PLACEHOLDER_RE.findall(text)))
    return (not hits), "no placeholders" if not hits else f"placeholder markers: {hits}"


def _no_unresolved_critical(ctx: GateContext) -> tuple[bool, str]:
    ok = ctx.unresolved_critical == 0
    return ok, "no unresolved critical issues" if ok else f"{ctx.unresolved_critical} unresolved critical issue(s)"


def _debate_resolved(ctx: GateContext) -> tuple[bool, str]:
    """Advisory: if a debate informs this gate, it must have CONVERGED or preserved dissent —
    a debate that was silently cut off is a reservation, not a clean pass."""
    if ctx.debate_record is None:
        return True, "no debate attached"
    outcome = (ctx.debate_record.get("result") or {}).get("outcome")
    if outcome == "CONVERGED":
        return True, "debate converged"
    if outcome == "DISSENT_PRESERVED":
        return False, "debate preserved dissent (unresolved disagreement)"
    return False, f"debate outcome {outcome!r} unresolved"


def _plan_acyclic(ctx: GateContext) -> tuple[bool, str]:
    """Referential integrity AND genuine acyclicity (DFS): a dependency cycle t1->t2->t1 is a
    FAIL, not just an undefined-dep check."""
    tasks = ctx.plan_tasks or []
    if not tasks:
        return False, "empty plan"
    deps = {t["task_id"]: list(t.get("deps", [])) for t in tasks}
    for tid, ds in deps.items():
        missing = [d for d in ds if d not in deps]
        if missing:
            return False, f"task {tid} has undefined deps {missing}"
    WHITE, GREY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in deps}

    def visit(node: str, stack: list[str]) -> list[str] | None:
        color[node] = GREY
        for d in deps[node]:
            if color[d] == GREY:                      # back-edge -> cycle
                return stack[stack.index(d):] + [d]
            if color[d] == WHITE:
                cyc = visit(d, stack + [d])
                if cyc:
                    return cyc
        color[node] = BLACK
        return None

    for tid in deps:
        if color[tid] == WHITE:
            cyc = visit(tid, [tid])
            if cyc:
                return False, f"dependency cycle: {' -> '.join(cyc)}"
    return True, "plan well-formed (acyclic)"


_REGISTRY: dict[str, tuple[Callable[[GateContext], tuple[bool, str]], Severity]] = {
    "artifact_present": (_artifact_present, Severity.CRITICAL),
    "structured_output_valid": (_structured_output_valid, Severity.CRITICAL),
    "artifact_content_addressed": (_artifact_content_addressed, Severity.CRITICAL),
    "claims_cite_evidence": (_claims_cite_evidence, Severity.CRITICAL),
    "evidence_refs_resolve": (_evidence_refs_resolve, Severity.CRITICAL),
    "no_placeholders": (_no_placeholders, Severity.CRITICAL),
    "no_unresolved_critical": (_no_unresolved_critical, Severity.CRITICAL),
    "debate_resolved": (_debate_resolved, Severity.ADVISORY),
    "plan_acyclic": (_plan_acyclic, Severity.CRITICAL),
}


class UnknownCriterion(Exception):
    pass


def evaluate_criterion(name: str, ctx: GateContext) -> CriterionResult:
    if name not in _REGISTRY:
        raise UnknownCriterion(f"unknown gate criterion (fail closed): {name!r}")
    fn, severity = _REGISTRY[name]
    passed, reason = fn(ctx)
    return CriterionResult(name, passed, severity, reason)


def known_criteria() -> tuple[str, ...]:
    return tuple(_REGISTRY)
