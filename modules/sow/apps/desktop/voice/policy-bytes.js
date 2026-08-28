"use strict";
/**
 * Phase 17C `.disarm-authority` (U181) — the voice-turn boundary's OWN bytes, re-verified at dispatch.
 *
 * THE DEFECT. The launch ticket points the vendor CLI's hook at `tools/live/voice_turn_boundary.js`,
 * which is inside this repository — and this repository is the conductor's `cwd`. That hook `require`s
 * `apps/desktop/voice/turn-authority.js`, also inside it. Both were hashed ONCE, when the ticket was
 * built, and nothing looked at them again. During any unrestricted typed turn the attended CLI can
 * rewrite either file; every subsequent voice turn would then be "enforced" by bytes nobody checked.
 * U25 records the absence of OS confinement — it does not record that the POLICY TRANSPORT lives
 * inside the contained process's write set.
 *
 * WHAT THIS DOES. Hashes the policy files when a governed launch is authorized, and re-hashes them on
 * every authority dispatch. A changed file, an unreadable file, or a file whose launch-time hash
 * disagrees with the ticket's is a REFUSAL — the authority service then fails closed for that event
 * (deny/block), which is the same answer it gives when the transport is absent.
 *
 * WHAT IT DOES NOT DO, stated plainly: it is a hash comparison, not confinement. A rewrite that is
 * reverted between two dispatches is invisible, and nothing here stops the write — U25 is still the
 * item for that. What it removes is the window in which a rewritten boundary is used as if it were
 * the pinned one.
 *
 * Pure over injected I/O: no Electron, no globals. Main binds it to the real files.
 */
const crypto = require("node:crypto");
const fs = require("node:fs");

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

class ConductorPolicyBytes {
  /**
   * @param {object} opts
   *   files    — absolute paths whose bytes ARE the boundary (hook + everything it requires here)
   *   readFile — injected reader (defaults to fs.readFileSync)
   */
  constructor(opts = {}) {
    this.files = Array.isArray(opts.files) ? opts.files.slice() : [];
    this._readFile = typeof opts.readFile === "function" ? opts.readFile : fs.readFileSync;
    this._pinned = null;      // {file: sha256} at the moment the launch was authorized
    this._pinnedAt = null;
  }

  _hash(file) {
    return sha256(this._readFile(file));
  }

  /**
   * Take the baseline for a governed launch.
   *
   * `expected` carries whatever the launch TICKET already claims about these files (today: the hook's
   * `hook_sha256`). A disagreement there is its own failure — the bytes changed between the ticket
   * being built and the session being spawned — and it refuses rather than adopting what it finds,
   * which would make the pin describe the swap instead of the authorized tree.
   */
  pin(expected = {}) {
    const pinned = {};
    for (const file of this.files) {
      let hash;
      try {
        hash = this._hash(file);
      } catch (e) {
        this._pinned = null;
        return { ok: false, reason: `the voice-turn policy file could not be read (${file}): `
          + `${(e && e.message) || e}` };
      }
      const claimed = expected && expected[file];
      if (claimed && String(claimed).toLowerCase() !== hash) {
        this._pinned = null;
        return { ok: false, reason: `the voice-turn policy file changed between the launch ticket and `
          + `the spawn (${file}): ticket ${String(claimed).slice(0, 16)}…, on disk ${hash.slice(0, 16)}…` };
      }
      pinned[file] = hash;
    }
    this._pinned = pinned;
    this._pinnedAt = new Date().toISOString();
    return { ok: true, pinned: { ...pinned }, pinned_at: this._pinnedAt };
  }

  /** Forget the baseline (the supervised session is gone; there is nothing left to protect). */
  clear() {
    this._pinned = null;
    this._pinnedAt = null;
  }

  /**
   * Re-read the policy files and compare. Called on EVERY authority dispatch.
   *
   * With nothing pinned this answers ok and says so: no governed conductor has been launched in this
   * process, so there is no supervised child that could have rewritten anything, and refusing here
   * would fail the headless/self-check paths closed against a threat that does not exist yet. The
   * moment a launch pins bytes, every dispatch is checked against them.
   */
  verify() {
    if (!this._pinned) {
      return { ok: true, pinned: false,
               reason: "no governed conductor launch has pinned voice-turn policy bytes in this process" };
    }
    const changed = [];
    for (const [file, hash] of Object.entries(this._pinned)) {
      let current;
      try {
        current = this._hash(file);
      } catch (e) {
        return { ok: false, pinned: true, changed: [file],
                 reason: `the voice-turn policy file is unreadable at dispatch (${file}): `
                   + `${(e && e.message) || e}` };
      }
      if (current !== hash) changed.push(file);
    }
    if (changed.length) {
      return { ok: false, pinned: true, changed,
               reason: `the voice-turn policy bytes changed under the running session `
                 + `(${changed.join(", ")}) — the boundary this session was authorized with is not the `
                 + "one that would answer, so the event is refused (fail closed)" };
    }
    return { ok: true, pinned: true, files: Object.keys(this._pinned).length };
  }

  /** What the receipt/inspector may read: which files, pinned when — never the bytes. */
  state() {
    return {
      files: this.files.slice(),
      pinned: Boolean(this._pinned),
      pinned_at: this._pinnedAt,
      hashes: this._pinned ? { ...this._pinned } : null,
    };
  }
}

module.exports = { ConductorPolicyBytes, sha256 };
