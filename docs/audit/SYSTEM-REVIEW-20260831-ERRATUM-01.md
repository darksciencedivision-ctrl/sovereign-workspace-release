# utc: 2026-09-01T05:50:00Z
# producer: claude-code B-1/B-2 execution

# Erratum 01 to SYSTEM-REVIEW-20260831 — F-5 was wrong, F-3 is declined

**What this document is.** A builder correction to `docs/audit/SYSTEM-REVIEW-20260831.md`. Evidence
is append-only (AGENTS.md §10), so the review is preserved and this supersedes two of its items
rather than editing them out. No gate status is asserted; `evidence/GATE-LEDGER.json` is untouched.

**How it was found.** By trying to act on both items. Punch list V8 listed F-3 as B-1 and F-4/F-5
as B-2, described as "ready, cheap, no decisions left in them". Neither survived contact with the
tree.

---

## F-5 is WITHDRAWN — `canonical_registry.py` is not dead code

The review said:

> `modules/sow/control_plane/canonical_registry.py`, 169 lines, 53 models × 18 fields, **zero
> references anywhere in the tree**, no `__main__`.

That is false. It has four consumers:

```
shell/tests/test_incompatible_selection_refused.py   from control_plane.canonical_registry import refuse_incompatible, IncompatibleSelection
shell/tests/test_legacy_alias_resolution.py          from control_plane.canonical_registry import dump_registry
shell/tests/test_promotion_axis_orthogonal.py        from control_plane.canonical_registry import dump_registry
```

Deleting it fails four tests. Measured, then reverted.

**Why the original measurement was wrong, stated precisely rather than as "an oversight".** The
orphan sweep ran `git ls-files .` from inside `modules/sow`, so its corpus was that module alone.
It never saw `shell/`. The conclusion drawn from it — "referenced by nothing else in **the tree**"
— is a whole-tree claim built on a one-module scan.

That is the same defect this review criticised in the independent PDF it corrected: a scope limit
that was true of the method and did not survive into the sentence. It is recorded here in those
terms because the review has no standing to hold others to a rule it broke itself.

The PDF's B-16 ("canonical_registry.py has zero consumers") is likewise not confirmed by this
tree, and the review's endorsement of it is withdrawn with F-5.

---

## F-4 is WITHDRAWN — the backups are preserved records, not clutter

The review called the 13 tracked `*.pre-CONVERGE01` / `*.pre-rebase` / `*.pre-add08` files a
"stale-read hazard" worth deleting. They are load-bearing in two ways it did not check:

1. **`RELEASE-MANIFEST.json` hashes four of them** under `batch_files`, so deleting them fails
   `release_manifest_check` by construction.
2. **The manifest's own prose declares them a preservation decision**: *"Prior
   RELEASE-MANIFEST.json preserved as RELEASE-MANIFEST.json.pre-CONVERGE01."*

That is AGENTS.md §10's append-only evidence rule working exactly as written — a superseded
artifact is preserved, not deleted. Removing them would undo a recorded decision, which the review
had no authority to propose and this builder had none to execute.

Measured: deleting all 14 files failed 6 tests across `shell/tests` and `tools/release`.

**What survives of F-4.** The narrow observation that every backup DIFFERS from its live
counterpart, and that nothing on disk marks them as superseded records rather than alternates. If
that is worth addressing, the fix is a marker or a README line, not a delete.

---

## F-3 is DECLINED on measurement — a generic path pattern is the wrong rule

The review proposed widening `shell/tests/test_developer_identifiers_are_bounded.py` beyond its
five host-scoped patterns, so it would catch a build-host path from any machine. Three candidate
rules were measured against the distribution:

| candidate rule | files it would newly flag |
|---|---|
| any drive-letter absolute path | 89 |
| non-system drive only (not `C:`) | 63 |
| the operator's three other project trees | 44 |

Nearly all are legitimate: `C:\Windows`, `C:\Program Files`, the **documented** install root
`C:\SovereignWorkspace` in `docs/INSTALL.md` and `docs/OPERATIONS.md`, and test fixtures.

**Why no threshold helps.** This workspace documents its own provenance. Every
`INSTALL-PROVENANCE.json` records the source path, and the guard's own disclosed list already
carries the category for it — *"provenance: the path IS the record."* SOW's receipts record where
the build ran; Distillery's run records record where its gates ran. Those paths are the content.
"An absolute path" is therefore not the signal, at any width.

A guard needing a 44-entry exemption list is the wrong guard. That is the conclusion F-2 reached
about the `runs` component rule, reached again here, and acted on the same way: the rule is not
added.

**What F-3 got wrong about the guard.** It is named `DeveloperIdentifiersAreBounded`. *Bounded*
means an enumerated, disclosed set — that is the design, not a shortfall. The review treated a
deliberate boundary as a gap.

---

## What stands from the review, unchanged

F-1 (SOVEREIGN at 0.76% coverage) — acted on in `057204b`. F-2 (the quarantine lane over shipped
bytes) — acted on in `c903ae4`, and it found four undeclared credential fixtures. F-6 (the silent
excepts, explicitly kept off any punch list), F-7 (the 131072 vs 20480 divergence) and F-8 (the
clean-room gap the builder cannot close) are unaffected.

Two of eight findings withdrawn, one declined. The three that mattered held.

---

BUILDER CLAIM: No gate is submitted for reviewer evaluation. No PASS status is asserted by the builder.
