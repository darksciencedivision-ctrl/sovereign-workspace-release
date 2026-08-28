# OX-ALPHA-DIRECTIVE-THEME-01 — Visual Identity Repair Loop, SWS-UI-001 (REM-04)

| Field | Value |
|---|---|
| Contract | `BUILD-DIRECTIVE-SWS-UI-001.md` v1.2, unchanged. `AGENTS.md` binds in full. This directive opens a **new, bounded mutation envelope** on an already-accepted build; it does not amend the contract. |
| Basis | The operator ran the accepted shell, found the rendered visuals do not carry SOVEREIGN's identity, and selected the target palette and scope in session. Four defects are named in §2. |
| Authorization | The operator places this file on disk and gives the kickoff sentence in session. The builder logs that sentence verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log` before any other mutation. That pair is the authorization artifact. |
| Standing | Gate 6 is `PASS` (operator, 2026-08-24T17:05:14.0265545Z). **v1.2 stays accepted.** This loop produces new candidates on top of it; it never edits, reopens, downgrades, or re-evaluates gates `0`–`6`, `4b`, `4c`, `5b`. |
| Supersedes | `docs/THEME-BASELINE-v2.md` is superseded by `docs/THEME-BASELINE-v3.md` on completion of G2, append-only: v2 is preserved, v3 names it and carries its hash. Nothing else is superseded. |
| Loop state | `evidence/theme01/LOOP-LEDGER.jsonl`, append-only, one JSON line per iteration. A fresh session resumes by reading it and re-running the goal check — never from memory. |
| Product version | The UI version string stays `SWS-UI-001 v1.2`. Bumping it is an operator decision and is **not** in this envelope. |

## 1. Operating principle

Verify, then act, then verify. Every iteration: run the goal check against disk, take the **single smallest authorized action** that flips the **first** failing goal, run the goal check again, append one loop-ledger line. No action is taken that a currently-failing goal does not require. No goal is marked done by recollection — only by the check re-run. The loop ends in exactly one of two states: all goals TRUE (submit candidates, report, claim line) or a STOP report per §7. There is no third exit.

## 2. The four defects

Each is stated as the directive author read it from disk. **The builder confirms each independently against the live files before acting on it.** A defect that does not reproduce is not repaired — it is recorded as `NOT_REPRODUCED` in the loop ledger and the report, and the loop moves on.

### D1 — light and dark are two different designs

`FACT[shell/static/app.css:33-49]` The `@media (prefers-color-scheme: light)` block overrides `--accent` to `#8a744a` (gold) while `:root` carries `--accent: #bb9af7` (violet). A viewer whose OS is light gets a gold-on-white product; a viewer in dark gets violet-on-black. `FACT[docs/REVIEW-BUILD-06.md §4]` The reviewer raised this as the operator's open decision. The operator has now decided: **pin a matching light variant** — same design, one palette, two surface levels.

### D2 — the dark accent is not SOVEREIGN's identity

`FACT[shell/static/app.css:23]` `--accent: #bb9af7` is SOW's conductor violet, pinned by REM-03 under the operator instruction logged 2026-08-22T23:01:33.2358027Z. `FACT` The operator has now selected a different target: a HUD ice-blue. This **supersedes the REM-03 accent decision only**; every other REM-03 token decision, including `--text-muted: #9aa7bd`, stands.

### D3 — the THEME-BASELINE link in the UI serves the wrong document

`FACT[shell/src/server.py:38]` `"theme-baseline": os.path.join("docs", "THEME-BASELINE.md")` — the v1 baseline. `FACT[docs/THEME-BASELINE-v2.md]` v2 has been the theme in force since REM-03. `FACT[shell/tests/test_render.py:205]` H-14 asserts the stale mapping, so the suite protects the wrong target. Clicking THEME-BASELINE in the header shows a palette the product does not use.

### D4 — the pre-flight panel reads 0/7 with every dot unknown

`FACT[evidence/loop5/screenshots/*.png]` Every acceptance capture shows `0/7 available`, all dots grey, while Ollama and the ports were live. `FACT[docs/REVIEW-BUILD-06.md §4]` The reviewer raised it as probably a genuine probe defect and out of 4c/5b scope.

