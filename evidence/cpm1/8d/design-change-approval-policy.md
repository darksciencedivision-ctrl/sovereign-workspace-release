# Design change under ADDENDUM-01 §6 — Conductor approval policy remap

# utc: 2026-08-26T01:09:57.315Z
# producer: ox-alpha CP-M1 Band 4 / G26 remap authorization

| Field | Value |
|---|---|
| Removed value | `untrusted` |
| New value | `never` |
| Authorization | Operator instruction logged verbatim in evidence/OPERATOR-INSTRUCTIONS.log at entry utc 2026-08-26T01:09:21Z |
| Containment boundary unchanged | Yes — --sandbox read-only + --cd workspace scoping remain pinned (T2 containment); the sandbox+directory scope IS the containment boundary per build_interactive_codex_command docstring and the operator's rationale on record. |

## Rationale (operator's own words, on record)

build_interactive_codex_command already pins --sandbox read-only together with --cd workspace
scoping... THE CONTAINMENT BOUNDARY IN THIS DESIGN IS THE SANDBOX AND THE DIRECTORY SCOPE,
NOT THE APPROVAL POLICY. Under read-only, an approval prompt can only ever fire on an action
the sandbox already refuses, so `never` removes a prompt that has nothing left to gate.

## Eight pin sites carried in this pass

1. modules/sow/adapters/conductor/provider_commands.py — _codex_command emission
2. modules/sow/apps/desktop/conductor/launch-source.js :133 — boundary JSON b.approval_policy
3. modules/sow/apps/desktop/conductor/launch-source.js :137 — argv assertion
4. modules/sow/tests/unit/test_frontier_provider_recon.py
5. modules/sow/tests/unit/test_op12_frontier_adapters.py
6. modules/sow/tests/unit/test_provider_agnostic_conductor.py
7. modules/sow/tests/unit/test_provider_document_shape.py
8. modules/sow/tests/unit/test_side_effect_identity_fence.py

## Unchanged by explicit operator instruction

- automatic_approval stays **false** (never-ask is not auto-approve)
- --sandbox stays **read-only**
- --cd workspace scoping stays
- model ref stays **gpt-5.6-sol**

Semantic tests asserting 'approvals are not automatic' or 'escalation is refused' pass
unchanged because `never` still satisfies those properties.
