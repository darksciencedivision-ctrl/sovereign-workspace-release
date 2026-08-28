# SOVEREIGN ORCHESTRATION WORKSPACE — INDEPENDENT REVIEW, TARGET-HOST EDITION

**Document id:** SOW_INDEPENDENT_REVIEW_WINDOWS_HOST_20260816
**Reviewer:** Claude (claude-fable-5), Research Validator / Reviewer
**Substrate:** the LIVE working tree at `D:\multi model terminal app\sovereign-orchestration-workspace`, HEAD `bad029e76a0bcc2f57062245ccf67ddf9394e47d`, branch `main`, on the operator's Windows 11 host — with working `git`, `py -3.12`, `node` 24, `npm` 11.
**Date:** 2026-08-16
**Authority:** none. Nothing in the repository was created, modified, or deleted. No live provider CLI was invoked. No git write command was run.

---

## 0. WHAT THIS REVIEW ADDS THAT THE THREE PRIOR REVIEWS COULD NOT

All three earlier reviews (Opus-5 88-finding review; the "Independent Engineering Review"; the "Independent Review" summary) ran in Linux sandboxes over the candidate ZIP. Every Windows-specific claim in them was labelled [UNVERIFIED]; `git` could not run; the JS↔Python integration legs skipped; the freeze check exited 1 for a packaging reason. This review ran **on the target host, over the live tree**, so it can (a) execute those Windows-only predicates, (b) reproduce the recorded suite contract, (c) read the operator-only state the ZIP excluded (`.sovereign_store/`, `~/.codex/config.toml`, `config/live_operation.json` structure), and (d) adjudicate where the three prior reviews disagree.

Six scoped sub-reviewers were launched to widen coverage. Their first round was terminated by a session limit with nothing recoverable; a second round (with incremental on-disk writing) produced five complete reports and one partial. Their raw output is summarised in **§11**; the findings I then re-derived personally by execution are promoted to numbered findings in **§12** (`A-1`…`A-9`), and §12.1 lists what remains reviewer-labelled. Everything in §§1–10 is what I personally read or executed: every claim there is [OBSERVED] on the target host unless labelled otherwise. Where I did not re-verify a prior finding, I say so (§10).

Labels: **[OBSERVED]** I read/ran it here; **[INFERRED]** reasoning from observed code without exercising the trigger; **[UNVERIFIED]** not exercised.

---

## 1. EXECUTED EVIDENCE (this session, this host)

| Action | Result |
|---|---|
| `git rev-parse HEAD` / branch / `git status --porcelain` / tags | `bad029e7`, `main`, **exactly three entries** (M `docs/loop/LOOP_STATE.json`, M `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`, ?? `docs/evidence/PHASE19_UNIT10_U339_SUITE_AND_GATE.md`), 50 tags, `gate/phase-19` absent. Closes the prior turn's [UNVERIFIED] gap. |
| Full Python suite, `py -3.12 -m pytest -q`, detached | **2382 passed / 1 skipped / 0 failed in 720.92 s** (contract in `pytest.ini`: 2381/1/1 in 638 s; 800 s ceiling). Ran under contention from six agents and still inside the ceiling. |
| `node --test apps/desktop/test/*.test.js` | **1020 pass / 0 fail / 0 skipped** (the 28 legs that skipped on Linux — including the stdio MCP handshake — ran and passed here) |
| `node --test terminal/test/*.test.js` | 216 pass / 0 fail |
| `py -3.12 tools/manifest/compute_manifest.py --check` | **freeze check OK** on the live tree (R-20 was package-only) |
| 11 canonical docs | not re-hashed here (prior review verified 11/11; freeze check green covers the frozen set) |
| Electron install state | `apps/desktop/node_modules/electron/dist/electron.exe` (180 MB) + `path.txt` present, 31.7.7; node-pty 1.1.0 prebuilds present (`prebuilds/win32-*`, `build/Release/conpty/`) — the live tree is runnable; F5 is a fresh-`npm ci` problem |
| `npm audit --json` (apps/desktop) | 2 HIGH: `electron` (32 GHSAs rolled up, fix 43.4.0 semver-major) and `extract-zip` (symlink traversal, dev-time) |
| MCP server boot: no env / closed port / wrong cwd | exit 2 in 0.45 s / exit 2 in 2.5 s / **exit 1 `ModuleNotFoundError`** |
| Full stdio MCP session vs stub gateway | see N-01, R-09b, R-11 |
| `.cmd` shim + `subprocess.run` with `&`, `\|`, `^` in an argument | **command injection executed** (N-03) |
| `run_managed_process(["cmd","/c","echo hi"])` ×2 | **15.15 s, 15.12 s** (N-04) |
| `os.replace` while another handle reads the target | `PermissionError [WinError 5]` (R-27 premise) |
| Codex login predicate vs 7 phrasings | R-05 confirmed |
| `parse_antigravity_models` vs 7 inputs | R-06 + R-07 confirmed |
| `live_call_guard.live_provider_name` vs 13 shapes | R-19 confirmed (Windows `.cmd` leg passes here) |
| `git ls-files --eol` + BOM scan | 0 blobs with CRLF; 40 worktree files CRLF/mixed; 3 blobs with BOM |
| Receipts scan (`docs/evidence/receipts/**/*.json`) | 68 `ok:true` / **15 `ok:false`** / 3 no field |
| `.sovereign_store/nodes/node_events.jsonl` | 154 events: `grok_build` 22, `google_antigravity` 20, `claude_code` 0, `openai_codex_cli` 0 |
| `~/.codex/config.toml`, repo `.codex/config.toml`, `.grok/config.toml`, `.agents/mcp_config.json` | read (see N-06) |
| `config/live_operation.json` | structure read (values not reproduced beyond what STATE_OF_THE_WORKSPACE already publishes) |

---

## 2. HEADLINE JUDGEMENT

The three prior reviews converge on the right verdict and I concur: **serious, unusually well-instrumented engineering; not release-ready; Phase 19 gate not earned; the conductor→MCP→worker path is dead; the containment boundary has an open notify path.** I re-derived their top-tier findings on the live tree and every one I checked holds (§3).

What this host-side pass changes:

1. **F2 now has a concrete, reproduced, previously-unknown root-cause candidate that fits the observed asymmetry.** The sovereign MCP server writes JSON-RPC to stdout in the Windows ANSI codepage. Its `tools/list` reply contains two raw `0x97` bytes (cp1252 em dashes) and is **not valid UTF-8**. A strict UTF-8 line reader — which is what Codex's Rust stdio client is — fails on exactly the request Codex issues during MCP startup, after a clean ASCII `initialize`. Node (Claude Code, and the project's own JS stdio test) decodes lossily and never sees it. That is precisely "sovereign initialised for the Node test, not initialised for the Codex conductor" (N-01). The prior review's leading hypothesis (".mcp.json is a Claude Code config; Codex has no sovereign server configured") is **refuted**: the repo tracks `.codex/config.toml` with `[mcp_servers.sovereign]` (N-06).
2. **Two Windows-only claims every prior reviewer left [UNVERIFIED] are now measured, and both are worse than inferred**: the `.cmd`-shim metacharacter injection *executes* even through Python's quoting (N-03); every managed provider call pays a fixed **15 s** Job-Object teardown (N-04).
3. **The suite is reproducible on the target host** (2382/1/0). The prior "the recorded green is not reproducible by anyone" is true off-host and false on-host — the contract is host-coupled, not fictional.
4. **F6 is answered by code, not inference**: `claude_code`/`openai_codex_cli` panes are excluded from node registration *by design* (`_OP12_PANE_NODE_ADAPTERS`), self-declared as owed leg U313. "Governed: YES" for those two in the handoff means leased+supervised, not registered-node.
5. **The most current position documents are not in the repository.** `STATE_OF_THE_WORKSPACE.md`, `README_BASELINE.md`, `PACKAGE_MANIFEST.txt`, `WORKTREE_PROVENANCE.patch` exist only inside the unpromoted ZIP. Anyone opening the repo gets `README.md` ("Phase 1").

