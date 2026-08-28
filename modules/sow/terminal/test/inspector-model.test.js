"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const {
  STATUS_ORDER, statusRank, buildInspectorModel, taskView, summarize,
} = require("../inspector/inspector-model");

// ---- helpers: minimal real-shaped records ----------------------------------
const entry = (id, over = {}) => ({
  entry_id: id, project_id: "proj", tier: "shared_project", kind: "finding",
  status: "ACCEPTED", content_hash: `sha256:${"a".repeat(64)}`, version: 1,
  provenance: { author_node: "worker-A", task_id: "t-1", ts: "2026-07-18T00:00:00Z",
                directive_version: "v2.4", confidence: "high" },
  ...over,
});
const withProv = (id, prov, over = {}) => entry(id, { provenance: { ...entry(id).provenance, ...prov }, ...over });

// ---- status ordering --------------------------------------------------------
test("STATUS_ORDER puts CANDIDATE first and ARCHIVED last; ranks are monotone", () => {
  assert.equal(STATUS_ORDER[0], "CANDIDATE");
  assert.equal(STATUS_ORDER[STATUS_ORDER.length - 1], "ARCHIVED");
  assert.ok(statusRank("CANDIDATE") < statusRank("ACCEPTED"));
  assert.ok(statusRank("REJECTED") < statusRank("ACCEPTED"));
});

test("an unknown status sorts AFTER every known one, deterministically (never hidden)", () => {
  assert.equal(statusRank("WAT"), STATUS_ORDER.length);
  assert.ok(statusRank("WAT") > statusRank("ARCHIVED"));
});

// ---- attribution + unattributed bucket -------------------------------------
test("entries are bucketed by provenance.task_id", () => {
  const m = buildInspectorModel({ entries: [entry("m-1", { provenance: { task_id: "t-1", author_node: "a", ts: "z" } }),
                                             entry("m-2", { provenance: { task_id: "t-2", author_node: "a", ts: "z" } })] });
  assert.deepEqual(m.tasks.map((t) => t.taskId), ["t-1", "t-2"]);
  assert.equal(taskView(m, "t-1").artifacts.length, 1);
  assert.equal(taskView(m, "t-2").artifacts[0].entryId, "m-2");
});

test("a mis-provenanced entry (null/empty task_id) is NOT dropped — it lands in unattributed (inv 27)", () => {
  const m = buildInspectorModel({ entries: [
    withProv("m-1", { task_id: null }),
    withProv("m-2", { task_id: "" }),
    entry("m-3"), // has t-1
  ] });
  assert.equal(m.unattributed.artifacts.length, 2);
  assert.deepEqual(m.unattributed.artifacts.map((a) => a.entryId).sort(), ["m-1", "m-2"]);
  assert.equal(m.tasks.length, 1);
});

test("artifact row keeps content hash, status, and FULL provenance (source_artifacts survives)", () => {
  const m = buildInspectorModel({ entries: [withProv("m-1", { source_artifacts: ["m-0"], task_id: "t-1" })] });
  const row = taskView(m, "t-1").artifacts[0];
  assert.equal(row.hash, `sha256:${"a".repeat(64)}`);
  assert.equal(row.status, "ACCEPTED");
  assert.deepEqual(row.provenance.source_artifacts, ["m-0"]);
});

// ---- status divergence (same entry id, two statuses) -----------------------
test("same entry id at two statuses -> keeps the MOST-ADVANCED and records an anomaly", () => {
  const m = buildInspectorModel({ entries: [
    entry("m-1", { status: "UNDER_REVIEW" }),
    entry("m-1", { status: "ACCEPTED" }),
  ] });
  assert.equal(taskView(m, "t-1").artifacts.length, 1);
  assert.equal(taskView(m, "t-1").artifacts[0].status, "ACCEPTED");
  assert.equal(m.anomalies.length, 1);
  assert.equal(m.anomalies[0].kind, "status-divergence");
});

test("divergence resolution is order-independent (advanced-then-earlier keeps advanced)", () => {
  const m = buildInspectorModel({ entries: [
    entry("m-1", { status: "ACCEPTED" }),
    entry("m-1", { status: "CANDIDATE" }),
  ] });
  assert.equal(taskView(m, "t-1").artifacts.length, 1);
  assert.equal(taskView(m, "t-1").artifacts[0].status, "ACCEPTED");
  assert.equal(m.anomalies.filter((a) => a.kind === "status-divergence").length, 1);
});

test("an exact duplicate (same id, same status) is idempotent — no anomaly, single row", () => {
  const m = buildInspectorModel({ entries: [entry("m-1"), entry("m-1")] });
  assert.equal(taskView(m, "t-1").artifacts.length, 1);
  assert.equal(m.anomalies.length, 0);
});

