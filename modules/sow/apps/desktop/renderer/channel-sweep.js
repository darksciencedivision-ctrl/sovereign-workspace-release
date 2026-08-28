"use strict";
/**
 * The U177 runtime sweep — drive EVERY renderer IPC channel, so the in-Electron receipt can assert
 * that an admitted voice turn is still admitted afterwards.
 *
 * WHY IT EXISTS. `voice-disarm-wiring.test.js` closed the static forms of "a renderer channel
 * releases the voice restriction": no `ipcMain.handle` body, and nothing reachable by NAME from one,
 * calls a release or names the authority service at all. What a source reading cannot see is a callee
 * reached through a getter or a Proxy trap, or a reference stored on one channel and invoked from
 * another. The register carries that residual as U177 and prescribes the instrument: arm a turn, drive
 * every channel, assert the turn is still admitted. This module is the driver.
 *
 * IT GRANTS NOTHING. Every call here goes through the preload bridge the renderer already holds; the
 * surface is INJECTED rather than reached for, which is what lets the whole driver be falsified in a
 * headless test (`test/channel-sweep.test.js`) against a fake bridge. With no surface it does nothing.
 *
 * FAIL-CLOSED COVERAGE, in both directions, because a sweep that silently skipped the one channel
 * somebody just added would be worse than no sweep — the receipt would still be green:
 *   • a method the bridge exposes that no entry names   → `uncovered`, `ok:false`
 *   • an entry whose method the bridge does not answer  → `missing`,   `ok:false`
 *   • a pane-targeted entry with no pane to target      → not invoked, `ok:false`
 * A handler that THROWS is still `invoked:true` with its error recorded: the property under test is
 * what happened to the turn, not whether the intent succeeded. Most of these are expected to refuse
 * (a second conductor launch, an approval decision on an item that does not exist), and a refusal is
 * a governed answer — it means the channel ran.
 *
 * SAFETY, which is a real constraint and not a caveat: this runs against a LIVE conductor session
 * mid-receipt. Anything that could kill, hide or re-tile pane 1 is pointed at a scratch pane the
 * sweep creates and closes; only the non-destructive intents are aimed at the conductor pane — and
 * `input` deliberately IS, because bytes on `pane:input` are the exact channel U175 was about.
 *
 * WHAT THOSE BYTES MAY BE, learned the hard way. The first version of this sweep typed its probe
 * STRING into pane 1 and claimed a trailing ETX cleared the line. The receipt it produced proved
 * otherwise: the live CLI took the ETX as an interrupt, KEPT the text, and the next typed prompt was
 * submitted as `sovereign-channel-sweep-u177What is twenty-six plus twenty-six?…` — a prompt the
 * operator never composed, under their own provenance, in the vendor's durable session store. Both
 * reviewers charged it. So the conductor payload is now CONTROL BYTES ONLY (kill-line), which cannot
 * become a prompt and cannot exit the session: the property under test is that renderer bytes on this
 * channel do not release a turn, and that property is about the CHANNEL, not about the payload.
 *
 * THE ARGUMENTS ARE GOVERNED AND NON-DESTRUCTIVE — they are NOT no-ops, and calling them that was the
 * other overstatement. Several of them record: the protected verb queues a proposal, the approval
 * decision routes to the governed Python resolve, the succession request writes a log line. Each is a
 * governed WRITE that the shell attributes to the operator, and the only reason that is acceptable is
 * that this module is reachable ONLY from the self-check hook (renderer.js loads it on demand under
 * `?selfcheck=1`), whose run has its own isolated recovery store — never an operator session.
 */
