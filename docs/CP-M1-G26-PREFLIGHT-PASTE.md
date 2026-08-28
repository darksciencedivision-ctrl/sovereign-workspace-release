OPERATOR INSTRUCTION — CP-M1 G26: two reconnaissance questions before the governance decision. No product edit, no spend, no gate submission this turn.

Your re-diagnosis is accepted. Reviewer re-read every citation from source: Q1 matches conductor-write.js:57-62 exactly; Q2's CONFIRMED matches an independent trace of main.js:932-968; Q4's citation is real and its comment is verbatim - "Do not fabricate Claude hooks for a provider that does not implement that hook protocol." That comment is the codebase refusing, by design, the option that was withdrawn. This is the standard T-2 asks for. E-7c backwards and the G3 per-session settlement are both confirmed on disk.

ONE CORRECTION, AND IT WEAKENS YOUR OWN CASE UNNECESSARILY. You wrote "codex.py: zero references to hooks, PreToolUse, UserPromptSubmit, or settings_json injection." There are TWO hook references in that file, and both SUPPORT your conclusion better than the negative claim did:

  codex.py:399 - "--dangerously-bypass-hook-trust" sits inside _FORBIDDEN_CODEX_ARGS: the adapter
                 structurally refuses to emit it.
  codex.py:352 - "Residual host-config.toml keys the flags do not override (e.g. declared MCP
                 servers/hooks) are a recorded live-run item (U32)."

Together those say something sharper than "no hooks exist": codex hooks come from HOST-GLOBAL config.toml, not from a per-launch settings injection, which is precisely WHY no supervisor process can pin them per session. That is the real architectural reason R-04 is not provable on codex today. Correct the line in g26-rediagnosis.txt and cite those two lines. Under T-2 a negative claim you did not verify is worth less than the positive evidence sitting next to it.

THE MATERIAL OMISSION IN YOUR OPTION SET. Option A is scored "zero product change" with no cost stated. Its real cost is not one goal:

  G29 requires "a task issued by the Conductor arriving at a named worker."
  G30 requires "the Conductor reporting it to the operator in the G25 transcript."

Both need a Conductor that can receive a human directive. If G26 is NOT_RUN, G29 and G30 may follow it, and Gate 8e becomes largely a record of absences - that is most of Band 5, R-05 and R-06, not just R-04. An option set that prices A at zero without naming that is not a complete option set. This is T-3's sibling: the cost of NOT acting is part of the scope too.

TWO QUESTIONS. ANSWER BOTH FROM DISK, THEN STOP. Write evidence/cpm1/8d/g26-preflight.txt.

  P1 - IS claude_code EVEN AVAILABLE ON THIS HOST? Nobody has checked - evidence/cpm1/baseline/
       runtime-inventory.json records only py/node/npm/git/powershell. Record verbatim: the result
       of the adapter's own detection path (detect.claude_code_executable), the resolved executable
       path or null, and `claude --version` stdout/stderr/exit if it resolves. Capture to a FILE and
       read the file back - T-1: nothing completed from a console fragment. If it does not resolve,
       say so plainly; Option C dies there and that is a useful, cheap answer.

  P2 - HOW MUCH OF BAND 5 ACTUALLY DEPENDS ON THE BLOCKED CHANNEL? Read G28-G32 in the work order
       against the code. For G29 and G30 specifically, determine whether the Conductor can issue a
       task and report a result through the EXISTING MCP worker-control surface / control-plane
       dispatch WITHOUT a human directive crossing deliverConductorChat - or whether the human ->
       Conductor channel is on the critical path for both. Cite the dispatch code by file:line.
       State each of G29, G30, G31 as BLOCKED or REACHABLE with the lines that decide it.

Then re-score your three options with P1 and P2 folded in, and STOP for the operator. Do not implement.

Do not run a claude_code session, do not launch a conductor, and do not spend anything this turn. P1 is a detection and a --version call, nothing more. The spend envelope is unchanged: openai_codex_cli only, for the G25/G26 Conductor leg and the G58 API-model leg. If P1 shows claude available, that is a FACT for the operator to act on, not an authorization to use it.

E-8 stands: name any TRUE -> FALSE goal with its cause on the same line as the count.

A-7: same session - the fs-watch window stays open, you record nothing, driver untouched. C-4 stands.

Unchanged and still binding: builder only - no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. T-1 through T-5 bind. The launchConductorSession boundary-population option remains permanently withdrawn. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or shell=True.
