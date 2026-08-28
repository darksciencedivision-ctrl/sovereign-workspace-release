"use strict";
/**
 * Phase 19 unit 19.3 — the U328 in-Electron receipt's own falsifiability.
 *
 * A self-check is evidence only if it can FAIL. `PHASE19_3_SYSTEM_PANE_WRITE_SELFCHECK*.json` is
 * the D-P16-0 receipt this unit closes on, so this file drives the REAL check function against a
 * simulated runtime and proves each of its four legs goes red on the exact defect it exists to
 * catch — a gate that never refuses, a refusal reported while the bytes go out anyway, an own-echo
 * exclusion that never happens, and a sessionless pane read as clean.
 *
 * The doubles here stand in for Electron (a window whose `executeJavaScript` answers a fake screen)
 * and for main.js's bindings. What they CANNOT prove is the wiring — that main.js hands the check
 * its production write path rather than a lookalike — which is `system-pane-write-wiring.test.js`'s
 * job and the mutation harness's. Together: this file says the check discriminates, that one says
 * the thing it discriminates is the shipped one.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// Receipts are written at module load-time paths; keep every run of this file out of the evidence
// directory (the receipt-path override exists for exactly this, 18B review round 1).
const RECEIPT_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "u328-selfcheck-"));
process.env.SHELL_SELFCHECK_RECEIPT_DIR = RECEIPT_DIR;
const { runSystemPaneWriteSelfCheck, RECEIPT_PATH } = require("../selfcheck/system-pane-write-selfcheck");
const { classifyProviderScreen } = require("../control/provider-readiness");

const TRUST_LINE = "do you trust the contents of this project";

/**
 * A simulated runtime: panes hold a screen string, the operator's input path appends to it, and the
 * system write path is the REAL rule under test — classify, then append only if allowed.
 *
 * `flaws` re-introduces one defect at a time, which is what makes the assertions below falsifiable
 * rather than self-confirming.
 */
function fakeRuntime(flaws = {}) {
  const screens = new Map();
  const world = {
    banner: "SOVEREIGN_U328_PANE_READY",
    refusedOnce: false,
    refusalFor(paneId) {
      if (flaws.gateNeverRefuses) return null;   // mutation P1: the gate refuses nothing, anywhere
      if (!screens.has(paneId)) {
        return flaws.sessionlessIsClean ? null : {
          state: "STALLED", terminal_state: "PANE_SCREEN_UNREADABLE",
          reason: "the pane screen could not be read, so no write into it can be shown to be safe",
        };
      }
      return classifyProviderScreen(null, screens.get(paneId));
    },
    /** The real shape: gate, write the body, gate AGAIN for the submit key — that second read sees
     *  the pane's echo of the body, which is why the exclusion exists. A submitted line advances the
     *  pane's prompt token, exactly as a real shell's prompt does. */
    async writePrompt(paneId, body) {
      const before = world.refusalFor(paneId);
      if (before) {
        world.refusedOnce = true;
        // The invariant-1 defect: report the refusal, send the bytes anyway.
        if (flaws.refusesButWrites) screens.set(paneId, `${screens.get(paneId) || ""}\n${body}`);
        // The WORSE one: withhold the body, emit the bare carriage return — the byte that answers a
        // numbered menu, and the one that leaves no needle behind it.
        if (flaws.refusesButSubmits) {
          screens.set(paneId, `${screens.get(paneId) || ""}\nSOVEREIGN_U328_PROMPT> `);
        }
        return false;
      }
      if (!screens.has(paneId)) return false;
      screens.set(paneId, `${screens.get(paneId)}\n${body}`);   // the body is out; the pane echoes it
      const echoed = screens.get(paneId);
      const judged = flaws.noEchoExclusion ? echoed : echoed.split(body).join(" ");
      const submitRefusal = flaws.gateNeverRefuses ? null : classifyProviderScreen(null, judged);
      if (submitRefusal) return false;       // a withheld submit leaves the body in the input box
      screens.set(paneId, `${screens.get(paneId)}\nSOVEREIGN_U328_PROMPT> `);   // the line submitted
      return true;
    },
  };
  const ctx = {
    win: {
      webContents: {
        async executeJavaScript(expr) {
          const pane = (/"([^"]+)"/.exec(expr) || [])[1];
          if (expr.includes("hasTerm")) return screens.has(pane);
          if (expr.includes("paneText")) return screens.get(pane) || null;
          if (expr.includes("window.sovereign.input")) {
            const data = (/,\s*"((?:[^"\\]|\\.)*)"\)$/.exec(expr) || [])[1] || "";
            screens.set(pane, `${screens.get(pane) || ""}\n${JSON.parse(`"${data}"`)}`);
            return true;
          }
          return null;
        },
      },
    },
    isSupervised: () => true,
    createPaneWithSession: (spec) => {
      const id = `pane-${screens.size + 1}`;
      screens.set(id, `${world.banner}\n${spec.title}\nSOVEREIGN_U328_PROMPT> `);
      return id;
    },
    writePanePrompt: (paneId, body) => world.writePrompt(paneId, body),
    paneWriteRefusalFor: (paneId) => world.refusalFor(paneId),
    killSession: () => {},
    log: () => {},
  };
  return { ctx, screens, world };
}

function cleanup() {
  try { fs.rmSync(RECEIPT_PATH, { force: true }); } catch { /* nothing written */ }
}

