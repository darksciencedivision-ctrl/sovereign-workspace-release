# tests/
- `unit/` — schema validation scaffolding (Phase 0). Grows with each phase.
- `integration/`, `security/`, `recovery/`, `evaluation/` — reserved for their owning
  phases (Plan §12.1); populated starting Phase 2. `security/` receives the adversarial
  matrix (T1–T16), `recovery/` the kill-matrix, `evaluation/` the Phase 13 comparative harness.
Run: `python -m pytest tests/ -q`
