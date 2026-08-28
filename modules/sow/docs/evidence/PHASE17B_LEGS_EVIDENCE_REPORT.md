# Phase 17B `.legs` — evidence report

**Work unit:** `phase-17b.legs` (directive §16 track 17B, second half — U58's live worker legs)
**Date:** 2026-07-26 · **Loop iteration:** 81
**Work commit:** `12fc2e9` · **Review-fix commit:** this commit's parent
**Status:** WORK-IN-PROGRESS CHECKPOINT inside track 17B. **No tag.** `gate/phase-17b` closes at
`.close` with a mandatory whole-track gate-validator, exactly as 17A closed.

---

## 1. What this unit was asked to do

Directive §16, track 17B (second half):

> Conductor dispatch drives ≥1 LIVE worker publishing CANDIDATE over MCP → real gates → conductor
> synthesis; leg labels remain unfakeable (`_assert_legs_honest`). Minimal live exchanges;
> D-LOOP-1 in checks.

## 2. What shipped

`LiveGovernedFlow` accepts injected `WorkerHandle`s, so the SAME governed loop runs the
deterministic `LocalWorkerAdapter` pool or a real supervisor-spawned vendor terminal with **no
branch in the governed path** (invariant 4 — workers interchangeable behind the adapter contract).
A live handle is minted only by `live_claude_worker_handle`, which is born from
`spawn_claude_code_terminal` — the one governed live-frontier spawn site — so every live gate applies
before any call: roster profile + `LIVE_OPERATION_AUTHORIZED`, provider-live, R8 §6 operator terms
(OP-9), CLI presence, I-X3 acquire.

A worker leg is **derived from that node's own evidence row**, never asserted:

| condition | per-node leg |
|---|---|
| executed nothing | `skipped` |
| mock-bound | `mock` |
| live-bound, verified checkpoint | `live` |
| live-bound, call counted, no checkpoint | `attempted` |
| live-bound, executed, no call counted | `skipped` |

`_assert_legs_honest` refuses a declared leg that contradicts the evidence **in both directions** —
a `live` claim with no verification record is unrepresentable, and an under-claim that would hide
real spend is equally refused, because under-reporting spend is the dishonest direction (§6).

## 3. Three real defects, each found by a live run failing, each fixed test-first

1. **`ModelWorkerAdapter.execute` never returned `structured`** — the STAGE gate had nothing to
   evaluate, so the live adapter could not complete the governed flow at all.
2. **U60 root cause** (recorded for two phases as "transient loopback flakiness"; it is neither
   transient nor environmental). `mcp_server/server.py` gives each handler `timeout = 60` (F6), and a
   live model call runs longer, so the **server** reaps the caller's connection mid-call. The
   subsequent write SUCCEEDS into the local buffer (the FIN is unread) and the failure lands on the
   READ as `WinError 10053` — where retrying is forbidden, since a delivered request may already have
   been applied. The send-side retry therefore never fired. Fixed by checking liveness **before** the
   write: nothing has been sent, so re-establishing cannot re-apply anything. Desync fails closed.
3. **`claude -p` blocks on inherited stdin.** A supervised worker inherited the supervisor's
   never-EOF stdin and the CLI waited on input that never came. Measured on this host: **150 s
   timeout inherited vs 3.5 s with `DEVNULL`.** Fixed in both live CLI backends (claude_code +
   codex parity). The prompt travels in argv, and a governed node reading the supervisor's console
   would be a containment hole anyway (invariant 29).

## 4. The live result (the exit criterion)

`docs/evidence/live/PHASE17B_LEGS_DISPATCH_FEED.json`, produced by
`py -3.12 tools/live/emit_conductor_dispatch.py --emit-conductor-dispatch --live-workers`:

```
legs        : {"conductor": "mock", "workers": "live"}
worker_legs : {"worker:worker-claude-live": "live"}
evidence    : node_id worker-claude-live, leg live, adapter claude_code,
              executed true, spent true, verified true, model "claude-opus-5[1m]", tasks ["t-1"]
gates       : plan PASS, stage_pass 1/1, acceptance PASS, accepted_count 1
live_workers_owed.owed : false   (DERIVED from the packet's evidence, never asserted)
torn_down   : true
ts          : 2026-07-26T19:19:27+00:00        (real clock — the mock path keeps DISPATCH_TS)
live_run    : elapsed_s 277.4, cli_present true, repo_live_config_exists true, timeout_s 420
```

A LIVE `claude_code` worker was resolved BY DESCRIPTOR, executed the assignment, published a
CANDIDATE over MCP, the **real gate engine** read the stored bytes back and accepted them, and the
conductor synthesized them into the acceptance packet. **Reproduced three times independently**
(254 s, 318 s, 277 s elapsed). The 150 s ceiling the first attempts used was genuinely too low; it
is now 420 s — a fail-closed bound on ONE exchange, not a target.

## 5. Self-check of every exit criterion

| Criterion | Result | Evidence |
|---|---|---|
| ≥1 LIVE worker publishes CANDIDATE over MCP | **MET** | receipt above; `verified:true` checkpoint |
| real gates, then conductor synthesis | **MET** | stage PASS 1/1, acceptance PASS, `accepted_count 1` |
| leg labels unfakeable (`_assert_legs_honest`) | **MET (bounded)** | both directions refused; limit in §7 |
| minimal live exchanges | **MET** | one subtask routes to the single live node ⇒ one exchange |
| D-LOOP-1 teardown in-unit | **MET** | `torn_down:true`; lease ledger `{}` and `in_use 0` after every run |
| full suite green | **MET** | **1370 passed** (baseline 1338 ⇒ **32 new tests**) |

## 6. Independent review (foreground, in-unit — D-LOOP-2)

Both ran synchronously against the committed state `12fc2e9`.

**gate-validator: PASS_WITH_RESERVATIONS.** Re-ran the suite itself (1366 at that commit), traced
the reconnect for double-apply safety and found it airtight, and empirically confirmed the default
path launches zero subprocesses. It independently corroborated the live run from filesystem evidence
outside the artifact.

**spec-auditor: PROHIBITED DRIFT: NONE**, 3 MAJOR + 6 MINOR.

Both found the **same** top defect independently: a real live run stamped with the fixed replayable
`DISPATCH_TS`. **Every finding from both reviews is fixed in this unit:**

| Finding | Fix |
|---|---|
| V-R1 / A-MAJOR-3 — real run stamped with the mock timestamp | live runs take the real clock; receipt gains a `live_run` block (`run_ts`, `elapsed_s`, `cli_present`, bounds) |
| A-MAJOR-1 — spend vanished on a post-call fault (`undispatched_feed` hard-coded `skipped`) | the fail-closed feed now carries the flow's worker evidence and derives its legs from it |
| A-MAJOR-2 — CLI-presence gate skipped for an injected backend | gate (4) now applies to any REAL CLI backend, injected or not; pinned by a test asserting no I-X3 terminal is acquired |
| V-R4 — durable lease stranded if `connect()` raises | client creation moved inside the try that releases |
| V-R5 — published-but-unstructured artifact orphaned as CANDIDATE | rejected in MCP before falling into the refusal path |
| A-MINOR-1 — a live node that spent nothing was labelled `mock` | now `skipped`; aggregate folded from the per-node legs so the two derivations cannot drift |
| A-MINOR-2 — "unfakeable" overclaim | STATED LIMIT added (see §7) |
| V-R6 — codex stdin parity untested | test added for both codex call sites |
| V-R7 / R8, A-MINOR-3 — stale/overstated docstrings | corrected, including the residual race and the 420 s-vs-60 s consequence |
| A-MINOR-4 — token ceiling claim false | corrected in place; recorded as **U116** |
| A-MINOR-5 — selfcheck vs. a now-reachable `owed:false` | assertion kept STRICT (it guards the shell's launch path, which must never spend) and its intent made explicit |
| V-R9 — default path unpinned by any test | test asserts no subprocess is launched at all |
| V-R3 — commit-message test numbers wrong | corrected here: baseline **1338 → 1370**, **32 new tests** (the commit body's "1362 / 4 new" is wrong; history is not rewritten, §2.6) |

## 7. Limitations, stated

- **The `live` leg is trustworthy exactly as far as the caller minting the handle is** (U43,
  inherited). `WorkerHandle.leg`/`verify` are injected fields; unforgeable only for handles from
  `live_claude_worker_handle`. What the design rules out is every ACCIDENTAL and every mock-SHAPED
  path — this suite deliberately mints fake verifiers to drive the flow deterministically.
- **The receipt cannot by itself distinguish a live run from a stubbed one** — demonstrated by the
  validator. Narrowed by the `live_run` block and the real timestamp, not eliminated. **U119.**
- **U60 is narrowed, not eliminated:** a reap between the check and the write still fails closed
  unrecovered, and a 420 s call against a 60 s handler timeout means every live dispatch is reaped
  at least once and relies on the reconnect. A workaround for a timeout mismatch, not a resolution.
- **No enforceable token bound on a live exchange** — only the wall clock. **U116.**
- **No cost instrumentation on the worker spend path** (Buildout §4). **U117.**
- **The new feed fields reach no UI surface yet.** **U118.**
- **`ruff` is not installed on this host** and §2.7 does not permit a pip install for it; the
  validator independently confirmed the absence is genuine. Substitution recorded, not skipped.
- **No D-P16-0 in-Electron receipt is required for this sub-step:** it changes no shell/UI code.
  The picker→spawn UI receipt belongs to `.spawn` and is unchanged.

## 8. Scope honesty

The dispatch's **conductor** leg is still `mock` on this path — a live conductor session is 17A/17C
work, and nothing here claims otherwise. No new provider. No credential read, stored, or transmitted
(the CLI uses its own host-native auth). `config/live_operation.json` is untouched and uncommitted.
`docs/canonical/` and `schemas/` untouched. Registers appended, never rewritten.

## 9. Register

U58 worker half **RESOLVED** (conductor half unchanged); U60 **root-caused and RESOLVED** with its
prior diagnosis explicitly withdrawn; **U116–U119** opened. All append-only in
`docs/registers/UNRESOLVED_ISSUE_REGISTER.md`.
