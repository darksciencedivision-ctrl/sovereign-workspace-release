"use strict";
/**
 * Phase 17C `.close-revalidate` — the voice→conductor delivery orchestration (U148 fix under
 * revalidation; the register closes only after independent confirmation).
 *
 * Every guard here exists because a mandatory review found the delivery doing the opposite. The tests
 * are written so that removing a guard turns one of them red: that is the property `.close` did not
 * have, when the validator reverted half a BLOCKING fix and all 579 tests stayed green.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { deliverChat, operatorInputResolvesResidue } = require("../voice/conductor-write");

const ESC = String.fromCharCode(27);
const INPUT_CHROME = `${ESC}[1m❯ ${ESC}[0m\r\n  ⏸ plan mode on\r\n`;
const PROMPT_CHROME = "  Do you want to proceed?\r\n  ❯ 1. Yes\r\n    2. Yes, and don't ask again\r\n    3. No\r\n";
const TURN_MARKER = "[[SOVEREIGN_VOICE_CHAT_V2:0123456789abcdef0123456789abcdef]] ";

/**
 * A pane whose ConPTY behaves like the live TUI: it echoes what is written to it (unless told not to),
 * and it keeps a monotonic stream with a bounded window, like the real RingBuffer.
 */
function pane(opts = {}) {
  const st = {
    emitted: Buffer.from(opts.chrome === undefined ? INPUT_CHROME : opts.chrome, "utf8"),
    dropped: 0,
    writes: [],
    residue: opts.residue || null,
    terminal: opts.terminal === true,
    launch: opts.launch || "running",
    session: opts.session !== false,
    liveHandle: opts.liveHandle !== false,
    echoes: opts.echoes !== false,
    trimOnWrite: opts.trimOnWrite === true,
    now: 1_000_000,
    authorityCancels: [],
    authorityArms: [],
    fateReads: 0,
  };
  const io = {
    paneId: opts.paneId === undefined ? "pane-1" : opts.paneId,
    hasSession: () => st.session,
    isTerminal: () => st.terminal,
    launchState: () => st.launch,
    authorityBoundary: () => opts.authorityBound === false ? null : {
      schema: "voice_turn_boundary@1.0",
      supervisor_owned: true,
      non_executing_voice_turns: true,
      enforced_by_supervisor_process: opts.supervisorEnforced !== false,
      broker_schema: "supervisor_voice_turn_authority@1.0",
    },
    armAuthority: async (body) => {
      st.authorityArms.push(body);
      if (opts.armFails) return { ok: false, reason: "supervisor arm failed" };
      return {
        ok: true,
        turn_id: "0123456789abcdef0123456789abcdef",
        prompt_marker: TURN_MARKER,
        payload: `${TURN_MARKER}${body}`,
      };
    },
    cancelAuthority: (turnId, reason) => {
      st.authorityCancels.push({ turnId, reason });
      return true;
    },
    // Phase 17C `.disarm`: what the supervisor still holds for this turn after the submit key.
    // `opts.turnFates` is consumed one per read, so a test can model "pending, then admitted" — and
    // "the operator's keystroke ended it while we were waiting".
    ...(opts.noTurnFate ? {} : {
      turnFate: () => {
        st.fateReads += 1;
        const scripted = opts.turnFates;
        if (!scripted) return "vendor_reported_submission";
        return scripted[Math.min(st.fateReads - 1, scripted.length - 1)];
      },
    }),
    emittedAll: () => st.emitted,
    streamPosition: () => (opts.brokenBuffer ? null : st.dropped + st.emitted.length),
    emittedSince: (from) => {
      const start = from - st.dropped;
      if (start < 0 || start > st.emitted.length) return null;   // trimmed away / ahead of the stream
      return st.emitted.subarray(start).toString("utf8");
    },
    write: (data) => {
      if (!st.liveHandle) return false;
      st.writes.push(data);
      if (st.echoes && data !== "\r") {
        st.emitted = Buffer.concat([st.emitted, Buffer.from(`${ESC}[K${data}`, "utf8")]);
      }
      if (st.trimOnWrite) {
        // A repainting TUI fills the ring and the front is evicted — INCLUDING the region the caller
        // is watching. `sliceFrom` then answers null (the position predates what is still held), which
        // is the case the old code turned into "search the whole scrollback".
        st.dropped += st.emitted.length;
        st.emitted = Buffer.from(`${INPUT_CHROME}[later repaint]`, "utf8");
      }
      return true;
    },
    getResidue: () => st.residue,
    setResidue: (r) => { st.residue = { ...r }; },
    now: () => (st.now += 500),             // the wait cannot hang a test
    sleep: async () => {},
  };
  return { st, io };
}

