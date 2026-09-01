# utc: 2026-09-01T09:24:52.2321239Z
# producer: claude-code builder EPC-04 (W-1 … W-6)

# EPC-04 — OpenCode as a pickable terminal slot

**Authority:** operator instruction 2026-09-01, quoted in §0. **Repo:** `release-worktree`, `main`.
**Seal at start:** `570a642`.

---

## 0. The instruction this answers

> *"I want open code, the harness, to be one of the model selections in the multi model app so I can
> use it from the multi model app. The conductor can conduct it if needed, but I want open code, the
> harness, an available slot to be picked in one of the terminals, and then I'll load a model into
> it."*

and, on execution:

> *"Stop doing this in segments. Get it done. … Don't come back until open code is done in the
> system and operational."*

---

## 1. Result against the directive's five done-when conditions

| # | Condition | Verdict | Where measured |
|---|---|---|---|
| 1 | The picker offers OpenCode as a selectable option, with the local models it can drive | MET | §3, live host picker |
| 2 | Choosing it spawns a pane that registers as a Sovereign node — `class`, `locality: local`, a residency reservation, no subscription | MET | §4, §5 |
| 3 | The pane reaches a live process with an attested pid | MET *for the spawn*; the shell's `READY` attestation itself was not driven — see §7 | §6 |
| 4 | The session is confined to its own git worktree; the trunk working tree is unmodified after | MET | §5 |
| 5 | `worker_pane_spawn` no longer refuses the local coding role with U95 | MET | §2 |

`FACT[docs/evidence/EPC-04-OPENCODE-PANE-20260901.md]` — every number below was produced by a run on
the operator's host on 2026-09-01, not derived from a model card or a constant.

---

## 2. W-1 — measurement first, and what it decided

`opencode --version` on this host: **1.18.25**, resolving to
`C:\Users\Sslaw\AppData\Roaming\npm\opencode.CMD`.

`--help` reports the TUI as the **default** command, taking the project directory positionally, with
`-m provider/model`, `--pure` and `--auto`. So **Option A** (a real interactive pane) was available
and was taken; Option B was not needed. `ASSUMPTION` — none; this is the binary's own output.

The `.CMD` spelling matters and is handled rather than ignored: npm ships Windows shims as batch
files, cmd.exe re-parses the argument vector, and `adapters/cmd_shim.assert_cmd_shim_argv_safe`
(independent review N-03) refuses `& | ^ < > %` in any argv element destined for one.
`build_interactive_opencode_command` calls it before returning.

**U95 is lifted, not deleted.** The refusal it replaces read:

> *"a local CODING pane is the supervised OpenCode-harness path (worktree-isolated, Phase 10 / 14C),
> not a bare `ollama run` session — deferred, not unavailable (U95)"*

It named a route rather than denying one. Its **reason** — *"a coding role without a worktree would
be a model with write hands and no containment"* — is now **enforced** instead of deferred to: the
worktree is a precondition, and its absence refuses the pane under `GATE_WORKTREE_UNAVAILABLE`.
The frontier coding path is untouched and still refuses under `GATE_ROLE_DEFERRED`.

---

## 3. W-2 — the picker, measured live

`build_host_picker` on this host, 71 models enumerated from the daemon:

```
groups : ['claude_code','openai_codex_cli','grok_build','google_antigravity','ollama_local','opencode_local']
counts : {'total': 84, 'available': 72, 'frontier': 7, 'local': 77}
OpenCode options: 6   (codestral, devstral-small-2, qwen2.5-coder:32b,
                       qwen2.5-coder:3b-instruct, qwen3-coder-next, qwen3-coder:30b)
```

OpenCode is its **own provider group**, registered in `_PROVIDER_TABLE` with locality `local` —
which is what keeps it out of `registered_frontier_providers()` and therefore out of the status
bar's n/allowance counters. An OpenCode pane holds no subscription terminal, and counting one would
advertise spend that does not exist.

Availability was verified to **agree model-for-model** with the bare Ollama group, so the two local
groups cannot disagree about whether a model can run.

Absence is disclosed, never hidden: with the CLI absent the six options are still listed and greyed
with the reason, per this module's stated contract (S-19 / ENTRY 017).

