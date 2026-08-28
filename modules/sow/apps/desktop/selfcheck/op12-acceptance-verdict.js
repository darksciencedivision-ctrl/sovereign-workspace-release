"use strict";
/**
 * Phase 18C `.close` — what the OP-12 live-acceptance receipt is ALLOWED to claim.
 *
 * Directive §17 defines 18C acceptance as ONE harmless live probe per provider plus ONE in-Electron
 * receipt per provider (picker → supervised pane → exact provider+model verified → harmless prompt →
 * live response → teardown → lease 0 → no credential material in any log → tree clean). Its ENTRY
 * CONDITION is the operator's: each CLI's own login, **and the operator's own edit to the
 * never-committed `config/live_operation.json`**. On this host that file cites `OP-6`, so both OP-12
 * providers are DENIED. Unmet ⇒ **skip-with-record, not failure** (§17) — and what this receipt
 * evidences instead is the fail-closed world itself: everything except the operator's switch is
 * ready, and the switch is the thing that refuses.
 *
 * These rules are kept out of the check, and pure, so `node --test` can falsify each one without a
 * window, a supervisor or a provider CLI. Each exists because a green 18C receipt could otherwise be
 * produced by the wrong world or the wrong gate:
 *
 *   • `worldIsFailClosed` — the receipt may only stand in for the live legs while the operator has
 *     NOT opened the switch. The moment they do, the live legs are runnable and owed, and a
 *     fail-closed receipt would be a summary of a world that no longer exists. Unreadable ⇒ not
 *     fail-closed either: "we could not tell" is never "we checked".
 *   • `authorityRefusalIsFailClosed` — reads the GATE ID and the ticket's own gate map, never prose
 *     (`emit_worker_launch._gate_id` exists because a receipt leg that regex-matched a reason once
 *     went green on an unrelated crash). It additionally requires every gate BEFORE the live one to
 *     have PASSED: a refusal at `host_enumeration` proves the option was never the host's, and one
 *     with `cli_present:false` proves nothing about the operator's switch.
 *   • `leasesAreZero` / `statusBarPaintsZeroOfOne` — §17's lease-to-zero line, measured on the
 *     durable ledger AND read back off the surface the operator actually reads (invariant 27:
 *     "visible" cannot mean "computed").
 *   • `noCredentialMaterial` — §17's "no credential material in any log" as a measurement: sentinel
 *     values are planted under the OP-12 credential NAMES and must appear in neither of the two
 *     sinks this run can read (the shell's durable main-process log and the receipt payload — the
 *     check enumerates them in `sinks_checked`; "nowhere the run wrote" was more than it measures).
 *     §2.2 stands throughout — the sentinels are placeholders, and no real credential is ever read.
 *   • `owedLegsAreNamed` — the most dangerous failure of a skip-with-record is silence about what
 *     was skipped, so every unevidenced leg must be named with a reference a reader can look up.
 *
 * HONEST RESIDUAL: the OWED list is AUTHORED (the same residual `fully-live-verdict` records). This
 * enforces that every leg we KNOW is unevidenced is named; it cannot discover one nobody wrote down.
 */

//: The two OP-12 providers, in the order the operator directive names them. Never a third spelling —
//: the subscription refs below are IMPORTED from the ticket contract that already owns them.
const OP12_PROVIDERS = Object.freeze(["grok_build", "google_antigravity"]);

const { ADAPTER_SUBSCRIPTION_REF } = require("../picker/launch-source");

//: provider → the ONE durable I-X3 resource a terminal for it is counted against (operator
//: directive §12, allowance 1 each, never merged). Projected from the ticket contract's own map so
//: this module cannot disagree with the launcher about which bucket to read.
const OP12_SUBSCRIPTION_REFS = Object.freeze(Object.fromEntries(
  OP12_PROVIDERS.map((p) => [p, ADAPTER_SUBSCRIPTION_REF[p]]),
));

//: The per-provider display ceiling the operator directive §12 fixes at 1. Read as a constant here
//: only to state what "0/1" means; the status-bar leg compares against the SHIPPED model's own map.
const OP12_ALLOWANCE = 1;

