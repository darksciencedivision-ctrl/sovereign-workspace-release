"use strict";
/**
 * Phase 18E `.live.electron` — what the OP-12 **LIVE** in-Electron acceptance receipt is allowed to
 * claim.
 *
 * 18C's `op12-acceptance` receipt evidenced the FAIL-CLOSED world and refused, by construction, to
 * stand in for the live legs once the operator opened the switch. The operator opened it, that
 * receipt failed by design (`PHASE18C_ACCEPTANCE_SELFCHECK.json`, 2026-08-02, ok:false), and
 * OP-12.2 (directive §17.2) named the leg that now has to exist: per provider, a real picker
 * selection → a supervised ConPTY pane **as a registered Sovereign node** → the exact provider and
 * model verified → ONE harmless prompt → a live response → teardown → lease 0 → a credential
 * sentinel scan of every sink that NOW EXISTS (the PTY transcript and the child environment
 * included — the skip receipt's scan was narrow because its world was) → durable-ledger AND
 * node-log consistency.
 *
 * The rules live here, pure, so `node --test` can falsify each one without a window, a supervisor
 * or a provider CLI. Each exists because a green LIVE receipt could otherwise be produced by
 * something other than a live model answering:
 *
 *   • `worldIsLiveOpen` — the mirror of 18C's `worldIsFailClosed`, and the same argument in the
 *     other direction: a LIVE receipt may only be written where the operator's switch actually
 *     authorizes the provider. Unreadable ⇒ NOT live: "we could not tell" is never "we checked".
 *   • `paneRunsExactlyThisSelection` — §17's "exact provider+model verified", read off what was
 *     SPAWNED (the resolved binary, the argv's model flag, the observed node-pty spawn) rather than
 *     off the chrome that describes it. A pane that launched the right provider on a different
 *     model is a different live call than the one the receipt names.
 *   • `childEnvIsScrubbed` — §2.2 on the environment the CHILD was handed, plus the OP-12
 *     credential NAMES specifically: this is one of the two sinks 18C could not scan because
 *     nothing was ever spawned.
 *   • `liveAnswerIsHonest` — the U238 lesson generalised. An echo is not an answer, a token already
 *     on screen is not an answer, and a receipt that cannot separate "the keystrokes arrived" from
 *     "a model replied" proves only that a terminal exists.
 *   • `nodeRecordLifecycleIsComplete` / `appendOnlyChainIsIntact` — invariant 2 and invariant 12 on
 *     the operator's OWN durable node log: the pane was a registered node for the whole of its
 *     life, bound to THIS session (U315), and the log it was written to is still a hash chain.
 *   • `paneConsentGate` / `consentOutcomeIsHonest` — the first live run found both CLIs sitting on
 *     their own directory-trust modal, which no argv flag dismisses and which only the operator may
 *     answer (invariant 1). A gate is not a dead terminal and it is not an answer: a gated leg is
 *     reported as skip-with-record, spends no live budget, and names the one-time operator step.
 *   • `owedLegsAreNamed` — a live receipt owes MORE disclosure than a skipped one, not less.
 *
 * HONEST RESIDUAL, the same one `fully-live-verdict` and `op12-acceptance-verdict` record: the OWED
 * list is AUTHORED. These rules enforce that every leg we KNOW is unevidenced is named with a
 * reference; they cannot discover one nobody wrote down.
 */

const {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, OP12_ALLOWANCE,
  leasesAreZero, noCredentialMaterial,
} = require("./op12-acceptance-verdict");
const { ADAPTER_EXECUTABLE } = require("../picker/launch-source");

//: provider → the ONE executable basename its pane may run. Projected from the ticket contract's
//: own allowlist rather than re-spelled: a second literal is how a provider ends up verified
//: against a binary nothing else would accept.
const OP12_EXECUTABLE = Object.freeze(Object.fromEntries(
  OP12_PROVIDERS.map((p) => [p, ADAPTER_EXECUTABLE[p]]),
));

//: The flags either OP-12 CLI carries its model id on (`grok -m …`, `agy --model …`). The VALUE
//: after one of these is what the live call actually asked for, and it is the only thing §17's
//: "exact provider+model verified" can honestly rest on — the chrome label is a description of the
//: selection, not of the process.
const MODEL_FLAGS = Object.freeze(["-m", "--model"]);

//: The genesis `prev_hash` of the append-only node log (`AppendOnlyEventLog`): 64 zeros.
const GENESIS_PREV_HASH = "0".repeat(64);