const UTTERANCE = "What is 31 plus 32? Answer with only the sum and nothing else.";

// ---- Phase 17C `.disarm` (spec-audit M-6): the turn the operator ended was never delivered ------
// `.disarm` let the operator's next keystroke end a voice turn — and that window now overlaps the
// delivery. A keypress while the utterance is still PENDING clears it, the marked prompt is then
// blocked, and the model never sees it. Reporting `submitted:true` there renders "Delivered to
// conductor" for something the conductor was never given.

test("an operator keystroke during the delivery is reported as NOT delivered", async () => {
  const { st, io } = pane({ turnFates: ["pending", "ended_by_operator"] });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false, "the conductor never accepted this utterance");
  assert.strictEqual(r.turn_fate, "ended_by_operator");
  assert.match(r.reason, /ended the voice turn/i);
  assert.match(r.reason, /NOT delivered/);
  // …and the operator is pointed at the pane. What a vendor CLI does with a prompt its own hook
  // blocked is not pinned by anything in this repo, so the reason must not assert where the text is.
  assert.match(r.reason, /check pane pane-1/);
  assert.doesNotMatch(r.reason, /sitting in the input box/);
  // the next utterance must not be spliced onto whatever is there
  assert.ok(st.residue, "an undelivered body must leave a residue record");
});

test("each cause of a turn ending gets its own reason, and the process exit is not the operator", async () => {
  const byExit = await deliverChat(UTTERANCE, pane({ turnFates: ["ended_by_process_exit"] }).io);
  assert.strictEqual(byExit.submitted, false);
  assert.match(byExit.reason, /session ended/i);
  assert.doesNotMatch(byExit.reason, /you ended/i);
  const byCancel = await deliverChat(UTTERANCE, pane({ turnFates: ["ended_by_cancel"] }).io);
  assert.match(byCancel.reason, /cancelled/i);
});

test("a turn still PENDING at the admit deadline is UNCONFIRMED, never a delivery", async () => {
  // `pending` is the supervisor answering "the CLI has NOT presented this payload back to me". The
  // first draft reported it as submitted, which is fail-OPEN on an answered negative and made it
  // better news than `unavailable`, which knows strictly less.
  const { st, io } = pane({ turnFates: ["pending"] });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.submitted, false);
  assert.strictEqual(r.turn_fate, "pending");
  assert.match(r.reason, /UNCONFIRMED/);
  assert.match(r.reason, /may still land/);
  assert.ok(st.residue, "an unconfirmed body may be sitting in the input too");
  // …and it is NOT cancelled: a pending turn can still be admitted, and cancelling it here would
  // turn a slow admission into a blocked prompt.
  assert.deepStrictEqual(st.authorityCancels, []);
});

test("a turn admitted and then ended within one poll interval is still a delivery", async () => {
  // The mirror image of M-6: reading only the live state would report a delivery the model DID
  // receive as voided, block the next utterance, and blame the operator's keystroke for it.
  const { io } = pane({ turnFates: ["vendor_reported_submission"] });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.submitted, true);
  assert.strictEqual(r.turn_fate, "vendor_reported_submission");
});

test("the submission fate is reached by polling, not by one impatient read", async () => {
  const { st, io } = pane({ turnFates: ["pending", "pending", "vendor_reported_submission"] });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.submitted, true);
  assert.strictEqual(r.turn_fate, "vendor_reported_submission");
  assert.ok(st.fateReads >= 3, `expected repeated reads, got ${st.fateReads}`);
});

