"use strict";
/**
 * Phase 19 unit 19.6 — is THIS descriptor a conductor readiness may proceed with? ([[U331]])
 *
 * WHAT THIS REPLACES, verbatim from the audited code:
 *
 *     if (descriptor.provider_id !== "openai_codex_cli" || descriptor.model_id !== "gpt-5.6-sol") {
 *       ... reason: "conductor readiness requires exact OpenAI/Codex gpt-5.6-sol selection"
 *
 * That test ran AFTER the selection layer had resolved a descriptor, after the registry had
 * declared it conductor-capable, and after the governed spawn path — live switch, provider-live,
 * operator terms, I-X3 lease — had admitted it and started a real session. Everything upstream was
 * provider-neutral; this line was not, and it disagreed with the commit that introduced it.
 *
 * THE RULE NOW. Four questions, each true of a conductor of any provider: is this a conductor
 * descriptor, does it name a provider and a model, did the registry register it, is it
 * conductor-capable. None of them is a name, and an unresolved selection is a genuine configuration
 * error that still reports as one.
 *
 * Unit 19.10 closes the absence asymmetry recorded in U430: `role`, `registered` and
 * `conductor_capable` are required exactly as the registry emits them. The launch ticket and the
 * independently sourced readiness feed are compared field-by-field before process birth; two
 * individually valid descriptors are not interchangeable authority for different conductors.
 *
 * NO AUTHORITY LIVES HERE. This module decides whether readiness can proceed; it authorizes
 * nothing. Whether this conductor may run at all was settled by the governor and the launch ticket
 * before a process existed.
 */
const nonEmpty = (v) => typeof v === "string" && v.trim() !== "";

const refuse = (reason) => Object.freeze({ ok: false, state: "FAILED", reason });

/**
 * @param descriptor the resolved conductor descriptor (`conductorDescriptor()` in `main.js`).
 * @returns `{ok: true, provider_id, model_id, readiness_turns, selection_source, decided_by}` or
 *          `{ok: false, state: "FAILED", reason}` — the reason names the missing property, never a
 *          vendor, because a refusal that names a vendor is the pin returning as a message.
 */
function conductorAdmission(descriptor) {
  if (!descriptor || typeof descriptor !== "object") {
    return refuse("conductor selection is unresolved: no descriptor");
  }
  if (descriptor.role !== "conductor") {
    return refuse("conductor selection is unresolved: descriptor is not for the conductor role");
  }
  if (!nonEmpty(descriptor.provider_id)) {
    return refuse("conductor selection is incomplete: descriptor names no provider");
  }
  if (!nonEmpty(descriptor.model_id)) {
    return refuse("conductor selection is incomplete: descriptor names no model");
  }
  if (descriptor.registered !== true) {
    return refuse("conductor selection is unresolved: the descriptor is not registered");
  }
  if (descriptor.conductor_capable !== true) {
    return refuse("conductor selection is unresolved: the descriptor is not conductor-capable");
  }
  return Object.freeze({
    ok: true,
    provider_id: descriptor.provider_id.trim(),
    model_id: descriptor.model_id.trim(),
    readiness_turns: Number.isInteger(descriptor.readiness_turns) && descriptor.readiness_turns > 0
      ? descriptor.readiness_turns : 1,
    // Provenance the Python registry stamps (19.6): whether this selection came from the operator's
    // host preference file or is the recorded default the registry resolves in its absence. The
    // shell reports it; it is never a reason to refuse. "unstated" is the honest answer for a
    // descriptor minted before the field existed — not an assumption about which it was.
    selection_source: nonEmpty(descriptor.selection_source)
      ? descriptor.selection_source.trim() : "unstated",
    decided_by: "conductor_descriptor",
  });
}

/**
 * The rule, and it is the general one this set exists to hold: A FIELD THAT CHANGES BEHAVIOUR IS AN
 * AGREEMENT FIELD. `readiness_turns` was absent from this list and drives behaviour — the admission
 * above reads it, and `control/conductor-readiness.js:29` loops `for (turn = 1; turn <=
 * admission.readiness_turns; …)`. Its value is 1 by default and 2 for `grok_build`, so a feed
 * descriptor disagreeing about it still "agreed", and the readiness gate could run a different
 * number of turns than the launch ticket authorized (W-17).
 */
const AGREEMENT_FIELDS = Object.freeze([
  "role", "provider_id", "adapter_id", "model_id", "permission_profile_id", "readiness_turns",
]);

/**
 * How each agreement field is read before it is compared. The set is no longer all strings, and
 * `nonEmpty` is a STRING predicate — applying it to an integer answers false for every descriptor,
 * which would make every comparison disagree. `readiness_turns` is therefore normalised exactly as
 * the admission normalises it above: a positive integer, or 1. Absent MEANS one turn, so a
 * descriptor minted before the field existed still agrees with an identical one that spells it out
 * — a refusal with no behaviour behind it is not a guard.
 */
const AGREEMENT_READERS = Object.freeze({
  readiness_turns: (v) => (Number.isInteger(v) && v > 0 ? v : 1),
});

/** The feed may drive readiness only for the exact conductor the launch ticket authorized. */
function conductorDescriptorsAgree(ticketDescriptor, feedDescriptor) {
  if (!ticketDescriptor || !feedDescriptor) return false;
  return AGREEMENT_FIELDS.every((key) => {
    const read = AGREEMENT_READERS[key];
    if (read) return read(ticketDescriptor[key]) === read(feedDescriptor[key]);
    return nonEmpty(ticketDescriptor[key]) && ticketDescriptor[key] === feedDescriptor[key];
  });
}

module.exports = { conductorAdmission, conductorDescriptorsAgree, AGREEMENT_FIELDS };
