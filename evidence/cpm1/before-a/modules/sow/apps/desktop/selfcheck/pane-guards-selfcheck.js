"use strict";
/**
 * Phase 17D `.close` in-Electron self-check (D-P16-0 binding) — the pane-guard receipt.
 *
 * Two things the operator's own launch produced, proven inside the packaged runtime:
 *
 *  1. **U73** — the renderer fits pane 1 (the conductor PLACEHOLDER, no ConPTY until the governed
 *     launch admits one) and the shell used to answer that with a thrown handler. This drives the
 *     REAL preload bridge (`window.sovereign.resize`) at the REAL `pane:resize` handler and asserts
 *     an ANSWER comes back — a refusal with a reason — rather than a rejected invoke. It then proves
 *     the guard did not become a refusal of real work (an admitted session IS resized), and that a
 *     geometry the least-trusted surface made up is refused before a ConPTY sees it (invariant 29).
 *     The falsification is direct: re-inline the old dereference and leg 3 rejects instead.
 *
 *  2. **U69** — the ONE micro-link the 16A receipt could not exercise: the browser delivering a
 *     focused textarea's keydown into xterm's `onData`. It is attempted here with real OS-level input
 *     events, and whatever happens is RECORDED, not asserted: a gate that depended on synthetic key
 *     delivery into an automated window would be a gate on someone else's harness. What this leg adds
 *     over 16A is one layer, not a closure — 16A drove `term.input()`, which starts BELOW the DOM;
 *     this drives the focused helper textarea's own text-input path and counts what the DOM saw. The
 *     load-bearing input proof stays the one 16A already carries.
 *
 * It spawns one supervised pane, tears it down in-unit (D-LOOP-1), starts no live model, spends no
 * live exchange, and touches no credential.
 */
const fs = require("fs");
const path = require("path");

const RECEIPT_PATH = path.resolve(
  __dirname, "..", "..", "..", "docs", "evidence", "receipts", "PHASE17D_CLOSE_SELFCHECK.json"
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(pred, timeoutMs, stepMs) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    let ok = false;
    try { ok = await pred(); } catch { ok = false; }
    if (ok) return true;
    if (Date.now() >= deadline) return false;
    await sleep(stepMs);
  }
}

/**
 * Call `window.sovereign.resize(...)` in the renderer — the exact bridge the pane's own
 * `term.onResize` uses — and report either the handler's answer or the rejection it produced.
 * A rejected invoke is what a THROWN handler looks like from the renderer's side, which is the
 * whole of U73; it is captured, never swallowed.
 */
async function bridgeResize(win, paneId, cols, rows) {
  const expr = `(async () => {
    try { return { rejected: false, answer: await window.sovereign.resize(
      ${JSON.stringify(paneId)}, ${JSON.stringify(cols)}, ${JSON.stringify(rows)}) }; }
    catch (e) { return { rejected: true, error: String((e && e.message) || e) }; }
  })()`;
  try { return await win.webContents.executeJavaScript(expr); }
  catch (e) { return { rejected: true, error: `executeJavaScript failed: ${(e && e.message) || e}` }; }
}

