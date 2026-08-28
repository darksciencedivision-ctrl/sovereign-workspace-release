# RC3 surgical integration map

Canonical baseline: `f1904399ffc8cc357b2d413127b406fedf44b903`

Accepted implementation source: `a332e68823ab426310c5d37f3c0bfed5c52cc1f0`

Source tree: `162e8aa2f8fe842b599e4f9503fb01e63b278468`

This map was fixed after read-only inspection of the canonical remote, the exact downloaded archive, the separate Sovereign-only thesis repository, and the active Sovereign runtime. The canonical baseline contained only `README.md`, `docs/THESIS.md`, and `docs/SPEC-v1.1-draft.md`; therefore no canonical shared implementation existed to replace.

| RC3 file/module | Canonical destination | Action | Rationale |
|---|---|---|---|
| `grounded_common.py` | `distillery/common.py` | ADAPT | Treaty-neutral canonical helpers |
| `validators/` | `validators/` | ADOPT | One shared validator implementation |
| `source_admission/` | `source_admission/` | ADOPT | Shared schema/state machine; policies remain separate |
| `schema/*.json` | `schema/*.json` | ADOPT | Canonical treaty schemas |
| `curation/shard.py` | `curation/shard.py` | ADAPT | Shared immutable shard/provenance path |
| `curation/miner.py` | `grounded/curation.py` | KEEP_GROUNDED_ONLY | Usage/outcome curriculum policy |
| `exclusion/` | `exclusion/` | ADOPT | One shared transitive rebuild engine |
| `gate/paired.py` | `gate/paired.py` | ADOPT | Shared paired statistics; project policy remains outside primitive |
| `gate/historical.py` | `gate/historical.py` | ADOPT | Shared promotion-time aggregate store |
| `gate/controlled.py` | `gate/controlled.py` | ADOPT | Shared scientific model-effect evaluator |
| `gate/experiment_db.py` | `gate/experiment_db.py` | ADOPT | Shared experiment record |
| `ops/evidence.py` | `ops/evidence.py` | ADOPT | Shared attempt/evidence contract |
| `ops/bundle.py` | `ops/bundle.py` | ADOPT | Shared exact-bundle canonicalization |
| `ops/promotion.py` | `ops/promotion.py` | ADAPT | Shared atomic mechanism; human policy remains project-owned |
| `train/card_lock.py` | `train/card_lock.py` | ADOPT | Configurable shared exclusive-card mechanism |
| `telemetry/store.py` | `grounded/telemetry.py` | ADAPT | Durable Grounded G0 collection; telemetry does not imply admission |
| `harness_adapters/` | `grounded/harness_adapters/` | ADAPT | Grounded normalization, including Sovereign runtime evidence |
| `grounded_cli.py` | `grounded/cli.py` | ADAPT | Grounded-only operational entry point |
| RC3 abbreviated `README.md` | canonical `README.md` | MERGE | Preserve joint shell/authorship; amend stale RC semantics only |
| RC3 abbreviated thesis/spec | existing full canonical thesis/spec | MERGE | Full documents remain canonical and are patched in place |
| `docs/DECISIONS.md` | `docs/DECISIONS.md` | ADAPT | Preserve D-1…D-13 with RC3 semantics |
| RC3 ship checklist | `docs/SHIP_CHECKLIST.md` | ADOPT | No prior checklist existed |
| RC3 tests | `tests/` | ADAPT | Imports follow canonical package layout; coverage preserved |
| RC3 directive/manifest | `docs/integration/rc3/` plus source bundle | ADOPT | Execution authority and provenance retained |
| RC3 `runs/**` | exact Git bundle + integration evidence | ADOPT | Full source history/evidence retained without duplicating live run paths |
| RC3 `pyproject.toml` | root `pyproject.toml` | ADAPT | Joint identity; no unsupported license declaration |
| generated build/cache files | none | REJECT_DUPLICATE | Never canonical or tracked |

## Duplicate-infrastructure rule

`validators`, `source_admission`, `curation.shard`, `exclusion`, `gate`, `ops`, and `train.card_lock` are the sole canonical treaty implementations in this repository. `grounded` contains policy and adapters only. The dirty active Sovereign runtime was not copied or modified; its existing response evidence is consumed through an adapter.
