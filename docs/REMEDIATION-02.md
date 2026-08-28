# REMEDIATION ORDER REM-02 — Shell UI Render Defects (Gate 4 addendum), SWS-UI-001 v1.2

| Field | Value |
|---|---|
| Governing contract | SWS-UI-001 v1.2, unchanged |
| Basis | `docs/STOP-REPORT-GATE5.md` (Ox Alpha, 2026-08-22); reviewer adjudication in `docs/REVIEW-BUILD-04.md` |
| Authorization required | **Operator**, by instruction in session, quoted verbatim by the builder. This order widens the Gate 5 §6 defect envelope for four named defects only. |
| Builder | Any builder under `AGENTS.md` (Ox Alpha or Claude Code). Same envelope either way. |
| Effect on gates | Gate 4 reopened to `CANDIDATE` for the four items below; Gates 2–3 PASS unchanged; Gate 5 visual steps re-run after Gate 4 re-passes. Non-visual Gate 5 evidence from the 2026-08-21 session stands and is not repeated. |

```
OPERATOR AUTHORIZATION: given by operator instruction in session (AGENTS.md §1 item 3).
The builder records the instruction verbatim with UTC in evidence/OPERATOR-INSTRUCTIONS.log.
No file edit or signature by the operator is required.
```

---

## 1. Defects in scope — and nothing else

| ID | Defect | Evidence | Contract clause it violates |
|---|---|---|---|
| D1 | `shell/static/index.html` references `app.css`/`app.js` relatively from `/`; server serves them only under `/static/`. Page renders blank. | `STOP-REPORT-GATE5.md` §FACT 1–5; `server.py:130-149` | §7.3 (grid must render); §7.1 |
| D2 | Header links `/discovery`, `/theme-baseline`, `/directive` return 404. | same, FACT 4 | §7.3 item 5 (header "links to DISCOVERY / THEME-BASELINE / this directive") |
| D3 | `app.js` `loadDistillery()` expects `open_questions` (number/array), `links` (array), `snapshot_id` (string); `/api/distillery` returns `questions{open_count, open_ids}`, `links{…}` object, `snapshot{snapshot_id}`. Card would show placeholders. | `STOP-REPORT-GATE5.md` secondary finding; `evidence/gate5/distillery.json`; `app.js:693-753` | §7.5 (derived count **and** matched IDs displayed) |
| D4 | Light theme: `--ok/--warning/--danger` not overridden in the light block; badge color on `#ffffff` panel = 2.03 / 2.19 / 3.65 : 1. | `evidence/gate5/theme-contrast.txt` | §7.7 (contrast ≥ 4.5:1), §5 (tokens only) |

Out of scope, explicitly: anything else in `shell/**`; any module; any new feature; any token not in `docs/THEME-BASELINE.md`.

## 2. Envelope (replaces Gate 5 §6 for D1–D4 only)

- Total across all four: ≤ 80 changed lines in `shell/src` + `shell/static`, counted by `git diff --stat`-equivalent on the files (the workspace is not a repo; compute with a before/after line diff and record it).
- One regression test per defect (four total), each failing before and passing after, in `shell/tests/test_render.py`.
- D2 may add **at most one** read-only `GET` route or static-mapping rule in `server.py` that serves exactly the three named documents as `text/plain` or `text/markdown` from `docs/` and `BUILD-DIRECTIVE-SWS-UI-001.md`, with canonical-path containment (reuse the existing H-5 helper), `nosniff`, and the same H-3 headers. No directory listing, no other paths. This is the only route addition permitted by this order.
- D4 fix must use baseline tokens only. Permitted approach: in the light block, badge **text** uses `--text`; the `--ok/--warning/--danger` color is applied to the glyph/dot only (non-text, WCAG 3:1 applies) and to a 1px border. Do not invent new hex values.
- No refactors, no renames, no cleanup, no dependency. Anything beyond → `docs/STOP-REPORT-REM-02.md`, reason `DEFECT_EXCEEDS_REM02_ENVELOPE`.

## 3. Required new proofs (added to Gate 4 permanently)

