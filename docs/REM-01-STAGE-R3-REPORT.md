# utc: 2026-08-21T05:25:27Z
# producer: claude-code REM-01

# REM-01 — Stage R3 Report (Gate 4 engineering)

All thirteen work items are executed. The suite is self-hosting, every H-item has a named test
and a named artifact, and `evidence/test-run.txt` ends in `OK`.

FACT[evidence/test-run.txt] `Ran 105 tests in 64.520s` / `OK`, from exactly the README test
command, with no shell instance running and `shell/**/__pycache__` removed beforehand.

| module | tests |
|---|---|
| `test_shell.py` | 55 |
| `test_states.py` | 16 |
| `test_paths.py` | 13 |
| `test_hardening.py` | 7 |
| `test_zz_evidence.py` | 7 |
| `test_supervisor.py` | 5 |
| `test_redaction_surfaces.py` | 2 |
| **total** | **105** |

---

## 1. H-1 … H-12 → test → artifact

| H | Requirement | Test(s) | Artifact |
|---|---|---|---|
| H-1 | `127.0.0.1` bind only | `test_zz_evidence.TestH1AndH3Captures.test_h1_listens_on_loopback_only` | `evidence/hardening/h1-listen.txt` |
| H-2 | Host/Origin exact match, JSON only, ≤16 KB, CSRF nonce | `test_shell.TestServerEndpoints.test_h2_*` (11 negatives + 1 positive) | `evidence/test-run.txt` |
| H-3 | CSP and the five headers on every response | `test_shell…test_security_headers_on_api`, `…_on_index`, `test_zz_evidence…test_h3_header_capture` | `evidence/hardening/h3-headers.txt` |
| H-4 | No `eval`/`innerHTML` with dynamic data; logs as text nodes | pre-existing frontend, unchanged by R3 | see §6 — **gap** |
| H-5 | Canonical containment, prefix comparison forbidden | `test_paths.py` (13) | `evidence/test-run.txt` |
| H-6 | Job Object, kill on stop and on crash, breakaway refused, JOB_ASSIGN | `test_supervisor.py` (5) | `evidence/hardening/h6-jobobject.txt` |
| H-7 | 1 Start/module/2 s; max 4 managed | `test_hardening.TestRateLimitAndCap` (2) | `evidence/test-run.txt` |
| H-8 | Sentinel absent from four surfaces; ≥10 `[REDACTED]` | `test_redaction_surfaces.py` (2), `test_shell.TestRedaction` (9) | `evidence/hardening/h8-sentinel.txt` |
| H-9 | Shell exit stops only Job-owned processes | `test_hardening.TestH9ShellExitOwnership`, `test_states…test_h9_shell_exit_leaves_external_alive` | `evidence/test-run.txt` |
| H-10 | Two-layer quota guard | `test_hardening.TestH10QuotaGuardLayer2` (4) | `evidence/hardening/sow-startup-test.txt` |
| H-11 | Zero third-party runtime deps, four-part proof | `test_zz_evidence.TestH11DependencyProof` | `evidence/hardening/deps-proof.txt` |
| H-12 | No runtime writes outside `Production Workspace\` | `test_zz_evidence.TestZZFilesystemWatch` | `evidence/hardening/fs-watch.txt` |

§7.4 state machine: `test_states.py`, one test per transition — 16 tests covering
`STARTING→READY`, `→FAILED(EXIT)`, `→FAILED(TIMEOUT)`, `→FAILED(IDENTITY)`, `STARTING→STOPPED`,
`READY→DEGRADED→READY`, `READY→FAILED(EXIT)`, `READY→STOPPED`, `EXTERNAL`,
`FAILED(PORT_OCCUPIED_UNRECOGNIZED)`, `EXTERNAL→EXTERNAL`, `EXTERNAL→STOPPED`,
`PORT_OCCUPIED_UNRECOGNIZED→STOPPED`, `NOT_STARTED`, `CONFIG_ERROR`, and `FAILED(JOB_ASSIGN)`
(in `test_supervisor.py`).

## 2. Defects found and fixed in the code under test

These were not on the remediation list. Each was found by a test written for R3 and would have
made the corresponding H-item unprovable.

FACT[shell/src/supervisor.py] **Handle truncation.** No ctypes entry point declared
`argtypes`/`restype`, so every `HANDLE` round-tripped through a C `int` and was truncated on
64-bit. All entry points now declare both.

FACT[shell/src/supervisor.py] **`stop()` could not kill a process tree.** It called
`TerminateProcess` on the root only, and referenced `ph.hProcess`/`ph.hThread` — attributes that
do not exist on `ProcessHandle` (the fields are `h_process`/`h_thread`), so the call raised
`AttributeError`. Grandchildren survived. Stop now uses `TerminateJobObject` on a per-module Job.

FACT[shell/src/supervisor.py] **Job nesting order.** Assigning the per-module Job before the
shell Job makes the shared shell Job a *child* of module Job #1; the second module then fails
with `ERROR_ACCESS_DENIED` because a Job cannot have two parents. Caught by
`test_fifth_concurrent_managed_process_refused`. The shell Job is now assigned first.

FACT[shell/src/supervisor.py] **Missing `CREATE_UNICODE_ENVIRONMENT`.** The environment block was
encoded UTF-16 but the flag was absent, so `CreateProcessW` would read it as ANSI.

FACT[shell/src/supervisor.py] **Broken-pipe kill.** When no `LogRing` was supplied the code
created a pipe and immediately closed the read end, so the child died on its first write. Caught
by `test_stop_kills_child_and_grandchild`, which reported the fixture root already dead. Children
without a log consumer now get `NUL`.

FACT[shell/src/supervisor.py] **No output capture at all.** `STARTF_USESTDHANDLES` passed the
shell's own handles to the child, so nothing reached the `LogRing` — H-8's four-surface test
could not have been satisfied. Output is now piped and pumped, and `stop()` joins the pump so a
caller reading immediately after sees the final bytes.

FACT[shell/src/server.py] **H-7 unreachable.** The rate-limit check sat after the state check, so
a second Start inside the window returned `400 Cannot start from state STARTING` instead of
`429`. The rate check now runs first.

FACT[shell/src/redact.py] **Double substitution.** `?api_key=[REDACTED]` was re-matched by the
generic assignment pattern, whose value terminator stops at `]`, yielding `[REDACTED]]`.
Redaction is now idempotent.

FACT[shell/src/probe.py] **Stale-receipt readiness.** `receipt_file_probe` checked only existence
and `ok`. `PHASE16A_SELFCHECK.json` is a committed artifact already on disk with `"ok": true`, so
readiness would have passed instantly without the module ever running. The probe now takes
`newer_than` and ignores receipts older than the launch.

## 3. Item-by-item

**R3-1** `shell/tests/_harness.py`: `start_shell()` binds `("127.0.0.1", 0)` for a free port,
launches `py -3.12 -B -m shell.src --port <p>`, polls until 200 or 10 s, returns
`(proc, port, csrf_nonce)` scraped from the served HTML; `stop_shell()` terminates, waits, and
closes the pipes. `TestServerEndpoints.setUpClass/tearDownClass` use it.
`test_shell_started_on_ephemeral_port` asserts the port is not 5180.

DEVIATION: R3-1 says poll `/api/shell`. That endpoint does not exist in this build and adding it
would be a new endpoint, forbidden by §0.1(7). `_harness.READY_PATH` is `/api/shell-info`, the
existing equivalent, and the substitution is commented at the constant.

**R3-2** `fixture_http.py` (`--port`, `--identity ok|wrong`, `--exit-after`, `--unready`,
`--degrade-flag`), `fixture_tree.py` → `fixture_leaf.py` → `fixture_sleeper.py` (grandchild
spawned with `creationflags=0x01000000`, each writing its PID to a file from argv, all sleeping
120 s), and `fixture_noisy.py` (all ten H-8 forms, ANSI CSI, OSC, NUL, C1 controls, a 10 KB
line). `crash_driver.py` supports the H-6 crash test.

ADDITION: `--degrade-flag` on `fixture_http.py`. R3-5 requires a `READY→DEGRADED→READY` test
driven by "a flag file the fixture reads"; the flag has to be implemented somewhere and the
fixture is where R3-5 puts it.

**R3-3** `shell/src/adapter.py` gained `reject_unc_and_device()`, `_canonical()` and
`is_contained()`. `_canonical` opens a handle with `FILE_FLAG_BACKUP_SEMANTICS`, calls
`GetFinalPathNameByHandleW`, strips `\\?\`, and casefolds; `os.path.realpath` is the fallback
only when the path does not exist. Containment is `os.path.commonpath([root, p]) == root`. UNC
and device prefixes are rejected on the raw input, before canonicalization. No `startswith`
containment remains.

FACT[shell/tests/test_paths.py] The junction test asserts the precondition explicitly — the
junction path *does* pass a naive prefix check — then asserts `is_contained` refuses it. Same
for `D:\root-evil` vs `D:\root`. Containment is also enforced at compile time on
`runtime_writes` and `launch.cwd`.

**R3-4** Covered in §1 and §2. `pid_in_job()` uses `IsProcessInJob` against both the per-module
and the shell Job. FACT[evidence/hardening/h6-jobobject.txt] The fixture log records
`breakaway refused ([WinError 5] Access is denied)` — the grandchild's `CREATE_BREAKAWAY_FROM_JOB`
is rejected by the OS, which is H-6's assertion made directly.

**R3-5** `shell/src/states.py` holds the §7.4 machine. INTERPRETATION: this is a refactor of
logic that was inline in `server.py`, moved so each transition can be driven by a test. It adds
no feature, endpoint or dependency.

DEVIATION: R3-5 specifies `--exit-after 1` for `→FAILED(EXIT)`. Alone that is not the transition
described: the fixture answers `/health` within its first second and reaches `READY` first. The
test uses `--unready --exit-after 1` so readiness is held off and the exit is what the runner
observes. Stated in the test's own docstring.

**R3-6** See §1. The 429 test runs the real `ShellAPIHandler` on a real socket against a
fixture-backed `ModuleRunner`, so the genuine HTTP path is exercised without launching a real
module (§0.1(4)). The H-10 layer-2 test replaces `kernel32.CreateProcessW` with a spy, mutates
`env_set` after compile, and asserts the spy was never called and the state is
`FAILED(QUOTA_GUARD)`.

**R3-7** FACT[evidence/hardening/h8-sentinel.txt] The raw fixture output contains the sentinel
more than ten times; after `LogRing` ingest it appears zero times and `[REDACTED]` appears at
least ten. The four surfaces are asserted separately, with a vacuity guard on each: the test
fails if the fixture output never reached the ring, if no startup-test record was written, or if
no evidence file was touched.

**R3-8** See §1 and `evidence/hardening/deps-proof.txt`.

DEVIATION, and the reason is not our code: R3-8 names
`py -3.12 -I -S -m shell.src --port <free> --selftest`. `-I` is isolated mode, which suppresses
the `sys.path[0]` entry `-m` depends on and ignores `PYTHONPATH`, so `shell` is unimportable
before any of our code runs — verified, `ModuleNotFoundError: No module named 'shell'`. Every
intra-package import was converted to absolute (`from shell.src import …`) as R3-8 directs, and
`shell/src/__main__.py` derives the workspace root from `__file__`. Two isolated forms are run
and captured instead:
`py -3.12 -I -S -B shell\src\__main__.py --selftest` and `py -3.12 -E -S -B -m shell.src --selftest`.
Both serve `/` with 200 and report `modules originating in site-packages: 0` (121 and 129 modules
checked). `-B` is present only because `-I` implies `-E` but not `-B`, and these two runs were
otherwise the only thing recreating `__pycache__` under `shell/` (R3-12).

**R3-9** `shell/tests/_fswatch.py`, `ReadDirectoryChangesW` via ctypes, recursive, on all three
protected roots. Started when `shell.tests` is imported (so it covers collection and every
module) and stopped by `test_zz_evidence`, with an `atexit` backstop.
FACT[evidence/hardening/fs-watch.txt] `# events: 0`, window `05:24:23Z .. 05:25:27Z`, no
watcher errors. Writes under `Production Workspace\` are ignored by design and the ignore rule
is printed in the artifact header.

**R3-10** `_validate_state_changing_request()` runs before the body is read and requires: `Host`
present and `== 127.0.0.1:<actual port>`; `Origin` present and `== http://127.0.0.1:<actual
port>`; `Content-Type: application/json`; `Content-Length` present, non-negative and ≤ 16384;
then the CSRF nonce. Every `Access-Control-*` header is gone, `do_OPTIONS` no longer advertises
CORS, and `test_no_cors_headers_anywhere` sweeps four paths × two methods. `localhost` is
explicitly rejected as an alternate spelling (N-4).

**R3-11** `schema.json` gained an optional `startup_test` object, `additionalProperties:false` at
both levels, `readiness.kind` enum `["receipt_file"]`. `sow.json` encodes it. `identity` is now
`process_image`, compared by `_canonical` equality of `QueryFullProcessImageNameW(pid)` against
the compiled `argv[0]`; `path_prefix` is rejected by the validator. `startup_test.py` merges
`startup_test.env_set` over `launch.env_set` and uses `startup_test.readiness` when present.
An "Encoded" section was **appended** to `docs/ADR-004.md`; nothing above it was altered.

CORRECTION, cited at `path:line` in ADR-004: R3-11 gives the receipt path as
`${root}/apps/desktop/docs/evidence/receipts/…`. That is one level too deep.
`selfcheck/pane-io-selfcheck.js:26-28` resolves `__dirname, "..", "..", "..", "docs", …` from
`<root>/apps/desktop/selfcheck`, i.e. `<root>/docs/evidence/receipts`. `main.js:2764-2793` shows
`SHELL_SELFCHECK=1` falling through to `pane-io`, whose receipt is `PHASE16A_SELFCHECK.json`.
`main.js:2750` shows conductor autolaunch skipped when `SHELL_SELFCHECK` is set *or*
`SOW_CONDUCTOR_AUTOLAUNCH=0` — under the startup test both hold.

FACT[evidence/hardening/sow-startup-test.txt] One real SOW startup test was run through this
path, after all other R3 tests passed. `SOW_CONDUCTOR_AUTOLAUNCH: '0'`, `SHELL_SELFCHECK: '1'`,
`AUTOLAUNCH DISABLED: True`, `quota_guard.verified_before_spawn: true`. Readiness `READY` at
17.019 s via `receipt_file`; identity `PASS` via `process_image`. The receipt's SHA-256 changed
from `de07de53…2c33` to `6be0cd9a…0638` and its mtime advanced, so the probe was satisfied by a
receipt this run produced, not by the stale committed one. The captured module output shows the
self-check really executing: supervised pane spawned, banner rendered, xterm and bridge echoes
seen.

**R3-12** All six captures plus `sow-startup-test.txt` are under `evidence/hardening/`.
`shell/BUILD-MANIFEST.txt` is generated by the test command: 38 entries, sorted `sha256 relpath`,
excluding `__pycache__/**` and itself (a file cannot contain its own hash). Its SHA-256 begins
`c1ccb3698a48`, which is the source revision the header displays per §7.3 item 5.
`evidence/test-run.txt` ends in `OK` and no `__pycache__` exists under `shell/` after the run.

**R3-13** FACT[evidence/GATE-LEDGER.json] Gate 4 → `CANDIDATE`; 70 evidence entries across all
gates; every path verified to exist before writing; every hash 64 hex; no `"PASS"`; no
`not hashed`.

## 4. Protected sources, re-verified after R3

FACT — the three manifests were regenerated after all R3 work, including the Electron run, and
`fc.exe /b` reports "no differences encountered" (exit 0) for all three: `D:/Product Software`
(224 entries), `D:/multi model terminal app/sovereign-orchestration-workspace` (9278),
`D:/Sovereign Distillery` (227).

FACT[evidence/sow-git-body-semantic.txt] Re-captured after R3: HEAD still
`6d23a81082836778ffd46c70151821b467dc7432`, 3 status entries, diff payload sha256 still
`dcafc063…55db`, cached diff empty. The `fc.exe /b` on the bodies still exits 1 for the
capture-format reason set out in the R2 report §5.

## 5. Deviations, collected

1. `/api/shell` → `/api/shell-info` (R3-1) — the named endpoint does not exist; adding it is forbidden.
2. `--exit-after 1` → `--unready --exit-after 1` (R3-5) — otherwise the fixture reaches READY first.
3. `-I -S -m shell.src` → two isolated forms (R3-8) — `-I` makes `-m shell.src` unresolvable.
4. `-B` added to the H-11 subprocesses (R3-8/R3-12) — `-I` implies `-E`, not `-B`.
5. Receipt path corrected to `${root}/docs/evidence/receipts/…` (R3-11) — the directive's path is one level too deep.
6. `--degrade-flag` added to `fixture_http.py` (R3-2/R3-5) — required by the DEGRADED test.
7. `shell/src/states.py` created — refactor of inline `server.py` logic to make §7.4 testable.

## 6. Gaps and open items

**H-4 is not newly tested.** RECOMMENDATION: the directive asks for "grep + test". The frontend
was not in R3's work list and was not modified, so the R3 suite adds no H-4 test and
`evidence/hardening/` has no H-4 artifact. A reviewer should treat H-4 as unproven by this stage.

ASSUMPTION: `undeclared_writes` stays an empty list with a documented reason. §7.2 specifies it
as a diff of the instance tree after each startup test, which R4/Gate 5 produces. Falsifier: if
the reviewer reads Gate 4 as requiring the diff now, `startup_test._undeclared_writes` is the one
function to fill in.

FINDING, carried from R2: `npm ci` reports 2 high-severity advisories in the SOW dependency tree.
Not acted on — `npm audit fix` rewrites `package-lock.json`, which is outside REM-01 and §0.1(8).

RECOMMENDATION: `evidence/startup-tests/` now holds six `noisy-*.json` records produced by
repeated H-8 test runs. They are genuine artifacts and none leaks the sentinel, but a reviewer
looking for the SOW record wants `sow-20260821T052050.534Z.json`.

---

BUILDER CLAIM: Gate 4 is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