**One defect found and fixed in passing.** `build_pane_picker` assembled its flat `options` list by
naming each group literally (`anthropic + openai + grok_options + antigravity_options + local`) —
directly above a comment warning about exactly that hazard. Adding a provider to the table and to
`by_provider` left the flat list and every count silently omitting it. `flat` is now **derived from
the groups**, so `options == the union of the groups` holds by construction.

---

## 4. W-5 — node registration

`opencode_local` is added to `_PROVIDER_FACTS`, which is the single declaration
`REGISTRABLE_PROVIDERS` is derived from:

* node class **`worker_coding`**, not `worker_reasoning` — a conductor routes on this, and filing a
  file-editing harness as a reasoning worker answers the registry's question wrongly while looking
  correct;
* capability **`coding`**, `locality: local_only` (the `node@1.1` enum member; `"local"` is not one),
  no `tool_use` requirement;
* **residency-governed**, so the record names a `ResidencyPlanner` decision and carries **no lease** —
  a synthetic lease id would assert a subscription terminal nobody counted (invariant 19).

`RESIDENCY_GOVERNED_ADAPTERS` gained the adapter. One existing test asserted that set by exact
equality; it was restated as the rule it was defending — *no frontier adapter is in the set* — which
is stronger and does not break the next time a local adapter is added.

---

## 5. W-3 / W-6 — containment, measured

`WorktreeManager` gained **`ensure()`**: `create` is not restart-safe, because `_nodes` is in-memory
and a reopened pane would hit `git worktree add -b` on an existing branch and be refused. `ensure`
reconciles against `git worktree list --porcelain` and adopts the pane's own tree — and **refuses to
adopt one registered anywhere else**, which is where the containment is actually kept.

Live run, against a scratch repository named through `SOW_CODING_BASE_REPO`:

```
AUTHORIZED
  adapter      : opencode_local
  locality     : local
  role         : coding
  subscription : None          sub_governed : False
  residency    : loading   decision={'model':'qwen2.5-coder:3b-instruct','scheduled':True,
                                     'status':'loading','reason':'fits in free VRAM'}
  cwd          : …\project\worktrees\opencode-live-1
  argv         : [opencode.CMD, …\worktrees\opencode-live-1, --pure, -m,
                  ollama/qwen2.5-coder:3b-instruct]

CONTAINMENT
  worktree exists      : True
  inside the base repo : True
  on its own branch    : node/opencode-live-1

TRUNK AFTER THE NODE WROTE app.py AND COMMITTED ON ITS BRANCH
  node branch HEAD     : de96ed5f716e  (moved: True)
  trunk HEAD unchanged : True
  trunk files unchanged: True      (sha256 per file, before vs after)
  trunk status clean   : True
```

`--auto` is **absent** and that is a containment decision, not a default: OpenCode's own help calls
it *"auto-approve permissions that are not explicitly denied (dangerous!)"*. `--pure` is on, so
unmeasured plugins do not run beside a model with write hands.

**Base-repo resolution** (`node_runtime/supervisor/coding_worktrees.py`) is explicit and fails
closed: `SOW_CODING_BASE_REPO` if set (and a real repo, else refuse rather than silently code in a
different project), otherwise the nearest enclosing git repository of the workspace, otherwise
**None** — which becomes a refusal upstream. No repository means no containment means no pane.

`INTERPRETATION` — the live proof used a scratch repo deliberately. The default resolution would
walk up from `modules/sow` to the release repo, and a proof run must not leave `node/*` branches in
it. The override is the product's own first resolution rule, so the same code path was exercised.
Pointing a pane at a real project is the operator's call, via that variable.

---

## 6. W-6 — the process actually runs

The authorized argv was spawned for real, under the harness's scrubbed environment:

```
opencode --version : rc=0  '1.18.25'
credential vars scrubbed from the child env : 18
pid 33184 — ALIVE after 25.0s, then terminated by the harness
```

`FACT` — the process started from the resolved `.CMD`, in the worktree, with the `ollama/*` model
ref, and stayed up. The harness's own exit was `124` because it blocked reading the TUI's pipe after
`terminate()`; that is a defect in the measuring script, not in the product, and the liveness
measurement it was taken for had already completed.

---

## 7. What this did NOT do, stated plainly

* **The conductor driving OpenCode is out of scope** and was not attempted. The operator said "can
  conduct it if needed" — permission for later, not this loop's goal.
