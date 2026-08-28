# Audit B — candidate-gate evidence

## Method

I parsed `evidence/GATE-LEDGER.json`, selected gates `7a`, `7b`, `8a`–`8j`, and `9c`–`9j`, and recomputed `SHA256(path)` for every evidence row. Full 64-hex comparison was used; no console truncation was used as evidence.

Command (PowerShell-hosted Python 3.12): parse the ledger, iterate each candidate gate's `evidence`, resolve each `path` below the workspace, hash with `hashlib.sha256`, and report missing/drift counts. Output:

```text
7a evidence=17 missing=0 drift=6
7b evidence=15 missing=0 drift=4
8a evidence=33 missing=0 drift=0
8b evidence=28 missing=0 drift=0
8c evidence=19 missing=0 drift=0
8d evidence=9  missing=0 drift=0
8e evidence=4  missing=0 drift=0
8f evidence=4  missing=0 drift=0
8g evidence=4  missing=0 drift=0
8h evidence=5  missing=0 drift=0
8i evidence=5  missing=0 drift=0
8j evidence=4  missing=0 drift=0
9c evidence=5  missing=0 drift=0
9d evidence=5  missing=0 drift=0
9e evidence=3  missing=0 drift=0
9f evidence=3  missing=0 drift=0
9g evidence=3  missing=0 drift=0
9h evidence=3  missing=0 drift=0
9j evidence=7  missing=0 drift=0
```

The ten live-path hash drifts are:

| Gate | Path | Ledger SHA-256 | Recomputed SHA-256 |
|---|---|---|---|
| 7a | `shell/static/app.css` | `82a85c50928246b279498376508176924509916572a1337f618ea04f72e97a36` | `2e9deb652a845b48cf72580890818540142325de79bd637254548c6c92516fc9` |
| 7a | `evidence/hardening/h16-contrast.txt` | `35722ddb261f872a36358338ac189a05029120764b2ba93475394ec903f67005` | `a3f371212476e4d2e5b9471227c61cb7810cf1014edcc3ccf853d45b72056b73` |
| 7a | `evidence/hardening/h14-doclinks.txt` | `50c1582fafc5d088899e11c380390334648094ed743619891304928fcd7833d6` | `a9622457c36b31c24656483f34685cb59e51ba9ff7a73074ff953d48caf77551` |
| 7a | `evidence/test-run.txt` | `da402eafc5c688a333510f0d22e7d9731253467173228669a17263a04aa3fbf0` | `5852eb9fa8dc84d25df0430ac2159567104a3836395695e5c796e0a52e04a98b` |
| 7a | `shell/BUILD-MANIFEST.txt` | `6ebc05edba4fe6857b1438166b39ee2386af1c2cbe867966368e207841289706` | `c7ca80ed9b90c29d8d5b7cdab0ad037713bc0c3d79e4fc9ffec98ce6c52aa59b` |
| 7a | `evidence/OPERATOR-INSTRUCTIONS.log` | `17d7b2e1246dac0cbbbe4296896b2b3f7a2189d28ab71e29e72e36c28908af45` | `1e99fa646790798394eb05bf65fcc3eb53b86b6d43ec5d9587d58d8e9dd89c7e` |
| 7b | `shell/static/app.js` | `8f0f395e7c435845532363a4caef3dfcc0269079c9604a19bbb4a2fc1ea5a534` | `487c1e99d0fe09e2a2dd6e90f1d46a164873232ee994a4c398220998242541c4` |
| 7b | `evidence/test-run.txt` | `da402eafc5c688a333510f0d22e7d9731253467173228669a17263a04aa3fbf0` | `5852eb9fa8dc84d25df0430ac2159567104a3836395695e5c796e0a52e04a98b` |
| 7b | `shell/BUILD-MANIFEST.txt` | `6ebc05edba4fe6857b1438166b39ee2386af1c2cbe867966368e207841289706` | `c7ca80ed9b90c29d8d5b7cdab0ad037713bc0c3d79e4fc9ffec98ce6c52aa59b` |
| 7b | `evidence/OPERATOR-INSTRUCTIONS.log` | `17d7b2e1246dac0cbbbe4296896b2b3f7a2189d28ab71e29e72e36c28908af45` | `1e99fa646790798394eb05bf65fcc3eb53b86b6d43ec5d9587d58d8e9dd89c7e` |

`evidence/GATE-LEDGER.json:956` and `:1045` are the 7a/7b objects. All later candidate objects' recorded hashes currently verify, but that does not cure mutable-path evidence.

## E-7c freeze check

E-7c requires gate evidence to point at gate-local frozen copies, not a live path that later stages can mutate (`docs/SWS-UI-001-v1.2-ADDENDUM-04.md:46`). The following candidate evidence entries use mutable paths:

```text
7a: shell/static/app.css; evidence/test-run.txt; shell/BUILD-MANIFEST.txt; evidence/OPERATOR-INSTRUCTIONS.log
7b: modules/sow/tools/live/probe.py; shell/static/app.js; shell/tests/test_shell.py; evidence/test-run.txt; shell/BUILD-MANIFEST.txt; evidence/OPERATOR-INSTRUCTIONS.log
8a: docs/CP-MAP-01.md; evidence/cpm1/tools/goalcheck.py
8b: four live shell test/fixture files
8c: three live test files; worker-spawn-selfcheck.js; worker-spawn.js; main.js
8h: shell/modules/distillery.json
8i: shell/modules/tokencenter.json
8j: docs/CP-M1-REPORT.md
9c: modules/sow/adapters/base/backend.py
9e: modules/sow/schemas/deployment-manifest.schema.json
9g: shell/src/logring.py; modules/sow/adapters/local/llamacpp.py
9j: docs/CP-M1-REPORT.md; evidence/cpm1/linecount-b.txt
```

Gate 8d is the clean example: all nine entries resolve below `evidence/cpm1/8d/frozen/`. The other listed gates do not fully comply with E-7c even when their current hashes happen to match.

## Status and missing gates

Every gate in scope is `CANDIDATE` and `evaluated_by` is null. The only `PASS` values in the entire ledger are historical gates `0,1,2,3,4,4b,4c,5b,6` (`evidence/GATE-LEDGER.json:7,38,85,137,209,579,593,760,803`). No candidate gate reads PASS.

Ledger keys 9a and 9b are absent. The ledger itself says why: `evidence/GATE-LEDGER.json:1905` — `"9a/9b not submitted (llama.cpp live legs NOT_RUN)."` Directory `evidence/cpm1/9a/` nevertheless contains five preparatory files (`a1-version.txt`, `gguf-provenance.txt`, `gguf-stage.txt`, `ollama-after.txt`, `pin.txt`); `evidence/cpm1/9b/` is absent. The closing statement `docs/CP-M1-REPORT.md:160` says “9a through 9j are CANDIDATEs,” overstating the ledger by two gates.

**Verdict:** evidence hashes are clean for 8a–8j and 9c–9j at audit time, but 7a/7b have ten live drifts and E-7c is violated across multiple gates. Gate 9a/9b absence is correctly recorded in the ledger and incorrectly summarized in the closing report.
