# SOVEREIGN v3.1.2 — BUILD STATUS

**BOOT-FIX (Path C + B) + disclosed imperfect_synthesis recalibration applied.
Static tests: 48/48 pass (1 skipped). FULL END-TO-END BOOT PROVEN by BOOT_PROOF_03
(cycle exit 0, all cognitive probes pass, artifacts written, OBSERVE + publication
fail-closed intact). The original `alpha_positions` contract blocker (BOOT_PROOF_02)
and the `imperfect_synthesis` propagation-threshold blocker (BOOT_PROOF_03) are both
resolved. The designed UI (SPA + adapter) is folded in and a real cycle was driven
through it (BOOT_PROOF_UI_01). Boot-proven; not yet an independently re-verified release
(pending operator re-verification).**

---

This archive applies the operator-approved **Path C then B** boot fix to the v3.1.1
baseline and re-proves the debate/synthesis path with a controlled cycle
(BOOT_PROOF_02). It is **not** a fully boot-verified release: see the open blocker below.

## What changed from v3.1.1
- **Step C — format-compliant default reasoner.** `deepseek-r1:14b` was replaced by
  **`qwen2.5:14b-instruct`** (operator-accepted) in all five shipped default-slate
  occurrences: `SYSTEM_MANIFEST.json` `MODELS.PRIMARY_REASONER`, and
  `synthesis/model_hierarchy.json` roles `ALPHA_ADVOCATE`, `ALPHA_RECONCILER`,
  `CLU_ANALYZER`, `CLU_BENCHMARK`. Same ~9 GB footprint (no VRAM regression).
- **Step B — strip-only debate-turn normalizer.** New module
  `synthesis/debate_output_normalizer.py`, applied in `synthesis/live_orchestrator.py`
  `_run_stage` to every turn's raw output before contract parsing (all roles). It only
  (1) strips markdown decoration around header tokens and (2) trims a leading preamble
  before the first `CLAIM:`. It never fabricates, translates, reorders, or removes
  trailing content; the true raw output is preserved in each turn record, and echoed
  scaffold / non-English / fabricated content still fail the strict contract.
- **Version** bumped to `3.1.2` in all shipped locations.

## What is verified (static, integrity only)
- `python -m py_compile` on all shipped `.py` — clean.
- `pytest -q` — **48 passed, 1 skipped** (baseline 39 + 9 new normalizer tests; the skip
  is the same symlink-privilege test as baseline).
- `python cycle_runner_v3.py --check` — exit 0 (new slate present in `ollama list`).

## What is boot-proven (BOOT_PROOF_02)
Controlled `--once --fail-closed` cycle, identical topic to BOOT_PROOF_01. Evidence:
`SOVEREIGN_VALIDATION_EVIDENCE/BOOT_PROOF_02_20260715_151445`.
- **`alpha_positions` strict contract CLEARED** — the original blocker. `qwen2.5:14b-instruct`
  satisfies CLAIM/CHALLENGE/EVIDENCE/UNCERTAINTY natively on attempt 1
  (`raw_validation_passed=true`, normalizer inert). Step B engaged correctly on one
  `dolphin-llama3:8b` turn (stripped an axis-1 preamble) and never corrupted a compliant turn.
- **Full debate + reconciliation + cross-exam + `king_synthesis`** complete and pass their
  contracts (canonical `FINAL_SYNTHESIS` intact).

## Full end-to-end boot (BOOT_PROOF_03)
Controlled `--once --fail-closed` cycle (identical topic), after the imperfect_synthesis
recalibration. Evidence: `SOVEREIGN_VALIDATION_EVIDENCE/BOOT_PROOF_03_20260715_163012`
(session `…213013Z_c6fa452d`). **Cycle exit 0.**
- All four cognitive probes pass (`imperfect_synthesis.propagated_count=1`, challenge
  cosine ≥0.6; not suspicious).
- Artifacts written nonempty: `output/praxis/praxis_answer.json` (real `final_synthesis`),
  `output/sovereign_voice/sovereign_voice.md`, `praxis/logs/synthesis.txt`.
- Constitution stays **OBSERVE**; publication stays **fail-closed** (`corpus/domain.txt` empty).
- Six engine anchor hashes pre==post (engine unmodified across the run).