test("a binding with no way to ask the supervisor reports an UNCONFIRMED delivery", async () => {
  const { io } = pane({ noTurnFate: true });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false, "an unconfirmable delivery is not a delivery");
  assert.strictEqual(r.turn_fate, "unavailable");
  assert.match(r.reason, /UNCONFIRMED/);
});

// ---- U179/U180: what the delivery may assume, and what it may claim ----------------------------

test("the manual-mode pane is accepted only while the boundary is STILL bound, re-read at the write", async () => {
  // The flag was the literal `true`, so `pane-state`'s one refusal — vendor chrome alone is not
  // authority (invariant 29) — could never fire (U179). It is derived from the boundary now, and the
  // boundary is re-read AT THE PANE READ: the authority service can stop between guard 1 and here,
  // and a manual-mode pane behind no live boundary is exactly the case that refusal is for.
  const manualChrome = `${ESC}[1m❯ ${ESC}[0m\r\n  ⏸ manual mode on\r\n`;
  const live = pane({ chrome: manualChrome });
  const ok = await deliverChat(UTTERANCE, live.io);
  assert.strictEqual(ok.submitted, true, "a manual-mode pane behind a live boundary still delivers");

  const dropped = pane({ chrome: manualChrome });
  let reads = 0;
  const bound = dropped.io.authorityBoundary;
  dropped.io.authorityBoundary = () => (++reads > 1 ? null : bound());
  const r = await deliverChat(UTTERANCE, dropped.io);
  assert.strictEqual(r.written, false, "nothing may be typed into a manual-mode pane with no boundary");
  assert.match(r.reason, /vendor chrome alone is not authority/);
  assert.deepStrictEqual(dropped.st.writes, []);
  // …and a PLAN-mode pane is unaffected: that marker never depended on the boundary
  const plan = pane();
  plan.io.authorityBoundary = ((b) => { let n = 0; return () => (++n > 1 ? null : b()); })(plan.io.authorityBoundary);
  assert.strictEqual((await deliverChat(UTTERANCE, plan.io)).submitted, true);
});

test("the delivery reports the vendor's own claim as the vendor's own claim", async () => {
  // U180: admission is `UserPromptSubmit` — the child presenting the marked payload back. It holds
  // both the payload and the bearer, so this is its claim about itself. It is a delivery REPORT, and
  // the name it carries into the badge now says which fact it rests on.
  const { io } = pane({ turnFates: ["vendor_reported_submission"] });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.submitted, true);
  assert.strictEqual(r.turn_fate, "vendor_reported_submission");
  assert.strictEqual(r.submission_basis, "vendor_reported");
  // …and the operator-facing reason says WHO reported it, in words rather than in a field name
  assert.match(r.reason, /conductor CLI reported/i);
});

test("the happy path: body written, echo observed, submit key sent", async () => {
  const { st, io } = pane();
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, true);
  assert.deepStrictEqual(st.writes, [`${TURN_MARKER}${UTTERANCE}`, "\r"]);
  assert.deepStrictEqual(st.authorityArms, [UTTERANCE]);
  assert.deepStrictEqual(st.authorityCancels, []);
  assert.strictEqual(r.echo.window, "appended");
  assert.strictEqual(st.residue, null);
  assert.strictEqual(r.pane_state.state, "input");
});

// ---- guard 1: the sink is the governed conductor node -------------------------------------------

test("a pane that is not running a GOVERNED conductor session is never written to", async () => {
  for (const launch of ["unstarted", "refused", "exited", "launching", "failed"]) {
    const { st, io } = pane({ launch });
    const r = await deliverChat(UTTERANCE, io);
    assert.strictEqual(r.written, false, `launch=${launch} must not write`);
    assert.strictEqual(r.submitted, false);
    assert.deepStrictEqual(st.writes, [], "nothing may reach a non-governed pane");
    assert.match(r.reason, /governed conductor session/);
  }
});

test("vendor plan-mode chrome is not authority — production refuses without supervisor binding", async () => {
  const { st, io } = pane({ authorityBound: false });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.submitted, false);
  assert.deepStrictEqual(st.writes, []);
  assert.match(r.reason, /supervisor-owned|invariants 25\/29/i);
});

