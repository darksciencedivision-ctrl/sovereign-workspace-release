# PHASE 17D `.events` — the approval drawer shows what the session did

**Work unit:** `phase-17d.events` (sub-step of directive §16 track 17D — no `gate/phase-17d` tag here).
**Date:** 2026-07-31 · **Host:** Windows 11, Electron 31.7.7 / Node 20.18.0 / `py -3.12`.
**Work commit:** `1282636` · **review-fix commit:** see the register/evidence commit that carries this file.
**Closes:** operator finding **F2** (directive §16, first use 2026-07-25).

---

## 1. What was wrong

The operator opened the shipped shell and found three pending approvals waiting for them — a plan, a
protected action, a clarification — that no session had produced. They were Phase 16D's DETERMINISTIC
DEMONSTRATION trio: a canned objective run through the real flow and gate engine, two canned commands
run through the real `CommandBroker`, rebuilt identically on every fetch by
`control_plane/orchestration/approval_feed.py`. The authority path was real; the content was canned.

The 16D in-Electron self-check asserted the defect as its success condition (`has_plan`,
`has_protected_action`, `has_clarification`, `badge_at_least_3`). It was green the whole time.

## 2. What shipped

**The producer is replaced, not patched.**

| Piece | What it does |
|---|---|
| `apps/desktop/approvals/session-events.js` (new) | The shell's append-only, per-run record of what THIS session produced: a protected/destructive utterance the broker queued, a clarification the bridge would not route, and (built + covered, producer owed to 17E) a governed dispatch's plan. Records evidence, never verdicts. |
| `control_plane/orchestration/session_approvals.py` (new) | Folds that log into a real `ApprovalQueue`, RE-DERIVING every row with the classifiers that decided it live. No events ⇒ an empty drawer. |
| `tools/live/emit_approval_drawer.py` / `emit_approval_decision.py` | Now take `--events <log>`; they start no MCP server and no flow (D-LOOP-1 by construction). |
| `tests/support/demo_approval_queue.py` | The demonstration trio, moved under `tests/`. A test fails if any product tree imports it. |
| `control_plane/orchestration/approval_feed.py` | **Deleted** — a test asserts it does not exist. |

**The shell does not get to say what an event means.** A recorded utterance is re-routed through the
real `ConductorVoiceBridge` over the real `CommandBroker` (invariant 30 — no second classifier), and a
recorded classification that no longer matches fails the whole feed closed. A plan's `approvable` is
derived from its recorded `gate@1.0` verdict through the same `build_plan_proposal` the 15E surface
uses. A recorded decision is replayed through `ApprovalQueue.resolve`, so invariants 1 and 16 are
re-enforced on every rebuild — which is also what makes a resolve PERSIST (the gap 16D recorded as
owed) with no component holding a mutable queue.

**Two things found on the way, both fixed here:**
1. A low-confidence or blank utterance was refused correctly and then dropped — it never reached the
   one drawer OP-7 §12.5 puts clarifications in. `_clarify` now routes through the same broker + mirror
   the proposed action uses.
2. The launch-time governed dispatch (a real gate verdict over the emitter's own fixed smoke
   objective) is deliberately NOT recorded: it is F2 one layer down. `recordDispatchPlan` refuses
   anything not marked as an operator-originated objective.

## 3. Exit-criterion self-check (directive §16 track 17D, the `.events` half)

| Criterion | Evidence |
|---|---|
| The drawer sources ONLY real session events | `PHASE17D_APPROVALS_SELFCHECK.json` — at launch `sourced:true`, `source:"session_events"`, `badgeCount:0`, no rows, `launch_no_demo_trio:true` |
| Protected verbs reach the drawer | one capture → exactly one row, `kind:"protected_action"`, `detail.verb:"spawn"` (from the classifier), broker ref present, provenance `event_id`/`channel:"voice:capture"` |
| Voice clarifications reach the drawer | `tests/integration/test_conductor_voice.py::test_a_clarified_utterance_reaches_the_operators_drawer` (`approvable:false`, nothing delivered, nothing executed) |
| Gate promotions | event kind + builder + recorder BUILT and covered; the producer (an operator-originated dispatch) is owed to 17E — stated in the module header and in `main.js`, not implied |
| The demo trio is test-only, never in the product path | `test_the_demo_trio_is_not_reachable_from_the_product_source`, `test_the_demo_builder_is_not_importable_from_the_product_tree` |
| The decide is governed, self-authorizing nothing | receipt: `decide_routed`, `decide_self_authorized_false`, `decide_resolved_by_python`, `decision_event_minted_by_authority` |
| A resolve persists; no override path | receipt: `decision_persisted_empty_drawer`, `re_decide_governed_refused` |
| D-P16-0 in-Electron receipt | `docs/evidence/receipts/PHASE17D_APPROVALS_SELFCHECK.json` — **ok:true, 21/21**, exit 0, `duration_ms 2499` |

## 4. Commands run (this host, foreground — D-LOOP-2)