/**
 * The consent gates each OP-12 CLI raises on an interactive launch in this workspace — measured,
 * not imagined. Every phrase below was READ OFF a live in-Electron run of this very check, and the
 * SURVIVING receipt `docs/evidence/receipts/PHASE18E_LIVE_ACCEPTANCE_SELFCHECK.json` carries the
 * same text in `banner_excerpt` / `pane_excerpt_at_teardown` (the first run's copy was overwritten
 * at that path by the re-run, so the citation points at what a reader can still open). Both panes
 * came up, painted, settled — and sat on a modal that ignores typed text:
 *
 *   grok  → "Grok Build may run or modify contents in this directory, posing security risks.
 *            Yes, proceed y  No, quit n"
 *   agy   → "Do you trust the contents of this project? Antigravity CLI requires permission to
 *            read, edit, and execute files here.  > Yes, I trust this folder   No, exit"
 *
 * WHY THE LOOP MAY NOT ANSWER THEM. Pressing "yes" grants a frontier CLI directory-scoped authority
 * to read, edit and execute in the operator's workspace — agy's modal says so in as many words.
 * That is a protected action, and invariant 1 says the app never self-authorizes one; the OP-12
 * operator directive §11 puts tool permission under the launch ticket with "no always-approve, no
 * unsandboxed defaults" and states that a provider CLI's own always-approve setting is never
 * operator approval. OP-12 authorized live SESSIONS on these subscriptions — a statement about
 * subscription terms — and did not delegate the operator's filesystem-trust decision over their own
 * repository to the loop.
 *
 * Both panes launch in the mode this build pins for a governed frontier pane (`--permission-mode
 * plan` / `--mode plan` — a reasoned choice, NOT a documented ranking: `adapters/frontier/
 * grok_build.py` records that the CLI's enum is unordered and refuses to call it the most
 * restrictive value), and the gate is raised anyway. It is a directory-trust question, orthogonal
 * to the tool-permission mode. No PERMITTED argv flag dismisses it: the two that might —
 * `--always-approve` and `--dangerously-skip-permissions`, both recorded in this repo's own host
 * reconnaissance — are precisely what §11 forbids, and neither was tried.
 *
 * WHY THE RULE IS HERE AND NOT IN THE CHECK. Without it the receipt reported "the keystrokes are
 * not reaching the live session" — a dead-terminal finding, about a pane whose session was alive
 * and simply waiting for a human. This build has one standing rule about that shape (17A, U310,
 * `.live.shape`): never report one failure wearing another's clothes.
 */
const PROVIDER_CONSENT_GATES = Object.freeze({
  grok_build: Object.freeze([
    Object.freeze({
      gate: "workspace_trust",
      all: Object.freeze([/may run or modify contents in this directory/i, /yes,\s*proceed/i]),
      operator_step: "run `grok` once from a terminal in this workspace and answer its "
        + "\"Yes, proceed\" directory-trust prompt yourself — the loop must not answer it "
        + "(invariant 1; OP-12 operator directive §11: no always-approve, no unsandboxed defaults)",
    }),
  ]),
  google_antigravity: Object.freeze([
    Object.freeze({
      gate: "workspace_trust",
      all: Object.freeze([/do you trust the contents of this project/i, /yes,\s*i trust this folder/i]),
      operator_step: "run `agy` once from a terminal in this workspace and answer its "
        + "\"Do you trust the contents of this project?\" prompt yourself — the loop must not "
        + "answer it (invariant 1; OP-12 operator directive §11)",
    }),
    Object.freeze({
      // Only when the CLI is NOT already resolving it: the same run observed "You are currently not
      // signed in. ⣯ Signing in…" and then went on to reach the workspace prompt. A CLI reporting
      // progress is not a CLI waiting on the operator, and calling it one would invent an operator
      // step that is not owed.
      gate: "sign_in",
      all: Object.freeze([/not signed in/i]),
      none: Object.freeze([/signing in/i]),
      operator_step: "complete this CLI's own sign-in on the host (`agy` interactively) — the loop "
        + "never handles credentials (§2.2)",
    }),
  ]),
});

/**
 * Is this pane sitting on a provider consent gate — a modal that consumes keystrokes and answers
 * to nobody but the operator?
 *
 * Every signature requires ALL of its phrases, and a `none` phrase forbids the state it describes.
 * One phrase would match a pane where a model merely SAID "yes, proceed", and a receipt that
 * mistakes an answer for a gate is the same error as the one this function exists to end, pointing
 * the other way.
 *
 * WHAT ALL-OF DOES NOT BUY, stated because the first version of this comment implied it did
 * (gate-validator MEDIUM-3): a single utterance that PARAPHRASES the modal — "if you meant: Grok
 * Build may run or modify contents in this directory, then yes, proceed" — matches in full. Text
 * matching cannot separate a modal from a model quoting one. What separates them here is WHEN this
 * runs and what `consentOutcomeIsHonest` then permits: the gate is read BEFORE any prompt is typed,
 * when nothing on that screen is a response to us, and a gate found AFTERWARDS may not explain a leg
 * that typed or submitted anything. Residual recorded as U323.
 *
 * @param {string} provider  an OP-12 provider id
 * @param {string|null} text the pane's rendered text
 * @returns {{gate: string|null, operator_step: string|null, matched: string[], reason: string}}
 */
function paneConsentGate(provider, text) {
  const signatures = PROVIDER_CONSENT_GATES[provider];
  if (!signatures) {
    return { gate: null, operator_step: null, matched: [],
      reason: `${JSON.stringify(provider)} is not an OP-12 provider — no consent signature is known `
        + "for it, and an unknown pane is never reported as gated" };
  }
  if (!nonEmpty(text)) {
    return { gate: null, operator_step: null, matched: [],
      reason: "the pane rendered nothing — a blank pane is a blank pane, not a consent gate" };
  }
  const flat = String(text).replace(/\s+/g, " ");
  for (const sig of signatures) {
    if (!sig.all.every((re) => re.test(flat))) continue;
    if ((sig.none || []).some((re) => re.test(flat))) continue;
    return {
      gate: sig.gate,
      operator_step: sig.operator_step,
      matched: sig.all.map(String),
      reason: `the pane is waiting on this CLI's own ${sig.gate.replace(/_/g, " ")} gate — a modal `
        + "that consumes keystrokes and can only be answered by the operator",
    };
  }
  return { gate: null, operator_step: null, matched: [],
    reason: "no known provider consent gate is on screen" };
}

