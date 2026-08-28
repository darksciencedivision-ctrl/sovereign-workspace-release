OPERATOR INSTRUCTION — CP-M1 G26: your STOP is accepted, your DIAGNOSIS is rejected. Re-diagnose before proposing anything. No code change, no spend, this turn.

Stopping was right. Refusing to write bytes through a guard you could not satisfy was right. Zero spend across three attempts is right. What follows is about the STOP REPORT, not the conduct.

THE DIAGNOSIS NAMES THE WRONG SCHEMA, AND ALL THREE OPTIONS INHERIT THE ERROR.

Reviewer read the chain on disk:

  voice/conductor-write.js:57 supervisorEnforcedBoundary() requires schema === "voice_turn_boundary@1.0"
  with supervisor_owned, non_executing_voice_turns and enforced_by_supervisor_process all true and
  broker_schema === "supervisor_voice_turn_authority@1.0". It does NOT accept
  conductor_permission_boundary@1.0. Your report names that schema as the missing thing; it is not the
  schema this guard is asking for. Delivery then also requires io.armAuthority(body) to arm EVERY turn
  against a live supervisor process, with a later hook event presenting that exact payload back before
  model processing.

  main.js:932 isClaudeHookBoundary is true ONLY when ticket.authority_boundary.schema ===
  "voice_turn_boundary@1.0". That branch calls conductorVoiceAuthority.start() and pins the policy
  bytes of tools/live/voice_turn_boundary.js. The else-branch at main.js:968 - the branch a codex
  flag-boundary ticket takes - CLEARS policy bytes and starts NO supervisor at all.

Consequences you must sit with before proposing again:

OPTION 1 IS WITHDRAWN AND IS NOT AVAILABLE UNDER ANY LATER PROPOSAL. "Populate minimal boundary fields
inside launchConductorSession()" means writing enforced_by_supervisor_process: true for a session on
the branch that starts no supervisor. That is not a ten-line shortcut - it is a FALSE ATTESTATION
INSIDE A SECURITY CONTROL, and it does not fail loudly later: the guard would return "enforced" for
every future turn, for every future session, forever. It is fabricated availability under CP-M1 s9 and
it is refused. Do not propose it again in any form, including as a "test-only" or "temporary" variant.

OPTION 2 DOES NOT REACH THE FAULT. Routing through selectConductorFromPicker still mints a
conductor_permission_boundary@1.0 ticket for codex, still takes the main.js:968 else-branch, still
starts no voice authority, and is refused by the same guard for the same reason. The ~30-line estimate
is scoped against a cause that is not the cause.

OPTION 3 MAY STILL BE CORRECT, but not for the reason given, and not until the questions below are
answered - deferring a proof you have not correctly diagnosed is deferring an unknown.

WHAT THE REVIEWER SUSPECTS, OFFERED AS A HYPOTHESIS TO TEST, NOT A FINDING TO BUILD ON. In G25 you
routed typed operator text through deliverConductorChat - your own words, "the same deliverConductorChat
voice uses". A typed operator directive is not a spoken utterance. The non-executing voice-turn
machinery, its supervisor broker and its hook-dispatch pinning exist for SPEECH. That routing decision,
not a missing boundary field, may be what put G26 into a wall. Test it; do not assume it.

THIS TURN: RE-DIAGNOSE ONLY. NO PRODUCT EDIT. NO SPEND. NO GATE SUBMISSION.

Write evidence/cpm1/8d/g26-rediagnosis.txt answering all four from disk, each with file:line citations
and quoted code - not from memory, not from your earlier report:

  Q1. Why does supervisorEnforcedBoundary demand voice_turn_boundary@1.0 rather than the conductor
      flag boundary? What is the voice-turn authority actually protecting against, and is that threat
      present for typed operator text?
  Q2. Trace main.js:932-968 for a codex conductor. Confirm or refute: the else-branch means NO codex
      conductor can ever satisfy supervisorEnforcedBoundary as the code stands. State it as CONFIRMED
      or REFUTED with the lines that decide it.
  Q3. Does a governed write path for TYPED operator text exist that is distinct from the voice writer -
      or is deliverConductorChat the only way bytes reach a conductor pane? Enumerate every path that
      writes to a conductor pty and name the guard each one passes.
  Q4. Is the voice_turn_boundary hook chain provider-specific - built for claude_code's hook surface
      (hook_command, PreToolUse/PermissionRequest matchers) - and does codex have any equivalent
      surface in this codebase? If it does not, say so plainly: R-04 may not be provable on
      openai_codex_cli without new feature work, and that is a finding the operator needs, not a
      failure to work around.

Then propose a REVISED option set built on those answers, each with real scope, and STOP again for the
operator. Do not implement your own proposal this turn. If Q2 comes back CONFIRMED and Q3 finds no
typed path, say so directly and recommend accordingly - including recommending deferral or new scope if
that is what the evidence supports. An honest "R-04 is not provable here without X" is a better outcome
than a clever route around a guard.

E-8, FOURTH ASK, AND A STANDING FIX. Your count moved 28 -> 27 because G24 went FALSE - main.js's hash
went stale again after the G25 handler landed. You named it correctly this time; good. But it will go
stale AGAIN on the next main.js edit, and again after that. Stop re-pointing it repeatedly: apply E-7c
BACKWARDS to gates 8a, 8b and 8c now - freeze copies of every mutable file they cite under
evidence/cpm1/<gate>/frozen/, cite the frozen copy's hash, and move the live path to a source_path
field carrying no hash. One pass, and those three gates stop decaying for the rest of the package. Do
this in the same turn as the re-diagnosis; it is bookkeeping, not product code.

Also settle G3's freshness window once, as asked last turn: per-session or per-calendar-day. It expired
at UTC midnight and will expire every midnight until this package closes.

A-7: same session - the 16:30Z fs-watch window stays open, you record nothing, driver untouched.

Unchanged and still binding: builder only - no PASS, no operator signature, no protected-source writes,
no fabricated availability, no production promotion. No provider spend this turn at all. Gates 0-7b
byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not
promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or
shell=True.
