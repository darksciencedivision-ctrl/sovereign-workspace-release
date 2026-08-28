# CP-02-CONFLICT-AUDIT — CP-02 against the in-flight CP-01

| Field | Value |
|---|---|
| Question | Does `OX-ALPHA-DIRECTIVE-CP-02` conflict with `OX-ALPHA-DIRECTIVE-CP-01`, which is running now? |
| Method | File-area by file-area comparison of the two mutation envelopes (`ADDENDUM-01 §3` vs `ADDENDUM-02 §3`), plus shared-artifact, port, and process-ownership checks. Not a comparison of band titles. |
| **Verdict** | **No true conflict.** Four overlapping file areas, every one resolved by strict sequencing — which CP-02's G0.0 already enforces as a hard STOP, not a wait loop. **Three corrections applied** (F-13, F-14, F-15). **Two pre-existing conditions** will block CP-02 on day one unless answered; neither is caused by CP-02. |
| CP-01 status at audit | G0.2 — capturing `before/` copies across its `modules/sow/apps/desktop/**` envelope. `goalcheck.py` written 06:54Z; two goalcheck runs. No `8*` ledger keys yet. |

---

## 1. Overlapping file areas — all four resolved by sequencing

| Area | CP-01 touches it for | CP-02 touches it for | Assessment |
|---|---|---|---|
| `modules/sow/adapters/**` | Gate 8f — OpenCode backend into the picker; roster wiring | Band C — widen the `Backend` Protocol, add `LlamaCppBackend`; Band E — roster consumers | **Overlap, safe sequentially.** CP-02 widens a Protocol CP-01 will have left conforming to the narrow shape. Concurrently, the two would be editing the same Protocol definition from opposite directions. |
| `modules/sow/control_plane/**` | Gate 8e conductor round-trip; Gate 8g the canonical model registry | Band E — model identity / artifact split in that same registry | **Highest-risk overlap, safe sequentially.** CP-02 Band E *extends what 8g creates*. This is a dependency, not a collision — and it is why ADD-02 §5 gates on 8g carrying a reviewer verdict rather than merely existing. |
| `shell/src/**`, `shell/static/**` | Gate 8b lifecycle and failure classes; Gate 8i Token Center panel and central layout | Band G — resource accounting surface, log field extension | **Overlap, safe sequentially.** Both add to `app.js` and the state surface. CP-02's 220-line cap is measured against whatever CP-01 leaves (F-13). |
| `evidence/GATE-LEDGER.json` | writes keys `8a`–`8j` | writes keys `9a`–`9j`, asserting `0`–`8j` byte-identical first | **Overlap by design, safe sequentially.** Two writers on one JSON file concurrently is silent corruption; sequentially it is the established pattern. |

**Why sequencing is sufficient and enforced.** CP-02 G0.0 requires, from disk: CP-01 has produced either `docs/CP-01-REPORT.md` with all ten `8*` keys, or `docs/STOP-REPORT-CP-01.md`; a reviewer verdict covers the `8*` band; and `evidence/cp01/` is unchanged across two reads ≥ 60 s apart. Failing any of those is `CP01_STILL_LIVE` — **a STOP, not a poll**. The launcher enforces the same condition before OpenCode even opens.

## 2. Non-overlapping — confirmed clean

| Area | Owner | Note |
|---|---|---|
| `evidence/cp01/**` vs `evidence/cp02/**` | separate | No shared path. |
| `docs/CP-MAP-01.md`, `CP-01-REPORT.md`, `STOP-REPORT-CP-01.md` | CP-01 | CP-02 writes `CP-02-REPORT.md`, `STOP-REPORT-CP-02.md`. Disjoint. |
| `modules/distillery/**` | CP-01 (Gate 8h creates it) | **Read-only to CP-02.** Band E defines the ingestion *contract* on the registry side only; it does not touch the Distillery. |
| `modules/tokencenter/**` | CP-01 (Gate 8i creates it) | Read-only to CP-02. |
| `modules/sovereign/**`, `modules/debate/**` | neither | Read-only to both. |
| `modules/sow/apps/desktop/**` | CP-01 only | CP-02 does not enter the Electron layer at all. |
| `modules/sow/node_runtime/**` | CP-01 only | CP-02 declines it — see C-2 below for why that needed a decision. |
| `modules/sow/scheduler/**` | CP-02 only | CP-01 never touches the residency planner. |
| `modules/sow/schemas/**` | CP-02 only | See B-2 — this exposes a gap in CP-01's own envelope. |
| `runtime/**` | CP-02 only | New tree. |
| `app.css` `:root`, `THEME-BASELINE-v3.md` | neither may change | Both packages treat drift as a STOP. Consistent. |

---

## 3. Corrections applied

### C-1 → **F-13** · Cap-compounding ambiguity

ADD-02 originally said that where the envelopes overlap on a file, "the stricter cap governs." That framing is wrong, and would have produced a spurious STOP.

