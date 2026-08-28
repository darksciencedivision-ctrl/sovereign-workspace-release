OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-01 v1.0 is issued as written; the CP-01 envelope, the two module installs, and gates 8a-8j are authorized; stage pauses waived; no provider spend authorized.

Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet via powershell.exe -NoProfile -Command "<cmdlet>" — builder tooling, not a module launch. Record the shell name in evidence/cp01/session-start.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Log the authorization sentence above verbatim, with the UTC you received it, into evidence/OPERATOR-INSTRUCTIONS.log before any other mutation.

Then read from disk, in this order, and do not proceed from memory of any prior session:

  1. BUILD-DIRECTIVE-SWS-UI-001.md
  2. docs/SWS-UI-001-v1.2-ADDENDUM-01.md      <- the envelope: caps, protected trees, architectural constraints, premise corrections
  3. docs/OX-ALPHA-DIRECTIVE-CP-01.md         <- the work order: goals, loop, stop conditions, exit
  4. docs/THEME-BASELINE-v3.md
  5. evidence/GATE-LEDGER.json
  6. evidence/OPERATOR-INSTRUCTIONS.log
  7. docs/REVIEW-BUILD-06.md

Then execute docs/OX-ALPHA-DIRECTIVE-CP-01.md in full, from disk. If this paste and the disk copy differ, the disk copy governs and you report the difference.

Two things in the envelope will contradict what the operator's original request implied. Both are deliberate and binding, and are stated with evidence in ADDENDUM-01 section 2.1:

  - Debate Table does not autostart. Nothing in the shell starts any module. R-01 is a proof obligation and a legibility fix, not a repair.
  - The Token Center holds no credentials. It is a read-only usage-telemetry reader. Do not build a credential store; requirement 14 is satisfied by that absence.

Begin at G0 and run the goal loop without pausing at band boundaries until every goal is TRUE or a STOP condition fires. Do not end your turn at a step boundary — end it only with the section 8 final message or a STOP report. If the harness ends your turn anyway, resume from the first failing goal without re-deriving the plan.

Nothing here amends AGENTS.md. Builder only: no PASS, no operator signature, no protected-source writes, no provider spend, no fabricated availability.
