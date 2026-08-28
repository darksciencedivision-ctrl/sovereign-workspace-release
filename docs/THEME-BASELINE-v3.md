# utc: 2026-08-25T04:05:12Z
# producer: ox-alpha THEME01

# THEME-BASELINE v3 — SOVEREIGN identity palette (THEME-01), SWS-UI-001 v1.2

| Field | Value |
|---|---|
| Status | Active baseline on completion of THEME-01 G2. Supersedes docs/THEME-BASELINE-v2.md (preserved byte-identical, sha256 35311af375186654820866119ac6bfbbaeb8cfe88c8803ad5a86130204e1ba5b), which superseded docs/THEME-BASELINE.md v1. |
| Authority | docs/OX-ALPHA-DIRECTIVE-THEME-01.md §3, operator session instruction logged verbatim in evidence/OPERATOR-INSTRUCTIONS.log at 2026-08-25T03:52:11.4027714Z. Palette selections are operator decisions; ratios recomputed by the builder and by the loop oracle (evidence/theme01/goalcheck-*.txt, PINNED-RATIOS: 0 disagree). |
| Effect | D1 (one design, two surface levels) and D2 (accent = SOVEREIGN ice-blue) repaired; supersedes the REM-03 --accent decision only. Every other REM-03 token decision, including --text-muted #9aa7bd, stands unchanged. |

## Dark tokens (:root) — §3.1

| Token | Value | Change vs v2 | Measured ratio |
|---|---|---|---|
| --bg | #0b0e14 | unchanged | — |
| --panel | #151b28 | unchanged | — |
| --sidebar | #0d121c | unchanged | — |
| --input | #1b2333 | unchanged | — |
| --border | #232b3a | unchanged | — |
| --text | #c7d1de | unchanged | 12.51 on bg; 11.16 on panel |
| --text-muted | #9aa7bd | unchanged (REM-03 operator decision stands) | 7.08 on panel |
| --text-faint | #3a4353 | unchanged | 1.73 on panel — recorded, not asserted (§3.4 carry, below) |
| --accent | #7fc8e8 | from #bb9af7 | 10.42 on bg; 9.29 on panel |
| --accent-dim | #2a4a5c | from #3a2f57 | text on it = 6.09 |
| --ok | #9ece6a | unchanged | 9.42 on panel |
| --warning | #e0af68 | unchanged | 8.61 on panel |
| --danger | #f7768e | unchanged | 6.51 on panel |
| --radius / --font / --mono | carried from v2 | unchanged | — |

## Light tokens (@media prefers-color-scheme: light) — §3.2, same design at a second surface level

Measured against --panel #ffffff unless noted.

| Token | Value | Change vs v2 | Measured ratio |
|---|---|---|---|
| --bg | #f4f5f7 | unchanged | — |
| --panel | #ffffff | unchanged | — |
| --sidebar | #eceef1 | unchanged | — |
| --border | #d3d8e0 | unchanged | — |
| --text | #1b2027 | unchanged | 16.37 |
| --text-muted | #58616e | unchanged | 6.27 |
| --text-faint | #8a93a1 | unchanged | 3.10 — recorded, not asserted (§3.4 carry, below) |
| --accent | #1f6f94 | from #8a744a | 5.59 on panel; 5.12 on bg; white on it = 5.59 |
| --accent-dim | #a8d6ea | from #a68b58 | text on it = 10.50 |
| --ok | #2f7a49 | new light override | 5.25 on panel; 4.81 on bg |
| --warning | #8a6008 | new light override | 5.59 on panel; 5.12 on bg |
| --danger | #c8394f | new light override | 5.06 on panel; 4.63 on bg |

#1f6f94 is the darkened member of the #7fc8e8 ice-blue hue family, cleared to 4.5:1 as text on white. Dark and light are one identity at two surface levels.

## §3.3 rule-set decision — light block content

The light block contains custom-property overrides only. The four selector rules REM-02 D4 added inside the light block (badge text demoted to var(--text); per-state .dot background/border re-declarations) existed only to work around v1/v2 light --ok/--warning/--danger measuring 1.83/2.00/2.65:1 on white. With the §3.2 status tokens all clearing 4.5:1, those values no longer exist and the rules are deleted outright. justified-rules: none — no selector rule is retained inside the light media block.

H-16 is strengthened in the same change: all six C-2 pairs are asserted >= 4.5:1 as TEXT in both themes (12 rows); the glyph branch no longer excuses light ok/warning/danger. This retires the reviewer standing contrast finding from REVIEW-BUILD-05 §6 and REVIEW-BUILD-06 §4 instead of carrying it forward.

## §3.4 out-of-scope carry — --text-faint

--text-faint (#3a4353 dark / #8a93a1 light) measures 1.73:1 and 3.10:1 on its panel and sits below 4.5:1 in both themes today, exactly as it did through Gate 6. It is out of scope for this loop (directive §3.4): it is NOT changed here, it stays recorded in evidence/hardening/h16-contrast.txt so it remains visible rather than hidden, and widening into it would be ENVELOPE_EXCEEDED. Changing it requires a separate directive.

## Scope note

Per directive §5 this baseline changes ONLY the token values above plus deletion of the §3.3 workaround rules in shell/static/app.css. Layout, markup, JS behavior outside pre-flight resolution, server routes beyond the D3 doc-map entry, dependencies, and every other rule are out of scope.
