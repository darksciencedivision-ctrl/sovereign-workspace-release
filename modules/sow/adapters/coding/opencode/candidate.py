"""Phase 14C `.gate`: package a driven worktree as a CANDIDATE + controlled merge.

This is the FINAL cell of directive §9 table 14C:

    … isolated worktree modification → CANDIDATE artifact submitted → controlled merge path passed

`.harness` proved a supervisor-spawned OpenCode; `.worktree` drove it in an isolated worktree from
scoped MCP context. This module turns a driven `NodeWorktree` into a governed CANDIDATE published to
shared MCP memory THROUGH the node-local gate, and couples that gate verdict to
`node_runtime.workspace.worktree.MergeCoordinator` so the trunk merge requires the SAME passing gate
AND explicit operator approval. Load-bearing invariants, all enforced in code and fail-closed:

  - **Worker publishes CANDIDATE, never self-canonizes (invariant 10).** `publish_candidate` writes
    the entry with `status="CANDIDATE"`; promotion to ACCEPTED is a SEPARATE transition performed by a
    DIFFERENT node (invariant 18) — never by this module.
  - **Provenance on every shared entry (invariant 11).** Every CANDIDATE carries the full
    `memory@1.0` provenance block (author_node/task_id/ts/directive_version/confidence + evidence).
  - **A failed artifact cannot advance (invariant 16).** The node-local gate runs BEFORE publish; a
    FAIL verdict refuses to publish AND refuses to merge — nothing leaves the node.
  - **The system never self-authorizes the protected merge (invariant 1).** The trunk merge goes
    only through `MergeCoordinator.merge`, which requires the passing gate verdict AND
    `operator_approved is True`; a refusal is a governed outcome, recorded, never a crash.

HONESTY (directive §6, register U31). A small local coder did NOT complete a live schema-correct edit
this session (`.worktree` recorded this: OpenCode drove and executed its real tools, but the flaky
local model did not land a completed edit headlessly). So the worktree edit this module packages and
merges is a DETERMINISTIC SEEDED edit, not live-model output — `CandidatePacket.from_live_model`
records which, and the caller/evidence states it plainly. The GOVERNED path (package → node-local
gate → CANDIDATE publish → controlled merge) is the system under test and is exercised end-to-end
regardless of where the bytes came from; no live landed edit or live merge is ever claimed here.
"""
from __future__ import annotations

import base64
import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from adapters.coding.opencode.git_porcelain import parse_porcelain_z
from node_runtime.workspace.git_runner import GitTimeout, run_git
from node_runtime.gate.local_gate import GateVerdict, LocalGate
from node_runtime.workspace.worktree import (
    MergeCoordinator,
    MergeRefused,
    NodeWorktree,
    WorktreeError,
    WorktreeManager,
)

# logical media type of the packaged change — a proposed worktree state, not a frontier text answer
_MEDIA_TYPE = "text/x-worktree-manifest"

# the merge coordinator speaks the control-plane gate vocabulary (PASS / PASS_WITH_RESERVATIONS); the
# node-local gate is binary (PASS / FAIL). A FAIL never reaches the merge — invariant 16 refuses at
# the early return — so the verdict fed to the merger is always a genuine PASS, not a coerced constant.


