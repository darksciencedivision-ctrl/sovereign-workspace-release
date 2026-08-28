"use strict";
/**
 * Phase 18B `.picker` in-Electron self-check (D-P16-0 binding, per-track) — the two OP-12
 * providers in the REAL packaged shell.
 *
 * The binding lesson this exists for: headless Node tests alone closed 14A while shipping a runtime
 * that failed at first launch. So every claim below is measured against the running renderer's own
 * picker model and the running status bar, not against a fixture.
 *
 * What it proves on THIS host, and what it deliberately does not:
 *   1. both provider groups RENDER — `Grok Build` and `Gemini · Antigravity`, the operator
 *      directive §14 labels, never "Gemini CLI";
 *   2. no OP-12 option was COMPOSED by this build: each one's id is its own label, carries no
 *      "CLI default" fallback shape, is flagged verified, and states in its note that it came from
 *      that provider's OWN `models` command — and a provider that enumerated nothing shows ZERO
 *      options with a reason rather than a fabricated default. (Leg 2 is a shape check, not a
 *      provenance measurement: the renderer receives only the picker dict, so there is no second
 *      enumeration here to compare against. The claim that these ids ARE the CLIs' listings is
 *      established outside this receipt, by running `grok models` / `agy models` on the host —
 *      review round 1 corrected this docstring, which used to assert a cross-check the code never
 *      performed while the receipt published its result: validator MAJOR-1 / spec-audit M-1.)
 *   3. the fail-closed grey is REAL: with the operator's live switch citing OP-6, both providers
 *      are DENIED, every option carries the live-authorization reason, and each reason names its
 *      OWN provider (§14 — never the other's text);
 *   3b. that reason is PAINTED, not merely modelled: the group's own refusal line is read back out
 *      of the DOM. Round 1 found the renderer dropping `group.status` entirely, so a provider that
 *      enumerated nothing rendered the bare words "no options" (validator BLOCKING-1 / M-3);
 *   4. selecting an OP-12 option through the SAME governed intent a click fires is REFUSED, with
 *      the recorded reason — the guard is load-bearing in the wired UI;
 *   5. the status bar shows a per-provider ceiling: the OP-12 pair at n/1, the OP-6 pair at n/2
 *      (U255 — a global 2 would advertise a terminal the governor refuses), and the CHIP TEXT the
 *      bar painted is captured, so §14's "never one provider's name under another's" is checked
 *      where the operator actually reads it.
 *
 * It does NOT prove a live Grok/Antigravity session: no live call is made, nothing is spawned for
 * either provider, and no terminal is leased. That is 18C's, behind the operator's own switch.
 * If the operator's config were to authorize these providers, legs 3–4 would find them AVAILABLE;
 * the receipt records which of the two worlds it observed rather than assuming one.
 */
const fs = require("fs");
const path = require("path");
const { receiptPath } = require("./receipt-path");
// The commit + tracked-product-tree stamp every receipt since 17C carries, from the module that owns
// it (a third copy is how two truths start). Without it a receipt cannot be tied to a tree at all —
// this one shipped with no `schema`, no `source` and no tree-clean fact (MEDIUM-1).
const { sourceIdentity } = require("./voice-conductor-selfcheck");
// The per-provider display ceiling, from the model the shell actually ships (never re-typed here).
const { PROVIDER_ALLOWANCE } = require("../../../terminal/statusbar/statusbar-model");

const RECEIPT_SCHEMA = "phase18b_picker_selfcheck@1.0";
const RECEIPT_PATH = receiptPath("PHASE18B_PICKER_SELFCHECK.json");

const GROK = "grok_build";
const ANTIGRAVITY = "google_antigravity";
const OP12 = [GROK, ANTIGRAVITY];
const DISPLAY = { [GROK]: "Grok Build", [ANTIGRAVITY]: "Gemini · Antigravity" };
// The other provider's identifying words, so "this reason names its own provider" is checked in
// both directions instead of merely finding the right word somewhere.
const FOREIGN_WORDS = { [GROK]: ["agy", "antigravity"], [ANTIGRAVITY]: ["grok", "xai"] };

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

async function evalR(win, expr) {
  try { return await win.webContents.executeJavaScript(expr); } catch { return null; }
}

