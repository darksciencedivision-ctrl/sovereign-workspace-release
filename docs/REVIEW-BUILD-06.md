# REVIEW-BUILD-06 — Gate 4c and Gate 5b reviewer verdict, SWS-UI-001 v1.2

# utc: 2026-08-24T17:20:00Z
# producer: reviewer (Claude) LOOP-01-REVIEW

| Field | Value |
|---|---|
| Subject | `docs/REM-03-REPORT.md` (builder: Ox Alpha, LOOP-01), ledger keys `"4c"` and `"5b"` |
| Basis | `docs/REMEDIATION-03.md`, `docs/OX-ALPHA-DIRECTIVE-LOOP-01.md`, `docs/THEME-BASELINE-v2.md`, operator instruction logged 2026-08-24T06:42:39Z |
| Method | Every claim recomputed by the reviewer from disk: hashes with sha256, ledger byte-prefix comparison against the builder's own pre-write snapshot, independent inspection of the goalcheck oracle's six corrections, and **the PNGs opened and looked at** — not accepted on hash alone. |
| Verdict | **Gate 4c: PASS. Gate 5b: PASS.** Gates 0–4b unchanged (PASS). Gate 5 (2026-08-22 STOP) superseded by 5b. Gate 6 NOT_REACHED — the operator's promotion. |

## 1. Gate 4c — theme re-pin

- `FACT[shell/static/app.css]` sha256 `329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab` — the pinned v2 value, unchanged since REM-03 T2.
- `FACT[evidence/test-run.txt]` sha256 `d361f9bf…91d00`, `Ran 121 tests`, `OK`, run after the G1 baselines.
- `FACT[shell/BUILD-MANIFEST.txt]` 40 of 40 entries equal live file hashes.
- `FACT[evidence/GATE-LEDGER.json]` `"4c"` carries 7 evidence entries; all 7 hashes match disk, none missing.
- `FACT` The 38,106-byte prefix preceding the `"4c"` key is byte-identical to `evidence/loop5/ledger-snap-pre4c.json` — every reviewer-evaluated entry is untouched.
- `INTERPRETATION` The v2 tokens are visibly in effect: the captures render near-black ground, violet accent, monospace throughout, which is what the operator asked for.

## 2. Gate 5b — visual evidence on v2

Verified by opening the images, per the H-17 rule that closed the Gate-4 render gap:

- `FACT[card-sovereign-READY.png]` The grid renders four cards in contract order, six actions each, SOVEREIGN showing a live green **Ready** badge; `g4-captures.jsonl` records `api_state: READY` at 16:21:09Z for that file.
- `FACT[side-by-side-sovereign-module.png]` Genuine SOVEREIGN 3.1.2 UI, "Engine connected · Local-only" — the keep-run reached a real running module, and the timeline shows it stopped afterwards through `/api/stop`.
- `FACT[shell-light-mode.png]` Decodes light (median luminance 0.913) and renders the full grid.
- `FACT[screenshots/b7-dom.txt]` Four cards; six actions per card (`start, stop, restart, open, test, logs`); Distillery Start/Stop/Restart/Open/Test all `disabled` with reason titles, Logs enabled; Distillery card shows snapshot id and `9 (OQ-001 … OQ-009)` — D3 behaviour intact on v2.
- `FACT[evidence/loop5/fs-watch-loop01.txt]` window 07:24:00Z–16:25:55Z, 32,515 s, `events: 0`, bracketing G1 through G4.
- `FACT[evidence/rem03/quiescence-inspect-1/2.txt]` 127 s apart, bodies identical; REM-03 baselines name each superseded original and its hash; originals verified byte-untouched.
- `FACT[evidence/GATE-LEDGER.json]` `"5b"` carries 35 evidence entries; all 35 hashes match disk, none missing.

## 3. The oracle corrections — reviewed individually

A builder that edits its own test until it passes is the failure mode this design exists to catch. All six edits were examined:

| # | Change | Verdict |
|---|---|---|
| 1 | G0 port predicate: 5180 "free now" vs the required live shell | **Reviewer's defect.** My G0 demanded free ports while the loop demands a running shell. Fix keeps 5175/8700 strict and accepts 5180 only when the shell's own stdout proves it held the port. Not a weakening. |
| 2 | `parse_iso` truncating 7-digit fractional seconds | Genuine bug — PowerShell emits 7 digits, `%f` takes 6. |
| 7 | B-7 action tuple `startup-test` → `test` | Oracle was wrong; the DOM uses `data-action="test"`. Reviewer confirmed independently in `b7-dom.txt`. |
| 8 | `shot_ok` sparse 6×6 grid → dense pixel walk | **Stronger**, same ≥8-colour threshold; validated against a solid-PNG control. |
| 11 | G0 evaluated from persisted records of detached operation | **Reviewer's defect.** My G0 (helpers alive) and G5 (helpers stopped) cannot both be true at the final check. Substituting proof-of-having-run — fs-watch artifact, >1000 timeline rows, shell listening line — is the correct resolution. |
| 13 | G3 ignore-set extended to `5b` | Mechanical and correct. |

`INTERPRETATION` None weakened a substantive claim; two fixed defects in my own goal definitions. The loop ledger records each as its own iteration rather than folding them into the goals they unblocked, which is the honest presentation.

## 4. Findings carried to the operator — none blocking

- `FACT[shell/static/app.css]` **Light and dark themes no longer match each other.** REM-03 §1 T2 deliberately left the light block on the v1 SOVEREIGN tokens because SOW has no light theme, so a viewer whose OS is set to light gets the old gold-on-white look while dark gets SOW's violet-on-black. Authorized, but the operator should decide whether to pin a light variant.
- `FACT[all captures]` The pre-flight panel reads **0/7 available** with every dot unknown, in each capture, while Ollama is demonstrably listening on 11434. This may be a genuine defect in the pre-flight probe. It is out of 4c/5b scope (both concern the token swap and its evidence) and predates them, but I am raising it rather than letting it pass silently — the Gate-4 render gap started the same way.
- `FACT[evidence/hardening/h16-contrast.txt]` Light-theme `--ok`/`--warning` dots remain below WCAG non-text 3:1. Unchanged carry.
- `INTERPRETATION` H-15 verifies only top-level payload keys; nested renames would pass. Unchanged carry.
- `FACT[evidence/rem03/]` The REM-03 SOW baseline was captured against a dirty working tree (3 entries, HEAD `e6fcb899`), which option 2 permits. Future C-3/C-4 comparisons are against that state. The one authorized rebaseline is now spent.
- Cosmetic: a supersede header reads `manifest-before-sow.txt.txt`. The recorded original hash is correct.

## 5. Ledger writes made by this review

`evidence/GATE-LEDGER.json`: `"4c"` → PASS, `"5b"` → PASS, each with `evaluated_by: "reviewer"`, `evaluated_utc`, and a reviewer note. Pre-write copy preserved at `evidence/loop5/ledger-snap-pre-review06.json`. Post-write sha256 `a0b22ec40fe32e85b2fe6459ffb72033b56b18a64f365d11988c9764091b4434`. Every other entry byte-identical.

## 6. Next step

Gate 6 is the operator's promotion and requires no file edit — one sentence in session, logged verbatim by the builder.

REVIEWER VERDICT: Gate 4c PASS; Gate 5b PASS. Gate 6 NOT_REACHED, awaiting operator promotion.