class CandidateRefused(Exception):
    """The node-local gate failed the packaged artifact — it may not be published or merged
    (invariant 16, fail closed)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_out(repo: Path, *args: str) -> str:
    # CR-028: bounded, non-interactive git wrapper (timeout + process-tree kill).
    try:
        rc, out, err = run_git(repo, *args, timeout=120)
    except GitTimeout as exc:
        raise CandidateRefused(f"git {' '.join(args)} timed out in {repo}: {exc}") from exc
    if rc != 0:
        raise CandidateRefused(f"git {' '.join(args)} failed in {repo}: {err.strip()}")
    return out


def _git_out_bytes(repo: Path, *args: str) -> bytes:
    try:
        rc, out, err = run_git(repo, *args, timeout=120, text=False)
    except GitTimeout as exc:
        raise CandidateRefused(f"git {' '.join(args)} timed out in {repo}: {exc}") from exc
    if rc != 0:
        msg = (err or b"").decode("utf-8", "replace").strip()
        raise CandidateRefused(f"git {' '.join(args)} failed in {repo}: {msg}")
    return out


def _worktree_changes(wt_path: Path) -> dict[str, bytes | None]:
    """Map each changed worktree-relative path to its NEW content bytes (None ⇒ deleted). Reads
    `git status -z --porcelain` inside the worktree, so C-quoted / non-ASCII paths stay literal.
    Fail-closed: if git status cannot run, `_git_out_bytes` raises `CandidateRefused`."""
    raw = _git_out_bytes(wt_path, "status", "-z", "--porcelain", "--untracked-files=all")
    changes: dict[str, bytes | None] = {}
    for code, rel in parse_porcelain_z(raw):
        if "D" in code and not (wt_path / rel).exists():
            changes[rel] = None
            continue
        try:
            changes[rel] = (wt_path / rel).read_bytes()
        except OSError:
            changes[rel] = None
    return changes


def _render_manifest(node_id: str, task_id: str, changes: dict[str, bytes | None]) -> bytes:
    """Deterministic, content-addressable rendering of the proposed worktree state. Sorted by path
    so the same change always hashes the same. The manifest IS the CANDIDATE artifact content — the
    node-local gate's `no_placeholders` check then meaningfully scans the PROPOSED code (a TODO/FIXME
    left in the change fails the gate), and its `artifact_metadata_valid` check ties this exact byte
    string to the artifact hash."""
    lines: list[str] = [f"# worktree change manifest — node {node_id}, task {task_id}"]
    for rel in sorted(changes):
        body = changes[rel]
        lines.append(f"--- {rel} ---")
        if body is None:
            lines.append("<deleted>")
        else:
            lines.append(body.decode("utf-8", errors="replace"))
    return ("\n".join(lines) + "\n").encode("utf-8")


@dataclass(frozen=True)
class CandidatePacket:
    """A driven worktree packaged for governed submission. `content` is exactly the bytes that get
    content-addressed, gated, and published — hashing/schema-validation all key off it."""

    node_id: str
    task_id: str
    context_entry_id: str
    changed_files: tuple[str, ...]
    content: bytes
    content_hash: str          # "sha256:…" over `content`
    structured: dict[str, Any]  # {summary, claims, artifact} — the node-local gate's input
    from_live_model: bool       # honesty (U31): True ONLY if a real model drive produced the edit
    model: str | None = None    # the model id the edit came from (e.g. "ollama/…") when live; None ⇒ seeded

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id, "task_id": self.task_id,
            "context_entry_id": self.context_entry_id, "changed_files": list(self.changed_files),
            "content_hash": self.content_hash, "from_live_model": self.from_live_model,
            "model": self.model,
        }


def package_worktree_candidate(
    worktree: NodeWorktree, *, task_id: str, context_entry_id: str, author_node: str | None = None,
    from_live_model: bool, model: str | None = None, ts: str | None = None,
) -> CandidatePacket:
    """Read what the drive changed in `worktree`, render a deterministic content-addressed manifest,
    and build the `{summary, claims, artifact}` structured output the node-local gate evaluates.

    Fail-closed: a worktree with NO changes cannot be packaged into a CANDIDATE (there is nothing to
    submit) — refuse rather than publish an empty artifact. `from_live_model` is recorded verbatim; a
    caller must NEVER pass True unless a real model actually produced the edit (directive §6, U31).
    `model` is the id the edit came from (e.g. `drive.model`) — recorded in provenance on a live edit
    so a genuine model-produced CANDIDATE carries the actual model, not a generic marker (invariant 11)."""
    node_id = author_node or worktree.node_id
    changes = _worktree_changes(worktree.path)
    if not changes:
        raise CandidateRefused(
            "no worktree changes to package — refuse to submit an empty CANDIDATE (fail closed)")
    changed_files = tuple(sorted(changes))
    content = _render_manifest(node_id, task_id, changes)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    when = ts or _now()
    structured = {
        "summary": (f"coding CANDIDATE for {task_id}: {len(changed_files)} file(s) changed in "
                    f"worktree {worktree.branch}"),
        "claims": [
            {"text": "change confined to the node's own worktree",
             "evidence_refs": [worktree.branch]},
            {"text": "objective read from a single scoped MCP entry (invariant 8)",
             "evidence_refs": [context_entry_id]},
            {"text": "artifact content-addressed", "evidence_refs": [digest]},
        ],
        "artifact": {
            "artifact_id": digest, "media_type": _MEDIA_TYPE, "size_bytes": len(content),
            "created_by_node": node_id, "task_id": task_id, "ts": when, "schema": "artifact@1.0",
        },
    }
    return CandidatePacket(
        node_id=node_id, task_id=task_id, context_entry_id=context_entry_id,
        changed_files=changed_files, content=content, content_hash=digest,
        structured=structured, from_live_model=from_live_model, model=model)


class WorktreeCandidateGate:
    """Node-local gate + CANDIDATE publish for a driven coding worktree (invariants 16, 10, 11)."""

    def __init__(self, local_gate: LocalGate | None = None,
                 on_event: Callable[..., Any] | None = None) -> None:
        self._gate = local_gate or LocalGate()
        self._on_event = on_event

    def _emit(self, kind: str, **data: Any) -> None:
        if self._on_event is not None:
            self._on_event(kind, **data)

    def evaluate(self, packet: CandidatePacket) -> GateVerdict:
        """Run the node-local gate on the packaged artifact BEFORE anything leaves the node."""
        verdict = self._gate.evaluate(packet.structured, packet.content)
        self._emit("candidate_local_gate", node_id=packet.node_id, task_id=packet.task_id,
                   verdict=verdict.verdict, reasons=verdict.reasons())
        return verdict

    def publish(self, mcp_client: Any, packet: CandidatePacket, *,
                verdict: GateVerdict | None = None, confidence: str = "medium") -> dict[str, Any]:
        """Gate, then publish the CANDIDATE with full provenance. A FAIL verdict REFUSES to publish
        (invariant 16 — a failed artifact cannot advance); the node never self-canonizes, so status
        is always CANDIDATE (invariant 10)."""
        verdict = verdict or self.evaluate(packet)
        if not verdict.passed:
            self._emit("candidate_refused", node_id=packet.node_id, task_id=packet.task_id,
                       reasons=verdict.reasons())
            raise CandidateRefused(
                f"node-local gate FAIL — CANDIDATE not published (invariant 16): {verdict.reasons()}")
        # record the true origin of the change: the actual model id for a live edit (invariant 11 —
        # never under-record provenance the system already knows), or the honest "seeded-edit" marker.
        if packet.from_live_model:
            model_marker = packet.model or "local-coder"
        else:
            model_marker = "seeded-edit"
        provenance = {
            "author_node": packet.node_id, "task_id": packet.task_id, "ts": _now(),
            "directive_version": "v2.4", "confidence": confidence, "model": model_marker,
            "evidence": [packet.context_entry_id, packet.content_hash],
        }
        pub = mcp_client.call(
            "publish", kind="finding", tier="shared_project",
            content_b64=base64.b64encode(packet.content).decode("ascii"),
            provenance=provenance, status="CANDIDATE")
        self._emit("candidate_published", node_id=packet.node_id, task_id=packet.task_id,
                   entry_id=pub.get("entry_id"), status=pub.get("status"))
        return {"published": True, "entry_id": pub["entry_id"], "status": pub["status"],
                "local_gate": verdict.verdict, "content_hash": packet.content_hash}


@dataclass
class ControlledMergeResult:
    """The observable outcome of the full `.gate` chain for one driven worktree."""

    local_gate: str                # "PASS" | "FAIL"
    published: bool
    entry_id: str | None
    merged: bool
    merge_sha: str | None
    branch_sha: str | None
    refused_reason: str | None = None
    from_live_model: bool = False
    changed_files: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "local_gate": self.local_gate, "published": self.published, "entry_id": self.entry_id,
            "merged": self.merged, "merge_sha": self.merge_sha, "branch_sha": self.branch_sha,
            "refused_reason": self.refused_reason, "from_live_model": self.from_live_model,
            "changed_files": list(self.changed_files),
        }


def submit_candidate_and_merge(
    *, mcp_client: Any, worktree_manager: WorktreeManager, merger: MergeCoordinator,
    worktree: NodeWorktree, packet: CandidatePacket, operator_approved: bool,
    gate: WorktreeCandidateGate | None = None, commit_message: str | None = None,
    confidence: str = "medium",
) -> ControlledMergeResult:
    """The whole `.gate` chain, fail-closed at every hop:

      1. node-local gate (invariant 16) — a FAIL stops here: NOT published, NOT committed, NOT merged;
      2. commit the change on the node's own branch (the only writer of that branch) — done BEFORE
         publish so a commit failure aborts fail-closed with nothing having left the node;
      3. publish CANDIDATE to shared MCP memory with provenance (invariants 10, 11);
      4. controlled merge via `MergeCoordinator.merge` — requires the passing gate verdict AND
         `operator_approved is True` (invariant 1). A refusal (no approval / conflict) is a governed
         outcome recorded on the result, NOT a crash — the CANDIDATE stays published for review.

    Promotion of the MCP entry to ACCEPTED is deliberately NOT done here: a different node must do it
    (invariant 18 — no node solely judges its own work)."""
    gate = gate or WorktreeCandidateGate()
    verdict = gate.evaluate(packet)
    if not verdict.passed:
        return ControlledMergeResult(
            local_gate=verdict.verdict, published=False, entry_id=None, merged=False,
            merge_sha=None, branch_sha=None,
            refused_reason=f"node-local gate FAIL: {verdict.reasons()}",
            from_live_model=packet.from_live_model, changed_files=packet.changed_files)

    # commit the node's own branch BEFORE publish: a commit failure then aborts with nothing
    # published or merged (fail closed), rather than crashing after the CANDIDATE has left the node.
    try:
        branch_sha = worktree_manager.commit(
            worktree.node_id, commit_message or f"candidate: {packet.task_id}")
    except WorktreeError as exc:
        return ControlledMergeResult(
            local_gate=verdict.verdict, published=False, entry_id=None, merged=False,
            merge_sha=None, branch_sha=None, refused_reason=f"worktree commit failed: {exc}",
            from_live_model=packet.from_live_model, changed_files=packet.changed_files)

    pub = gate.publish(mcp_client, packet, verdict=verdict, confidence=confidence)
    try:
        # feed the merger the ACTUAL gate verdict (not a constant) so a non-PASS is structurally
        # incapable of producing a merge — MergeCoordinator's own verdict guard stays a live defense.
        merge_sha = merger.merge(
            worktree, gate_verdict=verdict.verdict, operator_approved=operator_approved)
    except MergeRefused as exc:
        # not-approved / conflict is the CORRECT governed behaviour (invariant 1), not an error to
        # swallow silently: record it, leave the CANDIDATE published for review, do not merge.
        return ControlledMergeResult(
            local_gate=verdict.verdict, published=True, entry_id=pub["entry_id"], merged=False,
            merge_sha=None, branch_sha=branch_sha, refused_reason=str(exc),
            from_live_model=packet.from_live_model, changed_files=packet.changed_files)
    return ControlledMergeResult(
        local_gate=verdict.verdict, published=True, entry_id=pub["entry_id"], merged=True,
        merge_sha=merge_sha, branch_sha=branch_sha, from_live_model=packet.from_live_model,
        changed_files=packet.changed_files)