The packages never run simultaneously, so the caps never apply simultaneously. CP-02's baseline is the workspace **as CP-01 left it**. Lines CP-01 changed are part of CP-02's *baseline*, not part of CP-02's *budget*. A builder measuring `difflib` against a pre-CP-01 state would attribute CP-01's ~1,850 lines to CP-02 and STOP `ENVELOPE_EXCEEDED` on its first mutation.

Fixed: ADD-02's precedence row and §3.2 now state that caps are measured against the G0.3 `before/` capture, and the work order's G0.3 requires that capture explicitly.

### C-2 → **F-14** · Nobody owned the llama.cpp server process

The supplied CP-02 never says which component starts and stops `llama-server`. Bands A and B imply an operator runs it by hand. Bands C and D need it running whenever the backend is exercised — and G20 explicitly forbids the planner from spawning or killing it.

Left unspecified, a worker resolves this one of two ways, both bad: it spawns the server from inside an adapter or the planner (violating G20 and the layering in the operator's §32), or it leaves an operator-run server that the closeout check cannot account for and that survives a deliberate STOP.

Fixed: **llama.cpp is a shell module.** `shell/modules/llamacpp.json` with a real `http` readiness probe against its own `GET /models`, `http_json` identity, `job_object` stop, `runtime_writes` scoped to its log directory. New goal G5.1 proves Start → `READY` on an observed health response and Stop → pid gone, port free, plus a `grep` proof that nothing else spawns it.

This is the third consumer of the same adapter pattern — Distillery and Token Center take it under CP-01. That is evidence the pattern is right, not a reason to invent a fourth mechanism. It also means llama.cpp inherits, for free, the job-object containment, the failure classes, and the runtime-truth guarantee that CP-01 Gate 8b is building right now.

### C-3 → **F-15** · Port unpinned

`llama-server` defaults to 8080. Nothing in the workspace referenced `8080` or `5183` (ABSENT: searched `shell/`, ADD-01, and the CP-01 work order). An unpinned port means the quiescence checks, the baseline capture, and the closeout verification all have a hole exactly the size of one orphaned inference server.

Fixed: **pinned to 5183**, adjacent to the shell's 5180. It joins 5175 / 8700 / 8765 / 5180 in G0.3's `ports.txt`, in G52's closeout, and in the launcher's blocking quiescence gate.

---

## 4. Pre-existing conditions that will block CP-02 — neither caused by it

### B-1 · The provider-spend contradiction will STOP CP-02 at G0.2

`modules/sow/config/live_operation.json` carries `"live_operation_authorized": true` with `providers: ["openai_codex_cli","claude_code","grok_build","google_antigravity"]`. Both CP-01's and CP-02's authorization sentences say **no provider spend authorized**.

CP-02's G0.2 makes that a hard STOP with no interpretation permitted — correctly, since your own PRE-02 demands it. **This is the single most likely thing to stop CP-02 in its first minute.** It is worth resolving before you launch rather than reading it in a stop report.

Two clean resolutions, operator's choice:

- **Narrow the configuration** — set `live_operation_authorized: false`, or reduce `providers` to an empty list, for the duration of CP-02. CP-02 exercises local runtimes only and needs nothing from those four.
- **Widen the authorization** — add a sentence naming the providers and a spend bound. Only worth it if you want a frontier leg exercised, which CP-02 does not require.

Note this also affects CP-01, which is running under the same contradiction right now. It has not stopped on it because CP-01's Gate 8e defaults to local models and never invokes the live path — but a worker spawn on the wrong branch could bill against a subscription while a directive says spend is unauthorized.

### B-2 · CP-01's own envelope may not cover `schemas/**`

ADD-01 §3.2 lists `modules/sow/control_plane/**`, `adapters/**`, and `node_runtime/**` — and **not** `modules/sow/schemas/**`. If Gate 8g's canonical model registry needs a schema change to carry the capability metadata G21 requires, CP-01 will hit `ENVELOPE_EXCEEDED` and STOP.

This is not a CP-02 conflict. It surfaced while auditing which package owns `schemas/**` (CP-02 does). It is a CP-01 exposure worth pre-empting: either accept the STOP and answer it when it arrives with 2–3 bounded options, or issue a one-line amendment now adding `modules/sow/schemas/**` to ADD-01's control-plane bucket. Doing nothing is also defensible — the STOP would be the system working correctly.

---

## 5. One observation on the running loop

CP-01 has produced `evidence/cp01/goalcheck-1.txt` and `goalcheck-2.txt` but `evidence/cp01/LOOP-LEDGER.jsonl` is still absent, where its §4 requires one appended JSON line per iteration. Not blocking, and its `before/` capture is proceeding normally. Worth raising at its next report so the ledger reflects the whole run rather than starting mid-way.

CP-02's work order tightens the same rule: the ledger line is written **before the next iteration begins**, not batched.

---

## 6. Bottom line

Run them back to back, never side by side. Every overlap is an ordering constraint, not a design collision, and the ordering is enforced three times over — by ADD-02 §5, by the work order's G0.0, and by the launcher's precondition check.

*Statements above are tagged against artifacts on disk or marked ABSENT where a search returned nothing. This audit authorizes nothing.*