/**
 * How a consent-gated leg is allowed to be reported. Skip-with-record (directive §6/§17) has two
 * halves, and both are enforced here:
 *
 *   • it spends NOTHING it could have avoided. A gate seen BEFORE the probe is drawn is never typed
 *     into, so it costs zero live exchanges of the directive's per-provider budget. A gate that
 *     rises AFTER quiescence — which is what `agy` did on the first run, settling on its sign-in
 *     screen and reaching the trust prompt only later — could not have been known, and the rule
 *     says so rather than convicting the check of a decision it never made;
 *   • it claims NOTHING. A gated leg is never green, it never reports an answer, and it names the
 *     one-time operator step, so the receipt reads as "owed, and here is who owes it".
 *
 * And the reclassification cannot become a hiding place. The pane text a late gate is read out of is
 * the buffer as rendered at that moment — for these full-screen TUIs, the alternate-buffer SCREEN,
 * which keeps no scrollback (U324) — so a session that took the keystrokes into a real prompt and
 * then said nothing (the U310 shape) could be re-labelled a consent skip by trust text still on that
 * screen, handing the operator a keystroke that fixes nothing while the U310 finding disappears. A
 * prompt that ECHOED proves the pane was not a modal: modals do not echo what you type. So a late
 * gate may not explain a leg whose prompt echoed.
 *
 * That was half a rule, and two review rounds were needed to find the right key. Echo detection is
 * evidence when it fires and nothing when it does not — a full-screen TUI on the alternate buffer
 * may never render the prompt back in a form `promptEchoed` can see. Round 2 keyed on SUBMISSION,
 * and the spec-auditor showed that was still wrong: in this check submission happens only AFTER an
 * echo, so `submitted && !echoed` cannot arise, and the residual route — TYPED, never echoed, a late
 * gate read off the post-typing screen — was not merely uncovered but asserted honest by a test.
 *
 * The key is TYPING. Once keystrokes have gone into the pane, a modal that ate them and a live
 * session that took them and said nothing look identical from out here, and picking the flattering
 * reading is exactly how a U310 disappears. So a late gate may explain only a leg that never typed;
 * anything else is an unexplained silence, which is a worse-looking receipt and a truer one. (The
 * echo and submission clauses are kept for the sharper message each can give.)
 *
 * @param {{gate: string|null, operator_step: string|null, detected_before_typing: boolean,
 *          typed: boolean, submitted: boolean, echoed: boolean, answer_seen: boolean,
 *          ok: boolean}} leg
 * @returns {{ok: boolean, reasons: string[], skipped: boolean}}
 */
function consentOutcomeIsHonest(leg) {
  const reasons = [];
  const o = leg && typeof leg === "object" ? leg : {};
  const gated = nonEmpty(o.gate);
  if (!gated) return { ok: true, reasons, skipped: false };
  if (!KNOWN_CONSENT_GATE_IDS.has(o.gate)) {
    reasons.push(`the leg claims a consent gate ${JSON.stringify(o.gate)} that no provider `
      + "signature in this module can produce — a skip is only ever explained by a gate the "
      + "matcher itself recognises, never by a name the caller invented");
  }
  if (o.ok === true) {
    reasons.push("a leg blocked on a provider consent gate is reported as PASSED — the live "
      + "acceptance §17 asks for did not happen, and a gate is not an answer");
  }
  if (o.detected_before_typing === true && (o.typed === true || o.submitted === true)) {
    reasons.push("a prompt was pushed into a consent modal the check had ALREADY seen — the gate "
      + "is not answerable by keystrokes the operator did not authorize, and the attempt spends "
      + "live budget on a prompt that reaches no model");
  }
  if (o.detected_before_typing !== true && o.echoed === true) {
    reasons.push("the prompt ECHOED into this pane and a consent gate is being blamed anyway — a "
      + "modal does not echo what you type, so the gate was read out of scrollback and what "
      + "actually happened is a session that took the keystrokes and said nothing (U310). A skip "
      + "here would hand the operator a keystroke that fixes nothing and lose the finding");
  }
  if (o.detected_before_typing !== true && (o.typed || o.submitted)) {
    reasons.push("this leg TYPED into the pane before any gate was seen, and a gate found "
      + "afterwards is being blamed for the silence — from out here a modal that ate the keystrokes "
      + "and a live session that took them and said nothing are indistinguishable, so the honest "
      + "report is an unexplained silence (U310's shape), not a consent skip the operator can fix "
      + "with a keystroke. Truthiness deliberately: a non-boolean `typed` fails this closed");
  }
  if (o.answer_seen === true) {
    reasons.push("a gated leg reports an answer — a modal waiting on the operator did not produce "
      + "one, so whatever satisfied the matcher was not a model");
  }
  if (!nonEmpty(o.operator_step)) {
    reasons.push("the gated leg names no operator step — an owed leg with no owner reads as an "
      + "unexplained failure of the product rather than a one-time human consent");
  }
  return { ok: reasons.length === 0, reasons, skipped: true };
}

