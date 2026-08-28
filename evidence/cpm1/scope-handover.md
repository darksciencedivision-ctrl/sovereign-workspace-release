# utc: 2026-08-26T07:13:49.2860381Z
# producer: ox-alpha master-run-order-20260826 phase3-to-4-scope-handover

# SCOPE HANDOVER - Phases 2-3 wrote a tree CP-M1's Band-0 recorded as protected

Authority: MASTER-RUN-ORDER-20260826.md section 2, "Phase 3 -> 4" (mandatory and explicit), which itself cites
the operator's live instruction of 2026-08-26 logged verbatim in evidence/OPERATOR-INSTRUCTIONS.log
(utc 2026-08-26T06:18:59Z). Without this handover CP-M1's protected-source claim would become retroactively false.

## 1. What Phases 2-3 changed in that root (D:\multi model terminal app)

Phase 2 (SPA Track A) changed NOTHING - NOT_RUN(BUNDLE_ABSENT) in its entirety; zero writes to any tree.
Phase 3 (MT-P1) changed exactly ONE file:

| file | before sha256 | after sha256 | nature |
|---|---|---|---|
| sovereign-orchestration-workspace/docs/registers/UNRESOLVED_ISSUE_REGISTER.md | `9e1b31c68d36e9aa3899e1d5ca2373a393f79cf99164aa2e459e3a73ca80ea79` (1,034,948 bytes) | `9efd08a56616fe75f21353b962c19fcd063284d42b00f2e47d10b1fd72d91658` (1,041,977 bytes) | single append-only event: rows U543/U544/U545 (MT-05/06/07). ARRIVAL STATE PROVEN AN EXACT BYTE PREFIX of the after-state (recomputed hash of first 1,034,948 bytes == before hash). |

Full-root verification: the pinned tool re-capture below found exactly THREE changed paths against Band-0 -
the register above PLUS two pytest runtime-cache files (.pytest_cache/v/cache/lastfailed,
.pytest_cache/v/cache/nodeids) rewritten by tonight's authorized suite run. Runtime state, not source;
named for completeness. Zero other differences across all 9,727 tracked-path entries.

## 2. Protected-root manifest RE-CAPTURED for THAT ROOT ONLY

Superseded artifact, preserved untouched and named:
evidence/cp01/manifests/manifest-cp01-before-multi-model-terminal-app.txt
(root D:/multi model terminal app, 9,727 entries, captured 2026-08-25T06:56:12Z, sha256
`438a7a3ac72f8ea69e392c9a6252ec0f107efdba128efbf9d6eadaf7539fc08d`)

Superseding artifact, methodologically identical (same pinned tool sha256 64c488ed07c95579c69bcb8dee42fb2aec88b821bf676cc7b259740d7f955d22,
same excludes node_modules/.git/__pycache__, same root, 9,727 entries):
evidence/cpm1/mt/manifest-cpm1-handover-multi-model-terminal-app.txt
sha256 `b267cde705bda9c23e02c1cd94ed052ee76a1707aeba5dd3dbde8d4648395d66` (captured 2026-08-26T07:13:49.2860381Z)

Diff against the superseded artifact: 3 changed entries (listed in section 1), 0 new, 0 removed.
The other four protected roots are untouched by Phases 2-3 and their Band-0 artifacts stand unamended.

## 3. Standing statement owed to Gate 8j's note (to be written verbatim into the 8j note when submitted)

"The multi-model-terminal root was writable during Phases 2-3 by operator authorization (MASTER-RUN-ORDER-20260826
Phase 0 case-3 rule and Phase 3->4 handover, logged at utc 2026-08-26T06:18:59Z); it was read-only to this builder
before those phases began and is read-only again from this handover forward. The one source file changed there is
accounted above with before/after hashes and an append-only prefix proof."

## 4. Boundary assertions

- No product tree (D:\Sov 1\, D:\Sovereign Distillery\, D:\Token Piggy Bank\) was read into evidence beyond
  design-intent citations, nor launched, nor written. R-7 STRUCK honoured: byte-identical.
- Ollama's store untouched. docs/canonical/ and schemas/*.schema.json untouched (git-clean verified twice).
- No gate ledger key was altered by Phases 2-3. Gates 0-7b byte-identity obligation carries into Phase 4.