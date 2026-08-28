# Open Questions Register - F-19 Reconciliation Appendix

Machine-readable determinations: `runs/completion-loop/F19_OPEN_QUESTION_RECONCILIATION.json`.

Identifier policy: canonical numbering per `docs/sovereign/DECISIONS-v1.md` section 3 crosswalk; register-local IDs preserved (SR-3 collision documented, not merged). The canonical register `docs/sovereign/OPEN_QUESTIONS.md` is a frozen canon import whose bytes are hash-pinned by `docs/integration/SOVEREIGN_CANON_IMPORT_MAP.md`; this appendix therefore lives beside it rather than inside it. No historical register text was modified or deleted.

| ID | Determination | Authority |
|---|---|---|
| OQ-001 seed path | STILL_OPEN (narrowed in principle to bootstrap+native; exact seed unacquired) | STATUS D.3; DR-2 outstanding |
| OQ-002 teacher inventory | RESOLVED_BY_DECISION (resolved by executed measurement; evidence class stated honestly) | registry/sovereign/teachers.json |
| OQ-003 v1 acceptance | RESOLVED_BY_DECISION | DECISIONS-v1 section 2 (Route A / Route B) |
| OQ-004 M/T/D margins | DEFERRED_EMPIRICAL | requires measured variance on an evaluation suite that does not yet exist |
| OQ-005 mixing ratios | STILL_OPEN | operator method call; no accepted ruling located |
| OQ-006 compute envelope | STILL_OPEN (narrowed by D-HW-01 current-trainer rebaseline: primary trainer UNASSIGNED >=24 GiB usable VRAM) | docs/decisions/D-HW-01 |
| OQ-007 distribution intent | STILL_OPEN | operator-only |
| OQ-008 native architecture timing | DEFERRED_EMPIRICAL | ADR-0003 |
| OQ-009 sibling contracts | STILL_OPEN | sibling repositories never inspected (B-10) |
| Register-local ordering rationale | SUPERSEDED -> HYP-1 explicit testable hypothesis | STATUS D.3 row OQ-010 |

Summary: 5 STILL_OPEN, 2 RESOLVED_BY_DECISION, 2 DEFERRED_EMPIRICAL, 1 SUPERSEDED.
Every item marked STILL_OPEN genuinely remains unresolved.
