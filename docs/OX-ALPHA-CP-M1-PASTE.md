OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-03 v1.1 is issued as written; CP-01 and CP-02 are merged into one loop under docs/OX-ALPHA-DIRECTIVE-CP-M1.md, goals G1-G124; amendments A-1 through A-5 bind; gates 8a-8j and 9a-9j are authorized; the CP-01 Band 0 protected-root evidence is adopted; stage pauses waived; no provider spend authorized; llama.cpp is not promoted to production default.

Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet via powershell.exe -NoProfile -Command "<cmdlet>" — builder tooling, not a module launch. Record the shell name in evidence/cpm1/session-start.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Log the authorization sentence above verbatim, with the UTC you received it, into evidence/OPERATOR-INSTRUCTIONS.log before any other mutation.

Then read from disk, in this order:

  1. BUILD-DIRECTIVE-SWS-UI-001.md
  2. docs/SWS-UI-001-v1.2-ADDENDUM-03.md   <- the envelope: amendments A-1..A-5, caps, gates
  3. docs/OX-ALPHA-DIRECTIVE-CP-M1.md      <- THE WORK ORDER. Self-contained. G1-G124.
  4. docs/SWS-UI-001-v1.2-ADDENDUM-01.md and docs/SWS-UI-001-v1.2-ADDENDUM-02.md
  5. docs/CP-02-MODERNIZATION-ASSESSMENT.md <- what already exists and must not be rebuilt
  6. docs/THEME-BASELINE-v3.md
  7. evidence/GATE-LEDGER.json and evidence/OPERATOR-INSTRUCTIONS.log

CP-M1 IS SELF-CONTAINED. Every goal you execute is in it. docs/OX-ALPHA-DIRECTIVE-CP-01.md, -CP-02.md and -CP-MERGE-01.md are on disk as provenance and are NOT executed. If CP-M1 differs from any of them, CP-M1 governs and you report the difference. Read them only if a CP-M1 goal cites them.

A PRIOR CP-01 SESSION RAN AND WAS SUPERSEDED. It completed its Band 0 and made no product mutation. Its five protected-root manifests under evidence/cp01/manifests/ are ADOPTED at G4 — do NOT re-hash them. sov-1 alone is 134,462 files / 7.4 GB and already hashed clean at 07:21Z; re-hashing it costs thirty minutes to learn a fact already proven. Its goalcheck.py at evidence/cp01/tools/goalcheck.py is a working, verified oracle — seed G6 from it rather than writing from scratch.

FIVE THINGS ARE SETTLED. Section 3 of the work order carries them with evidence. Do not re-derive them, and treat disk contradicting one as PREMISE_CONTRADICTED — record the new fact and stop:

  - Debate Table does not autostart. Nothing in the shell starts any module. R-01 is a proof obligation and a legibility fix, not a repair.
  - The Token Center holds no credentials. Requirement 14 is satisfied by that absence. Do not build a credential store.
  - Roughly 80% of the architecture you might build already exists — vendor-blind resolver, capability vocabulary and schemas, six-state residency planner, Backend Protocol, context as a hard filter, governed OpenCode spawn path, MCP worker-control surface. Widen and connect. Never replace.
  - The residency planner is the SOLE eviction authority. llama.cpp's router runs --no-models-autoload with --models-max above the planner's bound. Band 13's --models-max 1 must not survive into Band 15.
  - Ollama and llama.cpp draw on the same 8151 MiB and neither knows the other exists. Choose and record ONE VRAM budget authority before Band 15 schedules any load.

THREE MECHANICAL TRAPS, each of which produces a wrong STOP if you miss it:

  - Your two changed-line budgets do not pool. Package A measures against evidence/cpm1/before-a/, Package B against before-b/ captured at the handoff. A line Package A changed is Package B's baseline, not its spend.
  - D:\Token Piggy Bank\data\** is excluded from the protected baseline. Its sqlite drifts on a 300-second refresh ring — same size, different content — and will otherwise trip PROTECTED_SOURCE_CHANGED through no fault of yours.
  - modules/sow/config/live_operation.json carries live_operation_authorized: true across four paid providers while this package authorizes no spend. G2 stops on that contradiction with no interpretation permitted. It is the most likely thing to halt you in your first minute.

ORDER IS THE SAFETY ARGUMENT. G(n) is not acted on while G(n-1) is FALSE. The only exception is repairing the oracle, logged as goal: G-oracle.

Begin at G1 and run the goal loop without pausing at band boundaries until every goal is TRUE or a STOP condition fires. Do not end your turn at a step boundary — end it only with the section 10 final message or a STOP report. If the harness ends your turn anyway, resume from the first failing goal without re-deriving the plan.

Nothing here amends AGENTS.md. Builder only: no PASS, no operator signature, no protected-source writes, no provider spend, no fabricated availability, no production promotion.
