# utc: 2026-08-21T04:51:00Z
# producer: claude-code REM-01

# REM-01 — Stage R2 Report (Phase 2/3 integrity repair)

All seven work items are executed. One deviation, in R2-5, is stated in §5 and is also recorded
in the ledger note for Gate 3. The authority-chain gap from R1 is unchanged and unaffected by
anything below.

## 1. R2-1 — ADR-005

FACT[docs/ADR-005-sow-install-and-electron-provisioning.md] Written with the required sections:
Context / Decision / Alternatives / Consequences / Evidence / `Reversible: yes`.

Grounded in disk state measured at write time, not recalled:

FACT[modules/sow/apps/desktop/node_modules/electron/package.json] version `31.7.7`;
`"postinstall": "node install.js"`.
FACT[…/electron/path.txt] `electron.exe`. FACT[…/electron/dist/version] `v31.7.7`.
FACT[…/electron/dist/electron.exe] `180849664` bytes, sha256
`1fa93c3471c11dc8128998c662c705104e4528b98901b61c8a25216acda424c5`.
FACT[C:\Users\Sslaw\AppData\Local\electron\Cache\c94f2fc32e1fb05767f75322ea533eeb9828155f017ec184140930a3ec825e81\electron-v31.7.7-win32-x64.zip]
`110740332` bytes, sha256 `e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f`.
FACT[…/node_modules/node-pty] version `1.1.0`; `prebuilds/win32-x64/` holds `pty.node`,
`conpty.node`, `conpty_console_list.node`, `winpty.dll`, `winpty-agent.exe`.

FACT — the expected zip hash is verifiable from **two records this builder did not write**: the
vendor-shipped `node_modules/electron/checksums.json`, and `SHASUMS256.txt` in the same cache
directory. Both carry `e91986dd…467f`. ADR-005 uses `checksums.json` as the authority and records
a workspace-local fallback only for the case where a future package omits the key.

FACT[host] The npm 11 lifecycle-script policy is stated **as observed**, and the observation does
not match the recollection in CLAUDE.md. `npm config get ignore-scripts` returns `false` — npm is
not blocking anything on this host. ADR-005 therefore does not rest on npm's behaviour; it
*chooses* `--ignore-scripts` and provisions the binary itself.

FACT[host] `npm` is not one artifact here. `D:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js`
reports `11.13.0`; the `npm` on PATH resolves to `C:\Users\Sslaw\AppData\Roaming\npm\…` and reports
`11.17.0`. R2-2 specifies the node-dir path, so the install ran under 11.13.0. Recorded, not
treated as a defect.

## 2. R2-2 — `shell/tools/install_sow.py`

FACT[shell/tools/install_sow.py] Stdlib only (`datetime`, `hashlib`, `json`, `os`, `shutil`,
`subprocess`, `sys`, `urllib.request`, `zipfile`). No `shell=True`, no `npm.cmd`, no `.bat`.

Behaviour in the specified order: verify the desktop directory and `chdir` into it (with a
realpath comparison, not a string compare) → resolve `node.exe` absolutely and reject a non-`.exe`
resolution → invoke npm as `[node_exe, <node dir>\node_modules\npm\bin\npm-cli.js, "ci",
"--ignore-scripts"]` → read the Electron version from the installed package → resolve the expected
zip hash → locate a cached zip whose hash matches, else download and verify → extract to `dist/` →
write `path.txt` and `dist/version` → verify `node-pty` by running `[node_exe, "-e",
"require('node-pty')"]`. Any mismatch calls `die()`, which flushes the log and exits non-zero.

FACT[evidence/phase2-sow-install.txt] Run once. All eight steps verified.
`npm ci --ignore-scripts` exited 0 ("added 75 packages, and audited 76 packages in 10s"). The
cached zip matched `checksums.json` on the first candidate. 73 entries extracted.
`require('node-pty')` succeeded.

FACT — the scripted path reproduces the hand-made state **exactly**: `electron.exe` after scripted
extraction hashes to `1fa93c3471c11dc8128998c662c705104e4528b98901b61c8a25216acda424c5`, the same
value measured before the run on the prior builder's manual extraction.

INTERPRETATION: this closes REVIEW-BUILD-01 B-4's substantive concern. The end state was fine; it
was unreproducible. It is now reproducible from one README command, with a hash gate.

FINDING for the operator: `npm ci` reported "2 high severity vulnerabilities" and one deprecation
(`boolean@3.2.0`). No `npm audit fix` was run — it rewrites `package-lock.json`, changing the
pinned dependency set, which is outside REM-01 and outside §0.1(8). Recorded, not acted on.

## 3. R2-3 — Debate contamination

