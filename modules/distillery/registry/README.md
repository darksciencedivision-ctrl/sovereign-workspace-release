# Canonical registries

## Grounded students and trainer

`grounded/students.json` is the immutable-revision candidate inventory for HG-3.
`PINNED_FOR_HG3` means only that a base checkpoint is authorized for the bounded
architecture smoke; it is not a production selection, corpus-admission decision,
deployment, or promotion.

`grounded/trainer.json` is the credential-free machine and trainer-requirement
registry. It preserves the retired gfx906 planning target, records the measured
local development node, and leaves `GND-TRAINER-PRIMARY` unassigned until a real
machine satisfies the capability contract. Historical expectations are never
copied into measured fields.

## Source admission

`source_admission_candidates.json` is the D-9 classification inventory. Local Ollama manifests now provide exact digests and model blobs for three candidates, but entries remain intentionally `UNKNOWN` until output-use evidence, intended use, and an authorized operator decision are recorded as immutable admission events.

Telemetry collection is permitted to retain privacy-minimized hashes and measurements while classification is pending. Curation, synthesis seeding, and training call `assert_admitted` and fail closed.
