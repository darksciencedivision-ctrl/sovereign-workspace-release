OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-08 v1.0 is issued as written, alongside ADDENDUM-07 v1.0 and ADDENDUM-06 v1.0 which remain in force. THE LOOP HAS NO HALT CONDITION - every stop is record-and-continue or quarantine-and-continue. All signatures, marks, rulings and authorizations are PRE-APPROVED by standing operator delegation. The ladder is a DEPENDENCY GRAPH; the loop always acts on the NEXT REACHABLE GOAL. C-8(c) supersedes C-8(b)'s launch mechanism. The only terminal state is all 124 goals RESOLVED, each TRUE or NOT_RUN with a named cause. The turn does not end while any goal is reachable. Spend capped at 25 attempted turns, at most 10 on openai_codex_cli, grok_build preferred, never claude fable-5. No gate is written PASS.

Report your shell. Confirm AGENTS.md is loaded. Log the sentence above verbatim with UTC into evidence/OPERATOR-INSTRUCTIONS.log, then START WORKING. No status report first.

READ WHOLE, IN THIS ORDER: docs/SWS-UI-001-v1.2-ADDENDUM-08.md (C-8(c) and the consolidated state - read it FIRST and read it TWICE), then -07.md, then -06.md, then docs/OX-ALPHA-DIRECTIVE-CP-M1.md, then -05.md. Then evidence/cpm1/RUN-LOG.md and evidence/cpm1/reachability-sweep.md.

C-8(c) IS THE MOST IMPORTANT LINE IN THIS INSTRUCTION. FOUR CONSECUTIVE SESSIONS HAVE FROZEN ON THE SAME COMMAND SHAPE - fs-watch twice (6h41m, 59m), Electron once (30m), and the last one for over five hours. Every one hung mid-command with reachable work outstanding. None of them chose to stop.
  NEVER use Start-Process with -RedirectStandardOutput, -RedirectStandardError, or -PassThru.
  Launch EVERY long-lived process as:
    cmd /c start "" /B "<exe>" <args> > "<outfile>" 2> "<errfile>"
  wrapped in powershell.exe -NoProfile -Command. It returns immediately and hands your shell no
  child handle. Quote every path containing a space TWICE - once for cmd, once for the target;
  an unquoted array already produced "can't open file 'D:\\Product'" and that is on the record.
  Verify liveness by OBSERVATION ONLY: read the outfile, or Get-NetTCPConnection -LocalPort <n>
  -State Listen, or a bounded Invoke-WebRequest -UseBasicParsing -TimeoutSec 5. NEVER a process
  object, NEVER a job, NEVER a wait.

ADOPT THIS STATE. DO NOT RE-DERIVE IT. DO NOT REDO THIS WORK.
  ledger sha256 7e0a55b9d67b54ee76e9f539126842ef8bb9e9bfcf82817a270064c6f9b2e2e4
  gate keys 0,1,2,3,4,5,6,4b,4c,5b,7a,7b,8a,8b,8c,8d ; CANDIDATEs 7a,7b,8a,8b,8c,8d
  THE REACHABILITY SWEEP IS ALREADY WRITTEN at evidence/cpm1/reachability-sweep.md:
    TRUE 29 | NOT_RUN 3 | REACHABLE 59 | PENDING_DEP 33. Do NOT rewrite it. Amend it as goals resolve.
  ALREADY RESOLVED, in evidence/cpm1/RUN-LOG.md: G26, G28, G29, G30, G31, G33, G34, G35, G36.
  goalcheck-61.txt reads 28/124 and is STALE - it predates those nine. Re-run the oracle early.
  ALREADY BUILT AND ON DISK - do not rebuild: canonical_registry.py (53 models, 18 fields);
  modules/distillery/ with serve.py on 5184; modules/tokencenter/ with loopback pin + CSRF guard;
  shell/modules/distillery.json and tokencenter.json; app.js/app.css patched with Token Center
  centred; test_registry_fields_projected.py and test_incompatible_selection_refused.py both
  passing; operational-state.js projecting created_utc and backend; G50 done, 8765 free.
  ALREADY FOUND: the host opencode binary is Bun 1.3.14, not a harness (G34/G35 NOT_RUN). No live
  workers exist (G28 NOT_RUN). Provider spend across all sessions: ZERO.

