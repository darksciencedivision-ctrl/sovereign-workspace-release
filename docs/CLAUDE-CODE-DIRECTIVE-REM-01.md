# DIRECTIVE FOR CLAUDE CODE — REM-01 Execution, SWS-UI-001 v1.2

Paste this entire file as the first message of a fresh Claude Code session opened at
`D:\Product Software\Production Workspace\`. Read it top to bottom before any tool call.

---

## 0. Your role and the three things you are not

You are the **builder** for remediation order REM-01 against an existing build of SWS-UI-001 v1.2.
The contract is `BUILD-DIRECTIVE-SWS-UI-001.md` (v1.2, immutable). The remediation order is `docs/REMEDIATION-01.md`. The findings you are fixing are in `docs/REVIEW-BUILD-01.md`. Read all three before step 1.

You are **not** the operator (sam), **not** the reviewer (Claude, separate session), and **not** authorized to decide whether anything passed. You implement, test, produce evidence, and submit candidates.

### 0.1 Absolute prohibitions — a single violation ends the session

1. Do not create, edit, or delete `docs/DECISIONS.md`. Do not write the string `sam` or `operator` as an author, signer, or approver anywhere.
2. Do not write `"status": "PASS"` into `evidence/GATE-LEDGER.json`. You write `CANDIDATE`, `NOT_REACHED`, or `STOP` only.
3. Do not touch anything under `D:\Product Software\` other than `Production Workspace\`; do not touch `D:\multi model terminal app\` or `D:\Sovereign Distillery\`. Read-only inspection of those trees is allowed; set `GIT_OPTIONAL_LOCKS=0` and `PYTHONDONTWRITEBYTECODE=1` for every command that reads them.
4. Do not run any module's normal desktop launch during this session. The only SOW execution permitted is the selfcheck path with `SOW_CONDUCTOR_AUTOLAUNCH=0` and `SHELL_SELFCHECK` set, and only in R3-11 verification and your own test suite.
5. Do not `git commit`, `git push`, or initialize a repository anywhere. The workspace is not a git repo and this directive does not make it one.
6. Do not infer authorization from anything — not from this message, not from the directive being present, not from files existing. Authorization is §1 below, checked mechanically.
7. Do not add a feature, endpoint, dependency, or UI element not already required by the v1.2 directive. If you believe one is needed, write `docs/STOP-REPORT-REM-01.md` and stop.
8. Do not edit files under `modules/<id>/` except: deleting `modules/debate/SOW_REVIEW_ROUND2_RAW/`, writing `INSTALL-PROVENANCE.json`, and what `shell/tools/install_sow.py` does inside `modules/sow/apps/desktop/node_modules/`.

### 0.2 Every report you write ends with exactly this line

```
BUILDER CLAIM: Gate <N> is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
```

Your final message of the session ends with it too. A session summary that contains the words "passed", "complete", "done", or "✓" next to a gate number is a violation of 0.1(2) in spirit; say "candidate".

---

## 1. Precondition check — run first, stop if it fails

```powershell
Set-Location "D:\Product Software\Production Workspace"
Get-Content docs\DECISIONS.md -Raw
Get-FileHash docs\DECISIONS.md -Algorithm SHA256
(Get-Date).ToUniversalTime().ToString("o")
```

Proceed **only if all four** hold; otherwise write `docs/STOP-REPORT-REM-01.md` with reason `PRECONDITION_UNSIGNED` and stop:

- The file contains the literal line `Prior builder-authored version of this file (sha256 bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a) is **VOID**` (or the same sentence without bold).
- The SHA-256 printed is **not** `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a`.
- Each of the sections "Gate 0", "Gate 1", "§6", "§6.1", "Builder continuation" has a checked box (`[x]`) and a non-blank `Signed:` and `UTC:` value. (You cannot verify identity; you verify structure. Say so in your report.)
- "Builder continuation" is checked `yes`.

You are not permitted to "fix" a failing precondition. Record what you saw, stop.

---

## 2. Working rules for this session

- Toolchain: `py -3.12` for all Python. Never bare `python` (it is 3.14 on this host). Node 24 / npm 11 for SOW only.
- Every evidence file you create starts with a header line `# utc: <(Get-Date).ToUniversalTime().ToString("o")>` and `# producer: claude-code REM-01`.
- Every hash you write anywhere is the full 64-hex SHA-256. Never truncate, never write "not hashed".
- Every path you write into the ledger must exist at the moment you write it. Verify with `Test-Path` before writing.
- Prefer `Edit` over rewriting whole files. When you must rewrite a file, state why in the report.
- After each stage (R1, R2, R3) write `docs/REM-01-STAGE-R<n>-REPORT.md` with the HC-10 labels (`FACT[path]`, `ASSUMPTION`, `INTERPRETATION`, `RECOMMENDATION`) and the §0.2 closing line. Then **stop and wait** for the operator to say "continue R<n+1>". Do not roll into the next stage on your own.

