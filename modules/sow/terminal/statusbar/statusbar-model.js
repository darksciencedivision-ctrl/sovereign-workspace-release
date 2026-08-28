"use strict";
/**
 * Subscription-concurrency status-bar view model (directive §11 track 15A), phase-15a.statusbar.
 *
 * The OP-6 authorization raised the per-subscription terminal allowance to at most 2 and asked
 * that "the n/2 count live in the shell status bar". The concurrency DATA is produced entirely by
 * the Python governor — node_runtime/supervisor/subscription_governor.py `status()` yields, per
 * registered subscription, `{provider, allowance, active:[…], in_use}`. This module is the PURE,
 * deterministic fold that turns that dict into the rows the status bar renders. It renders nothing
 * and performs no I/O; the drawn bar is an operator-run surface (like the window itself), exactly
 * the Phase-1 substitution pattern. apps/desktop/statusbar/source.js reads the governor status
 * over the D-IPC-01 channel and feeds it here.
 *
 * FAIL-CLOSED DISPLAY — the two bars this code must clear (directive §11 15A: "fail-closed display
 * (unknown/unreadable => not a fabricated count)"):
 *   - if the governor status is unreadable (null / not an object — a disconnected control plane or
 *     a surface that does not expose the op), the model is `readable:false` and every row is
 *     `state:"unknown"` with an em-dash count (`—/2`). It NEVER shows `0/2`, because 0 is a claim
 *     that the governor reported zero active terminals; when we could not read, we must not claim it.
 *   - a single subscription whose count is malformed (in_use / allowance not a non-negative int)
 *     is `state:"unknown"` on its own row rather than poisoning the whole bar.
 * `readable:true` with a provider that has NO registered subscription yet is shown as `0/<cap> idle`
 * (`0/2` for the OP-6 pair, `0/1` for the OP-12 pair): the governor was successfully read and holds
 * no subscription for that provider, so zero terminals are active — an honest zero, distinct from
 * the em-dash "we could not read". (This is a display default: with no subscription registered the
 * governor supplied no allowance, so the row shows the authorized per-provider ceiling; a registered
 * subscription always shows its OWN governed allowance. See `capForProvider` for the order of
 * authority — the FEED's number wins over the pinned map, and never exceeds it.)
 *
 * Every selectable live provider is surfaced with its allowance cap visible, even when idle or
 * unknown, so the bar reflects the authorized concurrency ceiling (I-X3), not just what happens to
 * be registered right now.
 */

// The frontier providers a pane can actually be spawned on, and therefore the ones with a
// subscription counter to render. This MIRRORS the authority
// control_plane/nodes/pane_picker.py `registered_frontier_providers()` — NOT the broader
// live_authorization scope. The two sets can differ, and the mirror must follow the NARROWER one:
// a counter for a subscription no pane can hold would advertise a terminal the product cannot take.
// Since 18B `.picker` the OP-12 pair IS selectable and dispatchable, so it belongs in this list;
// the comment that stood here until the 18B close still described the pre-`.picker` world ("not yet
// selectable") directly above the constant that already listed them (validator MAJOR-4 /
// spec-audit MEDIUM-3). (An older comment also called the authorized set "the frozen
// node.schema.json adapter enum". That was never true of THIS list — a live-subscription set and a
// node-record vocabulary are different things — and it is doubly wrong now: OP-12.1 put the OP-12
// pair and `ollama_local` into the successor `node@1.1`, so the enum it named has moved on and
// still would not be this list. See U227.) The mirror is pinned by a cross-language
// test (tests/unit/test_statusbar_constants_pinned.py) so this list cannot drift from what is
// selectable — in EITHER direction.
const LIVE_PROVIDERS = ["claude_code", "openai_codex_cli", "grok_build", "google_antigravity"];

// The DISPLAY ceiling per provider — U255, owed before the picker sub-step wired the OP-12 pair and
// closed with it. A single global number was correct only while every selectable provider shared the
// OP-6 allowance of 2; `grok_build` and `google_antigravity` are capped at 1 EACH by operator
// directive §12 and are never merged, so a global ceiling would have shown `0/2` for a subscription
// that can hold one terminal — overstating the operator's authorized concurrency in exactly the
// surface §14 governs. Mirrors control_plane/profiles/live_authorization `_PROVIDER_TERMINAL_CAP`
// and is pinned to it by tests/unit/test_statusbar_constants_pinned.py, so a future amendment that
// raises one provider's allowance cannot leave this bar understating (or overstating) it.
const PROVIDER_ALLOWANCE = {
  claude_code: 2,
  openai_codex_cli: 2,
  grok_build: 1,
  google_antigravity: 1,
};