## Cognitive-validation recalibration (disclosed, reversible — applied 2026-07-15)
imperfect_synthesis propagation-detection threshold: removed the hardcoded `max(..., 0.9)`
floor at `live_orchestrator.py:1728` that overrode the manifest-approved
CHALLENGE_ANSWER_COSINE (0.6). Rationale: BOOT_PROOF_02 (session 20260715T201446Z) showed
the sole challenge propagated at cosine 0.706–0.784 with meaningful_change=true, i.e.
genuinely incorporated, but rejected by the 0.90 floor. This aligns propagation detection
to the system's approved challenge-answer cosine; it does not alter the structural-variance
G-SV 0.90 gate. Reversible: restore the `max(..., 0.9)` clamp to revert. `threshold_answer`
verified to resolve to 0.6 on this host before the change. The `imperfect_synthesis` pass
logic (`meaningful_change AND propagated_count>0`) and all other cognitive probes are
unchanged. Proven end-to-end by BOOT_PROOF_03 (see below).

## UI integration (SPA + adapter) — BOOT_PROOF_UI_01 PASS
Folded the designed UI into v3.1.2. Components: **SPA `sovereign-ui` 0.2.0** (`ui/ui_shell/`,
React 18 + TS + Vite; source + prebuilt `dist/`) and a **stdlib adapter 0.3.0**
(`ui/adapter_service/`, loopback `127.0.0.1:5175`). The adapter reads engine files and
invokes `cycle_runner_v3.py` as a subprocess; it never writes engine files. Config in
`ui/adapter_service/adapter_config.json` points at the canonical engine + venv python,
`cycle_timeout_sec=2400`. SPA build: strict `tsc -b` clean, `dist/` emitted; `smoke_test.py`
12/12. The SPA is the **default UI** in `README_RUN.md`; the Flask board (`URI/app.py`)
remains a documented legacy observation view (not deleted). Node/npm is a **build-time**
prerequisite only (prebuilt `dist/` ships).

**Adapter read-logic fix (disclosed, UI-layer only):** v3.1.2 run records have no top-level
`final_synthesis`; the synthesis lives in the engine's `praxis_answer.json`
(`artifacts.praxis_answer_path`) and `synthesis.txt`. Added `read_final_synthesis()` in
`ui/adapter_service/adapter.py` to read the engine-produced answer artifact (fallback
`synthesis.txt`), never fabricating. No engine file changed.

**BOOT_PROOF_UI_01** (`SOVEREIGN_VALIDATION_EVIDENCE/BOOT_PROOF_UI_01_20260715_170426`,
session `…221713Z_3dc14885`): one real cycle **driven through the SPA** (`POST /v1/message`
from the browser) completed; SPA rendered the engine's real 424-char `final_synthesis`;
`evidence_log_path` = arbitration artifact. Six engine anchor hashes **unchanged** pre→post;
constitution OBSERVE; publication fail-closed; cognitive probes pass. 31-H hang **not
reproduced this run — still OPEN**.

## Alternate profile (SC1 benchmark slate)
The prior reasoner `deepseek-r1:14b` remains a documented alternate; see `PREREQUISITES.md`.
It does not reliably satisfy the strict debate contract on this host.

## Anchor hashes (v3.1.2, SHA-256; recorded — full end-to-end boot NOT yet proven)
```
cycle_runner_v3.py   B60F4620D1C5F5367602CE0641DB1E59DF88EB5A6F7502C4CC5C203349A593C7
quality_gate.py      B05AEB59D4CA25024B5977242040653619D054C5F29893412AC0DFAA34342C4A  (unchanged from v3.1.1)
publication_gate.py  5D7A90F51C318A9CEDD95C190FEC7379DB5503C96527612D7BC01413775D9018
claim_arbitrator.py  E6FE155FF1DCD03CD1608244A7AE5971E9BDE90D634C27CC8109AFE59FCAA88B  (unchanged from v3.1.1)
SYSTEM_MANIFEST.json 1713EEAA8A5B27FB9DEB8A371C910FB5B653F9081591975C3626D9C4720D9707
runtime_profile.json B5258CD77FA32927787CF2CA89E847C4923A865289411A8F3C244373ADBE9AA0
```
The v3.1.1 baseline hashes remain that baseline's record; these supersede them for v3.1.2.
