"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createReleaseRetryScheduler,
  createReleaseTargetStore,
  releaseOrSchedule,
} = require("../voice/conductor-release-retry");

test("release retries are isolated per conductor session", async () => {
  const queued = [];
  const retried = [];
  const scheduler = createReleaseRetryScheduler({
    retry: async (sessionId) => {
      retried.push(sessionId);
      return { ok: true };
    },
    schedule: (fn, delayMs) => {
      queued.push({ fn, delayMs });
      return { unref() {} };
    },
    delayMs: 30_000,
  });

  assert.equal(scheduler.schedule("session-a"), true);
  assert.equal(scheduler.schedule("session-a"), false);
  assert.equal(scheduler.schedule("session-b"), true);
  assert.deepEqual(scheduler.pendingSessions(), ["session-a", "session-b"]);
  assert.equal(queued.length, 2);
  assert.deepEqual(queued.map((item) => item.delayMs), [30_000, 30_000]);

  await queued[0].fn();
  await queued[1].fn();

  assert.deepEqual(retried, ["session-a", "session-b"]);
  assert.deepEqual(scheduler.pendingSessions(), []);
});

test("a failed retry can schedule the same session again", async () => {
  const queued = [];
  let attempts = 0;
  const scheduler = createReleaseRetryScheduler({
    retry: async () => {
      attempts += 1;
      return { ok: attempts > 1 };
    },
    schedule: (fn) => {
      queued.push(fn);
      return { unref() {} };
    },
  });

  scheduler.schedule("session-a");
  await queued.shift()();

  assert.equal(attempts, 1);
  assert.deepEqual(scheduler.pendingSessions(), ["session-a"]);
  assert.equal(queued.length, 1);

  await queued.shift()();
  assert.equal(attempts, 2);
  assert.deepEqual(scheduler.pendingSessions(), []);
});

test("an immediate pre-birth release failure is enrolled in the retry scheduler", async () => {
  const scheduled = [];
  const result = await releaseOrSchedule({
    sessionId: "session-a",
    release: async () => ({ ok: false, released: false, error: "temporary emitter failure" }),
    schedule: (sessionId) => { scheduled.push(sessionId); },
  });

  assert.equal(result.ok, false);
  assert.deepEqual(scheduled, ["session-a"]);
});

test("a conductor pre-birth retry preserves unavailable/failed instead of inventing exit", () => {
  const targets = createReleaseTargetStore();
  targets.mark("ticket-session", "unavailable", "ticket undelivered");
  targets.mark("spawn-session", "failed", "ConPTY construction failed");

  assert.deepEqual(targets.get("ticket-session"), {
    state: "unavailable", reason: "ticket undelivered",
  });
  assert.deepEqual(targets.get("spawn-session"), {
    state: "failed", reason: "ConPTY construction failed",
  });
  assert.deepEqual(targets.take("ticket-session"), {
    state: "unavailable", reason: "ticket undelivered",
  });
  assert.equal(targets.get("ticket-session"), null);
});
