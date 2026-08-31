# EPC-03 — conductor orchestration, layers 3 to 6

**Directive:** `release-planning/EPC-03-DIRECTIVE-20260831.md` (ENTRY 036)
**Seal at start:** `45cfc92` · **Seal at finish:** the commit this report is sealed in
**Date:** 2026-08-31 · **Mode:** continuous, reporting once

---

## What the operator asked for

> *"the conductor is absolutely supposed to be talking to those models and communicating with
> them, injecting their prompts, telling them what to do. I should be able to tell the conductor
> to open up two more terminals, and then it automatically open them up… it's gotta be able to
> communicate with those extra workers."*

All four capabilities in that sentence now exist in code and are proven against the running host.
One of them cannot be proven end to end without a terminal the operator opens, and that is stated
rather than worked around.

---

## Layer by layer

### Layer 3 — the conductor knows which panes are up

**L3-1 · done** (`af79ae7`). `emit_worker_launch`'s local branch hardcoded a no-record result and
never called `_register_pane_node` at all. It read as a design statement while being the reason
invariant 2 was unmet for every local terminal on the host — measured: 154 node events,
`grok_build` 22, `google_antigravity` 20, local **0**. The branch now registers. Under D-1 the
test asserting it must not was inverted; its `claude_code`/`codex` sibling still asserts no-record,
because those remain genuinely unwired.

**L3-5 · done** (`7a06a0c`). `pane_presence` shipped in EPC-02 able to fold a registry and was
never handed one — every caller left `pane_records` at its `()` default, so the operator's surface
reported `panes_present: []` on a host with panes open. `node_log_reader` reads the durable log
**read-only**, never constructing an `AppendOnlyEventLog`: that class opens for append and caches
`prev_hash`, and a second opener writes duplicate `seq` values and breaks the chain permanently.
`resolve_worker_ids` prefers live registered panes; `DEFAULT_WORKER_IDS` is untouched and remains
the fallback. The registry is read **once**, at the I/O boundary, so the feed cannot say it
dispatched to a pane it does not also list as present.

The operator's DISPATCH line now reads `2/2 pane(s) live (dispatched)`, or `no registered panes`
on a host with none.

