# DIRECTIVE FOR OX ALPHA (OpenCode) — REM-02 Execution → Gate 4b Candidate, SWS-UI-001 v1.2

Paste as the first message of a fresh OpenCode session opened at
`D:\Product Software\Production Workspace\` (`AGENTS.md` auto-loads there). This file is the
current work order; it supersedes `docs/OX-ALPHA-DIRECTIVE-GATE5.md` for this session only.
The Gate 5 directive's §1a facts (`D:\Sov 1\` protected; `DECISIONS.md` live-tree statement false)
remain in force.

**Operator instruction (process control):** do not end your turn at any step boundary; end it only
with the §7 final message or a STOP report. If the harness ends your turn anyway, the operator will
send `continue` and you resume from the last completed step without re-deriving the plan.

---

## 0. Role, entry state, prohibitions

Builder only. Not operator, not reviewer, not gate authority.

Entry state (`FACT`, `evidence/GATE-LEDGER.json` after REVIEW-BUILD-04): Gates 0/1 `STOP` (unsigned
root) · 2, 3 `PASS` · 4 `PASS` with reviewer addendum naming the render gap · 5 `STOP` (correct;
non-visual evidence carried forward) · 6 `NOT_REACHED`.

Read before step 1, from disk: `BUILD-DIRECTIVE-SWS-UI-001.md` §5, §7.1–7.7 · `docs/REMEDIATION-02.md`
(the envelope you work under) · `docs/REVIEW-BUILD-04.md` · `docs/STOP-REPORT-GATE5.md` ·
`docs/THEME-BASELINE.md` · `shell/src/server.py` · `shell/src/adapter.py` (the H-5 canonical-path
helper you will reuse) · `shell/static/index.html` · `shell/static/app.js` (`loadDistillery`,
`refreshButtons`, `buildCards`) · `shell/static/app.css` · `shell/tests/_harness.py` ·
`shell/tests/test_zz_evidence.py` (how hardening artifacts are emitted) · `evidence/gate5/distillery.json`.

### 0.1 Absolute prohibitions — one violation ends the session

1. Never create/edit/delete `docs/DECISIONS.md` or `docs/REMEDIATION-02.md`; never write `sam` as signer. Operator authorization is recorded only by quoting the operator's own words with a timestamp.
2. Never write `"status": "PASS"` to the ledger. Never alter Gates 2–5 or the existing Gate 4 entry; Gate 4b is a **new** key. Gates 0/1 may move STOP → CANDIDATE per §1.
3. Protected trees untouched: `D:\Product Software\` outside `Production Workspace\`, `D:\multi model terminal app\`, `D:\Sovereign Distillery\`, `D:\Sov 1\`.
4. `shell/**` edits only as REM-02 §1–§2 permit: D1–D4, ≤ 80 changed lines total in `shell/src` + `shell/static`, one new test file `shell/tests/test_render.py`, at most one new read-only route for D2. Nothing else in `shell/**`.
5. No module launches in this session. No `pip`, `npm`, `install_sow.py`, Ollama changes, provider sessions, admin elevation.
6. No `cmd.exe`, `.cmd`, `.bat`, `shell=True` in code you write. No git.
7. Ambiguity → `docs/STOP-REPORT-REM-02.md`, then stop.

### 0.2 Closing line — every report and the final message

```
BUILDER CLAIM: Gate 4b is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
```
(or the "No gate is submitted…" variant if you STOP). Never "passed / complete / done" beside a gate.

---

## 1. Precondition — run first, stop on failure

```powershell
Set-Location "D:\Product Software\Production Workspace"
(Get-Date).ToUniversalTime().ToString("o")
Get-FileHash docs\REMEDIATION-02.md, docs\DECISIONS.md -Algorithm SHA256
Get-NetTCPConnection -State Listen -LocalPort 5175,8700,5180 -ErrorAction SilentlyContinue
Get-Process python,electron,node -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*Production Workspace\modules*" }
```

Record in `evidence/gate4b/precondition.txt` (`# utc:` / `# producer: ox-alpha GATE4B` headers).

**Authorization:** the operator's message that delivered this directive contains the sentence
`OPERATOR AUTHORIZATION: REM-02 D1–D4 authorized; DECISIONS content adopted as written; stage pauses waived.`
Quote that sentence verbatim with the UTC you received it into `evidence/OPERATOR-INSTRUCTIONS.log`
(append-only, `# utc:` / `# producer:` header on first creation) and into `precondition.txt`. That
record is the authorization for this order and for Gates 0/1 (the operator adopts the existing
`docs/DECISIONS.md` content, with one correction you also log: a live SOVEREIGN tree exists at
`D:\Sov 1\`). You may therefore set Gates 0 and 1 to `CANDIDATE` in the ledger with
`authorized_by: "operator (session instruction, see evidence/OPERATOR-INSTRUCTIONS.log)"`; the
reviewer evaluates them. If the sentence is absent from the message → STOP `PRECONDITION_UNSIGNED`.
Proceed only if ports are free and no module processes exist; otherwise STOP `HOST_NOT_QUIESCENT`.
Report the `DECISIONS.md` hash as found. Do not edit it.

Then start the H-12 watcher exactly as Gate 5 A-1 did (`evidence/gate5/tools/fswatch_driver.py`
may be reused; output path `evidence/gate4b/fs-watch-gate4b.txt`; do not modify `_fswatch.py`).

---

## 2. Baseline before any edit

Copy `shell/static/index.html`, `app.js`, `app.css`, `shell/src/server.py` to
`evidence/gate4b/before/` and hash them. Run the README test command once → `evidence/gate4b/test-run-before.txt`
(expect 116 `OK`). This is the "fails before" baseline for the four new tests.

---

## 3. Repairs — in this order, one test each, line count recorded after each

Line counting: after each defect, `py -3.12 -c` with `difflib.unified_diff` over before/after
copies of the touched files; sum added+removed; append to `evidence/gate4b/linecount.txt`.
Running total must stay ≤ 80 across `shell/src` + `shell/static` (test file excluded).

**D1 — asset paths.** In `index.html` change `href="app.css"` → `href="/static/app.css"` and
`src="app.js"` → `src="/static/app.js"`. Nothing else in the file. Test
`test_render.py::test_first_party_urls_resolve` (REM-02 H-13): via `_harness.start_shell()`, GET `/`;
collect every first-party URL from the HTML (`html.parser`, attrs `href`/`src`), from `app.css`
(`url(...)`), and from `app.js` (string literals starting `/api/` or `/static/`; skip ones containing a
template placeholder or `<id>`); GET each; assert no 4xx/5xx and `Content-Type` `text/css` / `text/javascript`
(or `application/javascript`) for the two assets. Write every URL+status to `evidence/hardening/h13-assets.txt`.
The test must fail against the `before/` copy — prove it by running once before the edit and capturing
the failure to `evidence/gate4b/h13-fails-before.txt`.

**D2 — doc links.** Add exactly one read-only route in `server.py`: `GET /doc/<name>` where `name ∈
{discovery, theme-baseline, directive}` maps to `docs/DISCOVERY.md`, `docs/THEME-BASELINE.md`,
`BUILD-DIRECTIVE-SWS-UI-001.md`. Resolve with the existing H-5 canonical helper; assert containment in
the workspace root; serve `text/markdown; charset=utf-8` with the H-3 header set (incl. `nosniff`);
any other name → 404; no directory listing. Update the three `href`s in `index.html` to `/doc/…`.
Test `test_header_links_resolve` (H-14): each returns 200, `text/markdown`, `nosniff`, body's first
non-empty line matches the file's; `/doc/../AGENTS.md` and `/doc/other` → 404. Artifact `h14-doclinks.txt`.

**D3 — Distillery payload contract.** Fix `loadDistillery()` in `app.js` to read the keys `/api/distillery`
actually returns (`questions.open_count`, `questions.open_ids`, `links` object values, `snapshot.snapshot_id`,
file hashes), rendering: the count **and** the matched IDs, the three links, the snapshot id, and the
verbatim line. Do not change the API. Test `test_distillery_payload_contract` (H-15): regex every
`data.<key>` / `data["<key>"]` path that `loadDistillery()` reads out of `app.js` and assert each resolves
in the live `/api/distillery` JSON. Artifact `h15-distillery-contract.txt` listing each path and its value type.

**D4 — light-theme badge contrast.** In `app.css` light block only: badge text color `var(--text)`;
the state color (`--ok/--warning/--danger`) applied to the badge glyph/dot and a 1px border only.
Baseline tokens only — no new hex. Test `test_light_theme_contrast` (H-16): parse `app.css` per block;
compute the six REM-02/C-2 pairs; assert every **text** pairing ≥ 4.5:1 in both themes; record
glyph pairings at ≥ 3:1. Artifact `h16-contrast.txt`. The test must fail on the `before/` CSS
(capture to `h16-fails-before.txt`).

**H-17 — rendered DOM (no code change; the proof that closes the gap).** Test `test_rendered_dom`:
resolve Edge from `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe` (record the path);
run `msedge.exe --headless=new --disable-gpu --no-first-run --user-data-dir=<temp> --virtual-time-budget=8000
--dump-dom http://127.0.0.1:<port>/` via `subprocess.run([...])` (argv list); parse the DOM with
`html.parser`; assert four `article.module-card` in order sovereign → sow → debate → distillery (use the
`data-module` attribute), each with five action buttons, and the Distillery card's Start/Stop/Open/Test
carrying `disabled`. Also `--screenshot` the same URL → `evidence/gate5/screenshots/shell-grid-rendered.png`
and assert the PNG's sha256 differs from the blank-render hash `f7744eb44a77e0401b85dd4dc07a9cc48860d79f2ad6ff908ba2839bd0669271`.
Artifact `h17-dom.txt` (the assertions and the exact command). If Edge is absent → STOP `SCREENSHOT_TOOL_ABSENT`.

---

## 4. Closing evidence

1. Full README test command, fresh shell, no `__pycache__` → `evidence/test-run.txt` only if it ends `OK`
   (expect ≥ 121 tests). Regenerate `shell/BUILD-MANIFEST.txt`.
2. `evidence/gate4b/after/` copies + hashes of the four touched files; final `linecount.txt` total.
3. Manifests: `manifest.py` for the three protected roots → `evidence/manifests/manifest-4b-*.txt`; `fc.exe /b`
   vs `manifest-before-*.txt` → `manifest-diff-4b-*.txt`, all "no differences".
4. Stop the watcher → `fs-watch-gate4b.txt`, `events: 0`, window brackets §2 through §4.1.
5. Orphan/port check → `evidence/gate4b/orphans-after.txt` (expect empty; ports free).

---

## 5. Ledger

Add key `"4b"` (do not touch `"4"`):
```json
"4b": { "status": "CANDIDATE", "claimed_by": "builder", "evaluated_by": null, "authorized_by": null,
        "utc": "...", "basis": "docs/REMEDIATION-02.md", "defects": ["D1","D2","D3","D4"],
        "evidence": [ {"path": "...", "sha256": "<64 hex>"} ] }
```
listing every file under `evidence/gate4b/`, the five `evidence/hardening/h1[3-7]-*.txt`, `test-run.txt`,
`shell/BUILD-MANIFEST.txt`, `shell/tests/test_render.py`, and the four touched source files (after hashes).
Assert Gates 0–6 byte-identical before and after the write.

---

## 6. Stop conditions → `docs/STOP-REPORT-REM-02.md`

`PRECONDITION_UNSIGNED` · `HOST_NOT_QUIESCENT` · `DEFECT_EXCEEDS_REM02_ENVELOPE` (line cap, second route,
any change outside D1–D4) · `SCREENSHOT_TOOL_ABSENT` · `PROTECTED_SOURCE_CHANGED` · a new test cannot be
made to fail-before without touching something outside the envelope · any instruction here that would
require violating §0.1.

---

## 7. Reports and final message

`docs/REM-02-REPORT.md`: 1 Precondition facts · 2 Per-defect table (defect · files · lines changed ·
test · fails-before artifact · passes-after) · 3 H-13…H-17 artifact table · 4 Closing evidence · 5
Deviations · 6 Unsigned-root statement · 7 Open risks (two npm advisories; anything new). Every
sentence in 2–7 tagged `FACT[path]` / `ASSUMPTION` / `INTERPRETATION` / `RECOMMENDATION`.

Final message: the per-defect table, the line-count total, the five H artifacts with hashes, the
test count and `OK`, the manifest/fs-watch/orphan verdicts, the unsigned-root statement, then the
§0.2 line. Do **not** start Gate 5 visual work — that follows only after the reviewer's Gate 4b verdict.