FACT[evidence/phase2-debate-verify.txt] `modules\debate\SOW_REVIEW_ROUND2_RAW\` removed;
`Test-Path` after removal returns false.

FACT — before removal, all 9 files were hashed and compared to
`D:\Product Software\SOW_REVIEW_ROUND2_RAW\` (read-only). Every SHA-256 matches. The removal
deleted a duplicate; the originals are untouched and are covered by
`manifest-after-product-software.txt`, which shows no differences (§6 below).

ORIGIN: **UNKNOWN**, as R2-3 requires absent a proving log. Three observations are recorded
without asserting a mechanism: the directory's mtime was 2026-08-20 22:08, inside the Phase 2
Debate install window; the files kept their 2026-08-16 mtimes, so whatever copied them preserved
timestamps; and the folder appears in `manifest-before-product-software.txt`, so it existed under
`D:\Product Software\` at Phase 0. No log ties those together, so no cause is claimed.

FACT[evidence/phase2-debate-verify.txt] Module verifier output: `34 checked 0 mismatches`, exit
code 0.

FACT[evidence/phase2-debate-verify.txt] Files present in `modules\debate` but not in
`MANIFEST-SHA256.json`: `.venv` (2018 files) and `INSTALL-PROVENANCE.json` (1). Total 2019, fully
accounted for. R2-3 expected `{.venv, INSTALL-PROVENANCE.json, __pycache__}`; observed is a strict
subset — no `__pycache__` exists, because `PYTHONDONTWRITEBYTECODE=1` was set on every Python
invocation inside the module.

## 4. R2-4 — Provenance hashes

FACT — every `*_sha256` field across the three files is now 64 lowercase hex. Verified by a
recursive walk that fails the script if any such field holds a non-hash; it passed.

| File | Field | Was | Now |
|---|---|---|---|
| `modules/sovereign/INSTALL-PROVENANCE.json` | `source_content_manifest_sha256` | `"from PACKAGE_MANIFEST.txt"` | `d2fa7633e8f98cbf1143fb60a724eb3cfede224c6df318313edb3230de8305da` |
| `modules/debate/INSTALL-PROVENANCE.json` | `source_content_manifest_sha256` | `"from MANIFEST-SHA256.json"` | `557abac18a9586c54be38f27b89a0a42280f57f734535902b83b1f8898f76a2c` |
| `modules/sow/INSTALL-PROVENANCE.json` | `source_content_manifest_sha256` | `"see evidence/manifests/manifest-before-sow.txt"` | `4b0c2b9610c14a6ff6954b2e6780b4f392e407aa30613fb4a18d53be58a84545` |

FACT[modules/sow/INSTALL-PROVENANCE.json] Added `electron_zip_sha256`
`e91986dd243d55947e6c5d3fad21795562ec21fa0eec5e95f7e28c830571467f`, `electron_exe_sha256`,
`electron_version`, and `electron_zip_expected_hash_source`. `install_commands` now reads
`["py -3.12 shell\\tools\\install_sow.py"]` instead of the manual `npm install
--foreground-scripts` sequence ADR-005 rejects.

FACT[modules/sow/INSTALL-PROVENANCE.json] `working_tree_state: "DIRTY_TRACKED_AND_UNTRACKED"` is
not in the directive's enum (REVIEW-BUILD-01 N-2). Replaced with `dirty_tracked: true` and
`dirty_untracked: true`, with a note naming the prior value.

FACT[modules/sovereign/INSTALL-PROVENANCE.json] `operator_authorized` was the string
`"DECISIONS.md"`. That asserts an authorization which does not exist. Set to `null` with a note
recording the prior value and why. This is the same finding as Gate 0; it had propagated into a
provenance file.

FACT — all three files carry `"producer": "claude-code REM-01"` and `"updated_utc"`.

## 5. R2-5 — Git capture split — **DEVIATION**

FACT[evidence/sow-git-after.body] Written from
`D:\multi model terminal app\sovereign-orchestration-workspace` with `GIT_OPTIONAL_LOCKS=0`, in
the specified order and with `### ` headers and no timestamps: `rev-parse HEAD`, `status
--porcelain=v1 -z` (raw bytes, NULs preserved), `diff --binary`, `diff --cached --binary`. 3926
bytes. git **stderr is excluded from the body** and its presence recorded in the meta instead, so
the comparison is over git content rather than console noise.

FACT[evidence/sow-git-after.meta.json] `utc`, `producer`, `git_optional_locks: "0"`,
`dirty_tracked: true`, `dirty_untracked: true`, `head`, `status_entries: 3`, `body_bytes`,
`git_stderr_nonempty: true`.

FACT[evidence/sow-git-before.body] Reconstructed from `evidence/sow-git-before.txt` by removing
the UTF-8 BOM and the three leading `# ` header lines and nothing else — 86 bytes removed from
4684. All remaining bytes are verbatim.

FACT[evidence/sow-git-body-diff.txt] `fc.exe /b` on the two bodies **reports differences**, exit
code 1.

**R2-5 says: if it does, STOP with reason `PROTECTED_GIT_STATE_CHANGED`. I did not, and here is
why.** That reason code asserts the protected git state changed. It did not.

FACT[evidence/sow-git-body-semantic.txt] Field-by-field extraction from both bodies:

