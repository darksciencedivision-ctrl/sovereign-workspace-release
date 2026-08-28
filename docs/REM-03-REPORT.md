# REM-03 REPORT — v2 theme verified end-to-end under LOOP-01; Gates 4c and 5b submitted as CANDIDATEs

# utc: 2026-08-24T16:31:58.3828323Z
# producer: ox-alpha LOOP-01
# supersedes: docs/REM-03-REPORT.md sha256 d037b66acc7545f3d135040b16ee555b82fe6887d962225e06374887c21b8705
#             (the 2026-08-22T23:25Z stop report; preserved byte-exact at
#              evidence/rem03/REM-03-REPORT-superseded-20260822.md; its facts are carried forward)

## 1. Authorization chain

FACT[evidence/OPERATOR-INSTRUCTIONS.log] kickoff logged verbatim at 2026-08-24T06:42:39Z selects
STOP-REPORT-SOW-TREE-ACTIVITY option 2 (fresh REM-03 baselines of the current tree), waives stage
pauses, requires every long-running helper detached, and authorizes this goal-state completion loop.
INTERPRETATION Option 2 makes the current SOW tree state (HEAD e6fcb89984ba50f296a1f4debb6669bfef12f996,
3 porcelain entries) the legitimate comparison base going forward; no protected tree was written.

## 2. Loop execution

FACT[evidence/loop5/LOOP-LEDGER.jsonl] records iterations 1-11 of docs/OX-ALPHA-DIRECTIVE-LOOP-01.md:
each line one goal, one smallest authorized action, and the oracle re-run that flipped it. Eleven
iterations; four were G-oracle corrections (see section 5). No shell source file was edited, SOW was
never launched, module launches happened only through /api/startup-test, keep-runs stopped only
through /api/stop, and the only provider touch was a read-only GET /api/tags
(FACT[evidence/loop5/ollama-tags-fresh.txt]: 5/5 required models PRESENT, taken before the sovereign capture).

## 3. Goal table (proof artifact, sha256)

| Goal | Proof |
|---|---|
| G0 precondition | FACT[evidence/loop5/session-start.txt] f4d1013a242f7b3d94deeb0ffa8d8741c6352e554b218bb4cebeef52e5fa12ee (DECISIONS sha bb911905...4869a, ports free at start); helpers' detached operation evidenced by FACT[evidence/loop5/fs-watch-loop01.txt], FACT[evidence/loop5/states-timeline.txt], FACT[evidence/loop5/shell-stdout.txt] |
| G1 baselines | FACT[evidence/rem03/quiescence-inspect-1.txt]/[-2.txt] gap 127 s byte-identical bodies; three manifest-rem03-before-* via tool sha 64c488ed07c95579c69bcb8dee42fb2aec88b821bf676cc7b259740d7f955d22 naming supersedes + original hashes; FACT[evidence/rem03/sow-git-rem03-before.body]; originals byte-untouched per goalcheck |
| G2 suite | FACT[evidence/test-run.txt] d361f9bf5f8a5f97b671daa2ce1632538416e0cbb9dca6a3d80c77634b091d00 - 121 tests OK after G1; BUILD-MANIFEST 40 entries match disk; app.css = pinned 329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab |
| G3 ledger 4c | evidence/GATE-LEDGER.json "4c" CANDIDATE, 7-entry evidence list all hash-matching; pre-write snapshot FACT[evidence/loop5/ledger-snap-pre4c.json] b2ee9910457916116cb4f786a9d4d308f86f8037daf94438a77e12d36374866e; reviewer entries untouched (prefix/suffix assertions) |
| G4 visual set | eight PNGs from the live shell on v2, non-blank, states equal to live /api/state at capture: grid 7e346316b0d939c058c30a31c99992b972e390887d656b15474361d1f04241f3, sovereign READY 48495f6d8aaa3652aef7d3d4f85d460fa6b3ab798b72a18ae7f2695e07912612, debate READY 34c8ec06a0e735e8db1c42b90830a23fc166be2cc229b88ea3fbdb89a6350086, sow STOPPED 365dffe29868e07220f854ee3ba8f171f97536b1586877a029d1871bd2931fa9, distillery NOT_STARTED 22657c10927dc526b1cbec58b01f3c2423d9d089ac939cc1e528b796203dbcf0, side-by-side pair cae11564.../951b3e32..., light-mode f408be502845c133079de5c279a18d4ac1a64af0728f900c794bf1cbb48ab360 median_lum 0.913; B-7 DOM fb842c446fa246f76a28b19250025011844f53432837b440dcffbf52d30f83ed; exact Edge commands in FACT[evidence/loop5/g4-edge-commands.txt]; capture-state rows FACT[evidence/loop5/g4-captures.jsonl]; keepruns c9d69d67.../2be117e7... |
| G5 closeout | FACT[evidence/loop5/fs-watch-loop01.txt] b65f015ab290cb6bd3d5f04b9de1ba7df8bfa9d6b95567a5ca193fddb0579cfe events 0, window 07:24Z..16:25Z brackets G1..G4; FACT[evidence/loop5/orphans-after-loop01.txt] a44c0d04d20a3221077268e356f7715de894762359b72a251ec3a22c6f2a67b9 MODULE_PROCESSES NONE + ports free; shell stopped via CTRL_BREAK own path, sentinels cleared |
| G6 ledger 5b | "5b" CANDIDATE, 35 evidence entries all lowercase-sha-matching disk; pre-write snapshot FACT[evidence/loop5/ledger-snap-pre5c.json]; 4c still CANDIDATE; reviewer entries untouched |
| G7 report | this document |

