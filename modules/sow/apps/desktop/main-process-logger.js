"use strict";

const fs = require("fs");
const path = require("path");

const crypto = require("crypto");

function isEpipe(error) {
  return Boolean(error && error.code === "EPIPE");
}

/**
 * W-35: render an argv for logging with any `--settings` PROFILE identified rather than reproduced.
 *
 * `tools/live/emit_conductor_launch.py:185` appends `--settings <profile.settings_json>`, so the
 * authority-boundary profile — hook command paths included — travelled verbatim into the durable
 * log AND, via `rendererSink`, to the renderer console: the least-trusted surface in the app.
 *
 * Identified, not merely removed. A reader must be able to tell WHICH profile a launch used, and to
 * tell two launches apart, or the log has traded a leak for a blind spot (invariant 27). A digest
 * does both. The length is reported because "empty profile" and "large profile" are different
 * facts, and neither is recoverable from a digest alone.
 */
function redactArgvForLog(argv) {
  const parts = Array.isArray(argv) ? argv.map(String) : [];
  const out = [];
  for (let i = 0; i < parts.length; i += 1) {
    out.push(parts[i]);
    if (parts[i] === "--settings" && i + 1 < parts.length) {
      const value = parts[i + 1];
      const digest = crypto.createHash("sha256").update(value, "utf8").digest("hex").slice(0, 12);
      out.push(`<profile sha256:${digest}, ${Buffer.byteLength(value, "utf8")} bytes>`);
      i += 1;
    }
  }
  return out.join(" ");
}

/**
 * W-35: is `candidate` a log path this process is willing to write to?
 *
 * `SOW_MAIN_LOG_FILE` was used raw. An env-supplied path that this process appends to on every log
 * line is an arbitrary-append primitive, and the failure is silent — nobody notices the log went
 * somewhere else. Absolute and traversal-free, refused loudly otherwise.
 */
function logPathIsAcceptable(candidate) {
  if (typeof candidate !== "string" || !candidate.trim()) return "empty";
  if (candidate.includes("\0")) return "contains a NUL byte";
  if (!path.isAbsolute(candidate)) return "is not absolute";
  if (path.normalize(candidate) !== candidate) return "contains traversal or redundant segments";
  return null;
}

/**
 * Durable-first main-process logging.
 *
 * stdout/stderr are inherited pipes during self-checks. Their consumer is allowed to disappear;
 * that makes EPIPE a terminal detachment, not an application failure. Other stream failures retain
 * normal fatal visibility by being re-thrown on the next microtask unless a test observer is
 * explicitly supplied.
 */
function createMainProcessLogger({
  file,
  stdout = process.stdout,
  stderr = process.stderr,
  rendererSink = () => {},
  onNonEpipeError = null,
  // W-35. 8 MiB live + one rotated generation: a bound on TOTAL growth, not a bound per file with
  // an unbounded number of files, which is the same unbounded disk use with more steps.
  maxBytes = 8 * 1024 * 1024,
  fallbackFile = null,
  onPathRefused = null,
} = {}) {
  if (!file) throw new Error("main-process logger requires a persistent file");
  // W-35: an env-supplied path is validated before anything is written to it. Falling back is only
  // safe if the fallback is itself acceptable — otherwise this would launder a bad path into a
  // "safe" one nobody chose.
  const refusal = logPathIsAcceptable(file);
  if (refusal) {
    if (!fallbackFile || logPathIsAcceptable(fallbackFile)) {
      throw new Error(`main-process logger refuses the log path (it ${refusal}) and has no usable `
        + "fallback");
    }
    if (typeof onPathRefused === "function") onPathRefused(refusal);
    file = fallbackFile;
  }
  fs.mkdirSync(path.dirname(file), { recursive: true });

  const rotated = `${file}.1`;
  let bytesWritten = (() => {
    try { return fs.statSync(file).size; } catch { return 0; }
  })();

  let consoleAttached = true;
  let pendingWrites = 0;
  const settledWaiters = new Set();
  const observedErrors = new WeakSet();

  const settle = () => {
    if (pendingWrites !== 0) return;
    for (const resolve of settledWaiters) resolve();
    settledWaiters.clear();
  };

  const persist = (line) => {
    const payload = `${line}\n`;
    // W-35: rotate BEFORE the write that would breach the ceiling, so the live file never exceeds
    // it. Rotating after would leave the log momentarily over the bound, which on a crash is the
    // state that survives.
    if (bytesWritten > 0 && bytesWritten + Buffer.byteLength(payload, "utf8") > maxBytes) {
      try {
        fs.rmSync(rotated, { force: true });
        fs.renameSync(file, rotated);
        bytesWritten = 0;
      } catch {
        // A rotation that cannot happen must not lose the line: fall through and append. A log that
        // throws on its own maintenance turns a disk condition into an application failure.
      }
    }
    fs.appendFileSync(file, payload, "utf8");
    bytesWritten += Buffer.byteLength(payload, "utf8");
  };

  const observeNonEpipe = (error, streamName) => {
    if (error && typeof error === "object") {
      if (observedErrors.has(error)) return;
      observedErrors.add(error);
    }
    persist(`[shell] ${streamName} stream error: ${error && error.stack ? error.stack : String(error)}`);
    if (typeof onNonEpipeError === "function") {
      onNonEpipeError(error, streamName);
      return;
    }
    queueMicrotask(() => { throw error; });
  };

  const onStreamError = (streamName) => (error) => {
    if (isEpipe(error)) {
      consoleAttached = false;
      pendingWrites = 0;
      settle();
      return;
    }
    observeNonEpipe(error, streamName);
  };

  // Narrow stream handlers: EPIPE is consumed; every other stream error is surfaced.
  stdout.on("error", onStreamError("stdout"));
  stderr.on("error", onStreamError("stderr"));

  const writeConsole = (line) => {
    if (!consoleAttached) return;
    pendingWrites += 1;
    try {
      stdout.write(`${line}\n`, (error) => {
        pendingWrites = Math.max(0, pendingWrites - 1);
        if (error) onStreamError("stdout")(error);
        settle();
      });
    } catch (error) {
      pendingWrites = Math.max(0, pendingWrites - 1);
      if (isEpipe(error)) consoleAttached = false;
      else observeNonEpipe(error, "stdout");
      settle();
    }
  };

  return {
    file,
    log(message) {
      const line = `[shell] ${message}`;
      persist(line);
      rendererSink(line);
      writeConsole(line);
      return line;
    },
    async flushAndDetach() {
      if (pendingWrites > 0) {
        await new Promise((resolve) => settledWaiters.add(resolve));
      }
      consoleAttached = false;
    },
    detachConsole() { consoleAttached = false; },
    isConsoleAttached() { return consoleAttached; },
  };
}

module.exports = { createMainProcessLogger, isEpipe, redactArgvForLog, logPathIsAcceptable };
