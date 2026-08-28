# utc: 2026-08-21T04:33:22.3059758Z
# producer: claude-code REM-01

# STOP REPORT — REM-01

**Reason code: `PRECONDITION_UNSIGNED`**

Stage reached: R1, item 0. `docs/CLAUDE-CODE-DIRECTIVE-REM-01.md` §1 was executed as the first
action after reading §0. All four conditions fail. No R1 work item was started.

This report supersedes an earlier copy written at `2026-08-21T04:30:01.7102581Z` in a prior
session. Same reason code, re-verified against the file as it stands now; restructured to the
§6 required contents (reason code / observations / what was not done / operator options).
Rewritten rather than edited because the §6 structure changes every section.

---

## 1. What was observed

Commands run verbatim from §1, from `D:\Product Software\Production Workspace`:

FACT[docs/DECISIONS.md] `Get-FileHash -Algorithm SHA256`:

```
BB911905C68B85F2C8ABD5D3D2DB8176CBD7A6999F8ED93FD815B4185C14869A
```

Lowercased, that is `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a` — bit-for-bit
the value §1 nominates as the VOID builder-authored artifact.

FACT[docs/DECISIONS.md] `grep -c VOID` returns `0`. The required VOID sentence is absent in both
the bold and unbold forms.

FACT[docs/DECISIONS.md] `grep -n -E "\[x\]|\[X\]|Signed:|UTC:"` returns zero matches. There is no
checked box in `[x]` form anywhere (the file's Gate 0 line uses a `☑ yes` glyph), no `Signed:`
line, and no `UTC:` line.

FACT[docs/DECISIONS.md] The sections `§6.1` and `Builder continuation` do not exist in the file at
all. Its sections are: Gate 0, Gate 1, §6, SOVEREIGN dependency lock, SOW live tree HEAD,
SOVEREIGN and Debate live trees, Distillery snapshot selection.

FACT[docs/DECISIONS.md] Line 2 is an `# Operator:` header naming the operator, followed by
`# Date: 2026-08-21`. The operator's name is not reproduced here: §0.1(1) bars this builder from
writing that string, and a reviewer grepping for it should get no hit outside the file being
described. The body asserts operator positions in the third person ("The operator pre-authorizes…",
"The operator states…").
Last write time `2026-08-20 22:07` local — unchanged since the prior session's check.

| §1 condition | Required | Observed | Result |
|---|---|---|---|
| 1 | VOID sentence present | absent | **FAIL** |
| 2 | hash is not `bb911905…` | hash is exactly `bb911905…` | **FAIL** |
| 3 | Gate 0, Gate 1, §6, §6.1, Builder continuation each `[x]` + non-blank `Signed:` + `UTC:` | 0 of 5 qualify; 2 of 5 do not exist | **FAIL** |
| 4 | Builder continuation checked `yes` | section does not exist | **FAIL** |

INTERPRETATION: this is the exact condition §1 was written to detect. `docs/DECISIONS.md` is the
prior builder's own file. Under §0.1(1) I may not create, edit, or delete it, and under §0.1(6) I
may not treat its presence, its confident tone, or the presence of this directive as authorization.

STRUCTURE ONLY: per §1's parenthetical, I verify structure, not identity. Even had the five
sections been checked and signed, I could not attest that the signer is the operator. Nothing in
this report claims otherwise.

FACT[docs/DECISIONS-OPERATOR-TEMPLATE.md] The unsigned operator template exists in the same
directory. Every field is `____`; all five checkboxes are `[ ]`; it carries the VOID sentence
verbatim. It is the artifact §1 expects the signed `docs/DECISIONS.md` to be derived from.

## 2. Corroborating state — read only, not acted on

FACT[evidence/GATE-LEDGER.json] Gates 0, 1, 2, 3, 4 all carry `"status": "PASS"`. §0.1(2) permits
a builder only `CANDIDATE`, `NOT_REACHED`, or `STOP`. These are the prior builder's values and are
what R1-2 / R2-8 / R3-13 exist to replace. Left untouched.

FACT[evidence/GATE-LEDGER.json] Two `evidence_sha256` entries read `not hashed`; three are
truncated to 8 hex characters — both prohibited by §2.

FACT[evidence/phase2-install.txt] Records `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a`
as "DECISIONS.md SHA-256 (captured BEFORE any mutating command)". The install phase was therefore
gated on the void file. The `## RE-AUTHORIZATION (REM-01)` block required by R1-1 is absent.

FACT[docs] No `docs/REM-01-STAGE-R1-REPORT.md`, `-R2-`, or `-R3-` exists. REM-01 has never
progressed past §1 in any session.

FACT[docs] `docs/ADR-005-sow-install-and-electron-provisioning.md` does not exist; ADR-001 through
ADR-004 are present. ADR-005 is R2-1 work and is correctly absent at this point.

## 3. What I did not do

- Did not create, edit, complete, or delete `docs/DECISIONS.md`, and did not copy the operator
  template into it. §0.1(1), and §1's "You are not permitted to 'fix' a failing precondition."
- Did not write the string naming the operator into any author, signer, or approver field.
- Did not touch `evidence/GATE-LEDGER.json`. The five `PASS` values remain as the prior builder
  left them; correcting them is R1-2, which is not authorized to begin.
- Did not append the R1-1 re-authorization block to `evidence/phase2-install.txt` — it requires
  the operator-signed hash as its payload, which does not exist.
- Did not start any R2 or R3 item: no ADR-005, no `shell/tools/install_sow.py`, no deletion of
  `modules/debate/SOW_REVIEW_ROUND2_RAW/`, no provenance edits, no manifest or git re-capture,
  no README rewrite, no test or fixture files, no `shell/src` changes.
- Did not read or execute anything under `D:\multi model terminal app\` or `D:\Sovereign Distillery\`
  in this session.
- Did not run any module, selfcheck, or npm command; did not run any git command.

The only file this session created or modified is this report.

## 4. Options for the operator

**Option A — sign the template. Unblocks REM-01 as written.**
Open `docs/DECISIONS-OPERATOR-TEMPLATE.md` and fill it yourself: every `____`, including the host
clock check; `[x]` plus a typed name and a UTC value on each of Gate 0, Gate 1, §6, §6.1, and
Builder continuation; confirm or correct the three facts the prior builder asserted on your behalf;
keep the VOID sentence naming `bb911905c68b85f2c8abd5d3d2db8176cbd7a6999f8ed93fd815b4185c14869a`
verbatim; delete the template's "Delete this line when done" instruction line. Save the result over
`docs/DECISIONS.md`. Its hash will then differ from `bb911905…`, satisfying condition 2, while the
retained VOID sentence satisfies condition 1. Then open a session and say `continue R1`.
Cost: a few minutes. Risk: none. This is the path the directive assumes.

**Option B — sign at a different path and amend §1.**
If you want `docs/DECISIONS.md` preserved as a historical record of what the prior builder asserted,
sign to a new path (e.g. `docs/DECISIONS-SIGNED.md`) and amend §1 to hash that path. The amendment
must also drop or restate condition 2, which is phrased against the void file's own path.
Cost: a directive edit. Risk: two decision files on disk invites the reviewer to read the wrong one.

**Option C — hold REM-01; leave the review findings unactioned.**
Leave the workspace exactly as it stands. `evidence/GATE-LEDGER.json` continues to assert five
builder-written `PASS` values that §0.1(2) forbids, and the `docs/REVIEW-BUILD-01.md` findings stay
open.
Cost: none now. Risk: the ledger currently reads as though Gates 0–4 were adjudicated, which no
reviewer has done.

RECOMMENDATION: Option A. It is the only path that satisfies §1 as written without editing the
directive, and it is the one action in this workspace that a builder is structurally barred from
performing on your behalf.

## 5. Note on the §1 timestamp command

FACT[host] The amended §1/§2 form `(Get-Date).ToUniversalTime().ToString("o")` executes correctly
here and produced the header of this file. The earlier `Get-Date -AsUTC -Format o` form fails on
this host — Windows PowerShell 5.1 has no `-AsUTC` parameter. No action needed; recorded so the
reviewer can reconcile the two forms across sessions.

ASSUMPTION: `docs/CLAUDE-CODE-DIRECTIVE-REM-01.md` on disk still carries the older `-AsUTC` form in
§1 and §2, while the directive text pasted into this session carries the amended form. I treated
the pasted text as authoritative for command syntax and the on-disk file as authoritative for
everything else. The two agree on all four precondition conditions, so the choice does not affect
the outcome.

---

BUILDER CLAIM: Gate 0 is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.