---

## 3. ADJUDICATION OF THE PRIOR REVIEWS' CLAIMS (live tree, this host)

Only claims I personally re-derived. IDs are the Opus-5 review's `R-nn`; "Rev-2" is the Independent Engineering Review.

| Claim | Verdict | Evidence on the live tree |
|---|---|---|
| R-01 notify path has no role gate; recipient/message_id caller-controlled; conductor pane reachable | **CONFIRMED**, one narrowing | `application-control.js:285-306` no `requireControlRole`; only `sender_node_id === identity.node_id`; `pane-writer.js:327-330` maps recipient id to the conductor pane. **Narrowing:** `sovereign-control-server.js:95-102` binds each token to a frozen identity, so a worker cannot *impersonate* the conductor — it can only *write to* the conductor's pane. Severity unchanged. |
| R-02 model-authored bodies written raw, no `\r`/`\n` flattening | **CONFIRMED** | `pane-writer.js:273 io.write(paneId, prompt)`; the "before"/"submit" refusal checks (`:268`, `:277-284`) gate the *trailing* Enter, not CRs inside the body. |
| R-03 `pane:new` sanitiser strips only env/cwd; `file`/`args` reach node-pty; env deletion → full inherit | **CONFIRMED** | `main.js:488-496`, `:469-485` (`spec.env \|\| { ...process.env }`). |
| R-04 no `will-navigate`/`setWindowOpenHandler`; R-12 no `unhandledRejection`/`uncaughtException` | **CONFIRMED** | grep of `main.js` returns none of the four. |
| R-05 Codex `login_status` substring inversion | **CONFIRMED** | executed: "You are not currently logged in.", "Not currently logged in", "no longer logged in", "Never logged in" → `authed=True` at rc 0; only `returncode` protects. |
| R-06 (F1) Antigravity parser empties on any column format | **CONFIRMED** | executed: TAB, multi-space, `* slug`, header+TAB rows → `()`. |
| R-07 same parser accepts one-word junk as model ids | **CONFIRMED** | executed: `Error\nTraceback` → `('Error','Traceback')`; `error:\nunauthenticated` → `('unauthenticated',)`. |
| R-09 MCP server exits before handshake on any capability fault | **CONFIRMED** + new trigger | exit 2 in 0.45 s (no env), 2.5 s (closed port); **exit 1 `ModuleNotFoundError` from any cwd but the repo root** (N-02). |
| R-09 hypothesis "Codex has no sovereign MCP config" | **REFUTED** | repo-tracked `.codex/config.toml` `[mcp_servers.sovereign]` (N-06). |
| R-09b `resources/list` → -32601 | **CONFIRMED** live | stub session: `{"error":{"code":-32601,"message":"method not found: resources/list"}}`. |
| R-10 `load_live_authorization()` outside every gate `try` | **CONFIRMED** | `emit_worker_launch.py:610` vs `try` `:637`; `emit_conductor_launch.py:255` vs `:304`; `enumerate_pane_picker.py:413` unguarded; `main()` has no outer wrapper for `LiveAuthorizationError`. |
| R-11 MCP `inputSchema` never enforced | **CONFIRMED** live | `spawn_worker {"bogus":"x","cmd":"rm -rf /"}` forwarded verbatim, `isError:false`. |
| R-14 `.cmd` shim metacharacter injection | **CONFIRMED and escalated** | N-03: executes on this host even with a quoted argument. |
| R-15 lease released only in governance `except`, not `finally` | **CONFIRMED** | `:816-826` release; `:845` `finally` comment: "the durable lease is untouched". |
| R-16 Electron 31.7.7 EOL / advisories | **CONFIRMED and measured** | `npm audit`: 32 GHSAs against `electron <=40.10.2`, several matching this app's shape (named `window.open` targets GHSA-f3pv-wv63-48x8, contextBridge prototype setters GHSA-ff2p-hmqr-hxm4, context-isolation bypass via `Function.prototype.bind` GHSA-h7rp-cf8h-j98x, renderer switch injection). Fix = 43.4.0 (semver-major, node-pty ABI rebuild). |
| R-16 "`ws` is a dead dependency" | **REFUTED** | `apps/desktop/ipc/client.js:26` requires `ws` as the WebSocket fallback. |
| R-18 29 selfchecks / receipts never read / 15 `ok:false` / no CI | **CONFIRMED** | 68/15/3 on the live tree (list in §7); no `.github/`, no `.yml`, no pre-commit tracked. |
| R-19 live-call guard blind to wrapper shapes | **CONFIRMED** (one leg host-specific) | executed: `npx`, `cmd /c`, `wsl`, `powershell -Command`, `bash -lc`, string, `py -c "…subprocess…"` all → `None`. The Windows `.cmd` full-path leg **is** caught here — that failure was Linux-only. |
| R-20 freeze check exits 1 | **NARROWED to the package** | live tree: `freeze check OK`. |
| R-22 41 host-coupled failures | **NARROWED to off-host** | on-host: 0 failures. |
| R-23 28 JS↔Python legs skip | **NARROWED to off-host** | on-host: 0 skipped, all 1020 ran. |
| R-27 Windows `os.replace` sharing violation | **OS premise CONFIRMED** | `PermissionError [WinError 5]` reproduced with a concurrent reader; whether the product's read window is long enough to hit it in practice is [INFERRED] narrow. |
| R-31/R-32/R-83 CRLF/BOM | **NARROWED, made precise** | `git ls-files --eol`: **0** blobs `i/crlf`; **40** files `w/crlf`/`w/mixed` against LF blobs with local `core.autocrlf=false` → tool-written post-checkout (U274); **3** blobs carry a BOM (`tools/evaluation/harness.py`, `tools/loop/driver_prompt.txt`, `tools/spike_compositor/test/manual_ws_probe.js`) — those are repo defects; the 40 are worktree hygiene invisible to `git status`. |
| R-51 register cites `…0245Z.json`; file is `…0224Z.json` | **CONFIRMED** | register `:5890` vs `:6560`; only `…0224Z.json` exists. |
| R-54 unescaped `innerHTML` for pane titles | **CONFIRMED** | `renderer.js:456-461` (rail: `info.title`, `c.id`), `:499-501` (minimized: `m.title`); `esc()` at `:607` used elsewhere. |
| R-61 ~15 s Job-Object teardown | **CONFIRMED and measured** | N-04. |
| C1 handoff §11 (U330 "five of seven writers bypass") stale | **CONFIRMED** | `persistence/store.py:304` comment records the deletion; no `put_operational_*` remains outside `tools/evaluation/u326_before_after.py`'s deliberate historical stub; STATE_OF_THE_WORKSPACE §H repeats the stale premise. |
| C2 AGENTS.md mandates the dead path | **CONFIRMED** | `AGENTS.md:5-9` read verbatim. |
| C3 README says Phase 1 | **CONFIRMED** | `README.md:8`. |
| C4 CLAUDE.md phases →13, "one frontier terminal per subscription", conductor "Fable 5" | **CONFIRMED** | file read; live authorization is OP-12/Codex `gpt-5.6-sol`. |
| Rev-2: `AGREEMENT_FIELDS` omits `readiness_turns` | **CONFIRMED** | `conductor-admission.js:74-76` = role/provider_id/adapter_id/model_id/permission_profile_id; `:62-63` consumes `descriptor.readiness_turns`. |
| Rev-2: duplicate-worker detection matches provider only | **CONFIRMED** | `application-control.js:215 find(r => r.chrome.provider === provider)`; requesting model B while model A of the same provider is live returns A as `duplicate:true` with no model comparison. Under one-terminal-per-subscription this may be intended, but the returned node's `model_id` differs silently from the request. |
| Rev-2: `record_synthesis(contribution_bindings=None)` skips binding validation | **CONFIRMED** | `collaboration_service.py:380-383`, `:401 if contribution_bindings is not None`. Candidate-completeness check runs always; hash binding is caller-optional. |
| Rev-2: approvals route presumes operator identity | **CONFIRMED, disclosed** | `session_approvals.py:471-473` fabricates `Identity(node_id="operator", role=operator)`; the output carries `operator_identity_presumed: true` (`:455-457`) — honest, still a presumption. |
| Rev-2: packaged candidate lacks four `.claude/` files + `.grok/config.toml` its tests need | **CONFIRMED (package)** | all five are git-tracked; live tree freeze check passes; `.grok/config.toml` present. |
| Prior turn: no persisted node events for Codex/Claude | **CONFIRMED and explained** | N-05. |

