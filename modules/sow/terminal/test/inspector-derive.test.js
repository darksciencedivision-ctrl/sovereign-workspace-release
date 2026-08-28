"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { deriveInputs, decisionToGate, GATE_DECISION_KIND } = require("../inspector/derive");

const prov = (over = {}) => ({ author_node: "n", task_id: "t-1", ts: "2026-07-18T00:00:00Z",
                               directive_version: "v2.4", confidence: "high", ...over });
const entry = (id, kind, over = {}) => ({
  entry_id: id, project_id: "proj", tier: "shared_project", kind, status: "ACCEPTED",
  content_hash: `sha256:${"b".repeat(64)}`, version: 1, provenance: prov(), ...over,
});

test("decision entries become DERIVED gate rows; everything else stays an entry", () => {
  const out = deriveInputs([
    entry("m-1", "finding"),
    entry("m-2", "decision"),
    entry("m-3", "artifact_ref"),
  ]);
  assert.deepEqual(out.entries.map((e) => e.entry_id).sort(), ["m-1", "m-3"]);
  assert.equal(out.gates.length, 1);
  assert.equal(out.gates[0].gate_id, "m-2");
  assert.equal(out.gates[0].derived, true);
  assert.equal(out.gates[0].kind, GATE_DECISION_KIND);
});

test("gate verdict is read from provenance.gate_result; absent -> null (never invented)", () => {
  const withResult = decisionToGate(entry("m-2", "decision", { provenance: prov({ gate_result: "ACCEPTED by gate:gate-1" }) }));
  assert.equal(withResult.verdict, "ACCEPTED by gate:gate-1");
  const without = decisionToGate(entry("m-3", "decision", { provenance: prov({}) }));
  assert.equal(without.verdict, null);
});

test("derived gate carries task_id, author, ts, evidence, entry_status from the entry's provenance", () => {
  const g = decisionToGate(entry("m-2", "decision", {
    status: "ACCEPTED",
    provenance: prov({ task_id: "t-9", author_node: "gate-1", evidence: ["m-7"] }),
  }));
  assert.equal(g.task_id, "t-9");
  assert.equal(g.author, "gate-1");
  assert.equal(g.entry_status, "ACCEPTED");
  assert.deepEqual(g.evidence, ["m-7"]);
  assert.equal(g.source_entry_id, "m-2");
});

test("an unattributed decision (null task_id) yields a gate row with task_id null (bucketed later)", () => {
  const g = decisionToGate(entry("m-2", "decision", { provenance: prov({ task_id: null }) }));
  assert.equal(g.task_id, null);
});

test("routes are ALWAYS empty and routingReadable is false — ScopedContext has no read path", () => {
  const out = deriveInputs([entry("m-1", "finding"), entry("m-2", "decision")]);
  assert.deepEqual(out.routes, []);
  assert.equal(out.routingReadable, false);
});

test("empty / default input is safe", () => {
  const out = deriveInputs();
  assert.deepEqual(out.entries, []);
  assert.deepEqual(out.gates, []);
  assert.deepEqual(out.routes, []);
  assert.equal(out.routingReadable, false);
});

test("fail-closed: non-array input and malformed records THROW", () => {
  assert.throws(() => deriveInputs("nope"), /expected an array/);
  assert.throws(() => deriveInputs([null]), /malformed entry/);
  assert.throws(() => deriveInputs([42]), /malformed entry/);
});