The author's reading of the root cause, **to be verified, not assumed**:

- `FACT[shell/src/probe.py]` `run_preflight()` returns `{"ollama": {"reachable": …}, "toolchain": {"py-3.12": {"present": …}}, "ports": {"5175": {"free": …}}, "timestamp": …}`.
- `FACT[shell/static/app.js:273]` `interpretPreflight()` looks for a boolean in `[value.ok, value.available, value.up, value.running, value.installed, value.pass]`. The payload's booleans are named `reachable`, `present`, `free` — none of them is in that list, so every object resolves to `unknown`.
- `FACT[shell/static/app.js:293-322]` `normalizePreflight()` descends into `payload.ports` but never into `payload.toolchain`, so `py -3.12`, `node` and `npm` are never found at all. The backend key is also `py-3.12` while `PREFLIGHT_ITEMS` looks for `py3.12`/`py312`.
- `FACT[shell/static/app.js:300-317]` A `payload.checks` array is already supported, but top-level keys are written into the lookup **after** it, so a `checks` entry for `ollama` or `port_5175` would be overwritten by the raw nested value.
- `FACT[shell/tests/test_shell.py:286-288]` The only test asserts `"ollama" in payload` — a top-level key check, which is exactly the H-15 shallow-contract gap the reviewer noted. It cannot catch this class of defect.

## 3. The target palette — pinned, with measured ratios

Every value below was computed with the WCAG 2.x relative-luminance formula. The builder recomputes them; a disagreement is a STOP, not a rounding note.

### 3.1 Dark — `:root`

| Token | Value | Change | Measured |
|---|---|---|---|
| `--bg` | `#0b0e14` | unchanged | — |
| `--panel` | `#151b28` | unchanged | — |
| `--sidebar` | `#0d121c` | unchanged | — |
| `--input` | `#1b2333` | unchanged | — |
| `--border` | `#232b3a` | unchanged | — |
| `--text` | `#c7d1de` | unchanged | 12.51 on bg · 11.16 on panel |
| `--text-muted` | `#9aa7bd` | unchanged (REM-03 operator decision stands) | 7.08 on panel |
| `--text-faint` | `#3a4353` | unchanged | 1.73 on panel — recorded, not asserted, see §3.4 |
| **`--accent`** | **`#7fc8e8`** | **from `#bb9af7`** | **10.42 on bg · 9.29 on panel** |
| **`--accent-dim`** | **`#2a4a5c`** | **from `#3a2f57`** | `--text` on it = 6.09 |
| `--ok` | `#9ece6a` | unchanged | 9.42 on panel |
| `--warning` | `#e0af68` | unchanged | 8.61 on panel |
| `--danger` | `#f7768e` | unchanged | 6.51 on panel |

`#0b0e14` background, `#c7d1de` silver body text, `#7fc8e8` ice-blue accent. That is the target the operator described.

### 3.2 Light — `@media (prefers-color-scheme: light)`

The light block becomes the **same design at a different surface level**: same roles, same rule set, only token values differ.

| Token | Value | Change | Measured on `--panel` `#ffffff` |
|---|---|---|---|
| `--bg` | `#f4f5f7` | unchanged | — |
| `--panel` | `#ffffff` | unchanged | — |
| `--sidebar` | `#eceef1` | unchanged | — |
| `--border` | `#d3d8e0` | unchanged | — |
| `--text` | `#1b2027` | unchanged | 16.37 |
| `--text-muted` | `#58616e` | unchanged | 6.27 |
| `--text-faint` | `#8a93a1` | unchanged | 3.10 — recorded, not asserted, see §3.4 |
| **`--accent`** | **`#1f6f94`** | **from `#8a744a`** | **5.59** (5.12 on bg; `#ffffff` on it = 5.59) |
| **`--accent-dim`** | **`#a8d6ea`** | **from `#a68b58`** | `--text` on it = 10.50 |
| **`--ok`** | **`#2f7a49`** | **new light override** | **5.25** (4.81 on bg) |
| **`--warning`** | **`#8a6008`** | **new light override** | **5.59** (5.12 on bg) |
| **`--danger`** | **`#c8394f`** | **new light override** | **5.06** (4.63 on bg) |

