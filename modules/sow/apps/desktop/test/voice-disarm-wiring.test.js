"use strict";
/**
 * Phase 17C `.disarm` (U166) — the WIRING net the enumeration test does not provide.
 *
 * `voice-turn-authority.test.js` pins which source STRINGS may end a voice turn. The gate-validator
 * showed that is not the same thing as pinning which CALL SITES may end one: it re-added a
 * `disarm("electron_main_before_input_event", …)` call inside main's `pane:input` IPC handler — the
 * exact bypass this sub-step found and rejected, because xterm.js also emits `onData` for terminal
 * replies the pane's own process elicits — and all 511 tests stayed green. The audit row would have
 * read `electron_main_before_input_event`, indistinguishable from a real keystroke.
 *
 * `main.js` cannot be required headlessly (it pulls in electron), so this reads its source. A source
 * assertion is a weak instrument in general; here it is the right one, because the property is
 * exactly "this call does not appear in that handler".
 *
 * U175 (validator R-2a) — the residual the first form left open. Asserting the handler body contains
 * no `.disarm(` pins the DIRECT bypass and nothing else: inserting
 * `handleOperatorResumeInput({type:"keyDown",key:"a"}, …)` into the same handler left the suite green,
 * because every release call site was still, textually, inside `handleOperatorResumeInput`.
 *
 * The first attempt at a fix was a DENY-list: compute which of main's top-level functions reach a
 * release, and assert the handler names none of them. The spec-auditor took it apart — it fails OPEN
 * on every callee the analysis cannot resolve. `main.js` declares three functions INSIDE `registerIpc`
 * (`captureFromRef`, `captureFromPcm`, `foldCapture`), so a one-line relay declared beside them was
 * not a node of the graph and the whole suite stayed green; so did a call built by concatenation
 * (`eval("conductorVoiceAuthority" + ".disarm(…)")`) and a bare `conductorVoiceAuthority.stop()`,
 * which clears `_active` too. A deny-list is also the wrong shape for this repo: everything else in
 * this unit demands POSITIVE evidence (Buildout §4, fail closed on ambiguity).
 *
 * So the guard is the closed form the register itself prescribed: **enumerate every call in the
 * `pane:input` handler, require each callee to be one of three named, audited functions, and walk
 * main's own functions out from there so that no body on that path holds a release.** A callee it
 * cannot name is reported as `<computed>`, which no allow-list contains.
 *
 * Its scope, stated rather than implied — the second review pass caught this file claiming a
 * universal it did not have, which is the same certainty inflation the rest of the unit was
 * correcting. What is pinned: every call in this handler written as `name(`, `a.b(`, `x?.(`, `)(` or
 * `](`; a rebinding of an audited name inside the handler; a release in ANY main.js function reachable
 * from it; and the absence of template literals, which would otherwise hide both a tagged call and
 * `${…}` code. What is NOT: a callee reached by a getter, a Proxy trap, or a reference stored here and
 * invoked elsewhere — those are not calls in this body. That residual is U177.
 *
 * The THIRD review pass closed two more classes, both of which it falsified against this file first:
 *
 *  * **A release needs no call at all.** `conductorVoiceAuthority._active = null` in the handler
 *    (also `delete`, a computed member, or via a local alias) lifts the restriction with no audit row
 *    at all — invisible to `RELEASE_SINK`, which only matches `.method(`, and to the receipt leg that
 *    enumerates provenance rows (validator BLOCKER-3). Pinned two ways now: the handler and everything
 *    reachable from it may not NAME the service, and — file-wide — every use of it in `main.js` must be
 *    a method call on it, never an alias, a destructuring, a computed member, a `delete`, or a write.
 *  * **The channel next door.** The property was per-CHANNEL, so the same relay moved into
 *    `pane:focus` left this suite and all 522 desktop tests green (validator RESERVATION-1). Every
 *    `ipcMain.handle` channel is now walked, and only the channels audited in
 *    `CHANNEL_MAY_REACH_RELEASE` may reach a release at all.
 *
 * What remains out of scope after that is the DYNAMIC form — a getter, a Proxy trap, or a reference
 * stored on one channel and invoked from another — which no source reading can see. It is a runtime
 * assertion, recorded as **U177**, not implied here.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");

/**
 * The body of `ipcMain.handle("<channel>", …)`, by brace matching from the handler's opening.
 *
 * The channel is a string literal, so it is located on the comments-only view; the body is sliced
 * from the structural view, where a brace inside a comment or a literal cannot end it early. Both
 * views preserve every offset of `main.js`, so the two indices are the same indices.
 */
