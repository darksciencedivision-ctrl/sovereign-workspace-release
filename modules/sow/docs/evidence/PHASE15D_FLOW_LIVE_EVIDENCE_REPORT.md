# PHASE 15D `.flow` — LIVE RE-RUN — EVIDENCE REPORT

**Work unit:** `phase-15d.flow` **(LIVE re-run under OP-9)** — first live sub-step of the Phase 15D
live pass (`.flow` → `.debate` → `.succession` → `.gate`, each re-run LIVE per OP-9).
**Date:** 2026-07-20 · **Iteration:** 47 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15d` is a HIGH-STAKES phase gate and closes only at `.gate`, on live
evidence, with the mandatory independent gate-validator.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` §14 (OP-9 — "Go live"), §11 track 15D,
§13 (OP-8), loop protocol §3, honesty §6/§10.4, D-LOOP-1 teardown constraint.

---

## 0. Provenance note — this supersedes an uncommitted prior attempt (read first)

A previous invocation of this exact work unit left **uncommitted** working-tree files (the code
change, the `tools/live/` tooling, a captured fixture, and a draft of this report) — the recurring
D-LOOP-1 crash-before-commit pattern the loop notes warn about, in which a survived draft "claimed a
passed gate-validator." **None of that survived draft's claims were trusted.** This iteration
independently re-established everything from scratch:

- re-ran the full suite myself (§6) and had the gate-validator re-run it in isolation (§7);
- **re-captured** the real CLI JSON shape myself rather than trusting the survived fixture (§2);
- **freshly witnessed one live smoke** myself (§1) — the acceptance-packet id below is from *this*
  iteration's run and differs from the survived draft's id precisely because packet ids are
  per-run and non-reproducible (that non-reproducibility is itself the honest limit, §7 R1);
- re-ran gate-validator **and** spec-auditor fresh (§7).

The survived draft's two-run narrative is NOT carried forward; this report records only what was
witnessed or deterministically re-derived in iteration 47.

---

## 1. The live evidence (one real `claude` call, this host, iteration 47, 2026-07-20)

One live smoke through `tools/live/run_15d_flow_live_smoke.py` — **witnessed by the builder this
iteration** (NOT part of `pytest tests/`; it spawns the real CLI — the Phase-1-spike substitution
pattern for an operator-run metric). The run spawns → exercises → tears down **within the call**
(`ClaudeCliBackend.generate` uses synchronous `subprocess.run` with a hard timeout; a synchronous
`subprocess.run` cannot return while its child lives, so the live process is gone before the driver
prints and exits 0 — **D-LOOP-1 satisfied by construction**; no background live process is spawned).

```
py -3.12 tools/live/run_15d_flow_live_smoke.py --model claude-fable-5 --timeout 150
```

Observed outcome (verbatim fields):

| field | value |
|---|---|
| `ran` / `published` / `skipped_with_record` | `true` / `true` / `false` |
| `legs` | `{conductor: "live", workers: "mock"}` |
| `selection.model` | `fable-5` (`reason: operator_selected`, `since: 2026-07-19`) |
| `executing.model` | `claude-fable-5` (`requested: claude-fable-5`, `resolved_slug: claude-fable-5`) |
| `executing.verified` | **`true`** (`verified_by: claude_code.verify_reported_checkpoint@1`, `is_fallback: false`) |
| `leg_degraded` | `null` |
| `acceptance_packet` | `m-d2f1bb8a0877f031` |
| `accepted_count` | `2` |
| `reason` | `governed flow ran on a live conductor; acceptance packet published` |

**This is the OP-9 deliverable — a verified LIVE Fable-5 conductor** driving the full governed loop:
- **Conductor decomposition is real model output:** the live `claude-fable-5` conductor produced a
  structured decomposition; the governed path accepted **2 tasks** (`accepted_count: 2`).
- **Capability-routed workers → CANDIDATE → real gates → conductor synthesis → acceptance packet**
  `m-d2f1bb8a0877f031` published and gated. Workers ran on the deterministic `LocalWorkerAdapter`,
  honestly recorded `"workers": "mock"` (§4 limit U58 — live workers are OWED, not faked).
- **Selection vs executing, both recorded, aligned:** `selection.model = fable-5`
  (`operator_selected`, invariant 3, preserved even if the executing checkpoint had differed);
  `executing.model = claude-fable-5`, `verified = true`, `is_fallback = false`, `leg_degraded: null`.