test("a vendor-dispatched hook policy is not supervisor enforcement and direct chat stays disabled", async () => {
  const { st, io } = pane({ supervisorEnforced: false });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.match(r.reason, /supervisor-process enforcement|disabled/i);
  assert.deepStrictEqual(st.writes, []);
});

test("a supervisor that cannot arm the exact turn refuses before writing", async () => {
  const { st, io } = pane({ armFails: true });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.match(r.reason, /arm failed|supervisor/i);
  assert.deepStrictEqual(st.writes, []);
});

test("a malformed or incomplete supervisor boundary fails closed before the body write", async () => {
  for (const boundary of [
    {},
    { schema: "voice_turn_boundary@0.9", supervisor_owned: true,
      non_executing_voice_turns: true, broker_schema: "supervisor_voice_turn_authority@1.0" },
    { schema: "voice_turn_boundary@1.0", supervisor_owned: false,
      non_executing_voice_turns: true, broker_schema: "supervisor_voice_turn_authority@1.0" },
    { schema: "voice_turn_boundary@1.0", supervisor_owned: true,
      non_executing_voice_turns: false, broker_schema: "supervisor_voice_turn_authority@1.0" },
  ]) {
    const { st, io } = pane();
    io.authorityBoundary = () => boundary;
    const r = await deliverChat(UTTERANCE, io);
    assert.strictEqual(r.written, false);
    assert.deepStrictEqual(st.writes, []);
  }
});

test("no session / an ended session / no pane are refusals, not deliveries", async () => {
  const noSession = pane({ session: false });
  assert.match((await deliverChat(UTTERANCE, noSession.io)).reason, /not admitted/);
  assert.deepStrictEqual(noSession.st.writes, []);

  const ended = pane({ terminal: true });
  const r = await deliverChat(UTTERANCE, ended.io);
  assert.strictEqual(r.written, false);
  assert.match(r.reason, /has ended/);
  assert.deepStrictEqual(ended.st.writes, []);

  const noPane = pane({ paneId: null });
  assert.match((await deliverChat(UTTERANCE, noPane.io)).reason, /no conductor pane/);
});

// ---- guard 2: no splicing onto an unsubmitted utterance ------------------------------------------

test("an unsubmitted utterance in the input box refuses the next one (never spliced)", async () => {
  const { st, io } = pane({ residue: { excerpt: "an earlier sentence", why: "echoed 0/5" } });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.deepStrictEqual(st.writes, []);
  assert.match(r.reason, /never submitted/);
  assert.match(r.reason, /spliced/);
  assert.strictEqual(r.residue.excerpt, "an earlier sentence");
});

test("a withheld submit RECORDS the residue so the next utterance is refused", async () => {
  const { st, io } = pane({ echoes: false });          // the pane never echoes: submit withheld
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false);
  assert.deepStrictEqual(st.writes, [`${TURN_MARKER}${UTTERANCE}`],
    "the submit key must NOT follow an unobserved echo");
  assert.ok(st.residue, "the body is still in the input box — that must be recorded");
  assert.match(st.residue.excerpt, /What is 31 plus 32/);
  // …and the next attempt is refused rather than appended
  const second = await deliverChat("another sentence entirely", io);
  assert.strictEqual(second.written, false);
  assert.deepStrictEqual(st.writes, [`${TURN_MARKER}${UTTERANCE}`]);
  assert.equal(st.authorityCancels.length, 1,
    "a body that was not submitted must cancel the supervisor's pending turn");
});

// ---- guard 3: the pane must be showing its text input --------------------------------------------

test("THE CONVERGENT BLOCKING FINDING: an open permission prompt receives NOTHING", async () => {
  const { st, io } = pane({ chrome: INPUT_CHROME + PROMPT_CHROME });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.submitted, false);
  // the utterance carries 3, 1, 3, 2 — digits are the affordance of a numbered prompt
  assert.deepStrictEqual(st.writes, [], "not one character may reach a confirmation dialog");
  assert.strictEqual(r.pane_state.state, "prompt");
  assert.match(r.reason, /confirmation prompt/);
});

test("a pane whose state this shell cannot read is refused (absence is not consent)", async () => {
  const { st, io } = pane({ chrome: "PS D:\\work> \r\n" });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.deepStrictEqual(st.writes, []);
  assert.strictEqual(r.pane_state.state, "unknown");
});

