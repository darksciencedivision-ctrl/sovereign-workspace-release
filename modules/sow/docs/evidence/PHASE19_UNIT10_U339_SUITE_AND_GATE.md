# Phase 19 · unit 19.10 — U339: measured suite contract and Phase 19 gate

**Unit:** `phase-19.10` (`AUTONOMOUS_BUILD_DIRECTIVE.md` §18, U339).
**Entry HEAD:** `ba8cc55fc06cc2a632ce887f3d3b7052136b51be` (iteration 137, 19.9 closed).
**Work commit:** `bad029e76a0bcc2f57062245ccf67ddf9394e47d`.
**Evidence/register commit:** pending until the two cold reviews pass.
**Gate tags:** pending review: `gate/phase-19` and successor `product/governed-live`.
`product/multi-frontier-v2` is not moved.
**Provider/live activity:** zero provider calls, zero Electron launches, zero Sovereign MCP
connections, zero dependency installs.

## 0. Recovery provenance and entry checks

The turn inherited a substantial uncommitted 19.10 tree from a dead predecessor. Every byte was
treated as CANDIDATE material. No receipt, test total, timing, hash pin, or reviewer claim from the
dead turn was adopted.

Entry checks were fresh:

```text
git rev-parse HEAD
ba8cc55fc06cc2a632ce887f3d3b7052136b51be

tools/mutation/*.lock
NO_MUTATION_LOCKS

Win32_Process Name='node.exe'
NO_NODE_PROCESSES
```

The sandboxed `py` launcher exposed only Python 3.14, so the exact import was retried in the
operator context rather than misclassified as a product defect:

```text
py -3.12 -c "import sys; import mcp_server.sovereign_tools; ..."
3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]
IMPORT_OK D:\multi model terminal app\sovereign-orchestration-workspace\mcp_server\sovereign_tools.py
```

The reported MCP handshake failure therefore was not reproduced as an import failure.

## 1. What the work commit closes

### 1.1 Inspectable pytest contract

`pytest.ini`, root `conftest.py`, and `tools/run_phase19_pytest.py` now commit:

- strict marker definitions;
- the exact Phase 19 focused path set;
- measured host-coupled timing-outlier paths;
- the whole-suite wall-clock ceiling;
- a standard-library process-tree wrapper that enforces the ceiling on Windows and POSIX.

The focused and host-coupled markers are applied during collection from those committed path sets.
No plugin or new dependency is required.

### 1.2 Gate preconditions carried from earlier review rounds

The recovery candidate also closes preconditions that U430 and the 19.9 evidence left for 19.10:

- synthesis contribution membership and candidate `content_hash` binding are rechecked inside the
  task write fence, so a candidate committed after the tool's first read cannot be omitted;
- empty `points_of_agreement` is accepted for genuine dissent instead of requiring invented
  agreement;
- launch-ticket and readiness-feed conductor descriptors must agree field by field;
- conductor admission requires the registry-emitted role/registration/capability shape;
- containment verification selects a declared boundary-profile verifier rather than branching on
  an adapter allowlist;
- worker spawn accepts only exact `provider_id` and `model_id` values returned by `list_models`,
  with no hidden vendor aliases or model defaults;
- an adapter with no implemented host model probe reports UNPROBED rather than fabricating model
  availability from registry membership;
- Grok's login instruction is provider-scoped rather than a universal classifier rule;
- readiness-turn count is descriptor data, and the final-turn failure label is not hardcoded to
  exactly two turns.

The four affected mutation baselines carry comments naming the byte change and why their mutation
anchors remain load-bearing.

### 1.3 A stale negative control discovered by the full tree

The first direct full run found
`test_an_amendment_citing_a_ruling_nobody_recorded_is_unattributed` using `OP-13.2` as its invented
ruling. OP-13.2 became real at `d059f01`, so the negative control no longer planted an unattributed
amendment. The test now generates an intentionally remote ruling id and first asserts that the id is
absent from both ruling sources. The manifest comment no longer names the now-real OP-13.2 as its
example. The repaired file passed 34/34 in isolation and in the final full run.

## 2. The candidate ceiling failed — and why

