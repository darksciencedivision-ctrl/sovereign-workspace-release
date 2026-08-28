OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-04 v1.0 is issued as written; CP-M1 resumes in a fresh session under docs/OX-ALPHA-DIRECTIVE-CP-M1.md, goals G1-G124; amendments A-1 through A-8, C-1, C-4, D-3, E-1, E-2, E-7a/b/c, E-8 and standing rules T-1 through T-5 bind; the launchConductorSession boundary-population option is permanently withdrawn; the prior session's evidence is adopted; provider spend is limited to openai_codex_cli for the G25/G26 Conductor leg and the G58 API-model leg; llama.cpp is not promoted to production default.

Before step 1, report which shell your bash tool runs (PowerShell, Git Bash, WSL, cmd). If it is not PowerShell, run every PowerShell cmdlet via powershell.exe -NoProfile -Command "<cmdlet>" - builder tooling, not a module launch. Record the shell name in evidence/cpm1/session-start-2.txt.

Confirm AGENTS.md from this project root is loaded in your context before any tool call; if it is not, say so and stop.

Log the authorization sentence above verbatim, with the UTC you received it, into evidence/OPERATOR-INSTRUCTIONS.log before any other mutation.

Then read from disk, in this order:

  1. BUILD-DIRECTIVE-SWS-UI-001.md
  2. docs/SWS-UI-001-v1.2-ADDENDUM-04.md   <- READ THIS SECOND AND READ IT WHOLE. Entry state, the full amendment register, the withdrawn option, and standing rules T-1..T-5.
  3. docs/OX-ALPHA-DIRECTIVE-CP-M1.md      <- THE WORK ORDER. G1-G124. ADD-04 amends it; it does not replace it.
  4. docs/SWS-UI-001-v1.2-ADDENDUM-01.md, -02.md, -03.md
  5. docs/CP-M1-VERIFY-01.md and docs/CP-M1-VERIFY-02.md   <- the reviewer's findings on the prior session. VERIFY-02 is why T-1..T-3 exist.
  6. docs/CP-02-MODERNIZATION-ASSESSMENT.md <- what already exists and must not be rebuilt
  7. evidence/GATE-LEDGER.json and evidence/OPERATOR-INSTRUCTIONS.log

A PRIOR CP-M1 SESSION RAN AND CLOSED. Its evidence under evidence/cpm1/ is ADOPTED, not regenerated. Bands 0-3 are closed; G25 is TRUE; 26 of 124 goals TRUE; 371 of 1850 Package-A changed lines used; Package B has not started and has no baseline. Gates 8a, 8b and 8c stand CANDIDATE. Verify that state from disk in Band 0; do not re-derive it.

YOUR FIRST TWO ACTIONS, IN THIS ORDER, BEFORE THE LADDER:

FIRST - close the decay. Apply E-7c BACKWARDS to gates 8a, 8b and 8c. Each of them cites at least one still-editable file by hash - modules/sow/apps/desktop/main.js, evidence/cpm1/tools/goalcheck.py, evidence/cpm1/before-a/HASHES.txt - and each goes stale the next time that file is touched. G24 has gone FALSE three times for this one reason. Freeze a copy of every mutable file those three gates cite under evidence/cpm1/<gate>/frozen/<name>, cite the frozen copy's hash, and move the live path into a source_path field carrying no hash. One pass. Bookkeeping, not product code. Gates 0-7b stay byte-identical and the preamble guard passes before and after.

SECOND - settle G3 per T-4. Its freshness window is PER SESSION, not per calendar day. It expired at UTC midnight and will expire every midnight until this package closes. Amend the goal note to say so, capture once for this session, and stop re-capturing.

THEN THE LADDER. The first failing goal after those two is G26.

G26 IS BLOCKED AND YOU MAY NOT UNBLOCK IT BY GUESSING. The prior session STOPPED there correctly and then diagnosed it wrongly - it named voice/conductor-write.js as the root cause in a STOP report WITHOUT EVER OPENING THAT FILE, and it quoted an error message it had only seen truncated, inventing the four words that produced the wrong cause and three wrong options. Before you propose anything, write evidence/cpm1/8d/g26-rediagnosis.txt answering all four from source, each with file:line citations and quoted code:

  Q1. Why does supervisorEnforcedBoundary (voice/conductor-write.js:57) demand voice_turn_boundary@1.0 rather than the conductor flag boundary? What is the voice-turn authority protecting against, and is that threat present for TYPED operator text?
  Q2. Trace main.js:932-968 for a codex conductor. CONFIRMED or REFUTED: the else-branch at :968 means no codex conductor can ever satisfy supervisorEnforcedBoundary as the code stands. Name the lines that decide it.
  Q3. Enumerate EVERY path that writes bytes to a conductor pty, and name the guard each one passes. Is deliverConductorChat the only one, or does a governed path for typed operator text exist that is distinct from the voice writer?
  Q4. Is the voice_turn_boundary hook chain provider-specific - built for claude_code's hook surface (hook_command, PreToolUse/PermissionRequest matchers)? Does codex have any equivalent surface in this codebase? If it does not, say so plainly.