// ---- gate chain (incl. derived rows) ---------------------------------------
test("gate rows attach to their task; derived origin fields survive toGateRow", () => {
  const m = buildInspectorModel({ gates: [{
    gate_id: "m-g1", kind: "decision", verdict: "ACCEPTED by gate:gate-1", evidence: ["m-9"],
    task_id: "t-1", derived: true, source_entry_id: "m-g1", author: "gate-1", ts: "2026-07-18T00:00:00Z",
    entry_status: "ACCEPTED",
  }] });
  const g = taskView(m, "t-1").gateChain[0];
  assert.equal(g.gateId, "m-g1");
  assert.equal(g.verdict, "ACCEPTED by gate:gate-1");
  assert.deepEqual(g.evidence, ["m-9"]);
  assert.equal(g.derived, true);
  assert.equal(g.sourceEntryId, "m-g1");
  assert.equal(g.author, "gate-1");
  assert.equal(g.entryStatus, "ACCEPTED");
});

test("a native (non-derived) gate row carries no derived markers", () => {
  const m = buildInspectorModel({ gates: [{ gate_id: "g-1", kind: "stage", verdict: "PASS", task_id: "t-1" }] });
  const g = taskView(m, "t-1").gateChain[0];
  assert.equal(g.derived, undefined);
  assert.equal(g.sourceEntryId, undefined);
});

test("an unattributed gate (no task_id) lands in the unattributed bucket, not dropped", () => {
  const m = buildInspectorModel({ gates: [{ gate_id: "g-1", kind: "plan", verdict: "PASS", task_id: null }] });
  assert.equal(m.unattributed.gates.length, 1);
});

// ---- context routed ---------------------------------------------------------
test("a routing record populates contextRouted with included ids + count", () => {
  const m = buildInspectorModel({ routes: [{ task_id: "t-1", role: "worker", objective: "do x", included_entry_ids: ["m-1", "m-2"] }] });
  const r = taskView(m, "t-1").contextRouted;
  assert.equal(r.role, "worker");
  assert.deepEqual(r.includedEntryIds, ["m-1", "m-2"]);
  assert.equal(r.count, 2);
});

test("two routes for one task -> keeps the latest and records a duplicate-route anomaly", () => {
  const m = buildInspectorModel({ routes: [
    { task_id: "t-1", role: "worker", included_entry_ids: ["m-1"] },
    { task_id: "t-1", role: "worker", included_entry_ids: ["m-2"] },
  ] });
  assert.deepEqual(taskView(m, "t-1").contextRouted.includedEntryIds, ["m-2"]);
  assert.equal(m.anomalies.filter((a) => a.kind === "duplicate-route").length, 1);
});

// ---- deterministic output ---------------------------------------------------
test("tasks are sorted by id and artifacts by status rank (deterministic output)", () => {
  const m = buildInspectorModel({ entries: [
    entry("m-2", { provenance: { task_id: "t-2", author_node: "a", ts: "z" } }),
    entry("m-1", { provenance: { task_id: "t-1", author_node: "a", ts: "z" } }),
    entry("m-3", { status: "CANDIDATE", provenance: { task_id: "t-1", author_node: "a", ts: "z" } }),
  ] });
  assert.deepEqual(m.tasks.map((t) => t.taskId), ["t-1", "t-2"]);
  // within t-1: CANDIDATE (m-3) before ACCEPTED (m-1)
  assert.deepEqual(taskView(m, "t-1").artifacts.map((a) => a.entryId), ["m-3", "m-1"]);
});

// ---- summarize --------------------------------------------------------------
test("summarize counts tasks, artifacts, gates, routed, unattributed, anomalies", () => {
  const m = buildInspectorModel({
    entries: [entry("m-1"), withProv("m-2", { task_id: null })],
    gates: [{ gate_id: "g-1", task_id: "t-1", verdict: "PASS" }],
    routes: [{ task_id: "t-1", included_entry_ids: ["m-1"] }],
  });
  const s = summarize(m);
  assert.equal(s.taskCount, 1);
  assert.equal(s.artifactCount, 2); // 1 attributed + 1 unattributed
  assert.equal(s.gateCount, 1);
  assert.equal(s.routedTaskCount, 1);
  assert.equal(s.unattributedCount, 1);
  assert.equal(s.anomalyCount, 0);
});

// ---- fail-closed ------------------------------------------------------------
test("a malformed entry (not an object) THROWS — never guesses past ambiguity", () => {
  assert.throws(() => buildInspectorModel({ entries: ["nope"] }), /malformed entry/);
  assert.throws(() => buildInspectorModel({ gates: [42] }), /malformed gate/);
  assert.throws(() => buildInspectorModel({ routes: [null] }), /malformed route/);
});

test("taskView returns null for an unknown task", () => {
  const m = buildInspectorModel({ entries: [entry("m-1")] });
  assert.equal(taskView(m, "t-nope"), null);
});