//: Every acceptance leg a LIVE run still does not establish. A live receipt is the one most likely
//: to be read as covering everything, so its OWED block is required to be LONGER than the skipped
//: run's, not shorter.
const REQUIRED_OWED_KEYS = Object.freeze([
  "operator_first_use",          // a machine typing is not the operator using it
  "provider_answer_quality",     // an arithmetic token is not a capability claim
  "concurrent_same_provider",    // deliberately never exercised: one session per provider, §17
  "op6_provider_pane_records",   // U313 — claude_code/codex panes still hold no node record
  "containment_beyond_env",      // U25/U78(a) — job object + permission-profile binding still owed
  "provider_workspace_trust",    // the directory-trust consent each CLI raises: the operator's alone
]);

//: An OWED marker must cite something a reader can look up, not merely gesture at incompleteness.
//: Word-anchored: without the boundaries, "MENU42" satisfied the register-id alternative and the
//: rule was weaker than its own message (gate-validator MINOR-3).
const OWED_REFERENCE = /(\bU\d{1,3}\b|\bOP-\d{1,2}(\.\d)?\b|§\s*\d|directive\s+§|\bD-[A-Z0-9-]+|\binv(ariant)?\s*\d)/;

//: Every gate id any provider signature above can actually produce. A claimed gate outside this set
//: is a caller's invention, and `consentOutcomeIsHonest` refuses to let one explain a skip.
const KNOWN_CONSENT_GATE_IDS = new Set(
  Object.values(PROVIDER_CONSENT_GATES).flat().map((sig) => sig.gate));

function nonEmpty(s) { return typeof s === "string" && s.trim().length > 0; }

/** The comparable basename of an executable path (the ticket contract's own normalisation, applied
 * to a path this shell already spawned — quotes, padding, ADS suffix and extension removed). */
function executableBasename(value) {
  let v = String(value || "").trim().replace(/^"+|"+$/g, "").replace(/[\s.]+$/g, "");
  const parts = v.split(/[\\/]/);
  let base = parts[parts.length - 1] || "";
  base = base.split(":")[0];
  base = base.replace(/\.[a-z0-9]+$/i, "");
  return base.toLowerCase();
}

/** The model id an argv actually asks for: the value after the FIRST model flag, or null. */
function modelSlugInArgv(argv) {
  const list = Array.isArray(argv) ? argv.map(String) : [];
  for (let i = 0; i < list.length; i += 1) {
    const [flag, inlineValue] = list[i].split(/=(.*)/s);
    if (!MODEL_FLAGS.includes(flag)) continue;
    if (inlineValue !== undefined) return inlineValue;
    const next = list[i + 1];
    // A value that looks like a flag is a MISSING value, not a model id (the `--pid`-as-node-key
    // defect this build already found once, on the emitter's own argv parser).
    if (next === undefined || next.startsWith("-")) return null;
    return next;
  }
  return null;
}

/**
 * Which world is this host in — and may a LIVE receipt be written for these providers?
 * The mirror of 18C's `worldIsFailClosed`: there, an open switch REFUSED the receipt; here, a
 * closed one does.
 *
 * @param {object} authorization the picker enumeration's own `authorization` block
 * @returns {{live: boolean, op12_authorized: string[], op12_denied: string[],
 *            authorized_providers: string[], register_row: string|null, reason: string}}
 */
function worldIsLiveOpen(authorization) {
  const auth = authorization && typeof authorization === "object" ? authorization : null;
  const providers = auth && Array.isArray(auth.providers) ? auth.providers : null;
  if (!providers) {
    return {
      live: false, op12_authorized: [], op12_denied: OP12_PROVIDERS.slice(),
      authorized_providers: [], register_row: null,
      reason: "the live-operation authorization could not be read (no authorization block, or its "
        + "`providers` is not a list) — an unknown world is never treated as authorized, and a "
        + "LIVE receipt is never written against one",
    };
  }
  // The switch must SAY yes. `authorized:false` is it being off, and a MISSING `authorized` key is
  // a block this code cannot read — `!== false` treated that as consent, which is the fail-OPEN
  // reading of an ambiguous authorization on the gate that decides whether paid live sessions may
  // start (spec-auditor m-1). The provider list can still be populated by the code-pinned scope, so
  // reading the list alone would call a DENIED world live.
  const switched = auth.authorized === true;
  const yes = OP12_PROVIDERS.filter((p) => switched && providers.includes(p));
  const no = OP12_PROVIDERS.filter((p) => !yes.includes(p));
  if (!yes.length) {
    return {
      live: false, op12_authorized: [], op12_denied: no,
      authorized_providers: providers.slice(), register_row: (auth && auth.register_row) || null,
      reason: `the operator's switch authorizes ${providers.join(", ") || "nothing"} `
        + `(authorized=${JSON.stringify(auth.authorized)}) — no OP-12 provider is live, so every `
        + "live leg is skip-with-record (directive §17) and this receipt cannot be green",
    };
  }
  return {
    live: no.length === 0, op12_authorized: yes, op12_denied: no,
    authorized_providers: providers.slice(), register_row: (auth && auth.register_row) || null,
    reason: no.length === 0
      ? `the operator's switch cites ${auth.register_row || "an unnamed row"} and authorizes both `
        + `OP-12 providers (${yes.join(", ")}) — §17's live acceptance legs are runnable and OWED`
      : `the operator's switch authorizes ${yes.join(", ")} but DENIES ${no.join(", ")} — that `
        + "provider's live leg is skip-with-record (directive §17), and this receipt says so "
        + "rather than reporting partial coverage as acceptance",
  };
}

