# REMEDIATION ORDER REM-03 — Theme re-pin to SOW palette, SWS-UI-001 v1.2

| Field | Value |
|---|---|
| Governing contract | SWS-UI-001 v1.2, unchanged. §5 already binds the shell to "the tokens in `docs/THEME-BASELINE.md`"; this order re-pins that baseline, it does not amend the contract. |
| Basis | Operator instruction in session, 2026-08-22: the shell "needs to match this visual theme" — the Sovereign Orchestration Workspace (SOW) screenshot, not SOVEREIGN's slate/gold. `docs/THEME-BASELINE.md` v1 §"Debate Table family note" records the SOVEREIGN choice as a builder design decision; the operator has now overruled it. |
| Authorization | Operator instruction in session, quoted verbatim with UTC by the builder into `evidence/OPERATOR-INSTRUCTIONS.log`. No file edit or signature by the operator. |
| Builder | Any builder under `AGENTS.md`. |
| Sequencing | After the current Gate 5 visual run closes (its CANDIDATE stands as evidence of the v1 theme). REM-03 then reopens Gate 4 as `"4c"` and Gate 5 visual steps are re-run once more under the v2 baseline. |

```
OPERATOR AUTHORIZATION: given by operator instruction in session (AGENTS.md §1 item 3).
```

## 1. What changes — and nothing else

| ID | Item | Scope |
|---|---|---|
| T1 | **Pin `docs/THEME-BASELINE-v2.md`** from SOW's own stylesheet(s), read-only, under `D:\multi model terminal app\` (`GIT_OPTIONAL_LOCKS=0`, `PYTHONDONTWRITEBYTECODE=1`, no writes, never launched). Record the source file path(s) and sha256. Extract verbatim: page background, pane/panel background, pane border, primary text, muted text, the violet/purple accent used on pane headers and the CONDUCTOR bar, the green used on status chips, the warning and danger colours if SOW defines them, and the monospace font stack. v1 is not edited (it is Gate 1 evidence); v2 names v1 and supersedes it. | new doc only |
| T2 | **Swap token values in `shell/static/app.css` `:root`** to the v2 set. `--font` becomes the SOW monospace stack (SOW is monospace throughout; the shell follows). `--radius` → the value SOW uses for panes (expected small, 2–4px; record it). Light block: **unchanged** (SOW has no light theme; the existing light tokens stay until the operator says otherwise). | token lines only |
| T3 | **Re-verify contrast**: H-16 (`test_light_theme_contrast`) must still pass ≥ 4.5:1 for every text pairing in both themes on the v2 values. If a SOW-verbatim pairing fails, STOP and report the exact ratio — do not pick a different hex. | existing test |
| T4 | **Re-render**: H-17 DOM/PNG, then Gate 5 visual steps under v2 (card screenshots, side-by-side with SOVEREIGN, light-mode capture). | evidence only |

Out of scope, explicitly: layout, components, markup, JS, any rule in `app.css` other than the `:root` token block and `--font`/`--radius`; any new hue not present verbatim in SOW's stylesheet; any module; any edit to `docs/THEME-BASELINE.md` v1 or `docs/DISCOVERY.md`.

## 2. Envelope

- ≤ 40 changed lines in `shell/static/app.css`, all inside the `:root { … }` block (plus the header comment's contrast figures if the builder updates them — those lines count).
- No other `shell/**` file changes. `shell/tests/test_render.py` unchanged; if H-16 needs a different token *list*, STOP — that is a test change and needs a separate order.
- One new doc: `docs/THEME-BASELINE-v2.md`. One new ledger key: `"4c"` (`CANDIDATE`), all other entries byte-identical.
- STOP reason if exceeded: `DEFECT_EXCEEDS_REM03_ENVELOPE`, report at `docs/STOP-REPORT-REM-03.md`.

## 3. Sequence

1. Log the operator instruction verbatim with UTC. Session-start precondition per the Gate 5 directive §1.
2. T1: locate and hash SOW's stylesheet(s); write `THEME-BASELINE-v2.md` with a token table, the verbatim source lines each value came from (file:line), and the light block carried forward from v1.
3. Baseline copy of `app.css` to `evidence/rem03/before/`; T2; line-count diff recorded to `evidence/rem03/linecount.txt`.
4. Full README suite → `evidence/test-run.txt` ends `OK` (121 tests); H-16 artifact regenerated; H-17 regenerated (`h17-dom.txt`, `shell-grid-rendered.png`).
5. Gate 5 visual steps re-run → new `-rem03` screenshot set. Ledger `"4c"` CANDIDATE and `"5c"` CANDIDATE.
6. Builder report `docs/REM-03-REPORT.md`, ending with the §14 claim line.

## 4. Reviewer notes to the operator

- `FACT[docs/THEME-BASELINE.md]` v1 pinned SOVEREIGN's tokens (`--bg #0e1116`, `--accent #c9a86a` gold, Segoe UI) and recorded that SOW "uses a terminal palette" as the reason for not following it. The shell therefore matches SOVEREIGN, not SOW, by design — this order reverses that design choice on your instruction.
- `INTERPRETATION` A token swap gets the palette and typography to SOW's: near-black ground, violet accent, green chips, monospace everywhere. It does not turn the card grid into SOW's multi-pane terminal layout; the contract §7.3 fixes the grid, and changing it would be a contract amendment, not a remediation.
- `INTERPRETATION` The PNG in REVIEW-BUILD-05 looked light because headless Edge on your host defaulted to the light scheme; users with a dark OS theme already get the dark palette. The mismatch you are seeing is the hue (slate/gold vs black/violet), and that is what T2 fixes.
- `RECOMMENDATION` Let the running Gate 5 finish first. Interrupting it leaves a shell and watcher to clean up and discards an hour of valid evidence; the re-run under v2 is quick because the driver and helpers now exist.
