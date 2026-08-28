OPERATOR DECISION — CP-M1 G26 STOP resolved. Option 0 (new): try the config channel before any policy remap.

Reviewer verified your E-corrections on disk. All confirmed: legacy-assertion-changes.txt restored byte-exact to 650c4f07a56c367691d20c1a97f1fcf29e9ffcad97a0feca675255bd7a8e6cc7 (your CRLF diagnosis was correct); u175-allowlist-design-change.txt relocated under 8d; as_of_utc/mutated_by present on all three re-pointed rows; e9 account written; G19 and G24 both TRUE again; 28/124; gates 0-7b snapshot-clean under the preamble guard; TOTAL-A 371/1850; spend-log turn count 0. The STOP itself is verified: provider_commands.py:52 does emit "--ask-for-approval", "untrusted" alongside sandbox=SANDBOX_READ_ONLY, and you stopped before spending. Correct conduct - reported rather than spent into.

TWO REVIEWER FINDINGS THAT CHANGE THE OPTION SET.

Finding 1 - the removal may not be a removal. OpenAI's current published approval-policy documentation STILL lists untrusted as a valid value alongside on-request and never, and the upstream enum UnlessTrusted still appears in current issue traffic. Your host CLI rejected it from the FLAG parser only. That is the signature of a flag-surface regression in 0.149, not a semantic retirement of the policy. Your code already passes a policy through the config channel one line above the failure - "--config", "check_for_update_on_startup=false". The config channel may still accept the policy the flag parser now refuses. Treat this as a HYPOTHESIS TO TEST, not a fact to build on.

Finding 2 - the remap is wider than your STOP report scoped. untrusted is pinned in SEVEN files, not four: modules/sow/adapters/conductor/provider_commands.py:52; modules/sow/apps/desktop/conductor/launch-source.js at BOTH :133 (boundary JSON b.approval_policy) and :137 (argv assertion); and five unit tests - test_frontier_provider_recon.py, test_op12_frontier_adapters.py, test_provider_agnostic_conductor.py, test_provider_document_shape.py, test_side_effect_identity_fence.py. Any remap must carry all seven or it will pass one gate and fail another. Note also that launch-source.js:133 asserts b.automatic_approval !== false; that field stays false under every candidate policy and must NOT be changed.

OPERATOR DECISION - OPTION 0. Do this first, and ONLY this:

Replace the flag with the config form - emit "--config", "approval_policy=untrusted" in place of "--ask-for-approval", "untrusted" in _codex_command, leaving the boundary JSON's approval_policy value, automatic_approval, the read-only sandbox and all governance semantics untouched. Update launch-source.js:137's argv assertion to match the new emission shape. This is a TRANSPORT change, not a policy change: the governed intent - supervisor-approved escalation only - is preserved exactly, and no governance decision is delegated to you or to me.

Then launch once and observe. TWO OUTCOMES, both bounded:

  OUTCOME A - it launches. Capture the emittedTail proving acceptance, record the transport change in the 8d evidence with this instruction cited as its authorization, and PROCEED IMMEDIATELY to the G26 live round-trip under the spend envelope below. No further operator turn needed.

  OUTCOME B - the config channel also rejects untrusted. STOP AGAIN and report, with the verbatim error and the codex --version output. Do NOT fall back to never or on-request on your own judgment. The remap is a governance-boundary decision and the operator has explicitly reserved it; guessing it to keep moving is exactly the scope drift this package forbids. A second stop here costs one operator turn and is the correct outcome.

Either way, capture codex --version verbatim into the 8d evidence. The STOP report asserts 0.149.0 and the reviewer could not verify a host binary version from the filesystem; it needs to be an artifact, not a report line.

G26 WHEN IT RUNS - the first and only live spend so far.

A-6 binds: the Conductor leg runs on openai_codex_cli/gpt-5.6-sol, recorded by name and provider in the artifact; the work order's local-model predicate is unsatisfiable and the file stays unamended so the amendment remains traceable. Prove: a directive typed into the surface, the response returned into the transcript, a follow-up in the same thread demonstrably carrying prior context, and an interrupt or redirect exercised or recorded UNSUPPORTED(<reason>). A failed delivery surfaces as CONDUCTOR_COMMUNICATION_FAILED, never as silence.

Append every turn to spend-log.txt AS IT HAPPENS - timestamp, provider, model, running count - never batched at the end. Envelope unchanged: openai_codex_cli only, for the G25/G26 Conductor leg and the G58 API-model leg, nothing else; claude_code, grok_build and google_antigravity record NOT_RUN(NO_SPEND_AUTHORIZATION) naming the registry entries examined; terminals_per_subscription stays 1; no worker on a frontier provider. If the round-trip is not proven inside roughly a dozen turns, stop and report - that is a design problem in the surface, not a budget problem. Any spend outside the envelope is STOP SPEND_REQUIRED with no interpretation permitted.

Then G27 (Gate 8d) applying E-7c: cite frozen copies under evidence/cpm1/8d/frozen/ with source_path fields carrying no hash. Then Band 5 onward without pausing at band boundaries until every goal is TRUE or a STOP fires.

E-8 stands: any goal going TRUE -> FALSE is named in your status report with its cause, on the same line as the count.

A-7: same session - the 16:30Z fs-watch window stays open, you record nothing, driver untouched. C-4 stands.

Unchanged and still binding: builder only - no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or shell=True.
