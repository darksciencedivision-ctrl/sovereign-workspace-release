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

145 KB Distillery design and validation docs, re-run on the final code (HEAD `c1a469e`, which includes D1).

- status: completed
- elapsed: 798.651189 s
- answer length: 505 characters
- appendix: capped
- coverage gap: none

`prose.job.json` is that completed job, `job_dbbacf9876144a58b9f8a119e2736283` (local paths stripped; this copy had none). The earlier audited run, before the cap, was 863.6 s with no coverage gap; about half of that answer was the uncapped appendix.

## 65k MoE map/reduce, qualification r2

Same input, after D1, on the r2 stack (`docs/performance/qualification-20260926-long-r2/`). Job `job_8cbed56a19214a3aad6272c9a401cef4`.

- 2,613.8 s end-to-end, 9 model calls, 1 split, 0 failures, every map ledger empty
- answer 115, equal to the sum of the per-part counts (31+25+27+12+13+1+6)
- truth 124; the gap is the model's per-part counting
- the product answer carries the capped appendix

## Decisions now in the branch

- **D1** (`ed82343`): the appendix is one checkpoint-summary line per completed map (`- <task_id>: <summary>`, summary already at most 400 characters). It is omitted when the reduce answer already names every completed map. Replay is an identical answer with 0 model calls.
- **D2** (`ed82343`): `/v1/health` reports `long_active_job` (job id or null). The composer warns when a non-LONG, non-STATUS route is selected while a LONG job is active: QUICK/DEEP swap the model server (about 50 s) and pause the LONG run.
- **D3**: `qwen3.5:35b-a3b` stays out of LONG. No change.
