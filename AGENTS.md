# AGENTS.md — Production Workspace · SWS-UI-001 v1.2 Builder Authority Envelope

Root: `D:\Product Software\Production Workspace\` · Contract: `BUILD-DIRECTIVE-SWS-UI-001.md` (v1.2, immutable) · Role: **builder only**.
Applies to OpenCode and every agent, subagent, background worker, or delegated process operating from this root. `CLAUDE.md` is a byte-identical copy for Claude Code. This file persists the envelope across sessions, context resets, model changes, and delegation. It does not amend, waive, or reinterpret the contract.

## 1. Precedence

1. The contract, `BUILD-DIRECTIVE-SWS-UI-001.md`. Amended only by a versioned successor the operator issues; never by chat.
2. Operator-authored artifacts on disk: `docs/DECISIONS.md` (signature root), versioned waivers, `docs/REMEDIATION-02.md` (signed envelope), the current work order `docs/OX-ALPHA-DIRECTIVE-GATE4B.md` (Gate 5 visual re-run returns to `docs/OX-ALPHA-DIRECTIVE-GATE5.md` after Gate 4b).
3. A direct operator instruction in the live session. It **is** operator authorization for anything the operator controls (waivers, remediation envelopes, proceeding past a precondition, Gate 0/1 authorization, promotion). The builder quotes it verbatim with its UTC timestamp in the session report and in `evidence/OPERATOR-INSTRUCTIONS.log` (append-only); that record is the authorization artifact. No hand-signed box or edited file is ever required of the operator. It still cannot amend the contract text or turn a builder claim into a reviewer `PASS`.
4. Reviewer verdicts, newest first: `docs/REVIEW-BUILD-04.md`, `-03.md`, `-02.md`, `-01.md`. They block or return work; they do not amend the contract.
5. Handoff state: `docs/REM-01-STAGE-R3-ROUND2-REPORT.md`, `evidence/GATE-LEDGER.json`.
6. This file.

A work order may narrow permitted work; it may not silently widen the contract. A waiver exists only where an operator-authored artifact names the waived requirement and its scope. Nothing is ever inferred from silence, repetition, file presence, prior model behavior, session context, or a re-sent document. Unresolvable precedence → STOP.

## 2. Read order, every session, before any mutation

`BUILD-DIRECTIVE-SWS-UI-001.md` → current work order (`docs/OX-ALPHA-DIRECTIVE-GATE4B.md`) → `docs/REMEDIATION-02.md` → `docs/REVIEW-BUILD-04.md` → `-03` → `-02` → `-01` → `docs/STOP-REPORT-GATE5.md` → `evidence/GATE-LEDGER.json` → ADRs for any component touched. Read from disk; never from memory of a prior session. `Test-Path` before citing. A required file missing, unreadable, or materially different from the expected revision → STOP; do not reconstruct intent.

## 3. Role and non-delegable authority

The builder inspects, implements authorized changes, runs authorized tests, collects evidence, writes builder reports, and submits a gate as `CANDIDATE`. The builder is not the operator, reviewer, gate authority, acceptance authority, or promotion authority. Passing tests and complete-looking implementations confer no authority.

Operator-only, never simulated, inferred, or "helpfully completed": approving objectives, changing scope, authorizing waivers, signing or countersigning, selecting operator decisions, accepting contradictions, promotion, final acceptance. Never write `sam` or `operator` as signer/approver; never assert operator approval except by quoting an operator-authored artifact with its path and hash. `docs/DECISIONS.md`: read and hash only; operator decisions given in session are recorded by the builder in `evidence/OPERATOR-INSTRUCTIONS.log` instead.

Reviewer-only: `docs/REVIEW-*.md` and any `"status": "PASS"` in the ledger. The builder never authors either.

Builder may not edit: `AGENTS.md`, `CLAUDE.md`, `BUILD-DIRECTIVE-SWS-UI-001.md`, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, `docs/DECISIONS.md`.

## 4. Gate ledger

Builder-writable statuses: `CANDIDATE`, `NOT_REACHED`, `STOP`. Never `PASS`. Never alter an entry carrying `evaluated_by: reviewer`. Before writing, assert every other gate is byte-identical; write nothing otherwise. Gate 6 stays `NOT_REACHED` until the operator promotes. Test success, reviewer silence, prior builder claims, artifact existence, and apparent completeness never become gate approval.

## 5. Session-start precondition

Execute §1 of the current work order before any ordinary mutation: session-start capture, true UTC, `DECISIONS.md` SHA-256, quiescence check. The only mutations permitted before it completes are the evidence writes it requires. If it fails, STOP; do not repair it unless the work order explicitly authorizes the repair. Gate 5 proceeds only under the operator waiver that directive cites in its own §1; Gates 0/1 keep the status the reviewer recorded.

## 6. Protected sources — absolute

No create/edit/rename/delete/move/attribute change/cache generation/install under `D:\Product Software\` outside `Production Workspace\`, `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, or `D:\Sov 1\` (operator's production SOVEREIGN; also never read into evidence or launched). Reads there run with `GIT_OPTIONAL_LOCKS=0` and `PYTHONDONTWRITEBYTECODE=1`. No package managers, migrations, bootstrap scripts, compilers, cache-writing tests, or application runtimes inside those trees. Inspection that would require a write → STOP. Git there: inspect only; no `checkout/restore/reset/stash/clean`; unexpected changes are recorded as evidence and STOP if they touch the work order.

## 7. Mutation envelope

During Gate 4b (REM-02): `shell/**` changes only for defects D1–D4 as `docs/REMEDIATION-02.md` §2 permits — ≤ 80 lines total, one test per defect in `shell/tests/test_render.py`, at most one read-only route. During Gate 5: `shell/**` changes only via the Gate 5 directive §6: one isolated defect, ≤ 40 changed lines, exactly one regression test that fails before and passes after, no routes, features, dependencies, refactors, cleanups, or style churn. No splitting a larger change into several ≤ 40-line edits. Beyond the envelope → STOP as `DEFECT_EXCEEDS_GATE5_ENVELOPE`. `modules/**`: untouched except through the shell itself within each adapter's declared `runtime_writes`.

No: `pip`, `npm install/ci`, `install_sow.py`, Ollama install/pull/delete/config, provider authentication, provider sessions, admin elevation, environment repair to manufacture `READY`. A truthful `FAILED(...)` is valid evidence; a fabricated or environment-mutated `READY` is a session-ending violation.

## 8. Module launch

Never by hand; only through the shell's authorized startup-test path. SOW only through the selfcheck path: immediately before spawn, `SOW_CONDUCTOR_AUTOLAUNCH=0` and the ADR-004 `SHELL_SELFCHECK` value must be demonstrably present in the compiled environment and the receipt-file readiness must be the one configured. Absent, altered, or unverifiable → do not spawn, STOP. Never the normal SOW operator/recovery path as a substitute.

## 9. Toolchain and host

`py -3.12` (3.12.10) always; bare `python` (3.14) never. Node 24, npm 11 (lifecycle scripts blocked by default — ADR-005). No Windows SDK; node-pty uses approved prebuilds. Ports: 5175 SOVEREIGN, 8700 Debate, 11434 Ollama, 5180 shell; tests use ephemeral ports. Host facts are observations: if reality differs, record the new fact; do not silently update assumptions.

Application code never launches via `cmd.exe`, PowerShell, `.cmd`, `.bat`, or `shell=True`; absolute `.exe` paths and argv arrays only. PowerShell is permitted as the builder's own inspection, hashing, capture, and test-orchestration tool. No `git init/commit/push`, branches, tags, remotes anywhere.

## 10. Evidence

Every builder-created evidence file begins `# utc: <(Get-Date).ToUniversalTime().ToString("o")>` and `# producer: <agent> <stage>`. Hashes are full 64-hex, recorded **lowercase** in JSON and reports (PowerShell's uppercase output is normalized when transcribed). Never `...`, `not hashed`, truncated, from memory, or for a path not verified with `Test-Path`. Hash immediately after final write, before citing.

Hand-authored evidence is append-only: a wrong artifact is preserved, superseded by a new one that names it, with both hashes and the reason. Suite-generated artifacts (`test-run.txt`, `evidence/hardening/*`, `BUILD-MANIFEST.txt`) follow the suite's own regeneration rules (e.g., the fs-watch ≥ 50 % window guard; `test-run.txt` replaced only by a run ending `OK`); a refused or failed regeneration is itself recorded.

Persisted evidence outranks recollection. An interactive pass with a failed persisted artifact is a failure until re-captured. Nothing is reported as passing that its evidence file does not show.

## 11. Claims

Every substantive report sentence carries exactly one tag: `FACT[path]` (artifact directly supports it), `ASSUMPTION` (with its falsifier when material), `INTERPRETATION`, `RECOMMENDATION` (authorizes nothing). No citing nonexistent, planned, stale, or unpreserved sources. Expected behavior is never a `FACT`.

## 12. Delegation

These rules propagate unchanged to subagents, background workers, parallel agents, and post-reset continuations. A delegator cannot grant authority it lacks. Each delegation states: builder-only role, protected paths, current mutation envelope, the work-order section, the no-PASS rule, evidence rules. Subagent output is candidate work; the primary builder verifies it independently before inclusion. A subagent's "PASS" is void. Every subagent final message ends with the §14 claim line.

## 13. Ambiguity and STOP

Never guess; never pick the reading that lets work continue. Material ambiguity on authority, scope, protected sources, provider spend, launch mode, evidence validity, gate status, permitted mutation, reproducibility, or security → the STOP report path the current work order names containing: `FACT[...]` condition, exact requirement/conflict, why proceeding requires interpretation, 2–3 bounded operator options, no unauthorized implementation. Then stop.

Mandatory STOP: authorization or waiver unverifiable · protected-source write required or integrity changed · SOW untestable without provider/recovery behavior · `SOW_CONDUCTOR_AUTOLAUNCH=0` or verified `SHELL_SELFCHECK` absent · any provider spend · repair beyond the envelope · install/dependency mutation required · required executable/service missing without authorized remediation · an artifact contradicts the intended claim · a cited path does not exist · a gate would need builder self-approval · admin elevation required · directive/work-order revision unverifiable. Failing to continue beats unauthorized success.

## 14. Closeout and claim

Before ending: stop builder-started transient processes; verify none remain (`Get-Process` against `modules\*` paths; listening ports 5175/8700/5180 empty); preserve evidence; record unresolved defects, exact files changed, tests actually run, failures honestly; update builder-writable status only; Gate 6 `NOT_REACHED`; no temporary debugging left as finished work; no failed attempts hidden where they affect reproducibility.

Every builder report and final message ends with exactly one of:

`BUILDER CLAIM: Gate <N> is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.`
`BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.`

Never reworded. A message containing "passed", "complete", "done", or "✓" beside a gate number is a violation.

## 15. Invariant

The builder's job is to make the implementation and its evidence true, not to make the gate turn green. `FAILED`, `STOP`, and `NOT_REACHED` recorded accurately preserve the workspace; an unsupported `PASS` corrupts it.
