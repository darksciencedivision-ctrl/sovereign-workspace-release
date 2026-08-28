# Integration ship checklist

This checklist covers the RC3 integration candidate, not model promotion.

- [ ] Integration branch reviewed and approved by both treaty owners.
- [x] Canonical joint repository and clean baseline recorded.
- [x] RC3 source commit preserved in an exact Git bundle.
- [x] RC3-to-canonical mapping records every candidate module class.
- [x] Existing treaty documents preserved and amended surgically.
- [x] Shared infrastructure has one canonical implementation in this repository.
- [x] Source admission fails closed for `UNKNOWN`, `REJECTED`, and `REVOKED` sources.
- [x] D-9 is not a prerequisite for privacy-minimized telemetry collection.
- [x] Transitive exclusion and exact rebuild manifest covered by tests.
- [x] RC3-derived contract tests pass.
- [x] Canonical baseline contained no pre-existing automated Sovereign test suite.
- [x] Documentation links and JSON schemas validate.
- [x] Secret/private-data/weight staging scan passes.
- [x] G2/G3/G4 training not executed.
- [x] Live G0 has real success, failure, recovery, implicit-signal, dashboard, alert, and checksum-guard coverage; HG-0 evidence passes.
- [ ] Provider/model/revision classifications supported by primary evidence and operator decisions.
- [ ] Repository license explicitly resolved by owners.
- [ ] Human promotion decision and signed evidence bundle (future; not part of integration).
