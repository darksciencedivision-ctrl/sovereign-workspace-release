# DECISIONS.md — SWS-UI-001 v1.2
# Operator: sam
# Date: 2026-08-21

## Gate 0 — Directive Authorization

SWS-UI-001 v1.2 approved for Phase 0/1: ☑ yes
Date: 2026-08-21
By: sam (operator)

## Gate 1 — Discovery Authorization

Phase 1 discovery reviewed. All §3 FACTs confirmed or corrected in DISCOVERY.md.
Four ADRs accepted: ADR-001 (Architecture), ADR-002 (SOVEREIGN launch vector),
ADR-003 (Debate identity fingerprint), ADR-004 (SOW readiness mode + executable chain).

## §6 — Module Install Authorization

**Option A authorized** — workspace-owned runtime instances under `Production Workspace\modules\`.

Date: 2026-08-21
By: sam (operator)

## SOVEREIGN dependency lock — pre-authorization

The operator pre-authorizes creation of a workspace-owned resolved lock for SOVEREIGN.
The lock will be produced by `pip freeze` from a clean `pip install -r requirements.txt`
resolve inside the workspace-owned venv, written to `modules/sovereign/WORKSPACE-RESOLVED-LOCK.txt`,
and hashed into `INSTALL-PROVENANCE.json`. This pre-authorization avoids the STOP at Gate 2.

## SOW live tree HEAD

The operator acknowledges that the actual SOW HEAD is `6d23a81082836778ffd46c70151821b467dc7432`
(not `bad029e7` as stated in the directive §3.1). The directive's stated HEAD is stale.
The actual HEAD, dirty-state classification (DIRTY_TRACKED_AND_UNTRACKED), and working-tree
captures are recorded in `evidence/sow-git-before.txt` and `DISCOVERY.md`.

## SOVEREIGN and Debate Table live trees

The operator states: no live trees for SOVEREIGN or Debate Table exist on this host.
The sole source artifacts are the packaged zips in `D:\Product Software\`.

## Distillery snapshot selection

Exactly one snapshot folder matches: `SOVEREIGN_DISTILLERY_ENTERPRISE_20260821T011825Z_5ff6f56e`.
No ambiguity rule needed. The live tree at `D:\Sovereign Distillery\` is the canonical source
for file-driven status parsing.