---

## 3. Stage R1 — Authority chain reconstruction

R1-1. Append to `evidence/phase2-install.txt`:
```
## RE-AUTHORIZATION (REM-01)
# utc: <now>
DECISIONS.md sha256 (operator-signed): <64 hex from §1>
Prior line "bb911905…" above is VOID — builder-authored, never an authorization.
```
Do not delete the original hash line.

R1-2. Replace `evidence/GATE-LEDGER.json` entirely with the REM-01 §3 schema. Gates 0 and 1: `"status": "CANDIDATE"`, `"claimed_by": "builder"`, `"evaluated_by": null`, `"authorized_by": "operator"`, evidence = `docs/DECISIONS.md` with full hash and the UTC value copied from the operator's signature block. Gates 2–6: `NOT_REACHED`. `manifest_tool_sha256` = `Get-FileHash evidence\tools\manifest.py`.

R1-3. Write `docs/REM-01-STAGE-R1-REPORT.md`. Stop.

---

## 4. Stage R2 — Phase 2/3 integrity repair

R2-1. **ADR-005.** `docs/ADR-005-sow-install-and-electron-provisioning.md` with sections Context / Decision / Alternatives / Consequences / Evidence / `Reversible: yes|no`. Content must be grounded in what is on disk now: inspect `modules/sow/apps/desktop/node_modules/electron/` (`path.txt`, `dist/version`, `dist/electron.exe` size and SHA-256), `node_modules/node-pty/prebuilds/`, and the npm cache location of the Electron zip (`$env:LOCALAPPDATA\electron\Cache\` or as found — record the actual path and the zip's SHA-256). State the npm 11 lifecycle-script policy as observed, not as remembered.

R2-2. **`shell/tools/install_sow.py`** (stdlib only). Behaviour, in order: verify cwd is `modules/sow/apps/desktop`; run `npm ci --ignore-scripts` via `subprocess.run([... "npm.cmd" is NOT allowed ...])` — resolve the absolute `node.exe` and invoke npm as `[node_exe, npm_cli_js, "ci", "--ignore-scripts"]` where `npm_cli_js` is `<node dir>\node_modules\npm\bin\npm-cli.js`; locate or download the Electron zip matching `node_modules/electron/package.json` version, verify its SHA-256 against the value ADR-005 records (first run may record it; subsequent runs must match); extract to `dist/`; write `path.txt` = `electron.exe` and `dist/version`; verify `node_modules/node-pty/prebuilds/win32-x64/` contains a loadable `.node` by running `[node_exe, "-e", "require('node-pty')"]`; log every step to `evidence/phase2-sow-install.txt`; exit non-zero on any mismatch. Run it once now and keep the log.

R2-3. **Debate contamination.** `Remove-Item -Recurse modules\debate\SOW_REVIEW_ROUND2_RAW`. Then run the module's own verifier from `modules/debate`:
```powershell
.\.venv\Scripts\python.exe -c "import hashlib,json,pathlib,sys; r=pathlib.Path('.'); m=json.loads((r/'MANIFEST-SHA256.json').read_text(encoding='utf-8')); bad=[e['path'] for e in m['files'] if not (r/e['path']).is_file() or hashlib.sha256((r/e['path']).read_bytes()).hexdigest()!=e['sha256']]; print(len(m['files']),'checked',len(bad),'mismatches'); print(*bad,sep='\n'); sys.exit(bool(bad))"
```
Save output to `evidence/phase2-debate-verify.txt`. Also list any file in `modules/debate` not in the manifest (expect `.venv`, `INSTALL-PROVENANCE.json`, `__pycache__` only) and record it. Record origin of the removed folder as `UNKNOWN` unless a prior log proves otherwise — do not guess.

R2-4. **Provenance hashes.** In all three `INSTALL-PROVENANCE.json`: replace every non-hash string in a `*_sha256` field with a real hash or remove the field. Add `electron_zip_sha256` to SOW. Add `"producer": "claude-code REM-01"` and `"updated_utc"`.

R2-5. **Git capture split.** From `D:\multi model terminal app\sovereign-orchestration-workspace` with `$env:GIT_OPTIONAL_LOCKS=0`: write `evidence/sow-git-after.body` containing, in this order with `### ` section headers and no timestamps: `git rev-parse HEAD`, `git status --porcelain=v1 -z` (raw bytes), `git diff --binary`, `git diff --cached --binary`. Write `evidence/sow-git-after.meta.json` with `utc`, `git_optional_locks`, `dirty_tracked` (bool), `dirty_untracked` (bool). Reconstruct `evidence/sow-git-before.body` from the existing `sow-git-before.txt` by stripping its header lines only — do not alter git content. Normalize both bodies (strip BOM, CRLF→LF, keep only the four named sections) and compare → `evidence/sow-git-body-diff.txt`. STOP with `PROTECTED_GIT_STATE_CHANGED` only if HEAD, the status entries, or the diff payload hashes differ. (Amended by REVIEW-BUILD-02 §5.)

R2-6. **Manifest diffs.** Re-run `evidence/tools/manifest.py` for the three protected roots (same exclusions as the before files — read them from the before-file headers), write `manifest-after-*.txt`, and `fc.exe` each pair into `evidence/manifests/manifest-diff-{product-software,sow,distillery}.txt`. All three must be empty of differences. If not, STOP with reason `PROTECTED_SOURCE_CHANGED` and include the diff.

R2-7. **README.** Rewrite `README.md` Install/Run/Test as the from-zero sequence: extract both zips → verify with their own manifests → `py -3.12 -m venv` + pip from `WORKSPACE-RESOLVED-LOCK.txt` (SOVEREIGN) and `requirements.lock.txt` (Debate) → copy SOW source excluding `.git`, `node_modules`, `__pycache__`, `.pytest_cache`, `.sovereign_store` → `py -3.12 shell\tools\install_sow.py` → `py -3.12 -m shell.src` → `py -3.12 -m unittest discover -s shell/tests -v`. Remove "Modules are already installed". The test command must have no precondition sentence.

R2-8. Ledger: Gates 2 and 3 → `CANDIDATE` with evidence entries for every file created above (full hashes, verified paths). Write `docs/REM-01-STAGE-R2-REPORT.md`. Stop.

---

## 5. Stage R3 — Gate 4 engineering

Work items, each with the test name(s) that prove it. Put tests in `shell/tests/test_<area>.py`; keep `test_shell.py` but fix it per R3-1.

R3-1. **Self-hosting tests.** In a shared `shell/tests/_harness.py`: `start_shell()` picks a free loopback port via `socket.bind(("127.0.0.1",0))`, launches `py -3.12 -m shell.src --port <p>` as a subprocess, polls `/api/shell-info` until 200 or 10 s, returns (proc, port, csrf_nonce from the served HTML); `stop_shell()` terminates and waits. `TestServerEndpoints.setUpClass/tearDownClass` use it. No test may assume port 5180.

R3-2. **Fixtures** in `shell/tests/fixtures/`:
- `fixture_http.py --port P --identity {ok|wrong} [--exit-after S] [--unready]`: serves `/` and `/health`; `ok` returns `{"status":"ok","product_version":"fixture"}` and HTML containing `Debate Table`; `wrong` returns `{"status":"ok"}` and HTML without the marker; `--unready` returns 503 on `/health`.
- `fixture_tree.py`: spawns `fixture_leaf.py` as a child, which spawns a grandchild with `creationflags=0x01000000` (CREATE_BREAKAWAY_FROM_JOB); each writes its PID to a file passed in argv; all sleep 120 s.
- `fixture_noisy.py`: prints the sentinel `SWS_SENTINEL_7f3a9c` in every H-8 form (`API_KEY=`, `api-key:`, `token=`, `secret:`, `password=`, `passwd=`, `Authorization: Bearer `, bare `Bearer `, `?api_key=`, `&access_token=`), plus ANSI CSI sequences, a NUL byte, and a 10 KB line.

R3-3. **H-5 canonical containment.** In `shell/src/adapter.py` replace all `startswith` containment with: `_canonical(p)` = `GetFinalPathNameByHandleW` on a handle opened with `FILE_FLAG_BACKUP_SEMANTICS` (fallback `os.path.realpath` only if the path does not yet exist), strip `\\?\`, casefold; containment = `os.path.commonpath([canonical(root), canonical(p)]) == canonical(root)`. Reject UNC (`\\server\`) and device (`\\.\`, `\\?\` in input) **before** canonicalization. Tests in `test_paths.py`: `..` escape, junction escape (create with `subprocess.run(["cmd.exe","/c","mklink","/J",...])` inside a `tempfile` dir — this is test tooling, not a launch vector), case variant accepted as inside, UNC rejected, device path rejected, `D:\root-evil` rejected when root is `D:\root`.

R3-4. **H-6 Job Object.** `test_supervisor.py`: start `fixture_tree.py` via `Supervisor.spawn`; assert three PIDs alive; `stop()`; assert all three dead within `grace_s + 2`. Crash test: run a tiny driver script in a subprocess that spawns the tree via the supervisor then `os._exit(1)`; assert all three PIDs dead within 5 s. Breakaway test: assert the grandchild's PID is in the job (`IsProcessInJob`) — i.e. breakaway failed. `JOB_ASSIGN` test: monkeypatch `AssignProcessToJobObject` to return 0; assert process is terminated and state is `FAILED(JOB_ASSIGN)`.

R3-5. **State machine.** `test_states.py`, one test per §7.4 transition, using `fixture_http.py` with a temporary adapter JSON pointing `argv[0]` at the venv `python.exe` (absolute, `.exe`): `STARTING→READY`; `→FAILED(EXIT)` (`--exit-after 1`); `→FAILED(TIMEOUT)` (`--unready`, timeout 5); `→FAILED(IDENTITY)` (`--identity wrong`); `READY→DEGRADED→READY` (toggle a flag file the fixture reads); `READY→FAILED(EXIT)`; `EXTERNAL` (start fixture outside the supervisor, identity ok → state `EXTERNAL`, Start refused, `open` enabled); `PORT_OCCUPIED_UNRECOGNIZED` (outside, identity wrong); `EXTERNAL→STOPPED` (kill external fixture, re-probe).

R3-6. **H-7 / H-9 / H-10.** `test_hardening.py`: two Starts within 2 s → second returns 429; fifth concurrent managed process refused; shell process exit leaves an externally started fixture alive (H-9); compile the `sow` adapter, mutate `env_set` after compile, call the spawn path → assert it aborts before `CreateProcessW` (mock it and assert not called) and records `QUOTA_GUARD`.

R3-7. **H-8 four surfaces.** `test_redaction_surfaces.py`: run `fixture_noisy.py` under the supervisor via the self-hosted shell; after exit assert `SWS_SENTINEL_7f3a9c` is absent from `/api/logs/<id>`, from the ring buffer object, from the startup-test JSON, and from every file under `evidence/` modified during the test (snapshot mtimes before/after). Assert `[REDACTED]` count ≥ 10.

R3-8. **H-11.** Make `shell/src` importable as a package with absolute imports (`from shell.src import adapter`). Prove: (1) no `requirements.txt`/`pyproject` runtime deps — write `evidence/hardening/deps-proof.txt` §1 by listing; (2) static import inventory: `py -3.12 -c` script that walks `shell/src/*.py`, parses with `ast`, collects top-level import names, and checks each against `sys.stdlib_module_names` or `shell`; (3) `py -3.12 -I -S -B <abs path>\shell\src\__main__.py --port <free> --selftest` (or `-E -S -B -m shell.src`) must serve one request to `/` and exit 0 (`--selftest` is a proof hook, not a feature: it serves exactly one request, then prints and exits; document it as such in the README's Test section); (4) inside that same `--selftest` run, before exiting, iterate `sys.modules` and assert no module's `__file__` contains `site-packages`; print the count checked. Do **not** add any HTTP endpoint for this. Capture the full `--selftest` stdout into `deps-proof.txt` §3–4.

R3-9. **H-12.** `shell/tests/_fswatch.py` using `ReadDirectoryChangesW` via ctypes on the three protected roots during the whole suite (start in `_harness`, stop at the end); any event → test failure and `evidence/hardening/fs-watch.txt` lists it. Empty file with header = pass.

R3-10. **H-2 origin.** `server.py`: for every non-GET: `Host` header must be present and equal `127.0.0.1:<actual port>`; `Origin` must be present and equal `http://127.0.0.1:<actual port>`; `Content-Type` must be `application/json`; `Content-Length` ≤ 16384; else 403/400 before reading the body. Remove all `Access-Control-*` headers. Tests for each negative.

R3-11. **SOW adapter = ADR-004.** Extend `schema.json` with an optional `startup_test` object (`additionalProperties:false`) containing `env_set` and `readiness` (`kind: receipt_file`, `path`, `require` object). Add to `sow.json`:
```json
"startup_test": {
  "env_set": { "SHELL_SELFCHECK": "1" },
  "readiness": { "kind": "receipt_file",
                 "path": "${root}/docs/evidence/receipts/PHASE16A_SELFCHECK.json",
                 "require": { "ok": true }, "timeout_s": 90, "poll_ms": 1000 } }
```
Confirm `<CONFIRMED-NAME>` by reading `modules/sow/apps/desktop/selfcheck/run.js` and `main.js` for what `SHELL_SELFCHECK=1` actually writes; cite `path:line` in ADR-004 (append an "Encoded" section; do not rewrite the ADR). `startup_test.py` merges `startup_test.env_set` over `launch.env_set` and uses `startup_test.readiness` when present. Replace `identity.kind: process_path` with `process_image`: compare `_canonical(QueryFullProcessImageNameW(pid))` to `_canonical(compiled argv[0])` for equality. Update schema enums. Run one real SOW startup test through this path, with the receipt as evidence, **only** after all other R3 tests pass, and capture stdout showing autolaunch disabled.

R3-12. **Captures and regeneration.** `evidence/hardening/h1-listen.txt` (`Get-NetTCPConnection -State Listen -LocalPort <port>` while the shell runs), `h3-headers.txt` (`curl.exe -si http://127.0.0.1:<port>/`), `deps-proof.txt`, `fs-watch.txt`, `h6-jobobject.txt` (test output subset), `h8-sentinel.txt`. `shell/BUILD-MANIFEST.txt` = sorted `sha256  relpath` of every file under `shell/` excluding `__pycache__`, generated by the test command. `evidence/test-run.txt` = the output of **exactly** the README test command, run from a fresh PowerShell with no shell instance running, and it must end with `OK`. Add `-B` or set `PYTHONDONTWRITEBYTECODE=1` in the README test command so `__pycache__` stops appearing under `shell/`.

R3-13. Ledger: Gate 4 → `CANDIDATE` with every artifact above. Write `docs/REM-01-STAGE-R3-REPORT.md` including a table mapping H-1…H-12 → test name(s) → artifact path. Stop.

---

## 6. Stop conditions (write `docs/STOP-REPORT-REM-01.md`, then stop)

`PRECONDITION_UNSIGNED` · `PROTECTED_SOURCE_CHANGED` · `PROTECTED_GIT_STATE_CHANGED` · `ELECTRON_ZIP_UNVERIFIABLE` · `SELFCHECK_RECEIPT_UNCONFIRMED` (cannot find what `SHELL_SELFCHECK=1` writes) · `JOB_OBJECT_TEST_IMPOSSIBLE` (e.g., host policy blocks job assignment) · `DEBATE_VERIFY_FAILED` · any instruction here that would require violating §0.1 · any ambiguity you would otherwise resolve by guessing.

STOP-REPORT contents: reason code, what you observed (`FACT[path]`), what you did not do, 2–3 options for the operator. Then the §0.2 line with the current stage's gate number.

---

## 7. What the reviewer will do with your output

The reviewer re-runs the README test command and the manifest diffs independently, reads every `evidence/hardening/` artifact against §7.6 of the directive, greps your reports for unlabeled claims, and checks the ledger for any `PASS` you wrote. Optimize for that reader: short, labeled, traceable, boring.


---

## 8. Round-2 addendum (REVIEW-BUILD-02) — Gate 4 resubmission items

G4-1 regenerate `evidence/hardening/fs-watch.txt` from a full README test run; the watcher must refuse to overwrite with a shorter window. G4-2 fixture startup records go to a temp evidence root; delete the twelve `noisy-*.json`. G4-3 add `shell/tests/test_frontend.py` (static grep of `shell/static/*.js` for `innerHTML|outerHTML|insertAdjacentHTML|eval\(|new Function|document.write`, zero hits; plus a `<script>` log line round-trip asserting JSON escaping) and `evidence/hardening/h4-dom.txt`. Then a fresh `test-run.txt` ending `OK`, ledger Gate 4 → `CANDIDATE` again.
