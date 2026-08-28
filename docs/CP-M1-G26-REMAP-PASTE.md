OPERATOR DECISION — CP-M1 G26: remap the Conductor approval policy to `never`. Then run the live round-trip.

Your falsification is accepted in full and the reviewer's Finding 1 is withdrawn. Verified on disk: config-channel-attempt-tail.txt line 31 carries the verbatim `Error loading configuration: approval_policy = "untrusted" is no longer supported; remove this setting` (the TUI paints before the config load fails, which is why the tail reads as a live surface before the error); codex-version.txt records codex-cli 0.149.0 exit 0; spend-log.txt turn count 0 across both attempts. codex 0.149 retired the policy deliberately through both surfaces. Testing it cost one bounded attempt and zero spend, which is what the test was for. Option 3 is now withdrawn as well - pinning an old binary fights a vendor decision rather than routing around a defect, and returns this same choice on the next upgrade with no supported path back.

E-8, THIRD ASK. Your count moved 28 -> 27 and the E-8 paragraph re-explained the earlier 26 -> 25 instead. The actual current regression is G3: "host-hardware not a fresh capture today" - UTC rolled past midnight and the freshness predicate expired. Benign, and it will recur every midnight for the rest of this run. Two things: name the CURRENT regression in the CURRENT report from now on, and decide once whether G3's freshness window is per-session or per-calendar-day. If per-session, say so in the goal note and stop re-capturing; if per-day, re-capture and move on. Do not let a midnight rollover masquerade as a regression for the rest of the package.

DECISION — REMAP TO `never`.

Rationale, so it is on the record and the builder does not have to infer it: build_interactive_codex_command already pins --sandbox read-only together with --cd workspace scoping, and its own docstring states those are pinned "because a node-controlled ~/.codex/config.toml must never be able to widen either (T2 containment)". THE CONTAINMENT BOUNDARY IN THIS DESIGN IS THE SANDBOX AND THE DIRECTORY SCOPE, NOT THE APPROVAL POLICY. Under read-only, an approval prompt can only ever fire on an action the sandbox already refuses, so `never` removes a prompt that has nothing left to gate. It is the closest behavioural equivalent to `untrusted` under this specific sandbox, and it keeps the scripted G26 proof deterministic - `on-request` would risk hanging on a prompt with nobody at the TUI, which governs nothing and fails the proof for the wrong reason.

Carry the remap across ALL SEVEN pin sites in one pass. A partial remap passes one gate and fails another:
  1. modules/sow/adapters/conductor/provider_commands.py:52 - emit "--ask-for-approval", "never"
  2. modules/sow/apps/desktop/conductor/launch-source.js:133 - boundary JSON b.approval_policy
  3. modules/sow/apps/desktop/conductor/launch-source.js:137 - argv assertion
  4. modules/sow/tests/unit/test_frontier_provider_recon.py
  5. modules/sow/tests/unit/test_op12_frontier_adapters.py
  6. modules/sow/tests/unit/test_provider_agnostic_conductor.py
  7. modules/sow/tests/unit/test_provider_document_shape.py
  8. modules/sow/tests/unit/test_side_effect_identity_fence.py

DO NOT CHANGE: automatic_approval stays false (never-ask is not auto-approve, and launch-source.js:133 correctly asserts it); --sandbox stays read-only; --cd scoping stays; the model ref stays gpt-5.6-sol. If any test asserts a SEMANTIC property rather than the literal token - "approvals are not automatic", "escalation is refused" - it must keep passing unchanged. A test that only pins the string is a token update; a test that pins behaviour must not be relaxed to accommodate the remap. If one of the five cannot pass without weakening its assertion, STOP and report it rather than editing the assertion.

Record the remap as a design change under ADDENDUM-01 s6 in its own new evidence file - not appended to any submitted gate's artifact (E-7a). It must state: the removed value, the new value, the seven sites, the T2 rationale above, that this instruction is its authorization, and that the containment boundary is unchanged.

THEN G26 - THE FIRST LIVE SPEND.

A-6 binds: the Conductor leg runs on openai_codex_cli/gpt-5.6-sol, recorded by name and provider in the artifact. Prove: a directive typed into the surface, the response returned into the transcript, a follow-up in the same thread demonstrably carrying prior context, and an interrupt or redirect exercised or recorded UNSUPPORTED(<reason>). A failed delivery surfaces as CONDUCTOR_COMMUNICATION_FAILED, never as silence.

Append every turn to spend-log.txt AS IT HAPPENS - timestamp, provider, model, running count - never batched at the end. Envelope unchanged: openai_codex_cli only, for the G25/G26 Conductor leg and the G58 API-model leg, nothing else; claude_code, grok_build and google_antigravity record NOT_RUN(NO_SPEND_AUTHORIZATION) naming the registry entries examined; terminals_per_subscription stays 1; no worker on a frontier provider. If the round-trip is not proven inside roughly a dozen turns, stop and report - that is a design problem in the surface, not a budget problem. Any spend outside the envelope is STOP SPEND_REQUIRED with no interpretation permitted.

Then G27 (Gate 8d) applying E-7c: cite frozen copies under evidence/cpm1/8d/frozen/ with source_path fields carrying no hash. Then Band 5 onward without pausing at band boundaries until every goal is TRUE or a STOP fires.

A-7: same session - the 16:30Z fs-watch window stays open, you record nothing, driver untouched. C-4 stands.

Unchanged and still binding: builder only - no PASS, no operator signature, no protected-source writes, no fabricated availability, no production promotion. Gates 0-7b byte-identical before and after every write. Ollama's store is read-only always. llama.cpp is not promoted to production default. Application code never launches via cmd.exe, PowerShell, .cmd, .bat or shell=True.
