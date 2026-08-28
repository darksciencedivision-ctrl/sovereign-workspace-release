# REM-04 REPORT - THEME-01 visual identity repair (ledger keys 7a, 7b), SWS-UI-001 v1.2

# utc: 2026-08-25T04:25:14Z
# producer: ox-alpha REM04/THEME01

## 0. Executive summary

FACT[evidence/OPERATOR-INSTRUCTIONS.log entry 2026-08-25T03:52:11.4027714Z] The operator authorized THEME-01 verbatim in session; an identical sentence logged by a paused earlier session (03:28:19Z) carried a stale "directive not found" note, superseded append-only in that entry. FACT[docs/OX-ALPHA-DIRECTIVE-THEME-01.md] The work order defines goals G0-G11 and a 162-line product envelope. FACT[evidence/theme01/LOOP-LEDGER.jsonl] The loop ran 14 iterations with no repeated stalled action; the oracle now reports G0-G11 all TRUE, zero STOP markers. FACT[evidence/theme01/goalcheck-11.txt] All 22 pinned section-3 contrast ratios reproduce exactly. INTERPRETATION Gates 7a (theme: D1-D3) and 7b (pre-flight: D4) are submitted as CANDIDATEs below. FACT Gate 6 stays PASS untouched; every pre-existing ledger entry is byte-identical to the pre-write snapshot.

## 1. Authorization and conduct

- FACT Authorization root: operator instruction logged verbatim with UTC 2026-08-25T03:52:11.4027714Z.
- FACT Verify-act-verify ran via the read-only oracle evidence/theme01/tools/goalcheck.py; three oracle defects were fixed mid-loop, each a loop-ledger line with goal G-oracle; no goal predicate was ever weakened (the one G0 correction accepts either the pinned session-start hash or proven append-only growth from the G0 snapshot - same meaning across the authorized ledger write).
- FACT Single-writer checks at start and before the ledger write found no concurrent writer.
- FACT Launch discipline per AGENTS.md section 9 held throughout: absolute interpreter path + argv array + PYTHONDONTWRITEBYTECODE=1 for every shell start; CTRL_BREAK own-path stops; modules never launched by hand.

## 2. Defect verdicts

| ID | Verdict | Proof |
|---|---|---|
| D1 | CONFIRMED and repaired | FACT[evidence/theme01/baseline.txt] gold-vs-violet confirmed on disk and in before-captures. FACT[shell/static/app.css] light block is custom-property overrides only - same design at surface level 2. |
| D2 | CONFIRMED and repaired | FACT[shell/static/app.css] :root --accent #bb9af7 to #7fc8e8, --accent-dim #3a2f57 to #2a4a5c. Supersedes the REM-03 accent decision only; --text-muted #9aa7bd stands. |
| D3 | CONFIRMED and repaired | FACT[shell/src/server.py] doc map serves docs/THEME-BASELINE-v3.md. FACT[evidence/hardening/h14-doclinks.txt] /doc/theme-baseline returns 200 text/markdown nosniff serving THEME-BASELINE-v3.md, first line matching disk. |
| D4 | CONFIRMED and repaired | FACT[evidence/theme01/before/preflight-dom.txt] panel rendered "0/7 available" live before. FACT[evidence/theme01/after/preflight-live.json] all seven ids resolve server-side per directive section 4.1 with port_5180 inverted (ok/shell). FACT[evidence/theme01/after/preflight-dom.txt] live panel reads "5/7 available" with both unavailable ids named in its annotation. |

## 3. Changed files vs the section-5 envelope

| File | Before sha256 | After sha256 | Changed lines / cap |
|---|---|---|---|
| shell/static/app.css | 329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab | 82a85cdfea3498662849e71da50ea3b0a0705bfc594561c1a75a927ac769693a | 15 / 60 |
| shell/static/app.js | 5b2e9daba91188869ed241fe912d1a99685130e757e9b6424883e0d8b597e422 | 8f0fa6ff3973a110921ed006bfb09363a27817999cb6b94834ff1372ebc0bcf3 | 2 / 40 |
| shell/src/probe.py | 607f3b76f90f8ac56790c4a8e48e33364e2b576a6de491c5f365c3226831065f | f0df2775936f8bb3583304cadefa9d83b295ff932d47d13dcfe6f9327d7f0643 | 48 / 60 |
| shell/src/server.py | 2d97d170ebddc25ae125fe68fffccbc38bfffe3c878a945822db524f21227532 | 110697e683d554aed09da5b25b374030b7197564727ca09c623d2d16f32b71af | 2 / 2 |