| ID | Test | Artifact |
|---|---|---|
| H-13 | `test_render.py::test_first_party_urls_resolve`: GET `/`; collect every first-party URL from the HTML (`href`/`src` via `html.parser`), from `app.css` (`url(...)`), and from `app.js` (string literals starting `/api/` or `/static/`); GET each against the running shell; assert **zero** 4xx/5xx and the expected `Content-Type` for assets. This catches the next broken reference without enumeration. | `evidence/hardening/h13-assets.txt` (lists every URL checked and its status) |
| H-14 | `test_render.py::test_header_links_resolve`: the three doc links return 200, `text/*`, `nosniff`, and body starts with the expected first line of each document. | `evidence/hardening/h14-doclinks.txt` |
| H-15 | `test_render.py::test_distillery_payload_contract`: a JSON-schema-style assertion that `/api/distillery` keys match what `app.js` reads — implemented by extracting the key names `loadDistillery()` accesses (regex over `app.js`) and asserting each exists in the live payload. | `evidence/hardening/h15-distillery-contract.txt` |
| H-16 | `test_render.py::test_light_theme_contrast`: compute the six §C-2 pairs from `app.css` per block; assert ≥ 4.5:1 for every **text** pairing in both themes; record glyph pairings separately at ≥ 3:1. | `evidence/hardening/h16-contrast.txt` |
| H-17 | **Rendered-DOM check** (closes the gap that let D1 through): headless Edge `--dump-dom` of `/` after load, assert the four `article.module-card` elements exist with the fixed order, each has five action buttons, and the Distillery card's Start/Stop/Open/Test carry `disabled`. Edge path resolved from the App Paths registry key; builder tooling, not a launch. | `evidence/hardening/h17-dom.txt` + `evidence/gate5/screenshots/shell-grid-rendered.png` |

## 4. Sequence

1. Precondition: operator instruction authorizing REM-02 received and logged. Gate 5 STOP entry from 2026-08-22 left untouched.
2. D1 → test → D2 → test → D3 → test → D4 → test. Record the line-count diff after each.
3. Full README test command → `test-run.txt` ends `OK` (now ≥ 121 tests). Regenerate `BUILD-MANIFEST.txt`. H-13…H-17 artifacts written.
4. Ledger: Gate 4 → `CANDIDATE` (builder may not write PASS; the reviewer's prior PASS entry is superseded by the reviewer, not the builder — add a new Gate 4 entry keyed `"4b"` with the reviewer's original left byte-identical).
5. Reviewer evaluates Gate 4b. Only after PASS: Gate 5 **visual steps only** — A-5, B-4 screenshots for the four cards using the existing startup records (do not re-run module tests unless a record is older than the shell binary manifest), B-7 live-DOM confirmation, B-8 side-by-side with SOVEREIGN (re-run its startup test with keep, screenshot, stop), `shell-light-mode.png` with `--force-prefers-color-scheme=light` or the flag Edge 151 honors (record the exact command). Ledger Gate 5 → `CANDIDATE`.
6. `docs/BUILD-REPORT.md` per v1.2 §10.2, including in "Contradictions": the `DECISIONS.md` live-tree statement is false (§1a of the Gate 5 directive), and the Gate 4 render gap.

## 5. Closing line

Every report: `BUILDER CLAIM: Gate <N> is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.`

## 6. Reviewer's notes to the operator

- `FACT` H-13 was broadened after concurring review (ChatGPT, 2026-08-22) to assert zero first-party 4xx/5xx across HTML, CSS, and JS references rather than a fixed list. H-15 (Distillery payload contract) is retained although that review's list omitted it: D3 would survive a pure render check.

- `FACT` The Gate 4 PASS I recorded on 2026-08-21 was granted without a rendered-page check; the directive's §9 did not require one. H-17 closes that permanently.
- `FACT` The builder's STOP was correct and its option 1 is adopted here with D2–D4 folded in, because D2 is a contract requirement (§7.3 item 5), not a feature.
- `INTERPRETATION` ~80 lines is generous for four small fixes; the cap is there to stop scope creep, not to be reached.
- `RECOMMENDATION` Sign this and `DECISIONS.md` in the same sitting. Gate 6 still cannot close on an unsigned root.
