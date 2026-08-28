# RISKS — Debate Table v1.2.1-hardening

| ID | Risk | Evidence | Likelihood | Impact | Mitigation | Status |
|----|------|----------|------------|--------|------------|--------|
| R-01 | App exit code 1 on CTRL_BREAK/TerminateProcess shutdown path | v1.2 defect register "Open items carried forward"; reproduced in phase0 boot probe | certain | low | documented pre-existing behavior; not a Phase 0 blocker; revisit only if lifecycle AC requires zero nonzero exits | MONITORED |
| R-02 | Real-Ollama qualification depends on external model weights/latency | ollama 0.32.14 reachable; phi4:14b + qwen2.5:14b-instruct + dolphin-llama3:8b present | low | medium | gate currently UNBLOCKED; execute in Phase 10 | OPEN |
| R-03 | Hostile E2E may expose defects beyond enumerated register (e.g., stream parser edge cases) | not yet executed | medium | medium | add tests rather than substitute required set (AC-03); route new findings through OPEN-ITEMS | OPEN |
| R-04 | Dependency upgrades could destabilize WebSocket stack | current env matches lockfile exactly; no upgrade planned unless Phase 8 requires | low | high | default no-upgrade; any delta follows §18.4 qualification | CLOSED-BY-POLICY |
