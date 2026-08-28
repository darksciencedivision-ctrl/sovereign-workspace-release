# STOP REPORT REM-03 — SOW-verbatim muted text fails the H-16 4.5:1 text assertion
#
# utc: 2026-08-22T21:28:47.3023872Z
# producer: ox-alpha REM03

## 1. Condition (FACT)

- FACT[evidence/rem03/sow-token-extraction.txt] T1 extraction: SOW's renderer theme is the
  embedded <style> block in pps\desktop\renderer\index.html (sha256
  cb30769491a928f74ace92519cd97848a387f7efa09e39434b01b934f9ba4a3, lines 8-189). The live tree
  has no .css theme file. SOW's muted-text colour, used for .card .k, .rc-meta, #minimized,
  .dim, status-bar labels and idle chips, is verbatim #6b7687 (index.html:19,30,82,87,92,96,123).
- FACT[evidence/rem03/contrast-preview.txt] computed with the same WCAG formula as
  shell/tests/test_render.py::test_light_theme_contrast (H-16), BEFORE any edit:
  dark --text-muted #6b7687 on --panel #151b28 = **3.75:1** (on --bg #0b0e14: 4.20:1).
  Every other proposed v2 pairing passes its assertion (text 6.51-12.51:1; light block unchanged).
- FACT[shell/tests/test_render.py:322,338-343] H-16 asserts the pair set including
  ("text-muted","panel") at >= 4.5:1 in both themes. This is reviewer-verified Gate-4b evidence.

## 2. Exact requirement conflict

REM-03 §1 T2 pins --text-muted to SOW's verbatim muted value (#6b7687); REM-03 §1 T3 requires
H-16 to pass >= 4.5:1 on the v2 values and says: "If a SOW-verbatim pairing fails, STOP and report
the exact ratio — do not pick a different hex." Both cannot hold: applying T2 makes T3 fail at
3.75:1. The operator's live instruction repeats this verbatim ("STOP with the ratio — do not invent
a hex"). Choosing any other hex myself — including a brighter SOW colour such as #9aa7bd — is
exactly what the order forbids, so work stopped here.

## 3. State on disk (no unauthorized implementation)

- shell/static/app.css is UNTOUCHED: sha256 13875bf113d8a0e68e97303fafb674d9ddd89d773dca6f30b8738ad59f505037,
  byte-identical to its Gate-4b PASS state cited in evidence/GATE-LEDGER.json. The <= 40-line
  envelope was never opened; no other shell/** file changed.
- docs/THEME-BASELINE-v2.md NOT written: pinning a baseline whose required pairing provably fails
  would create a self-contradicting artifact. The full extraction with file:line cites stands as
  FACT[evidence/rem03/sow-token-extraction.txt].
- Gate "5b" was not written; Gate 5 remains at its existing reviewer STOP entry. The v1-theme
  visual captures taken earlier today are preserved but uncited (superseded by the operator's
  resequencing instruction of 2026-08-22T21:12Z).

## 4. Bounded operator options

1. **Name an alternative SOW-verbatim muted hex by new instruction.** Measured ratios against the
   v2 panel/bg: #9aa7bd (sb-prov/.ins-sum secondary text) 7.08/7.94 - #8a97a3
   (.cdispatch.unavailable) 5.77/6.47 - #8b93a3 (.cvoice.probing) 5.58/6.26. Any one of these
   passes H-16 unmodified. A one-line operator instruction naming the choice lets T1-T3 complete.
2. **Amend H-16's threshold or pair list by separate order** (REM-03 §2 already says a test change
   needs its own order). Accepting 3.75:1 for muted labels is an accessibility decision only the
   operator can make; it would be recorded honestly in h16-contrast.txt and the reports.
3. **Withdraw/park REM-03 and direct completion of the Gate 5 visual re-run on the v1 theme.**
   All v1-theme visual evidence except the B-7 DOM artifact was captured today and is preserved;
   B-7 is quick to finish, after which Gate 5 goes CANDIDATE exactly per the original work order.

## 5. Closeout

Session closed down per AGENTS.md §14 after the stop: shell stopped via its own shutdown path,
poller and watcher sentinels honoured, orphans checked, ports verified free. See
FACT[evidence/gate5/orphans-after-gate5b.txt] and FACT[evidence/gate5/fs-watch-gate5b.txt].

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.