- **Verification, not assertion:** the requested `--model claude-fable-5` slug flows ONLY into
  `build_command` argv; it never reaches `extract_reported_model`, which read `claude-fable-5` back
  out of the CLI's own `modelUsage` reply independently and matched it — that is what makes the leg
  `verified`. Confirmed by the gate-validator's code trace (§7).

`claude-fable-5` is therefore a **confirmed-accepted `--model` slug on this host**, verified end to
end (advances U33 — see §4).

---

## 2. The real CLI shape and the extractor reconciliation (re-captured this iteration)

I re-captured the real CLI envelope myself this iteration
(`py -3.12 tools/live/capture_claude_json_shape.py` → `tools/live/claude_json_shape.captured.json`,
sanitized: `result`/`session_id`/`uuid` elided). Firsthand-observed ground truth:

- The real `claude -p --output-format json` response carries **no top-level `model` string**
  (`type_of_model_field: NoneType`).
- The executing checkpoint lives in `modelUsage`, a `model_id -> {…, costUSD, …}` map that on a real
  call holds **more than one key** — the primary conductor model **plus the CLI's own auxiliary
  fast-model helper**. My re-capture: `modelUsage = { "claude-haiku-4-5-20251001": {costUSD
  0.000589}, "claude-opus-4-8[1m]": {costUSD 0.0906895} }` (the CLI-default run resolves to
  `claude-opus-4-8[1m]` as the cost-dominant primary — this host's default checkpoint).

**Fix (reconciliation, fail-closed):** `extract_reported_model` resolves a multi-key `modelUsage` to
the **cost-dominant** model — the entry with the strictly-greatest numeric `costUSD` (money compared
as `Decimal(str(cost))`, never float — CLAUDE.md/Buildout §4), the CLI's own integrated measure of
which checkpoint did the work. A tie, a missing/non-numeric/non-finite `costUSD` on any entry, a
non-dict entry, or a non-string/blank key ⇒ `None` (ambiguous ⇒ unverified — never a coin-flip
between two real checkpoints). The top-level `model` and single-key `modelUsage` paths are unchanged.
New `reported_models(payload)` surfaces the FULL model-id set beside the single-checkpoint claim, so
the multi-model reality is auditable, never hidden.

The requested `--model` slug **never reaches the extractor** — a checkpoint is verified only because
the CLI itself reported running it. This is the property the honesty architecture protects.

---

## 3. Exit criteria (recorded CONSTRAINT for `phase-15d.flow`, live) and verdicts

| # | Criterion (directive §11 15D, §14 OP-9) | Verdict | Evidence |
|---|---|---|---|
| 1 | Conductor decomposes an objective → Scheduler assigns **by capability** → workers publish CANDIDATE over MCP → gates → conductor **synthesizes** the ACCEPTED set into an acceptance packet | **PASS (live)** | §1 run: live `claude-fable-5` conductor; real `MCPServer`/`Scheduler`/`GateEngine`; packet `m-d2f1bb8a0877f031`, 2 accepted. Governed path was refutation-hardened at the mock-first `.flow` (capability-not-name routing proven there). |
| 2 | Conductor runs on the **live Anthropic backend, `model_ref = fable-5`** (else recorded fallback); `current_conductor = {model: fable-5, reason: operator_selected}`; selection preserved even when the executing checkpoint differs | **PASS (live)** | §1: `selection.model = fable-5` preserved; `executing.model = claude-fable-5`, `verified = true`, `is_fallback = false`. The recorded-fallback branch (CLI default / unverifiable checkpoint ⇒ honest `attempted`) is proven **deterministically by the test suite** (§6), not re-exercised as a second live call this iteration. |
| 3 | Live legs only when a **real call is produced**; never present a mock/degraded leg as live (§6/§10.4) | **PASS** | `build_acceptance_packet` refuses a `live` leg without a VERIFIED checkpoint; `_synthesize` degrades `live`→`attempted` upstream when unverified. Proven by `test_a_mock_run_cannot_be_packaged_as_a_live_result` + 5 refutation probes (gate-validator §7, all refuted). |
| 4 | §2.2 — invoke the host CLI; never read/store/transmit the credential | **PASS** | `ClaudeCliBackend.build_env` scrubs every credential/endpoint-bearing var (fail-closed superset); no `--api-key`/bypass flag emitted (`_assert_no_forbidden`, which even rejects a `model="--api-key"` injection). OAuth stays in the CLI's host-native store; no repo/MCP credential write. Both live tools run down that same scrubbed-env path. |
| 5 | D-LOOP-1 — live processes torn down within the unit | **PASS** | `subprocess.run` is synchronous with a hard timeout; a synchronous run cannot return while its child lives; the driver printed and exited 0; no background live process spawned. Pre-existing `claude.exe` processes on the host are the operator's own sessions (incl. this loop) — not this smoke's child, which had already exited. |
| 6 | I-X3 governor caps at the authorized allowance (2) | **PASS** | `spawn_claude_code_conductor` registers `allowance = live_auth.terminals_per_subscription` (config scope `= 2`); the ConductorAdapter acquires/releases at start()/close(); the governor test proves `in_use == 0` after teardown. |

---

## 4. Limits, honestly (recorded, not glossed)

- **Workers are still the deterministic `LocalWorkerAdapter`** (`"workers": "mock"`) — **U58**. This
  unit proves the **live CONDUCTOR** driving the governed loop; **live worker legs**
  (Anthropic/Codex/Ollama publishing CANDIDATE) are a distinct 15D item and are OWED — the packet's
  `_assert_legs_honest` makes a `live` worker leg **unrepresentable** without its own evidence
  record, so nothing here can be mistaken for a live-worker result.
- **U57:** cost-dominance is a *reconciliation*, not a field the CLI labels "primary". It is correct
  for the observed shape (primary + cheaper helper) and fails closed when it cannot tell; a
  hypothetical future config in which a helper outspends the primary would be misattributed. The
  full `modelUsage` set is surfaced (`reported_models`) for auditability. Cost-dominance can NEVER
  convert a mock/degraded run to `live` — the live/attempted decision is upstream
  (`verify_reported_checkpoint` / `_assert_legs_honest`); cost-dominance only selects WHICH id
  string is recorded once a real spent call is already established (spec-auditor confirmed the
  separation, §7).
- **U33 (advanced):** the accepted `--model` slug for the Fable-5 selection is **confirmed on this
  host = `claude-fable-5`** (§1 verified it end to end this iteration). The remaining generality — a
  selection-label → checkpoint mapping across hosts/versions — stays open.
- **Operator-run-metric trust boundary (gate-validator R1):** the live conductor result of §1 is an
  operator-run metric (Phase-1-spike pattern). Its acceptance-packet id is per-run and NOT
  independently re-derivable from the repo. The committed, CI-runnable proof is the *mechanism* on
  the re-captured fixture (§2, cost-dominant = `claude-opus-4-8[1m]`); the fable-5 headline is the
  witnessed run. The high-stakes `.gate` validator must obtain its own fresh live evidence and must
  not treat this sub-step as independent confirmation of the live claim.
- **Cost:** two smoke-scale live calls total this iteration (1 shape re-capture + 1 flow smoke),
  minimal prompts.
- **Substantive 15D items still OWED to later live sub-steps / `.gate`:** one bounded LIVE debate
  (`.debate`), live conductor succession (`.succession`), the OP-8 interactive ConPTY conductor
  pane + voice-in (15E). This sub-step is the live conductor-driven governed loop only.

---

## 5. Reproduction & raw outcome

```
py -3.12 tools/live/run_15d_flow_live_smoke.py --model claude-fable-5 --timeout 150
```
Witnessed stdout (iteration 47): `ran=true published=true skipped_with_record=false`,
`legs={conductor: live, workers: mock}`, `executing={model: claude-fable-5, requested: claude-fable-5,
resolved_slug: claude-fable-5, verified: true, is_fallback: false,
verified_by: claude_code.verify_reported_checkpoint@1}`, `acceptance_packet=m-d2f1bb8a0877f031`,
`accepted_count=2`, `leg_degraded=null`.

Re-captured real CLI shape (this iteration): `tools/live/claude_json_shape.captured.json`
(`model` = null; `modelUsage` = `{claude-haiku-4-5-20251001 (costUSD 0.000589),
claude-opus-4-8[1m] (costUSD 0.0906895)}`, dominant = `claude-opus-4-8[1m]`).

---

## 6. Tests & suite

- Reconciled `extract_reported_model` + new `reported_models` in `adapters/frontier/claude_code.py`.
- New extractor cases in `tests/integration/test_claude_code_conductor.py`: the real multi-model
  cost-dominant shape, a cost tie (→ None), a missing cost (→ None), a bool cost (→ None), a
  non-string key (→ None), plus `test_extract_reported_model_matches_the_captured_real_cli_shape`
  against the re-captured envelope (passes on my fresh fixture: 14/14 in the focused `-k
  "captured_real_cli_shape or fail_closed"` run).
- Full suite: **908 passed** (`py -3.12 -m pytest tests/ -q`, 183.55s builder-run; gate-validator
  independently re-ran in isolation: **908 passed, exit 0, 188.40s**). JS product suite unaffected
  (Python-only change).

---

## 7. Independent review (fresh this iteration)

**gate-validator (sub-step, isolated) — PASS_WITH_RESERVATIONS.** Re-ran the full suite in its own
context: **908 passed, exit 0, 188.40s**. All six criteria PASS: extractor deterministic + fail-closed
on every ambiguous path (tie / missing / non-numeric / non-finite cost / non-string-blank key /
non-dict entry ⇒ `None`, money as `Decimal`); the requested `--model` slug provably never reaches the
extractor (traced — slug flows only into `build_command` argv; extractor reads only the parsed
payload); §2.2 scrub intact with no bypass flag (and a `model="--api-key"` injection raises); the
honesty guarantee holds against **5 refutation probes** (mock packaged as live, non-spawning subclass,
unverified-run degrade, truthy-not-`True` verified, worker `live` leg) — **all refuted**; live drivers
not collected by `pytest tests/` and no test under `tests/` spawns a real `claude`; the re-captured
fixture test is a meaningful ground-truth pin. Reservations, all inherent/disclosed, not defects:
**R1** — the live conductor result is an operator-run metric, not reproducible in-process; carry to
`.gate`. **R2** — U57 cost-dominance reconciliation limit. **R3** — U43: the `live` rule constrains
class, not behaviour (a determined in-process falsifier still passes; documented, not closable
in-process). **R4** — the untracked `apps/desktop/package-lock.json` must NOT be swept into this
Python-only unit's commit (honoured — see §8).

**spec-auditor — CLEAN (no MAJOR, no invariant violation, no prohibited drift).** Central adversarial
question — *can cost-dominance turn a mock/degraded run into `live` or fabricate a checkpoint?* —
answered **No** by trace: the live/attempted decision is gated by `_leg_for_backend` (exact type) +
`verify_reported_checkpoint` (four conditions incl. call-spent-since-snapshot + freshness) +
`_assert_legs_honest` (refuses a `live` conductor leg unless `executing.verified is True`);
cost-dominance only selects which id string is recorded once a real spent call is already established,
and cannot manufacture a checkpoint where the CLI reported none. Invariants 1 (no self-authorization —
`operator_terms_confirmed=True` is set only in the operator-run smoke on the recorded OP-9 basis, every
other gate still applies), 3, 4, 7 (nothing added to `mcp_server/`), 10 (CANDIDATE only), I-SC1, and
§2.2 all confirmed intact; no prohibited drift (`reported_models` adds transparency, not scope; D-LOOP-1
teardown preserved). The three MINOR items from an earlier pass are confirmed **fixed in-tree**
(capture-script env scrub; smoke uses detected `cli_present`; money as `Decimal`). Residual NITs, all
already recorded: NIT-1 a test oracle compares two well-separated float costs (test assertion, not
pricing logic — acceptable); NIT-2 the fable-5 headline is an operator-attested non-repo-reproducible
metric (= gate-validator R1, disclosed); NIT-3 a future top-level `model` echo (inert against the
observed shape; recorded in U57).

New/amended unresolved items: **U57** (cost-dominance reconciliation limit), **U58** (live workers
owed); amendments to **U54** (conductor leg asserted → observed live), **U56** (unblocked; 15D row-1
MET), **U33** (fable-5 accepted slug on this host = `claude-fable-5`).

---

## 8. Commit hygiene

Per gate-validator R4, the untracked `apps/desktop/package-lock.json` (unrelated to this Python-only
unit) is **excluded** from this unit's commits. Only the files of this work unit are staged:
`adapters/frontier/claude_code.py`, `tests/integration/test_claude_code_conductor.py`,
`tools/live/` (runner, capture tool, re-captured fixture), plus the register/evidence pair.
