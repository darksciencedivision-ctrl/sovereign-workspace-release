"use strict";
/**
 * Picker + status-bar CHROME: the two pure string functions the renderer paints provider identity
 * and provider refusals with. Extracted at 18B `.picker` review round 1, because both reviewers
 * independently found the same defect and the same cause.
 *
 * THE DEFECT (gate-validator BLOCKING-1 / spec-audit M-3): `renderPicker` painted a provider group
 * as title + options and read `g.status` nowhere, so a provider that enumerated NOTHING rendered the
 * bare words "no options" — with the reason sitting unread in the model. That is the silent gap that
 * `pane_picker._group_status`, decision row D-P18-3 and the `.picker` checkpoint all say cannot
 * happen, on exactly the surface operator directive §14 governs (a signed-out `grok`, an `agy` that
 * is not installed). The receipted host had both CLIs enumerating, so the in-Electron receipt could
 * not see it either.
 *
 * THE CAUSE: these were template literals inside a 1000-line browser script with no module boundary,
 * so no test in the desktop suite could reach them — reverting the OP-12 entries from `PROV_LABEL`,
 * or pointing one provider's label at another's name, left all 640 tests green (validator mutation
 * E5). `pane-feed.js` already established the UMD idiom here: a pure helper the sandboxed renderer
 * loads as a `<script>` global and the Node suite `require`s. Chrome that carries an authority claim
 * belongs on that side of the boundary.
 *
 * Still true of this file: it decides nothing and authorizes nothing (invariant 1). It is a view over
 * a model the Python side already computed; it cannot make a provider available, and the only thing
 * it adds is that a refusal the model recorded is a refusal the operator can READ (invariant 27).
 */
(function () {
  // The chip label per provider — short command-style names, matching what the operator types. A
  // provider absent from this map falls back to its RAW ID, never to another provider's label:
  // operator directive §14 forbids showing one provider's text under another's name, and a silent
  // fallback to a neighbouring entry is exactly how that happens.
  const PROVIDER_LABEL = {
    claude_code: "claude",
    openai_codex_cli: "codex",
    grok_build: "grok",
    google_antigravity: "agy",
  };

  /** The status-bar chip name for a provider id. Unknown → the id itself (never another's name). */
  function providerLabel(provider) {
    const id = String(provider == null ? "" : provider);
    return Object.prototype.hasOwnProperty.call(PROVIDER_LABEL, id) ? PROVIDER_LABEL[id] : id;
  }

  /** Stable identity shared by the flat option list and the separately decoded provider groups. */
  function optionKey(option) {
    const o = option || {};
    return JSON.stringify([String(o.provider || ""), String(o.model_slug || ""), String(o.label || "")]);
  }

  /**
   * One picker provider GROUP as HTML: its §14 display title, the group's own availability reason
   * when it is not available, then the option rows the caller already rendered.
   *
   * The reason line is what BLOCKING-1 was about. It is emitted whenever the group is not available
   * and carries a reason — which covers both shapes the model produces:
   *   - zero options (CLI absent, signed out, enumeration empty) → the ONLY place a reason can live;
   *   - options present but all greyed (live switch DENIES the provider) → one line, rather than the
   *     same sentence repeated under twelve rows.
   * A group with no reason renders no line: an empty reason must never paint as an empty accusation.
   *
   * @param {object} group    a picker provider group: {provider, display, status:{available, reason}}
   * @param {string} optionsHtml  the already-rendered option rows ("" when there are none)
   * @param {function} esc    the caller's HTML escaper — the group's own text is untrusted (inv 29)
   */
  function providerGroupHtml(group, optionsHtml, esc) {
    const g = group || {};
    const status = g.status || null;
    const title = esc(g.display || g.provider);
    const unavailable = !!(status && status.available !== true);
    const reason = (status && status.reason) ? String(status.reason) : "";
    const reasonLine = (unavailable && reason)
      ? `<div class="pk-greason" title="${esc(reason)}">${esc(reason)}</div>` : "";
    // "no options" is the SHAPE, never the explanation: it appears only where a reason does not.
    const body = optionsHtml || (reasonLine ? "" : '<div class="dim">no options</div>');
    return `<div class="pk-group"><div class="pk-gtitle">${title}</div>${reasonLine}${body}</div>`;
  }

  const api = { PROVIDER_LABEL, providerLabel, optionKey, providerGroupHtml };
  // UMD: the Node test suite `require`s it; the sandboxed renderer takes it off `window` (it has no
  // Node integration — TB-2 / invariant 29).
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.PickerChrome = api;
})();