/**
 * §17's "exact provider+model verified", measured on what was SPAWNED.
 *
 * @param {{provider: string, option: object, launch: object, record: object, session: object,
 *          spawned: object, repoRoot: string, samePath?: (a: string, b: string) => boolean}} obs
 * @returns {{ok: boolean, reasons: string[], model_slug_launched: string|null}}
 */
function paneRunsExactlyThisSelection(obs) {
  const reasons = [];
  const o = obs && typeof obs === "object" ? obs : {};
  const provider = o.provider;
  const option = o.option && typeof o.option === "object" ? o.option : null;
  const launch = o.launch && typeof o.launch === "object" ? o.launch : null;
  const record = o.record && typeof o.record === "object" ? o.record : null;
  const session = o.session && typeof o.session === "object" ? o.session : null;
  const spawned = o.spawned && typeof o.spawned === "object" ? o.spawned : null;
  const expectedBinary = OP12_EXECUTABLE[provider];
  const samePath = typeof o.samePath === "function"
    ? o.samePath
    : (a, b) => String(a || "").toLowerCase() === String(b || "").toLowerCase();
  if (!expectedBinary) {
    return { ok: false, model_slug_launched: null,
      reasons: [`${JSON.stringify(provider)} is not an OP-12 provider`] };
  }
  if (!option) reasons.push("no picker option was captured for this provider");
  if (!launch) reasons.push("no launch result was captured");
  if (!record) reasons.push("no launcher record was captured");
  if (!session) reasons.push("no supervised session was captured");
  if (!spawned) reasons.push("no node-pty spawn was observed");
  if (reasons.length) return { ok: false, reasons, model_slug_launched: null };

  const argv = Array.isArray(record.argv) ? record.argv.map(String) : [];
  const slug = modelSlugInArgv(argv);

  // ---- it LAUNCHED, and it is governed as a frontier terminal --------------------------------
  if (launch.launched !== true) reasons.push(`the launch reports launched=${launch.launched}`);
  if (record.state !== "running") reasons.push(`the launcher record reads state=${record.state}`);
  if (record.supervised !== true) {
    reasons.push("the launcher record does not claim a SUPERVISED spawn (invariant 2)");
  }
  if (record.subscriptionGoverned !== true) {
    reasons.push("the pane is not subscription-governed — an OP-12 frontier pane holds a durable "
      + "I-X3 terminal (operator directive §12)");
  }
  if (record.subscriptionRef !== OP12_SUBSCRIPTION_REFS[provider]) {
    reasons.push(`the terminal is counted against ${JSON.stringify(record.subscriptionRef)}, not `
      + `${JSON.stringify(OP12_SUBSCRIPTION_REFS[provider])} — a lease in a bucket nothing else `
      + "reads is the U76 two-bucket defect");
  }
  if (!nonEmpty(record.leaseId)) reasons.push("the running pane holds no durable lease id");

  // ---- the EXACT provider: the binary that was actually spawned -------------------------------
  if (executableBasename(record.executable) !== expectedBinary) {
    reasons.push(`the pane's resolved binary is ${JSON.stringify(record.executable)}, whose `
      + `basename is not ${JSON.stringify(expectedBinary)}`);
  }
  if (executableBasename(argv[0]) !== expectedBinary) {
    reasons.push(`argv[0] is ${JSON.stringify(argv[0])}, not ${JSON.stringify(expectedBinary)} — `
      + "the process's own name is a separate fact from the file that was opened");
  }
  if (!samePath(spawned.file, record.executable)) {
    reasons.push(`the observed node-pty spawn (${JSON.stringify(spawned.file)}) is not this pane's `
      + `binary (${JSON.stringify(record.executable)}) — every fact read off that spawn would be `
      + "about a different session");
  }

  // ---- the EXACT model: what the argv asked for -----------------------------------------------
  if (!nonEmpty(slug)) {
    reasons.push("the launched argv carries no model id — an unpinned live call is not a verified "
      + `provider+model (looked for ${MODEL_FLAGS.join("/")})`);
  } else if (slug !== option.model_slug) {
    reasons.push(`the pane launched model ${JSON.stringify(slug)} while the operator's selection `
      + `was ${JSON.stringify(option.model_slug)}`);
  }

  // ---- and the chrome the operator READS agrees with all of it --------------------------------
  const chrome = record.chrome && typeof record.chrome === "object" ? record.chrome : {};
  if (chrome.governed !== true) reasons.push("the pane chrome does not claim a governed node");
  if (chrome.adapter !== provider) {
    reasons.push(`the pane chrome names adapter ${JSON.stringify(chrome.adapter)}, not `
      + `${JSON.stringify(provider)} (operator directive §14)`);
  }
  if (nonEmpty(option.label) && chrome.model_label !== option.label) {
    reasons.push(`the pane badge reads ${JSON.stringify(chrome.model_label)} while the selection `
      + `was ${JSON.stringify(option.label)} — the operator would be shown a model the process is `
      + "not running");
  }

  // ---- a LIVE process, in the governed workspace ------------------------------------------------
  if (session.state !== "RUNNING") reasons.push(`the supervised session is ${session.state}`);
  if (!Number.isInteger(session.pid) || session.pid <= 0) {
    reasons.push(`the supervised session reports pid ${JSON.stringify(session.pid)}`);
  }
  if (nonEmpty(o.repoRoot)) {
    if (!samePath(record.cwd, o.repoRoot)) {
      reasons.push(`the ticket bound the session to ${JSON.stringify(record.cwd)}, not the governed `
        + `workspace ${JSON.stringify(o.repoRoot)}`);
    }
    if (!samePath(spawned.cwd, o.repoRoot)) {
      reasons.push(`the ConPTY was started in ${JSON.stringify(spawned.cwd)}, not the governed `
        + `workspace ${JSON.stringify(o.repoRoot)}`);
    }
  }
  return { ok: reasons.length === 0, reasons, model_slug_launched: slug };
}