async function paneText(win, paneId) {
  const expr = `window.__sovereignSelfCheck && window.__sovereignSelfCheck.paneText(${JSON.stringify(paneId)})`;
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function pollNeedle(win, paneId, needle, timeoutMs) {
  let last = null;
  const hit = await waitFor(async () => {
    last = await paneText(win, paneId);
    return typeof last === "string" && last.includes(needle);
  }, timeoutMs, 200);
  return hit ? last : null;
}

/**
 * Type with real OS-level input events (U69).
 *
 * The 16A version sent `keyCode: "\r"` for the newline. Electron's `sendInputEvent` takes an
 * ACCELERATOR key name there, not a control character, so that submit key named nothing and could
 * never have been delivered — the harness was asking a question it had disabled the end of. It is
 * "Return" here. Whether the rest arrives is the open part of U69.
 */
async function typeDom(win, str) {
  for (const ch of str) {
    const isCR = ch === "\r" || ch === "\n";
    const keyCode = isCR ? "Return" : ch;
    win.webContents.sendInputEvent({ type: "keyDown", keyCode });
    if (!isCR) win.webContents.sendInputEvent({ type: "char", keyCode });
    win.webContents.sendInputEvent({ type: "keyUp", keyCode });
    await sleep(25);
  }
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, conductorPaneIdOf, paneModel, log } = ctx;
  const receipt = {
    check: "phase-17d.close",
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    // ---- U73: the sessionless conductor placeholder --------------------------------------------
    conductor_pane_id: null,
    conductor_pane_sessionless: false,
    placeholder_resize: null,          // the handler's ANSWER (or the rejection, if it threw)
    placeholder_answered: false,       // an answer came back at all — the U73 property
    placeholder_refused_with_reason: false,
    // ---- U73: the guard must not refuse real work ----------------------------------------------
    worker_pane_id: null,
    live_resize: null,
    live_resize_accepted: false,
    // ---- invariant 29: the renderer's numbers are checked ---------------------------------------
    bad_dimensions: null,
    bad_dimensions_refused: false,
    live_session_survived_bad_dimensions: false,
    // ---- U69: the physical keystroke micro-link (recorded, never asserted) ----------------------
    u69: {
      attempted: false,
      active_element: null,
      window_focus: null,              // WHY, when it fails: Chromium drops key events at an unfocused widget
      keystroke_leg_events: null,      // what the DOM actually saw: keydowns, and text-input events
      keydown_seen_by_renderer: false, // did the event reach the DOM at all, before xterm is blamed?
      focus_after_typing: null,        // …and was the textarea still focused when the loop finished?
      dom_keystroke_echo: false,
      dom_textinput_echo: false,       // text input ON THE FOCUSED TEXTAREA + a delivered Enter → echo
      xterm_oninput_echo: false,       // the 16A load-bearing control leg, re-run here
      verdict: null,
    },
    error: null,
  };
  const BANNER = "SOVEREIGN_17D_BANNER";
  const PROBE_DOM = "SOVEREIGN_17D_ECHO_DOM";
  const PROBE_TEXTINPUT = "SOVEREIGN_17D_ECHO_TEXTINPUT";
  const PROBE_XTERM = "SOVEREIGN_17D_ECHO_XTERM";
  try {
    // 1. supervision READY — no naked session is reachable from here (invariant 2)
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) throw new Error("supervision never became READY within 25 s");

    // 2. pane 1 is the conductor PLACEHOLDER: it exists and holds no session. This is the exact
    //    startup state the operator's log complained about — the check would be vacuous without it.
    const conductorPaneId = conductorPaneIdOf();
    receipt.conductor_pane_id = conductorPaneId;
    const pane1 = paneModel().panes.get(conductorPaneId) || null;
    receipt.conductor_pane_sessionless = Boolean(pane1) && !pane1.sessionId;
    if (!receipt.conductor_pane_sessionless) {
      throw new Error(`pane ${conductorPaneId} is not the sessionless placeholder this check needs `
        + `(${pane1 ? `sessionId=${pane1.sessionId}` : "no such pane"})`);
    }

    // 3. THE DEFECT: resize the placeholder through the real bridge. An ANSWER is the property.
    const placeholder = await bridgeResize(win, conductorPaneId, 120, 40);
    receipt.placeholder_resize = placeholder;
    receipt.placeholder_answered = placeholder.rejected === false;
    receipt.placeholder_refused_with_reason = Boolean(
      receipt.placeholder_answered && placeholder.answer
      && placeholder.answer.resized === false && placeholder.answer.reason);
    log(`[selfcheck] placeholder resize → ${JSON.stringify(placeholder)}`);
    if (!receipt.placeholder_refused_with_reason) {
      throw new Error("the sessionless pane's resize did not come back as a reasoned refusal (U73)");
    }

    // 4. the guard must not have become a refusal of real work: spawn a supervised pane and resize it
    const paneId = createPaneWithSession({
      file: "powershell.exe",
      args: ["-NoLogo", "-NoProfile", "-NoExit", "-Command", `Write-Output '${BANNER}'`],
      title: "17d-selfcheck",
    });
    receipt.worker_pane_id = paneId;
    const termReady = await waitFor(
      async () => win.webContents.executeJavaScript(
        `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`), 15000, 200);
    if (!termReady) throw new Error("the renderer never created an xterm view for the supervised pane");
    if (!(await pollNeedle(win, paneId, BANNER, 25000))) {
      throw new Error("the supervised pane never rendered its banner (output feed)");
    }
    const live = await bridgeResize(win, paneId, 100, 30);
    receipt.live_resize = live;
    receipt.live_resize_accepted = Boolean(!live.rejected && live.answer && live.answer.resized === true);
    log(`[selfcheck] live resize → ${JSON.stringify(live)}`);
    if (!receipt.live_resize_accepted) throw new Error("an admitted session was refused a real resize");

    // 5. invariant 29: a geometry no ConPTY can take is refused, and the session is untouched by it
    const bad = await bridgeResize(win, paneId, 0, 0);
    receipt.bad_dimensions = bad;
    receipt.bad_dimensions_refused = Boolean(
      !bad.rejected && bad.answer && bad.answer.resized === false && bad.answer.reason);
    const after = await bridgeResize(win, paneId, 90, 28);
    receipt.live_session_survived_bad_dimensions = Boolean(
      !after.rejected && after.answer && after.answer.resized === true);
    if (!receipt.bad_dimensions_refused || !receipt.live_session_survived_bad_dimensions) {
      throw new Error("a made-up geometry was not refused cleanly (invariant 29)");
    }

    // 6. U69 — attempted, recorded, never asserted. See the header.
    // Take the foreground as hard as Electron allows first: an unfocused render widget DROPS
    // synthetic key events, and "xterm internals" is a guess until the focus state is written down.
    try {
      win.show();
      win.setAlwaysOnTop(true);
      win.focus();
      win.moveTop();
      win.webContents.focus();
    } catch { /* background */ }
    await sleep(300);
    await win.webContents.executeJavaScript(
      `window.__sovereignSelfCheck.focusPane(${JSON.stringify(paneId)})`);
    await sleep(200);
    receipt.u69.active_element = await win.webContents.executeJavaScript(
      "document.activeElement && (document.activeElement.className || document.activeElement.tagName)"
    ).catch(() => null);
    receipt.u69.window_focus = {
      visible: win.isVisible(),
      window_focused: win.isFocused(),
      webcontents_focused: win.webContents.isFocused(),
    };
    // A keydown listener at the top of the document: it sees the event BEFORE xterm's own handler and
    // regardless of what xterm does with it, so a false here means the event never arrived at the DOM
    // and a true with no echo means it arrived and xterm did not turn it into data.
    // Count what actually arrives, rather than inferring a mechanism afterwards: keydowns, and the
    // text-input events xterm builds printable characters from. "The key arrived and produced no
    // data" is a measurement; "Chromium did not translate it" was a guess until these were recorded.
    await win.webContents.executeJavaScript(`(() => {
      window.__u69 = { keydowns: 0, first: null, textinput: 0, beforeinput: 0, input: 0 };
      document.addEventListener("keydown", (e) => {
        window.__u69.keydowns += 1;
        if (!window.__u69.first) {
          window.__u69.first = {
            key: e.key, code: e.code, isTrusted: e.isTrusted,
            target: (e.target && (e.target.className || e.target.tagName)) || null,
          };
        }
      }, true);
      for (const type of ["textInput", "beforeinput", "input"]) {
        document.addEventListener(type, () => {
          window.__u69[type === "textInput" ? "textinput" : type] += 1;
        }, true);
      }
      return true;
    })()`).catch(() => false);
    receipt.u69.attempted = true;
    await typeDom(win, `echo ${PROBE_DOM}\r`);
    receipt.u69.keystroke_leg_events = await win.webContents
      .executeJavaScript("window.__u69").catch(() => null);
    receipt.u69.keydown_seen_by_renderer = Boolean(
      receipt.u69.keystroke_leg_events && receipt.u69.keystroke_leg_events.keydowns > 0);
    // Focus was sampled BEFORE typing; a loop that ran for a second could have lost it midway, which
    // would be a different explanation for the same silence. Read it again on the way out.
    receipt.u69.focus_after_typing = await win.webContents.executeJavaScript(
      "document.activeElement && (document.activeElement.className || document.activeElement.tagName)"
    ).catch(() => null);
    receipt.u69.dom_keystroke_echo = (await pollNeedle(win, paneId, PROBE_DOM, 12000)) != null;

    // The link one layer down, and the reason it is worth its own leg: xterm.js does NOT build data
    // for printable characters in its keydown handler — it lets them land in the focused helper
    // TEXTAREA and reads the resulting text-input event. `insertText` drives Chromium's text-input
    // pipeline into that textarea, so this exercises focus → textarea input → xterm.onData →
    // pane:input → PTY → echo, with only the OS driver layer above it left synthetic. The submit key
    // is a real delivered keydown, because Enter IS handled in xterm's keydown path.
    await win.webContents.insertText(`echo ${PROBE_TEXTINPUT}`);
    await sleep(150);
    win.webContents.sendInputEvent({ type: "keyDown", keyCode: "Return" });
    win.webContents.sendInputEvent({ type: "keyUp", keyCode: "Return" });
    receipt.u69.dom_textinput_echo = (await pollNeedle(win, paneId, PROBE_TEXTINPUT, 12000)) != null;
    try { win.setAlwaysOnTop(false); } catch { /* window already gone */ }

    // the control: term.input() fires the exact onData handler a delivered keystroke would reach
    await win.webContents.executeJavaScript(
      `window.__sovereignSelfCheck.typeInto(${JSON.stringify(paneId)}, ${JSON.stringify(`echo ${PROBE_XTERM}\r`)})`);
    receipt.u69.xterm_oninput_echo = (await pollNeedle(win, paneId, PROBE_XTERM, 12000)) != null;
    // Say what was measured and no more. This receipt cannot close U69 and does not claim to: what it
    // does is move the automated proof one layer up from 16A's `term.input()` and record precisely
    // where the automation stops — leaving the operator's own keyboard as the remaining evidence,
    // which is where directive §16 puts it anyway.
    receipt.u69.verdict = receipt.u69.dom_keystroke_echo
      ? "whole chain delivered in automation: OS-level key event → focused xterm textarea → onData → PTY → echo"
      : receipt.u69.dom_textinput_echo
        ? "proven from the focused textarea down: text input on the xterm helper textarea + a delivered "
          + "Enter keydown → xterm.onData → pane:input → PTY → echo (16A's term.input() started below "
          + "this). NOT exercised: a real OS key event and Chromium's handling of it — the synthetic "
          + "keydowns arrived at the textarea and produced no terminal data (see keystroke_leg_events "
          + "for the text-input events counted during that leg), but this run isolated no mechanism "
          + "for that and does not claim one. The unexercised layer is the operator's keyboard."
        : receipt.u69.keydown_seen_by_renderer
          ? "the synthetic keys REACHED the DOM and produced no terminal data, and the textarea text-input "
            + "leg did not echo either — the shell wiring below is proven by xterm_oninput_echo; operator use closes U69"
          : "the synthetic keys never reached the renderer's DOM at all (see window_focus) — nothing about "
            + "this link was tested; the shell wiring below it is proven by xterm_oninput_echo; operator use closes U69";
    log(`[selfcheck] U69 dom=${receipt.u69.dom_keystroke_echo} textinput=${receipt.u69.dom_textinput_echo} `
      + `xterm=${receipt.u69.xterm_oninput_echo} (activeElement=${receipt.u69.active_element})`);
    if (!receipt.u69.xterm_oninput_echo) {
      throw new Error("the 16A input control leg did not echo — the pane input path itself regressed");
    }

    receipt.ok = receipt.supervision_ready && receipt.conductor_pane_sessionless
      && receipt.placeholder_refused_with_reason && receipt.live_resize_accepted
      && receipt.bad_dimensions_refused && receipt.live_session_survived_bad_dimensions
      && receipt.u69.xterm_oninput_echo;
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  }
  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron,
    node: process.versions.node,
    chrome: process.versions.chrome,
    platform: process.platform,
    arch: process.arch,
  };
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] pane-guards ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runPaneGuardsSelfCheck: run, RECEIPT_PATH };
