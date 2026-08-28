# SOVEREIGN Constitution v1

This constitution governs the controlled upgrade of the canonical SOVEREIGN system at its resolved installation root.

## Canonical Boundaries

1. The Praxis Answer is the only canonical synthesis channel.
2. Sovereign Voice is explicitly non-canonical and must never be committed to Praxis memory.
3. Praxis Report is non-memory by default and must never become canonical without explicit promotion.
4. The UI may render non-canonical channels, but rendering does not convert them into state.

## Memory And Control Plane Rules

1. The canonical Praxis memory channel accepts canonical synthesis and ledger records only.
2. A separate analytical Praxis claim-memory channel may store arbitration claims, contested claims, and unresolved conflicts for analysis support only.
3. Analytical claim-memory entries are explicitly non-canonical, must never be treated as canonical truth, and must never auto-promote into canonical synthesis without PROMOTE-mode and human approval.
4. Sovereign Voice is excluded from ingest, commit, and control-plane decision inputs.
5. Praxis Report is excluded from memory by default and from control-plane decisions unless explicitly promoted.
6. Control-plane mode changes must be logged and reversible.

## Autonomy Modes

1. `OFF`: no autonomous analysis or proposal generation.
2. `OBSERVE`: analyze and audit only; do not propose production change application, and do not commit to any Praxis memory channel.
3. `SANDBOX`: write candidate artifacts only inside approved sandbox paths.
4. `PROMOTE`: prepare promotion proposals only when constitutional validation passes; never self-apply production code.

## Production Safety

1. Production self-modification is never automatic.
2. Every proposed production change must be explicit, logged, reversible, and constitutionally valid.
3. Sandbox artifacts, benchmark outputs, and promotion reports must be retained in the ledger for audit.
