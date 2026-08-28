# SOW REMEDIATION PROGRAMME — FINDING INTAKE (W-06)

**Document id:** SOW_REMEDIATION_FINDINGS_20260816
**Governs:** `SOW_REMEDIATION_EXECUTION_DIRECTIVE_20260816`, unit **W-06** (punch list 1.0)
**Baseline:** HEAD `bad029e76a0bcc2f57062245ccf67ddf9394e47d`, branch `main`
**Status:** **CONSTRAINED-NOT-CLOSED.** See §0.

Provenance labels follow the directive's §0.1: **[OBSERVED]** = re-derived or executed here;
**[REPORTED]** = adopted from a sub-reviewer, not independently re-executed.

---

## 0. WHY THIS IS NOT IN THE REGISTER — an unresolved conflict between two operator rulings

W-06 as specified appends to `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`. That file **is one of
the three 19.10 worktree entries** named in the directive's §3.6, and operator ruling **D-4** froze
those entries: *"Leave the three 19.10 worktree entries exactly as they are."*

Operator ruling **D-3** requires register-before-repair. The two rulings therefore collide on this
exact file. Under the directive's own §0.3 the tighter reading governs, and D-4's "exactly as they
are" is tighter than D-3's choice of location — so the register was **not modified**. Its SHA-256 is
still `687acf7af073d7cd8eb8e213538076c31bca94e825e19770f46c970b0fb18e19`, byte-identical to the
W-00.1 baseline.

This document records the findings **before** any Tier 1 repair, which is D-3's substance. Only the
location differs, and it uses `docs/evidence/`, the repository's established convention — it is not
a new governance document, hierarchy or taxonomy (§10, rule 9).

**Owed to the operator, and blocking:**
1. A ruling on D-3 vs D-4 for this file. If D-3 is read strictly as *the register file
   specifically*, then Tier 1 repairs are blocked until D-4 is answered and this content is merged
   into the register under the ids proposed below (U445–U447).
2. W-06's acceptance criterion — *"every Tier 0–3 unit has a register id"* — cannot be met until
   that merge happens. It is **not** claimed as met here.

---

## 1. W-00 PRE-FLIGHT AND BASELINE — proposed as U445

Baseline verified [OBSERVED]: HEAD `bad029e7…`, branch `main`, 50 tags, `gate/phase-19` absent, and
the three recorded worktree SHA-256 values byte-exact.

**Baseline deviation, recorded rather than treated as refusal condition R1.** The tree carries
**four** entries beyond HEAD, not three. The fourth is untracked
`docs/evidence/INDEPENDENT_REVIEW_WINDOWS_HOST_20260816.md` (297 lines, sha256 `72260296…e392`) —
the review that produced the directive. R1 fires on a HEAD mismatch or on the three entries
drifting from their recorded hashes; neither happened, and an added untracked evidence file is not a
mismatch of an enumerated item. Left untouched under D-4.

**Suite baseline on the target host [OBSERVED]:**

| Suite | Result |
|---|---|
| `py -3.12 -m pytest -q` | **2382 passed, 1 skipped**, 703.97 s, exit 0 |
| `apps/desktop` `npm test` | **1020 tests, 1020 pass, 0 fail, 0 skipped**, 99.5 s |
| `terminal/test` (15 files) | **216 tests, 216 pass, 0 fail, 0 skipped**, 0.22 s |

The tracked `pytest.ini` contract (`2381/1/1`) remains stale; the uncommitted 19.10 record
(`2382/1`) is the accurate one and is reproduced here. D-4 defers its adoption. The single skip is
`tests/unit/test_run_frontier_providers_ps1.py:522` (host-coupled, `SOW_PROVIDER_HOST_CHECK=1`) —
notable because it is the `.ps1` provider leg that F-1 leaves untested.

---

## 2. THE FALSIFICATION TESTS — F-1 … F-6