async function run(ctx) {
  const { win, createPaneWithSession, isSupervised, log } = ctx;
  const receipt = {
    schema: RECEIPT_SCHEMA,
    check: "phase-18b.picker",
    authorization: "OP-12 (operator, 2026-07-31)",
    source: sourceIdentity(),   // commit + tracked-product-tree state this run observed
    started: new Date().toISOString(),
    ok: false,
    supervision_ready: false,
    target_pane_id: null,
    picker_opened: false,
    groups_rendered: {},        // provider → the display title the renderer actually painted
    options: {},                // provider → {count, slugs, available, reason}
    // provider → the option SHAPE verdict: no composed label, no CLI-default fallback, verified,
    // and a note naming that provider's own `models` command. NOT a provenance measurement — see
    // the header (this field used to be called `enumeration_matched`, which claimed more than the
    // code did: validator MAJOR-1 / spec-audit M-1).
    options_are_uncomposed: {},
    reasons_name_own_provider: {},
    group_reason_painted: {},   // provider → the refusal line READ BACK OUT OF THE DOM (BLOCKING-1)
    selection_refused: {},      // provider → {attempted, refused, reason}
    statusbar_rows: {},         // provider → [the label(s) the bar painted, e.g. "0/1"]
    statusbar_chip_text: null,  // the bar's own rendered text, so §14 is checked where it is read
    statusbar_readable: null,
    live_switch_authorized_globally: null,  // the GLOBAL switch; per-provider verdicts are above
    error: null,
  };
  try {
    receipt.supervision_ready = await waitFor(isSupervised, 25000, 250);
    if (!receipt.supervision_ready) {
      throw new Error("supervision never became READY within 25s");
    }

    const paneId = createPaneWithSession({
      file: "powershell.exe", args: ["-NoLogo", "-NoProfile", "-NoExit"], title: "op12-target",
    });
    receipt.target_pane_id = paneId;
    await waitFor(async () =>
      evalR(win, `window.__sovereignSelfCheck.hasTerm(${JSON.stringify(paneId)})`), 15000, 200);

    // The picker's enumeration runs the real host probes (`grok models` / `agy models`), so give it
    // the whole source-side budget before calling it unrendered.
    await evalR(win, `window.__sovereignSelfCheck.openPicker(${JSON.stringify(paneId)})`);
    receipt.picker_opened = await waitFor(async () => {
      const s = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()");
      return !!(s && s.ok);
    }, 45000, 300);
    if (!receipt.picker_opened) throw new Error("picker never rendered a live enumeration");

    const summary = await evalR(win, "window.__sovereignSelfCheck.pickerSummary()") || {};
    receipt.live_switch_authorized_globally = summary.authAuthorized;

    // ---- leg 1: both groups render, under the §14 labels ------------------------------------
    const groupTitles = await evalR(win, `(function(){
      return Array.from(document.querySelectorAll("#picker-body .pk-gtitle")).map(e => e.textContent);
    })()`) || [];
    for (const provider of OP12) {
      const wanted = DISPLAY[provider];
      receipt.groups_rendered[provider] = groupTitles.find((t) => t === wanted) || null;
      if (!receipt.groups_rendered[provider]) {
        throw new Error(`provider group ${wanted} did not render (titles: ${groupTitles.join(" | ")})`);
      }
    }
    if (groupTitles.some((t) => /gemini cli/i.test(t))) {
      throw new Error("the retired 'Gemini CLI' label rendered — operator directive §14 forbids it");
    }

    // ---- leg 2 + 3: options come from the CLI's own listing; grey is honest and provider-correct
    const model = await evalR(win, `(function(){
      const m = window.__sovereignSelfCheck.pickerModel() || {};
      const p = m.picker || {};
      const out = { groups: {}, options: {} };
      for (const g of (p.providers || [])) {
        out.groups[g.provider] = g.status || null;
        out.options[g.provider] = (g.options || []).map(o => ({
          slug: o.model_slug, label: o.label, available: o.available,
          reason: o.unavailable_reason, verified: o.verified, is_fallback: o.is_fallback,
          roles: o.roles, note: o.note,
        }));
      }
      return out;
    })()`) || { groups: {}, options: {} };

    for (const provider of OP12) {
      const options = model.options[provider] || [];
      const status = model.groups[provider] || {};
      receipt.options[provider] = {
        count: options.length,
        slugs: options.map((o) => o.slug),
        available: options.filter((o) => o.available).length,
        group_available: status.available === true,
        group_reason: status.reason || null,
      };
      // Zero options is legitimate ONLY with a reason on the group (never a fabricated default).
      if (options.length === 0) {
        if (!status.reason) {
          throw new Error(`${provider} rendered zero options with no recorded reason`);
        }
        receipt.options_are_uncomposed[provider] = "no options — reason recorded";
      } else {
        // No option was COMPOSED here: its slug is its own label (never "label (slug)"), it is not
        // the CLI-default fallback shape (these CLIs publish their ids, so no fallback exists to
        // invent), it is flagged verified, and its note names THIS provider's own `models` command
        // — the last one is the only part that speaks to where the id came from, and it is the
        // builder's own statement, not an independent measurement.
        const cmd = provider === GROK ? "grok models" : "agy models";
        const bad = options.filter((o) => !o.slug || o.slug !== o.label || o.is_fallback
                                          || o.verified !== true
                                          || !String(o.note || "").includes(cmd));
        if (bad.length) {
          throw new Error(`${provider} rendered a composed/fallback option: ${JSON.stringify(bad[0])}`);
        }
        receipt.options_are_uncomposed[provider] = true;
      }
      // Reason honesty, in both directions: an unavailable option carries a reason, and that reason
      // does not carry the OTHER provider's identifying words (§14).
      const greyed = options.filter((o) => !o.available);
      if (greyed.some((o) => !o.reason)) {
        throw new Error(`${provider} greyed an option with no reason (dishonest grey)`);
      }
      const texts = [status.reason || "", ...greyed.map((o) => o.reason || "")].join(" ").toLowerCase();
      const foreign = FOREIGN_WORDS[provider].filter((w) => texts.includes(w));
      receipt.reasons_name_own_provider[provider] = foreign.length === 0;
      if (foreign.length) {
        throw new Error(`${provider}'s refusal text names the other provider (${foreign.join(",")})`);
      }
    }

    // ---- leg 3b: the group's refusal reason is PAINTED, not merely modelled --------------------
    // Round 1's BLOCKING-1: `renderPicker` read `g.display` and `g.options` and nothing else, so the
    // reason existed in the model (this receipt's `group_reason` proved that) and reached no pixel.
    // Read it back out of the DOM, beside its own group title, and require it to be the model's.
    const painted = await evalR(win, `(function(){
      const out = {};
      for (const el of document.querySelectorAll("#picker-body .pk-group")) {
        const title = el.querySelector(".pk-gtitle");
        const reason = el.querySelector(".pk-greason");
        out[title ? title.textContent : "(untitled)"] = {
          reason: reason ? reason.textContent : null,
          says_no_options: /no options/.test(el.textContent || ""),
        };
      }
      return out;
    })()`) || {};
    for (const provider of OP12) {
      const group = painted[DISPLAY[provider]] || {};
      const modelled = receipt.options[provider].group_reason;
      receipt.group_reason_painted[provider] = group.reason || null;
      if (receipt.options[provider].group_available) continue;   // an available group is not accused
      if (!group.reason) {
        throw new Error(`${DISPLAY[provider]} rendered no refusal line — the reason the model `
                        + `records (${modelled}) never reached the DOM (BLOCKING-1)`);
      }
      if (modelled && group.reason !== modelled) {
        throw new Error(`${provider}: the painted reason is not the recorded one — painted `
                        + `${JSON.stringify(group.reason)}, recorded ${JSON.stringify(modelled)}`);
      }
      if (group.says_no_options && receipt.options[provider].count === 0) {
        throw new Error(`${provider} still paints the words "no options" where its reason belongs`);
      }
    }

    // ---- leg 4: selecting an OP-12 option goes through the governed intent ---------------------
    for (const provider of OP12) {
      const idx = await evalR(win, `(function(){
        const o = (window.__sovereignSelfCheck.pickerModel().picker.options || []);
        return o.findIndex(x => x.provider === ${JSON.stringify(provider)});
      })()`);
      if (typeof idx !== "number" || idx < 0) {
        receipt.selection_refused[provider] = {
          attempted: false, refused: null,
          reason: "no option enumerated for this provider on this host",
        };
        continue;
      }
      const res = await evalR(win,
        `window.__sovereignSelfCheck.selectOption(${idx}, "reasoning")`);
      const refused = !!(res && res.recorded === false && res.error);
      receipt.selection_refused[provider] = {
        attempted: true, refused,
        recorded: !!(res && res.recorded),
        reason: (res && (res.error || res.reason)) || null,
      };
      // With the live switch citing OP-6 (the state this host is in), the selection MUST be refused.
      // If the operator has since authorized these providers, a recorded governed selection is the
      // correct outcome instead — the receipt says which, and only "neither" is a failure.
      if (!refused && !(res && res.recorded)) {
        throw new Error(`${provider} selection neither refused nor recorded: ${JSON.stringify(res)}`);
      }
    }

    // ---- leg 5: per-provider display ceiling in the running status bar (U255) ------------------
    const bar = await evalR(win, "window.sovereign.statusBar()");
    receipt.statusbar_readable = !!(bar && typeof bar.readable === "boolean") ? bar.readable : null;
    const rows = (bar && Array.isArray(bar.rows)) ? bar.rows : [];
    // Collected as a LIST per provider: allowance 2 permits two rows for the OP-6 pair, and
    // last-write-wins would silently drop one of them (spec-audit N-1).
    for (const r of rows) {
      (receipt.statusbar_rows[r.provider] = receipt.statusbar_rows[r.provider] || []).push(r.label);
    }
    // Read from the SHIPPED model's own pinned map rather than hand-copied here (spec-audit
    // MINOR-3): a hard-coded third copy turns this receipt leg red for the WRONG reason after a
    // future operator amendment, and the receipt is the D-P16-0 evidence. That map is pinned to
    // the Python authority by tests/unit/test_statusbar_constants_pinned.py, so this reads through
    // to `live_authorization._PROVIDER_TERMINAL_CAP` with no second maintenance site.
    const expectedCeiling = PROVIDER_ALLOWANCE;
    receipt.expected_ceiling_source = "terminal/statusbar/statusbar-model.js PROVIDER_ALLOWANCE";
    for (const [provider, ceiling] of Object.entries(expectedCeiling)) {
      const row = rows.find((x) => x.provider === provider);
      if (!row) throw new Error(`status bar rendered no row for ${provider}`);
      if (row.allowance !== ceiling) {
        throw new Error(`status bar shows ${provider} at allowance ${row.allowance}, expected `
                        + `${ceiling} (U255: the ceiling is per provider)`);
      }
    }
    // …and what the bar actually PAINTED, since the rows above are the model. §14 is about the
    // surface: every provider's chip must carry its own name (spec-audit MINOR-4).
    receipt.statusbar_chip_text = await evalR(win, `(function(){
      const el = document.getElementById("statusbar");
      return el ? el.textContent.replace(/\\s+/g, " ").trim() : null;
    })()`);
    for (const [provider, chip] of Object.entries(
      { claude_code: "claude", openai_codex_cli: "codex", grok_build: "grok",
        google_antigravity: "agy" })) {
      if (!String(receipt.statusbar_chip_text || "").includes(chip)) {
        throw new Error(`the status bar painted no chip named ${chip} for ${provider} `
                        + `(painted: ${receipt.statusbar_chip_text})`);
      }
    }

    // Every leg the header claims, folded — the two vacuous conjuncts this used to carry
    // (`selection_refused[p] !== undefined`, which both branches satisfy, and a non-empty row map)
    // made `ok` read as a summary while contributing nothing (spec-audit Mn-5 / MINOR-2).
    const refusedOrRecorded = (p) => {
      const s = receipt.selection_refused[p] || {};
      // Not attempted is acceptable ONLY as the honest degrade it is: this provider enumerated
      // nothing on this host, and the receipt says so with the reason.
      if (s.attempted === false) return receipt.options[p].count === 0 && !!s.reason;
      return s.attempted === true && (s.refused === true || s.recorded === true);
    };
    const groupReasonHonest = (p) => receipt.options[p].group_available === true
      || !!receipt.group_reason_painted[p];
    receipt.ok = receipt.picker_opened
      && OP12.every((p) => !!receipt.groups_rendered[p])
      // `options_are_uncomposed[p] !== undefined` used to sit here and was satisfied by BOTH
      // branches of leg 2 — the third vacuous conjunct of the same class (spec-audit MINOR-2).
      // Folded as the disjunction it actually is: either the options are uncomposed, or the
      // provider offered none AND said why. `statusbar_readable` is folded for the same reason —
      // it was measured, recorded, and then contributed nothing to the verdict.
      && OP12.every((p) => receipt.options_are_uncomposed[p] === true
        || (receipt.options[p].count === 0 && !!receipt.options[p].group_reason))
      && receipt.statusbar_readable === true
      && OP12.every((p) => receipt.reasons_name_own_provider[p] === true)
      && OP12.every(groupReasonHonest)
      && OP12.every(refusedOrRecorded)
      && ["claude_code", "openai_codex_cli", ...OP12].every(
        (p) => Array.isArray(receipt.statusbar_rows[p]) && receipt.statusbar_rows[p].length > 0)
      && !!receipt.statusbar_chip_text
      && !!(receipt.source && receipt.source.commit);
  } catch (e) {
    receipt.error = String((e && e.message) || e);
  }
  receipt.finished = new Date().toISOString();
  receipt.env = {
    electron: process.versions.electron, node: process.versions.node,
    chrome: process.versions.chrome, platform: process.platform, arch: process.arch,
  };
  try {
    fs.mkdirSync(path.dirname(RECEIPT_PATH), { recursive: true });
    fs.writeFileSync(RECEIPT_PATH, JSON.stringify(receipt, null, 2) + "\n");
  } catch (e) {
    log(`[selfcheck] could not write receipt: ${e.message}`);
  }
  log(`[selfcheck] op12-picker ${receipt.ok ? "PASS" : "FAIL"} → ${RECEIPT_PATH}`);
  return receipt;
}

module.exports = { runOp12PickerSelfCheck: run, RECEIPT_PATH };
