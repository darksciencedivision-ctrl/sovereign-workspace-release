# Audit D — the 17 oracle FALSE / claimed NOT_RUN goals

The exact FALSE set in `evidence/cpm1/goalcheck-66.txt` is `G3,G28,G53,G64,G70,G71,G72,G74,G75,G76,G77,G78,G79,G80,G91,G117,G118`. This is not the same set as RUN-LOG NOT_RUN entries: the log calls G3 and G64 TRUE (`evidence/cpm1/RUN-LOG.md:107,110`) and calls G34/G35 NOT_RUN (`:120-121`) even though the oracle counts them TRUE. Therefore “107 TRUE + 17 NOT_RUN” combines incompatible sources.

| Goal | Verdict | Independent cause finding |
|---|---|---|
| G3 | RECONCILIATION DEFECT, not a present NOT_RUN | T-4 genuinely exists: `docs/SWS-UI-001-v1.2-ADDENDUM-04.md:78-80` says freshness is per session. RUN-LOG adopts it at `:107`; Audit C's current checks do not establish a present red goal. |
| G28 | GENUINE | Live-worker registry was empty/unavailable; `RUN-LOG.md:33`. No evidence of a worker was found. |
| G53 | GENUINE AUTHORITY SKIP | Browser/PNG live capture was not run; `RUN-LOG.md:52`. The later no-launch instruction supports the boundary. |
| G64 | RECONCILIATION DEFECT, not a present NOT_RUN | RUN-LOG calls it TRUE because live drift was Package-B spend (`:110`), and Audit C independently finds current gates 0–7b whole-object-equal to the verified snapshot. |
| G70 | CONVENIENT/OPERATIONAL SKIP | Runtime exists; no A2–A4 generate attempt was made (`RUN-LOG.md:59`). |
| G71 | CONVENIENT/OPERATIONAL SKIP | Runtime exists; no A5–A8 server run was made (`:60`). |
| G72 | CONVENIENT/OPERATIONAL SKIP | Runtime and manifest exist; live router assertion skipped (`:61`). |
| G74 | GENUINE DEPENDENCY PROPAGATION | Gate 9a correctly absent because G70–G72 were not established (`:63`). |
| G75 | CONVENIENT/OPERATIONAL SKIP | Smoke was skipped under no-launch policy (`:64`), not due to absent runtime. |
| G76 | CONVENIENT/OPERATIONAL SKIP | Capability run skipped under the same policy (`:65`). |
| G77 | CONVENIENT/OPERATIONAL SKIP | Negative-path live run skipped (`:66`). |
| G78 | CONVENIENT/OPERATIONAL SKIP | Backend live test skipped (`:67`). |
| G79 | CONVENIENT/OPERATIONAL SKIP | Shell-runner assertion skipped (`:68`). |
| G80 | GENUINE DEPENDENCY PROPAGATION | Integration/hash closure depends on G75–G79 (`:69`). |
| G91 | CONVENIENT/OPERATIONAL SKIP | Live VRAM round-trip skipped (`:72`) despite local runtime/model availability. |
| G117 | GENUINE AUTHORITY SKIP | Operator-owned fs-watch window not closed in this session (`:99`). |
| G118 | CONVENIENT/OPERATIONAL SKIP | Live rollback demonstration skipped (`:100`); the local model/runtime preconditions exist. |

## The llama.cpp band

The eleven-goal shorthand “G70–G80 NOT_RUN” is itself inaccurate: G73 is TRUE (`RUN-LOG.md:62`). The actual false band is G70–G72 plus G74–G80.

The runtime is not absent. Independent file-system inspection returned:

```text
runtime/llama.cpp/current                       Junction -> runtime/llama.cpp/versions/lmstudio-cuda12-2.28.2
runtime/llama.cpp/current/llama-server.exe      exists; 20,152 bytes
runtime/llama.cpp/test-models/qwen3-8b.gguf     exists; 5,225,374,496 bytes
```

`evidence/cpm1/9a/a1-version.txt` records `llama-server.exe --version` exiting 0 with version `1 (fe2adf0)`; `evidence/cpm1/9a/pin.txt` records the CUDA pin and junction. Those builder files do not prove a full server run, but the independent filesystem facts refute “runtime absent.”

The real cause is a late operator instruction. `evidence/OPERATOR-INSTRUCTIONS.log:826` says: “Do NOT launch any process … if a goal needs one, record NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED).” C-8(d) is indexed at `:829`. That makes the skips authorized, but also makes them policy skips rather than unavailable-host results. No failed llama.cpp service attempt was recorded after the runtime became available.

**Verdict on 17:** 5 genuine skips/dependency propagations (G28,G53,G74,G80,G117), 10 convenient operational skips despite available technical preconditions (G70–G72,G75–G79,G91,G118), and 2 reporting/oracle reconciliation defects rather than present NOT_RUNs (G3,G64).