FACT[evidence/theme01/linecount.txt] Total capped product lines 67 of 162 absolute, computed by difflib unified diff against the before snapshots (not hand-tallied). FACT Test code changed (uncapped): test_render.py (H-14 mapping/format, H-16 rewritten, producer tag), test_shell.py (pre-flight contract updated, new end-to-end regression test). ASSUMPTION[falsifier: rerun difflib] counts reflect the final tree.

## 4. Tests - fail-before / pass-after

| Test | Fails before | Passes after |
|---|---|---|
| H-16 strengthened: six C-2 pairs TEXT >= 4.5:1 both themes | FACT[evidence/theme01/h16-fails-before.txt] on pre-change CSS: light ok/warning/danger 1.83/2.00/2.65 | FACT[evidence/hardening/h16-contrast.txt] 12 TEXT OK rows + faint/accent-dim RECORDED rows |
| test_preflight_panel_ids_resolved (new, through /api/preflight) | FACT[evidence/theme01/g7-preflight-fails-before.txt] all seven ids missing from payload.checks | passes against a live shell; statuses limited to ok/bad, details non-empty |
| test_get_preflight (contract updated to resolved checks) | same artifact | passes after |

FACT[evidence/test-run.txt] Full README suite after all product edits: Ran 122 tests in 91.406s, OK (121 before this loop).

## 5. Retired finding and carries

- RETIRED: "light --ok/--warning dots remain below WCAG non-text 3:1" (REVIEW-BUILD-05 s6, REVIEW-BUILD-06 s4). FACT Section 3.2 light status tokens measure 5.25/5.59/5.06:1 on white and are asserted as text pairs; the four REM-02 workaround selector rules are deleted and the glyph exception retires.
- CARRIED (--text-faint): 1.73:1 dark, 3.10:1 light on panel; unchanged per directive section 3.4; visible as RECORDED rows in evidence/hardening/h16-contrast.txt and stated in docs/THEME-BASELINE-v3.md.
- CARRIED (H-15): Distillery contract test still verifies top-level keys only; nested-key limits remain as the reviewer noted. Out of scope here.
- CARRIED (npm): absent from the shell PATH (WinError 2), reported truthfully bad; nothing was installed or reconfigured (directive section 9, AGENTS.md section 7).
- CARRIED (port_8700): occupied by the operator-side Debate Table instance pid 52968 (D:\Debate table\app.py), predating this session; truthful bad "in use"; untouched.

## 6. Visual evidence, both themes

FACT[evidence/theme01/after/edge-commands.txt] exact msedge commands recorded; dark used --force-dark-mode, light omitted it (loop5 convention). FACT[evidence/theme01/after/grid-dark.png] median luminance 0.007 with #7fc8e8 accent pixels present; compare FACT[evidence/theme01/before/grid-dark.png] violet pre-change. FACT[evidence/theme01/after/grid-light.png] median luminance 0.980 with #1f6f94 accent present; compare FACT[evidence/theme01/before/grid-light.png] gold-on-white pre-change.

## 7. Ledger write

FACT[evidence/theme01/ledger-snap-pre7.json] equals the G0-pinned ledger sha256 518ac84ce6a2b55b0c2d2f0bdcbd4dcd64886669012e1354432c28df6ef28085. FACT The write appended keys "7a"/"7b" only: byte-prefix preserved, every prior gate deep-equal post-write, post-write file sha256 176429fc4012ce57c1a19558e7aaed55e7f37ca268be0fdd067996fe79b8fc77. FACT Both keys carry status CANDIDATE with lowercase full sha256 for every cited artifact; no PASS written anywhere.

## 8. Goal table