/**
 * §2.2 on the environment the CHILD was handed — one of the two sinks the 18C skip receipt could
 * not scan, because in that world nothing was ever spawned.
 *
 * NAMES only: the shell observes the child's env KEYS, never its values, so this measures that no
 * credential-bearing name reached the process. A value scan belongs to the transcript sink.
 *
 * @param {{spawned: object, scrubNames: string[], credentialNames?: string[]}} obs
 * @returns {{ok: boolean, reasons: string[], scrub_count: number}}
 */
function childEnvIsScrubbed(obs) {
  const reasons = [];
  const o = obs && typeof obs === "object" ? obs : {};
  const spawned = o.spawned && typeof o.spawned === "object" ? o.spawned : null;
  const scrubNames = (Array.isArray(o.scrubNames) ? o.scrubNames : []).filter(nonEmpty);
  const credentialNames = Array.isArray(o.credentialNames) && o.credentialNames.length
    ? o.credentialNames : OP12_CREDENTIAL_NAMES;
  if (!spawned) {
    return { ok: false, scrub_count: 0,
      reasons: ["no node-pty spawn was observed — an unmeasured child environment has not been "
        + "checked"] };
  }
  if (spawned.inheritedEnv === true) {
    reasons.push("the child inherited this shell's environment verbatim — the §2.2 scrub was not "
      + "applied at all");
  }
  const keys = Array.isArray(spawned.envKeys) ? spawned.envKeys.map(String) : [];
  if (!keys.length) {
    reasons.push("the observed spawn carries no environment key list — nothing was measured");
  }
  // Case-INSENSITIVELY, because Windows env names are case-insensitive to the OS while a plain
  // object delete is not: that divergence is what U105 exists for, and an exact-spelling check
  // would be blind to the class of leak it claims to guard.
  const lower = new Set(keys.map((k) => k.toLowerCase()));
  if (keys.length && !lower.has("path")) {
    reasons.push("the child lost PATH — a scrub that empties the environment proves nothing about "
      + "the scrub");
  }
  if (!scrubNames.length) {
    reasons.push("the ticket named no environment variable to drop — with nothing to remove, an "
      + "absent name is not evidence the removal works");
  }
  for (const name of scrubNames) {
    if (lower.has(String(name).toLowerCase())) {
      reasons.push(`the child environment still carries ${name}, which the ticket named for `
        + "removal (§2.2)");
    }
  }
  for (const name of credentialNames) {
    if (lower.has(String(name).toLowerCase())) {
      reasons.push(`the child environment carries the credential-bearing name ${name} (§17: no `
        + "credential material in any sink)");
    }
  }
  return { ok: reasons.length === 0, reasons, scrub_count: scrubNames.length };
}

/**
 * Did a MODEL answer, as opposed to a terminal echoing?
 *
 * Every conjunct is load-bearing and each fails independently, so the receipt can say WHICH half
 * broke: a live pane that never received the keystrokes and a live pane whose model said nothing
 * are different findings, and reporting only their AND hides which one happened.
 *
 * @param {{falsifiable: boolean, absentBefore: boolean, echoed: boolean, submitted: boolean,
 *          answer: {seen: boolean, form: string|null}}} obs
 * @returns {{ok: boolean, reasons: string[]}}
 */
