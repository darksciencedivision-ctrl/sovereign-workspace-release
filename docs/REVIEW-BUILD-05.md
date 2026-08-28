# REVIEW-BUILD-05 — Gate 4b (REM-02) and Gates 0/1 reviewer verdict, SWS-UI-001 v1.2

# utc: 2026-08-22T17:05:00Z
# producer: reviewer (Claude) GATE4B-REVIEW

| Field | Value |
|---|---|
| Subject | `docs/REM-02-REPORT.md` (builder: Ox Alpha), ledger key `"4b"`, Gates 0 and 1 |
| Basis | `docs/REMEDIATION-02.md` sha256 `4cf8b1f66f5d3c06030f08052bb3c000f813b50bfab9f40ceab3cf6afb9f4606`; `docs/OX-ALPHA-DIRECTIVE-GATE4B.md` sha256 `3667973c18b6b3a53c4626cf1dff78a1935b92a3ff41ac89f21e512b1b39286f`; `AGENTS.md` = `CLAUDE.md` sha256 `80c0d4a18cc1fa0c6c3fbab4feab80c6a86b756755d22096ad30ae38ed2c8fc5` |
| Method | Every claim below was recomputed by the reviewer from the workspace on disk (hashes with sha256, diffs against `evidence/gate4b/before/`, H-15 re-executed independently, PNG opened and inspected). Nothing is taken from the builder's report on trust. |
| Verdict | **Gate 4b: PASS. Gate 0: PASS. Gate 1: PASS.** Gates 2, 3 unchanged (PASS). Gate 4 (2026-08-21) superseded for D1–D4 by 4b. Gate 5 remains STOP pending the visual re-run. Gate 6 NOT_REACHED. |

## 1. Authorization root (Gates 0/1)

- `FACT[evidence/OPERATOR-INSTRUCTIONS.log]` contains the operator's sentence verbatim with capture UTC `2026-08-22T01:07:28.4544624Z` (en dash preserved; the hyphen transcription is retained and superseded in-file) and the `D:\Sov 1\` correction at `01:11:48Z`.
- `FACT[AGENTS.md §1(3)]` defines that record as the authorization artifact; no hand-signed box or operator file edit is required.
- `FACT[docs/DECISIONS.md]` sha256 `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a`, unchanged; its content is adopted as written plus the logged correction.
- `FACT[evidence/GATE-LEDGER.json]` Gates 0/1 carry `authorized_by: "operator (session instruction, see evidence/OPERATOR-INSTRUCTIONS.log)"`, `authorized_utc`, original notes and reviewer notes retained. Gates 2–6 were byte-identical to the Gate-5-era ledger before this review's writes.
- Verdict: the authorization is on disk in the form the envelope prescribes. **PASS** both.

## 2. Envelope compliance (REM-02 §2)

| Check | Reviewer result |
|---|---|
| Files changed | `FACT[diff vs evidence/gate4b/before/]` exactly `shell/static/index.html`, `shell/src/server.py`, `shell/static/app.js`, `shell/static/app.css`; plus new `shell/tests/test_render.py`. No other `shell/**` file differs from the Gate-4 manifest. |
| Changed lines | `FACT[evidence/gate4b/linecount.txt]` D1 4 · D2 35+6 · D3 12+19 · D4 4 = **80 / 80**. Reviewer's own unified diffs agree. At the cap, not over it. |
| Route additions | `FACT[shell/src/server.py]` one: `GET /doc/<name>` over a fixed three-entry map; `is_contained` (H-5) applied; `_common_headers()` supplies `nosniff` and the H-3 set; `text/markdown; charset=utf-8`; unknown name, traversal and bare `/doc/` → 404 (`FACT[evidence/hardening/h14-doclinks.txt]`). |
| Tokens | `FACT[shell/static/app.css]` D4 adds four rules inside the light block using only `--text`, `--ok`, `--warning`, `--danger`. No new hex values. |
| Tests per defect | `FACT[shell/tests/test_render.py]` five tests, H-13…H-17, one file. |
| Refactors/cleanup/deps | none observed. |

## 3. Defect verification