`#1f6f94` is the same ice-blue hue family as `#7fc8e8`, darkened until it clears 4.5:1 as text on white. The two themes are then one identity.

### 3.3 Retire the light-theme glyph exception

`FACT[shell/static/app.css:45-48]` The light block currently demotes badge text to `var(--text)` and re-declares `.dot` rules, because `--ok`/`--warning`/`--danger` inherited the dark values and measured 1.83 / 2.00 / 2.65 on white — below the 3:1 non-text bar. `FACT[evidence/hardening/h16-contrast.txt]` H-16 records those three as `GLYPH (<3:1)` rather than asserting them.

With the §3.2 values all clearing 4.5:1, that exception is no longer needed. **Goal:** the light block contains custom-property overrides only. Any selector rule retained inside it must be named and justified in `THEME-BASELINE-v3.md`; a rule that exists only to work around the old low-contrast values is deleted. This retires the reviewer's standing contrast finding outright instead of carrying it forward.

### 3.4 `--text-faint` is explicitly out of scope

`FACT` `--text-faint` measures 1.73:1 (dark) and 3.10:1 (light) against `--panel`. It sits below 4.5:1 in both themes today and did so through Gate 6. It is **not** changed by this loop. It **is** recorded in the H-16 artifact so it is visible rather than hidden. Changing it is a separate directive; widening into it here is a STOP (`ENVELOPE_EXCEEDED`).

## 4. Goal state — every predicate must be TRUE on disk

| # | Goal | TRUE when (machine-checkable) |
|---|---|---|
| G0 | Session precondition | Kickoff logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`; true UTC captured; `docs/DECISIONS.md` sha256 recorded (read-only); `evidence/GATE-LEDGER.json` sha256 recorded and equal to `518ac84ce6a2b55b0c2d2f0bdcbd4dcd64886669012e1354432c28df6ef28085`; ports 5175/8700/5180 state recorded; `evidence/theme01/` created with the goalcheck oracle written. |
| G1 | Pre-change baseline | `shell/BUILD-MANIFEST.txt` 40/40 against live files; `app.css` = `329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab`; a pre-change capture of both themes exists under `evidence/theme01/before/`; each of D1–D4 confirmed or marked `NOT_REPRODUCED`, with the evidence line that decided it. |
| G2 | Baseline v3 pinned | `docs/THEME-BASELINE-v3.md` exists, carries `# utc:`/`# producer:` headers, names `docs/THEME-BASELINE-v2.md` as superseded with v2's sha256, lists every token in §3.1 and §3.2 with its measured ratio, records the §3.3 rule-set decision, and states §3.4 as an out-of-scope carry. |
| G3 | Dark tokens applied | `app.css` `:root` matches §3.1 exactly. No other `:root` value changed. |
| G4 | Light variant applied | `app.css` light block matches §3.2 exactly and contains custom-property overrides only, except rules justified in v3. |
| G5 | Contrast asserted, not merely recorded | `shell/tests/test_render.py` H-16 **asserts** every one of the six pairs at ≥ 4.5:1 in **both** themes — the glyph branch no longer excuses light `ok`/`warning`/`danger`. `evidence/hardening/h16-contrast.txt` regenerated by that test, showing 12 TEXT rows all OK, plus `--text-faint` and `--accent-dim` rows recorded. The test fails against the pre-change CSS and passes after. |
| G6 | D3 repaired | `/doc/theme-baseline` serves `docs/THEME-BASELINE-v3.md`; H-14's expected mapping updated in the same change; H-14 passes. |
| G7 | D4 repaired and proved | All seven pre-flight ids resolve to a definite status against a live shell. A new regression test asserts, end to end through `/api/preflight`, that each of `ollama`, `py312`, `node`, `npm`, `port_5175`, `port_8700`, `port_5180` yields a non-`unknown` status and a non-empty detail, with the §4.1 semantics. The test fails before the fix and passes after. A live capture in `evidence/theme01/after/` shows the panel reading `7/7 available` — or a lower count where a checked dependency is genuinely absent, with the absent one named. |
| G8 | Suite green | `evidence/test-run.txt` from the README command ends `OK`, test count ≥ the pre-change count, run after G3–G7. `shell/BUILD-MANIFEST.txt` regenerated by the suite; entries equal live file hashes. |
| G9 | Visual proof, both themes | `evidence/theme01/after/` holds a dark-theme grid capture and a light-theme grid capture from the live shell, each non-blank, each decoding to the expected background luminance, both showing the ice-blue accent; the exact capture command recorded. Before/after pairs referenced side by side in the report. |
| G10 | Ledger | `"7a"` (theme: D1, D2, D3) and `"7b"` (pre-flight: D4), both `CANDIDATE`, each with full lowercase sha256 for every artifact cited. Every other key — including `"6"` — byte-identical to a pre-write snapshot preserved at `evidence/theme01/ledger-snap-pre7.json`. |
| G11 | Report and closeout | `docs/REM-04-REPORT.md`: every substantive sentence tagged per AGENTS.md §11; changed files with before/after hashes; exact changed-line count per file against §5; each of D1–D4 with its verdict; tests added and their fail-before/pass-after evidence; the retired contrast finding named; `--text-faint` carried openly. Shell stopped, ports 5175/8700/5180 empty, no orphan module processes. Ends with the §9 claim line. |

