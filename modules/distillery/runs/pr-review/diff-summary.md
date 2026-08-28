# Pre-PR diff summary

Reviewed range: `f1904399ffc8cc357b2d413127b406fedf44b903` → `c3594cfc6284b7b5008bb131434436d5a3a77c9a`.

The integration changes 49 files: 1,743 insertions and 23 deletions. The three canonical treaty documents are amended in place; no Sovereign research objective, authorship record, phase namespace, or project-policy boundary is replaced.

Shared treaty infrastructure appears once under `validators/`, `source_admission/`, `curation/shard.py`, `exclusion/`, `gate/`, `ops/`, and `train/card_lock.py`. Grounded-specific mining, telemetry, CLI, and harness normalization remain under `grounded/`.

The RC3 source is retained as a verified complete Git bundle at accepted commit `a332e68823ab426310c5d37f3c0bfed5c52cc1f0`. The original source remains clean and its 23 tests pass; the integrated suite has 25 passing tests.

No repository license was inferred. No prompt/output content, corpus data, weights, credentials, raw runtime records, workstation runtime paths, or reversible source-session identifiers are tracked.

`git diff --check` passes. The working tree was clean before these review-evidence files were created.