| id | Result | Disposition |
|---|---|---|
| **F-1** | Clone at a path containing `&`. cwd `work&space` and argv `a&b`, `%PATH%`, `c\|d`, `e\rf`, `g;h`, `$(id)`, `` `whoami` `` all reached the child **byte-literal** through `run_managed_process`; rc=0, no shell interpolation | **W-38 severity reduced for the Python supervised path.** The Node/`.ps1` leg is NOT tested and remains open. Sharpened: `codex` and `grok` resolve to **`.ps1`**, `claude` to `.exe` — W-38 anticipated only `.cmd`. R-14/N-03 reports the `.cmd` shim executing on this host, so the residual is real |
| **F-2** | Leg a (gateway first): a second bind **succeeds** but the gateway keeps all 20 connections. Leg b (squatter first): the gateway's `start()` **succeeds and reports its port as healthy** while **all 20 connections go to the squatter** | **W-31 severity RAISED to HIGH.** The naive hijack is refuted; silent pre-bind interception is the defect. Compounds with W-40: `run_gateway.py` prints `IPC_TOKEN=`/`IPC_KEY=` immediately after a "successful" bind an unprivileged local process is holding |
| **F-3** | Supervised run median **15.150 s** vs **0.028 s** bare control; tax **15.12 s**, spread 23 ms across 3 runs — a fixed wait, not variable work | **CONFIRMED**, root cause located: `adapters/frontier/process_tree.py:227` `job.terminate_and_wait(15.0)` → `:128` `WaitForSingleObject(handle, 15000)`, in the `finally`, paid on **every** probe including clean exits. Corroborates N-04 |
| **F-4** | `npm audit`: **2 vulnerabilities, both high, 0 critical** — `electron` (direct) and `extract-zip` (transitive, `effects: electron`) | Both resolve **only** via `electron@43.4.0`, `isSemVerMajor: true`. There is no surgical fix. Supports the directive's ordering: W-29 and W-30 first, since GHSA-9wfr-w7mm-pc7f (renderer command-line switch injection) and the `window.open` scoping advisories (GHSA-f3pv-wv63-48x8, GHSA-v93f-fgjr-hjrj, GHSA-9f4c-93c8-jc8g) are exactly what those two one-liners mitigate |
| **F-5** | 154 node events: `grok_build` 22 spawns, `google_antigravity` 20, `openai_codex_cli` **0**, `claude_code` **0** | **Proposed finding F6 DISCARDED as a new defect** — it is the already-open **U313**. See the correction in §3 |
| **F-6** | Run after W-04 landed: `tools/list` is **9023 bytes, valid UTF-8, zero raw `0x97` bytes**, two proper UTF-8 em-dash sequences | The **encoding** root-cause candidate for F2 (N-01) does **not** survive W-04. **W-55 must NOT be credited with fixing F2.** The second candidate, **N-02** (the module is cwd-dependent and no MCP config pins a `cwd`), is untouched by W-04 and remains open. Only a live Codex conductor bring-up settles F2 |

---

## 3. F-5 CORRECTION — the first answer given in this programme was wrong

The initial F-5 answer reported *"no code gate exists"*, derived from `FRONTIER_PANE_ADAPTERS`
(`node_runtime/supervisor/worker_pane_spawn.py:114`) containing all four providers. **That is the
LAUNCH gate.** The **REGISTRATION** gate is a different set:

- `_register_pane_node` (`tools/live/emit_worker_launch.py:513`) refuses any adapter outside
- `_OP12_PANE_NODE_ADAPTERS` (`:124`) = `REGISTRABLE_PROVIDERS`
  (`node_runtime/supervisor/provider_node_registration.py:123`)
- = `{google_antigravity, grok_build}` — [OBSERVED], both sets printed from the live modules.