/** The display ceiling for a row the governor gave no allowance for, in order of authority:
 *   1. `allowanceByProvider` — the FEED's own `allowance_by_provider`, i.e. what the emitter
 *      computed from the live authorization (`auth.terminals_for`), which is `min(config, cap)`.
 *      This is the only figure that follows the operator's config: an operator who narrows
 *      `terminals_per_subscription` to 1 was still shown `—/2` while this map was the only source
 *      (spec-audit Md-4 — U255 asked for a ceiling SOURCED FROM THE FEED, and the first cut shipped
 *      a second hand-maintained copy instead);
 *   2. `PROVIDER_ALLOWANCE` — the code-pinned per-provider cap, used on the FAULT path where there
 *      is no feed to read (it is pinned to the Python authority, so it cannot drift upward);
 *   3. the global governor maximum, for a provider neither source records.
 *
 * The feed wins, but it is CLAMPED to the pinned cap and never exceeds it (spec-audit MINOR-1): the
 * comment above claims the pinned map "cannot drift upward", and until the 18B close that claim was
 * true of the map and false of the function, which preferred a producer's number with no ceiling.
 * The emitter can only produce `min(config, cap)` today, so this is unreachable — which is exactly
 * why it is cheap to close, and the direction matters: an OVERSTATED ceiling on the one surface
 * U255 exists to protect advertises concurrency the governor will refuse (I-X3 / invariant 21).
 * Narrowing is honoured in full; widening is not. */
function capForProvider(provider, fallback, allowanceByProvider = null) {
  const recorded = PROVIDER_ALLOWANCE[provider];
  const fromFeed = isPlainObject(allowanceByProvider) ? allowanceByProvider[provider] : undefined;
  if (Number.isInteger(fromFeed) && fromFeed >= 0) {
    return Number.isInteger(recorded) ? Math.min(fromFeed, recorded) : fromFeed;
  }
  return Number.isInteger(recorded) ? recorded : fallback;
}

// The OP-6 governor cap, used ONLY as the DISPLAY ceiling for rows the governor gave no allowance
// for (a provider with no registered subscription, and unknown/unreadable rows); a registered
// subscription always shows its OWN governed allowance. This MIRRORS the authority
// node_runtime/supervisor/subscription_governor.py `MAX_ALLOWANCE`; if a future operator ruling
// raises that cap (a code change, per that module's docstring), this display default must move with
// it. The mirror is pinned by tests/unit/test_statusbar_constants_pinned.py so it cannot silently
// understate the real ceiling.
const SUBSCRIPTION_CAP = 2;

function isPlainObject(x) {
  return x !== null && typeof x === "object" && !Array.isArray(x);
}

function isNonNegInt(n) {
  return typeof n === "number" && Number.isInteger(n) && n >= 0;
}

/** Classify a readable, well-formed count into a display state. */
function countState(inUse, allowance) {
  if (inUse >= allowance) return "at-capacity"; // no more terminals may be spawned on this subscription
  if (inUse > 0) return "active";
  return "idle";
}

function unknownRow(provider, subscriptionRef, cap) {
  // Fail-closed: we could not read a trustworthy count. Never fabricate a number — the em-dash
  // makes "we don't know" visible instead of implying zero active terminals.
  return {
    subscriptionRef: subscriptionRef ?? null,
    provider,
    inUse: null,
    allowance: cap,
    label: `—/${cap}`,
    state: "unknown",
  };
}