```
py -3.12 -m pytest tests/ -q                     → 1470 passed
apps/desktop:  node --test test/*.test.js        → 581 pass, 0 fail
terminal:      node --test test/*.test.js        → 209 pass, 0 fail
py -3.12 tools/manifest/compute_manifest.py --check → freeze check OK (no drift in FROZEN set)
apps/desktop:  npm run test:falsify              → ALL MUTATIONS CAUGHT, main.js restored BYTE-IDENTICAL
apps/desktop:  npm run test:falsify:authority    → ALL 11 MUTATIONS CAUGHT, all files restored BYTE-IDENTICAL
apps/desktop:  node selfcheck/run.js approvals   → exit 0, receipt ok:true 21/21
apps/desktop:  node selfcheck/run.js assembled   → exit 0, 16F receipt ok:true (approval leg re-proven)
```

**Falsification (the receipt is load-bearing).** `recordUtterance` made to drop the event ⇒ 7 checks
red, `ok:false`; file restored byte-identically (SHA-256
`38F1CB863DA5657458109B6D3FFC549613BD8D901460CB7B1BA4316301C07127`) and re-run green. The
gate-validator independently reproduced this falsification and its restore.

**Launcher ceiling.** `selfcheck/run.js` gave `approvals` its own 420 s bound: the old 150 s default
killed a run whose receipt was 21/21 green — a launcher that reports a shell failure that did not
happen is its own defect.

## 5. Independent review (mandatory, foreground, this turn)

**gate-validator — PASS_WITH_RESERVATIONS.** Re-ran every suite (numbers matched), re-ran the receipt,
independently falsified and restored it, and attacked the re-derivation with ten hand-written forged
logs: a chat sentence claimed as a protected action, a protected verb demoted to a clarification, a
minimal `{"verdict":"PASS"}` plan, a non-operator decision, a drifted event schema, and a mixed
good/forged log — **all refused, all fail-closed with an empty drawer, no partial render**. It also
confirmed the decide path refuses an approve of a clarification, a re-decide, an unknown item, and an
illegal decision value, and that no `decision_event` is minted on a refusal.

**spec-auditor — CHANGES_REQUIRED.** Findings and what was done, in this unit:

| # | Finding | Response |
|---|---|---|
| 1 | A forged `decision` event can dispose of an approvable row; three places claimed it could not | Claims corrected in `session-events.js`, `session_approvals.py`, `emit_approval_decision.py`; residual widened to name row DISPOSAL; **U206** opened; the misnamed test renamed and a new test pins the hole honestly |
| 2 | An approve made a row vanish while nothing executed, and the renderer discarded the governed feed | `renderer.js` now renders the governed outcome above the rows — including "NOT YET EXECUTED: …" on an approve and the reason on a refusal |
| 3 | The 16F assembled self-check was silently broken by the feed-source rename | Rewritten to CAUSE the event it approves; re-run green on this host; stale initialized-false receipt fields removed |
| 4 | The module claimed three producers; one is wired | Header now names exactly what is wired and what is not (typed → U149; plan → 17E) |
| 5 | "a verdict the gate engine decided" is a shape check, not provenance | Docstring + error text corrected; U205 covers the residual |
| 6 | The `authority` string's invariant-1 half is a presumption | Feed now carries `operator_identity_presumed`; **U207** opened |
| 7 | Transcript retention has no TTL and no disposal at quit | Stated in the module header; **U208** opened |
| 8 | `begin()` ran on every renderer load, truncating mid-session | Now once per process |
| 9–11 | Dead broker `ref`, unbacked "recorded as owed", unused parameter | `side_effects_owed` now explains the `ref`; register rows landed; parameter removed |

**gate-validator reservations answered here:** R1→U205, R2→construction-time guard + four new tests,
R3→`side_effects_owed` wording, R4/R5→header correction (producers), R6→**U209**, R7→log text fixed,
R8→this report + the register rows, R9 (`__pycache__` residue) and R10 (a mutated run can present as a
timeout) noted, no action.

## 6. Substitutions and limits (directive §6, stated plainly)

* The read/decide path is a bounded `py -3.12` subprocess, not the authenticated IPC surface — the
  §6 substitution inherited from 16B/16C/16D, unchanged.
* No live model call, no credential, no network on any path in this unit; the drawer emitters fold a
  file and start nothing.
* The drawer's `ref` is the pending id of the classification that rebuilt the row, not a handle into a
  live broker: it is re-minted per fetch and routes nowhere until the durable queue lands (17E).
* Re-derivation binds rows to the real classifiers, NOT to a proof of governed origin (U205/U206).
* Gate promotions: the event kind and the recorder exist and are covered; the producer is owed to 17E.

## 7. What remains in track 17D (for the `.close` unit)

`U73` (`pane:resize` guard — the guard is present at `main.js`, needs verification + register update),
audit item `R4` (the non-hermetic wsl-PATH test — the `wsl_present` fixture is present, needs the same),
`U69` discharge, then the track gate `gate/phase-17d` with the mandatory validator.
