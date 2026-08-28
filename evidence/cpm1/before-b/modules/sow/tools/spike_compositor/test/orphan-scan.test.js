"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { findOrphans, parseCimJson } = require("../lib/orphan-scan");

test("conhost child of own pid is an orphan", () => {
  const procs = [{ Name: "conhost.exe", ProcessId: 500, ParentProcessId: 100 }];
  const r = findOrphans(procs, 100, []);
  assert.equal(r.length, 1);
  assert.equal(r[0].pid, 500);
});

test("OpenConsole child of a known pty pid is an orphan (case-insensitive)", () => {
  const procs = [{ Name: "OpenConsole.exe", ProcessId: 501, ParentProcessId: 222 }];
  assert.equal(findOrphans(procs, 100, [222]).length, 1);
});

test("unrelated conhost (foreign parent) is not ours", () => {
  const procs = [{ Name: "conhost.exe", ProcessId: 502, ParentProcessId: 9999 }];
  assert.equal(findOrphans(procs, 100, [222]).length, 0);
});

test("non-console processes never match", () => {
  const procs = [{ Name: "cmd.exe", ProcessId: 503, ParentProcessId: 100 }];
  assert.equal(findOrphans(procs, 100, []).length, 0);
});

test("parseCimJson: empty -> [], single object -> [obj], array -> array", () => {
  assert.deepEqual(parseCimJson(""), []);
  assert.deepEqual(parseCimJson(null), []);
  assert.equal(parseCimJson('{"Name":"conhost.exe","ProcessId":1,"ParentProcessId":2}').length, 1);
  assert.equal(parseCimJson('[{"Name":"a"},{"Name":"b"}]').length, 2);
});
