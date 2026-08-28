# ROUND-3-OBSERVATION

Round: 3
Current HEAD: 9a890e8
Working tree: clean
Selected defect cluster: P0-04 canonical configuration resolution + P0-05 strict loopback default / explicit remote opt-in
Open P0 before round: 14

## Effective-configuration derivations found (the "four implementations")

1. Runtime app.py:262: OLLAMA = os.environ.get("OLLAMA_URL", CONFIG["ollama_url"]).rstrip("/") - env override applied with NO endpoint policy check (P0-05 bypass vector).
2. app.py:260-264 module constants (port for uvicorn at 1568) - runtime truth.
3. scripts/bootstrap.ps1 inline _check_models.py: reads ollama_url via cfg.get("ollama_url", default) - its own resolution, no relation to env override.
4. scripts/bootstrap.sh line ~150 model check: same independent read; line ~207 port probe: strict parse previously, now utf-8-sig after R1, still silent "|| echo 8700" fallback.
No component validates the endpoint CLASS (loopback vs remote).

## Policy requirements extracted from contract S11.2-S11.3

- One code path decides effective config path / Ollama URL / remote opt-in / host / port; runtime, bootstrap verification, health endpoints, tests consume equivalent logic.
- Allowed default class: loopback only (127.0.0.1, localhost, ::1). Non-loopback rejected unless deliberate named setting allow_remote_ollama=true.
- Env overrides must not silently bypass policy.
- Remote enabled => log warning, expose in diagnostics, never claim local-only privacy.

## Design decisions for this round

- New module debate/config_policy.py (fits existing debate/ package; NOT new architecture): ConfigurationError, _read_config_text/_parse_config_document moved here from app.py; app.py imports and re-exports to preserve test-facing names.
- classify_ollama_endpoint(url) -> ("loopback"|"remote", host); enforce at the single choke point where OLLAMA is derived (app.py) AND inside the new scripts/effective_config.py CLI that bootstrap scripts call instead of their inline parsers.
- DEFAULTS gains allow_remote_ollama=False (bool coercion like insight_panel).
- sh silent port fallback removed: effective_config.py prints resolved port or exits nonzero with diagnostic.
- Diagnostics exposure this round: ws snapshot diagnostics gains ollama_endpoint_class (+ warning log when remote). Fuller /health,/ready surfaces arrive in Phase 6.

## Regression surfaces

Existing tests set OLLAMA_URL=http://127.0.0.1:9 etc. (loopback) -> unaffected. test_smoke spawns real subprocesses on loopback ports -> unaffected.

## Reason highest-priority

Closes Phase 1; every later security phase (origin/host/mutation) assumes a trustworthy single resolver and endpoint policy.
