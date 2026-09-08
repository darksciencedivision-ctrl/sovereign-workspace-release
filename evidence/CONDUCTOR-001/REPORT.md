# SW-CONDUCTOR-001 — run report

**Builder seat:** grok-4.6, Phase 4 continuation. Phases 1–3 were already on disk, reviewer-verified, when this session started.
**Phase 4 UTC:** re-pin and harness 1 captured 2026-09-08T02:20:31.8434687Z; exit hashes 2026-09-08T02:34:05.6153794Z.
This document asserts no repair, test pass, review, release, or production status.

The file this replaces was a STOP report from an earlier aborted attempt (`HOST_NOT_QUIESCENT`). It is not appended to.

---

## Phase 1 — A: give delegation an address

**Files:** `modules/sow/apps/desktop/control/conductor-delegation.js` (16,332 → 25,381 bytes), `main.js` one call site, new `apps/desktop/test/objective-addressing.test.js` (15,023 bytes).

**What changed.** Addressing reuses `resolveTerminalRefs` from read-only `conductor-view.js`. Broadcast stays the default. A named terminal that is not open or not live is reported and does not silently broadcast; if every named terminal is unreachable, delivery is to none. Every recipient gets one short delivery-position line.

The two-argument F-36 signature is preserved as a wrapper that forwards `arguments[2]` when present (`conductor-delegation.js:368-371`). The contractual three-parameter form is `selectObjectiveRecipientsFor`. `main.js:2719` passes the objective: `selectObjectiveRecipients(liveWorkerRecords(), registered, text)`.

**Decision.** Keep the two-argument source shape the protected F-36 mutation control anchors on, rather than widening that function's formal parameters.

**Captured (predecessor):** `evidence/CONDUCTOR-001/phase1-fastcheck.txt` — `tests 69`, `pass 69`, `fail 0`. `broadcast-delegation.test.js` was not edited.

---

## Phase 2 — the B audit

Read-only. Artifact: `evidence/CONDUCTOR-001/AUDIT.md`.

**Gate verdict (from that file):** Q1 CLEAN, Q3 CLEAN, Q6 CLEAN → the gate does not stop B. Phase 3 proceeded.

Informational: Q5 records that a bridge-relayed `assign_task` hits the gateway delivery surface (pre-shaped `args.task`), not the Python MCP tool that creates a durable task. Named, not a stop.

---

## Phase 3 — B: wire the bridge

**Files:** `main.js` only. `local-mcp-bridge.js` was not modified (audit found no gap in the module).

**What changed (read this session, targeted):**
- `require("./control/local-mcp-bridge")` (`main.js:74`)
- `conductorSessionAlive` — RUNNING registry record AND `processIdentity` (`main.js:878-882`)
- `attachConductorBridge` / `detachConductorBridge` (`main.js:887-949`)
- io bindings: `writePanePrompt`, `paneWriteRefusalFor`, `readinessWindow`, `createLoopbackRequest()`, minted token
- attach after governed spawn, before `runConductorReadiness()` (`main.js:1170-1172`)
- detach on launch failure (`:1176`), real session end (`:1238`), `completeNormalQuit` (`:3225`)

Relay-only: the bridge forwards model-emitted blocks; identity attach cannot raise `operationCount`. No new IPC channel.

**What was not done.** No new Phase 3 test file is on disk. `test/local-mcp-bridge.test.js` is still 13,983 bytes dated 2026-09-01. The loop's Phase 3 decisive-test list (real server + real bridge + source-shape wiring) was not added by the predecessor and was not added here — Phase 4 does not add product tests. Live attach against a running app was not exercised (no application launch).

`main.js` 218,002 → 225,050 bytes. `node --check` exit 0. Zero CR bytes.

---

## Phase 4 — U186 re-pin, harnesses, four suites

### Re-pin

Counted on the 225,050-byte `main.js` before editing either baseline:
- bare substring `handleOperatorResumeInput(event, input)` ×2
- anchor constant (four-space indent, trailing semicolon) ×1
- CR bytes: 0
- SHA-256: `c43a91a2dd2e35b68fd351b4ed3942ee16883456d7fc77ef751ff0adfe31010b`

`PINNED_BASELINE` / `[MAIN]` moved from `43D79F5C7D8B6521DBFA67708D6626BF8DD18AD1AAE96393EFB1A616795D2B35` to `C43A91A2DD2E35B68FD351B4ED3942EE16883456D7FC77EF751FF0ADFE31010B` in both mutation files, with a house-style note. The other four pins in `system_pane_write_mutations.js` (pane-writer, conductor-readiness, worker-readiness, modal-affordance) were left alone.

### Harnesses (sequential)

`evidence/CONDUCTOR-001/mutation-pane-input.txt` (exit_code=0):
- 37 lines `CAUGHT`
- `restored main.js SHA-256 C43A91A2DD2E35B68FD351B4ED3942EE16883456D7FC77EF751FF0ADFE31010B — BYTE-IDENTICAL`
- `ALL MUTATIONS CAUGHT`

`evidence/CONDUCTOR-001/mutation-system-pane.txt` (exit_code=0):
- 39 lines `CAUGHT` including P28 and P29
- all five files restored BYTE-IDENTICAL to their pinned hashes
- `ALL 39 SYSTEM→PANE MUTATIONS CAUGHT`