The first candidate committed `phase19_suite_timeout_seconds = 600`. That value was inherited from
the operator's historical invocation narrative, not derived from a completed whole-suite run. This
was the same evidence-class error U337 records: a number with provenance-shaped prose but no
measurement behind it.

The first wrapper run correctly failed its own bad contract:

```text
py -3.12 tools/run_phase19_pytest.py full -- --durations=20
........................................................................ [ 15%]
...............Phase 19 full suite exceeded the committed 600s ceiling
```

The process tree was then checked: no Python or Node process survived. `pytest-timeout` was absent,
the operator denied its installation, and nothing was installed. The suite was not hanging: pytest
collects the slow integration directory before the fast unit directory, and iteration 134 already
recorded the long non-unit subset alone at 613.71 seconds.

The required direct measurement then ran with a 30-minute command bound:

```text
py -3.12 -m pytest tests/ -q --durations=20
FAILED tests/unit/test_node_schema_amendment.py::test_an_amendment_citing_a_ruling_nobody_recorded_is_unattributed
1 failed, 2381 passed, 1 skipped, 61 warnings in 638.34s (0:10:38)
```

That run completed and produced the timing data even though the stale negative control failed. Its
eight clear timing outliers were above 15 seconds; the ninth was 7.17 seconds. `pytest.ini` records
those eight file paths. The ceiling is now 800 seconds: 638.34 + 161.66 seconds, or 25.3% measured
headroom for host variance. The derivation and the failed inherited value are comments beside the
setting, not facts that live only in this report.

The corrected wrapper then demonstrated the committed contract:

```text
py -3.12 tools/run_phase19_pytest.py full -- --durations=20
SKIPPED [1] tests\unit\test_run_frontier_providers_ps1.py:522: host-coupled; set SOW_PROVIDER_HOST_CHECK=1 to run
2382 passed, 1 skipped, 61 warnings in 608.47s (0:10:08)
```

The eight outliers remained above 15 seconds and the ninth was 7.08 seconds:

```text
121.18s tests/integration/test_opencode_candidate_live.py::test_live_drive_then_governed_candidate_and_merge
66.93s  tests/integration/test_opencode_worktree_live.py::test_live_opencode_drives_local_model_in_isolated_worktree
38.36s  tests/integration/test_voice_input.py::test_voice_stack_detection_recorded
37.08s  tests/integration/test_conductor_voice_feed.py::test_select_engine_matches_host_detection_shape
30.14s  tests/integration/test_assembled_roster.py::test_item7_ollama_smoke_runs_live
17.75s  tests/integration/test_wsl_parakeet.py::test_default_runner_streams_the_complete_program_into_real_wsl
15.13s  tests/integration/test_frontier_process_tree.py::test_windows_job_gate_preserves_supported_ascii_lf_text_for_the_target
15.12s  tests/unit/test_no_live_provider_calls_in_suite.py::test_the_managed_boundary_still_runs_a_non_provider_command
7.08s   tests/integration/test_multi_model_adapters.py::test_live_ollama_backend_smoke
```

## 3. Fresh validation on the work bytes

### 3.1 Suites

```text
npm.cmd test                         # apps/desktop, operator context
tests 1020 · pass 1020 · fail 0 · skipped 0

node --test test/*.test.js           # terminal/
tests 216 · pass 216 · fail 0 · skipped 0

py -3.12 tools/run_phase19_pytest.py focused -- --durations=20
417 passed, 1 skipped in 17.31s
SKIPPED [1] tests\unit\test_run_frontier_providers_ps1.py:522: host-coupled; set SOW_PROVIDER_HOST_CHECK=1 to run

py -3.12 tools/run_phase19_pytest.py full -- --durations=20
2382 passed, 1 skipped, 61 warnings in 608.47s (0:10:08)
```

The U438 test
`TestExitCodeContract::test_a_refused_probe_exits_three_and_spends_nothing` passed on the otherwise
idle host in the focused run at 0.57 seconds and again in the full run. The committed contract does
not claim to serialize itself against unrelated external workloads, so U438's historical
concurrent-load failure remains recorded rather than declared impossible.

### 3.2 Four re-pinned mutation harnesses — each run separately

No harness was chained with `;`. Each command had a 20-minute bound.

