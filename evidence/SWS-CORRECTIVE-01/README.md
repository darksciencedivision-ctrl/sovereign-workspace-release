# SWS-CORRECTIVE-01 — evidence index

**Run ID:** `SWS-CORRECTIVE-01-20260908T151625Z`
**Reviewed baseline:** `52bcc931e6ebb0db24155758cf19d1cf592731fa`
**Candidate:** `45751ac54363cf77ff8bc672eca7f375d42de9cb`
**Executor model:** Opus 5 (`claude-opus-5`)

This directory is `export-ignore`d, so nothing here ships. It is the record of one execution, kept
separate from the historical records already in `evidence/`.

| Document | What it holds |
|---|---|
| `IMPLEMENTATION-REPORT.md` | **Start here.** What changed, why, how it was validated, what is blocked and by exactly what, and the A–E outcome. |
| `01-baseline/REPRODUCTIONS.md` | Every documented defect reproduced on this host at the baseline, **before** any correction, with transcripts. Includes the R2 root-cause trace and one defect the review had not recorded. |
| `02-release/CANDIDATE.md` | Candidate identity, all eight artifact hashes, the twelve gate results, the reproducible-build evidence, and ten executed negative controls. |
| `03-contract/LAUNCH-PROOF.md` | The launcher executed: readiness by service identity, `-CheckOnly` through all three entry points, and an honest note about forced-kill shutdown. |
| `04-acceptance/ACCEPTANCE-RECORD.md` | The acceptance sequence run against a real installation, labelled FIXTURE throughout, with the gate D blocker stated. |
| `05-benchmark/RESULTS.md` | SWS-BENCH-01 coverage, results, what they support and what they do not. |

## The frozen documents these refer to

Written and committed **before** the thing they govern was run:

- `tools/benchmark/PROTOCOL.md` — conditions, primary outcome, thresholds, and what the
  comparison cannot establish.
- `tools/benchmark/dataset.json` — 30 held-out tasks, `dataset_sha256` `f844c7dc…`.
- `docs/ACCEPTANCE-WORKFLOW.md` — the operator task, its independently checkable artifacts, and
  the recovery contract.

## Reading rule

Every result in here carries its environment label. `FIXTURE` means the development host and
proves a mechanism. `CLEAN` means a fresh machine and is the only thing that satisfies gate D.
No `FIXTURE` result is offered as a `CLEAN` one anywhere in this record.