`claude_code` and `openai_codex_cli` are therefore excluded from node registration **by design and
by a documented refusal**, self-declared as owed leg **U313** (*"the OP-6 providers' panes hold a
durable terminal and are NOT Sovereign node records"*, opened 2026-08-02). The ledger could never
have contained them. No new row is warranted — **U313 is the row**, and the review's own N-05 said
so. This correction is recorded because the wrong reason was reported first.

---

## 4. PROPOSED U446 — a mutation harness row does not hold at HEAD

[OBSERVED] `py -3.12 tools/mutation/_op18d_close_mutations.py` returns **28/29 RED, EXIT=1** at HEAD.
Row **R3** (*"the incarnation is asked of memory, not of the log"*, spec-audit MEDIUM-2, mutating
`node_runtime/supervisor/provider_node_registration.py`) reports `GREEN (guard does not hold)` — the
mutation is applied and its grading test still passes.

Proven **pre-existing**: re-run with the W-03 changes stashed, the result is identical. This
**falsifies the directive's Tier 2 note** that round 2 found *"all five harnesses caught … EXIT 0"*
with only `_op12_close_mutations.py` needing repair.

Restores are byte-identical, so nothing is left mutated on disk; what is missing is the **guard**,
which is the U367 class again. Owner: Tier 2, alongside W-25. Deliberately **not** repaired inside
W-03, whose causal chain does not reach it (§10).

---

## 5. PROPOSED U447 — errors in the execution directive itself

Each re-derived on disk [OBSERVED]. Recorded so a later reader does not act on the directive's text
where the tree disagrees with it.

1. **W-31's file citation is wrong.** The directive names `control_plane/ipc/run_gateway.py`; the
   `allow_reuse_address = True` is at **`control_plane/ipc/gateway.py:257`**. A second instance is at
   `mcp_server/server.py:118`, outside W-31 as written.
2. **Tier 7's "Drop `ws` (declared, never `require`d)" is FALSE and would break the IPC client.**
   `apps/desktop/ipc/client.js:26` is `require("ws").WebSocket`, the fallback used when
   `globalThis.WebSocket` is undefined. The review already recorded this as **R-16 REFUTED**.
   **Do not drop `ws`.**
3. **W-03's `codex.py` citation is off by two** (`:673` vs the actual `:671`), and it names two
   decode sites where there are **three**: `adapters/frontier/codex.py:658` carries its own
   undecoded `subprocess.run`. (`process_tree.py:162` inherits stdio and `:242` is the repo's own
   `taskkill`; neither is defective and both were left alone.)
4. **W-27's count is wrong**: `terminal/test` holds **15** `*.test.js` files, not 14. A third JS
   suite, `tools/spike_compositor/test`, is named by no gate-runner scope.
5. **W-06's `PACKAGE_MANIFEST.txt` sub-item cannot be executed on this tree.** The file does not
   exist at the repository root and is not git-tracked — it is an artifact of the **packaged**
   candidate, which lives outside the repository root, and absolute constraint **1.4** forbids
   modifying it. **Owed to the operator, not done.** For scale: the live register carries **399**
   `###` rows of which **91** read OPEN; neither number intersects a "4".
6. **W-20's premise is package-only.** The review's R-20 narrows the freeze-check failure to the
   package; on the live tree `compute_manifest.py --check` reports OK. (W-20 is blocked on D-1
   regardless.)
7. **W-22 and W-23's premises are off-host.** On this Windows host the suite reports **0**
   host-coupled failures and **0** skipped JS legs (all 1020 ran), because `py -3.12` is present.
   The 41 failures and 28 skips are real off-host and are not observable here.
8. **`ruff` is not installed on this host**, so the project's "ruff-clean" rule could not be verified
   for any unit in this programme.

---

## 6. U330 — CORRECTION (the row's headline claim is stale)

The U330 heading records *"five of seven orchestration writers bypass the transactional path"*.
That is the **pre-19.5** state. On this baseline [OBSERVED]:

- the unfenced primitives were **deleted**, not deprecated (`persistence/store.py:303-307`);
- **0 of 9** writers bypass the fence;
- `tests/unit/test_operational_write_path.py` passes **42/42**.

Per absolute constraint 6 the original row must be left exactly as written and corrected by an
appended amendment — which is what this section becomes on merge. **U330 is CLOSED on this baseline
for the bypass claim.**

The **distinct** property — that a legal state *transition* is enforced inside the fence rather than
checked by the caller — is not this row's and is **not** closed: that is **W-05**, blocked on D-5.

---

## 7. CROSS-REFERENCES — existing rows this programme touches, NOT duplicated

- **U13** — evidence-refs presence vs resolution (punch list 6.5). Open since Phase 0.
- **U140** — voice confidence. `wsl_parakeet.py:193` is `confidence = 1.0 if text.strip() else 0.0`,
  so the I-V3 clarify gate protects against silence, not mishearing (punch list 6.18).
- **U206** — forged decision. W-43's negative test is the **inversion** of
  `tests/unit/test_session_approvals.py:297`.
- **U207** — presumed operator identity. **W-42 gates this; it does not close it.** Any write-up
  claiming closure will cause the next agent to enable approval side effects believing the operator
  identity is authenticated. Blocked on D-6.
- **U274** — CRLF/BOM. `git ls-files --eol`: **0** blobs `i/crlf`; **40** files `w/crlf` or `w/mixed`
  against LF blobs — tool-written, not committed. W-26 owns the sweep.
- **U313** — F-5's answer; see §3.
- **U410** — `record_synthesis` has no debate check.
- **U434** — no on-demand node verification. **No claim of on-demand node verification may be made
  anywhere until W-62 closes it.**

---

## 8. TIER 0 DISPOSITION

| Unit | State | Evidence |
|---|---|---|
| **W-01** | **CLOSED** | `456ab7e` — notify identifiers shape-checked and refused; recipients scoped to the notify's own task plus the conductor |
| **W-02** | **CLOSED** | `b865de4` — model-authored bodies flattened at the single write boundary |
| **W-03** | **CLOSED** | `42ec534` — transcript codec pinned on all three sites; a lost transcript no longer classifies SUCCESS |
| **W-04** | **CLOSED** | `176b0f3` — MCP stdio pinned in both directions; F-6 re-run in §2 |
| **W-05** | **BLOCKED** | operator decision **D-5** unanswered. Not a permission gate: the directive forbids choosing for the operator, and a blanket authorization does not supply which of two mutually exclusive designs (candidate *freeze* vs synthesis *invalidation*) is wanted |

Every closed unit carries a negative test **verified failing against pre-repair code**, with the
failure output recorded in its commit message. Every unit's mutation harnesses were re-run and every
restore was byte-identical.

*Document ends. It records; it closes nothing that lacks evidence.*
