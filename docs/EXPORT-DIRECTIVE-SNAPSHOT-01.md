# EXPORT-DIRECTIVE-SNAPSHOT-01 — Source + snapshot export, SWS-UI-001 v1.2 (accepted)

| Field | Value |
|---|---|
| Status of the project | **Accepted.** Gate 6 PASS (operator, 2026-08-24T17:05:14Z). Ledger sha256 `518ac84ce6a2b55b0c2d2f0bdcbd4dcd64886669012e1354432c28df6ef28085`. |
| Nature of this task | **Export only.** Read the accepted tree, copy it into a new archive, verify the copy. Nothing is built, fixed, refactored, or improved. |
| Authorization | Operator instruction in session, logged verbatim with UTC in `evidence/OPERATOR-INSTRUCTIONS.log`. |
| Envelope | `AGENTS.md` binds in full. **Zero** modifications to `shell/**`, `docs/**`, `evidence/**`, `modules/**`, the ledger, or any protected tree. The only writes permitted are new files under `dist/`. No `git init/commit/push`. No package managers. No module launches. |

## 1. What to produce, under `dist/` only

| # | Artifact | Contents |
|---|---|---|
| A1 | `dist/sws-ui-001-v1.2-source.zip` | The complete `shell/` tree — `src/`, `static/`, `tests/`, `modules/`, `README.md`, `BUILD-MANIFEST.txt` — **excluding** `__pycache__/**`. This is the runnable application. |
| A2 | `dist/sws-ui-001-v1.2-full.zip` | A1's contents plus: `BUILD-DIRECTIVE-SWS-UI-001.md`, `AGENTS.md`, `docs/THEME-BASELINE-v2.md`, `docs/THEME-BASELINE.md`, `docs/DISCOVERY.md`, `docs/ADR-001..005*.md`, `docs/REVIEW-BUILD-06.md`, `docs/REM-03-REPORT.md`, `evidence/GATE-LEDGER.json`, and the eight PNGs plus `b7-dom.txt` from `evidence/loop5/screenshots/`. |
| A3 | `dist/SOURCE-BUNDLE.md` | Every file in A1 concatenated as fenced code blocks, each preceded by its repo-relative path, byte size, and sha256 — a single human-readable read-through of the source. Order: `src/`, then `static/`, then `modules/`, then `tests/`, then `README.md`. |
| A4 | `dist/SNAPSHOT-MANIFEST.txt` | `# utc:` / `# producer:` headers, then: the Gate 6 ledger hash; each archive's path, byte size and sha256; a line per file inside A1 with its sha256; and the verification result from §2. |
| A5 | `dist/README-SNAPSHOT.md` | Short plain-language page: what this is, what the four cards do, how to run it (`py -3.12 -m shell.src` from the workspace root, then `http://127.0.0.1:5180`), how to run the tests, and the three known cosmetic issues from `docs/REVIEW-BUILD-06.md` §4 stated plainly. |

## 2. Verification — the export must prove it is faithful

1. Before archiving, recompute the sha256 of every entry listed in `shell/BUILD-MANIFEST.txt` against the live file. All 40 must match. Any mismatch → STOP, write `dist/EXPORT-STOP.md` naming the files, change nothing.
2. After writing each zip, extract it to a temporary directory under `dist/_verify/`, recompute sha256 for every extracted file, and assert byte-identity with the live source. Record the pass/fail per file in A4.
3. Assert `shell/static/app.css` is `329a52a175da7ccb37909b5fbfa009dd2f444a9f4d2a1b748ee86c2080ecb8ab` (the accepted v2 theme) and that `docs/THEME-BASELINE-v2.md` is present in A2.
4. Delete `dist/_verify/` when done. Leave the zips and the four documents.
5. Re-hash `evidence/GATE-LEDGER.json` and assert it still equals `518ac84c…8085` — proof this export changed nothing.

## 3. Method notes

- PowerShell `Compress-Archive` is acceptable; if it is unavailable use `py -3.12` with `zipfile` and `PYTHONDONTWRITEBYTECODE=1`. Either way, exclude `__pycache__`.
- Archives are freshly created, never appended to an existing zip.
- Paths inside the zips are relative, with `shell/` as the top-level folder so the tree extracts self-contained.
- Every document created carries `# utc: <true UTC>` and `# producer: <agent> EXPORT-01` as its first two lines, and hashes are full 64-hex lowercase.

## 4. Final message

Report: the four `dist/` paths with sizes and sha256; the 40/40 manifest check; the extract-and-compare result; and the post-export ledger hash. Then, since no gate is involved:

`BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.`
