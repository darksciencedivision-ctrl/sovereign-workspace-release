# CORRECTION — `phase18e_probe_document_shape_20260802T0219Z.json`

**Issued:** 2026-08-02, at the round-1 review of `phase-18e.live.shape`.
**Found by:** the gate-validator (MAJOR-1/MAJOR-2) and the spec-auditor (MAJOR-1), independently.
**The artifact is NOT edited.** Its content is preserved exactly as the tool emitted it — no field
was changed, added, or removed. (One mechanical caveat, stated rather than left for someone to
discover: `--emit` writes through Python's default newline translation on this host, so the file was
written with CRLF and git normalises it to LF on commit. That is a line-ending conversion applied by
the repository to every text file, not a correction to the record.) This file is the correction, in
the convention this repo already uses for
`phase18a_host_recon_CORRECTION.md` and `PHASE17E_DISPATCH_GATE_REFUSAL_….CORRECTION.md`.

---

## 1. The defect

The artifact's Grok entry contains, at `probes[0].document_shape.skeleton`:

```json
"text": "<str:0>"
```

That is the **pre-fix** rendering of an empty string. It should read `"text": ""`, as its sibling
artifact `phase18e_probe_grok_default_mode_20260802T0224Z.json` does.

Why it matters, in one sentence: `<str:0>` is a **non-empty string** under `text`, which is a
recognised response key, so **replaying this published skeleton through the strict reader reports
`strict_response_found: true` — i.e. that Grok's CLI DID answer.** That is the exact opposite of
what the artifact was produced to establish.

Measured:

```
skeleton as published : extract_provider_response_field(...) = '<str:0>'  -> found=True
the same run's record : strict_response_found=false, response_key_matched=null,
                        token_paths=["thought"]
```

## 2. How it happened

The describer's first implementation mapped every string leaf to `<str:LEN>`, including empty ones.
The unit caught that while building — blankness is load-bearing, because both readers test
`val.strip()` — and fixed it (mutation row **S1**, test
`test_the_skeleton_replays_the_strict_reader_faithfully`). The fix landed **between the two live
runs**: this artifact was written at 02:19:24Z, the fix followed, and the 02:24:47Z artifact carries
the corrected rendering.

The commit message and checkpoint described S1 as "a defect this unit caused and caught", which
reads as *caught before publication*. It was not. It was caught between two runs, and this artifact
was never regenerated.

**It was not regenerated for this correction either, and deliberately so:** regenerating it would
require a fresh live provider call, and the artifact's value is that it is the record of a run that
actually happened. A measurement record is corrected beside itself, never rewritten.

## 3. What in the artifact is UNAFFECTED

The load-bearing fields are computed from the real document, not from the skeleton, and every one
of them is correct:

| Field | Value | Correct? |
|---|---|---|
| `probes[0].accepted` | `false` | yes |
| `probes[0].reason` | "…carried no recognised response field…" | yes |
| `document_shape.response_key_matched` | `null` | yes |
| `document_shape.strict_response_found` | `false` | yes |
| `document_shape.token_paths` | `["thought"]` | yes |
| `document_shape.token_visible_to_strict_reader` | `false` | yes |
| `document_shape.key_types.text` | `"string"` | yes |
| `response_excerpt` / `outcome.detail` | show `"text": ""`, `"stopReason": "cancelled"` verbatim | yes |

**So U305's closure and U311's withdrawal do not rest on the defective field** — they rest on the
row above it, and on the raw excerpt, which shows the empty `text` directly. The Antigravity entry
in the same artifact is unaffected in every field: every string in that document is non-empty, so
the blank-string branch was never reached.

## 4. Corrections made elsewhere in the same pass

- `docs/evidence/PHASE18E_LIVE_SHAPE_CHECKPOINT.md` §3.2 printed `"text": ""` while citing this
  artifact. It now prints what the artifact contains and points here.
- `tests/unit/test_provider_document_shape.py` claimed its fixtures were this run's skeletons
  "verbatim". They are not; the provenance note there now states which artifact each fixture comes
  from and why they differ.
- Both artifacts were **renamed** to their real write times. They had been named `…0230Z` and
  `…0245Z` (the slots intended when the commands were issued) while the files were written at
  02:19:24Z and 02:24:47Z. A filename is a provenance claim (gate-validator MINOR-12).

## 5. The rule this leaves behind

An evidence artifact produced by code that changed mid-unit must be either regenerated or corrected
**before** any prose quotes it. Quoting the intended output rather than the emitted output is how a
report and its own evidence end up disagreeing — and here the disagreement pointed the wrong way,
which is the direction that matters.