/**
 * Fold a governor `status()` dict into status-bar rows.
 * @param {object} input
 * @param {object|null} input.status  the governor status dict, or null/undefined when unreadable
 * @param {string[]} input.providers  which providers to always surface (defaults to the OP-6 pair)
 * @param {number}   input.cap        the display ceiling for idle/unknown rows (OP-6 cap = 2)
 * @param {object|null} input.allowanceByProvider  the FEED's `allowance_by_provider` — the operator's
 *   own authorized concurrency per provider. Preferred over the code-pinned map for every ceiling
 *   this fold has to invent, so a config that NARROWS an allowance is not displayed at the code cap
 *   (spec-audit Md-4). Absent/unreadable ⇒ the pinned map, which is the fault-path fallback.
 * @returns {{readable:boolean, cap:number, providers:string[], rows:Array}}
 */
function buildStatusBarModel({ status = null, providers = LIVE_PROVIDERS, cap = SUBSCRIPTION_CAP,
  allowanceByProvider = null } = {}) {
  const provList = providers.slice();

  // Unreadable governor => the whole bar is unknown (fail-closed): one unknown row per provider,
  // no fabricated counts. This is the disconnected / unsupported-op / malformed-payload case.
  if (!isPlainObject(status)) {
    return {
      readable: false,
      cap,
      providers: provList,
      rows: provList.map((p) => unknownRow(p, null, capForProvider(p, cap, allowanceByProvider))),
    };
  }

  // Bucket the registered subscriptions by provider. A subscription whose entry is malformed, or
  // whose provider is not one we surface, is still captured (under its stated provider) so a real
  // registration is never silently hidden — observability over silent omission (invariant 27).
  const byProvider = new Map(provList.map((p) => [p, []]));
  const extraRows = []; // subscriptions on a provider outside the surfaced set — shown, not dropped

  for (const ref of Object.keys(status).sort()) {
    const s = status[ref];
    const rec = isPlainObject(s) ? s : {};
    const provider = typeof rec.provider === "string" ? rec.provider : "(unknown)";
    let row;
    if (isNonNegInt(rec.in_use) && isNonNegInt(rec.allowance)) {
      const inUse = rec.in_use;
      const allowance = rec.allowance;
      row = {
        subscriptionRef: ref,
        provider,
        inUse,
        allowance,
        label: `${inUse}/${allowance}`,
        state: countState(inUse, allowance),
      };
    } else {
      // A registered subscription whose count we cannot trust: unknown ON ITS OWN ROW, so one bad
      // record does not fabricate a count or poison the readable rows around it.
      row = unknownRow(provider, ref, capForProvider(provider, cap, allowanceByProvider));
    }
    if (byProvider.has(provider)) byProvider.get(provider).push(row);
    else extraRows.push(row);
  }

  const rows = [];
  for (const p of provList) {
    const found = byProvider.get(p);
    if (found.length) rows.push(...found);
    // No subscription registered for this provider: the governor WAS read and holds no subscription
    // for it, so zero terminals are active — an honest 0/cap idle row (distinct from the unreadable
    // em-dash above). `subscriptionRef:null` marks that this is a not-yet-registered provider rather
    // than a registered subscription that happens to be at zero (both read 0/cap in the bar; the
    // distinction is preserved in the row for any later consumer that needs it).
    else {
      // Per-provider ceiling (U255): an idle `grok_build` row reads 0/1, not 0/2.
      const pcap = capForProvider(p, cap, allowanceByProvider);
      rows.push({ subscriptionRef: null, provider: p, inUse: 0, allowance: pcap, label: `0/${pcap}`, state: "idle" });
    }
  }
  rows.push(...extraRows);

  return { readable: true, cap, providers: provList, rows };
}

/** Compact totals for a header badge (observability). Unknown rows do not contribute a count. */
function summarizeStatusBar(model) {
  const counted = model.rows.filter((r) => r.state !== "unknown");
  const inUse = counted.reduce((n, r) => n + r.inUse, 0);
  const atCapacity = model.rows.filter((r) => r.state === "at-capacity").length;
  const unknown = model.rows.filter((r) => r.state === "unknown").length;
  return {
    readable: model.readable,
    totalInUse: inUse,          // total live terminals across readable subscriptions
    subscriptionCount: counted.length,
    atCapacityCount: atCapacity,
    unknownCount: unknown,
  };
}

module.exports = {
  LIVE_PROVIDERS,
  SUBSCRIPTION_CAP,
  PROVIDER_ALLOWANCE,
  capForProvider,
  buildStatusBarModel,
  summarizeStatusBar,
};