### Four suites (captured)

| file | captured trailing summary |
|---|---|
| `evidence/CONDUCTOR-001/js.txt` | `tests 1325` / `pass 1325` / `fail 0` / `duration_ms 99121.203` |
| `evidence/CONDUCTOR-001/python.txt` | `2746 passed, 3 skipped, 23 warnings, 12 subtests passed in 272.98s` |
| `evidence/CONDUCTOR-001/shell.txt` | `323 passed, 34 subtests passed in 210.90s` |
| `evidence/CONDUCTOR-001/text.txt` | `4 passed in 0.78s` |

JS 1325 = the 1,313 hold plus 12 tests from `objective-addressing.test.js` (all 12 present in `js.txt:533-544`). Both protected F-36 tests are in `js.txt:52` and `js.txt:56`. `broadcast-delegation.test.js` hash unchanged.

The shell suite rewrote `evidence/gate5/screenshots/shell-grid-rendered.png` — expected, not this run's edit.

---

## Exit hashes

Captured `evidence/CONDUCTOR-001/exit-hashes.txt` at 2026-09-08T02:34:05.6153794Z. Lowercase.

**Changed (vs LOOP entry pins):**

| file | bytes | SHA-256 |
|---|---:|---|
| `apps/desktop/control/conductor-delegation.js` | 25381 | `05daff5db7cfbd5f55d842f89f24a5f105fffe8a6e831b29cce34fd511bbe410` |
| `apps/desktop/main.js` | 225050 | `c43a91a2dd2e35b68fd351b4ed3942ee16883456d7fc77ef751ff0adfe31010b` |
| `tools/mutation/pane_input_bypass_mutations.js` | 39215 | `a35acee74a24fe8bcb166695ebb3105aa0dd2aaf7724d4f25bcbca48dafcf3a2` |
| `tools/mutation/system_pane_write_mutations.js` | 49292 | `81d5cd833120c36f2e983e56127a3c989e9b5677caba38edc31a9fd6f47c7e5a` |
| `apps/desktop/test/objective-addressing.test.js` (new) | 15023 | `f19b1b4590efe7aa0edcb5039296fc8fafd4fe18e056020175fe08a420aabbf5` |

**Unchanged, matching LOOP entry pins:**

| file | bytes | SHA-256 |
|---|---:|---|
| `apps/desktop/control/conductor-view.js` | 19197 | `6e1bcc395f0e9d371ab6c9c61941a664e13c4a955f0066c33ae56e04ee3d171c` |
| `apps/desktop/control/local-mcp-bridge.js` | 19283 | `c5f20c7e652c3ec3d1ff6158ed38185ec3b3ac7e6eefb453b7b592468c24f2da` |
| `apps/desktop/test/broadcast-delegation.test.js` | 4459 | `f9db388cfd56a1547b4705c5e1e0c1277ed16394061eadf7bef903d8f27b6bd9` |

**Read-only set, hashed at exit (this session did not edit them):**

| file | bytes | SHA-256 |
|---|---:|---|
| `apps/desktop/preload.js` | 9080 | `f4b880a56e64800856b2d262074eba74845ca0b05f98121b4a2c595d1ca3d111` |
| `apps/desktop/renderer/renderer.js` | 90766 | `92540b1043dc67d7b7956c745d79564792cee713f3a85ec95aea0f6e89f2f76f` |
| `apps/desktop/renderer/index.html` | 22699 | `2ff07a7bbd9d93fa2d71a2cb1145d15f394f79b33a6677566a763e7e55ef8419` |
| `apps/desktop/picker/source.js` | 8756 | `77521719668fedc8078b565f0ac76945e725689816d3787639d3ee018ba992e8` |
| `apps/desktop/control/workspace-journal.js` | 22820 | `acbf56ab65e8788300263187fc1077e1b64480556b3af5f2a080c5f42d528107` |
| `control_plane/policy.py` | 21570 | `712cdc071155f7461e76257aaa733a38661744cce75da724813fd05005ff1abc` |
| `mcp_server/memory_service.py` | 9578 | `41e1b87738e628f2b67e8115a2ecdb8de92e7927b92adc0b8113d777b71764cb` |
| `control_plane/tasks/graph.py` | 5817 | `217daa1b09d70fb06406da11505834e3eac60d13d4303e61b5394c0eaa2793da` |

`shell/**` was not edited. The screenshot rewrite above is under `evidence/`, not `shell/`.

Harness-2 non-MAIN pins still match the constants left in `system_pane_write_mutations.js`: pane-writer `a517069e…`, conductor-readiness `b264243d…`, worker-readiness `494e01fb…`, modal-affordance `3f0e3cbb…`.

---

## What this run did not do

- No git commit, push, stage, checkout, or reset.
- No application launch; the bridge was not exercised against a live pane.
- No web access, pip, or npm install.
- No edit to `broadcast-delegation.test.js` or `local-mcp-bridge.js`.
- No Phase 3 wiring-integration test file added.
- No live proof that attachment clears a STALLED badge; that remains an operator acceptance run.
- Q5's durable-task gap is unchanged: a conductor `assign_task` through the bridge delivers, it does not create a store row.

BUILDER CLAIM: no gate is submitted for reviewer evaluation and no PASS status is asserted.
