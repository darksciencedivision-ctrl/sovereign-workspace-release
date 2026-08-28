OPERATOR INSTRUCTION — CP-M1. STOP-adjacent structural correction E-7 first, then E-8/E-9, THEN G26.

Reviewer verified on disk. Confirmed good: E-6 closed correctly (8a's goalcheck-5 citation was right and correctly left alone; 8b re-pointed to goalcheck-12; 8c to goalcheck-36). Gates 0-7b full-object identical to the verified snapshot, zero drifting fields, preamble guard clean. G25 TRUE and substantive - enabled input, submit, three timestamped turns, fails-before capture showing zero input elements. spend-log.txt correctly initialized with the envelope verbatim and turn count 0. NO SPEND HAS OCCURRED. Suites 1104 node / 144 python.

But your count went 26 -> 25 while G25 flipped TRUE, and the report did not say why. I asked for regression accounting last time and it was not done. Here is what the oracle actually shows and why it matters.

E-7 - THREE CANDIDATE GATES HAVE DECAYED, AND THE HABIT THAT FIXES IT IS THE HABIT THAT CORRUPTED GATES 4 AND 5.

Reviewer recomputed every evidence hash in 8a, 8b and 8c against live. Four rows have drifted:
  8a  evidence/cpm1/before-a/HASHES.txt        ledger 80d545599a  live 1cad88313d
  8a  evidence/cpm1/tools/goalcheck.py         ledger 4da3733f9e  live 77d9a1dc02
  8b  evidence/cpm1/8b/legacy-assertion-changes.txt  ledger 650c4f07a5  live 4989eeeb03
  8c  modules/sow/apps/desktop/main.js         ledger 0e70290062  live b2e4bd545f

That is why G19 and G24 went FALSE. Every one of those mutations was authorized work - C-7 extended the baseline, E-2/E-3 rewired the oracle, G25 edited main.js. The work is not the defect. THE GATE DESIGN IS: a CANDIDATE gate that cites a still-editable file by hash decays the moment a later band touches that file, and the only tool you have reached for so far is a scoped hash resync. An unscoped resync is exactly what corrupted gates 4 and 5. Do not resync your way out of this again. Fix it structurally, in three parts:

E-7a - ONE OF THESE FOUR IS NOT LEGITIMATE, AND IT IS RECOVERABLE. You appended a Band 4 addendum to a Band 2 gate's own evidence artifact - evidence/cpm1/8b/legacy-assertion-changes.txt line 32, "--- ADDENDUM (Band 4 / G25, utc 2026-08-25T23:5xZ): U175 allowlist design change ---". A submitted gate's artifact is frozen. Move that addendum into its own new file, cite it from the gate that actually owns the U175 change, and restore legacy-assertion-changes.txt by truncating the addendum until it hashes back to 650c4f07a5 exactly. Verify by hash, not by eye. If it does not return to that hash, the file was changed in some other way too - report that and stop rather than forcing it. Also note that addendum's timestamp is written "23:5xZ" with a literal x. Fix or drop it; a placeholder in an evidence artifact is not a timestamp.

E-7b - The other three are genuine, authorized mutations and cannot be restored, so re-point them HONESTLY, not silently. For each row add, alongside the corrected hash, an as_of_utc and a mutated_by field naming the goal or correction that changed the file (C-7 for HASHES.txt, E-2/E-3 for goalcheck.py, G25 for main.js). A reviewer reading the gate later must be able to see that the hash moved and why, without diffing snapshots. A bare hash swap is indistinguishable from a corruption and you now have direct experience of what that costs.

E-7c - STOP THE DECAY AT THE SOURCE, going forward. From gate 8d onward, when a gate cites a file that a later band may still edit, do not cite the live path by hash. Copy the file at submission time into evidence/cpm1/<gate>/frozen/<name>, cite the FROZEN copy's hash, and record the live path in a separate source_path field that carries no hash. Frozen artifacts never move, so gates never decay and no resync is ever needed again. This is a change to how you record evidence, not to what the goals require - it adds no scope and is inside your envelope. Apply it to 8d when you submit it.

E-8 - From now on, any goal that goes TRUE -> FALSE is named in your status report with its cause, in the same line as the count. A count that moves backwards silently is the exact shape of the defect this package exists to catch. This is the second time I have asked.

E-9 - You reported ledger sha a7c3f39b..1eae "at completion". Live is efa98fd048aadf9ee20ab15fbc44825dd1f7cc4d6f1db992c209ba81591ea425. Account for the writes between those two states in one line.

After E-7/E-8/E-9, re-run the oracle. G19 and G24 must read TRUE again before you touch G26 - if they do not, report and stop rather than proceeding into a spend with two closed gates broken behind you.

THEN G26 - THE FIRST AND ONLY LIVE SPEND SO FAR.

A-6 binds and replaces G26 as written in the work order; the local-model predicate is unsatisfiable and the file is deliberately unamended so the amendment stays traceable. The Conductor leg runs on openai_codex_cli/gpt-5.6-sol, recorded by name and provider in the artifact. Prove: a directive typed into the surface, the response returned into the transcript, a follow-up in the same thread demonstrably carrying prior context, and an interrupt or redirect exercised or recorded UNSUPPORTED(<reason>). A failed delivery surfaces as CONDUCTOR_COMMUNICATION_FAILED, never as silence.

Append every turn to spend-log.txt as it happens - timestamp, provider, model, running count - not in a batch at the end. The envelope is unchanged: openai_codex_cli only, G25/G26 Conductor leg and the G58 API-model leg, nothing else, every other provider leg NOT_RUN(NO_SPEND_AUTHORIZATION). If the round-trip is not proven inside roughly a dozen turns, stop and report - that is a design problem in the surface, not a budget problem. Any spend outside the envelope is STOP SPEND_REQUIRED with no interpretation permitted.

Then G27 (Gate 8d, applying E-7c) and on through Band 5 without pausing at band boundaries until every goal is TRUE or a STOP fires.

A-7: same session - the 16:30Z fs-watch window stays open, you record nothing, driver untouched. C-4 stands.

Unchanged and still binding: builder only - no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or shell=True.