(function () {
  /**
   * The conductor pane may only ever be the target of these — the intents that cannot destroy, hide
   * or re-tile the pane holding the live session. `input` is here on a narrower licence than the
   * other three, and it is stated rather than implied: it WRITES to the live session, so its payload
   * is restricted to control bytes that cannot become a prompt (see CONDUCTOR_INPUT_BYTES).
   */
  const CONDUCTOR_SAFE_METHODS = new Set(["input", "scrollback", "resize", "focus"]);

  const SWEEP_PROBE = "sovereign-channel-sweep-u177";
  /**
   * NAK / Ctrl-U — kill line. What goes to the LIVE conductor on `pane:input`, and all that may.
   *
   * Not a probe string (the first version's text survived its own "clearing" ETX and was submitted as
   * part of the operator's next prompt), and not ETX (which the live CLI answers with "press Ctrl-C
   * again to exit" — an interrupt is not a clear, and a second one ends the session). A kill-line is
   * inert if the CLI ignores it and clears the input line if it does not, and either way it is bytes
   * on `pane:input`, which is the whole property.
   */
  const CONDUCTOR_INPUT_BYTES = String.fromCharCode(0x15);

  /**
   * Every intent the preload bridge exposes, with arguments chosen to be governed and
   * non-destructive — NOT no-ops: several of them legitimately record (see the header).
   *
   * `pane` says which pane the intent is aimed at: `create` mints the scratch pane, `scratch` targets
   * it, `conductor` targets the live pane 1, `none` takes no pane. Order is execution order — the
   * create is first, the close is last.
   */
  const SWEEP = [
    // the scratch pane every destructive intent below is aimed at
    { method: "newPane", channel: "pane:new", pane: "create", args: () => [{ title: SWEEP_PROBE }] },

    // ---- the conductor pane ----
    // `input` is the point of the exercise: these are renderer bytes, on the channel the supervised
    // child can elicit by printing a device-attribute query. Control bytes only — nothing this write
    // leaves behind may become part of the operator's next prompt (see CONDUCTOR_INPUT_BYTES).
    { method: "input", channel: "pane:input", pane: "conductor",
      args: (c) => [c.conductorPaneId, CONDUCTOR_INPUT_BYTES] },
    { method: "scrollback", channel: "pane:scrollback", pane: "conductor", args: (c) => [c.conductorPaneId] },
    // the pane's CURRENT geometry — a real resize of a live TUI would repaint it mid-receipt
    { method: "resize", channel: "pane:resize", pane: "conductor", args: (c) => [c.conductorPaneId, c.cols, c.rows] },
    { method: "focus", channel: "pane:focus", pane: "conductor", args: (c) => [c.conductorPaneId] },

    // ---- the scratch pane: everything that re-tiles, hides or kills ----
    { method: "maximize", channel: "pane:maximize", pane: "scratch", args: (c) => [c.scratchPaneId] },
    { method: "restore", channel: "pane:restore", pane: "scratch", args: (c) => [c.scratchPaneId] },
    { method: "minimize", channel: "pane:minimize", pane: "scratch", args: (c) => [c.scratchPaneId] },
    { method: "pin", channel: "pane:pin", pane: "scratch", args: (c) => [c.scratchPaneId, false] },
    { method: "setActivity", channel: "pane:activity", pane: "scratch", args: (c) => [c.scratchPaneId, "idle"] },

    // ---- pane-less intents ----
    { method: "snapshot", channel: "shell:snapshot", pane: "none", args: () => [] },
    { method: "conductorState", channel: "conductor:state", pane: "none", args: () => [] },
    // refused: a live conductor session is already running in pane 1 (main's own fail-closed path)
    { method: "launchConductor", channel: "conductor:launch", pane: "none", args: () => [] },
    // refused: selection is pre-launch only, and an empty descriptor cannot resolve or persist
    { method: "selectConductor", channel: "conductor:select", pane: "none", args: () => [{}] },
    { method: "succeedConductor", channel: "conductor:succeed", pane: "none", args: () => [] },
    { method: "approvals", channel: "approvals:fetch", pane: "none", args: () => [] },
    // an item id no queue holds: the governed resolve refuses it, which is a governed answer
    { method: "decideApproval", channel: "approvals:decide", pane: "none",
      args: () => [`${SWEEP_PROBE}-no-such-item`, "reject", "U177 channel sweep probe"] },
    { method: "inspector", channel: "inspector:fetch", pane: "none", args: () => [] },
    { method: "statusBar", channel: "statusbar:fetch", pane: "none", args: () => [] },
    { method: "picker", channel: "picker:fetch", pane: "none", args: () => [] },
    // an empty selection: the fail-closed selection guard refuses it, so nothing is spawned
    { method: "spawnFromSelection", channel: "pane:spawnFromSelection", pane: "none", args: () => [{}] },
    { method: "voiceState", channel: "voice:state", pane: "none", args: () => [] },
    // a PROTECTED verb, so the bridge queues it for approval and delivers nothing into the live pane
    // (invariant 25). `voice:capture` is also the ONE channel permitted to cancel a turn — its OWN
    // pending one — which is precisely why it belongs in a sweep about the ADMITTED turn.
    { method: "captureVoice", channel: "voice:capture", pane: "none", args: () => ["audio:terminate-node-b"] },
    // unforced: the cached answer, not a fresh WSL NeMo import
    { method: "probeVoice", channel: "voice:probe", pane: "none", args: () => [{}] },

    // ---- last, because it destroys the pane the entries above target ----
    { method: "close", channel: "pane:close", pane: "scratch", args: (c) => [c.scratchPaneId] },
  ];

  /**
   * `ipcMain.handle("<channel>"` — what main actually registers.
   *
   * It reads ONE shape: a double-quoted literal. Everything else main could write —
   * `ipcMain.handle(CHANNEL, …)`, single quotes, a template, or a one-way `ipcMain.on(…)` — is
   * invisible to it, and an invisible channel is an undriven one that this sweep would still call
   * complete (validator RESERVATION-4). Rather than chase shapes, the counters below let a caller
   * REFUSE when the source contains a registration this parser cannot see; the desktop suite asserts
   * that refusal against the real `main.js`.
   */
  function registeredIpcChannels(mainSource) {
    return [...String(mainSource || "").matchAll(/ipcMain\.handle\(\s*"([^"]+)"/g)].map((m) => m[1]);
  }

  /**
   * How many registrations exist in total, by the crudest possible count, so a caller can compare it
   * with what the parser above could NAME. `handle_total !== parsed` or any `ipcMain.on` means the
   * coverage claim is not available on this source.
   */
  function ipcRegistrationCounts(mainSource) {
    const src = String(mainSource || "");
    return {
      parsed: registeredIpcChannels(src).length,
      handle_total: (src.match(/ipcMain\.handle\(/g) || []).length,
      one_way_total: (src.match(/ipcMain\.on\(/g) || []).length,
    };
  }

  /**
   * `name: … ipcRenderer.invoke("<channel>"…)` — what the bridge exposes, and the `on*` streams.
   *
   * The property name is taken by walking BACK from each `ipcRenderer.invoke(` to the nearest
   * `name:` at the start of a line, rather than by matching a parameter list: the first form used
   * `\([^)]*\)`, which any default value or destructured parameter would have defeated silently
   * (spec-audit F8). `invokeTotal` is the crude count, so a caller can refuse when a call exists that
   * this walk could not attribute.
   */
  function exposedInvokeChannels(preloadSource) {
    const src = String(preloadSource || "");
    const out = [];
    for (const m of src.matchAll(/ipcRenderer\.invoke\(\s*"([^"]+)"/g)) {
      const head = src.slice(0, m.index);
      const name = [...head.matchAll(/(?:^|[{,]\s*)\n?\s*([A-Za-z0-9_$]+)\s*:/gm)].pop();
      out.push({ method: name ? name[1] : null, channel: m[1] });
    }
    return out;
  }

  /** The `on*` subscribers — main→renderer streams, which are not invocations and are not driven. */
  function exposedStreamMethods(preloadSource) {
    const src = String(preloadSource || "");
    const out = [];
    for (const m of src.matchAll(/ipcRenderer\.on\(\s*"([^"]+)"/g)) {
      const head = src.slice(0, m.index);
      const name = [...head.matchAll(/(?:^|[{,]\s*)\n?\s*([A-Za-z0-9_$]+)\s*:/gm)].pop();
      out.push({ method: name ? name[1] : null, channel: m[1] });
    }
    return out;
  }

  function preloadCounts(preloadSource) {
    const src = String(preloadSource || "");
    return {
      invoke_total: (src.match(/ipcRenderer\.invoke\(/g) || []).length,
      on_total: (src.match(/ipcRenderer\.on\(/g) || []).length,
    };
  }

  /**
   * Drive them all. `surface` is the preload bridge (`window.sovereign`); `ctx` carries the conductor
   * pane id and its CURRENT terminal geometry.
   */
  async function runChannelSweep(surface, ctx) {
    const s = surface || {};
    const state = {
      conductorPaneId: (ctx && ctx.conductorPaneId) || null,
      scratchPaneId: null,
      cols: (ctx && ctx.cols) || 80,
      rows: (ctx && ctx.rows) || 24,
    };
    const out = { ok: true, probe: SWEEP_PROBE, scratch_pane_id: null, uncovered: [], missing: [], channels: [] };

    // A method on the bridge that no entry names is an undriven channel — the exact place a dynamic
    // release would hide from this assertion. It fails the sweep; it is never skipped quietly.
    const named = new Set(SWEEP.map((e) => e.method));
    for (const key of Object.keys(s)) {
      if (typeof s[key] !== "function" || /^on[A-Z]/.test(key)) continue;   // `onX` are main→renderer streams
      if (!named.has(key)) { out.uncovered.push(key); out.ok = false; }
    }

    for (const entry of SWEEP) {
      const row = { method: entry.method, channel: entry.channel, pane: entry.pane, invoked: false, error: null };
      const target = entry.pane === "conductor" ? state.conductorPaneId
        : entry.pane === "scratch" ? state.scratchPaneId : "n/a";
      if (typeof s[entry.method] !== "function") {
        out.missing.push(entry.method);
        row.error = "the bridge does not expose this intent";
        out.ok = false;
        out.channels.push(row);
        continue;
      }
      if (!target) {
        // Fail closed: an intent aimed at a pane that does not exist is NOT re-aimed at another one.
        row.error = `no ${entry.pane} pane to target`;
        out.ok = false;
        out.channels.push(row);
        continue;
      }
      let result = null;
      try {
        result = await s[entry.method](...entry.args(state));
      } catch (e) {
        row.error = String((e && e.message) || e);
      }
      row.invoked = true;
      if (entry.pane === "create") {
        state.scratchPaneId = typeof result === "string" ? result : (result && result.id) || null;
        row.created = state.scratchPaneId;
        if (!state.scratchPaneId) out.ok = false;
      }
      out.channels.push(row);
    }
    out.scratch_pane_id = state.scratchPaneId;
    return out;
  }

  const API = {
    SWEEP, SWEEP_PROBE, CONDUCTOR_INPUT_BYTES, CONDUCTOR_SAFE_METHODS,
    runChannelSweep, registeredIpcChannels, ipcRegistrationCounts,
    exposedInvokeChannels, exposedStreamMethods, preloadCounts,
  };
  // UMD, for the same reason wav.js is: the driver is exercised headlessly against a fake bridge and
  // runs in the renderer against the real one. A second copy would drift from the bridge it drives.
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (typeof window !== "undefined") window.SovereignChannelSweep = API;
})();
