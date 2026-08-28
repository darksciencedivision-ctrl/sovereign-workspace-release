OPERATOR DECISION — CP-M1 G26: Option 1 authorized. Fix the verifier, pin it with a round-trip test, then one retry.

Your diagnosis is verified in full and it is the best work of this run. Reviewer read all four sites from source: launch-source.js:102 renders `/\s/.test(arg) ? "\"" + arg + "\"" : arg` - DOUBLE quotes; conductor_permission_profile.py:114 renders " ".join(_powershell_single_quote(a) for a in argv) - SINGLE quotes with ' doubled; launch-source.js:300-312 confirms "malformed payload" = exit 0 + valid JSON + failed wellFormed(); and g26-hook-command-renderproof.txt shows commands_equal false on real host paths. The stale comment at launch-source.js:92-93 still describes subprocess.list2cmdline - the PRE-W-38 producer. W-38 moved the producer and left the verifier and its comment behind. You measured it instead of arguing it. That is the standard.

Your recommendation against reverting W-38 is upheld and the option is CLOSED. W-38's own docstring carries measured proof that list2cmdline output handed to powershell.exe -Command executed an injected subexpression - 'a$(Write-Host INJECTED)b' ran as code. Reverting trades a live injection vector for a quoting convenience. Do not revisit it.

AUTHORIZED: fix the VERIFIER, which is the side that is wrong, and pin the two renderers together. This is REPAIR OF A DEFECT, NOT NEW SCOPE - the verifier currently rejects its own producer's valid output, and no claude_code conductor can launch on this host as a result. Record it that way in the design-change note.

FOUR THINGS, ALL OF THEM, IN ONE PASS:

1. MIRROR _powershell_single_quote EXACTLY - BOTH LAYERS. Read conductor_permission_profile.py:71-84 before writing a line of JS. That function is NOT "wrap in single quotes". It walks the string, escapes a literal " as \" while DOUBLING any run of backslashes immediately preceding that quote (for CommandLineToArgvW), and only then wraps the result in single quotes with every ' doubled. A naive JS mirror that wraps in single quotes agrees on today's paths and diverges again the first time a path contains a quote or a backslash run. Port the algorithm, not the appearance.

2. FIX THE APOSTROPHE GAP THE REVIEWER FOUND. launch-source.js:94 refuses any argv element containing a double quote. Nothing anywhere handles a SINGLE quote - and ' is legal in a Windows path (C:\Users\O'Brien\...). Under single-quote rendering the apostrophe is the character that matters. Either handle it exactly as the producer does (doubling), or refuse it explicitly and say why. Do not leave it unaddressed; it is the same drift one apostrophe away.

3. KEEP THE DERIVE-DON'T-TRUST PROPERTY. The verifier must still RE-DERIVE the expected command from b.hook_argv and compare, never accept the producer's hook_command field on trust. That property is why this defect surfaced as a refusal instead of a silent admission, and it is the security value of the check. Do not weaken it to make the comparison easier. Update the stale list2cmdline comment at :92-99 to describe what the producer actually does now, citing W-38.

4. PIN THE TWO RENDERERS WITH A ROUND-TRIP TEST. This is the part that matters most - it converts a defect fix into the permanent retirement of a defect CLASS. The test drives the REAL Python renderer and the REAL JS verifier over a shared corpus and asserts agreement on every element. The corpus must include, at minimum: a path with spaces; a path with an apostrophe; and elements containing $, a backtick, a semicolon, an opening parenthesis, a trailing backslash, and a run of two or more backslashes before a quote. If either side is edited again, the suite fails immediately instead of a launch failing months later.

CONSTRAINTS ON THE FIX. Do not touch the Python producer - it is correct and W-38's reasoning stands. Do not relax any other predicate in isWellFormedVoiceBoundary. Do not change the argv vector, the sandbox, the model pin, or the boundary schema. Changed lines land in the sow-desktop cap; report the delta against 371/1850. If mirroring the algorithm cannot be done without weakening a check, STOP and report rather than approximating it.

THEN ONE AUTHORIZED RETRY. Re-run the renderproof FIRST and show commands_equal true before launching anything - a launch is not the way to test a pure function. Then, against the ALREADY-RUNNING Electron tree and driver (do not relaunch; C-8 binds): GET /state, POST /launch-conductor - SPEND BEGINS HERE, append to spend-log.txt BEFORE sending any directive - GET /state to confirm launchState running, then the G26 round-trip.

If the launch is refused again, capture verbatim from a FILE (T-1), diagnose, and STOP. Do not attempt a third variation on your own judgment.

G26 UNDER A-6: a directive typed into the surface; the response returned into the transcript; a follow-up in the same thread demonstrably carrying prior context; an interrupt or redirect exercised or recorded UNSUPPORTED(<reason>). Model and provider named - claude_code / fable-5. A failed delivery surfaces as CONDUCTOR_COMMUNICATION_FAILED, never as silence. Roughly a dozen turns is the ceiling.

SPEND ENVELOPE unchanged: openai_codex_cli and claude_code, for the G25/G26 Conductor leg and the G58 API-model leg ONLY. grok_build and google_antigravity record NOT_RUN(NO_SPEND_AUTHORIZATION). terminals_per_subscription 1. NO WORKER ON A FRONTIER PROVIDER. Counter increments on ATTEMPT; append as it happens, never batched. Outside the envelope is STOP SPEND_REQUIRED.

THE FINDING IS A DELIVERABLE. Gate 8d's note records that this build could never have admitted a claude_code conductor on any host with a space in its paths, that codex never exercised the path because the flag-boundary validator has no hook_command check, and that the first claude_code ticket in the build's history is what surfaced it. That is worth more than the goal it unblocks.

THEN Gate 8d with E-7c frozen copies, then Band 5: G28, G29, G30, G31, G32. Run without pausing at band boundaries until every goal is TRUE or a STOP fires.

T-1 through T-5 and C-8 bind. The launchConductorSession boundary-population option and the W-38 revert are both permanently withdrawn. E-8 stands. A-7: same session, fs-watch window stays open, driver untouched. The four Electron pids are operator-owned and stay alive.

Builder only: no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not promoted to production default.