test("the healthy runtime passes every leg, and the receipt says what it measured", async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, true, `expected PASS, got ${JSON.stringify(receipt.legs)}`);
  assert.strictEqual(receipt.legs.clean_pane_write.ok, true);
  assert.strictEqual(receipt.legs.modal_pane_refused.terminal_state, "WORKSPACE_TRUST_REQUIRED");
  assert.strictEqual(receipt.legs.own_echo_not_self_refusing.ok, true);
  assert.strictEqual(receipt.legs.sessionless_pane_unreadable.ok, true);
  // provenance every machine-emitted receipt in docs/evidence/receipts carries (U337's standard)
  assert.strictEqual(receipt.check, "phase-19.3.system-pane-write");
  assert.ok(receipt.source && Object.hasOwn(receipt.source, "commit"));
  assert.ok(Object.hasOwn(receipt.source, "tracked_product_tree_clean"));
  assert.ok(receipt.started && receipt.finished && receipt.electron_main_pid > 0);
  assert.strictEqual(receipt.live_exchanges, 0);
  // D-LOOP-1: both panes it opened are killed inside the check, not left for the launcher
  assert.strictEqual(receipt.sessions_killed_in_unit.length, 2);
  assert.ok(fs.existsSync(RECEIPT_PATH), "the receipt must be written to disk");
  cleanup();
});

test("a gate that never refuses fails the check", async () => {
  const { ctx } = fakeRuntime({ gateNeverRefuses: true });
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false);
  assert.strictEqual(receipt.legs.modal_pane_refused.ok, false,
    "a modal on screen must not be answerable");
  assert.strictEqual(receipt.legs.sessionless_pane_unreadable.ok, false,
    "a gate that refuses nothing also stops refusing the pane it cannot read");
  cleanup();
});

test("a shell that reports the refusal and writes anyway fails the check (invariant 1)", async () => {
  // The dangerous one: `written: false` is returned, the operator is told nothing was sent, and the
  // carriage return that answers the modal went out regardless. Only the ABSENCE leg sees it.
  const { ctx } = fakeRuntime({ refusesButWrites: true });
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false);
  assert.strictEqual(receipt.legs.modal_pane_refused.written, false);
  assert.strictEqual(receipt.legs.modal_pane_refused.withheld_body_observed, true,
    "the check must observe the bytes that went out behind the refusal");
  cleanup();
});

test("a shell that withholds the body but still sends the Enter fails the check", async () => {
  // The finding the 19.3 review made: the carriage return is the byte that answers a numbered menu,
  // and it leaves no needle. Watching for the BODY's absence would call this defect a pass.
  const { ctx } = fakeRuntime({ refusesButSubmits: true });
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false);
  assert.strictEqual(receipt.legs.modal_pane_refused.withheld_body_observed, false,
    "the body really was withheld — this defect is invisible to a body-only watch");
  assert.strictEqual(receipt.legs.modal_pane_refused.stray_submit_observed, true,
    "the pane's own submitted-line count is what catches it");
  cleanup();
});

test("an absence measured through a dead renderer bridge is not a pass", async () => {
  // `paneText` answers null when `executeJavaScript` fails, which makes every absence vacuously
  // true. The leg carries a positive control taken AFTER the window for exactly that reason.
  const { ctx, world } = fakeRuntime();
  const real = ctx.win.webContents.executeJavaScript;
  ctx.win.webContents.executeJavaScript = async (expr) => {
    // die exactly when the modal leg's absence window opens — not before, or an earlier leg fails
    // for an unrelated reason and this test would pass without exercising anything
    if (expr.includes("paneText") && world.refusedOnce) throw new Error("renderer gone");
    return real(expr);
  };
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false, "a blind window must not be reported as a quiet one");
  cleanup();
});

test("dropping the own-echo exclusion fails the check", async () => {
  const { ctx } = fakeRuntime({ noEchoExclusion: true });
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false);
  assert.strictEqual(receipt.legs.own_echo_not_self_refusing.ok, false,
    "a body quoting modal text must still be delivered — otherwise a notice silences itself");
  cleanup();
});

test("a sessionless pane read as clean fails the check", async () => {
  const { ctx } = fakeRuntime({ sessionlessIsClean: true });
  const receipt = await runSystemPaneWriteSelfCheck(ctx);
  assert.strictEqual(receipt.ok, false);
  assert.strictEqual(receipt.legs.sessionless_pane_unreadable.ok, false);
  cleanup();
});

test("a runtime that exposes no production write path fails before it spawns anything", async () => {
  const { ctx } = fakeRuntime();
  const receipt = await runSystemPaneWriteSelfCheck({ ...ctx, writePanePrompt: undefined });
  assert.strictEqual(receipt.ok, false);
  assert.match(receipt.error, /production system→pane write path/);
  assert.deepStrictEqual(receipt.panes, [], "nothing may be spawned once the wiring is absent");
  cleanup();
});

test("the trust line the check types is one classifyProviderScreen actually classifies", () => {
  // If the classifier's wording ever changes, this check would type a line nothing recognises and
  // its modal leg would go green for the wrong reason — a self-check quietly measuring nothing.
  const verdict = classifyProviderScreen(null, `some output\n${TRUST_LINE}\n> `);
  assert.ok(verdict && verdict.terminal_state === "WORKSPACE_TRUST_REQUIRED");
});
