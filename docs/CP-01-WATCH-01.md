# CP-01-WATCH-01 — Reviewer Watch Note on the Running Loop

| Field | Value |
|---|---|
| Subject | OX Alpha executing `docs/OX-ALPHA-DIRECTIVE-CP-01.md`, session opened 2026-08-25T06:26Z. |
| Status at review | Band 0 complete. Oracle reports **3/53 TRUE** (G0, G0.1, G0.2). Loop is in Band A read-only reconnaissance for `docs/CP-MAP-01.md`. No `8*` ledger keys. No product mutation yet. |
| Verdict | **The builder is executing correctly and its self-correction discipline is better than the directive requires.** Three conditions outside its control will stop it later. Two are fixable now with one operator sentence each. |
| Standing | Reviewer note. Authorizes nothing. |

---

## 1. W-1 — The Token Piggy Bank baseline is already invalid. **Confirmed, not predicted.**

The G0.1 protected-root baseline captured `data/piggybank.sqlite` at ~07:08Z:

```
391b8836c5d976da4e6569efc2ea9f5d15e5e826b18ece0c5c58892190eed33c  5259264  data/piggybank.sqlite
```
FACT[`evidence/cp01/manifests/manifest-cp01-before-token-piggy-bank.txt`]

The same file read at 07:44:06Z:

```
a7a283858781e2d205dd3050ee0c25cce61e28c6bad0df3f5cd9741d61260e72  5259264
```

**Same size, different hash — 36 minutes after capture.** The operator's live Token Center on :8765 refreshes on a 300-second loop and writes a snapshot row into its 288-row ring each time. The size is constant because the ring is fixed; the content changes on every refresh.

Consequences, both mandatory STOPs:

