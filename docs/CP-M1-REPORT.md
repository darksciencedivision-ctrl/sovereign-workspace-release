# utc: 2026-08-27T00:54:53.602Z
# producer: ox-alpha CP-M1 ADD-08 wave

# CP-M1-REPORT.md — Part A

Requirement IDs covered: R-1 R-2 R-3 R-4 R-5 R-6 R-7 R-8 R-9 R-10 R-11 R-12 R-13 R-14 R-15 R-01 R-02 R-03 R-04 R-05 R-06 R-07 R-08 R-09 R-10 R-11 R-12 R-13 R-14 R-15

Part A of the merged control-plane report. Builder only. No PASS asserted.

## R-01 Debate Table does not autostart
Requirement ID: R-01
Implementation location: FACT[shell/src/server.py] FACT[shell/src/states.py]
Files changed: shell modules/tests under Band 2
Behavior before: cold start not proven
Behavior after: GET /api/state after serve_forever shows no module STARTING/READY by shell action
Validation performed: FACT[evidence/cpm1/8b/cold-start.txt]
Result: implemented-and-verified (G13)
Remaining limitations: none for R-01

## R-02 Runtime truth / EXTERNAL
Requirement ID: R-02
Implementation location: FACT[shell/static/app.js]
Files changed: shell static + tests
Behavior before: EXTERNAL not distinct
Behavior after: EXTERNAL legible; Stop does not kill external pid
Validation performed: FACT[evidence/cpm1/8b/external-dom.txt]
Result: implemented-and-verified (G14-G16)
Remaining limitations: none

## R-03 Session container
Requirement ID: R-03
Implementation location: FACT[modules/sow/apps/desktop/main.js]
Files changed: SOW desktop picker
Behavior before: implicit PowerShell default
Behavior after: EMPTY container, selection precedes init
Validation performed: FACT[evidence/cpm1/8c/empty-session.json]
Result: implemented-and-verified (G20-G23)
Remaining limitations: live Initialize/Use deferred in unattended runs

## R-04 Conductor operator channel
Requirement ID: R-04
Implementation location: FACT[modules/sow/apps/desktop/conductor/source.js]
Files changed: conductor surface
Behavior before: no enabled input
Behavior after: persistent typing surface; round-trip NOT_RUN
Validation performed: FACT[evidence/cpm1/8d/conductor-dom.txt] FACT[evidence/cpm1/8d/conductor-roundtrip.txt]
Result: partial — G25 TRUE; G26 NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH)
Remaining limitations: in-app supervised spawn process death

## R-05/R-06 Worker control plane
Requirement ID: R-05 R-06
Implementation location: FACT[modules/sow/apps/desktop/control/operational-state.js]
Files changed: operational-state.js projection created_utc/backend
Behavior before: created_utc gap
Behavior after: fields projected; live workers unavailable
Validation performed: FACT[evidence/cpm1/8e/worker-registry.json]
Result: partial — machinery TRUE; live dump NOT_RUN(LIVE_WORKERS_UNAVAILABLE)
Remaining limitations: needs Electron tree

## R-07/R-08 OpenCode backend
Requirement ID: R-07 R-08
Implementation location: FACT[evidence/cpm1/8f/opencode-detect.txt]
Files changed: none this wave except detection artifacts
Behavior before: Bun 1.3.14 misread as OpenCode
Behavior after: OpenCode 1.18.23 detected; live session NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Validation performed: FACT[evidence/cpm1/8f/opencode-detect.txt]
Result: presence TRUE; direct/delegation NOT_RUN
Remaining limitations: no long-lived spawn this session

## R-09/R-10 Canonical registry
Requirement ID: R-09 R-10
Implementation location: FACT[modules/sow/control_plane/canonical_registry.py]
Files changed: canonical_registry.py
Behavior before: multiple lists
Behavior after: one dump, 18 fields, incompatible selection refused
Validation performed: FACT[evidence/cpm1/8g/registry-dump.json]
Result: implemented-and-verified (G38-G42)
Remaining limitations: artifacts sha256 unknown (not guessed)

## R-11/R-12 Distillery
Requirement ID: R-11 R-12
Implementation location: FACT[modules/distillery/serve.py] FACT[shell/modules/distillery.json]
Files changed: modules/distillery, shell module json, app.js
Behavior before: not_started
Behavior after: health console 5184, no compute on open
Validation performed: FACT[evidence/cpm1/8h/distillery-start.txt]
Result: implemented-and-verified (G44-G47)
Remaining limitations: operator owns process this session