//: Credential-bearing env names this receipt plants sentinels under. A SUBSET of the Python
//: authority's `adapters/frontier/provider_cli_common.PROVIDER_CREDENTIAL_ENV_KEYS`, pinned to it by
//: tests/unit/test_op12_acceptance_constants_pinned.py so a name that leaves the authority cannot
//: quietly stay here. §2.2: every value PLANTED is a placeholder, and no credential is created,
//: stored or transmitted. Exactly one read exists and it is not a leak: a check restores the
//: environment it changed, so on a host where one of these names is already set its prior value is
//: held in memory for the run's duration and written back — never logged, never scanned for, never
//: put in a receipt (U321(d); the earlier "no real credential is ever read" was not strictly true).
const OP12_CREDENTIAL_NAMES = Object.freeze([
  "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTIGRAVITY_API_KEY",
]);

//: The gate `emit_worker_launch` names when `LiveAuthorizationError` refuses — the ONE gate this
//: receipt's central leg is about. An id cannot be borrowed the way prose can.
const LIVE_GATE_ID = "live_operation";

//: The other provider's identifying words, so "this refusal names its own provider" is checked in
//: BOTH directions (operator directive §14 — never one provider's name under another's) instead of
//: merely finding the right word somewhere.
const FOREIGN_WORDS = Object.freeze({
  grok_build: ["agy", "antigravity", "gemini"],
  google_antigravity: ["grok", "xai"],
});

//: Every 18C acceptance leg this fail-closed run cannot perform. Each must be NAMED in the receipt
//: with a reference — a reader who sees a green 18C receipt must be able to enumerate exactly what
//: it did not establish.
const REQUIRED_OWED_KEYS = Object.freeze([
  "live_provider_probe",        // §17's GROK_PROVIDER_OK / GEMINI_PROVIDER_OK — never executed
  "live_in_electron_receipt",   // §17's per-provider live pane receipt — never executed
  "provider_node_record",       // U227 ruled by OP-12.1 (node@1.1); records now admissible, none wired
  "antigravity_auth_state",     // recorded at 18A: `agy` auth is UNVERIFIABLE offline
  "grok_auth_state",            // the OTHER half of §17's per-CLI login entry condition
  "probe_acceptance_holes",     // U238 — owner 18C; the two holes that decide the LIVE verdict
  "operator_live_switch",       // the entry condition itself: the operator's own file edit
]);

//: An OWED marker must cite something a reader can look up, not merely gesture at incompleteness.
const OWED_REFERENCE = /(U\d{1,3}|OP-\d{1,2}|§\s*\d|directive\s+§|D-[A-Z0-9-]+)/;

function nonEmpty(s) { return typeof s === "string" && s.trim().length > 0; }

/**
 * A refusal text with its ENUMERATED SCOPE removed, for the §14 cross-provider check.
 *
 * The live-authorization refusal legitimately lists the authorized providers
 * (`… scoped providers ['claude_code', 'openai_codex_cli']`). The moment the operator names ONE
 * OP-12 provider in their switch, the OTHER provider's refusal will carry `grok_build` /
 * `google_antigravity` inside that list AS DATA, and a bare substring rule would flag the honest
 * text of the world 18C is trying to reach (spec-audit MINOR-12). Bracketed lists are stripped
 * first; what remains is the prose an operator reads, which is what §14 governs.
 */
function proseOnly(text) {
  return String(text || "").replace(/\[[^\]]*\]/g, " ");
}

/** The other provider's identifying words present in a refusal's PROSE (never in its scope list). */
function foreignWordsIn(text, provider) {
  const prose = proseOnly(text).toLowerCase();
  return (FOREIGN_WORDS[provider] || []).filter((w) => prose.includes(w));
}

/**
 * Which world is this host in — and may a fail-closed receipt stand in for the live legs?
 * @param {object} authorization the picker enumeration's own `authorization` block
 * @returns {{fail_closed: boolean, op12_authorized: string[], authorized_providers: string[],
 *            register_row: string|null, reason: string}}
 */