---

## 4. NEW FINDINGS (not in any prior review)

**N-01 — The sovereign MCP stdio transport is not UTF-8 on Windows, in either direction; the `tools/list` reply is invalid UTF-8**
Severity: **HIGH** · [OBSERVED] server bytes; [INFERRED] client behaviour
`mcp_server/sovereign_tools.py:529` — `sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")` with no `reconfigure(encoding="utf-8")`, no `-X utf8`, no `PYTHONUTF8` in any of the three MCP configs; `:519 for line in sys.stdin` likewise. On this host `sys.stdout.encoding` for a pipe is `cp1252`. Measured over a real stdio session against a stub gateway: `initialize` = 643 bytes, pure ASCII, valid; **`tools/list` = 9020 bytes with two raw `0x97` bytes → invalid UTF-8** (the em dashes in the `abort_debate` and `publish_synthesis` descriptions, `:473`, `:477`). Read side: a request containing Cyrillic `А` (UTF-8 `D0 90`; `0x90` undefined in cp1252) came back `UnicodeEncodeError … '\udc90' surrogates not allowed`, `isError:true`; cp1252-representable non-ASCII (`é`, `—`, curly quotes) would be silently mojibaked into the store.
Why it matters: MCP-over-stdio is UTF-8 by specification. Codex's stdio client is Rust and reads lines strictly; the first invalid line is a transport error and the server is marked failed → "MCP server 'sovereign' was not ready for this step". Node clients (Claude Code; the project's own `sovereign-mcp-stdio.test.js`, which passes) decode lossily and never notice — which matches the observed asymmetry exactly. Independently of F2, any task objective/message/proposition with non-cp1252 characters is refused or corrupted on the live path.
Fix shape: first lines of `main()`: `sys.stdin.reconfigure(encoding="utf-8")`, `sys.stdout.reconfigure(encoding="utf-8", newline="\n")` — or add `-X utf8` to the args in `.mcp.json`, `.codex/config.toml`, `.grok/config.toml`, `.agents/mcp_config.json`. Then re-run the Codex conductor bring-up: this is the cheapest F2 discriminator available.

**N-02 — The MCP server module is cwd-dependent and no MCP config pins a cwd**
Severity: MEDIUM · [OBSERVED]
`py -3.12 -m mcp_server.sovereign_tools` from `%USERPROFILE%` → `ModuleNotFoundError: No module named 'mcp_server'`, exit 1, in 0.1 s. None of the four configs sets `cwd`; all depend on the provider CLI spawning MCP servers with cwd = repo root. Second F2 candidate, and a fragility for any provider whose MCP launcher does not inherit the session cwd. Fix shape: `cwd` in the configs where the format allows, or a launcher script that `chdir`s to `Path(__file__).parents[1]`.

