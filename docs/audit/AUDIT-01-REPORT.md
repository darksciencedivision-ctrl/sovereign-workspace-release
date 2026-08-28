# CP-M1 independent audit — AUDIT-01

## Verdict

**The claim under audit is not ratified.** The saved oracle does print 107/124 TRUE, but 58 of those 107 TRUE outcomes rest on TRIVIAL or SELF-REFERENTIAL predicates; 17 are structural and only 32 are judged by substantive predicates. An adversarial 15-goal sample produced 3 pass, 3 partial, and 9 fail/not-demonstrated. See `docs/audit/A-oracle-classification.md` and `G-adversarial-sample.md`.

The “17 NOT_RUN” framing is also not ratified. The exact oracle-FALSE set has 17 goals, but it does not match RUN-LOG NOT_RUN: G3/G64 are logged TRUE while G34/G35 are logged NOT_RUN even though the oracle counts them TRUE (`evidence/cpm1/RUN-LOG.md:107,110,120-121`). Of the 17, I classify 5 as genuine authority/dependency skips, 10 as convenient operational skips despite available technical preconditions, and 2 as reconciliation defects. See `D-notrun-causes.md`.

Ledger whole-object snapshot fidelity for gates 0–7b is intact, and all 379 recorded evidence hashes are well-formed 64-hex. But 7a/7b occur in neither independent witness, 7a/7b have ten live evidence hash drifts, and multiple later candidates violate E-7c by citing mutable live paths. No candidate gate reads PASS. Gates 9a, 9b, and 9i are absent, contrary to `docs/CP-M1-REPORT.md:160`; the ledger contains only 9c–9h and 9j in that series.

Envelope integrity fails. Independently recomputed line totals are Package A 814/1850 (810 excluding runtime `.recovery` drift), not 430, and Package B 279/1625, not 156. Package B's `llamacpp.json` is 53 changed lines against its 45-line area cap. Four protected roots plus the MMT handover root are clean, but `D:\Token Piggy Bank` has two modified launchers relative to Band 0. Zero delivered provider turns are recorded; monetary spend outside workspace records could not be checked.

## What could not be audited

These limitations are verdict-bearing, not footnotes:

- Provider billing/account records were unavailable. The audit proves zero *recorded delivered turns*, not zero external monetary spend.
- I did not stop or restart operator-owned Distillery/Token processes, so G52 clean-stop and G118 rollback were not re-demonstrated.
- I did not launch Conductor, OpenCode, Ollama, or llama.cpp services after the recorded no-launch instruction (`evidence/OPERATOR-INSTRUCTIONS.log:826`). Their live round-trips remain unverified.
- I could not reconstruct historical GPU/process state around prior launches; G47 was checked by live idle health, source, and tests.
- I could not attribute the two Token original-tree launcher mutations to a person or session. Their presence and timing are established; authorship is not.
- The workspace is not a Git repository (`git -C <workspace> status` returned `fatal: not a git repository`), so run-wide diff classification had to use the directive baselines and provenance sources rather than a repository commit diff.

## Findings ranked by cost if wrong

### 1. Protected original source is not intact — critical envelope cost

Independent manifest rehash found two changes under `D:\Token Piggy Bank`: `Start-SovereignTokenCenter.ps1` and `Start-TokenPiggyBank.ps1`. Both Band-0 hashes are `0d806419…` (`manifest-cp01-before-token-piggy-bank.excl-data.txt:51-52`); both now hash `50e56fe687f2b4a92c40d2d904cfd2ad27c86bbf7ae4b66d04da225de0146f97`. Git reports 92 insertions/18 deletions. A false “protected roots clean” conclusion risks accepting source-tree contamination.

### 2. The run's own diff and line-budget controls are false — critical scope cost

G120's `UNEXPECTED: 0` is not a diff. Ten independently hash-confirmed changed product files are absent from its list, including `shell/static/app.js`, Distillery `serve.py`, and Token `piggybank.py`; see `G-adversarial-sample.md`. G121 trusts stale files rather than recomputing (`goalcheck.py:1338-1341`). The correct Package-B `llamacpp.json` count is 53, over the 45 cap. If accepted, these controls allow out-of-envelope work to be promoted.

### 3. The canonical registry is not canonical in use — high product/governance cost

`list_for_selectors()` exists (`canonical_registry.py:167-169`) but no production selector consumes it. Roster and OpenCode retain independent hard-coded lists (`adapters/roster.py:23-24,64-65`; `opencode/harness.py:60`). This defeats the one-registry safety objective and makes availability/compatibility claims diverge by surface.

### 4. Band-10 acceptance was represented by files, not the required scenario — high acceptance cost

G57 is TRUE because eight files exist (`goalcheck.py:855-859`), while the files themselves say Debate, workspace, Conductor, and OpenCode were NOT_RUN. G58's proof chain marks every substantive branch NOT_RUN (`evidence/cpm1/8j/proof-chain.txt:5-8`). Promoting 8j would treat absence of the acceptance run as acceptance evidence.

### 5. The oracle's TRUE unit is non-uniform and often circular — high assurance cost