// ---- guard 4: the echo window is exact, or the submit is withheld ---------------------------------

test("THE OTHER CONVERGENT BLOCKING FINDING: a lost echo window withholds the submit key", async () => {
  // The ring trims the watched region mid-wait. The old code widened the search to the whole
  // scrollback, where an EARLIER echo of the same sentence could confirm the submit.
  const { st, io } = pane({ trimOnWrite: true });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false);
  assert.deepStrictEqual(st.writes, [`${TURN_MARKER}${UTTERANCE}`],
    "no submit key may follow an unanswerable window");
  assert.strictEqual(r.echo.window, "lost");
  assert.match(r.reason, /outran the echo window/);
  assert.ok(st.residue);
});

test("an EARLIER echo of the same utterance cannot confirm a later one", async () => {
  // the scrollback already contains the sentence (the operator said it once before)
  const { st, io } = pane({ chrome: `${INPUT_CHROME}❯ ${UTTERANCE}\r\n● 63\r\n${INPUT_CHROME}`,
                            echoes: false });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.submitted, false, "the window is the APPENDED region — history cannot satisfy it");
  assert.deepStrictEqual(st.writes, [`${TURN_MARKER}${UTTERANCE}`]);
  assert.strictEqual(r.echo.matched, 0);
});

test("an unreadable stream position writes nothing at all", async () => {
  const { st, io } = pane({ brokenBuffer: true });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.deepStrictEqual(st.writes, [], "the body must not be written when the echo cannot be watched");
  assert.match(r.reason, /fail closed/);
});

test("a dead pty handle reports not-written rather than a delivery", async () => {
  const { io } = pane({ liveHandle: false });
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, false);
  assert.strictEqual(r.submitted, false);
  assert.match(r.reason, /no live ConPTY handle/);
});

test("a THROWING body write records possible residue and never claims not-written", async () => {
  const { st, io } = pane();
  io.write = () => { throw new Error("close race"); };
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true, "a throwing write may have partially reached the PTY");
  assert.strictEqual(r.submitted, false);
  assert.ok(st.residue, "possible partial input must block the next utterance");
  assert.match(r.reason, /write failed|close race/i);
});

test("a THROWING submit write records residue and never reports a delivery", async () => {
  const { st, io } = pane();
  const realWrite = io.write;
  io.write = (data) => {
    if (data === "\r") throw new Error("submit close race");
    return realWrite(data);
  };
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false);
  assert.ok(st.residue);
  assert.match(r.reason, /submit key failed|close race/i);
});

test("a session that ends between the echo and the submit key is not a delivery", async () => {
  const { st, io } = pane();
  const realWrite = io.write;
  io.write = (data) => { if (data === "\r") return false; return realWrite(data); };
  const r = await deliverChat(UTTERANCE, io);
  assert.strictEqual(r.written, true);
  assert.strictEqual(r.submitted, false);
  assert.match(r.reason, /ended before the submit key/);
  assert.ok(st.residue);
});

// ---- shape ----------------------------------------------------------------------------------------

test("interior newlines are collapsed so one utterance stays one prompt", async () => {
  const { st, io } = pane();
  const r = await deliverChat("first line\nsecond line", io);
  assert.strictEqual(r.flattened, true);
  assert.strictEqual(st.writes[0], `${TURN_MARKER}first line second line`);
});

test("an empty transcript is never written", async () => {
  const { st, io } = pane();
  const r = await deliverChat("   \r\n", io);
  assert.strictEqual(r.written, false);
  assert.deepStrictEqual(st.writes, []);
});

test("residue clears only on an operator submit/cancel, never on arbitrary bytes", () => {
  for (const data of ["x", "\x1b[A", "\t", "\x7f", "\x1b"]) {
    assert.strictEqual(operatorInputResolvesResidue(data), false, JSON.stringify(data));
  }
  for (const data of ["\r", "\n", "\x03", "edited text\r"]) {
    assert.strictEqual(operatorInputResolvesResidue(data), true, JSON.stringify(data));
  }
});