```text
node tools/mutation/readiness_signal_mutations.js
base .../worker-readiness.js SHA-256 494E01FBF6881F1EA4E840A73EBCC78FE061F96D0D3ED85459CBDA47EE878037
ALL 26 READINESS-SIGNAL MUTATIONS CAUGHT
restored ... BYTE-IDENTICAL

node tools/mutation/orchestration_mutations.js       # operator context for py -3.12 rows
ALL 14 ORCHESTRATION MUTATIONS CAUGHT; every file restored BYTE-IDENTICALLY

node tools/mutation/pane_input_bypass_mutations.js
base main.js SHA-256 D74E32DF6E65CB5D318AB86AF68AB8A64BD5B960C8E79CF9C2F7CEBAF16A93D0
ALL MUTATIONS CAUGHT                                  # 36 rows
restored main.js ... BYTE-IDENTICAL

node tools/mutation/system_pane_write_mutations.js
base main.js SHA-256 D74E32DF6E65CB5D318AB86AF68AB8A64BD5B960C8E79CF9C2F7CEBAF16A93D0
base worker-readiness.js SHA-256 494E01FBF6881F1EA4E840A73EBCC78FE061F96D0D3ED85459CBDA47EE878037
ALL 32 SYSTEM→PANE MUTATIONS CAUGHT
every touched file restored BYTE-IDENTICALLY
```

The readiness pin `494E01FB...`, explicitly declared unearned at entry, is now earned by the
310.3-second completed run.

### 3.3 Integrity and teardown

```text
py -3.12 tools/manifest/compute_manifest.py --check
freeze check OK: no drift in FROZEN set against recorded manifest

git diff --check
[no output]

post-suite process check
NO_PYTHON_OR_NODE_PROCESSES
NO_MUTATION_LOCKS
```

## 4. Carried issue disposition

- **U432:** remains OPEN, narrowed exactly as U442 records. Observed-listening/error reporting, UI
  freshness emphasis, and heartbeat-linked semantics are protocol work, not suite-contract work.
  Owner: next orchestration protocol phase before stronger liveness claims.
- **U434:** remains OPEN. The application still has no server→node ping or periodic heartbeat.
  Owner: next orchestration protocol phase before claiming on-demand verification.
- **U435:** CLOSED by 19.9/U442 (bounded voice-authority shutdown).
- **U436:** CLOSED by 19.9/U442 (pre-create and pre-write assignment refusal).
- **U437:** (a), (b), and (e) are CLOSED; (f) closes here with the fresh full-Python result; (c),
  (d), and (g) are implemented but remain runtime-measurement owed because OP-13.2 forbids an
  Electron launch in this Codex session. Owner: Path A's committed-HEAD application run.
- **U438:** remains OPEN as a historical concurrent-host-load coupling. The named test passes on an
  idle host, but the wrapper does not claim external-workload exclusion. Owner: future test-runner
  isolation work; `tools/loop/run_loop.ps1` remains untouchable without a new operator ruling.
- **U439:** CLOSED by 19.9/U442 (mutation rows require their intended named failing test).
- **U440:** the Phase 19 instance is addressed by a terminating evidence-only review after the two
  cold reviews. Its final verdict is recorded in §6.

## 5. Prohibited-drift audit

- no credential, provider login, provider call, remote, push, purchase, or installation;
- no Electron application launch or Sovereign MCP connection (OP-13.2);
- no `docs/canonical/`, frozen schema, `tools/loop/run_loop.ps1`, or
  `config/live_operation.json` change;
- no existing tag moved;
- no TTS;
- no self-authorization or MCP policy relocation;
- unrelated `.claude/settings.local.json` left untracked and untouched;
- every child process and mutation lock absent at the end of its unit.

## 6. Independent cold reviews

Pending. A FAIL verdict blocks both tags. This section will carry each non-author review verbatim,
followed by a final evidence-only U440 pass over the diff introduced while recording the verdicts.

## 7. Gate conclusion

Pending the two cold reviews and §6's terminating evidence-only pass. Only PASS permits the local
tags `gate/phase-19` and `product/governed-live` on the evidence/register commit. Path A remains the
next step and must run against that committed, tagged HEAD.