Then propose a revised option set with real scope and STOP for the operator. Do not implement your own proposal in that turn. If Q2 is CONFIRMED and Q3 finds no typed path, recommend accordingly - including deferral or new scope. "R-04 is not provable on this provider without X" is a better outcome than a clever route around a guard.

THE OPTION THAT IS PERMANENTLY WITHDRAWN: populating authorityBoundary fields inside launchConductorSession(). It would write enforced_by_supervisor_process: true on the branch that starts no supervisor - a false attestation inside a security control that then reports "enforced" forever. Do not propose it in any form, including test-only or temporary.

THREE STANDING RULES THIS RUN EARNED. They are in ADD-04 §4; they are repeated here because breaking them is what cost the prior session its last four turns:

  T-1  TRUNCATED CONSOLE OUTPUT IS NOT EVIDENCE. A value that reaches the console truncated is never completed from context. Re-read it from the source file, or capture it to a file and read the file. This has now failed twice - a 63-character hash in a reviewer-evaluated ledger entry, and a fabricated error quotation in a STOP report.
  T-2  CITE ONLY WHAT YOU READ, IN THE TURN YOU READ IT. A file named as a root cause must have been opened in that turn, and the report must quote the deciding line with its file:line.
  T-3  NO PRICED OPTIONS FOR AN UNFINISHED DIAGNOSIS. Stopping the investigation is legitimate - stopping for turn length is legitimate - but then the report says "cause not established; here is what was ruled out and what remains unread." It does not publish remedies with line-count estimates.

Also retired: resync_8b.py and the resync pattern (T-5). That tool family corrupted gates 4 and 5. With E-7c in force nothing needs resyncing. Do not run it and do not write a replacement.

E-8, STANDING: any goal going TRUE -> FALSE is named with its cause, in the CURRENT report, on the same line as the count.

SPEND. ZERO has been spent so far and three launch attempts have already been made. Authorized: openai_codex_cli ONLY, for the G25/G26 Conductor leg and the G58 API-model leg. Nothing else. Other providers record NOT_RUN(NO_SPEND_AUTHORIZATION) naming the registry entries examined. terminals_per_subscription stays 1. No worker on a frontier provider. Append every turn to evidence/cpm1/8d/spend-log.txt AS IT HAPPENS - timestamp, provider, model, running count - never batched; the counter increments on ATTEMPT, not on delivery. If a round-trip is not proven inside roughly a dozen turns, stop and report: that is a design problem in the surface, not a budget problem. Anything outside the envelope is STOP SPEND_REQUIRED with no interpretation permitted.

A-6 BINDS. G26's "runs on a local model" predicate is unsatisfiable - CONDUCTOR_MODEL_REGISTRY holds only frontier entries. The Conductor leg runs on whichever conductor-capable model the spend authorization permits, recorded by name and provider in the artifact. The work order file stays unamended so the amendment remains traceable.

A-7, FRESH SESSION. The operator closes the prior fs-watch window and opens a new one. You record the gap in the A-7 table and you START NOTHING (C-4 - the operator owns the helper; Start-Process with redirected handles stalled the prior session twice).

ORDER IS THE SAFETY ARGUMENT. G(n) is not acted on while G(n-1) is FALSE. The only exception is repairing the oracle, logged as goal: G-oracle. Every Package-A goal is TRUE before any Package-B goal is acted on.

Run the goal loop without pausing at band boundaries until every goal is TRUE or a STOP fires. Do not end your turn at a step boundary - end it only with the section 10 final message, the A-8 pause line, or a STOP report. If the harness ends your turn anyway, resume from the first failing goal without re-deriving the plan.

Nothing here amends AGENTS.md. Builder only: no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always - never pull, rm, move, rename or write. llama.cpp is not promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or shell=True.
