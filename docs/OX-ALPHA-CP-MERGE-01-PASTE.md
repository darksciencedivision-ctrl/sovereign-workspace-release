OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-03 v1.0 is issued as written; CP-01 and CP-02 are merged into one loop under docs/OX-ALPHA-DIRECTIVE-CP-MERGE-01.md; amendments A-1 through A-4 bind; gates 8a-8j and 9a-9j are authorized; the CP-01 Band 0 evidence is adopted; stage pauses waived; no provider spend authorized; llama.cpp is not promoted to production default.

Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet via powershell.exe -NoProfile -Command "<cmdlet>" — builder tooling, not a module launch. Record the shell name in evidence/cpm1/session-start.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Log the authorization sentence above verbatim, with the UTC you received it, into evidence/OPERATOR-INSTRUCTIONS.log before any other mutation.

Then read from disk, in this order, and do not proceed from memory of any prior session:

  1. BUILD-DIRECTIVE-SWS-UI-001.md
  2. docs/SWS-UI-001-v1.2-ADDENDUM-03.md   <- the merge: amendments A-1..A-4, ordering, combined caps
  3. docs/OX-ALPHA-DIRECTIVE-CP-MERGE-01.md <- the work order: Band 0M, band sequence, handoff, loop, exit
  4. docs/SWS-UI-001-v1.2-ADDENDUM-01.md   <- CP-01 envelope (as amended by A-2)
  5. docs/OX-ALPHA-DIRECTIVE-CP-01.md      <- CP-01 goal definitions G0..G36, verbatim
  6. docs/SWS-UI-001-v1.2-ADDENDUM-02.md   <- CP-02 envelope (its section 5 superseded by A-4)
  7. docs/OX-ALPHA-DIRECTIVE-CP-02.md      <- CP-02 goal definitions G0.1..G54, verbatim
  8. docs/CP-02-MODERNIZATION-ASSESSMENT.md <- what already exists and must not be rebuilt
  9. docs/CP-02-REVIEW-01.md and docs/CP-02-CONFLICT-AUDIT.md
 10. docs/CP-01-WATCH-01.md                <- why A-1, A-2 and A-3 exist
 11. docs/THEME-BASELINE-v3.md
 12. evidence/GATE-LEDGER.json and evidence/OPERATOR-INSTRUCTIONS.log

A PRIOR CP-01 SESSION RAN AND WAS SUPERSEDED. It completed Band 0 and made no product mutation. Its evidence under evidence/cp01/ is ADOPTED, not regenerated — see ADDENDUM-03 section 2 and this work order's Band 0M. Do not re-hash the five protected roots; sov-1 alone is 134,462 files / 7.4 GB and already hashed clean at 07:21Z. Verify what is there, apply amendment A-1, and move on. Its goalcheck.py at evidence/cp01/tools/goalcheck.py is a working 53-goal oracle — extend it in place for CP-02's goals rather than rewriting it, and send its output to evidence/cpm1/.

ORDER IS THE WHOLE SAFETY ARGUMENT. Every CP-01 goal is TRUE before any CP-02 goal is acted on. CP-02 Band E extends the registry CP-01 Gate 8g creates; CP-02 Band C widens a Protocol CP-01 Gate 8f leaves in its narrow shape. Acting on a CP-02 goal while a CP-01 goal is FALSE is BAND_ORDER_VIOLATED — a STOP. Both packages number goals from G1: prefix every reference CP01:Gn or CP02:Gn.

Six things are already settled. Do not re-derive them:

  - Debate Table does not autostart. Nothing in the shell starts any module. CP-01 R-01 is a proof obligation and a legibility fix, not a repair.
  - The Token Center holds no credentials. It is a read-only usage-telemetry reader. Do not build a credential store; requirement 14 is satisfied by that absence.
  - Roughly 80% of CP-02's architecture already exists — vendor-blind resolver, capability vocabulary, six-state residency planner, Backend Protocol, context as a hard filter, governed OpenCode spawn path, MCP worker-control surface. Widen and connect; never replace.
  - The residency planner is the SOLE eviction authority. Run llama.cpp's router --no-models-autoload with --models-max above the planner's bound. Band B's --models-max 1 is a validation setting and must not survive into Band D.
  - Ollama and llama.cpp draw on the same 8151 MiB and neither knows the other exists. Choose and record ONE VRAM budget authority before Band D schedules any load.
  - Your changed-line budgets do not pool. CP-01 measures against evidence/cp01/before/; CP-02 measures against a SECOND baseline captured at the handoff. A line CP-01 changed is CP-02's baseline, not CP-02's spend.

Begin at M0.1 and run the goal loop without pausing at band boundaries until every goal is TRUE or a STOP condition fires. Do not end your turn at a step boundary — end it only with the section 9 final message or a STOP report. If the harness ends your turn anyway, resume from the first failing goal without re-deriving the plan.

Nothing here amends AGENTS.md. Builder only: no PASS, no operator signature, no protected-source writes, no provider spend, no fabricated availability, no production promotion.