* **Condition 3 is met at the process level, not through the shell's attestation path.** A real pid
  was observed for the authorized argv; `attestWorkerPaneSpawned` reaching `READY` from an Electron
  ConPTY was not driven in this run. The shell-side ticket acceptance IS covered
  (`worker-launch-source.test.js`, 6 new tests), and the allowlist entry it needs is in place.
* **No gate status was changed. `GATE-LEDGER.json` was not touched.** 19 of 29 gates remain
  `evaluated_by: null`; this loop does not move that number.

---

## 8. Falsification — the containment guards were mutation-proven

The directive required it (§6.3: *"a guard that cannot fail proves nothing"*). Six mutations, each
breaking one containment property; source restored and sha256-compared after every one.

```
baseline sha256 b6d724c2c2c9e3cc   restored b6d724c2c2c9e3cc   identical=True

CAUGHT  helpful fallback: no manager -> run in the workspace
CAUGHT  pane runs in the trunk instead of its worktree
CAUGHT  provisioning failure swallowed
CAUGHT  opencode absence gate bypassed
CAUGHT  subscription claimed on a local coding pane
CAUGHT  --pure dropped: unmeasured plugins beside a model with write hands
```

**Round 1 produced two survivors and both were defects in the harness, not holes in the guards.**
Recorded because reporting them as findings would have been false:

1. `if False:` on the no-manager refusal still refused — via `AttributeError` on `None` caught by the
   provisioning handler. Containment held; the mutation never breached it. Replaced with the
   realistic breach: the *helpful fallback* a future editor adds.
2. The subscription mutation used an anchor appearing **twice**; `replace(…, 1)` mutated
   `_authorize_local` (the reasoning pane) at line 800 instead of the coding pane at 893, and the
   coding-only test filter never exercised it. Re-anchored from the end of the file.

A dead guard was also found and removed while writing these: the first draft's
`if not exe:` after `_resolved_binary(...)` could never fire, because `_resolved_binary` **raises**
on empty and never returns falsy. It read like a gate. It is now a real presence check on
`shutil.which("opencode")`, with its own gate id `GATE_OPENCODE_ABSENT`, and a test that proves it
by injecting absence at the seam.

Related, and more serious: that draft passed the caller's `executable` to OpenCode. A local coding
option is an **`ollama_local`** option, so the executable reaching that function is **ollama's** —
launching it with OpenCode's argv would have run the wrong program with a worktree path as its first
argument. The parameter was removed so it cannot be done.

---

## 9. Tests

| Suite | Result |
|---|---|
| `modules/sow` pytest, whole module | **3168 passed, 0 failed, 3 skipped** |
| `apps/desktop` node --test, whole shell suite | **1138 passed, 0 failed** |
| New: `test_worktree_ensure.py` | 7 (real git repositories, not stubs) |
| New: `test_pane_picker_opencode.py` | 14 |
| New: `test_opencode_pane_registers_a_node.py` | 10 |
| New: coding-pane cases in `test_worker_pane_spawn.py` | 4 |
| New: OpenCode ticket cases in `worker-launch-source.test.js` | 6 |

Two existing tests were **rewritten, not deleted**, because EPC-04 deliberately changes what they
assert; both now state the rule they were defending:

* `test_local_coding_role_is_refused_as_deferred_not_unavailable` → the containment refusals;
* `test_both_coding_paths_refuse_under_the_deferred_role_gate` → split, so the frontier half keeps
  asserting `GATE_ROLE_DEFERRED` and the local half asserts `GATE_WORKTREE_UNAVAILABLE`.

`test_two_coding_panes_never_share_a_worktree` was removed rather than kept: against the fake it
proved only that a dict was keyed by node id. The property lives in
`test_worktree_ensure.py::test_two_panes_never_share_a_worktree_or_a_branch`, against real git.

---

## 10. Suite result

Whole-module run at the finished tree, 2026-09-01:

```
3168 passed, 3 skipped, 61 warnings in 700.85s (0:11:40)
```

Full output: `docs/evidence/EPC-04-SUITE-20260901.txt`. The three skips are pre-existing and
unrelated (host-coupled provider check, POSIX-only signalling, and a control that replays from a
commit SOW’s vendoring did not carry across).

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