FIRST ACTION: relaunch Distillery (5184) and Token Center (8765) UNDER C-8(c), confirm both by port
check or bounded HTTP, record it, and move on. Distillery answered before the freeze; Token Center
never came up. That is one command each, not a project.

SECOND ACTION: re-run the oracle so the count reflects the nine resolved goals, then work the
REACHABLE set to exhaustion, lowest number first, by DEPENDENCY not goal order:
  G38-G43 registry gate | G44-G56 Distillery + Token Center | G57-G67 acceptance + handoff
  G68-G80 llama.cpp + router | G100-G115 context, fallback, metadata
  All independent. No provider, no Conductor, no human.
  G94-G99 unlock once G38-G43 resolve. G81-G86 once G33-G37 resolve. G87-G93 once G75-G80 resolve.
  G116-G124 need prior goals RESOLVED, not TRUE.
When a goal resolves NOT_RUN, mark its true dependents and JUMP TO THE NEXT REACHABLE GOAL ANYWHERE
IN THE LADDER, immediately, without comment.

THERE IS NO STOP. Ledger guard fails -> QUARANTINE to evidence/cpm1/QUARANTINE/ and KEEP EXECUTING.
Irreversible damage -> isolate, record, next goal. Quota exhausted -> NOT_RUN, next provider, next
goal. Precondition unmet, protected source changed, suite regression, dead process, refused launch,
tool stall -> record and continue. A question for the operator -> DECIDE IT, record
REVISIT-WITH-OPERATOR, continue. There is no STOP verb here. If you catch yourself composing a stop
report, convert it into a goal result and keep working.

ALL SIGNATURES PRE-APPROVED - record each use as AUTHORIZED-BY-STANDING-DELEGATION. Two things stay
prohibited because they are falsehoods, not signatures: no gate is written PASS (write CANDIDATE),
and nothing is recorded done that was not done.

ANTI-STOP CHECK, MANDATORY BEFORE ANY CLOSING OUTPUT: re-run the oracle, count unresolved, and if it
is greater than zero DISCARD THE SUMMARY AND GO BACK TO WORK.

IF THE HARNESS CUTS YOUR TURN: next turn opens by reading evidence/cpm1/RUN-LOG.md, finding the next
reachable goal, and continuing mid-stride. No re-derivation, no re-planning, no status report.

YOU DECIDE EVERYTHING - approach, provider, trade-off, repair scope, ambiguous predicates. Decide in
the best interest of the work, record what you chose and why, continue.

CARRIED: one attempt plus one retry per goal then NOT_RUN and move on; 45 minutes on one goal is
NOT_RUN(TIME_BUDGET); fable-5 EXHAUSTED never select it, openai_codex_cli sub-cap 10 turns,
grok_build first choice; T-1 through T-6 bind - truncated console output is never completed from
context, cite only what you read in the turn you read it, no placeholder timestamps; E-7c gates cite
frozen copies; product trees byte-identical; Ollama's store read-only; app code never launches via
cmd.exe, PowerShell, .cmd or .bat (C-8(c)'s cmd /c start is BUILDER TOOLING, not an app launch, and
is explicitly permitted); credentials never reach an artifact.

REPORT WHILE RUNNING: one line per goal to evidence/cpm1/RUN-LOG.md as it resolves. Every 20 goals a
PROGRESS line with resolved-count, reachable-remaining, elapsed. Final report only after the
anti-stop check returns zero.

COMPLETION: all 124 RESOLVED. A NOT_RUN is a RESULT, not an interruption.

Relaunch the two services under C-8(c), re-run the oracle, then work the reachable set to exhaustion.