## R-13/R-14 Token Center
Requirement ID: R-13 R-14
Implementation location: FACT[modules/tokencenter] FACT[shell/modules/tokencenter.json]
Files changed: tokencenter copy, app.js/app.css
Behavior before: external piggy bank
Behavior after: loopback+CSRF copy; central UI; G53 PNG capture NOT_RUN
Validation performed: FACT[evidence/cpm1/8i/no-credentials.txt]
Result: partial — G50-G52 G54-G55 TRUE; G53 NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Remaining limitations: no credential surface (S-2)

## R-15 (remainder / local inference)
Requirement ID: R-15
Implementation location: FACT[shell/modules/llamacpp.json] FACT[runtime/llama.cpp]
Files changed: pin, adapter, planner notes
Behavior before: no llama.cpp candidate
Behavior after: pinned; live A1-A8/router NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Validation performed: FACT[evidence/cpm1/9a/pin.txt]
Result: partial
Remaining limitations: llama.cpp not production default (S / D5-3)

INTERPRETATION: Part A records Package A plus honest NOT_RUN for launch-gated legs.
ASSUMPTION: operator-owned 5184/8765 remain the Distillery/Token Center processes.
RECOMMENDATION: reviewer reads ⚑ artifacts; no gate is PASS.

# Part B

Per-band closeout. llama.cpp is not promoted to production default.

## Band 12–13 llama.cpp
Implementation location: FACT[runtime/llama.cpp] FACT[shell/modules/llamacpp.json]
Files changed: pin, llamacpp.json
Behaviour before: absent
Behaviour after: pinned candidate; live A2–A8/router NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED)
Validation performed: FACT[evidence/cpm1/9a/pin.txt]
Result: partial
Remaining limitations: no live router this session

## Band 14–15 protocol + planner
Implementation location: FACT[modules/sow/adapters/base/backend.py] FACT[modules/sow/adapters/local/llamacpp.py]
Files changed: backend protocol, LlamaCppBackend, resolver production_context, planner evidence
Behaviour before: Ollama-only protocol
Behaviour after: seven methods; metrics() on LlamaCppBackend; Ollama default
Validation performed: FACT[evidence/cpm1/9c/parity-matrix.txt]
Result: G81–G90 G92–G93 TRUE; G91 NOT_RUN
Remaining limitations: live VRAM round-trip not run

## Band 16–19 registry populate / context / fallback / metadata
Implementation location: FACT[modules/sow/control_plane/canonical_registry.py]
Files changed: artifacts[], deployment-manifest schema, logring fields
Behaviour before: empty artifacts[], null context
Behaviour after: tags populated; NOT_MEASURED recorded; fallback visible
Validation performed: FACT[evidence/cpm1/8g/registry-dump.json]
Result: G94–G115 mostly TRUE; G114 NOT_RUN(DEFERRED_HARDWARE)
Remaining limitations: no NVFP4

## parity matrix
FACT[evidence/cpm1/9c/parity-matrix.txt] — both backends, UNSUPPORTED where honest.

## measured vs not
Measured: registry shape, discovery, Distillery/Token Center install, protocol, planner grep-proofs.
NOT_MEASURED / NOT_RUN: llama.cpp generate/CUDA/offload/server, router LRU, planner VRAM round-trip, OpenCode live session, Conductor round-trip, G53 PNGs, NVFP4 research.

## deferred (verbatim)
DEFERRED_HARDWARE: ExLlamaV3 · EXL3 · Unsloth training · GRPO · speculative execution · broad quantization generation · large-student Distillery training
DEFERRED_OPERATOR_DECISION: remote-machine routing · loopback sovereignty invariant repeal · >=24 GiB trainer designation · named-role display aliases · Token Center ownership after Band 9
RESEARCH_ONLY: NVFP4

## carried defects C-1…C-7
C-1 quoting/T-rules: standing. C-2 inventory git field: G3. C-3..C-7: see 8d findings; G26 process death owed.

BUILDER CLAIM: Gates 8a through 8j and 9a through 9j are CANDIDATEs for reviewer evaluation. No PASS status is asserted by the builder, and llama.cpp is not promoted to production default by this package.

