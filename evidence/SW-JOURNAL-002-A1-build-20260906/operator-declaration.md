# utc: 2026-09-06T17:52:45.2344938Z
# producer: Codex SW-JOURNAL-002-A1 Step0
Adopt SW-JOURNAL-002-A1 and execute it.

Read it from disk: D:\production software 3\SW-JOURNAL-002-A1.md

HOST QUIESCENCE — the condition that stopped you is cleared. Verified by the
reviewer 2026-09-06: ports 5175, 8700 and 5180 all free, and no electron.exe,
python.exe, node.exe or ollama.exe process running from this worktree. The
SOW app and the shell are both closed. Re-verify it yourself at Step 0 as the
work order requires; do not take this line as a substitute for the check.

STANDING RULE, added to the A5 runbook and in force for every future
directive: the operator closes the application and the shell after every
acceptance run. If you find the host non-quiescent again, STOP exactly as you
did — that stop was correct both times over.

PINS — rehashed by the reviewer just now, all seven byte-identical to A4.
Nothing moved while you were stopped. Validate them yourself anyway.

ENVELOPE — the seven files in A4 are authorized under both the SWS-UI-001 §7
envelope and the SW-REMED-001 LEGACY\_REFERENCE constraint. This instruction is
the authorization artifact; record it verbatim with its UTC in
evidence/OPERATOR-INSTRUCTIONS.log.

Scope is F-37, F-38 and F-39 only. Do not reopen F-27 through F-36 — the write
side works and was verified. Do not wire tasks/graph.py. Do not touch
control\_plane/policy.py or mcp\_server/memory\_service.py. Do not reconcile the
store roots.

Constraints unchanged: you are a code builder and not a Sovereign node. No
Sovereign MCP tool call. No application launch. No commit, push, stage,
checkout or reset. No webfetch — pane content never leaves this host. Never
write PASS; never claim production-ready or that a gate passed.

A0.2 applies: main.js will change, so the U186 re-pin is mandatory — re-count
the anchor constants, verify zero CR bytes, re-pin both tools/mutation
baselines with notes, re-run both harnesses, all CAUGHT, byte-identical
restores. The JS suite is expected red until Step 4 completes.

Baselines to hold: 1,241 JS pass / 0 fail; 2,742 Python passed, 3 skipped,
0 failed; text integrity 4 passed. Run test\_text\_integrity.py after every
scripted edit.

Stop rather than widen on new\_channel\_required, shell\_becomes\_recipient, or
write\_side\_change\_required. Report and hand off; the operator runs the
acceptance.