function ipcHandlerBody(channel) {
  const at = UNCOMMENTED.indexOf(`ipcMain.handle("${channel}"`);
  assert.notEqual(at, -1, `no ipcMain.handle for ${channel}`);
  // The arrow must lie INSIDE this call's own argument list, or a handler registered by name
  // (`ipcMain.handle("pane:input", paneInput)`) would silently slice the NEXT handler's body and the
  // suite would assert against code that is not this channel's (auditor F6).
  const args = CODE.indexOf("(", at);
  const argsEnd = matchDelim(CODE, args, "(", ")");
  const arrow = CODE.indexOf("=>", args);
  assert.ok(arrow > 0 && arrow < argsEnd,
    `the ${channel} handler is not an inline arrow — this test reads the body it registers`);
  // A block body's `{` follows the arrow with nothing but whitespace between. Anything else means an
  // EXPRESSION body, and the whole expression is the body: `(…) => ({ write: manager.write })` has a
  // `{` too, and slicing that object literal as the handler let a call sitting after it go unread
  // (validator RES-2).
  const open = CODE.indexOf("{", arrow);
  const blockBody = open > 0 && open < argsEnd && CODE.slice(arrow + 2, open).trim() === "";
  if (blockBody) return CODE.slice(open, matchDelim(CODE, open, "{", "}") + 1);
  return CODE.slice(arrow + 2, argsEnd);   // expression-bodied arrow: the expression IS the body
}

/**
 * The ways the restriction is released, as METHOD names on the authority service.
 *
 * `disarm` ends an admitted turn, `reset` releases one because the supervised process is gone,
 * `cancel` voids a turn still pending admission — a lesser release, but a release: after it, the next
 * prompt is unrestricted — and `stop()` clears `_active`/`_pending` outright when the authority
 * service shuts down (auditor F4; it is reached only from teardown today, and the fact that it
 * releases without provenance is its own register item). All are main-owned; none may be reachable
 * from renderer bytes.
 */