**N-03 — `.cmd`-shim metacharacter injection executes on this host even through Python's own quoting**
Severity: **HIGH (latent)** · [OBSERVED]
A scratch `fake.cmd` invoked via `subprocess.run([cmd, "--cwd", r"C:\x\R&echo INJECTED"])`: `list2cmdline` produced `"C:\x\R&echo INJECTED"` (quoted) and cmd.exe **still executed `echo INJECTED`**; `C:\x\a|b^c` executed `bc`; an unquoted `R&D\ws` truncated at `&`. The adapters deliberately resolve `.cmd` shims for npm-installed CLIs, and workspace/cwd/slug values reach argv unvalidated (prior review's R-14 citations). Today's repo path contains spaces but no metacharacter, so it is latent. Precondition: any operator- or provider-influenced string with `& | ^ < > %` reaching a `.cmd`-resolved argv. Fix shape: validate every path/slug against a shell-metacharacter class before argv construction, or resolve to the underlying `node.exe` + script instead of the `.cmd` shim.

**N-04 — Every managed provider call pays a fixed 15 s Job-Object teardown on Windows**
Severity: MEDIUM (performance/latency; inflates every probe and the suite) · [OBSERVED]
`run_managed_process(["cmd.exe","/c","echo hi"])` = 15.15 s, 15.12 s. Cause: `process_tree.py:227 job.terminate_and_wait(15.0)` → `:128 WaitForSingleObject(job_handle, 15000)`; a Job Object handle is signaled only on end-of-job time limit, never on member exit, so the wait always runs to the ceiling. Every caller pays it: `provider_cli_common.py:1201`, `claude_code.py:460`, `provider_probe_session.py:529`, `wsl_parakeet.py:141`. The project's own suite shows it (`test_frontier_process_tree…` 15.16 s, `test_the_managed_boundary_still_runs_a_non_provider_command` 15.15 s). Fix shape: poll `pids()` until empty with a 50 ms sleep, bounded by 15 s; or a completion port on `JOB_OBJECT_MSG_ACTIVE_PROCESS_ZERO`.

**N-05 — F6 answered: OP-6 provider panes are excluded from node registration by design**
Severity: MEDIUM (Invariant-2 evidence hole, disclosed) · [OBSERVED]
`tools/live/emit_worker_launch.py:513-519`: `if adapter_id not in _OP12_PANE_NODE_ADAPTERS: return _no_pane_node_record(… "The OP-6 providers' panes hold a durable I-X3 terminal and no node record — an owed leg (U313)")`. This is why `node_events.jsonl` has 0 events for `claude_code`/`openai_codex_cli` after 154 events. The handoff's "Governed: YES" for Codex and Claude is true for lease+supervision and false for "registered Sovereign node". The lease ledger is rewritten (not appended) on release — `terminal_leases.json` is `leases: []` — which is why the two cited lease ids appear nowhere on disk.

**N-06 — The Codex conductor IS configured for the sovereign server; the config is tracked and non-fatal**
Severity: INFO (corrects the record) · [OBSERVED]
Repo-tracked `.codex/config.toml`: `[mcp_servers.sovereign] command="py" args=["-3.12","-m","mcp_server.sovereign_tools"] env_vars=[SOVEREIGN_CONTROL_PORT, SOVEREIGN_CONTROL_TOKEN, SOVEREIGN_STORE_ROOT] enabled=true required=false startup_timeout_sec=120`, plus per-tool `approval_mode="approve"` for `spawn_worker`/`stop_worker`/`assign_task`. `~/.codex/config.toml` trusts the project path and defines only `node_repl` (and Codex's own servers). `.grok/config.toml` and `.agents/mcp_config.json` also point at the server; neither declares an env whitelist (whether Grok/Antigravity forward the three env vars to MCP children is [UNVERIFIED]). `required=false` means a sovereign failure is non-fatal to Codex — consistent with the conductor proceeding and later answering `2+2` itself.

**N-07 — The current-position documents exist only in the unpromoted ZIP**
Severity: MEDIUM (successor-agent risk) · [OBSERVED]
`STATE_OF_THE_WORKSPACE.md`, `README_BASELINE.md`, `PACKAGE_MANIFEST.txt`, `WORKTREE_PROVENANCE.patch` are in the ZIP root and **not** in the repository (`git ls-files` root: 13 files, none of them). The repo's own `README.md:8` says Phase 1. The packaging step authored the most accurate narrative and left it outside the tree it describes.

**N-08 — Harness network denial in the freeze-bound `.claude/settings.json` is porous**
Severity: LOW/INFO (build harness, not product) · [OBSERVED]
Denies `curl`, `wget`, `Invoke-WebRequest`, `ssh`, `scp`; allows `python:*`, `node:*`, `py:*`, `pip install:*`, `npm install:*`, `git checkout:*`, `git stash:*`, `git merge:*`. `guard.py` regexes the same list. A loop agent can fetch anything via `python -c "urllib…"`/`node -e`/`iwr`. Noted because this file is inside the Phase-0 signature scope; not a product finding.

**N-09 — R-27's OS premise holds; product exposure is narrow**
Severity: LOW-MEDIUM · [OBSERVED premise / INFERRED exposure]
`os.replace(tmp, target)` while another handle has `target` open for read → `PermissionError [WinError 5]`. The lease ledger's readers hold the file only for the ms it takes to `json.load`, so the window is small; the release CLI does not catch `PermissionError` (an `OSError`), so a hit is a non-zero exit with the terminal not handed back. Fix shape: retry `os.replace` briefly on `PermissionError`, or read under the same lock.

**N-10 — Suite contract vs. reality on the target host**
Severity: INFO · [OBSERVED]
Recorded 2381/1/1 in 638 s; measured 2382/1/0 in 721 s under contention. Count is off by one (either the recorded failure was a flake or 19.10 added a test); time is inside the 800 s ceiling with 10 % headroom *while six agents ran* — the ceiling is honest. Off-host the same suite shows 41 failures (prior review); the contract should say "on the target host" explicitly.

**N-11 — Host-coupled tests spawn real `opencode run` through `cmd /c opencode.CMD`**
Severity: INFO · [OBSERVED]
`tests/integration/test_opencode_candidate_live.py` (157 s) and `…worktree_live.py` (117 s) drive a real local OpenCode harness against local Ollama (credential-free, correctly gated on both being present). `opencode` is not in `LIVE_PROVIDER_CLIS`, which is correct today. Two runs of the suite in parallel would collide on `.sovereign_store/tmp-tests/` (shared path) — the suite is not safe to run twice concurrently.

---

## 5. STATUS OF F1–F6 AFTER THIS PASS

| Finding | Status | What changed |
|---|---|---|
| F1 Antigravity parser | CONFIRMED, two-sided (R-06 + R-07) | executed both directions on host; a tab-split fix without slug/annotation gating widens R-07 |
| F2 MCP not initialised | **mechanism reproduced; two new root-cause candidates (N-01, N-02); prior hypothesis refuted (N-06)** | N-01 fits the Codex-fails/Node-passes asymmetry and costs one line to test |
| F3 ModelProbeLedger | unchanged; ledger holds only `fable-5 → claude-fable-5` (probed 2026-07-26) | (argv-builder validation gap not re-derived here — see §10) |
| F4 pane occupancy ritual | not re-derived here | — |
| F5 Electron restore | narrowed: live tree has 31.7.7 installed with `electron.exe`+`path.txt`; failure is fresh-`npm ci` only | Electron carries 32 GHSAs; upgrade is semver-major |
| F6 no node events for Codex/Claude | **answered: by design (U313), N-05** | handoff §4 wording should be corrected |

---

## 6. CONTRADICTIONS WITH THE RECORD (additions to the prior list)

- **STATE_OF_THE_WORKSPACE §H** repeats "U330 is that five of seven writers bypass it" — stale; U330 closed at 19.5 (C1).
- **STATE_OF_THE_WORKSPACE §D** "Governed: YES" for Claude/Codex — true for lease+supervision, false for node registration (N-05).
- **Prior review R-09 hypothesis 1** — refuted (N-06).
- **Prior review R-16 "`ws` dead dependency"** — refuted.
- **Prior review "recorded green not reproducible"** — true off-host, false on-host (N-10).
- **The four position documents** are outside the repo (N-07).

---

## 7. THE 15 `ok:false` RECEIPTS SITTING IN THE EVIDENCE TREE

`PHASE17C_DISARM_FALSIFICATION.json`, `PHASE18C_ACCEPTANCE_SELFCHECK.json`, `PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json` (+3 close-tagged reruns), `PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK_phase-19.3.close_…`, `…round1_…`, `PHASE19_4_READINESS_WINDOW_SELFCHECK_ab-pre-repair_…`, `…diag_…`, `…round3-rerun_…`, `…round3_…`, `PHASE19_6_CONDUCTOR_DESCRIPTOR_SELFCHECK_19.6-clean-tree_…`, `…19.6-round1_…`, `PHASE19_7_RUNTIME_HONESTY_SELFCHECK_19.7_20260813T225618Z.json`. Some are deliberate falsification/pre-repair runs (the names say so); nothing machine-readable distinguishes those from failures, and nothing reads them.

---

## 8. WHAT IS GENUINELY STRONG (re-confirmed on host)

- The suite is real and green on its target: 2382 Python + 1020 desktop + 216 terminal tests, zero skips on-host, inside its own measured ceiling under load.
- Token binding on the control gateway is correct: per-node, frozen identity, revoked wholesale on stop, 1 MB body cap, `_lastSeen` honesty states (`configured`/`connected`/`stale`) with the reasoning written next to the code.
- The lease acquisition order (authorize → seed governor from durable ledger → acquire → register node, all inside the governance `try`) is the right shape; the defect is only the exception class the release is keyed on.
- The freeze mechanism works on the tree it was designed for; the frozen set is intact.
- The codebase's self-disclosure is real: U313 (N-05), U207 (identity presumed), U274 (CRLF), the `finally` comment on the lease — each defect I found in code was already named in the code.
- No shell-string execution anywhere in product code; the `.cmd` exposure (N-03) is a Windows CreateProcess property, not a shell=True.

---

## 9. RECOMMENDED SEQUENCING (unchanged tiers; two insertions)

> **Revised after round 2 (§12).** The tiers below stand, with these insertions: **A-2** (provider stdout silently discarded, empty result published as SUCCESS) and **A-5** (MCP encoding, both directions, corrupting stored content and its hashes) join **Tier 0** — both are one-line-class fixes with live data-integrity consequences, and A-5 is also the leading F2 candidate. **A-3** (no operational state machine; synthesis binding invalidated after the fact) joins **Tier 1**, since it falsifies the durable record rather than merely risking it. **A-1** must land **before any Claude-conductor run** — it is latent only while the conductor is Codex. **A-4** (zero-length ledger fails open) belongs with R-15/R-26 in Tier 3.

**Tier 0 — before any multi-node live run:** R-01 + R-02 (role-gate the three `notify_*` handlers; flatten `[\r\n\x1b]` on every model-authored body at `pane-writer.writePrompt`).
**Tier 0.5 — the cheapest F2 test that exists:** N-01 — add the two `reconfigure` lines (or `-X utf8` in the four configs), then re-run the Codex conductor bring-up. If sovereign initialises, F2 is closed by a two-line change; if not, N-02 (cwd) is next.
**Tier 1:** record F1–F6 + the confirmed set in the register; fix `AGENTS.md`, `README.md`, add an ERRATA block to `FINAL_LIVE_REPORT.md`; move `STATE_OF_THE_WORKSPACE.md` into the repo (N-07); operator ruling on `CLAUDE.md` (resets the Phase-0 signature).
**Tier 2 (instruments):** live-call guard shapes (R-19); receipt reader failing on `ok:false` (R-18); make the suite contract host-explicit (N-10); a worktree-bytes-vs-blob check for the 40 CRLF files and the 3 BOM blobs.
**Tier 3:** F1 both-sided; N-04 (15 s tax); R-15 `finally`; R-10 load-inside-try; N-03 metacharacter validation before argv; R-12 job object + `unhandledRejection`; Electron 43.4.0 + node-pty rebuild as its own unit; Phase 19 gate last.

---

## 10. WHAT THIS PASS DID NOT COVER

- The six scoped sub-reviews were re-run in a second round; **four completed (control plane, adapters, MCP/persistence, evidence/docs) and two are partial (desktop, security/voice)**. Their raw reports are preserved at `D:\Product Software\SOW_REVIEW_ROUND2_RAW\` and are **not yet consolidated into this document** — see §11. Until that consolidation is done, the findings in those raw files are reviewer-labelled but not lead-adjudicated.
- No live provider CLI was invoked; the parsers were tested against plausible inputs, not today's real `agy`/`grok`/`codex` output.
- Codex's strict-UTF-8 stdio behaviour is asserted from knowledge of its Rust client, not observed on this host — the one-line fix + re-run is the test.
- Path-containment bypass attempts (`\\?\`, 8.3 names, junctions), the threat-model mapping, voice confidence semantics, and the full IPC channel inventory were assigned to the terminated agents and not redone.
- `docs/evidence/` was not read beyond the receipts scan.

*Everything above is re-derivable from the cited paths on the live tree. Where I could not re-derive it, I said so.*

---

## 11. ROUND 2 — SCOPED SUB-REVIEWS (RAW INPUT; ADJUDICATED IN SS12-13)

**Status: all six areas COMPLETE.** This section is the raw reviewer input. Findings I re-derived personally are promoted to `A-1`...`A-9` in **section 12**; the security area is consolidated in **section 13**. Section 12.1 lists what is still reviewer-labelled.

Six scoped reviewers were run over the live tree, read-only, no provider CLI invoked. Raw reports:
`D:\Product Software\SOW_REVIEW_ROUND2_RAW\REPORT_{control_plane,adapters,mcp,evidence,desktop,desktop2,security,security2}.md`
(plus `REVIEWER_PREAMBLE.md`, the shared instruction set — it lists what round 1 had already settled).

| Area | State | Suite run by that reviewer |
|---|---|---|
| control_plane | COMPLETE | 207 passed / 1689 deselected |
| adapters | COMPLETE | 249 passed / 1 skipped |
| mcp | COMPLETE | 101 passed |
| evidence | COMPLETE (bar the 19.10 diff, done by the lead — see below) | — |
| desktop | **COMPLETE** (finished after this section was first written; `REPORT_desktop.md` is the full report, `REPORT_desktop2.md` a partial duplicate-effort file that can be ignored) | desktop suite 1020/1020 on a scratch copy; **all 5 mutation harnesses ALL-CAUGHT, byte-identical restore, EXIT=0** |
| security | **COMPLETE** (`REPORT_security.md` + `REPORT_security2.md`, 420 lines; consolidated in section 13) | 15 path tricks vs the canonical freeze; guard-bypass matrix; dangerous-call census |

### 11.1 Round-2 items the lead personally re-derived

- **Conductor launch bypasses the model-probe ledger.** `tools/live/emit_conductor_launch.py:270-271` sets `model = desc.model_id` and `model_available = True` on the descriptor path, so the ledger consult at `:293` (`model is None and model_available is None`) is unreachable there; `main()` at `:532-533` always passes `descriptor=load_runtime_conductor_descriptor()`. The registry default for Claude is `fable-5` (`control_plane/conductor/registry.py:92`). The comment at `:288-292` states the ledger exists because `.pty` launched with the label and the CLI answered *"There's an issue with the selected model (fable-5)"* — the 17A `.roundtrip` fix is re-broken on the production path, and the record labels the unprobed slug `source: "registered-exact-slug"`. **Latent today** (the live switch prefers `openai_codex_cli`); fires the moment the conductor preference is Claude. HIGH.
- **The suite contract correction is in the uncommitted material, not `pytest.ini`.** Register row U443 (uncommitted) records `2382 passed, 1 skip, 608.47 s`. The lead's independent host run measured **2382 passed / 1 skipped** — an exact match (720.92 s under six-agent contention). This **supersedes N-10 above**: the count is not "off by one"; `pytest.ini`'s recorded `2381/1/1` is the stale value and the uncommitted 19.10 evidence is correct.

### 11.2 Highest-severity round-2 findings (reviewer-labelled, lead-verified only where stated)

- **MCP stdio is cp1252 in BOTH directions.** Beyond the lead's N-01 (stdout), the stdin leg uses `surrogateescape`, so non-ASCII task/message/artifact content is persisted as mojibake **and content hashes are computed over the mojibake**; UTF-8 bytes in {81,8D,8F,90,9D} make `publish_artifact` fail outright. `main()` has zero encoding test coverage (the protocol e2e test never spawns the process). Raises N-01 from "F2 candidate" to "live data-integrity defect".
- **Gateway `notify_*` accept store-unverified payloads** — recipients/participants come from the POST body with no role gate, no store lookup, no policy call, so any token-holder can have text typed into any live pane including the conductor's. (Extends R-01/R-02 with the store-verification half.)
- **Prompt/objective text reaches `cmd.exe` through `codex.CMD`** — widens the lead's N-03 from paths to model-controlled content; reviewer executed `&`-separated command execution, `%VAR%` expansion into prompts, and silent truncation at the first newline against a scratch shim.
- **cp1252 decoding blanks provider stdout** — an undefined byte kills the stdlib reader thread, `stdout` comes back empty with rc 0, and `CodexCliBackend.generate` publishes that empty result as SUCCESS.
- **Operational task status has no legality machine** — a worker can drive a shared task to COMPLETED/CANCELLED or regress it, and candidates can be overwritten after synthesis leaving the synthesis bound to a stale hash (reviewer-executed).
- **Truncated lease ledger reads as zero leases** and grants an over-cap acquire (reviewer-reproduced); `terminal_lease.py:248-249` treats zero-length as absent while the docstring promises fail-closed.
- **IPC gateway sets `allow_reuse_address = True`** (`control_plane/ipc/gateway.py:257`) — on Windows a second same-user socket co-bound the live gateway port (reviewer-reproduced; plain bind refused with 10048).
- **24 of 36 selfcheck files have no direct test**, including the 999-line producer behind the 17E "36/36" receipt.
- Receipt spot-checks **support** the FINAL_LIVE_REPORT narrative where checked (17E 36/36, typed+voice answers, I-X3=2 labelled `scope: diagnostic`); what they do not support is any reading in which both OP-12 providers answered a live prompt in the packaged shell — all four 18E close runs record `live_exchanges_spent: 0`.

### 11.3 Round-2 refutations of round-1 claims

- **Mutation harnesses are healthy, not broken.** All five harnesses referenced from `apps/desktop/package.json` (pane_input_bypass 23, disarm_authority, system_pane_write 32, readiness_signal 26, orchestration 14) ran headless: **ALL CAUGHT, every product file restored byte-identical, EXIT=0, no SETUP-FAIL**. R-33's stale-anchor problem is specific to `_op12_close_mutations.py`, not the harness suite.
- **The `py.exe` orphan concern is NOT reproduced** — killing the `py` launcher reaped the `python.exe` gateway child on this host; `main.js:2520` does tear the real gateway down.
- **R-72 substantially narrowed** — node-pty 1.1.0 sets `setEncoding('utf8')`, so `onData` yields strings and chunks are character-aligned; only the single >256 KB chunk trim can cut mid-sequence.

- **R-87 REFUTED on the live tree** — `OPEN_READY` has 0 occurrences repo-wide; it exists only in the ZIP-only documents.
- **R-75 partially refuted** — `tools/soak/results` is committed but not growing.
- **R-50 narrowed** — the PENDING/CLOSED divergence is a consequence of the manifest being a frozen artifact, not an oversight.
- **R-88 narrowed** — both stale line cites were accurate when written; append-only registers plus line-number citations guarantee the decay, and there is no cite-checker.

### 11.4 Remaining work

1. ~~Finish the partial areas~~ - **done** (section 13).
2. ~~Lead-adjudicate~~ - **done for nine findings** (section 12); section 12.1 names the residue.
3. ~~Re-sequence~~ - **done** (section 9 preamble and 13.4).
4. Still open and untouched by this review, all operator calls: whether to commit this report; the `CLAUDE.md` correction that resets the Phase-0 signature; and whether the findings are recorded in the register before any repair, per the handoff's 10.1 reasoning.

---

## 12. LEAD ADJUDICATION OF ROUND 2 — VERIFIED FINDINGS

Everything in this section I re-derived personally on the live tree by execution. These are promoted out of §11's raw status and carry stable `A-nn` ids. Round-2 claims **not** listed here remain reviewer-labelled (§11) until adjudicated.

**A-1 — The production conductor-launch path bypasses the model-probe ledger and stamps a false provenance label**
Severity: **HIGH** · [OBSERVED]
`tools/live/emit_conductor_launch.py:270-271` sets `model = desc.model_id` and `model_available = True` whenever a descriptor is supplied; the ledger consult at `:293` is guarded by `model is None and model_available is None` and is therefore unreachable on that path. `main()` at `:532-533` always supplies `descriptor=load_runtime_conductor_descriptor()`. The Claude registry default is `fable-5` (`control_plane/conductor/registry.py:92`). The comment at `:288-292` states this ledger exists *because* `.pty` launched with the operator's label and the CLI answered "There's an issue with the selected model (fable-5)". The host ledger (`.sovereign_store/model_probe/claude_code.json`, probed 2026-07-26) records `fable-5` REJECTED and `claude-fable-5` ACCEPTED. The emitted record additionally labels the unprobed slug `source: "registered-exact-slug"` — a provenance claim the code never earned.
*Precondition:* conductor preference is Claude. Latent today (the switch selects `openai_codex_cli`); fires on any switch to a Claude conductor. Regresses the 17A `.roundtrip` fix. *Fix:* on the descriptor path, resolve `desc.model_id` through `resolve_launch_model` for `claude_code`, or store accepted CLI slugs in the registry.

**A-2 — cp1252 decoding of provider stdout silently discards a provider's entire answer; Codex publishes the empty result as SUCCESS**
Severity: **HIGH** · [OBSERVED, executed]
`adapters/frontier/process_tree.py:195` and `adapters/frontier/codex.py:219,658` use `text=True` with no `encoding=`. Host preferred encoding is cp1252; nothing sets `PYTHONUTF8`. Measured: a child emitting UTF-8 containing `0x9D` as a continuation byte (U+276F `❯` — a glyph these CLIs use routinely, as do U+2588 block characters and most emoji) kills the stdlib reader thread with `UnicodeDecodeError`, and `subprocess.run` returns **`returncode == 0` with `stdout is None`**. The same child read with `encoding="utf-8", errors="replace"` (the shape `frontier_provider_recon.py:709-712` already uses) returns the text intact.
Downstream, measured by code read: `codex.py:668` coerces `out = (proc.stdout or "").strip()` and `:673` returns `json.dumps({"codex_exec": "empty", ...})` — **a lost provider answer is published as a successful candidate**. `codex.py:229-232` turns the same condition into `CodexUnavailable`, reporting a present, working CLI as absent. Defined-but-non-ASCII bytes (em dash, arrows, curly quotes) do not raise — they decode to mojibake and are stored verbatim.
*Fix:* `encoding="utf-8", errors="replace"` at every spawn site; the recon runner is the in-repo template.

**A-3 — Operational tasks have no state machine: a worker can drive a shared task to terminal states, regress it, and invalidate a recorded synthesis**
Severity: **HIGH** · [OBSERVED, executed in-process against the real service]
`mcp_server/collaboration_service.py:138-160` (`update_task`) applies any status to any status with no legality check, and `:350-378` (`record_candidate`) has no terminal-state guard. Measured on a fresh store, task owned by `w1`+`w2`, created by the conductor:
- worker `w1` → `COMPLETED`: **ACCEPTED**
- worker `w2` → `CANCELLED`: **ACCEPTED**
- worker `w1` → back to `IN_PROGRESS`: **ACCEPTED**
- after a conductor synthesis bound to candidate hashes `h-A`/`h-B` (task `COMPLETED`), worker `w1` re-published its candidate: **ACCEPTED**, task regressed `COMPLETED → CANDIDATE_READY`, and the stored synthesis still binds `h-A` while the live candidate is `h-A2` — **a stale binding**.
The contribution-hash binding built carefully inside the write fence (`:394-424`) is therefore only true at the instant of synthesis; nothing freezes the candidates afterwards, so the durable record of what was synthesized becomes false. Invariant 10 ("workers never self-canonize") still holds in the narrow sense — the worker cannot mark its own work ACCEPTED — but the shared task record is worker-writable in both directions.
*Fix:* an operational status machine mirroring `lifecycle.py`, plus refusing candidate/synthesis writes on a task in a terminal state.

**A-4 — A zero-length lease ledger reads as "no leases" and grants an over-cap terminal; only non-JSON corruption fails closed**
Severity: **MEDIUM-HIGH** · [OBSERVED, executed]
`node_runtime/supervisor/terminal_lease.py:248-249` returns `[]` for an empty/whitespace file; `:270-277` writes via temp + `os.replace` with **no fsync of file or directory**, which is exactly the sequence that yields a zero-length file after a crash or power loss. Measured: two leases held at allowance 2 → a third acquire correctly `SubscriptionLimitExceeded`; truncate the ledger to 0 bytes → `in_use` reads **0** → the third acquire is **GRANTED**, so three real terminals exist against an allowance of 2. For contrast, a non-JSON ledger raises `LeaseLedgerCorrupt` and fails closed correctly. The module docstring promises corrupt ledgers fail closed; the one corruption mode the filesystem actually produces is the one that fails open.
*Fix:* treat zero-length as corrupt (fail closed), and fsync the temp file and the directory before/after `os.replace`.

**A-5 — N-01 upgraded: the MCP stdio encoding defect is bidirectional and is a live data-integrity defect, not only an F2 candidate**
Severity: **HIGH** · [OBSERVED, executed] (extends N-01)
`mcp_server/sovereign_tools.py:519` (stdin) and `:529` (stdout) both run in host locale text mode. Confirmed: the `tools/list` reply carries raw `0x97` bytes and is not valid UTF-8; a request containing a character outside cp1252 returns `UnicodeEncodeError … surrogates not allowed`. The round-2 MCP reviewer additionally measured, against a scratch store, that `publish_artifact("a — b")` persists 12 bytes of mojibake (`61 20 C3 A2 E2 82 AC E2 80 9D 20 62`) with a content hash computed **over the mojibake** — so the CAS address is of corrupted content while the round-trip to the same cp1252 process looks correct. `main()` has no encoding test coverage (the protocol e2e test never spawns the process).
*Fix:* `sys.stdin/stdout.reconfigure(encoding="utf-8")` (strict) in `main()`, plus one subprocess test asserting stored bytes.

**A-6 — Codex demotes a successful answer to an auth pause when the answer merely discusses quotas or rate limits**
Severity: **MEDIUM** · [OBSERVED, executed]
`adapters/frontier/codex.py:669-671`: after `returncode == 0`, `if self._classify(out) and not out.strip().startswith("{")` raises `CodexAuthError`. `_AUTH_FAILURE_MARKERS` (`:417-423`) includes `quota`, `rate limit`, `http 429`. Measured: the strings *"The API enforces a per-user quota of 100 req/min for this endpoint."* and *"Handle HTTP 429 (rate limit) by exponential backoff."* both classify true and would raise a pause. `codex exec` emits prose, so the `{` exemption almost never applies.
Consequence: a worker asked to write backoff or quota-handling code has its node paused by its own correct answer, and the pause is attributed to the provider. This also contradicts the exit-code-first rule as implemented in `provider_cli_common.classify_provider_outcome:449-459`, which never demotes a zero exit on text. *Fix:* classify only on a nonzero exit or a structured error field.

**A-7 — The Antigravity parser reports authentication and status words as available models, and the picker marks them verified**
Severity: **MEDIUM** · [OBSERVED, executed] (the positive-acceptance half of F1/R-07)
`parse_antigravity_models("Unauthorized
401
please-login
gemini-3-pro")` returns `('Unauthorized', '401', 'please-login', 'gemini-3-pro')` with `parse_note: "ok"`. `control_plane/nodes/pane_picker.py:353-370` then builds a picker option per slug with `verified=True`, and the launch path ships the string to `--model`. The slugs are regex-clean so this is a fabricated-inventory defect, not an injection one — but a signed-out host is presented to the operator as a provider with four working models. *Fix:* gate on a known section header and a model-family shape, per `parse_grok_models`; report rejected lines in `parse_note`.

**A-8 — Grok AUTHENTICATED can be minted from prose that merely contains "you are logged in"**
Severity: **MEDIUM** · [OBSERVED, executed]
`_GROK_LOGIN_MARKER_RE` is `search`ed per line (`provider_cli_common.py:821, 886-891`). Measured: a transcript whose first line is *"Tip: if you are logged in elsewhere, run `grok login` again."* yields `login_reported: True`, which at `:1047-1050` becomes `AUTH_AUTHENTICATED` on a zero exit. Exit-code-first is respected; the positive predicate is not anchored. Together with A-6 this is the same class as R-05 (Codex `"logged in"` substring): the negative predicates in this codebase are strict and the positive ones are loose. *Fix:* anchor the marker and require the declarative sentence.

**A-9 — The Python IPC gateway sets `allow_reuse_address = True`, so another same-user process can co-bind its live loopback port on Windows**
Severity: **MEDIUM** · [OBSERVED, executed as a controlled A/B]
`control_plane/ipc/gateway.py:256-257` declares `class Server(socketserver.ThreadingTCPServer): allow_reuse_address = True`, which sets `SO_REUSEADDR`. On Windows `SO_REUSEADDR` does not mean what it means on POSIX: it permits a *second live bind* to the same address rather than only reclaiming a `TIME_WAIT` socket. Measured with an identical server under both settings: with `allow_reuse_address = True` a second `SO_REUSEADDR` socket **bound the live port successfully**; with `allow_reuse_address = False` Windows refused it (`WinError 10013`).
Consequence: a same-user local process can race for, steal, or wedge the control channel whose loss the worker ticket says forces the shell to kill every session. It cannot forge envelopes — the per-node HMAC key (`envelope.py:41-47`) is not derivable from the socket — but it can observe the bearer credential and disrupt availability. Threat boundary is "same Windows user", which is the boundary `docs/THREAT_MODEL.md` itself scopes to, so this is a hardening gap rather than a broken trust boundary. *Fix:* `allow_reuse_address = False` on win32 (or `SO_EXCLUSIVEADDRUSE`), here and in the sibling servers.

### 12.1 Round-2 claims still awaiting lead adjudication

Reviewer-executed but not re-derived by me: the `codex.CMD` prompt-content injection (I verified the generic `.cmd` mechanism in N-03, not this specific call path); private-tier memory promotion by a non-author; identity resolved once at startup for store-only tools; the gateway `notify_*` store-verification gap (its role-gate half is already confirmed as R-01). All are recorded with line cites in `SOW_REVIEW_ROUND2_RAW\`.

---

## 13. THREAT-MODEL MAPPING AND ELECTRON EXPOSURE (round 2, security area — COMPLETE)

The security area finished all four of its scope items. Its raw report is `SOW_REVIEW_ROUND2_RAW\REPORT_security2.md` (plus `REPORT_security.md` for the earlier half: STT confidence, protected-verb matcher, listener inventory, path-containment probe, PII counts). Findings below are reviewer-executed with line cites; I have not independently re-derived them, and they are labelled accordingly.

### 13.1 `docs/THREAT_MODEL.md` — verdict summary

52 lines naming 6 trust boundaries, 16 threats, 9 failure modes and a build-time analogue; every identifier mapped against the live tree.

| Verdict | Identifiers |
|---|---|
| **IMPLEMENTED** | TB-2 (signed envelopes — "the strongest boundary in the tree"), TB-3, TB-5, TB-6, T1, T5, T6, T9, T10, T11, T12, T13, T15, T16 |
| **PARTIAL** | TB-1, TB-4, T2, T4, T7, T8 |
| **MOSTLY / WHOLLY ABSENT** | T3 (1 of 3 named legs real), **T14 (CoWork — one docstring mention repo-wide)**, residency-planner failure mode (empty package) |
| **CONTRADICTED as written** | TB-1 convergence; T3's general containment claim; 3 of 4 build-time sub-claims |

Three items are worth the operator's attention directly:

- **TB-1 is contradicted in a fail-safe direction.** The document says text and voice converge on one command bus before the Permission Broker. The bus (`voice_bridge/command_broker.py:92`) is real and well built, but **every caller is a voice path**; the operator's *typed* surface bypasses it entirely — `main.js:1468` `pane:input` writes straight to the ConPTY child, and `main.js:1521` `pane:close` executes a destructive `kill` with no approval queue. Voice is strictly *more* governed than typing. Not a vulnerability; the document asserts a property the code does not have.
- **T-02 corrects R-12, in both directions.** `JobObjectContainment` (`containment.py:59`) genuinely has **zero product callers**. But a second, independently written Job-Object implementation — `WindowsJob` (`adapters/frontier/process_tree.py:32-142`) — **is** wired into product code (`claude_code.py:460`, `provider_cli_common.py:1201`, `wsl_parakeet.py:141`, `provider_probe_session.py:529`). So OS process-tree containment exists, but **only on the one-shot headless probe path**. The operator-facing panes running a real agentic CLI for minutes — precisely the path invariant 29 names — are plain node-pty children with no job object, so `manager.kill()` and the fail-closed `killAll()` reap the PTY, not the descendant tree. Working code to fix it already exists twice in the tree.
- **T-01: five asserted mitigations have no implementation** — T2's "adversarial tests" (`tests/security/` is `.gitkeep`-only), T3's "deny-by-default egress" (no OS/network control anywhere), T4's "periodic process audit" (no such symbol), T14 entire, and the residency planner. This is the repo's only threat-model artifact. *Fix shape:* a `status` column (`implemented`/`scaffold`/`deferred-to-P10`) — the honesty `containment.py:6-10` already practices about itself, applied to the document.

### 13.2 Build harness (`.claude/`) — the freeze holds where it is wired, and is absent where it is not

- **Good news, verified:** `guard.py`'s `docs/canonical/` protection **held against all 15 path tricks** tried (`..` re-entry, 8.3 short name, mixed case, `\\?\` prefix, junction, alternate cwd).
- **S-01 (HIGH, reviewer):** that protection is **not applied to the Bash tool at all** — `echo evil > docs/canonical/<frozen>.md` is ALLOWED, with `Bash(cat:*)`/`Bash(python:*)` pre-approved. The freeze is a write-tool-path control, not a content invariant.
- **S-02/S-03/S-04/S-05:** the Bash "outside project root" check is dead code on Windows; `guard.py` resolves relative paths against `PROJECT_ROOT` while the tool resolves against cwd; the hook **fails open on four error paths**; and `BASH_BLOCK` regexes are both evadable (quoting, variable indirection, `git -c x=y push`) and over-blocking.
- Also noted: `git stash`/`checkout`/`merge` are allowed and can each revert a frozen canonical file's content in the worktree without any Write/Edit — and nothing runs the manifest check automatically.

This is build-harness scope, not product scope — but the four `.claude/` files sit inside the Phase-0 signature set, and the threat model cites them as enforcement.

### 13.3 Electron 31.7.7 — reachability triage turns 32 advisories into a decision

Configuration verified: `contextIsolation:true, nodeIntegration:false, sandbox:true` (`main.js:2406`); `loadFile` only, **no remote content ever loaded** (`:2446`); CSP `script-src 'self'` with no `unsafe-eval`/`unsafe-inline` (`index.html:5`); both permission handlers installed with a microphone-only allow-list that refuses video outright (`:2432-2445`). **Zero occurrences** repo-wide of `window.open`, protocol registration, `<webview>`, `<iframe>`, offscreen rendering, `setAsDefaultProtocolClient`, `setLoginItemSettings`, `shell.openPath`/`openExternal`, `clipboard.*`, `second-instance`, `app.commandLine.appendSwitch`.

| Advisory class | Reachable here? |
|---|---|
| Chromium/V8 renderer RCE via remote web content | **NOT REACHABLE** — there is no browsing surface |
| Chromium bug via locally rendered untrusted text (PTY output through xterm.js; glyph/text-shaping) | **RESIDUALLY REACHABLE (low)** — the only live Chromium exposure |
| Context-isolation bypass; contextBridge prototype/setter advisories | **APIs IN USE** — reachable only after prior renderer script execution; **severe if reached** |
| `window.open` / navigation escapes | **not reachable in normal operation, but NOT MITIGATED** — no `setWindowOpenHandler`, no `will-navigate`; CSP `default-src` does not constrain top-level navigation |
| webview, offscreen, custom protocol, protocol-handler argv injection, `shell.*`, clipboard, command-line switch injection | **NOT REACHABLE** — APIs unused |
| DevTools-mediated | **OPERATOR-ONLY** — never opened programmatically, but the default menu is left in place |
| `extract-zip` symlink traversal (the second HIGH) | **DEV-TIME ONLY** — reached via `@electron/get` during `npm install`; cannot be triggered by running the app |

**Urgency verdict:** the semver-major jump to 43.4.0 is **moderate, not emergency** — *provided* the renderer-chooses-the-executable defect (R-03/E-01) is fixed, because that is what converts a renderer bug from a sandbox escape into host code execution. Two zero-cost hardening steps buy most of the value without the node-pty ABI rebuild: a `setWindowOpenHandler` returning `{action:"deny"}`, and a `will-navigate` listener that calls `preventDefault()` for any URL not starting with `file://`.

This supersedes R-16's framing: the exposure is real but narrow, and the ordering is **R-03 first, hardening second, upgrade third**.

### 13.4 Consequent correction to §9

Add to **Tier 1**: the two Electron one-liners above (zero cost, close two advisory classes outright). Move the Electron **upgrade** to Tier 3 with its ABI-rebuild unit, as already sequenced. Add to **Tier 2**: a `status` column in `THREAT_MODEL.md` (13.1) — it is the artifact an auditor reads to decide what is safe to run live, and it currently over-reports by five controls.

### 13.5 Three corrections the completed security report forces on earlier sections

**(a) A narrowing that must NOT be misread as downgrading R-01.** The security reviewer narrows "`notify_*` has no role gate" to INFO — but that verdict is about the **MCP-side** calls in `mcp_server/sovereign_tools.py:156,185,195,204,266`, where each `notify_*` is a side effect of a write the policy layer has *already* authorized (`collaboration_service.py:104,179,238`). That narrowing is correct **for that path**.

It does not touch **R-01**, which is about the *other* entrance: the Electron HTTP gateway handlers at `application-control.js:285-324`, reachable **directly** with the node's bearer token from the CLI child env, bypassing `mcp_server/` and the policy layer entirely. On that path there is no prior authorization to inherit — the caller supplies `recipient_node_ids`, `message_id` and `debate_id` verbatim, and `pane-writer.js:327-330` routes them to the conductor's pane. **R-01 stands at CRITICAL.** The two verdicts are consistent because they describe two different doors to the same room; anyone reading only the reviewer's INFO line would draw the wrong conclusion, which is why it is stated here.

**(b) R-03/E-01 is sharper than written: the process starts before supervision decides.** `terminal/conpty/session-manager.js:69` calls `this._ptyFactory(spec)` — the OS process is created — and `supervisor.admit({id, nodeId, pid})` is not called until `:101`. The file concedes this itself at `:76-77`: *"A denial still created an OS process, and kill() is only intent."* So a renderer-chosen executable (`spec.file`/`spec.args`, unsanitised by `sanitizeRendererSpec`) is **launched first and judged second**, and a supervision denial can only try to kill something already running. That is what makes R-03 the highest-leverage fix in the desktop area: it converts a renderer compromise from sandbox escape into host code execution, and no admission check stands in front of it.

**(c) A strong positive worth recording: the dangerous-call census came back essentially clean.** Repo-wide, product code contains **zero** `eval`, `exec(`, `pickle`, `yaml.load`, `os.system`, or `subprocess(shell=True)` in Python, and **zero** `new Function`, `vm.runIn*`, or shell-string `child_process.exec()` in JavaScript. No template-built SQL. `mcp_server/__init__.py:21-37` is an allow-list lazy importer rather than dynamic dispatch. The single RCE-shaped path in the tree is `Invoke-Expression (Invoke-RestMethod 'https://antigravity.google/cli/install.ps1')` at `tools/providers/run_frontier_providers.ps1:371` — an unpinned remote installer, but gated behind `-InstallMissing` and disclosed in place (reviewer S-06, LOW). This materially supports §8: the codebase's execution surface is disciplined, and the defects found are at boundary composition points rather than in how it runs code.