function worldIsFailClosed(authorization) {
  const auth = authorization && typeof authorization === "object" ? authorization : null;
  const providers = auth && Array.isArray(auth.providers) ? auth.providers : null;
  if (!providers) {
    return {
      fail_closed: false, op12_authorized: [], authorized_providers: [], register_row: null,
      reason: "the live-operation authorization could not be read (no authorization block, or its "
        + "`providers` is not a list) — an unknown world is refused, never assumed fail-closed",
    };
  }
  const op12 = OP12_PROVIDERS.filter((p) => providers.includes(p));
  if (op12.length) {
    return {
      fail_closed: false, op12_authorized: op12, authorized_providers: providers.slice(),
      register_row: auth.register_row || null,
      reason: `the operator's switch authorizes ${op12.join(", ")} — the 18C live acceptance legs `
        + "are runnable and therefore OWED; a fail-closed receipt must not stand in for them",
    };
  }
  return {
    fail_closed: true, op12_authorized: [], authorized_providers: providers.slice(),
    register_row: auth.register_row || null,
    reason: `the operator's switch cites ${auth.register_row || "an unnamed row"} and authorizes `
      + `${providers.join(", ")} — both OP-12 providers are DENIED (skip-with-record, directive §17)`,
  };
}

/**
 * Did the AUTHORITY (the Python emitter) refuse this provider at the live-operation gate, with every
 * earlier gate passed, nothing spawned and nothing leased?
 *
 * @param {{provider: string, ticket: object, launch: object,
 *          sessions_before: number, sessions_after: number}} attempt
 * @returns {{ok: boolean, reasons: string[]}}
 */
