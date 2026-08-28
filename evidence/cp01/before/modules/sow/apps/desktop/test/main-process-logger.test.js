"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createMainProcessLogger } = require("../main-process-logger");

class FakeWritable extends EventEmitter {
  constructor() {
    super();
    this.writes = [];
    this.nextError = null;
  }

  write(text, callback) {
    this.writes.push(text);
    const error = this.nextError;
    this.nextError = null;
    queueMicrotask(() => {
      if (error) this.emit("error", error);
      callback(error);
    });
    return !error;
  }
}

function fixture(t, onNonEpipeError = null) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sow-main-log-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const stdout = new FakeWritable();
  const stderr = new FakeWritable();
  const file = path.join(dir, "main.log");
  const logger = createMainProcessLogger({ file, stdout, stderr, onNonEpipeError });
  return { logger, stdout, stderr, file };
}

test("stdout EPIPE detaches the console while durable logging remains alive", async (t) => {
  const { logger, stdout, file } = fixture(t);
  stdout.nextError = Object.assign(new Error("pipe closed"), { code: "EPIPE" });

  logger.log("conductor: LIVE session running");
  await logger.flushAndDetach();
  assert.equal(logger.isConsoleAttached(), false);

  logger.log("conductor: teardown completed");
  const durable = fs.readFileSync(file, "utf8");
  assert.match(durable, /conductor: LIVE session running/);
  assert.match(durable, /conductor: teardown completed/);
  assert.equal(stdout.writes.length, 1, "no console writes occur after terminal detachment");
});

test("stderr EPIPE also detaches all best-effort console output", (t) => {
  const { logger, stdout, stderr, file } = fixture(t);
  stderr.emit("error", Object.assign(new Error("consumer exited"), { code: "EPIPE" }));
  logger.log("still durable");
  assert.equal(stdout.writes.length, 0);
  assert.match(fs.readFileSync(file, "utf8"), /still durable/);
});

test("non-EPIPE stream errors remain observable and are persisted", (t) => {
  const observed = [];
  const { stderr, file } = fixture(t, (error, streamName) => observed.push({ error, streamName }));
  const failure = Object.assign(new Error("terminal I/O failed"), { code: "EIO" });
  stderr.emit("error", failure);

  assert.deepEqual(observed, [{ error: failure, streamName: "stderr" }]);
  assert.match(fs.readFileSync(file, "utf8"), /stderr stream error: Error: terminal I\/O failed/);
});

test("unrelated renderer logging exceptions are not suppressed", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sow-main-log-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, "main.log");
  const failure = new Error("renderer channel failed");
  const logger = createMainProcessLogger({
    file,
    stdout: new FakeWritable(),
    stderr: new FakeWritable(),
    rendererSink: () => { throw failure; },
  });
  assert.throws(() => logger.log("durable before renderer"), failure);
  assert.match(fs.readFileSync(file, "utf8"), /durable before renderer/);
});
