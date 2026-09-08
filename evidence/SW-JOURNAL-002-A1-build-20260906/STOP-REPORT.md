# utc: 2026-09-06T17:59:20.033031+00:00
# producer: Codex SW-JOURNAL-002-A1 scope stop
FACT[entry.txt] Host quiescence was independently confirmed and all seven A4 pins matched. Previous entry evidence in ../SW-JOURNAL-002-A1-entry-20260906 is carried forward. The renewed operator instruction was quoted verbatim in operator-declaration.md and appended to ../OPERATOR-INSTRUCTIONS.log.

FACT[f39-boundary-receipt.txt] The real pane:select-execution handler, evaluated headlessly with injected pane state, accepts powershell without a model but returns CONFIGURING with pid=null and invokes no launcher. Selection is present; execution is not connected by that handler.

FACT[../../modules/sow/apps/desktop/picker/launch-source.js] The governed launch-ticket validator's ADAPTER_EXECUTABLE allowlist contains claude, codex, grok, agy, ollama and opencode, but no PowerShell executable. frontierClaim returns null for an unrecognized adapter and isWellFormedWorkerTicket rejects it. It also requires residency for every accepted non-frontier ticket.

FACT[f39-boundary-receipt.txt] The existing local-model ticket fixture is accepted by the validator. Replacing its adapter and executable with PowerShell makes that same validator reject it. The probe starts no product, model or provider process.

FACT[../../modules/sow/node_runtime/supervisor/worker_pane_spawn.py] authorize_worker_pane dispatches to frontier, opencode_local or ollama_local; all other adapters raise WorkerPaneRefused with gate unknown_adapter. This file is not in A4.

FACT[../../modules/sow/node_runtime/supervisor/provider_node_registration.py] The provider facts table has no PowerShell registration entry. Its local adapters are explicitly residency-governed. The amendment's requirement to retain a governed node record needs an explicit shell treatment; inventing a model or residency claim would not satisfy it.

INTERPRETATION: STOP condition required_change_outside_A4. F-39 A3.6 requires the existing governed launcher and node record, with no new spawn route; A4 does not authorize the validator or Python authorizer changes necessary for PowerShell. The root AGENTS.md sections 7 and 13 prohibit repair beyond the authorized envelope and require STOP. This is a source-scope blocker, not new_channel_required, shell_becomes_recipient, write_side_change_required, or unrun operator acceptance.

FACT[source-postimages.json] No product source was edited. All seven A4 files, both mutation baselines, policy.py, memory_service.py and tasks/graph.py remain byte-identical to this entry. F-37 and F-38 are NOT_STARTED; F-39 is BLOCKED. No earlier finding is reopened, no gate was changed and no git mutation was performed.

FACT[baseline-js.txt] Baseline JS: 1241 tests, 1241 pass, 0 fail, 0 skipped, 0 cancelled.

FACT[baseline-python.txt] Baseline Python: 2742 passed, 3 skipped, 0 failed, 23 warnings; 12 subtests passed.

FACT[execution-status.json] Both U186 mutation harnesses are NOT_RUN because main.js was never edited or re-pinned. No mutation or repair verification is claimed. Operator acceptance was not run.

RECOMMENDATION: Option 1: issue a revised, pinned directive authorizing a governed PowerShell execution type across the existing ticket validator, authorizer, registration and enumeration chain, explicitly defining the shell's node identity and non-model resource treatment. At minimum, apps/desktop/picker/launch-source.js and node_runtime/supervisor/worker_pane_spawn.py require changes outside A4; provider_node_registration.py, tools/live/emit_worker_launch.py and picker enumeration/selection contracts need inclusion in the revision's scope audit. Do not waive their checks or manufacture a local-model ticket for a shell. OpenCode's available adapter is opencode_local and uses a model-backed coding launch, which also needs to be distinguished from its no-model selection enum.

RECOMMENDATION: Option 2: explicitly defer F-39 and resume F-37/F-38 as a bounded build, retaining their required main.js re-pin, regression and mutation checks.

INTERPRETATION: Directive gap for the next amendment: an execution enum and exposed selection channel do not establish an executable governed adapter. Pin the whole existing launch chain after verifying that the requested backend is admitted by it.

RECOMMENDATION: Standing runbook requirement, adopted by the operator: the host must be quiescent before every future build run. The operator must close the application and shell after every acceptance; independently verify that no module processes remain and ports 5175, 8700 and 5180 are free. If not, STOP at HOST_NOT_QUIESCENT.

BUILDER CLAIM: this amendment submits no gate for reviewer evaluation and asserts no PASS or completion status.