**L3-2, L3-3, L3-4 · PARKED — require a pane the operator opens.** A durable node row can only be
written when a pane is spawned, and panes opened before `af79ae7` cannot retro-register. No
fabricated row was written. The registration was instead proven through a redirected log
(`SOW_NODE_EVENT_LOG` → a temp path, the operator's store untouched):

```json
"node_class": "worker_reasoning",  "class": "worker_reasoning",
"locality": "local",  "subscription_ref": null,  "lease_id": "",
"model_ref": "granite4.2:3b",
"capabilities": [{"requirements": {"locality": "local_only", "min_context": 8192}}],
"state": "SPAWNING", "pid": null
```

To close these three: open one worker pane in the app. The row appears, `attest_spawned` fires on
the existing path, and presence names it. Nothing further is needed from the builder.

### Layer 4 — the conductor reads what the workers are doing

**L4-1 · done.** The bounded reader already existed (`createScreenWindow` over
`RingBuffer.sliceFrom()`). `pane-observation.js` composes it into a `pane_observation@1.0` record,
reusing the shared window instance rather than constructing a second one that could drift.

**L4-2 · done, and the directive's premise was wrong.** D-4 says *"`LogRing` already strips ANSI,
control characters and redacts"*. Two of three. Measured: `plainScreen` strips OSC and CSI
sequences and control characters, and redacts **nothing**; every `scrub`/`redact` in this tree is
ENVIRONMENT scrubbing, keeping credentials out of a child process rather than out of its output.
There was no output redactor to reuse.

That was contained while the window's only consumers were a pattern classifier and a write gate —
text matched inside one process and thrown away. Layer 4 changes the consumer to a language model,
and prompts get logged, cached and carried into evidence artifacts on disk. The same bytes acquire
a different exposure the moment their destination changes, so the redactor arrives **with** the
change of destination.

It is a net, not a proof, and reports what it removed rather than certifying that nothing remains.
Removed spans become `[REDACTED:kind]` markers, not gaps. It fails **closed**. Redaction runs
**before** the character bound, because truncating first splits a secret across the boundary and
strands a suffix that matches no rule.

**L4-4 · done, measured rather than assumed.** The first draft carried "roughly 0.5 MiB per 1k
tokens" for the KV cache — about 290× too small, arithmetic nobody had run. Loading `qwen3:8b` at
four context lengths and reading `/api/ps` and `nvidia-smi` at each:

| `num_ctx` | resident | in VRAM | GPU |
|---|---|---|---|
| 2 048 | 5 030 MiB | 5 030 MiB | 6 830 / 8 151 |
| 4 096 | 5 320 MiB | 5 320 MiB | 7 120 / 8 151 |
| 8 192 | 5 900 MiB | 5 900 MiB | 7 339 / 8 151 |
| 16 384 | 7 450 MiB | 5 809 MiB | **SPILLED** — 1 641 MiB to system RAM |

145 MiB per 1k below the spill point, ~4 740 MiB of weights. At 16 384 the card gives up while
`/api/ps` still reports the model loaded — the failure this build already paid for at
`num_ctx: 131_072`. The derivation lands on **8 192**, the last fully-resident step, and yields
**8 000 characters** of pane observation per turn, shared across panes because the conductor has
one context window and not one per pane.

**L4-3 · done.** `pane_observations` sits beside `pane_presence` on the dispatch feed and carries
no `legs` key, deliberately, so the shape itself shows it cannot make an execution claim. A
drifted producer is refused rather than best-effort parsed. An overrun is reported, never silently
corrected.

### Layer 5 — the conductor delegates and reads the result back

**L5-1 · done.** `conductor_spawn.spawn_claude_code_conductor` calls itself *"the ONE place a LIVE
claude_code-backed conductor is born"*, and that was literally true: with no `claude` CLI it raises
`ClaudeCliUnavailable`, so on this host no conductor could spawn at all — while
`control_plane/conductor/registry.py` went on deriving LOCAL conductor seats from the operator's
model ceiling. The system offered a seat no code path could fill.

Every frontier gate has a local counterpart: the roster gate is the same call on the local
capability; `assert_provider_live` becomes `classify_local_model`'s cloud refusal, which is the
spend wall on a local path; the CLI check becomes the runtime **and** the model, refused
separately because an install and an un-run `pull` are different fixes; and the subscription
allowance becomes a `ResidencyPlanner` reservation.

One gate has no counterpart and the module says so: the R8 §6 operator live-terms confirmation
guards **spend**. Requiring it for a free local call would train the operator to click past the
confirmation that guards real money.

**Proven live:** `qwen3:8b` decomposed a real objective into 3 structured tasks in 10.7 s,
`parse_mode: structured`, `model_verified: true`.

**L5-3 / L5-4 · done.** The existing `assign_task` path writes a task into a pane and waits for
that worker to call `publish_candidate` over MCP — correct for a frontier coding agent with the
Sovereign tools wired in, impossible for a pane running `ollama run llama3.2:3b`. A local worker
was assignable and could never complete an assignment, because completion was defined as a call it
cannot make.

So the shell reads the answer off the pane and publishes it on the pane's behalf, carrying the
difference rather than smoothing it: `self_published: false`, `source: "observed_pane_output"`. It
reuses the U328-gated write path (a conductor's prompt is not exempt from a gate the operator's own
voice is subject to), the Layer 4 window, and the stream-position mark so an earlier run's output
cannot satisfy this turn. It waits for the pane to go quiet, because a local model streams and
reading on the first byte publishes half a sentence.

**Proven against a real streaming model** (`llama3.2:3b` behind a real `RingBuffer`, echo
included): delivered, answered in 12.1 s, prompt echo excluded from the candidate, three usable
bullets, `self_published: false`. What that cannot prove is the ConPTY itself, which needs a pane
the operator opens.

One defect found by testing rather than inspection: the pane echoes what we wrote, so a pane that
never answered still looked answered and the delegation published its own prompt back as the
worker's candidate. Fixed with `pane-writer.withoutOwnEcho`, reused rather than reimplemented.

**L5-5 · PARKED,** dossier at `docs/evidence/EPC-03-PARK-L5-5-LOCAL-WORKER-LEG.md`.
`derive_worker_legs` classifies a row that executed, is live-bound, spent nothing and carries no
verification as `skipped` — with the comment *"reached no model at all"*, the one thing definitely
untrue about a local pane that just answered. The derivation is not wrong; it was written for
subscription-backed workers where `spent` is the proxy for a call happening, and it has no
vocabulary for a worker that executes without spending because until now none could. Setting
`spent: true` would put a spend on the record for a free call; setting `verified: true` from a
reported tag is the reasoning `OllamaConductorBackend` already refuses for itself. Both are edits
to the guard's inputs designed to change its output. `legs.workers` stays `mock`, U58 stays owed,
and the dossier gives three bounded options.

### Layer 6 — "open two more terminals"

**L6-2 · done, measured first.** `qwen3:8b` against `/api/chat` with one tool declared: an
objective needing three parallel reviewers produced a tool call; an objective needing none, with
three panes already idle, produced none and said *"No additional workers are required for this
task."* Both directions — a model that always calls the tool is not deciding anything.

**L6-1 / L6-3 · done, with almost no new machinery.** `spawn` is **already** a protected verb
(`command_broker.py:27`, beside `grant`, `promote`, `elevate`); the broker already refuses to
auto-execute one from any source; the drawer already has `ApprovalKind.PROTECTED_ACTION`;
`apply_protected_decision` already routes the answer back. A conductor asking for a terminal gets
exactly the treatment the operator's own spoken *"spawn a worker"* gets. A separate approval path
would have been a second implementation of a decision the broker already makes.

**L6-4 · done, measured.** From the same host figures: 8 151 MiB total, less a 2 000 MiB host
reserve, less ~5 927 MiB for an 8B conductor at 8 192 context, leaves 224 MiB — which holds
**zero** co-resident workers. Even a 3B conductor at 4 096 leaves room for exactly one 3B worker.
That is arithmetic on the operator's card, and it is why D-2's *"≤4B workers"* is the right slate
rather than a compromise. A bound of zero names both levers — a smaller conductor, or a shorter
conductor context — and pulls neither.

One framing correction made before shipping: the number bounds concurrently **resident** worker
models, not open terminals. An idle `ollama run` pane holds no VRAM, so a host carries more open
panes than simultaneous answers, and the extra ones cost a model swap rather than a refusal.

**The whole layer, proven live through the shipping functions:**

```
derived bound : 1 pane(s)
requests      : 2
  qwen2.5:3b-instruct  admissible    "Reviewing the auth module requires dedicated parallel processing."
  phi4-mini:3.8b       REFUSED       "this host holds at most 1 worker pane(s) (8151 MiB VRAM
                                      measured by nvidia-smi, ...) and 0 are already up"
drawer: protected_action | spawn qwen2.5:3b-instruct | origin conductor | model_initiated true
```

The model asked for two terminals — the operator's sentence, exactly — the bound allowed one with
the arithmetic stated, and the admitted one is waiting for the operator. Nothing spawned.

---

## Phase R — the release is re-cut

Not in the operator's list; included because work that exists only in the worktree is not
delivered.

Two defects were found by the release gates and fixed rather than allow-listed:

1. **The boundary gate failed on five credential patterns**, all in the Layer 4 redaction tests.
   The gate is right — its job is that the archive carries no credential-shaped bytes, and neither
   it nor a recipient's own scanner can tell a fixture from a leak. There is a precedent for
   allow-listing exactly this; it was not taken, because an allowlist keeps the bytes in the
   archive and moves the cost to the recipient. The fixtures are assembled at runtime instead: the
   redactor receives identical characters and the file ships nothing shaped like a secret.
2. **A build-host path shipped in a test fixture.** `test_developer_identifiers_are_bounded` —
   a guard written earlier in this programme — caught it. Its own message is the rule: *"Fix the
   file — do NOT add it here unless you can say why it cannot be fixed."* There was no such
   reason.

**Measured on the lane, at `0e2530a`:**

| | |
|---|---|
| pytest, whole product | **4 000 passed, 1 failed**, 4 skipped, 461 subtests, 16 m 55 s |
| Node — SOW desktop | 1 132 passed |
| Node — SOVEREIGN UI | 26 passed, TypeScript clean |
| Release gates | all seven PASS |
| Boundary gate (distribution) | PASS — 0 violations, 0 credential hits |
| Lane stages | 13: 10 passed, 1 failed, 2 skipped (clean-room, opt-in) |

The previous statement recorded 3 822 passed / 8 failed. The seven frozen-schema failures are gone
because the **operator** decided the item (ENTRY 027), not because of any code change; the count
rose by ~180 because EPC-02 and EPC-03 added tests. `RELEASE-ASSURANCE.md` now says both.

The one remaining failure is the Debate module's known cross-run interference, and one property of
it is newly measured: it is **intermittent**. Two whole-product runs within the hour — it did not
fire in the first and did fire in the second. That rules out "deterministic in the combined run",
the phrasing the document used, and points at ordering or timing. A narrower unknown, still an
unknown.

**Artifacts re-cut from the seal commit**, all eight, each verified against the build manifest and
its `.sha256` sidecar: 8 artifacts, 0 mismatches. Provenance cross-hash: all five modules OK.

---

## What was NOT done, so absence is not read as success

- **L3-2/L3-3/L3-4** need one pane the operator opens. Not fabricable.
- **L5-5** is parked with its dossier; `legs.workers` stays `mock` and U58 stays owed.
- **No frontier call was made.** `live_operation.json` stays absent. The directive could not grant
  provider spend and did not.
- **No gate status was written.** Nineteen of twenty-nine gates have still never been evaluated by
  any reviewer, and no quantity of passing tests moves that number.
- **The lane has still never run on a hosted Windows runner**, and the clean-room install and
  verify were skipped (opt-in; they mutate the machine).
- **`Start-Shell.ps1` still prints `Stopped.` without verifying it stopped anything** — it left an
  orphan holding port 5180 earlier in this programme. Offered, never authorized, so untouched.

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
