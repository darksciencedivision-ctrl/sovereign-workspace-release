# ADR-006 — The product emits nothing

**Status:** Accepted · **Date:** 2026-08-30 · **Context:** EPC-01 P4-7
**Supersedes:** nothing · **Superseded by:** nothing

## Context

Punch List V7 recorded P4-7 as a gap: *"Crash reporting / telemetry — none, and no opt-in
framework to add one defensibly."* That framing treats absence as something to be filled.

Every comparable product ships some form of outbound signal — analytics, crash reporting, an
update check, a licence heartbeat. Each is defensible on its own terms, and each is a channel
out of the operator's machine.

## Decision

**Sovereign Workspace transmits nothing about itself, and no framework is added to make
transmitting easy later.**

Specifically, and permanently unless this ADR is superseded:

- no analytics or usage measurement
- no crash or error reporting
- no update or version check
- no licence or entitlement heartbeat
- no opt-in toggle for any of the above

The product's only outbound network traffic is what the operator's own work requires: calls
to the local Ollama daemon on loopback, and calls to frontier provider CLIs that the operator
has explicitly authorized through the live-operation gate.

## Rationale

**The name is the argument.** A product called Sovereign, whose stated purpose is local
orchestration under an operator's final authority, cannot coherently report on that operator
to its vendor. Adding telemetry would not be a feature trade-off; it would contradict the
thing being built.

**An opt-in framework is not a neutral capability.** Building the channel and defaulting it
off still ships the channel. It becomes a dependency, an attack surface, and a decision that
any future maintainer can reverse with a one-line default change. Not building it is the only
version of "off" that cannot be flipped by accident.

**The threat model already assumes the machine is the boundary.** The product is
single-operator and loopback-only (`docs/LIMITATIONS.md`). A component that originates
outbound connections on its own initiative is precisely the thing that model excludes.

**We are not the ones who need the data.** Telemetry serves the vendor. An operator running
a local, sovereign workspace can read their own logs, and `docs/OPERATIONS.md` is where that
capability belongs.

## Consequences

**Accepted, and stated plainly rather than minimised:**

- When the product breaks in the field, **nobody finds out unless the operator says so.**
  There is no crash volume, no error trend, no adoption signal.
- Field diagnosis depends entirely on what local logging captures. That raises the bar on
  observability (P4-6): the logs have to be good, because they are all there is.
- There is no automatic notification of a security fix. Update discovery is the operator's,
  and the support policy has to say so — see `docs/SUPPORT-POLICY.md`.

**Rejected alternatives:**

- *Opt-in telemetry, default off.* Ships the channel. See above.
- *Local-only crash dumps the operator may choose to send.* Closer to acceptable, and still
  rejected for this release: it is a file the operator can already produce from logs, so the
  feature adds a mechanism without adding a capability.
- *Anonymous version check on start.* An outbound connection on every launch, revealing
  installation existence and cadence. Rejected for what it leaks, not for what it fetches.

## Verification

There is nothing to test for presence, so the test is for absence:
`shell/tests/test_limitations_are_disclosed.py` asserts that the no-telemetry statement
remains in `docs/LIMITATIONS.md`. If a future change adds an outbound channel, that
disclosure has to be removed to keep the document honest — and removing it fails the suite,
which puts the decision in front of a human.
