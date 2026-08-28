# Audit G — 15-goal independent adversarial sample

I ignored `goalcheck.py` for these verdicts. Test command:

```text
py -3.12 -m pytest -q -p no:cacheprovider \
  shell/tests/test_registry_fields_projected.py shell/tests/test_legacy_alias_resolution.py \
  shell/tests/test_start_invokes_no_pipeline.py shell/tests/test_tokencenter_loopback_and_csrf.py \
  shell/tests/test_log_fields_redacted.py shell/tests/test_planner_never_evicts_generating.py \
  shell/tests/test_ingestion_rejects.py shell/tests/test_router_no_unrequested_transition.py \
  shell/tests/test_frontend.py
................ [100%]
16 passed in 1.12s

modules/tokencenter: 5 passed in 0.08s
modules/distillery: 4 passed, 61 subtests passed in 0.08s
```

An initial combined pytest invocation failed collection because `piggybank` was not importable from the workspace root. Re-running each copied module from its own root with `PYTHONPATH` set produced the results above; the collection failure is not hidden.

| Goal | Independent verdict | Evidence |
|---|---|---|
| G38 — canonical registry | **FAIL** | `canonical_registry.py:167-169` exposes `list_for_selectors`, but `rg -n 'list_for_selectors|canonical_registry' modules/sow shell --glob '!**/tests/**'` finds no production consumer outside that file. Actual selector code still consumes `_REASONING_MODELS/_CODER_MODELS` (`modules/sow/adapters/roster.py:23-24,64-65`) and OpenCode keeps `OPENCODE_CODER_MODELS` (`modules/sow/adapters/coding/opencode/harness.py:60`; `node_runtime/supervisor/opencode_spawn.py:34,72`). One registry does not serve every selector. |
| G39 — final registry shape | **PASS** | `canonical_registry.py:11-16` declares every required field; defaults are populated at `:23-46`; `dump_registry()` returned rows and the targeted tests passed. |
| G41 — live discovery | **FAIL** | Live discovery implements only Ollama (`canonical_registry.py:98-113`). Conductor and roster entries are seeds (`:51-95`), and there is no provider-CLI/OpenCode live enumeration in the registry builder (`:117-131`). |
| G46 — Distillery console | **PASS** | Live `GET http://127.0.0.1:5184/console -> 200`; all ten required labels independently searched TRUE, bare `D:/` FALSE. The source is the same literal console at `modules/distillery/serve.py:9-24`. |
| G47 — no compute on open | **PASS (bounded)** | Live `GET /health -> 200 {"ok":true,"status":"idle","compute":false}`. The server imports only HTTP/JSON and exposes GET-only health/console (`serve.py:1-48`); `test_start_invokes_no_pipeline.py:7-18` passed. I did not inspect GPU process history across its original launch, so this establishes the current product path, not historical absence of every transient process. |
| G52 — Token Center module | **PARTIAL** | Manifest has HTTP readiness/JSON identity/browser open/job-object stop (`shell/modules/tokencenter.json:31-52`). Live `GET :8765/healthz -> 200 {"ok":true,"collector_error":null}` and module tests pass. I did not stop the operator-owned PID, so clean stop was not re-demonstrated. |
| G54 — real Token backend state | **PARTIAL** | Live `GET :8765/api/summary -> 200`; response has `collected_at`, 10 provider rows, 40 model rows, usage totals and no collector error. UI renders provider/model/locality/tokens (`modules/tokencenter/static/app.js:70-89`) and refresh time (`:234-248`). It does not implement an explicit staleness threshold or clearly distinguish configured from observed availability, so the full displayed-state contract is not met. |
| G57 — Band-10 scenario | **FAIL** | The required one-session acceptance was not run. `stepB-debate.txt` says NOT_RUN; `stepC-workspace.txt` says NOT_RUN; `stepD-conductor.txt` says NOT_RUN; `stepE-opencode.txt` says NOT_RUN. File existence is not the scenario. Distillery and Token Center legs did run, but four central legs did not. |
| G58 — proof chain | **FAIL / NOT DEMONSTRATED** | `evidence/cpm1/8j/proof-chain.txt:5-8` marks local LLM, API model, OpenCode, and Conductor all NOT_RUN. The document accurately reports absence, but no end-to-end proof chain holds in product evidence. |
| G84 — backend parity | **FAIL** | The matrix is conditional prose, not two executed backends (`parity-matrix.txt:7-8` includes “when router up/model loaded” and a FAIL cell). Runtime inspection gives `capabilities()['stream'] == True` while `hasattr(backend,'stream') == False`; source sends only `"stream": False` (`llamacpp.py:13-30`) yet reports stream capability at `:53-54`. |
| G88 — single evictor | **FAIL** | Manifest has `--no-models-autoload` but no `--models-max` (`shell/modules/llamacpp.json:12-20`). The shipped test explicitly requires its absence (`test_router_no_unrequested_transition.py:10-11`). This directly contradicts `single-evictor.txt`, which says `--models-max` is set above the planner bound. |
| G102 — context variables | **FAIL** | `context-measurement.txt:4-11` provides one blanket NOT_MEASURED paragraph, not per model/context combination, and omits explicit requested/initialized context and processed-prompt-token values. NOT_MEASURED is allowed, but the goal still requires a per-combination record of each variable. |
| G108 — resource accounting in existing surfaces | **FAIL** | Shell UI contains resource terms only in the Token Center card description (`shell/static/app.js:45-49`). No source consumer calls backend `metrics()` or renders model/artifact/load/context/KV fields. A description string is not resource accounting. |
| G109 — logging and metrics | **PARTIAL** | LogRing fields and the shared redaction path are implemented (`shell/src/logring.py:32-49`) and the redaction test passed. Llama has `metrics()` (`llamacpp.py:56-66`), but Ollama does not, the `Backend` protocol omits it (`adapters/base/backend.py:20-38`), and no G108 surface consumes it. |
| G120 — diff classification | **FAIL** | Independent hash comparisons found at least ten changed product files absent from `diff-classification.txt`: `shell/src/{adapter.py,server.py,states.py}`, `shell/static/{app.css,app.js}`, `shell/modules/sow.json`, desktop `main.js` and `picker/worker-spawn.js`, `modules/distillery/serve.py`, and `modules/tokencenter/piggybank.py`. Each returned `changed=True|classified=False` with full baseline/live hashes. The file's `UNEXPECTED: 0` (`evidence/cpm1/9j/diff-classification.txt:21`) is therefore false for the run-wide goal; it classifies only a late subset. |

## Sample result

Three pass, three partial, nine fail/not-demonstrated. The failures concentrate exactly where Audit A predicted: structural existence checks and builder-authored prose allowed claimed TRUEs without the demanded live behavior. G88 and G120 are direct contradictions, not merely missing evidence.