- **D1** `FACT[index.html diff]` `href="/static/app.css"`, `src="/static/app.js"`. `FACT[evidence/gate4b/h13-fails-before.txt]` the test failed on the before tree; `FACT[evidence/hardening/h13-assets.txt]` 14 first-party URLs, zero 4xx/5xx except the four POST-only action routes pinned at 404-on-GET per H-2 (accepted, D-b).
- **D2** `FACT[index.html diff]` three header links → `/doc/discovery`, `/doc/theme-baseline`, `/doc/directive`. `FACT[h14-doclinks.txt]` each 200, `text/markdown`, `nosniff`, first line matches the disk file.
- **D3** `FACT[app.js diff]` `loadDistillery()` now reads `data.snapshot.snapshot_id`, `data.questions.open_count` / `open_ids` (rendered as "N (ids…)"), and `data.links` as an object. `FACT[reviewer re-run of the H-15 extraction]` on `before/app.js`: 6 of 9 accessed keys missing from the live payload; on the new `app.js`: 0 missing. The fails-before property holds even though no artifact was mandated for it.
- **D4** `FACT[app.css diff]` light-theme badge text uses `var(--text)`; state colour on the dot only. `FACT[h16-contrast.txt]` every text pairing ≥ 4.5:1 in both themes (light badge text now 16.37:1 on panel). `FACT[evidence/gate4b/h16-fails-before.txt]` failed before at 2.03/2.19/3.65.

## 4. H-13…H-17 artifacts

All five hashes in the builder's report match disk (`4953e204…5065d1c`, `cff323cf…f073c1`, `3822e9ed…03ea1a`, `a5dd2cb9…253d1a3`, `e9466d00…c89ded`). `FACT[evidence/gate5/screenshots/shell-grid-rendered.png]` sha256 `677b1236f97c36ed39b03ffeeb9d20de3f9b7315cb3f7170f3c1a8dceeb6dc1a`; opened by the reviewer: header with the three doc links and clock, pre-flight panel, SOVEREIGN and SOW cards with badges and action rows render. `FACT[h17-dom.txt]` four cards in contract order, six actions each (contract §7.3(2) governs over the order's "five" — D-a accepted), Distillery Start/Stop/Open/Test `disabled`, Logs enabled.

## 5. Closing evidence

- `FACT[evidence/test-run.txt]` README command, `Ran 121 tests`, `OK`.
- `FACT[shell/BUILD-MANIFEST.txt]` regenerated 16:16:04Z; entries for `server.py`, `index.html`, `test_render.py` equal the reviewer's hashes.
- `FACT[evidence/manifests/manifest-4b-*.txt]` sha256-identical to `manifest-before-*.txt` for all three protected roots; `fc` exit 0.
- `FACT[evidence/gate4b/fs-watch-gate4b.txt]` window 01:13:16Z–16:22:54Z, 54,578 s, `events: 0`.
- `FACT[evidence/gate4b/orphans-after.txt]` no module processes, ports 5175/8700/5180 free, builder transients (45020, 39792, 42232) stopped.
- `FACT[docs/REM-02-REPORT.md]` ends with the exact §14 claim line; no forbidden words beside a gate number.

## 6. Findings that do not block

- `INTERPRETATION` H-15's regex only sees `data.snapshot` / `data.questions` / `data.links` in the new code because the nested reads go through local variables; the nested keys (`snapshot_id`, `open_count`, `open_ids`) were verified by the reviewer against the live payload, not by the test. A future payload rename below the top level would pass H-15 and fail visually; H-17 would not catch it either. Carried as a hardening gap, not a defect.
- `INTERPRETATION` Light-theme `--ok`/`--warning` dots stay at 2.03/2.19:1 on white (non-text target 3:1). The baseline token set cannot reach 3:1 without a new colour, which REM-02 forbids. Recorded honestly; accepted as an open risk for the operator, not waived.
- `FACT[h17-dom.txt]` The rendered screenshot shows pre-flight `0/7 available` because the H-17 shell instance runs inside the test harness on an ephemeral port; it is not a statement about the host. Gate 5's `preflight.json` remains the host record.
- `FACT[evidence/gate4b/fs-watch-gate4b.txt]` header comment names the Gate 5 driver path (builder's D-f). Cosmetic.
- Process: the builder lost ~14 h to a tool call blocked on the detached-by-design watcher; recovered cleanly, watcher kept, window unbroken. `RECOMMENDATION` future work orders state explicitly that long-running helpers must be started detached.

## 7. Ledger writes made by this review

`evidence/GATE-LEDGER.json`: `"0"` → PASS, `"1"` → PASS, `"4b"` → PASS, each with `evaluated_by: "reviewer"`, `evaluated_utc`, and a reviewer note; every other gate entry byte-identical. Post-write sha256 recorded in the session report.

## 8. Next step (no operator file edit required)

Gate 5 visual re-run per `docs/OX-ALPHA-DIRECTIVE-GATE5.md` and REM-02 §4 step 5: A-5/B-4 card screenshots, B-7 live-DOM, B-8 side-by-side with SOVEREIGN, `shell-light-mode.png`, then Gate 5 → CANDIDATE. The stage-pause waiver already logged at 01:07:28Z covers it; the operator's go-ahead sentence is given in session and logged by the builder as before.

REVIEWER VERDICT: Gate 4b PASS; Gates 0 and 1 PASS. Gate 5 STOP stands until the visual re-run is submitted. Gate 6 NOT_REACHED.
