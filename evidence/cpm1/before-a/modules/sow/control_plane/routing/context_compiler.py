"""Scoped context compiler (Plan §7-P9; invariant 8).

Assembles the context a node receives for a task by role + task + NEED-TO-KNOW — never a
default full-transcript forward. For a task it includes only:
  - the task objective (the scoped directive for THIS task);
  - the ACCEPTED outputs of the task's DIRECT dependencies (what the worker must build on);
  - the node's role scope (its constitution/directive);
  - explicitly requested evidence refs.
It excludes: sibling tasks' work, candidates still under review, superseded/rejected entries,
and the project's full history. All reads go through MCP (governed, provenance-bearing).

The naive baseline (`compile_naive`) forwards the whole shared transcript — the compiler's
job is to beat it measurably (token_meter), and a test asserts the scoped bundle contains
ONLY the need-to-know entries.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScopedContext:
    task_id: str
    role: str
    objective: str
    role_scope: str
    dependency_outputs: list[dict[str, Any]] = field(default_factory=list)  # {entry_id, task_id, text}
    evidence: list[dict[str, Any]] = field(default_factory=list)
    included_entry_ids: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Flatten to the text a node would actually receive (what we meter)."""
        parts = [f"# ROLE SCOPE ({self.role})\n{self.role_scope}",
                 f"# TASK {self.task_id} OBJECTIVE\n{self.objective}"]
        for d in self.dependency_outputs:
            parts.append(f"# DEPENDENCY OUTPUT (task {d['task_id']}, {d['entry_id']})\n{d['text']}")
        for e in self.evidence:
            parts.append(f"# EVIDENCE {e['entry_id']}\n{e['text']}")
        return "\n\n".join(parts)


def _content(mcp_reader: Any, entry_id: str) -> str:
    res = mcp_reader.call("get_content", entry_id=entry_id)
    return base64.b64decode(res["content_b64"]).decode("utf-8", errors="replace")


class ContextCompiler:
    def __init__(self, mcp_reader: Any) -> None:
        self._mcp = mcp_reader

    def compile(self, *, task_id: str, deps: list[str], role: str, objective_entry: str,
                role_scope: str, project_id: str, evidence_refs: list[str] | None = None) -> ScopedContext:
        objective = _content(self._mcp, objective_entry)
        included = [objective_entry]

        # need-to-know: ACCEPTED outputs whose provenance task_id is a DIRECT dependency
        dep_outputs: list[dict[str, Any]] = []
        if deps:
            dep_set = set(deps)
            for entry in self._mcp.call("read_status", status="ACCEPTED"):
                if entry.get("project_id") != project_id:
                    continue
                if (entry.get("provenance", {}) or {}).get("task_id") in dep_set:
                    dep_outputs.append({"entry_id": entry["entry_id"],
                                        "task_id": entry["provenance"]["task_id"],
                                        "text": _content(self._mcp, entry["entry_id"])})
                    included.append(entry["entry_id"])

        evidence = []
        for ref in (evidence_refs or []):
            evidence.append({"entry_id": ref, "text": _content(self._mcp, ref)})
            included.append(ref)

        return ScopedContext(task_id=task_id, role=role, objective=objective, role_scope=role_scope,
                             dependency_outputs=dep_outputs, evidence=evidence, included_entry_ids=included)

    def measurement_baseline_naive(self, *, project_id: str, _measurement_only: bool = True) -> str:
        """MEASUREMENT COMPARAND ONLY — never feed this to a node. Forwards the ENTIRE shared
        transcript (every accepted/candidate/under-review entry, unscoped): precisely the
        blanket forward invariant 8 forbids as a default. It exists solely so the scoped
        compiler's reduction can be measured against it. The `_measurement_only` guard makes an
        accidental use as a context path a visible, deliberate act."""
        if not _measurement_only:
            raise ValueError("measurement_baseline_naive is a measurement comparand, not a "
                             "context path — forwarding it to a node violates invariant 8")
        parts: list[str] = []
        for status in ("ACCEPTED", "CANDIDATE", "UNDER_REVIEW"):
            for entry in self._mcp.call("read_status", status=status):
                if entry.get("project_id") != project_id:
                    continue
                parts.append(f"# {status} {entry['entry_id']} (task {(entry.get('provenance') or {}).get('task_id')})\n"
                             + _content(self._mcp, entry["entry_id"]))
        return "\n\n".join(parts)