### 4.1 Pinned pre-flight semantics — do not invent your own

The panel is a launch-readiness report. These meanings are fixed by this directive:

| Id | `ok` when | `detail` |
|---|---|---|
| `ollama` | the endpoint answers | model count, e.g. `4 models` |
| `py312` | `py -3.12 --version` succeeds | the version string |
| `node` | `node --version` succeeds | the version string |
| `npm` | `npm --version` succeeds | the version string |
| `port_5175` | the port is **free** — SOVEREIGN can be launched into it | `free` or `in use` |
| `port_8700` | the port is **free** — Debate Table can be launched into it | `free` or `in use` |
| `port_5180` | the port is **in use** — it is the shell you are talking to | `shell` |

`port_5180` inverts deliberately. `FACT[docs/REVIEW-BUILD-06.md §3 correction 1]` The reviewer already settled this reasoning: a predicate demanding 5180 be free contradicts a running shell. A dot that reports "bad" because the shell you are looking at is running would be false.

Absent tooling is a truthful `bad` with a reason, never repaired into a green dot. `FACT` Installing or reconfiguring anything to make a dot turn green is a session-ending violation under AGENTS.md §7.

## 5. Mutation envelope — nothing outside it

Product code, hard caps, counted as changed lines against the pre-change file:

| File | Permitted change | Cap |
|---|---|---|
| `shell/static/app.css` | token values in `:root` and the light block; removal of light-block rules made redundant by §3.3 | 60 |
| `shell/static/app.js` | pre-flight resolution only — `PREFLIGHT_ITEMS`, `normalizePreflight`, `interpretPreflight` | 40 |
| `shell/src/probe.py` | `run_preflight` and the `preflight_*` helpers only | 60 |
| `shell/src/server.py` | the `theme-baseline` doc-map entry only | 2 |

**162 changed product lines total, absolute.** Test code is not capped, but every new or changed test must be shown failing before the fix and passing after, captured as evidence. No refactors, no cleanups, no style churn, no new routes, no new dependencies, no reformatting of untouched regions. Splitting a larger change across stages to stay under a cap is itself a violation.

Docs and evidence the builder may write: `docs/THEME-BASELINE-v3.md`, `docs/REM-04-REPORT.md`, `docs/STOP-REPORT-THEME-01.md`, anything under `evidence/theme01/`, and the two new ledger keys. Suite-generated artifacts (`evidence/test-run.txt`, `evidence/hardening/*`, `shell/BUILD-MANIFEST.txt`) regenerate under the suite's own rules.

## 6. The loop

```
i = 0
while i < 40:
    i += 1
    state = goalcheck()                 # reads disk only; writes evidence/theme01/goalcheck-i.txt
    if all TRUE: break
    g = first failing goal
    act(g)                              # the ONE smallest authorized action for g (§5)
    state2 = goalcheck()
    append LOOP-LEDGER.jsonl: {i, utc, goal: g, action, changed_lines, flipped: state2[g], notes}
    if g unchanged for 2 consecutive iterations with the same action class:
        STOP LOOP_NO_PROGRESS (§7)
submit: docs/REM-04-REPORT.md + claim line
```

