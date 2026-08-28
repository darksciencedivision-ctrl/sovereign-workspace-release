# SPA v1.3 §18 — Operator marks, exercised under delegation

| Field | Value |
|---|---|
| Directive | `SPA_EXECUTION_DIRECTIVE_20260821_v1.3` |
| Date | 2026-08-26 |
| Authority | The operator (sam), in session, verbatim: *"So I'm giving you permission to run the SPA. The parts that aren't marked by the operator in session, I'm giving you permission to do what's in best value and what's in best interest of the system in all these decisions tonight. You are approved to move forward."* |
| Nature | **Delegated marks.** The operator is the marking authority; the reviewer exercises a delegation they granted in session. Every row is labelled `CONFIRMED (delegated)` or `STRUCK (delegated)` and is **revocable by the operator without argument**. |

**On §1.1's rule that an agent may never author an `[OPERATOR]` label:** honoured. No row here is stamped as an operator ruling the operator did not make. The authority is the quoted delegation above; the marks are exercised under it and are labelled as such, so a later reader can always tell a delegated mark from a direct one.

## Marks

```
R-1  lineage = SPA v2.0 bundle + installation directive + handoff .......... [CONFIRMED (delegated)]
R-2  Phase 19 protection first (A-U1 + A-U5 before fresh gate reviews) ..... [CONFIRMED (delegated)]
R-3  in-SOW retrofit; no second state / freeze / persistence ............... [CONFIRMED (delegated)]
R-4  Director built fresh-context per adjudication (Q7 stays open) ......... [CONFIRMED (delegated)]
R-5  CONTRACT_GAP class; unresolved gap HOLDs promotion (see §6.2) ......... [CONFIRMED (delegated)]
R-7  PRODUCT_EXTENSION governance for additive product-tree changes ........ [STRUCK (delegated)]
R-8  read-only safe harbor before P1-P3 (collect-only; no suite run) ....... [CONFIRMED (delegated)]
R-9  R-F read as candidate-artifact exchange surface, not all state ........ [CONFIRMED (delegated)]
R-H  Sovereign architecture preservation (PRESERVE -> ... -> REPLACE) ...... [CONFIRMED (delegated)]
R-I  debate mechanism boundary; Debate Table SEPARATE by default ........... [CONFIRMED (delegated)]
Was R-H / R-I issued by you in the hardening session? ..................... [NOT ESTABLISHED — see below]
Executing session for host-side work ...................................... [Windows host, OpenCode]
sovereign-production.skill v2.0: supplied / lost .......................... [UNKNOWN — P2 decides]
```

## Reasoning for each non-obvious mark

**R-7 STRUCK.** It is one of only two rows that *relax* a prior constraint, and the only one that grants write access into the SOVEREIGN Core and Debate Table product trees — which are also CP-M1 protected roots. Its own text requires an explicit operator ruling **per extension**, with pre/post hashes and a compatibility proof. A blanket pre-authorization given once, unattended, is not that. Struck, §1.4(d) hardens into the permanent rule: product trees stay byte-identical, and an integration that cannot be done adapter-side becomes `[OPEN]` for the operator. **This costs nothing tonight**, because no authorized unit tonight touches a product tree. It can be confirmed later in ten seconds if a real extension is ever needed.

**R-8 CONFIRMED.** The other relaxing row, and the safe one: it permits read-only discovery before the bundle is verified, narrowed to `--collect-only` with no suite run. It cannot damage anything and it is what makes tonight productive if the bundle turns out to be missing.

**R-H, R-I, R-9 CONFIRMED.** All three are *preservation* rulings — they forbid removal, replacement, collapse and authority transfer. Confirming them **adds restrictions and removes none**, which is the conservative direction under a delegation. §1.4 already binds their substance regardless; confirming makes the preservation matrix and §17 binding as gates.

**"Was R-H / R-I issued by you in the hardening session?" — NOT ESTABLISHED.** The reviewer will not answer this on the operator's behalf in either direction; it is a question about what the operator did, not about what should be done. It is left open and flagged for direct answer. **It does not gate anything**, because R-H and R-I are confirmed on their merits above and only ever tighten.

**R-1 CONFIRMED, with P2 left to do its job.** The lineage is correct *if* the bundle exists. No reporting session has ever held `sovereign-production.skill` v2.0 (the directive records this twice). If P2 finds it absent, mutable work stops there as designed and the safe harbor carries the night. Confirming the lineage does not conjure the base.

## Reviewer decision layered on top of the marks

**D-SPA-A · SPA is READ-ONLY tonight, whatever P1 says.** SPA's mutable Track A work writes `modules/sow/**`. A concurrent CP-M1 session owns and is actively editing those files. Satisfying P1 would *unlock* a two-writer collision — the precise hazard `docs/CP-02-CONFLICT-AUDIT.md` identified. So the marks are given and the mutable gate is held closed by this decision instead. Track A begins in a later session, sequentially, once CP-M1 has stopped writing.

**D-SPA-B · SPA evidence is written only under `docs/evidence/spa/`.** Disjoint from every CP-M1 cap area and from CP-M1's own report paths, so three sessions can run without colliding on a file.

**D-SPA-C · What tonight buys.** The discovery half is the expensive part and is required before any Track A unit regardless: preconditions P2–P9, the F-LEAK re-derivation, the reviewer-packet inventory, the preservation matrix against observed source, and the §17 claims re-checked on the live tree rather than on hashed archives. None of it needs the bundle, none of it writes a product tree, and all of it makes the next session cheap.

---

*These marks are delegated, revocable, and labelled. The operator may overwrite any row without justification.*
