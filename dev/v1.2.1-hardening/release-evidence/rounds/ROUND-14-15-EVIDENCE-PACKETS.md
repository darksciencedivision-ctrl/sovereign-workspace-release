# Rounds 14-15 Evidence Packets (Phases 9-10)

## Round 14 - PHASE 9 SYSTEM REGRESSION LOCK
Artifact: release-evidence/SYSTEM-VERIFICATION.json (11 checks, ALL PASS)
- git tree clean; python compileall OK; node JS syntax OK
- ORIGINAL SUITE EXACTLY 84 passed / 0 failed (AC-02)
- FULL SUITE 181 passed / 0 failed (+97 new); hostile e2e subset 9/9
- static security patterns: no innerHTML/document.write/eval; no CORS middleware anywhere
- purity scan: 250 files, no SOW refs outside sanctioned provenance record, no home paths, no secret patterns
- config validation loads (port 8700, 2 seats); lifecycle probe PASS

## Round 15 - PHASE 10 REAL OLLAMA QUALIFICATION
Artifact: release-evidence/real-ollama/real-ollama-qualification.json
VERDICT: REAL_OLLAMA_QUALIFIED (11/11)
- models present: phi4:14b, qwen2.5:14b-instruct
- live full-stack debate through REAL models: two completed public turns with terminal done observed
- measured latency (num_predict=96): turn1 TTFT 0.70s / 15.6s total / 6.14 tok-s; turn2 TTFT 12.5s / 30.4s / 3.16 tok-s (model load effect visible)
- live cancellation during generation: operator_interruption skip in 10.0s wall (bounded by local model stream cadence; unit SLA remains 0.3ms against stalled mock)
- topic change + thesis revision + position_revision broadcast verified live
- /ready == ready against real Ollama; shutdown clean, zero traceback
Harness note: first run flagged position_revision_broadcast=false due to single-frame read in the HARNESS (not product); fixed to scan-until-found and re-run produced the clean verdict above.

## Remaining
Phase 11 executed soak RUNNING in background (600s, real models, disturbances every ~75s; artifact will appear at release-evidence/lifecycle/executed-soak.json). Then Phases 12-14: allowlist staging -> manifest -> ZIP -> sha256 -> virgin cold extraction -> fresh review -> Director ACCEPT.