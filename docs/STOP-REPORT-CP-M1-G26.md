# utc: 2026-08-26T05:07:00.2199728Z
# producer: ox-alpha CP-M1 Band 4 / G26 STOP v6
# supersedes v5 (v5's blocker was removed by the operator's C-8(a) restart; this version records the
# new failure observed on the REPAIRED tree).

STOP condition: **CONDUCTOR_LAUNCH_PROCESS_DEATH** (Band 4 / G26) - on the fresh, repaired,
operator-started tree, POST /launch-conductor killed the whole electron tree mid-handler (client
saw the socket close; within seconds no electron process remained). No refusal JSON, no validator
message. Cause NOT ESTABLISHED from disk evidence (T-3); the app's own console output - which
holds its dying words - is in the operator's restart session and was not readable by the builder.

## FACT condition

- FACT[evidence/cpm1/8d/g26-newtree-proof.txt] - four pids (24052/61760/46092/49984) all started
  04:57:40-43Z, strictly after launch-source.js 04:24:27Z: the running verifier WAS the repaired one.
- FACT[evidence/cpm1/8d/g26-state-5-fresh-prelaunch.json] - driver healthy, launchState unstarted.
- The launch call failed with "The underlying connection was closed" (not a timeout, not a status).
- Immediately after: zero electron processes; 5199 TIME_WAIT only.
- Lease ledger EMPTY after; no orphaned claude.EXE CLI process (only the operator's unrelated
  Claude desktop store app from 02:42Z). ZERO SPEND; turn count remains 2.
- No Application-log Error events, no crash dumps, no app-tree writes at the crash moment -
  only startup-time .recovery/.approvals writes at 04:57:43Z.

## Ruled out / unread (T-3)

Ruled out: validator refusal (no response returned), lease leak, hidden provider session, builder
tooling (bounded handle-free call), stale code (process newer than repair). Unread: the console
stdout of the operator's restart session; any native abort trace (a node-pty/ConPTY-level abort
would kill the process silently - consistent with the observed silence, not provable from here).

## Bounded operator options

1. Read the restarted tree's console output for its last lines before death and paste them into
   session; the builder resumes diagnosis from those words. RECOMMENDED - it is the only witness.
2. Authorize the builder to re-run the launch ONCE more against a NEW operator-started tree with
   stdout captured to files the OS owns from the start (C-8(b)), so the dying output is EVIDENCE.
3. Defer G26 again as NOT_RUN(CONDUCTOR_LAUNCH_CRASH_UNDIAGNOSED) and take Band 5 goals that do
   not require a conductor session (G28 registry machinery), leaving R-04/R-05/R-06 open.

## State at stop

Zero spend; turn count 2; lease ledger empty; nothing running from modules\*; ports 5175/5180/
5183 free, 8700 still held by the pre-existing external owner (untouched); gates 0-7b byte-
identical throughout. Ladder: G25 TRUE; G26 FALSE (this stop); count 26/124 unchanged - cause
named per E-8 on the same line in the session report.