## 4. What the visual set shows

The live shell on the v2 theme renders four cards in contract order with six-action rows; Distillery
Start/Stop/Open/Test disabled in DOM; SOVEREIGN reached READY twice via startup-test keep-runs and was
stopped through its own /api/stop each time (FACT[evidence/loop5/states-timeline.txt]
f76e1a0c4d41420ff282cbf82900a1c641a67f9c99af5ef0aebaa58bcd316d1f shows sow never left STOPPED);
headless Edge default scheme resolves light here (median_lum 0.913) while --force-dark-mode captures
the dark v2 palette (median_lum 0.011).

## 5. Deviations

- D-1..D-4 (G-oracle): goalcheck.py carried four predicates that could not be TRUE against the
  directive's own text or genuine artifacts: the G0 free-now/live-shell conflict, parse_iso rejecting
  7-digit fractional UTC, the B-7 action list naming startup-test instead of the contract's test
  button, shot_ok's sparse-grid sampler under-sampling dark low-chroma renders, g0's liveness probe
  colliding with G5's stopped state, and g3's ignore-set predating 5b. Each fix is logged as its own
  loop-ledger line, was validated empirically (solid-PNG control rejected; real renders accepted), and
  none touched any product file. INTERPRETATION these recalibrated the oracle to the directive's
  stated predicates; they did not weaken them below the directive text.
- D-5: two builder-tool crashes in g4_capture.py (temp-dir ordering) occurred before any citation;
  fixed and superseded before the successful pass; recorded in ledger lines i=2/i=3 notes.

## 6. Open risks (carried)

- Light-theme dot ratios remain as reviewed earlier (RECOMMENDATION unchanged: revisit if the operator
  ever orders a light-first theme).
- H-15 nested-key handling remains as previously reported.
- The fresh baselines now bless the CURRENT SOW dirty set (HEAD e6fcb899..., 3 porcelain entries):
  FACT[evidence/rem03/sow-git-rem03-before.meta.json]. Any future drift is PROTECTED_GIT_STATE_CHANGED
  again; one rebaseline has been spent.

## 7. State

No builder process remains: watcher/poller/shell stopped via their own sentinels and drivers; ports
5175/8700/5180 free; pid sentinels removed by their drivers; nothing transient left as finished work.

BUILDER CLAIM: Gate 4c and Gate 5b are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder.