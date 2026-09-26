# Sharded inference live record, 2026-09-26

True record for `feature/sharded-inference`. This replaces the stale progress note that still said isolation was awaiting a live re-run.

## Isolation

`3e0a2de` isolates map prompts and ledger updates. Maps do not share a ledger. Plan-step carry is unchanged.

## 65k MoE map/reduce

`qwen3:30b-a3b`, input `qualification-65536.txt` (262,146 bytes). Recorded in `65k.evidence.json` (local paths stripped to `<scratch>`; this copy had none).

- 2,779 s, 9 model calls, 1 split, 0 failures
- every completed map ledger empty
- answer 118, equal to the sum of the per-part counts (16+13+0+29+26+28+6)
- truth 124; the gap is the model's per-part counting, not cross-map leakage

## Prose map/reduce

145 KB Distillery design and validation docs. 863.6 s, no coverage gap. About half of that answer was the uncapped per-part appendix, which D1 caps.

`prose.job.json` is the scratch capture of `job_576754b5e5db44128d5c009afc481f00` (status `running` at capture). It does not itself contain the 863.6 s figure.

## Decisions now in the branch

- **D1** (`ed82343`): the appendix is one checkpoint-summary line per completed map (`- <task_id>: <summary>`, summary already at most 400 characters). It is omitted when the reduce answer already names every completed map. Replay is an identical answer with 0 model calls.
- **D2** (`ed82343`): `/v1/health` reports `long_active_job` (job id or null). The composer warns when a non-LONG, non-STATUS route is selected while a LONG job is active: QUICK/DEEP swap the model server (about 50 s) and pause the LONG run.
- **D3**: `qwen3.5:35b-a3b` stays out of LONG. No change.