function authorityRefusalIsFailClosed(attempt) {
  const reasons = [];
  const a = attempt && typeof attempt === "object" ? attempt : {};
  const provider = a.provider;
  const ticket = a.ticket && typeof a.ticket === "object" ? a.ticket : null;
  const launch = a.launch && typeof a.launch === "object" ? a.launch : null;
  if (!OP12_PROVIDERS.includes(provider)) {
    return { ok: false, reasons: [`${JSON.stringify(provider)} is not an OP-12 provider`] };
  }
  if (!ticket) reasons.push("no governed ticket was captured for this provider");
  if (!launch) reasons.push("no launch result was captured for this provider");
  if (!ticket || !launch) return { ok: false, reasons };

  // ---- the refusal itself, by GATE ID on both producers -----------------------------------
  if (ticket.authorized !== false) reasons.push(`the ticket reports authorized=${ticket.authorized}`);
  if (ticket.refused !== true) reasons.push(`the ticket reports refused=${ticket.refused}`);
  if (launch.launched !== false) reasons.push(`the launcher reports launched=${launch.launched}`);
  if (ticket.refused_by !== LIVE_GATE_ID) {
    reasons.push(`the ticket names gate ${JSON.stringify(ticket.refused_by)}, not `
      + `${JSON.stringify(LIVE_GATE_ID)} — a refusal by another gate says nothing about the switch`);
  }
  if (launch.refusedBy !== ticket.refused_by) {
    reasons.push(`the launcher and the ticket disagree about which gate refused `
      + `(${JSON.stringify(launch.refusedBy)} vs ${JSON.stringify(ticket.refused_by)})`);
  }

  // ---- the gates BEFORE it must have PASSED -------------------------------------------------
  const gates = ticket.gates && typeof ticket.gates === "object" ? ticket.gates : {};
  if (gates.selection_offered !== true) {
    reasons.push("gates.selection_offered is not true — the option was not verified against this "
      + "host's own enumeration, so the refusal is about the selection, not the switch");
  }
  if (gates.cli_present !== true) {
    reasons.push("gates.cli_present is not true — an absent CLI refuses the same way on an "
      + "authorized host and an unauthorized one, so this proves nothing about the switch");
  }
  if (gates.live_operation_authorized !== false) {
    reasons.push(`gates.live_operation_authorized is ${JSON.stringify(gates.live_operation_authorized)}, `
      + "not false");
  }
  if (gates.ix3_counted !== false) reasons.push(`gates.ix3_counted is ${JSON.stringify(gates.ix3_counted)}`);

  // ---- nothing born, nothing counted, nothing left behind ------------------------------------
  if (ticket.lease !== null && ticket.lease !== undefined) {
    reasons.push("the refusal ticket carries a lease — a refusal that leased a terminal is not "
      + "fail-closed");
  }
  if (ticket.launch !== null && ticket.launch !== undefined) {
    reasons.push("the refusal ticket carries a launch block (argv/executable) — nothing was "
      + "authorized, so nothing may be spawnable from it");
  }
  if (ticket.subscription_governed !== false) {
    reasons.push(`the refusal ticket reports subscription_governed=${ticket.subscription_governed}`);
  }
  if (ticket.governor_released !== true) {
    reasons.push("governor_released is not true — the in-process governor slot leaked through the "
      + "refusal");
  }
  if (!Number.isInteger(a.sessions_before) || !Number.isInteger(a.sessions_after)) {
    reasons.push("the live-session count around the attempt was not measured");
  } else if (a.sessions_after !== a.sessions_before) {
    reasons.push(`the live session count moved during a refusal `
      + `(${a.sessions_before} → ${a.sessions_after}) — a refusal may never start anything`);
  }

  // ---- §14: the refusal names its OWN provider, and none of the other's words ----------------
  const texts = [ticket.reason, launch.reason].filter(nonEmpty).join(" ");
  if (!texts) {
    reasons.push("the refusal carries no reason at all (a silent refusal is not an honest one)");
  } else {
    if (!texts.includes(provider)) reasons.push(`the refusal does not name ${provider}`);
    const foreign = foreignWordsIn(texts, provider);
    if (foreign.length) {
      reasons.push(`the refusal for ${provider} carries the other provider's identifying words `
        + `(${foreign.join(", ")}) — operator directive §14`);
    }
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * The operator's own CLICK — refused by the shell's front-line guard before the authority is asked.
 * @returns {{ok: boolean, reasons: string[]}}
 */
function uxGuardRefused(result, provider) {
  const reasons = [];
  const r = result && typeof result === "object" ? result : null;
  if (!r) return { ok: false, reasons: ["no selection result was captured"] };
  if (r.recorded !== false) {
    reasons.push(`the click was RECORDED (recorded=${r.recorded}) — the front-line guard let it `
      + "through to the launcher");
  }
  if (r.launched !== false) reasons.push(`the click reports launched=${r.launched}`);
  if (!nonEmpty(r.error)) reasons.push("the refusal carries no reason (a silent grey is a dishonest one)");
  else {
    if (!String(r.error).includes(provider)) {
      reasons.push(`the refusal does not name ${provider} — the operator cannot tell which option `
        + "was refused");
    }
    // §14 in both directions here TOO. This is the text the operator actually reads (the authority's
    // reason reaches a log; this reaches the drawer), and it was the one leg not checking for the
    // other provider's words (spec-audit MINOR-12).
    const foreign = foreignWordsIn(r.error, provider);
    if (foreign.length) {
      reasons.push(`the click refusal for ${provider} carries the other provider's identifying `
        + `words (${foreign.join(", ")}) — operator directive §14`);
    }
  }
  return { ok: reasons.length === 0, reasons };
}

/**
 * §17's lease line, on the DURABLE ledger: both OP-12 subscriptions hold nothing.
 * @returns {{ok: boolean, reasons: string[], in_use: Record<string, number|null>}}
 */
function leasesAreZero(status) {
  const reasons = [];
  const inUse = {};
  const subs = status && typeof status === "object" && status.subscriptions
    && typeof status.subscriptions === "object" ? status.subscriptions : null;
  if (!subs) {
    for (const p of OP12_PROVIDERS) inUse[OP12_SUBSCRIPTION_REFS[p]] = null;
    return {
      ok: false,
      reasons: ["the durable lease status could not be read — an unmeasured ledger is unknown, and "
        + "unknown fails closed (it is never zero)"],
      in_use: inUse,
    };
  }
  for (const provider of OP12_PROVIDERS) {
    const ref = OP12_SUBSCRIPTION_REFS[provider];
    const entry = subs[ref];
    // An absent resource genuinely holds nothing: the ledger only carries a bucket once something
    // has been counted in it. `entry` present with a non-integer `in_use` is a shape drift, not a
    // zero.
    if (entry === undefined || entry === null) { inUse[ref] = 0; continue; }
    const n = entry.in_use;
    if (!Number.isInteger(n)) {
      inUse[ref] = null;
      reasons.push(`${ref} reports in_use=${JSON.stringify(n)} — not a count`);
      continue;
    }
    inUse[ref] = n;
    if (n !== 0) reasons.push(`${ref} still holds ${n} terminal(s) — §17 requires the lease back at 0`);
  }
  return { ok: reasons.length === 0, reasons, in_use: inUse };
}

/**
 * The same fact where the operator READS it: the status bar's own rows AND its painted text.
 * @param {Array<{provider: string, label: string, allowance: number}>} rows the bar's model
 * @param {string} paintedText the bar's rendered text
 * @returns {{ok: boolean, reasons: string[], painted: Record<string, string|null>}}
 */
function statusBarPaintsZeroOfOne(rows, paintedText) {
  const reasons = [];
  const painted = {};
  const list = Array.isArray(rows) ? rows : [];
  const text = typeof paintedText === "string" ? paintedText : "";
  for (const provider of OP12_PROVIDERS) {
    const row = list.find((r) => r && r.provider === provider) || null;
    painted[provider] = row ? row.label || null : null;
    if (!row) {
      reasons.push(`the status bar has no row for ${provider}`);
      continue;
    }
    if (row.allowance !== OP12_ALLOWANCE) {
      reasons.push(`${provider} is shown at allowance ${row.allowance}, not ${OP12_ALLOWANCE} `
        + "(U255 — a merged ceiling advertises a terminal the governor refuses)");
    }
    if (row.label !== `0/${OP12_ALLOWANCE}`) {
      reasons.push(`${provider} is shown as ${JSON.stringify(row.label)}, not "0/${OP12_ALLOWANCE}"`);
    } else if (!text.includes(`0/${OP12_ALLOWANCE}`)) {
      reasons.push(`the bar never painted "0/${OP12_ALLOWANCE}" — the model says ${provider} holds `
        + "nothing and the operator cannot see it (invariant 27)");
    }
  }
  return { ok: reasons.length === 0, reasons, painted };
}

/**
 * §17's "no credential material in any log", measured. The failure text names the SINK, never the
 * value — a leak report that repeats the value is itself a leak.
 *
 * @param {Record<string, string|null>} sinks  name → the text this run wrote there (null = unread)
 * @param {string[]} sentinels                 the placeholder values planted under the OP-12 names
 * @returns {{ok: boolean, reasons: string[], sinks_checked: string[], sentinels_checked: number}}
 */
function noCredentialMaterial(sinks, sentinels) {
  const reasons = [];
  const map = sinks && typeof sinks === "object" ? sinks : {};
  const values = (Array.isArray(sentinels) ? sentinels : []).filter(nonEmpty);
  const names = Object.keys(map);
  if (!values.length) {
    reasons.push("no sentinel value was planted — a scan with nothing to look for cannot establish "
      + "that nothing leaked");
  }
  if (!names.length) reasons.push("no sink was scanned");
  for (const name of names) {
    const text = map[name];
    if (typeof text !== "string") {
      reasons.push(`${name} could not be read — an unread sink has not been checked`);
      continue;
    }
    for (const value of values) {
      if (text.includes(value)) {
        reasons.push(`a planted sentinel value reached ${name} (value withheld from this report)`);
        break;
      }
    }
  }
  return { ok: reasons.length === 0, reasons, sinks_checked: names, sentinels_checked: values.length };
}

/**
 * Every acceptance leg this fail-closed run could not perform is NAMED, with a reference.
 * @returns {{ok: boolean, reasons: string[]}}
 */
function owedLegsAreNamed(owed) {
  const reasons = [];
  const block = owed && typeof owed === "object" ? owed : {};
  for (const key of REQUIRED_OWED_KEYS) {
    const value = block[key];
    if (!nonEmpty(value)) {
      reasons.push(`the OWED block does not name ${key} — silence about an unevidenced leg reads `
        + "as coverage");
      continue;
    }
    if (!OWED_REFERENCE.test(value)) {
      reasons.push(`the OWED marker for ${key} cites nothing a reader can look up `
        + "(expected an issue id, a register row or a directive section)");
    }
  }
  return { ok: reasons.length === 0, reasons };
}

module.exports = {
  OP12_PROVIDERS, OP12_SUBSCRIPTION_REFS, OP12_CREDENTIAL_NAMES, OP12_ALLOWANCE,
  REQUIRED_OWED_KEYS, LIVE_GATE_ID, FOREIGN_WORDS,
  worldIsFailClosed, authorityRefusalIsFailClosed, uxGuardRefused, leasesAreZero,
  statusBarPaintsZeroOfOne, noCredentialMaterial, owedLegsAreNamed,
};
