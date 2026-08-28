"use strict";
/**
 * W-37 — `refuseSelection` judged the option the CALLER handed it.
 *
 * Every front-line refusal read `sel.option` directly: `opt.available`, `opt.roles`,
 * `opt.provider`, `opt.label`. So a caller supplying an option object with `available: true` and
 * the roles it wanted passed the entire guard, because the guard was asking the claim about itself.
 *
 * THE DONOR IS TWENTY LINES AWAY AND WAS ALREADY CORRECT. `main.js`'s conductor pre-launch path
 * takes `supplied = selection.option`, RE-FINDS it in `lastPickerModel.picker.options` by
 * (adapter, model_slug, label), and then judges the RE-FOUND option — `option.available !== true`,
 * `option.registered !== true`, and so on. `hostVerifiedFlag` does the same thing again for the
 * verified flag, and says why in its comment: "an option this host does not currently offer — a
 * fabricated one, or a stale one — is NOT verified, whatever the caller claimed." The worker picker
 * path simply never got that treatment.
 *
 * SEVERITY, stated honestly: this is a UX guard and Python re-enforces every gate at
 * `emit_worker_launch.py`, so a forged option does not by itself produce a governed launch. What it
 * produces is a shell that presents a fabricated model as spawnable and sends it down the launch
 * path to be refused later, which is exactly the "fabricated inventory" shape A-7 found in the
 * Antigravity parser. The fix is to ask the host, which the shell already knows how to do.
 *
 * FAIL-CLOSED ON OMISSION. `hostOptions` is not optional: a caller that forgets it gets a refusal,
 * not a pass. An optional corroboration is corroboration nobody performs.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { refuseSelection } = require("../picker/pane-wiring");

/** What the host actually offers. */
const HOST = Object.freeze([
  Object.freeze({ provider: "ollama", adapter: "ollama_local", label: "qwen3:8b",
    model_slug: "qwen3:8b", available: true, roles: ["reasoning", "coding"] }),
  Object.freeze({ provider: "ollama", adapter: "ollama_local", label: "phi4:14b",
    model_slug: "phi4:14b", available: false, unavailable_reason: "not resident",
    roles: ["reasoning"] }),
]);

const sel = (option, over = {}) => ({ option, role: "reasoning", mode: "attended", ...over });

test("W-37 NEGATIVE: a FORGED option with available:true is refused by the JS layer", () => {
  // The host has never heard of this model. The caller says it is available and offers the role.
  const forged = { provider: "ollama", adapter: "ollama_local", label: "totally-real:70b",
    model_slug: "totally-real:70b", available: true, roles: ["reasoning"] };
  const why = refuseSelection(sel(forged), { hostOptions: HOST });
  assert.ok(why, "a fabricated option passed the guard — the guard asked the claim about itself");
  assert.match(why, /not offered by this host|host does not offer/i,
    "the refusal must say the HOST does not offer it, not that some field was wrong");
});

test("W-37 NEGATIVE: a real option with a FORGED available:true is refused", () => {
  // The sharper case: the model exists, the host says it is NOT available, and the caller
  // overrides that. Judging the supplied object cannot catch this; re-finding it does.
  const lying = { ...HOST[1], available: true, unavailable_reason: undefined };
  const why = refuseSelection(sel(lying), { hostOptions: HOST });
  assert.ok(why, "the caller's `available:true` overrode the host's `available:false`");
  assert.match(why, /unavailable \(not resident\)/,
    "the refusal must carry the HOST's reason, not the caller's silence");
});

test("W-37 NEGATIVE: forged ROLES are refused — the host's role list is the one that counts", () => {
  const lying = { ...HOST[0], roles: ["reasoning", "coding", "conductor", "voice"] };
  const why = refuseSelection(sel(lying, { role: "voice" }), { hostOptions: HOST });
  assert.ok(why, "a caller-supplied role list was believed");
  assert.match(why, /not offered by/);
});

test("W-37 NEGATIVE: corroboration is NOT optional — omitting the host model refuses", () => {
  const why = refuseSelection(sel(HOST[0]), {});
  assert.ok(why, "a caller that supplies no host model must be refused, not waved through");
  assert.match(why, /host/i);
});

test("W-37 POSITIVE: a genuine selection the host does offer still passes", () => {
  assert.strictEqual(refuseSelection(sel(HOST[0]), { hostOptions: HOST }), null);
});

test("W-37: matching is by (adapter, model_slug, label), the donor's own key", () => {
  // A same-labelled model from a different adapter is a different option. Matching on label alone
  // would let a caller borrow the availability of something else the host offers.
  const borrowed = { ...HOST[0], adapter: "grok_build" };
  assert.ok(refuseSelection(sel(borrowed), { hostOptions: HOST }),
    "an option matching only by label must not inherit another adapter's availability");
});