| Goal | Meaning | Proof |
|---|---|---|
| G0 | session precondition | `evidence/theme01/session-start.txt` sha256 `5971042d7ea0833af26c513de3f6db72215f3eddaf19c3b3d9a60d75b2227c0c` |
| G1 | pre-change baseline | `evidence/theme01/baseline.txt` sha256 `f826b89c5acc849048abe122ef98e006cf83c48dde726ba0c84ae9ab4fa3398e`; `evidence/theme01/before/app.css.snapshot` sha256 `329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab` |
| G2 | baseline v3 pinned | `docs/THEME-BASELINE-v3.md` sha256 `114fe5f6b0666ce7d2cea29bb30650f21e2aa9eed76c9bb3e35babdb54236969` |
| G3+G4 | dark+light tokens applied | `shell/static/app.css` sha256 `82a85cdfea3498662849e71da50ea3b0a0705bfc594561c1a75a927ac769693a`; oracle `evidence/theme01/goalcheck-11.txt` sha256 `42a5c308f8463ffc8f5e3a3b61688f17870ecb9ace97c56eecc520494e48b61c` |
| G5 | contrast asserted | `evidence/hardening/h16-contrast.txt` sha256 `3572f78d4629c9f9f0fa1255e9f7935ceff4b62b17aa60ba6dac6f59aeaf8f26`; fails-before `evidence/theme01/h16-fails-before.txt` sha256 `f259c6c53c982df35fae5c0a27652d06b615d1ec017a0376f369c48f3cff8bfc` |
| G6 | D3 repaired | `shell/src/server.py` sha256 `110697e683d554aed09da5b25b374030b7197564727ca09c623d2d16f32b71af`; `evidence/hardening/h14-doclinks.txt` sha256 `50c16898d351b8951dfb01f7776c1900dbfcf91364a192bee5326d4ad7cd6f9b` |
| G7 | D4 repaired and proved | `evidence/theme01/after/preflight-live.json` sha256 `d4f3e6221ad34555dca2d7e449e6b348a434ca60ba57e2401fe216c0ad708eec`; fails-before `evidence/theme01/g7-preflight-fails-before.txt` sha256 `6ebfd0f3d52df85507d503a1059a774ec8f8f1bc00b7f7a4ee5c95eb565287c2`; DOM `evidence/theme01/after/preflight-dom.txt` sha256 `657bec224d404166f93dba532a158249845d02be3894ccf17aa8dd121a6d56d9` |
| G8 | suite green | `evidence/test-run.txt` sha256 `da4027424759c12ad7797558984e13940f18462f7c4a9d56bb0cae03bc40508d`; `shell/BUILD-MANIFEST.txt` sha256 `6ebc420e59c6ed33f9563817a7c2f61bbb77a95e12de463bb4b319111745235e` |
| G9 | visual proof both themes | `evidence/theme01/after/grid-dark.png` sha256 `208eaa4e03a246f4994a1215eef2a98dbdec7f65f6934d7cc21761286f4a67b1`; `evidence/theme01/after/grid-light.png` sha256 `f80dcc0d60ed1bc23ad6b858d2315e448c4747e00f2163fb9a3882f384058fee`; commands `evidence/theme01/after/edge-commands.txt` sha256 `5e0b14a04ecc55fe47f7e234fe7e80b83f7626c2b8149e38bdac2a627d62f214` |
| G10 | ledger 7a/7b CANDIDATE | `evidence/GATE-LEDGER.json` post-write sha256 `176429fc4012ce57c1a19558e7aaed55e7f37ca268be0fdd067996fe79b8fc77`; pre-write snapshot `evidence/theme01/ledger-snap-pre7.json` sha256 `518ac84ce6a2b55b0c2d2f0bdcbd4dcd64886669012e1354432c28df6ef28085` |
| G11 | report and closeout | `evidence/theme01/orphans-after.txt` sha256 `9e22c90eb70eb62715cd4ae027a3612da41b1e9c39211844f8b6552635484f0b` |

## 9. Closeout

FACT[evidence/theme01/orphans-after.txt] every capture session stopped the shell through its own CTRL_BREAK path; zero workspace module processes remain; ports 5175 and 5180 free at close (8700 operator-side as above). FACT Product version string remains SWS-UI-001 v1.2, unchanged. RECOMMENDATION Reviewer evaluation of 7a and 7b against docs/OX-ALPHA-DIRECTIVE-THEME-01.md; promotion and any dist/ re-cut remain the operator's.

BUILDER CLAIM: Gate 7a and Gate 7b are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder.
