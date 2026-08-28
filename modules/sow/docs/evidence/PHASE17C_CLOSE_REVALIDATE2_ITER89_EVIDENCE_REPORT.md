# Phase 17C `.close-revalidate2` — Iteration 89 failed-gate evidence

Date: 2026-07-28
Verdict: **FAIL — no tag**

## Scope and reconciliation

At entry, `docs/loop/LOOP_STATE.json` and native git agreed: the latest Phase-17 tag was
`gate/phase-17b`, `gate/phase-17c` was absent, and the next step was
`phase-17c.close-revalidate2`. No reconciliation commit was required. The pre-existing
untracked `apps/desktop/package-lock.json` was preserved and excluded from every receipt.
Frozen canonical documents, schemas, and `mcp_server/` were not changed.

This single work unit produced these test-first source commits:

- `19d9c4b` — bind teardown and PTY callbacks to exact PID/generation identity;
- `2f5b084` — retain conductor/worker authority and I-X3 leases through confirmed process
  exit, retry failed releases, make recovery/audio/operator-resume evidence honest;
- `2855ec0` — isolate conductor release retry timers by session;
- `c492ee3` — correct stale lifecycle contract comments;
- `cad7aa9` — retain and retry every failed pre-birth/undelivered lease release;
- `7d465c1` — preserve `unavailable`/`failed` across conductor release retries rather than
  fabricating a process exit.

## Test-first and integrity output

The new regressions were observed red before implementation: missing retry module,
pre-birth release forgotten as `failed`, and pre-birth conductor retry target absent.
Final foreground results:

| Command | Result |
|---|---|
| `cd apps/desktop; npm test -- --test-reporter=spec` | **477 pass, 0 fail** |
| focused lifecycle/release tests | **32 pass, 0 fail** in the builder; final validator **37/37**, auditor **53/53** |
| `node --test terminal/test/*.test.js` | **199 pass, 0 fail** |
| `py -3.12 -m pytest tests/ -q` | **1418 pass, 61 warnings** in 291.50 s; later source commits were JavaScript/comments only |
| `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK: no drift in FROZEN set` |
| `git diff --check` | clean |
| `git diff --exit-code gate/phase-17b -- docs/canonical schemas mcp_server` | empty |

`node --check` was clean for every changed JavaScript file. No git remotes were present.

## Exact packaged Electron receipt

Final foreground command:
`cd apps/desktop; node selfcheck/run.js voice-conductor`

Receipt:
`docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json`

- source commit: `7d465c1d69317ac54e951ed258bf5085d9ba6342`;
- tracked product tree clean: `true`;
- SHA-256:
  `2069B47807B1A4C8461BF06ECA0445C937A17FBBA128752CD41EEABC494F1019`;
- result: **40/42 checks true; `ok:false`**;
- real PCM fixture -> real WSL Parakeet (`mock:false`) -> production bridge -> governed
  live Claude conductor ConPTY;
- main-owned `Ctrl+Shift+Escape` recovery was consumed and audited;
- the protected utterance was proposed/queued and wrote no bytes to the live pane;
- no TTS; capture existed only during transcription and was deleted afterward;
- authority released only on matching node-pty process exit; conductor and Electron PIDs
  were absent afterward; scratch ledger absent; capture count zero; lease usage returned
  to zero.

The failed checks were:

1. `live_conductor_answered`;
2. `voice_tool_call_denied_before_execution`.

The pane displayed the Claude Max weekly-limit screen (automatic reset Jul 30, 12:00
America/Chicago). It produced neither an answer nor a tool attempt, so a live denial could
not be observed. This is retryable failed-gate evidence, not a directive §8 blocker.

Six exact-source receipt attempts were run during this unit because each mandatory review
found a source defect that had to be fixed before the receipt could remain exact. Each
attempt used one governed session and one spoken fixture exchange, ran in the foreground,
and completed process/audio/lease cleanup before the next attempt.

Substitution: automation injected an OS-synthesized fixture WAV exactly where the physical
microphone hands PCM to the product. Everything below that seam was the unmodified product
path. A human speaking into a microphone remains operator first use, as Phase 17C permits.
The receipt also keeps the real-engine confidence-calibration limitation and deterministic
protected-verb lexicon limitation explicit.

## Exit criteria

| Criterion | Result |
|---|---|
| ≥60 s non-blocking probe, visible probing, refresh/reprobe, `SOW_*` overrides | **PASS** |
| Real PCM -> WSL Parakeet -> bridge -> governed live 17A conductor input | **PASS through submitted delivery** |
| Same live conductor answers | **FAIL — quota screen, no answer** |
| Protected action propose-never-execute | **PASS for brokered protected utterance; live tool-denial leg unproved** |
| Transcribe then discard; no TTS | **PASS** |
| Fixture packaged Electron receipt / D-P16 | **FAIL — exact receipt is red** |
| Physical microphone | **OWED to operator first use**, expressly permitted |
| Confidence limitation disclosed | **PASS** |
| D-LOOP-1 | **PASS** |
| Frozen canonical/invariant drift | **PASS** |

## Mandatory independent reviews

Both reviewers ran synchronously and completed inside this turn.

- **gate-validator: FAIL, no tag.** It confirmed exact source/hash, all 477 desktop tests,
  focused lifecycle checks, freeze/syntax, and clean teardown. After iterative adversarial
  findings were fixed, it reported **no remaining code findings**. The sole gate blocker is
  the red 40/42 live receipt.
- **spec-auditor: CLEAN for source.** It dynamically attacked denied admission, post-birth
  rollback, quit intent, exit correlation, per-session retries, every worker pre-birth
  release path, conductor retry targets, restart chrome, crash audio, operator recovery,
  and receipt wording. Its final verdict was **no functional or documentation findings**.
  Separately, the Phase 17C gate remains FAIL/pending quota retry.

## Disposition

`gate/phase-17c` was not created. Status remains `RUNNING`, not `BLOCKED`: no credential,
purchase, hardware, operator choice, or canonical contradiction is required, and the
provider reports an automatic reset. The next work unit remains
`phase-17c.close-revalidate2`: after provider availability returns, run one minimal
exact-source Electron receipt and both mandatory foreground reviewers; tag only on PASS.
