# schemas/ — @1.0 (FROZEN at Phase 0) + recorded successors

Single source of truth for the governed objects its files GROUND — the twelve frozen `@1.0`
schemas plus recorded successors, each with its Grounding row below. JSON Schema draft-07. Frozen
at Phase 0 (2026-07-16); any change after the operator signs the freeze manifest requires a new
schema version (@1.1+), a decision-register entry, and a recorded hash change.

**That path has been walked exactly once.** `node.schema@1.1.json` (OP-12.1, operator, 2026-08-01;
`AUTONOMOUS_BUILD_DIRECTIVE.md` §17.1) resolves U227 by adding the two OP-12 frontier provider ids
`grok_build` / `google_antigravity` and the pre-existing local id `ollama_local` (U254) to the
`adapter` enum. It is **additive**: the twelve frozen `@1.0` files are untouched, so
`freeze_integrity_sha256` and the operator's signature are unchanged, and the successor is recorded
in the manifest's separate, separately-hashed `schema_amendments` block — drift-checked as hard as
the frozen set, and required to name its authorizing ruling. Draft-07 cannot express "`@1.0` with a
wider enum" (`$ref`/`allOf` only narrow), so the successor is a standalone copy; the five
authorized deltas are pinned by `tests/unit/test_node_schema_amendment.py`, which fails on any
sixth. `node@1.0#/definitions` remains the canonical home of `capability_descriptor` and
`deployment_profile` — the successor copies them and re-points nothing.

| Schema | $id | Grounding |
|---|---|---|
| project | https://sovereign.local/schemas/project@1.0 | invariants 5/14 |
| node | https://sovereign.local/schemas/node@1.0 | Plan §9.1 |
| task | https://sovereign.local/schemas/task@1.0 | Plan §9.3 |
| message | https://sovereign.local/schemas/message@1.0 | Plan §9.2 (TB-2) |
| artifact | https://sovereign.local/schemas/artifact@1.0 | Plan §4.5, §9.3 |
| memory | https://sovereign.local/schemas/memory@1.0 | Plan §9.4; handoff §2.10.3 |
| evidence | https://sovereign.local/schemas/evidence@1.0 | Plan §19.2 |
| debate | https://sovereign.local/schemas/debate@1.0 | Plan §19.2 (I-DS1) |
| gate | https://sovereign.local/schemas/gate@1.0 | Plan §9.3 |
| permission | https://sovereign.local/schemas/permission@1.0 | Plan §9.8, §4.8 (invariant 29) |
| usage | https://sovereign.local/schemas/usage@1.0 | Plan §13.1 |
| checkpoint | https://sovereign.local/schemas/checkpoint@1.0 | Plan §9.11, §19.1 (I-CS1) |

Shared definitions (cross-referenced via `https://sovereign.local/schemas/` URIs — a resolver-friendly namespace; no network fetch occurs, the schema registry/store supplies them. The runtime MCP **resource** namespace `sovereign://…` (Plan §9.5) is a separate protocol concern and is unchanged, resolved by the test
resolver and later by the control plane's schema registry):

- `capability_descriptor` and `deployment_profile` live in **node@1.0** `#/definitions`
  (Plan §9.7, §9.10) and are referenced by task@1.0, debate@1.0, project@1.0.
- `provenance` and `conflict_record` live in **memory@1.0** `#/definitions` (Plan §9.6).
- `current_conductor` lives in **checkpoint@1.0** `#/definitions` (handoff §2.14.1).

Rationale: the Buildout Directive fixes exactly twelve schema files; shared definitions are
placed in the schema that owns their lifecycle rather than duplicated (duplication = drift
risk at @1.1).

## What schemas/ does NOT govern — the operational record family (W-60 / U414)

Stated here because this file once opened with "single source of truth for EVERY governed
object", and one governed family pins NO schema at all. The OPERATIONAL RECORD FAMILY — the
operational tasks, messages, and debates that `mcp_server/collaboration_service.py` writes
through `persistence/store.py`'s `operational_*` tables (`mutate_operational_task` /
`mutate_operational_debate` / the creators) — is UNSCHEMATIZED, deliberately, and this section
is the written retraction of the universal sentence above.

**Why the frozen schemas cannot describe it.** The twelve files ground OTHER record families.
`debate@1.0` (Plan §19.2, I-DS1) requires `debate_id` + `request` — caller_node, topic,
participants as CAPABILITY DESCRIPTORS, max_rounds, budget — and closes with an outcome enum
`CONVERGED` / `DISSENT_PRESERVED` / `BUDGET_EXHAUSTED` / `CUT_OFF`. The operational debate record
carries `state` `OPEN` / `CLOSED` / `ABORTED`, `turns`, `participant_node_ids`, `proposition` —
the state vocabulary and the outcome enum are disjoint, and the frozen required key `request` does
not exist on the operational row. `task@1.0` and `message@1.0` describe the Plan §9.x shapes the
same way, not the operational task with its `candidates` / `synthesis` / `progress`.
`tests/unit/test_operational_schema_scope.py` pins the debate half of that mismatch BEHAVIOURALLY,
so a reconciliation is a visible act, not a silent drift. The vocabulary overlap between `ABORTED`
and `CUT_OFF` is recorded as U414.

**What governs the family instead.** The service's hand-written shape checks (required fields,
non-empty string lists, CANDIDATE status), the `TASK_STATES` / `MESSAGE_KINDS` vocabularies
validated against on every write, the fenced transition legality (`_assert_legal_transition`,
checked inside the write fence), the referential checks (a candidate names only messages and
debates that exist), and the tool-layer `inputSchema` enforcement (`validate_tool_arguments`).
Legality at the transition, authority delegated to `control_plane.policy` — shape governance
without a schema file.

**How this changes.** Only the way every frozen thing here changes: a SUCCESSOR-SCHEMA ruling
(the OP-12.1 pattern walked once, above) authorizing an operational-family schema beside the
untouched freeze. A new `schemas/*.schema.json` is picked up by the manifest's frozen glob, moves
`freeze_integrity_sha256`, and resets the operator's signature to PENDING — so authoring one is an
operator act, never a worker's improvisation. Until such a ruling, this section IS the record:
the operational family is governed, but not by anything in this directory.