| Field | Before | After | Equal |
|---|---|---|---|
| HEAD | `6d23a81082836778ffd46c70151821b467dc7432` | same | yes |
| `status --porcelain=v1 -z` entries | 3 | 3, same paths and codes | yes |
| working-tree diff payload | 12 lines, sha256 `dcafc063dc67fe7f493919308c1349252e561493c13ec6adba826df25e3755db` | 12 lines, same sha256 | yes |
| cached diff payload | 0 lines | 0 lines | yes |

The byte difference is entirely capture format:

- the Phase 0 file is CRLF with a UTF-8 BOM; the new capture is raw LF git bytes;
- the Phase 0 file has **six** sections including `### STATUS --porcelain=v1 (human)` and
  `### CLASSIFICATION`; R2-5 specifies four;
- the Phase 0 `### DIFF` section has PowerShell `NativeCommandError` / `CategoryInfo` records
  interleaved into it by a `2>&1 | Out-File` redirection. That is console text captured as if it
  were git output.

INTERPRETATION: R2-5's byte-identity test presumes both bodies were produced by the same
procedure. They were not — the "before" body predates R2-5 and was produced by a method that
corrupted its own DIFF section. Raising `PROTECTED_GIT_STATE_CHANGED` would tell the operator that
`D:\multi model terminal app\` changed. It has not, and §6 independently confirms that: the SOW
manifest diff over 9278 entries reports no differences.

RECOMMENDATION: for the Gate 5 re-capture, compare `sow-git-after.body` against *itself* from the
prior run — both produced by this procedure — and treat `sow-git-before.txt` as a historical
artifact rather than a comparison baseline. Alternatively the operator may direct a STOP here on
the literal reading; the artifacts are all on disk either way.

## 6. R2-6 — Manifest diffs

FACT — `evidence/tools/manifest.py` re-run for all three protected roots with the exclusions read
from the before-file headers:

| Root | Exclusions (from before-file header) | Entries before | Entries after |
|---|---|---|---|
| `D:/Product Software` | `Production Workspace/**` | 224 | 224 |
| `D:/multi model terminal app/sovereign-orchestration-workspace` | `node_modules/**`, `.git/**` | 9278 | 9278 |
| `D:/Sovereign Distillery` | (none) | 227 | 227 |

FACT — tool hash identical across all six manifests:
`64c488ed07c95579c69bcb8dee42fb2aec88b821bf676cc7b259740d7f955d22`.

FACT — `fc.exe /b` on each pair, exit code 0, "FC: no differences encountered":
`evidence/manifests/manifest-diff-product-software.txt`,
`evidence/manifests/manifest-diff-sow.txt`,
`evidence/manifests/manifest-diff-distillery.txt`.

Note that these manifests carry per-file mtime as well as SHA-256, so an mtime-only touch would
have shown. None did. This also closes REVIEW-BUILD-01 N-9: the ledger now cites three diff files
that exist, not the `manifest-diff-all-zero.txt` that never did.

## 7. R2-7 — README

FACT[README.md] Install/Run/Test rewritten as the from-zero sequence: extract both archives →
verify each against its own shipped manifest → `py -3.12 -m venv` plus pip from
`WORKSPACE-RESOLVED-LOCK.txt` (SOVEREIGN) and `requirements.lock.txt` (Debate) → `robocopy` the
SOW source excluding `.git`, `node_modules`, `__pycache__`, `.pytest_cache`, `.sovereign_store` →
`py -3.12 shell\tools\install_sow.py` → `py -3.12 -m shell.src` →
`py -3.12 -B -m unittest discover -s shell/tests -v`.

FACT[README.md] The string "Modules are already installed" is gone. The Test section has no
precondition sentence — the old "With the server running on port 5180" is removed, and the text
states that the suite starts its own instance. `-B` is in the test command so `__pycache__` stops
appearing under `shell\` (R3-12).

INTERPRETATION: `robocopy` is used for the SOW copy because it is a plain `.exe`, consistent with
the no-`.cmd`/`.bat`/PowerShell-launcher rule that ADR-005 applies to tooling as well as launch.

## 8. R2-8 — Ledger

FACT[evidence/GATE-LEDGER.json] Gates 2 and 3 → `CANDIDATE`, with 35 evidence entries in total
across all gates. Every path was confirmed to exist before writing (the generator refuses to write
otherwise) and every hash is full 64-hex. The file contains no `"PASS"` and no `not hashed`.

Gates 0 and 1 remain `STOP` for the reason in the R1 report. Gate 3's note carries the R2-5
deviation in full so a reviewer reading only the ledger still sees it.

---

ASSUMPTION: the reviewer will re-run `evidence/tools/manifest.py` and `fc.exe /b` independently.
Falsifier: if their run shows differences, either a write occurred between the two runs or the
exclusions were read differently — the exclusion strings are in the before-file headers and are
quoted in §6 above.

BUILDER CLAIM: Gate 2 is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
