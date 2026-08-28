# Phase 17C close-revalidate checkpoint — gate withheld

Date: 2026-07-27
Work unit: `phase-17c.close-revalidate`
Outcome: **FAIL / checkpoint only**
Gate/tag: **withheld** (`gate/phase-17c` was not created)

## Objective and source state

Revalidate the Phase 17C live spoken round trip after the findings recorded by
`PHASE17C_CLOSE_EVIDENCE_REPORT.md`. At entry, `HEAD=d481abf`, the latest applicable tag was
`gate/phase-17b`, and `LOOP_STATE.next_step=phase-17c.close-revalidate`; tags and state agreed.
The worktree already contained the prior turn's coherent, uncommitted revalidation WIP.

This report is append-only and does not upgrade the older 33/33 receipt. The final tracked product-code
diff identity was `git patch-id --stable = d96056f2f6490f8904c39ae70d23aec03397d72b`;
the new untracked delivery modules/tests are additionally named below. No work commit could be created:
the managed filesystem denied creation of `.git/index.lock`.

## Implemented and falsifiable safety changes

- Extracted conductor delivery and pane-state decisions into headless modules with tests for every guard.
- Refused production writes unless a supervisor-owned non-executing authority boundary is bound.
  No such binding exists yet, so direct voice CHAT is disabled. Vendor `plan mode on` is retained only
  as an interaction-state guard; it is not treated as authority. Manual, accept-edits,
  bypass-permissions, confirmation prompts, unknown modal chrome, stale input history, and unreadable
  state also refuse before the body write.
- Scanned the whole normalized utterance for protected/destructive verbs, synonyms, and common
  inflections; polite prefixes no longer bypass the approval queue.
- Made echo confirmation window-exact; a prior echo and CLI chrome numbers cannot prove a reply.
- Made possible partial/throwing writes residue-safe; only operator Enter/Ctrl-C clears residue.
- Removed stale self-check claims that a stand-in pane proved live-conductor delivery.
- Preserved transcribe-then-discard, propose-never-execute, and the no-TTS boundary.

Principal new files:

- `apps/desktop/voice/conductor-write.js`
- `apps/desktop/voice/pane-state.js`
- `apps/desktop/test/conductor-write.test.js`
- `apps/desktop/test/pane-state.test.js`

## Real command evidence

| Check | Foreground result |
|---|---|
| Desktop suite: `npm test` in `apps/desktop` | 409 passed, 25 skipped, 0 failed |
| Terminal suite: `node --test terminal/test/*.test.js` | 196 passed, 0 failed |
| Phase 17C Python subset (five integration modules) | 122 passed, 0 failed under Python 3.14 |
| Focused JS safety/reply suite | 62 passed, 0 failed |
| Focused Python voice suite | 40 passed, 0 failed |
| Frozen contract check | `freeze check OK: no drift in FROZEN set against recorded manifest` |
| Canonical/schema diff | empty |
| `git diff --check` | clean |
| remotes | none |

The desktop skips are the repository's existing live checks that require Python 3.12 or explicit live
fixtures. They are not counted as proof of this close.

## Packaged receipt attempt

`node selfcheck/run.js voice-conductor` was run in the foreground. It exited 1 before producing a new
receipt: this managed context exposes only Python 3.14, so the pinned Python 3.12 gateway/emitter path
failed closed; Electron also lacked writable user-profile/cache access and lost its renderer/GPU
process. The existing receipt remained byte-identical at SHA-256
`B74AC169A982908383ADDE0A495A832C1A6B7104251389268E24469C9A99FE77`, so it predates these fixes and
is not cited as current-tree evidence. No product/model process, capture WAV, fixture WAV, or scratch
lease survived teardown.

There is no faithful substitution for the in-Electron receipt: a headless test cannot establish that
the packaged shell saw the real vendor state, transcribed real PCM, delivered through
the production boundary, received a reply, discarded audio, and released the terminal in one run.

## Independent reviews

The first fresh gate-validator returned **FAIL**: the code blockers were fixed, but stale U144 runtime
claims and the missing current-tree receipt remained. The stale runtime/self-check/test claims were
then corrected. The first fresh spec-auditor returned **FINDINGS / do not tag**: it identified the
semantic-paraphrase authority gap, typed-surface equivalence debt, stale receipt, and two stale
explanations. A later spec pass rejected vendor chrome as authority under invariant 29, so production
direct CHAT is now disabled pending a supervisor-owned boundary. Final review verdicts:

- Gate-validator: **FAIL** — its 406/122/196 sweep and freeze checks were green; after the auditor's
  final safety response, the builder re-ran the final tree at 409/122/196. The current-tree
  packaged receipt is absent and the prior receipt proves manual mode on the older tree.
- Spec-auditor: **FINDINGS / do not tag** — vendor plan-mode chrome is not authority, the initial
  parser mishandled manual→plan lifecycle/suffixes (corrected), physical typed equivalence is open,
  and no current-tree receipt exists. The authority finding is resolved only in the safe direction:
  production direct CHAT is disabled, so the Phase 17C positive criterion remains unmet. Its final
  minor stale runtime-metadata claim was corrected to call the old receipt historical, not current.

## Exit-criterion disposition

- Real microphone PCM → WSL Parakeet → bridge → live 17A conductor → reply: **not re-proven on this
  tree**; the prior receipt proves the older tree only.
- Protected/destructive speech proposes and never executes: **headlessly enforced in the safe
  direction**; unclassified semantic paraphrases cannot reach the tool-capable conductor because
  production direct CHAT is disabled. Ordinary-chat direct delivery is therefore not satisfied.
- Audio discard / no TTS / lease release: **headless and prior-tree evidence green; current packaged
  composition owed**.
- D-P16 in-Electron receipt and spoken human half: **not satisfied in this managed context**.
- Mandatory independent confirmation: **FAIL**, so the high-stakes gate cannot pass.

## Remaining work

The next revalidation must run on a host context with Python 3.12 and writable Electron
profile/cache access, implement and prove a supervisor-owned non-executing authority boundary (vendor
chrome cannot supply it), regenerate
`PHASE17C_CLOSE_SELFCHECK.json` from the exact committed tree, run both mandatory reviews against that
same tree, and tag only on PASS. It must also resolve or explicitly carry the physical typed-input
equivalence debt described in U149.

## Commit-protocol deviation

The required work/evidence/state commits could not be created. The real foreground command failed:

```text
fatal: Unable to create 'D:/multi model terminal app/sovereign-orchestration-workspace/.git/index.lock':
Permission denied
```

This is not a directive §8 terminal condition, so state remains RUNNING and the failure count advances.