`goalcheck()` is a builder tool at `evidence/theme01/tools/goalcheck.py` — `py -3.12`, stdlib only, read-only against the workspace, `PYTHONDONTWRITEBYTECODE=1`. It parses `app.css` tokens, recomputes every ratio in §3, hashes the cited artifacts, and decodes capture background luminance. It is the loop's only oracle. Write it at G0. If goalcheck itself errors, fixing goalcheck is a permitted action logged as `goal: G-oracle`. **Never** weaken a goal predicate to make it pass: any change to a goal's meaning is a STOP requiring a new operator instruction, and the loop ledger must record the proposed change rather than apply it.

Every iteration also asserts, before acting: `evidence/GATE-LEDGER.json` keys `0`–`6`, `4b`, `4c`, `5b` byte-identical to the G0 snapshot. Drift there is `PROTECTED_LEDGER_CHANGED` and an immediate STOP.

## 7. STOP conditions — AGENTS.md §13 in full, plus

`LOOP_NO_PROGRESS` (same goal, same action class, no flip, twice) · `ENVELOPE_EXCEEDED` (any cap in §5 would be passed, or a change is needed in a file not listed there) · `CONTRAST_UNREACHABLE` (a pinned §3 value does not measure as stated, or a required pair cannot clear its bar without changing a token this directive freezes) · `PROTECTED_LEDGER_CHANGED` · `PROTECTED_SOURCE_CHANGED` · `DEFECT_NOT_REPRODUCED` for **all four** defects (nothing to repair — report and stop) · `CONCURRENT_WRITER` (see §8) · iteration 40 reached.

A STOP writes `docs/STOP-REPORT-THEME-01.md` with the loop-ledger tail, the `FACT[...]` condition, the exact conflict, 2–3 bounded operator options, no unauthorized implementation — then closes out per AGENTS.md §14 and ends with the no-gate claim line.

## 8. Single-writer requirement

`FACT` On 2026-08-24 two agents executed `EXPORT-DIRECTIVE-SNAPSHOT-01` against this root within four minutes of each other, both appended to `evidence/OPERATOR-INSTRUCTIONS.log`, and one overwrote the other's `dist/` documents.

This loop runs as the **only** writer in `D:\Product Software\Production Workspace\`. At G0, and again before each ledger write, confirm no second agent session is active. If `evidence/OPERATOR-INSTRUCTIONS.log`, `evidence/GATE-LEDGER.json`, or any file under `shell/` changes without a loop-ledger line accounting for it, STOP as `CONCURRENT_WRITER`, name the files with before/after hashes, and change nothing further.

## 9. What this loop may never do

Write `PASS` anywhere. Alter any entry carrying `evaluated_by: reviewer` or `evaluated_by: operator`. Reopen or re-evaluate Gate 6. Edit `AGENTS.md`, `CLAUDE.md`, `BUILD-DIRECTIVE-SWS-UI-001.md`, any `docs/*DIRECTIVE*.md`, any `docs/REVIEW-*.md`, or `docs/DECISIONS.md`. Write anywhere under `D:\Product Software\` outside `Production Workspace\`, or in `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, `D:\Sov 1\`. Run a package manager, install anything, or touch provider configuration. Launch a module by hand. Change `--text-faint`, the product version string, or any token §3 marks unchanged. Re-interpret a goal so it passes — "close enough" is FALSE. Treat goalcheck output as evidence of anything goalcheck did not read from disk this iteration.

## 10. Exit

On all goals TRUE: write `docs/REM-04-REPORT.md`, then a final message giving the iteration count, the goal table with the artifact and hash proving each, the four defect verdicts, exact changed-line counts against the §5 caps, before/after captures in both themes, the retired light-contrast finding, and every carried risk — `--text-faint` in both themes, and H-15's shallow top-level check if G7 did not replace it. End with exactly:

`BUILDER CLAIM: Gate 7a and Gate 7b are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder.`

On any STOP, end with exactly:

`BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.`

The reviewer evaluates `7a` and `7b`. Promotion, and any decision to re-cut the `dist/` snapshot afterwards, remain the operator's.