- **G26** requires `D:\Token Piggy Bank\` byte-identical to its G0.1 baseline. Impossible while the app runs.
- **G32** requires all five protected manifests `fc /b` clean. Same.

This is not builder interference. It is an operator-owned application doing its normal job inside a tree the envelope declared frozen. The builder will hit it in Band I or Band J — hours from now — and stop correctly, having done everything right.

**Fix — one operator sentence, issued in session:**

```
OPERATOR AMENDMENT (ADD-01): the D:\Token Piggy Bank\ protected baseline excludes data/** — runtime state, not source, and already excluded from the §3.3 copy. Re-capture manifest-cp01-before-token-piggy-bank.txt with that exclusion and record the superseded artifact.
```

This is principled rather than expedient: ADD-01 §3.3 *already* excludes `data/` and `.git/` from the module copy. The baseline should have matched. Excluding it costs nothing — no source file lives there.

**Alternative:** stop the operator's Token Center now and re-capture. That also resolves W-2, at the cost of the running instance.

## 2. W-2 — Gate 8i cannot reach `READY` while the original holds :8765

G27 requires `modules/tokencenter` to start through the shell and reach `READY` on `http://127.0.0.1:8765/healthz`. The operator's own instance holds that port — recorded by the builder at G0 (`piggybank.py`, started outside the workspace). The builder spotted this itself and has already encoded a G34 closeout allowance for a pre-existing external owner, mirroring how :8700 was handled at Gate 7b.

But G34 is closeout. **G27 is a start-to-READY requirement, and it has no such allowance.** Band I will stall there.

Three resolutions, operator's choice:

| Option | Effect |
|---|---|
| **Stop the original before Band I** | Cleanest. Frees :8765, and also stops the W-1 drift. The module copy then owns the port, which is the intended end state anyway. |
| **Re-pin the copy to :8766** | Both can run. Adds a port to every quiescence and closeout check, and leaves two Token Centers live — the "stale second copy" failure I flagged as an open decision. |
| **Record `NOT_RUN(PORT_HELD_BY_EXTERNAL_OWNER)`** | Truthful, costs nothing now, leaves R-13 partially unproven. |

Recommend the first. It is the only one that ends with a single Token Center.

## 3. W-3 — `D:\Sov 1\` carries the same exposure, at 40× the cost

The sov-1 baseline is **134,462 files / 7.4 GB**, and took roughly 30 minutes to hash. `AGENTS.md` §6 describes it as the operator's production SOVEREIGN. If anything runs there during CP-01 — the app, a cache write, a log — `PROTECTED_SOURCE_CHANGED` trips the same way, and G32's re-verification costs another 30 minutes regardless.

No amendment needed if the tree is quiescent. Worth confirming it will stay that way for the duration, because the failure mode is a multi-hour run ending in a stop report about a log file.

## 4. W-4 — Two envelope gaps, one already papered over by interpretation

ADD-01 §3.2 names `modules/sow/control_plane/**`, `adapters/**`, and `node_runtime/**`. It does **not** name:

- **`modules/sow/mcp_server/**`** — which CP-01 §5's Band D/E envelope explicitly permits touching ("plus `control_plane/**` and `mcp_server/**` where the round-trip requires it").
- **`modules/sow/schemas/**`** — which Gate 8g's canonical registry may need for capability metadata.

The builder noticed the first and resolved it by self-assignment: it captured `mcp_server/` into `before/` and decided to "treat cap as covered by sow-python 400, conservative." That instinct is right and the outcome is safe — but it is a builder widening its own envelope by interpretation, where `AGENTS.md` §13 says material ambiguity on permitted mutation is a STOP.

I flagged the `schemas/**` half of this in `CP-02-CONFLICT-AUDIT.md` §4 (B-2) before the run started. It is now confirmed live.

**Fix — one operator sentence:**

```
OPERATOR AMENDMENT (ADD-01): the modules/sow control-plane cap area of §3.2 reads modules/sow/{control_plane,adapters,node_runtime,mcp_server,schemas}/** at the same 400-line cap. No other cap changes.
```

## 5. W-5 — The oracle is builder-authored. `TRUE` means "the artifact I chose exists."

This is not a defect; the directive instructed the builder to write `goalcheck.py`. But the reviewer should hold it clearly.

The builder defined, on its own authority: every evidence filename the oracle looks for, the `-fails-before.txt` / `-passes-after.txt` naming convention, and the ten failure-class stems that G7 checks (`PROCESS_START`, `PORT_UNAVAILABLE`, `HEALTH_CHECK`, `IDENTITY_MISMATCH`, `MODEL_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`, `OPENCODE_UNAVAILABLE`, `CONFIGURATION`, `WORKER`, `CONDUCTOR`). Its own reasoning is candid about it: *"Requiring exact strings would force my own naming — acceptable since I define them now as the class vocabulary."*

Most predicates are also **structural rather than semantic**. G12 — the Conductor typing surface, R-04, the most operator-visible requirement in the package — turns TRUE when `8d/conductor-dom.txt` contains `<input`, `submit`, and `turn`. A DOM dump with a disabled input and two stale lines satisfies that.

The practical rule for the reviewer: **read the artifacts, not the oracle summary.** `53/53 TRUE` means every artifact the builder decided would prove a goal exists and parses. It does not mean the Conductor answers, or that a worker round-trip happened. Those live in the artifacts and in the acceptance run.

## 6. What the builder is doing well — worth recording

Five self-caught defects in Band 0 alone, each handled by preserve-and-supersede rather than overwrite:

1. A capture helper named `H` silently resolved to PowerShell's `Get-History` alias, producing empty hash fields. Caught, faulty artifact preserved as `session-start.faulty-1.txt`, superseded by name and hash.
2. `OPERATOR-INSTRUCTIONS.log` lacked a trailing newline, fusing the new `# utc:` line onto the prior entry. Annotated rather than rewritten — correct under append-only.
3. Goal IDs rendered as `GG0` from a format-string doubling. Fixed and logged as `G-oracle`.
4. **UTF-8 BOM defeated `startswith('#')`**, leaking header lines into the compared bodies and producing a false "SOW git bodies differ". Subtle, and it would have manufactured a fake quiescence failure.
5. A `-First 8` pipe truncating the oracle's exit code, misread as a crash. Diagnosed correctly.

It also refused to `json.load`/`json.dump` the gate ledger, recognising unprompted that a round-trip would reformat gates 0–7b and break the byte-identity assertion — and it read the nested `modules/sow/AGENTS.md` when it surfaced and folded its MCP-spawn policy into its constraints.

Suite at entry: `Ran 122 tests … OK` — exactly the Gate 7a baseline.

One trivial code smell, non-blocking: chunk 3 of the oracle write contains `Add-Content -Value $c2b -ErrorAction SilentlyContinue` where `$c2b` is undefined — a silenced no-op.

## 7. Scale

Band 0 took roughly 65 minutes and produced no product change. Nine bands remain, including a Distillery runtime built from a snapshot, a Conductor conversation surface in the Electron renderer, OpenCode integration, a Token Center install, and up to 1,850 changed product lines — plus a live acceptance run. Iteration cap is 120.

This is a multi-session run. The loop is designed to resume from disk, and `continue` is the correct response to a harness-ended turn.

---

## 8. Recommended action, in order

1. **Now** — issue the W-1 amendment. It is already failing; every minute adds drift.
2. **Now** — issue the W-4 amendment. Cheap, and it removes an interpretation the builder has already had to make.
3. **Before Band I** — decide W-2. Stopping the original Token Center is the recommendation.
4. **Confirm** — W-3: `D:\Sov 1\` stays quiescent for the duration.
5. **At review time** — read the Band D/E/F artifacts directly. The oracle cannot tell you whether the Conductor answered.

*Every claim above is tagged `FACT[path]` or shown with the command output that produced it. Hashes are live reads taken 2026-08-25T07:44Z. This note authorizes nothing.*
