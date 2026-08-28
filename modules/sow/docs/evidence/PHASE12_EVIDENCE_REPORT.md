# PHASE 12 EVIDENCE REPORT — Parakeet Voice Input (STT-only)
Autonomous loop iteration 13 · 2026-07-17Z · gate: `gate/phase-12`

## Objective
Parakeet voice input per Buildout Directive §5 Phase 12 / Plan §7-P12, §2.4/§9.9 (I-V1..V3):
STT-only; push-to-talk; command preview; approval for destructive commands; raw audio
discarded by default; text and voice produce equivalent control events. §2.8 voice matrix.
Prohibited: NO TTS; Parakeet is a transducer not a reasoning node; voice cannot bypass
permissions.

## Source state
Tags through `gate/phase-11`; freeze `--check` clean throughout. `next_step: phase-12`.

## Host detection (no install, recorded)
NVIDIA GPU **present**, WSL **present**, NeMo **absent** (pip out of scope) → real Parakeet
unavailable → MockSTT behind the same interface (I-A1). U1/U2 remain open-for-hardware.

## Files
- **Work commit `e85f7713`:** `voice_bridge/{command_broker,__init__}.py`;
  `adapters/voice_parakeet/{engine,adapter,__init__}.py`; `tests/integration/test_voice_input.py`.
- **Remediation `0bf843f3`:** F1–F7 fixes.

## Exit criteria — met, mapped to code + test
- **STT-only, NO TTS:** the adapter/engine expose only STT; there is no synthesis/speak method
  by construction; `get_usage` reports `tts:False`. Test asserts no `synthesize/speak/say/tts`.
- **Propose-never-execute (invariant 25):** `propose_command` transcribes → maps to a candidate
  command → submits to the broker; the adapter holds a **submit-only** handle and structurally
  cannot approve/execute. Test asserts the transducer has no approve/_execute.
- **Push-to-talk + command preview:** start/stop_capture; propose_command returns the broker
  outcome (the preview) before any execution.
- **Low-confidence ⇒ clarification:** a voice transcript below the confidence threshold (or with
  absent confidence — fail closed) yields CLARIFY, never execution.
- **Destructive ⇒ approval queue:** destructive verbs are queued; nothing executes until the
  OPERATOR approves; a non-operator approve is refused; the operator can also reject.
- **Voice cannot instantiate nodes / expand permissions:** spawn/grant (and synonyms) are
  PROTECTED → queued, never auto-executed from voice.
- **Typed/voice equivalence:** both surfaces flow through the same broker (canonicalized at the
  broker); the same command produces control events with identical semantics (verb/target/args),
  differing only in id/ts/source.
- **Transcribe-then-discard + offline:** audio discarded by default; optional retention is off,
  bounded, TTL-purged (auto-purge on transcribe), local-only, cleared on close; `network=none`
  recorded (no network calls in the voice code).

## Independent review (standard-stakes: validator + spec-auditor)
- **gate-validator: PASS.** Mapped every §2.8 criterion to inspected code + self-run tests;
  verified the classifier is a fail-safe whitelist (EXECUTED reachable only for explicit SAFE
  verbs; unrecognized/synonym/case-variant fail safe), mock/real split honest, scope/freeze
  clean, no Phase 13 smuggled, no invariant drift.
- **spec-auditor: FINDINGS 2 MAJOR / 5 MINOR / 2 NOTE** (classifier sound; MAJORs were latent
  least-privilege gaps on the safety-critical path). Dispositions (all fixed pre-gate):
  - **F1 MAJOR — FIXED:** `approve()` had no operator-identity check. Now requires an operator
    Identity (role=='operator'); non-operator refused. Operator authority is a code invariant.
  - **F2 MAJOR — FIXED:** the transducer held the whole broker (incl. approve/execute). Now a
    submit-only handle (SubmitOnly); structurally cannot approve/execute. Pinned by test.
  - **F3 MINOR — FIXED:** absent voice confidence now fails closed to CLARIFY.
  - **F4 MINOR — FIXED:** auto-purge on transcribe; retention posture (ttl/local_only/
    auto_purge/retained_now) surfaced in get_usage.
  - **F5 MINOR — FIXED:** canonicalization moved to the broker (both surfaces); typed
    case/spacing variants equivalent to voice (hyphen vs space kept a real distinction).
  - **F6 MINOR — FIXED:** operator `reject()` path added (queue exit that isn't execution).
  - **F7 MINOR — FIXED:** synonym-escalation, double-approve-refused, confidence-None, reject,
    operator-approval tests added.
  - F8/F9 NOTE — recorded: classification keys on verb (real dispatch not wired yet → target-
    scope check when dispatch lands); real-audio buffer-free discard is a Track G integration
    test (mock stores only refs).

## Substitutions (loop directive §6)
MockSTT stands in for Parakeet/NeMo (absent on host); the command-safety bus, approval flow,
retention policy, and typed/voice equivalence are real code. Real Parakeet integration
(streaming latency, VRAM, WSL mic bridge) is Track G / U1/U2, open-for-hardware.

## Deviations / carried
- ruff unavailable (pip out of scope); code typed + stdlib-first.
- Carried: U1 (Parakeet streaming latency + VRAM under concurrency), U2 (Windows mic →
  WSL bridge + PTT trigger) — open-for-hardware; U24 (new: real-audio buffer-free discard +
  target-scope check when command dispatch is wired).

## Gate verdict
**PASS.** STT-only (no TTS by construction); propose-never-execute enforced by least privilege
(submit-only transducer + operator-gated approve); §2.8 matrix green; voice cannot bypass
permissions (fail-safe whitelist); mock/real split honest; both MAJOR review findings fixed
with pinning tests before closure. 322/322 tests.

## Commits
Work `e85f7713` → remediation `0bf843f3` → this evidence/register commit (tagged `gate/phase-12`).

## Next phase
`phase-13` (final build phase) — Evaluation & hardening: comparative harness (single model /
conductor+raw workers / Sovereign no-debate / Sovereign+debate) on the reference project with
mock/local backends; cost-to-accepted-output instrumentation; kill-matrix recovery; hardening
backlog triaged; report losses honestly (model-quality conclusions limited to mock/local).
Then `finalize` → FINAL_BUILD_REPORT.md + tag build/complete.