Thirty of 107 TRUEs are self-referential and 28 trivial. Examples: G26 accepts three words instead of a live dialogue (`goalcheck.py:593-603`); G84 accepts matrix vocabulary (`:1051-1057`); G108 accepts chosen words in UI source (`:1231-1236`); G120 accepts the builder's own `UNEXPECTED: 0` (`:1330-1336`). This does not prove all 58 underlying goals false, but it proves the score cannot carry a uniform “goal achieved” meaning.

### 6. Evidence freezing is incomplete — high reproducibility cost

E-7c says a gate never hashes a still-editable file (`docs/SWS-UI-001-v1.2-ADDENDUM-04.md:46`). Rehash found six drifts in 7a and four in 7b. Mutable-path evidence also remains in 8a, 8b, 8c, 8h, 8i, 8j, 9c, 9e, 9g, and 9j. Later changes can silently invalidate the gate record.

### 7. G88 directly contradicts source — high runtime-policy cost

The evidence says `--models-max` is above planner concurrency, but the manifest omits it (`shell/modules/llamacpp.json:12-20`) and the test asserts it is absent (`shell/tests/test_router_no_unrequested_transition.py:10-11`). This is a direct dual-evictor-control gap, not merely weak documentation.

### 8. Closing gate claim overstates three gates — medium reporting cost

`docs/CP-M1-REPORT.md:160` says 9a through 9j are candidates. Keys 9a, 9b, and 9i do not exist; 9b has no evidence directory and 9a has only five preparatory files. This is a three-gate overstatement.

## Audit A — oracle verdict

| Predicate class | TRUE | FALSE | Total |
|---|---:|---:|---:|
| SUBSTANTIVE | 32 | 6 | 38 |
| STRUCTURAL | 17 | 3 | 20 |
| SELF-REFERENTIAL | 30 | 1 | 31 |
| TRIVIAL | 28 | 7 | 35 |
| **Total** | **107** | **17** | **124** |

Headline answer: **58 of the 107 TRUEs rest on trivial or self-referential predicates.** The full 124-row classification, deciding code quotation, and minimum satisfying artifact are in `A-oracle-classification.md`.

## Audit B/C — ledger verdict

- Candidate evidence hash recomputation: 8a–8j and the present 9-series gates (9c–9h and 9j) currently match; 7a has 6 drifts and 7b has 4. Exact hashes are in `B-gate-evidence.md`.
- No candidate gate is PASS. Historical PASS keys are 0,1,2,3,4,4b,4c,5b,6.
- Current gates 0–7b equal the saved snapshot as whole objects.
- Pre6 witnesses 0–5b and the pre-promotion gate-6 placeholder; pre7 witnesses the promoted gate 6. Neither contains 7a or 7b. Snapshot provenance explicitly calls 7a/7b self-attested (`ledger-snapshot-verified.json:21-24`).
- All 379 ledger evidence hashes are well-formed; no 63-character hash remains.

## Audit D/E — NOT_RUN and backfill verdict

The llama.cpp runtime is present: `current` is a CUDA-version junction, `llama-server.exe` exists, and `qwen3-8b.gguf` is 5,225,374,496 bytes. The false band was skipped under the no-launch instruction, not because the runtime was absent. G73 is TRUE, so “G70–G80 all NOT_RUN” is wrong.

All 58 one-timestamp backfills genuinely correspond to TRUE lines in `goalcheck-66.txt`. Only 9 use substantive predicates; 11 are structural; 19 self-referential; 19 trivial. The timestamp proves when they were backfilled, not when the behavior occurred.

## Audit F — envelope verdict

- Package A: 814/1850 mechanically; 810 excluding four runtime-state lines. Under aggregate and area caps, but materially underreported as 430.
- Package B: 279/1625. Aggregate passes; `llamacpp.json` area fails 53/45. Underreported as 156.
- No budget pooling found.
- Protected roots: Product Software clean; MMT clean against authorized handover; Sovereign Distillery clean; Sov 1 clean; Token Piggy Bank **two changes**.
- Distillery copy has the recorded 51-line `serve.py` addition and source/original trees are clean.
- Token copy has the recorded 14-add/2-remove `piggybank.py` hardening; original `piggybank.py` is unchanged, but the original launchers are not.
- Recorded delivered provider turns: zero across 298 scanned run artifacts.

## Recommendation on PASS promotion

**No candidate gate is presently safe to promote to PASS.** Minimum blocker map:

- 7a/7b: live hash drift and no independent witness.
- 8a–8c: E-7c mutable evidence; 8d: G26 live round-trip unproved; 8e: G28 absent; 8f: G34/G35 not run; 8g: G38/G41 fail; 8h: mutable evidence; 8i: mutable evidence plus protected Token drift; 8j: G57/G58 fail and linecount invalid.
- 9a/9b/9i: absent. 9c: G84 parity fails; 9d: G88 fails and G91 not run; 9e: mutable evidence; 9f: G102 fails; 9g: G108 fails/G109 partial; 9h: dependent closeout/envelope unresolved; 9j: G117/G118 not run, G120/G121 false, protected manifest false.

Promotion should wait for an independent replacement/repair of the weak oracle predicates, frozen gate-local evidence, a reconciled run log, corrected linecounts and per-area compliance, investigation/restoration or authorization of the Token original-tree changes, and rerun of the live acceptance legs under explicit operator authority.
