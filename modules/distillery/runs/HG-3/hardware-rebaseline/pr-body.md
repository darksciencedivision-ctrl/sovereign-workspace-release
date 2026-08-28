# Hardware reality rebaseline before HG-3

## Summary

- preserves the eight unpushed post-merge remediation/evidence commits without rewrite;
- preserves RC3 source commit `a332e68823ab426310c5d37f3c0bfed5c52cc1f0` in its verified complete Git bundle;
- retires `GND-TRAINER-GFX906` as an unverified planning target while retaining `TARGET_NOT_FOUND` history;
- registers measured local node `GND-DEV-EXEC-01` as non-gating development hardware;
- creates unassigned, vendor-neutral `GND-TRAINER-PRIMARY` with 24 GiB provisional minimum and at least 32 GiB preferred;
- reclassifies the gfx906/ROCm stack as historical and keeps canonical HG-3 on FP16 LoRA;
- updates only thesis v1.2/current status; frozen v1.1 is unchanged;
- records D-HW-01 and changes HG-3 to `BLOCKED_HARDWARE_CAPACITY`.

## Branch and base

- head: `remediation/hardware-rebaseline-pre-hg3`
- proposed base: `main`
- proposed commit range: `44f69077f0d674bd7bef5730c2fe41a685e64b03..remediation/hardware-rebaseline-pre-hg3`

## Boundaries

- no model weights, adapters, optimizer state, model cache, private runtime content, credentials, or client data;
- no repository-wide license change;
- D-9 remains 4/4 `UNKNOWN` and fail closed;
- no HG-3 compute, full training, G2-G6, deployment, or promotion;
- no automatic merge requested.

## Validation

Full Windows/Linux tests, compilation, JSON/schema, Markdown links, package build,
diff checks, ancestry, RC3 bundle, secret/private-runtime, weight, oversized-artifact,
license, and G2-G6 scans are required before publication.

This file prepares review content only. No push or PR creation is authorized by the
hardware rebaseline directive.