function liveAnswerIsHonest(obs) {
  const reasons = [];
  const o = obs && typeof obs === "object" ? obs : {};
  const answer = o.answer && typeof o.answer === "object" ? o.answer : { seen: false, form: null };
  if (o.falsifiable !== true) {
    reasons.push("the drawn probe carries its own answer — a receipt built on it would prove "
      + "nothing about a model");
  }
  if (o.absentBefore !== true) {
    reasons.push("the answer token was already in the pane before the prompt was submitted — "
      + "scrollback would satisfy the leg for free");
  }
  if (o.echoed !== true) {
    reasons.push("what was typed never appeared in the pane — the keystrokes are not reaching the "
      + "live session (this fails SEPARATELY from the answer, so a dead model cannot be reported "
      + "as a dead terminal or the reverse)");
  }
  if (o.submitted !== true) reasons.push("the submit keystroke could not be delivered");
  if (answer.seen !== true) {
    reasons.push("no answer to the probe ever appeared — a session that exits, cancels or says "
      + "nothing is NOT a live response, however cleanly it exits (U310)");
  } else if (!["prefixed", "bare"].includes(answer.form)) {
    reasons.push(`the answer was reported in form ${JSON.stringify(answer.form)}, which is not one `
      + "the probe recognises");
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * The pane was a registered Sovereign node for the whole of its life, on THIS host's durable log,
 * bound to THIS session (invariant 2; U315's binding).
 *
 * @param {{rows: object[], nodeKey: string, sessionId: string, recordUuid: string, pid: number}} obs
 * @returns {{ok: boolean, reasons: string[], incarnation: number|null, states: string[]}}
 */
function nodeRecordLifecycleIsComplete(obs) {
  const reasons = [];
  const o = obs && typeof obs === "object" ? obs : {};
  const rows = Array.isArray(o.rows) ? o.rows : [];
  const nodeKey = String(o.nodeKey || "");
  const sessionId = String(o.sessionId || "");
  const recordUuid = String(o.recordUuid || "");
  const pid = o.pid;
  if (!nodeKey || !sessionId) {
    return { ok: false, incarnation: null, states: [],
      reasons: ["a node lifecycle is read for a (node key, session) pair; one of them is missing"] };
  }
  const mine = rows.filter((r) => r && r.node_id === nodeKey);
  const spawns = mine.filter((r) => r.kind === "spawn"
    && r.data && r.data.session_id === sessionId);
  if (spawns.length !== 1) {
    return { ok: false, incarnation: null, states: [],
      reasons: [`the durable node log carries ${spawns.length} spawn row(s) for ${nodeKey} under `
        + `session ${sessionId} — exactly one is expected (invariant 12: a record is written once, `
        + "and never re-written)"] };
  }
  const spawn = spawns[0];
  const incarnation = Number.isInteger(spawn.incarnation) ? spawn.incarnation : null;
  const record = (spawn.data && spawn.data.node_record) || {};
  if (recordUuid && record.node_id !== recordUuid) {
    reasons.push(`the log's spawn row carries record ${JSON.stringify(record.node_id)} while the `
      + `ticket reported ${JSON.stringify(recordUuid)} — the receipt would be about another record`);
  }
  if (record.adapter && !OP12_PROVIDERS.includes(record.adapter)) {
    reasons.push(`the record's adapter is ${JSON.stringify(record.adapter)}, which is not an `
      + "OP-12 provider");
  }
  if (spawn.data && spawn.data.adapter_schema_version !== "node@1.1") {
    reasons.push(`the record was written under ${JSON.stringify(spawn.data.adapter_schema_version)}, `
      + "not the successor schema node@1.1 OP-12.1 authorized");
  }
  const sameIncarnation = mine.filter((r) => r.incarnation === incarnation);
  const transitions = sameIncarnation.filter((r) => r.kind === "transition");
  const states = transitions.map((r) => (r.data && r.data.to) || null).filter(Boolean);
  const ready = transitions.find((r) => r.data && r.data.to === "READY");
  if (!ready) {
    reasons.push("the log has no SPAWNING → READY transition — the pane's record never recorded "
      + "the moment a supervised process existed");
  } else {
    if (Number.isInteger(pid) && ready.data.pid !== pid) {
      reasons.push(`the READY transition carries pid ${JSON.stringify(ready.data.pid)}, not the `
        + `supervised session's ${pid} — the attestation is about another process`);
    }
    // …and it came FROM `SPAWNING`. Only checking that a READY row exists let the docstring's
    // "SPAWNING → READY" be an unverified half of the sentence (spec-auditor m-11): a record that
    // reached READY from anywhere else did not have the life this receipt describes.
    if (ready.data.frm !== "SPAWNING") {
      reasons.push(`the READY transition came from ${JSON.stringify(ready.data.frm)}, not SPAWNING `
        + "— the record did not live the SPAWNING → READY → TERMINATED life this receipt claims");
    }
  }
  const terminated = transitions.find((r) => r.data && r.data.to === "TERMINATED");
  if (!terminated) {
    reasons.push("the log has no transition to TERMINATED — the record still reads open for a "
      + "session this run ended (D-LOOP-1, in the one place an auditor would look)");
  }
  if (!sameIncarnation.some((r) => r.kind === "exit")) {
    reasons.push("the log carries no exit row for this incarnation");
  }
  return { ok: reasons.length === 0, reasons, incarnation, states };
}

/**
 * The operator's node log is still an immutable, hash-chained append-only history (invariant 12).
 * @param {object[]} rows every row on the log, in file order
 * @returns {{ok: boolean, reasons: string[], rows: number}}
 */
function appendOnlyChainIsIntact(rows) {
  const reasons = [];
  const list = Array.isArray(rows) ? rows : null;
  if (!list) return { ok: false, reasons: ["the node log could not be read as rows"], rows: 0 };
  if (!list.length) return { ok: false, reasons: ["the node log is empty"], rows: 0 };
  let previous = null;
  list.forEach((row, i) => {
    if (!row || typeof row !== "object") {
      reasons.push(`row ${i} is not an object`);
      return;
    }
    const expectedSeq = i + 1;
    if (row.seq !== expectedSeq) {
      reasons.push(`row ${i} reports seq ${JSON.stringify(row.seq)}, not ${expectedSeq} — a gap or `
        + "a reorder in an append-only history");
    }
    const expectedPrev = previous === null ? GENESIS_PREV_HASH : previous.hash;
    if (row.prev_hash !== expectedPrev) {
      reasons.push(`row ${i} (seq ${row.seq}) does not link to its predecessor — the chain is `
        + "broken, which means the history was edited, not appended to");
    }
    if (!nonEmpty(row.hash)) reasons.push(`row ${i} carries no hash`);
    previous = row;
  });
  return { ok: reasons.length === 0, reasons, rows: list.length };
}

/**
 * Every acceptance leg this LIVE run still does not establish is NAMED, with a reference.
 * @returns {{ok: boolean, reasons: string[]}}
 */
function owedLegsAreNamed(owed) {
  const reasons = [];
  const block = owed && typeof owed === "object" ? owed : {};
  for (const key of REQUIRED_OWED_KEYS) {
    const value = block[key];
    if (!nonEmpty(value)) {
      reasons.push(`the OWED block does not name ${key} — silence about an unevidenced leg reads `
        + "as coverage, and a LIVE receipt is the one most likely to be read as covering "
        + "everything");
      continue;
    }
    if (!OWED_REFERENCE.test(value)) {
      reasons.push(`the OWED marker for ${key} cites nothing a reader can look up `
        + "(expected an issue id, a register row, an invariant or a directive section)");
    }
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * §17's "repo status unchanged" line, as a rule instead of a comparison.
 *
 * The first version compared the two measurements to each other, so two DIRTY readings agreed and
 * the field read `ok:true` (gate-validator MEDIUM-4). The field is published under the name
 * "repo unchanged BY the run", which asserts two things — clean before, clean after — and it must
 * assert both itself rather than borrow one from a sibling conjunct.
 *
 * @returns {{ok: boolean, before: object, after: object, scope: string}}
 */
function repoUnchangedByTheRun(before, after) {
  const b = before && typeof before === "object" ? before : {};
  const a = after && typeof after === "object" ? after : {};
  const bUntracked = (b.unexpected_untracked_product_files || []).length;
  const aUntracked = (a.unexpected_untracked_product_files || []).length;
  return {
    ok: b.tracked_product_tree_clean === true && a.tracked_product_tree_clean === true
      && bUntracked === aUntracked,
    before: { clean: b.tracked_product_tree_clean ?? null, untracked: bUntracked },
    after: { clean: a.tracked_product_tree_clean ?? null, untracked: aUntracked },
    scope: "the product paths git can speak for, CLEAN at both ends rather than merely equal; a "
      + "change elsewhere in the repo is NOT measured here and is not claimed",
  };
}

/**
 * Which credential names this check may plant a sentinel under, and which it must leave alone.
 *
 * §2.2 and OP-12 §13 forbid READING a credential in the same breath as storing one. A name the host
 * already sets is therefore SKIPPED — not captured for later restore, not overwritten with a
 * placeholder — and reported by name, because the names are this build's own constants while the
 * values are the operator's (spec-audit round-2 MEDIUM-5, closing U321(d)'s live half).
 *
 * @returns {{planted: string[], skipped: string[], sentinels: string[]}} `sentinels` is aligned with
 *   `planted`: a string nobody wrote cannot be found, and scanning for it would inflate the scan.
 */
function sentinelPlan(env, names, pid) {
  const source = env && typeof env === "object" ? env : {};
  const planted = [];
  const skipped = [];
  const sentinels = [];
  for (const name of Array.isArray(names) ? names : []) {
    if (Object.prototype.hasOwnProperty.call(source, name)) { skipped.push(name); continue; }
    planted.push(name);
    sentinels.push(`sow-18e-sentinel-${name}-${pid}`);
  }
  return { planted, skipped, sentinels };
}

/**
 * The §17 credential sinks this check can actually read, as a map the scanner refuses on `null`.
 *
 * Every entry is a place THIS RUN wrote to or through. The two durable stores are here because the
 * `py -3.12` children that write them inherit this process's sentinel-bearing environment
 * (spec-audit M-2): they are the only sinks a serialization change could put an env value into.
 * The pane entry is named for what it is — the screen as rendered at teardown, not a transcript:
 * both OP-12 CLIs are full-screen TUIs on xterm's alternate buffer, which keeps no scrollback
 * (U324).
 *
 * @returns {Object<string, string|null>}
 */
function credentialSinkMap(parts) {
  const p = parts && typeof parts === "object" ? parts : {};
  const sinks = {};
  sinks[p.logFile || "main-process.log (path unknown)"] = p.logFile ? p.logText ?? null : null;
  sinks[`${p.receiptName || "the receipt"} (this receipt, pre-write)`] = p.receiptPayload ?? null;
  // A missing path would publish the sink name "undefined (…)" — fails closed on the value either
  // way, but a receipt should not print that (spec-audit NIT-2).
  sinks[`${nonEmpty(p.nodeLogPath) ? p.nodeLogPath : "the node log (path unknown)"} `
    + "(the operator's durable node log)"] = p.nodeLogText ?? null;
  sinks[`${nonEmpty(p.ledgerPath) ? p.ledgerPath : "the lease ledger (path unknown)"} `
    + "(the operator's durable lease ledger)"] = p.ledgerText ?? null;
  for (const provider of Array.isArray(p.providers) ? p.providers : []) {
    sinks[`${provider} pane screen as rendered at teardown`] =
      (p.transcripts || {})[provider] ?? null;
  }
  return sinks;
}

module.exports = {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, OP12_ALLOWANCE,
  OP12_EXECUTABLE, MODEL_FLAGS, REQUIRED_OWED_KEYS, GENESIS_PREV_HASH, PROVIDER_CONSENT_GATES,
  KNOWN_CONSENT_GATE_IDS, repoUnchangedByTheRun, credentialSinkMap, sentinelPlan,
  executableBasename, modelSlugInArgv, paneConsentGate, consentOutcomeIsHonest,
  worldIsLiveOpen, paneRunsExactlyThisSelection, childEnvIsScrubbed, liveAnswerIsHonest,
  nodeRecordLifecycleIsComplete, appendOnlyChainIsIntact, owedLegsAreNamed,
  // re-exported so the check has ONE import for the rules it shares with the 18C receipt
  leasesAreZero, noCredentialMaterial,
};
