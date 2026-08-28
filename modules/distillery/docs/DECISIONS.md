# Integration decisions

Status: integration candidate, 2026-08-20. These decisions do not promote or deploy an artifact.

| ID | Decision | Status |
|---|---|---|
| INT-1 | `ryguy-pixel/Sovereign-Distillery` is the joint treaty owner and canonical integration destination. | CONFIRMED |
| INT-2 | RC3 commit `a332e68823ab426310c5d37f3c0bfed5c52cc1f0` remains an immutable candidate source; its Git bundle and mapping are retained. | CONFIRMED |
| INT-3 | Shared validators, schema, provenance, exclusion, gates, evidence, and source admission have one canonical implementation under joint top-level packages. | CONFIRMED |
| INT-4 | Grounded mining, telemetry, harness adapters, and CLI remain Grounded-specific. | CONFIRMED |
| INT-5 | Existing treaty documents are amended surgically; Sovereign phase/OQ/DR semantics are not replaced by Grounded G/HG/SL/E/D identifiers. | CONFIRMED |
| INT-6 | No license is inferred from the RC3 package declaration. Repository licensing remains unresolved and all rights remain with their owners absent an explicit grant. | OPEN — OWNER |
| D-9 | Provider/model/revision source admission is fail-closed. `UNKNOWN` evidence can be measured in privacy-minimized G0 telemetry but cannot enter curation or training. | OPEN — OWNER |
| [D-HW-01](decisions/D-HW-01-grounded-primary-trainer-reality-rebaseline.md) | The unverified gfx906 planning target is retired; the local RTX 5060 Ti remains a non-gating development node; the primary trainer is capability-defined and unassigned. | ACCEPTED — OPERATOR |

## Integration boundary

The active Sovereign product runtime is a separate, dirty working tree and was inspected read-only. The joint repository consumes its existing immutable turn-evidence format through an adapter. It does not replace or duplicate the runtime's response capture, provenance stamps, evaluation engine, or publication gates.

No G2, G3, or G4 training action is authorized by this integration.