const RELEASE_SINK = /conductorVoiceAuthority\s*\??\.\s*(disarm|reset|cancel|stop)\s*(?:\?\.)?\s*[(`]/g;

/**
 * Where each release is allowed to be called from. A release is not merely "somewhere in main" — it
 * belongs to exactly one function, and naming that function is the whole claim (auditor F-E: the
 * earlier form pinned only `disarm` and let the other three sit anywhere).
 */
const RELEASE_OWNER = {
  disarm: "handleOperatorResumeInput",   // the OS input path, via before-input-event
  reset: "onConductorSessionEnded",      // the observed node-pty exit
  cancel: "deliverConductorChat",        // voids a turn this same dispatch minted, before admission
  // Both paths call stop only after bounded SessionManager shutdown confirms the PTYs are gone.
  stop: ["teardownSelfCheck", "completeNormalQuit"],
};

/**
 * Which `ipcMain.handle` channels are allowed to reach a release AT ALL, and why.
 *
 * The per-channel property was never the whole one: the validator moved the `pane:input` relay into
 * `pane:focus` and every test in the repo stayed green (RESERVATION-1). Renderer bytes are renderer
 * bytes whichever channel carries them, so the walk below covers all of them and this is the closed
 * list of exceptions. `voice:capture` and `conductor:operator-text` are legitimate because each
 * MINTS a turn (`arm`) and the delivery it dispatches may `cancel` that same turn before admission —
 * a turn nobody else has seen.
 * No channel may reach `disarm` or `reset`: those two are answers to facts main observes for itself
 * (the OS input path and the node-pty exit), and a renderer cannot witness either.
 */
const CHANNEL_MAY_REACH_RELEASE = new Map([
  ["voice:capture", new Set(["cancel"])],
  ["conductor:operator-text", new Set(["cancel"])],
]);

/** Index of the closing quote of the `'`/`"` literal opening at `at`. */
function endOfQuoted(src, at) {
  const quote = src[at];
  let i = at + 1;
  while (i < src.length) {
    if (src[i] === "\\") { i += 2; continue; }
    if (src[i] === quote) return i;
    i += 1;
  }
  return src.length - 1;
}

/**
 * Index of the closing backtick of the template literal opening at `at`.
 *
 * `${…}` substitutions are code and may nest further templates, strings and braces — main.js has
 * exactly that (`ensureCaptureStore`'s purge log). A scanner that stops at the first backtick it
 * meets desynchronises there and every brace after it is counted against the wrong body.
 */
function endOfTemplate(src, at) {
  let i = at + 1;
  while (i < src.length) {
    const c = src[i];
    if (c === "\\") { i += 2; continue; }
    if (c === "`") return i;
    if (c === "$" && src[i + 1] === "{") {
      let depth = 1;
      i += 2;
      while (i < src.length && depth > 0) {
        const e = src[i];
        if (e === "\\") { i += 2; continue; }
        if (e === "`") { i = endOfTemplate(src, i) + 1; continue; }
        if (e === '"' || e === "'") { i = endOfQuoted(src, i) + 1; continue; }
        if (e === "{") depth += 1;
        else if (e === "}") depth -= 1;
        i += 1;
      }
      continue;
    }
    i += 1;
  }
  return src.length - 1;
}

/**
 * Blank the parts of main.js that are not code, preserving every offset and newline.
 *
 * `keepStrings` blanks comments only — the right view for asking whether a string ARGUMENT is
 * present (`on("before-input-event", …)`), where blanking the literal would erase the fact. The
 * default also blanks string and template bodies, which is the right view for structure: a brace or
 * a `.disarm(` inside a literal is not a call.
 */
function blankNonCode(src, { keepStrings = false } = {}) {
  const out = src.split("");
  const blank = (from, to) => {
    for (let k = from; k < to && k < out.length; k++) if (out[k] !== "\n") out[k] = " ";
  };
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const d = src[i + 1];
    if (c === "/" && d === "/") {
      const nl = src.indexOf("\n", i);
      const end = nl < 0 ? src.length : nl;
      blank(i, end); i = end; continue;
    }
    if (c === "/" && d === "*") {
      const close = src.indexOf("*/", i + 2);
      const end = close < 0 ? src.length : close + 2;
      blank(i, end); i = end; continue;
    }
    if (c === '"' || c === "'") {
      const end = endOfQuoted(src, i);
      if (!keepStrings) blank(i + 1, end);
      i = end + 1; continue;
    }
    if (c === "`") {
      const end = endOfTemplate(src, i);
      if (!keepStrings) blank(i + 1, end);
      i = end + 1; continue;
    }
    i += 1;
  }
  return out.join("");
}

/** Brace/paren match from an opening delimiter at `at`; returns the index of its closer. */
function matchDelim(code, at, open, close) {
  assert.equal(code[at], open, `expected ${open} at ${at}`);
  let depth = 0;
  for (let i = at; i < code.length; i++) {
    if (code[i] === open) depth += 1;
    else if (code[i] === close) {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  throw new Error(`unterminated ${open} at ${at}`);
}

/** Top-level `function NAME(...) { … }` declarations → {name, start, end, body}. */
function topLevelFunctions(code) {
  const found = [];
  const re = /^(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(/gm;
  let m;
  while ((m = re.exec(code))) {
    const params = code.indexOf("(", m.index);
    const paramsEnd = matchDelim(code, params, "(", ")");
    const open = code.indexOf("{", paramsEnd);
    assert.notEqual(open, -1, `no body for ${m[1]}`);
    const end = matchDelim(code, open, "{", "}");
    found.push({ name: m[1], start: m.index, end, body: code.slice(open, end + 1) });
  }
  return found;
}

/**
 * Every `function NAME(…) { … }` declaration, NESTED ones included.
 *
 * `topLevelFunctions` answers "who owns this call site", which is a question about the file's top
 * level. The cross-channel walk asks a different one — "what can this handler reach" — and there the
 * column-0 restriction is fail-OPEN: `main.js` declares `captureFromRef`, `captureFromPcm` and
 * `foldCapture` INSIDE `registerIpc`, so a relay declared beside them is not a node of the graph at
 * all (auditor F1). It is caught on `pane:input` by that channel's closed callee list; every other
 * channel has no such list, so the walk itself has to see nested declarations.
 */
function functionDeclarations(code) {
  const found = [];
  const re = /(?:^|[^\w$.])(?:async\s+)?function\s*\*?\s*([A-Za-z0-9_$]+)\s*\(/g;
  let m;
  while ((m = re.exec(code))) {
    const params = m.index + m[0].length - 1;
    const paramsEnd = matchDelim(code, params, "(", ")");
    const open = code.indexOf("{", paramsEnd);
    assert.notEqual(open, -1, `no body for ${m[1]}`);
    const end = matchDelim(code, open, "{", "}");
    found.push({ name: m[1], start: m.index, end, body: code.slice(open, end + 1) });
    re.lastIndex = params;   // a nested declaration inside this body is its own node
  }
  return found;
}

/** `(` that open a call rather than a group or a control-flow condition. */
const NOT_A_CALLEE = new Set([
  "if", "for", "while", "switch", "catch", "return", "typeof", "new", "delete", "void",
  "function", "await", "yield", "in", "of", "do", "else", "case",
]);

/**
 * Every callee named in `body`, as written.
 *
 * Deliberately crude, and fail-CLOSED within a stated scope: every `(` that is not grouping yields a
 * name, and one that cannot be resolved to a plain identifier-or-property chain yields the reserved
 * `"<computed>"`, which no allow-list contains. Whitespace inside a chain (`manager . write`)
 * truncates it, which also fails. Nothing here needs to be clever — the assertion is "is this one of
 * three known names", not "is this dangerous".
 *
 * The scope, exactly (auditor F-A/F-D, second pass): a `.` immediately before `(` is an OPTIONAL call
 * `f?.()` and is reported as `<computed>` — the first form of this function treated it as grouping and
 * SKIPPED it, so `conductorVoiceAuthority.reset?.("bytes", {source:"node_pty_exit"})` passed every
 * test in this file while forging a main-owned provenance row. A tagged template is a call with no
 * parenthesis at all and this function cannot see it; the handler is therefore asserted separately to
 * contain no backtick, which also keeps `${…}` code — blanked by the structural view — out of it.
 * A callee reached by a getter, a Proxy trap, or a reference stored here and invoked elsewhere is not
 * a call in this body and is out of scope: that is the runtime assertion recorded as owed.
 */
function calleesIn(body) {
  const names = [];
  for (let i = 0; i < body.length; i++) {
    if (body[i] !== "(") continue;
    let j = i - 1;
    while (j >= 0 && /\s/.test(body[j])) j -= 1;
    if (j < 0) continue;
    // `)(`, `](`, `?.(` — a call whose callee is an expression, not a name.
    if (body[j] === ")" || body[j] === "]" || body[j] === ".") { names.push("<computed>"); continue; }
    if (!/[\w$]/.test(body[j])) continue;      // `=> (`, `, (`, `&& (` — grouping, not a call
    let k = j;
    while (k >= 0 && /[\w$.]/.test(body[k])) k -= 1;
    const chain = body.slice(k + 1, j + 1).replace(/^\.+/, "");
    if (!chain || NOT_A_CALLEE.has(chain)) continue;
    names.push(chain);
  }
  return names;
}

/** Regex-escape a callee name (they contain dots). */
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Walk out from `entryBody` through main's own functions.
 *
 * Returns the set of main.js functions reachable by name and the set of callees that are NOT defined
 * in main.js. Both are then asserted against: reachable bodies must contain no release, and every
 * external name must be one this file has audited. That is what makes the allow-list more than one
 * hop deep — the second pass showed a release added to `clearConductorInputResidue`, an allow-listed
 * callee, left the whole suite green (validator BLOCKER-2).
 */
function reachableFrom(entryBody, fns) {
  const internal = new Map();
  const external = new Set();
  const queue = [entryBody];
  while (queue.length) {
    for (const name of calleesIn(queue.shift())) {
      const fn = fns.find((f) => f.name === name);
      if (!fn) { external.add(name); continue; }
      if (internal.has(name)) continue;
      internal.set(name, fn);
      queue.push(fn.body);
    }
  }
  return { internal, external };
}

const CODE = blankNonCode(MAIN);                        // structure: comments and literals gone
const UNCOMMENTED = blankNonCode(MAIN, { keepStrings: true }); // comments gone, string arguments kept

test("the pane:input IPC handler cannot end a voice turn", () => {
  const body = ipcHandlerBody("pane:input");
  assert.ok(body.includes("manager.write"), "the handler must still write the operator's bytes");
  assert.doesNotMatch(body, new RegExp(RELEASE_SINK.source),
    "bytes on pane:input are not operator provenance: xterm.js emits onData for terminal replies "
    + "the pane's own process can elicit, so the supervised child could release its own restriction. "
    + "This covers all four releases — disarm, reset, cancel and stop (auditor F4/R-2).");
});

test("only the main-owned keyboard handler and the observed process exit release a turn", () => {
  const fns = topLevelFunctions(CODE);
  assert.ok(fns.length > 20, `expected main's top-level functions, parsed ${fns.length}`);

  // Every release call site in the file must be accounted for — inside one of the parsed bodies, and
  // not hidden in a literal that the structural view blanks. Without both, a sink could sit somewhere
  // this test never looks and the assertions below would be a green no-op.
  const sinkSites = [...CODE.matchAll(new RegExp(RELEASE_SINK.source, "g"))].map((m) => m.index);
  assert.ok(sinkSites.length >= 3, `expected the release call sites to exist, found ${sinkSites.length}`);
  assert.equal([...UNCOMMENTED.matchAll(new RegExp(RELEASE_SINK.source, "g"))].length, sinkSites.length,
    "a release call site appears inside a string or template literal, where this analysis cannot see it");
  for (const at of sinkSites) {
    assert.ok(fns.some((f) => at >= f.start && at <= f.end),
      `a release call at index ${at} is in no parsed top-level function: `
      + `${CODE.slice(Math.max(0, at - 100), at + 60)}`);
  }

  // Each release belongs to ONE function, named in RELEASE_OWNER. The boundary comes from the parser,
  // not from a scan for the next "\nfunction " (which missed "\nasync function " and silently widened
  // the window to the rest of the file — auditor F5). `disarm`'s owner is the one that matters most:
  // handleOperatorResumeInput is what Electron main calls FROM `before-input-event`, the OS input path
  // the vendor is not on.
  const seenMethods = new Set();
  for (const at of sinkSites) {
    const method = new RegExp(RELEASE_SINK.source).exec(CODE.slice(at))[1];
    seenMethods.add(method);
    const expected = RELEASE_OWNER[method];
    const expectedOwners = Array.isArray(expected) ? expected : [expected];
    const owner = fns.find((f) => at >= f.start && at <= f.end);
    assert.ok(owner && expectedOwners.includes(owner.name),
      `conductorVoiceAuthority.${method}() at index ${at} is called from `
      + `${(owner && owner.name) || "no parsed function"}, not from ${expectedOwners.join("|")}: `
      + `${MAIN.slice(Math.max(0, at - 120), at + 80)}`);
  }
  assert.deepEqual([...seenMethods].sort(), Object.keys(RELEASE_OWNER).sort(),
    "every release method must have a call site to pin — if one is gone, this map is stale");

  const resume = fns.find((f) => f.name === "handleOperatorResumeInput");
  assert.ok(resume, "handleOperatorResumeInput must exist as a top-level declaration");
  assert.ok(resume.body.includes("shouldOperatorResumeVoiceTurn") && resume.body.includes("isOperatorTypedKey"),
    "the handler must decide from the two main-observed gestures");
  // BOTH gestures must actually disarm. Pinning the owner is not enough on its own: deleting the
  // ordinary-typing call leaves the chord call behind, and the chord is undocumented — that is U166
  // restored exactly, with every other assertion in this file still green.
  const resumeSrc = UNCOMMENTED.slice(resume.start, resume.end + 1);
  for (const source of ["electron_main_operator_chord", "electron_main_before_input_event"]) {
    assert.match(resumeSrc, new RegExp(`disarm\\(\\s*"${source}"`),
      `handleOperatorResumeInput no longer disarms on ${source}. If ordinary typing stops ending the `
      + "turn, the operator's own prompts are blocked for the rest of the session (U166).");
  }
  // …and `before-input-event` is where it is called from. Read with comments blanked, so a comment
  // that merely MENTIONS the OS input path cannot stand in for the registration.
  assert.match(UNCOMMENTED, /before-input-event[\s\S]{0,400}handleOperatorResumeInput/);
});

/**
 * Everything `pane:input` is allowed to call. ONE name since W-39, audited here:
 *
 *  * `manager.write` — the point of the handler: the operator's bytes reach their pane.
 *
 * It used to be three. `operatorInputResolvesResidue` and `clearConductorInputResidue` were removed
 * when the voice-residue decision moved to `before-input-event`: `pane:input` carries the terminal
 * replies the CHILD elicits, so it is not operator provenance and must not resolve an operator
 * decision. The predicate and the clearing both still exist and are still tested where they live;
 * what was withdrawn is their permission to be reached from here.
 *
 * Adding a name back is a deliberate act that has to come with a reason, which is the property this
 * test exists to enforce. Extending it because a test went red is the failure it is meant to prevent.
 */
// NARROWED at W-39, from three names to one. The residue decision left this handler for
// `before-input-event`, because `pane:input` carries the terminal replies the CHILD elicits and is
// therefore not operator provenance — the paragraph above the old call site said so already.
//
// The list is tightened rather than left permissive on purpose. A stale allow-list is an invitation:
// re-adding the residue clearing here would otherwise pass this audit silently, and the audit is the
// thing standing between that edit and a green suite. Mutation `A12` restores the old call and must
// go RED.
const PANE_INPUT_MAY_CALL = new Set([
  "manager.write",
]);

/**
 * Callees on that path which are NOT declared in main.js, each audited once, here.
 *
 * The walk below follows main's own functions; these are where it stops. Anything reached that is not
 * on this list fails, including the reserved `<computed>`.
 */
const EXTERNAL_AUDITED = new Map([
  ["manager.write", "SessionManager.write — the operator's bytes reach their pane; the point of the handler"],
  // TWO entries were withdrawn at W-39, because this file refuses to keep a standing permission for
  // a callee nothing on the path reaches. `operatorInputResolvesResidue` went when the residue
  // decision moved to `before-input-event`; `mainProcessLogger.log` went with it, because its only
  // reach on this path was THROUGH `clearConductorInputResidue`'s log line.
  //
  // Both are unchanged and still tested where they live. What is withdrawn is their permission to be
  // called from `pane:input`, which now reaches exactly one thing: the write it exists to perform.
]);

test("nothing the pane:input handler can reach releases a voice turn (U175)", () => {
  const body = ipcHandlerBody("pane:input");
  const called = calleesIn(body);
  const fns = topLevelFunctions(CODE);

  // The allow-list is only a guard if the enumerator actually sees the calls that are there.
  // W-39 removed `clearConductorInputResidue` from this handler, so it is no longer an anchor for
  // this self-check — but the self-check itself is kept, re-anchored on the call that remains. Its
  // purpose is unchanged: prove the walk is reading the real body rather than an empty slice, so an
  // allow-list satisfied by finding NOTHING cannot pass.
  for (const required of ["manager.write"]) {
    assert.ok(called.includes(required),
      `the enumerator did not find ${required}() in the handler — it is not reading the body it thinks `
      + `it is. Found: ${JSON.stringify(called)}`);
  }

  // A tagged template is a call with no parenthesis, so `calleesIn` cannot see one; `${…}` holds code
  // the structural view blanks. Neither belongs in this handler, and saying so is cheaper and more
  // honest than pretending the enumerator handles them (auditor F-B/F-C).
  assert.ok(!body.includes("`"),
    "no template literal in the pane:input handler: a tagged template is a call this analysis cannot "
    + "see, and `${…}` is code the structural view blanks");

  for (const name of called) {
    assert.ok(PANE_INPUT_MAY_CALL.has(name),
      `pane:input calls ${name}(), which is not one of its audited callees `
      + `(${[...PANE_INPUT_MAY_CALL].join(", ")}). Bytes on this channel are NOT operator provenance — `
      + "xterm.js emits onData for terminal replies the pane's own process elicits — so anything this "
      + "handler can reach, the supervised child can reach on demand. If the new call is genuinely "
      + "safe, add it to PANE_INPUT_MAY_CALL with the reason; do not widen the list to make a test "
      + "pass. Only before-input-event may end a voice turn.");
  }

  // The list is closed downward as well: a name may not sit in it unused, where it would pre-authorise
  // a future call nobody re-examined.
  for (const allowed of PANE_INPUT_MAY_CALL) {
    assert.ok(called.includes(allowed), `PANE_INPUT_MAY_CALL lists ${allowed}, which the handler no `
      + "longer calls — remove it rather than leaving a standing permission");
  }

  // …and the name must still mean the function it was audited as. Rebinding an allow-listed name
  // inside the handler would let an audited word stand in for anything (validator RES-1).
  for (const name of [...PANE_INPUT_MAY_CALL]) {
    assert.doesNotMatch(body, new RegExp(`(?:const|let|var|function)\\s+${esc(name)}\\b`),
      `the handler declares its own ${name} — an audited name must not be rebound here`);
    assert.doesNotMatch(body, new RegExp(`\\b${esc(name)}\\s*=[^=]`),
      `the handler assigns to ${name} — an audited name must not be rebound here`);
  }

  // ONE HOP IS NOT ENOUGH. A release added to `clearConductorInputResidue` — an audited callee — is a
  // release reached by renderer bytes just the same, and the first form of this test stayed green for
  // it (validator BLOCKER-2). So walk main's own functions from here and check every body.
  const { internal, external } = reachableFrom(body, fns);
  for (const [name, fn] of internal) {
    assert.doesNotMatch(fn.body, new RegExp(RELEASE_SINK.source),
      `${name}() is reachable from pane:input and releases a voice turn. Renderer bytes reach every `
      + "function on this path, so a release anywhere on it is a release the supervised child can "
      + "elicit — one hop from the handler is no different from inside it.");
  }

  // A RELEASE NEEDS NO CALL. `conductorVoiceAuthority._active = null` — or `delete`, or a computed
  // member, or a local alias assigned to — clears the restriction with NO audit row, so `RELEASE_SINK`
  // cannot see it and neither can the receipt leg that enumerates provenance (validator BLOCKER-3).
  // Nothing on this path has any business naming the service, so that is the assertion.
  for (const [name, src] of [["the pane:input handler", body], ...[...internal].map(([n, f]) => [`${n}()`, f.body])]) {
    assert.ok(!src.includes("conductorVoiceAuthority"),
      `${name} names conductorVoiceAuthority. Renderer bytes reach this code, and a release does not `
      + "have to be a CALL: assigning to or deleting one of its fields ends the restriction with no "
      + "provenance row at all. Nothing on the pane:input path may touch the authority service.");
  }
  for (const name of external) {
    assert.ok(EXTERNAL_AUDITED.has(name),
      `pane:input reaches ${name}(), which is not declared in main.js and is not audited. Add it to `
      + `EXTERNAL_AUDITED with the reason it cannot release a turn, or remove the call. `
      + `(\`<computed>\` means a callee this analysis cannot name — that is a refusal, not a gap.)`);
  }
  for (const name of EXTERNAL_AUDITED.keys()) {
    assert.ok(external.has(name) || called.includes(name),
      `EXTERNAL_AUDITED lists ${name}, which nothing on this path calls — remove the standing permission`);
  }
});

test("every use of the authority service in main.js is a method call on it (U175)", () => {
  // The other half of BLOCKER-3, file-wide. `RELEASE_SINK` and the walk above both assume the service
  // is only ever REACHED — that its state is not written, and that no other name refers to it. Neither
  // is guaranteed by anything else, and both are one line to break: `const a = conductorVoiceAuthority`
  // in any handler, followed by `a._active = null`, is a release the whole file above cannot see.
  const NAME = "conductorVoiceAuthority";
  const sites = [...CODE.matchAll(new RegExp(`\\b${NAME}\\b`, "g"))].map((m) => m.index);
  assert.ok(sites.length > 10, `expected the authority service to be used in main.js, found ${sites.length}`);

  let declarations = 0;
  for (const at of sites) {
    const before = CODE.slice(Math.max(0, at - 40), at);
    const after = CODE.slice(at + NAME.length);
    const where = MAIN.slice(Math.max(0, at - 80), at + 80);
    if (/(?:const|let|var)\s+$/.test(before)) { declarations += 1; continue; }
    assert.doesNotMatch(before, /\bdelete\s+$/,
      `main.js deletes the authority service itself: ${where}`);
    // `.method(` or `?.method?.(` and nothing else. A bare reference (passed as a value, destructured,
    // aliased), a computed member (`["_act" + "ive"]`), a tagged template and every form of write
    // (`= `, `++`, `--`) all fail here, because none of them is a method call on it.
    assert.match(after, /^\s*\??\.\s*[A-Za-z0-9_$]+\s*\??\.?\s*\(/,
      `every use of ${NAME} in main.js must be a method call on it — this one is not, so the "release" `
      + "analysis in this file cannot see what it does. Aliasing it, destructuring it, passing it as a "
      + `value, reaching a computed member or writing a field are all releases without provenance: ${where}`);
  }
  assert.equal(declarations, 1,
    `${NAME} must be bound exactly once in main.js; found ${declarations} bindings`);
});

test("no other IPC channel can release a voice turn either (U175)", () => {
  const fns = functionDeclarations(CODE);
  for (const nested of ["captureFromPcm", "foldCapture", "registerIpc"]) {
    assert.ok(fns.some((f) => f.name === nested),
      `the walk cannot see ${nested}() — a relay declared beside it would not be a node of the graph`);
  }
  const channels = [...UNCOMMENTED.matchAll(/ipcMain\.handle\("([^"]+)"/g)].map((m) => m[1]);
  assert.ok(channels.length > 15, `expected main's IPC channels, parsed ${channels.length}`);
  assert.ok(channels.includes("pane:input") && channels.includes("pane:focus"),
    "the channel enumeration is not reading the handlers it thinks it is");

  for (const channel of channels) {
    const body = ipcHandlerBody(channel);
    const allowed = CHANNEL_MAY_REACH_RELEASE.get(channel) || new Set();
    const { internal } = reachableFrom(body, fns);
    for (const [name, src] of [[`the ${channel} handler`, body], ...[...internal].map(([n, f]) => [`${n}()`, f.body])]) {
      for (const m of src.matchAll(new RegExp(RELEASE_SINK.source, "g"))) {
        assert.ok(allowed.has(m[1]),
          `${channel} reaches conductorVoiceAuthority.${m[1]}() in ${name}. A renderer channel cannot `
          + "witness the two facts that end a turn — the operator taking the keyboard back, and the "
          + "supervised process exiting — so no channel may reach disarm or reset, and only the channel "
          + "that MINTS a turn may cancel it. Moving the relay one channel over was a live bypass "
          + "(validator RESERVATION-1); if this channel genuinely needs it, add it to "
          + "CHANNEL_MAY_REACH_RELEASE with the reason.");
      }
    }
  }

  // Closed downward, like every other list here: an exception nobody exercises is a standing permission.
  for (const [channel, methods] of CHANNEL_MAY_REACH_RELEASE) {
    assert.ok(channels.includes(channel), `CHANNEL_MAY_REACH_RELEASE names ${channel}, which no longer exists`);
    const { internal } = reachableFrom(ipcHandlerBody(channel), functionDeclarations(CODE));
    const reached = new Set([...internal.values()]
      .flatMap((f) => [...f.body.matchAll(new RegExp(RELEASE_SINK.source, "g"))].map((m) => m[1])));
    for (const method of methods) {
      assert.ok(reached.has(method),
        `${channel} is permitted to reach ${method}() and no longer does — remove the permission`);
    }
  }
});

test("the imported predicate on that path is a predicate (U175)", () => {
  // `operatorInputResolvesResidue` is the one audited callee defined outside main.js, so the walk
  // above stops at its name. This is where it gets read.
  const src = fs.readFileSync(path.resolve(__dirname, "..", "voice", "conductor-write.js"), "utf8");
  const fn = topLevelFunctions(blankNonCode(src)).find((f) => f.name === "operatorInputResolvesResidue");
  assert.ok(fn, "operatorInputResolvesResidue must be a top-level declaration in voice/conductor-write.js");
  assert.doesNotMatch(fn.body, new RegExp(RELEASE_SINK.source), "it must touch no voice-turn authority");
  assert.deepEqual([...new Set(calleesIn(fn.body))].sort(), ["String", "test"],
    "it must remain a pure predicate over the bytes — String() and a regex test, nothing else");
});
