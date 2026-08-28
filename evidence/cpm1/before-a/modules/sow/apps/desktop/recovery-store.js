"use strict";
/**
 * RecoveryStore — durable persistence of the append-only session lifecycle log (product code).
 *
 * A gateway/control-plane restart while the shell keeps running is recovered in memory (the
 * supervisor's RecoveryMachine re-verifies the channel and re-admits — see supervisor.js). A
 * full SHELL PROCESS restart loses that memory, so this store persists the SessionRegistry's
 * append-only log (invariant 12) to a file inside the repo; on the next boot the shell folds it
 * (terminal/recovery/reconstruct) to surface what existed. Sessions that were still alive at the
 * cut come back marked `needsRelaunch` and NOT auto-recoverable — fail-closed, no naked re-spawn
 * (invariant 2); the operator relaunches them through supervised admission.
 *
 * fs is injected so the fold + persistence are headlessly testable; the Electron wiring in
 * main.js passes node's fs and a path under apps/desktop/.recovery/ (gitignored, in-repo).
 * Every read fails closed: a missing or corrupt file yields [], never a throw, never a fabricated
 * session.
 *
 * Phase 15E `.recovery` adds the conductor-first LAYOUT snapshot alongside the session log: a full
 * shell restart must come back with the pinned CONDUCTOR as pane 1 and the worker panes reattaching
 * (OP-7 §12.4 / directive §9 track 14A). The session log records what PTYs existed; the layout
 * snapshot records the pane structure (order, roles, models, attended/autonomous, pinned) so the
 * two fold together (terminal/recovery/layout-reconstruct) into the layout the shell rebuilds. The
 * snapshot lives in a sibling `layout.json` in the same in-repo `.recovery/` dir, same atomic-write
 * + fail-closed-read machinery, so a corrupt/missing snapshot degrades to a conductor-only layout.
 */
const { reconstructSessions, interruptedSessions } = require("../../terminal/recovery/reconstruct");

const FORMAT_VERSION = 1;

class RecoveryStore {
  constructor({ file, fs = require("fs"), log = () => {} }) {
    if (!file) throw new Error("RecoveryStore requires a file path");
    this._file = file;
    // the layout snapshot is a sibling of the session-log file in the same .recovery/ dir; the
    // capture keeps whatever separator the caller used (\\ on Windows, / on the test shim).
    this._layoutFile = /[\\/]/.test(file) ? file.replace(/([\\/])[^\\/]*$/, "$1layout.json") : "layout.json";
    this._fs = fs;
    this._log = log;
  }

  /** Persist the append-only session log (best-effort; a write failure never breaks the shell).
   *  Atomic: write a temp file then rename over the target, so a crash mid-write can never leave
   *  a truncated log that folds to [] and hides an interrupted session (invariant 27 — the
   *  recovery report must survive; the LAST GOOD log stays intact if the write is interrupted). */
  persist(eventLog) {
    this._writeAtomic(this._file, { version: FORMAT_VERSION, log: eventLog || [] }, "recovery persist");
  }

  /** Persist the conductor-first LAYOUT snapshot (Phase 15E `.recovery`). Same atomic write; a
   *  write failure never breaks the shell. The snapshot is produced by
   *  terminal/recovery/layout-reconstruct.buildLayoutSnapshot and folded on the next boot into the
   *  layout the shell rebuilds (pinned CONDUCTOR pane 1 + reattaching worker panes). */
  persistLayout(snapshot) {
    this._writeAtomic(this._layoutFile, { version: FORMAT_VERSION, snapshot: snapshot || null }, "layout persist");
  }

  /** Read the persisted layout snapshot (fail-closed to null ⇒ a conductor-only reconstruction). */
  loadLayout() {
    try {
      if (this._fs.existsSync && !this._fs.existsSync(this._layoutFile)) return null;
      const raw = this._fs.readFileSync(this._layoutFile, "utf8");
      const parsed = JSON.parse(typeof raw === "string" ? raw : raw.toString("utf8"));
      return parsed && typeof parsed.snapshot === "object" ? parsed.snapshot : null;
    } catch (e) {
      if (e.code !== "ENOENT") this._log(`layout load failed (fail-closed to null): ${e.message}`);
      return null;
    }
  }

  /** Atomic write shared by the session log + the layout snapshot: temp write then rename over the
   *  target, so a crash mid-write can never leave a truncated file that hides recovery state
   *  (invariant 27 — the LAST GOOD file survives). An injected fs without rename writes directly. */
  _writeAtomic(file, obj, label) {
    try {
      const dir = file.replace(/[\\/][^\\/]*$/, "");
      if (dir && dir !== file && this._fs.mkdirSync) { try { this._fs.mkdirSync(dir, { recursive: true }); } catch { /* exists */ } }
      const body = JSON.stringify(obj);
      if (this._fs.renameSync) {
        const tmp = `${file}.tmp`;
        this._fs.writeFileSync(tmp, body);
        this._fs.renameSync(tmp, file); // atomic on the same volume; last good file survives a crash
      } else {
        this._fs.writeFileSync(file, body); // injected fs without rename (tests): direct write
      }
    } catch (e) {
      this._log(`${label} failed (non-fatal): ${e.message}`);
    }
  }

  /** Read + fold the persisted log to the full reconstructed session view (fail-closed to []). */
  loadAll() {
    const log = this._readLog();
    return log === null ? [] : reconstructSessions(log);
  }

  /** The sessions a restart must surface for supervised relaunch (fail-closed to []). */
  loadInterrupted() {
    const log = this._readLog();
    return log === null ? [] : interruptedSessions(log);
  }

  _readLog() {
    try {
      if (this._fs.existsSync && !this._fs.existsSync(this._file)) return null;
      const raw = this._fs.readFileSync(this._file, "utf8");
      const parsed = JSON.parse(typeof raw === "string" ? raw : raw.toString("utf8"));
      return Array.isArray(parsed.log) ? parsed.log : null;
    } catch (e) {
      if (e.code !== "ENOENT") this._log(`recovery load failed (fail-closed to empty): ${e.message}`);
      return null;
    }
  }
}

module.exports = { RecoveryStore, FORMAT_VERSION };
