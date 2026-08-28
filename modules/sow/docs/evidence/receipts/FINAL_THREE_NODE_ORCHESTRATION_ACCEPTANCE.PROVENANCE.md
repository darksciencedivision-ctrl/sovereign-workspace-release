# Provenance classification — `FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json`

This sibling note classifies the existing JSON without changing it. The JSON is preserved
byte-for-byte at SHA-256
`E31F0C8A0D86032B6AC61B8DFF342E78F1BFC14C489FB4C118FC17250A8B1953`.

## Classification

The sibling JSON is an **operator-authored testimony/manual acceptance record**, not a
machine-emitted receipt. No producer for its declared
`final_three_node_orchestration_acceptance@1.0` schema exists in this repository. It does not carry
the machine-receipt provenance fields `check`, `source.commit`,
`source.tracked_product_tree_clean`, `started`, `finished`, or an Electron main PID.

The record is candid about its result: `PARTIAL_ACCEPTANCE`, live worker readiness blocked by
`AUTH_REQUIRED` and `USAGE_LIMIT`, collaboration not executed, mock legs present, an external
authentication window observed, and the full Python run not counted. Those statements remain useful
operator testimony. They must not be interpreted as measurements emitted by repository code.

Its tested source cannot be reconstructed. It names commit `a6dd83f70df2c6bf5ee4544ec80702c5adcb0a9b`
plus unspecified “uncommitted final-hardening changes,” with neither a tree hash nor a file list.
This note does not upgrade or regenerate any of those historical claims.

## Current machine-emitted evidence

Phase 19.8 added and ran the packaged `orchestration-collaboration` self-check. Its emitted receipt is
`PHASE19_8_ORCHESTRATION_COLLABORATION_SELFCHECK_19.8_20260814T233602Z.json`, sourced from committed
work `1d151e1fa48fdfbb164a2096014ed2281a06ab4f`, with a clean tracked product tree and an Electron
main PID. That run is explicitly mock-first (`legs: mock/mock`, `live_exchanges: 0`) and therefore
measures the governed orchestration/collaboration plumbing without claiming to replace the blocked
historical live-provider acceptance.

