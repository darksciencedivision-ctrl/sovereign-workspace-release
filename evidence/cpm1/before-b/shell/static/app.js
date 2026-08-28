/* ============================================================
   Sovereign Workspace Shell — app.js (SWS-UI-001 v1.2)

   Vanilla JS controller. Constraints honoured:
   - no framework, no build step, no CDN
   - no eval, no Function constructor, no dynamic HTML-string injection
   - DOM built with createElement + appendChild
   - all dynamic text set via textContent
   - every listener registered with addEventListener
   - every POST carries X-CSRF-Nonce from <meta name="csrf-nonce">
   ============================================================ */

"use strict";

(function () {
  /* ------------------------------------------------------------------ *
   * Configuration
   * ------------------------------------------------------------------ */

  const API_BASE =
    window.location.origin && window.location.origin !== "null"
      ? window.location.origin
      : "http://127.0.0.1:5180";

  const POLL_READY_MS = 5000; // any module READY (or STARTING) -> fast poll
  const POLL_SETTLED_MS = 30000; // STOPPED / other live states -> slow poll
  const PREFLIGHT_INTERVAL_MS = 30000;
  const LOG_REFRESH_MS = 2000;

  // Fixed card order, per spec.
  const MODULES = [
    {
      id: "sovereign",
      name: "SOVEREIGN",
      description:
        "Core control plane for the workspace: session supervision, state ledger, and module lifecycle.",
    },
    {
      id: "sow",
      name: "Multi-Model Terminal (SOW)",
      description:
        "Interactive terminal that routes statements of work across multiple local models.",
    },
    {
      id: "tokencenter",
      name: "Token Center",
      description:
        "Central usage telemetry. Resource accounting: VRAM, RAM, runtime, load state.",
    },
    {
      id: "debate",
      name: "Debate Table",
      description:
        "Structured multi-model debate surface with turns, rebuttals, and adjudication.",
    },
    {
      id: "distillery",
      name: "Sovereign Distillery",
      description:
        "Distillery runtime console: status, student model, pipeline, queue, logs. No compute on open.",
    },
  ];

  const DISTILLERY_NOTE =
    "Runtime Status idle. Student Model none. Pipeline State idle. Queue empty. Logs/Evidence local.";
  const DISTILLERY_TOOLTIP = "No runtime exists for Sovereign Distillery";

  const STATE_META = {
    NOT_STARTED: { cls: "badge-muted", label: "Not Started" },
    STOPPED: { cls: "badge-muted", label: "Stopped" },
    STARTING: { cls: "badge-warning", label: "Starting..." },
    READY: { cls: "badge-ok", label: "Ready" },
    DEGRADED: { cls: "badge-warning", label: "Degraded" },
    FAILED: { cls: "badge-danger", label: "Failed" },
    EXTERNAL: { cls: "badge-external", label: "External (not shell-owned)" },
    CONFIG_ERROR: { cls: "badge-danger", label: "Config Error" },
  };

  // States in which each action button is enabled.
  const ACTION_STATES = {
    start: ["NOT_STARTED", "STOPPED", "FAILED", "CONFIG_ERROR"],
    stop: ["READY", "STARTING", "DEGRADED"],
    restart: ["READY", "STARTING", "DEGRADED", "FAILED", "CONFIG_ERROR"],
    open: ["READY", "EXTERNAL"],
    test: ["NOT_STARTED", "STOPPED", "FAILED", "CONFIG_ERROR"],
  };

  const ACTION_LABELS = [
    ["start", "Start"],
    ["stop", "Stop"],
    ["restart", "Restart"],
    ["open", "Open"],
    ["test", "Run Startup Test"],
    ["logs", "Logs"],
  ];

  const PREFLIGHT_ITEMS = [
    { id: "ollama", label: "Ollama", keys: ["ollama"] },
    {
      id: "py312",
      label: "py -3.12",
      keys: ["py3.12", "py312", "python312", "python", "py"],
    },
    { id: "node", label: "node", keys: ["node", "nodejs"] },
    { id: "npm", label: "npm", keys: ["npm"] },
    { id: "port_5175", label: "port 5175", keys: ["port5175", "5175"] },
    { id: "port_8700", label: "port 8700", keys: ["port8700", "8700"] },
    { id: "port_5180", label: "port 5180", keys: ["port5180", "5180"] },
  ];

  /* ------------------------------------------------------------------ *
   * Shared state
   * ------------------------------------------------------------------ */

  const csrfMeta = document.querySelector('meta[name="csrf-nonce"]');
  const CSRF_NONCE = csrfMeta ? csrfMeta.getAttribute("content") || "" : "";

  const moduleState = new Map(); // id -> latest merged record (+ .state, ._url)
  const browserHandles = new Map(); // G18: id -> live Window handle from window.open
  const cards = new Map(); // id -> DOM refs for the module card
  const preflightRows = new Map(); // id -> { dot, detail }

  let statePollTimer = null;
  let logTimer = null;
  let logModuleId = null;

  const el = {
    version: document.getElementById("shell-version"),
    build: document.getElementById("shell-build"),
    host: document.getElementById("shell-host"),
    clock: document.getElementById("shell-clock"),
    linkDiscovery: document.getElementById("link-discovery"),
    linkTheme: document.getElementById("link-theme-baseline"),
    linkDirective: document.getElementById("link-directive"),
    preflightGrid: document.getElementById("preflight-grid"),
    preflightSummary: document.getElementById("preflight-summary"),
    moduleGrid: document.getElementById("module-grid"),
    logDetails: document.getElementById("log-details"),
    logModuleName: document.getElementById("log-module-name"),
    logStatus: document.getElementById("log-status"),
    logOutput: document.getElementById("log-output"),
    logClose: document.getElementById("log-close"),
    actionStatus: document.getElementById("action-status"),
  };

  /* ------------------------------------------------------------------ *
   * Small helpers
   * ------------------------------------------------------------------ */

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function firstString() {
    for (let i = 0; i < arguments.length; i++) {
      const v = arguments[i];
      if (typeof v === "string" && v.trim() !== "") return v;
      if (typeof v === "number" && isFinite(v)) return String(v);
    }
    return "";
  }

  function formatTime(value) {
    if (value === undefined || value === null || value === "") return "—";
    let date;
    if (typeof value === "number") {
      date = new Date(value < 1e12 ? value * 1000 : value); // sec vs ms epoch
    } else {
      date = new Date(value);
    }
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleTimeString([], { hour12: false });
  }

  function announce(message) {
    if (el.actionStatus) el.actionStatus.textContent = message;
  }

  function moduleById(id) {
    for (const mod of MODULES) {
      if (mod.id === id) return mod;
    }
    return null;
  }

  function urlForPort(port) {
    try {
      const u = new URL(API_BASE);
      u.port = String(port);
      return u.toString();
    } catch (err) {
      return "http://127.0.0.1:" + port;
    }
  }

  /* ------------------------------------------------------------------ *
   * API plumbing
   * ------------------------------------------------------------------ */

  async function apiGet(path) {
    const res = await fetch(API_BASE + path, {
      method: "GET",
      headers: { Accept: "application/json, text/plain" },
      cache: "no-store",
    });
    if (!res.ok) throw new Error("HTTP " + res.status + " for GET " + path);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (err) {
      return text;
    }
  }

  async function apiPost(path, body) {
    const res = await fetch(API_BASE + path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/plain",
        "X-CSRF-Nonce": CSRF_NONCE,
      },
      body: JSON.stringify(body == null ? {} : body),
    });
    if (!res.ok) throw new Error("HTTP " + res.status + " for POST " + path);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (err) {
      return text;
    }
  }

  /* ------------------------------------------------------------------ *
   * Pre-flight panel
   * ------------------------------------------------------------------ */

  function buildPreflight() {
    for (const item of PREFLIGHT_ITEMS) {
      const li = make("li", "preflight-item");
      const dot = make("span", "dot dot-unknown");
      dot.setAttribute("aria-hidden", "true");
      const label = make("span", "preflight-label", item.label);
      const detail = make("span", "preflight-detail", "");
      li.appendChild(dot);
      li.appendChild(label);
      li.appendChild(detail);
      el.preflightGrid.appendChild(li);
      preflightRows.set(item.id, { dot, detail });
    }
  }

  function interpretPreflight(value, isPort) {
    if (value === undefined || value === null) return { status: "unknown" };

    if (typeof value === "boolean") {
      return value ? { status: "ok" } : { status: "bad" };
    }

    if (typeof value === "string") {
      const lower = value.toLowerCase();
      const okWords = ["ok", "up", "ready", "available", "free", "running", "installed", "pass", "true", "yes", "listening"];
      const badWords = ["down", "missing", "unavailable", "busy", "error", "fail", "failed", "false", "no", "in use"];
      if (okWords.indexOf(lower) !== -1) return { status: "ok" };
      if (badWords.indexOf(lower) !== -1) return { status: "bad", detail: value };
      // Non-empty string (e.g. a version number) implies the tool is present.
      return { status: "ok", detail: value };
    }

    if (typeof value === "number") {
      return { status: value > 0 ? "ok" : "bad", detail: String(value) };
    }

    if (typeof value === "object") {
      const detail = firstString(value.detail, value.version, value.message, value.note);
      const flags = [value.ok, value.available, value.up, value.running, value.installed, value.pass];
      for (const flag of flags) {
        if (typeof flag === "boolean") {
          return flag ? { status: "ok", detail } : { status: "bad", detail };
        }
      }
      const status = String(value.status || value.state || "").toLowerCase();
      if (status) {
        const okStates = ["ok", "up", "ready", "available", "free", "running", "installed", "pass"];
        const badStates = ["bad", "down", "missing", "unavailable", "busy", "error", "fail", "failed", "in use"];
        if (okStates.indexOf(status) !== -1) return { status: "ok", detail };
        if (badStates.indexOf(status) !== -1) return { status: "bad", detail };
        return { status: "unknown", detail };
      }
      return { status: "unknown", detail };
    }

    return { status: "unknown" };
  }

  function normalizePreflight(payload) {
    const lookup = new Map(); // lowercased key -> raw value
    const put = function (k, v) {
      if (k !== undefined && k !== null) lookup.set(String(k).toLowerCase(), v);
    };

    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      if (Array.isArray(payload.checks)) {
        for (const c of payload.checks) {
          if (c && typeof c === "object") put(c.id || c.key || c.name || c.label, c);
        }
      }
      if (payload.ports && typeof payload.ports === "object") {
        for (const entry of Object.entries(payload.ports)) {
          put(entry[0], entry[1]);
          put("port_" + entry[0], entry[1]);
        }
      }
      for (const entry of Object.entries(payload)) {
        if (entry[0] === "checks" || entry[0] === "ports") continue;
        put(entry[0], entry[1]);
      }
    } else if (Array.isArray(payload)) {
      for (const c of payload) {
        if (c && typeof c === "object") put(c.id || c.key || c.name || c.label, c);
      }
    }

    const out = new Map();
    for (const item of PREFLIGHT_ITEMS) {
      let value;
      const candidates = [item.id].concat(item.keys);
      for (const key of candidates) {
        const v = lookup.get(String(key).toLowerCase());
        if (v !== undefined) {
          value = v;
          break;
        }
      }
      out.set(item.id, interpretPreflight(value, item.id.indexOf("port_") === 0));
    }
    return out;
  }

  async function loadPreflight() {
    let payload = null;
    try {
      payload = await apiGet("/api/preflight");
    } catch (err) {
      console.warn("SWS: pre-flight fetch failed:", err.message);
    }

    const results = normalizePreflight(payload);
    let okCount = 0;
    let badCount = 0;
    for (const item of PREFLIGHT_ITEMS) {
      const r = results.get(item.id) || { status: "unknown" };
      const row = preflightRows.get(item.id);
      if (!row) continue;
      row.dot.className = "dot dot-" + r.status;
      row.detail.textContent = r.detail || "";
      if (r.status === "ok") okCount++;
      else if (r.status === "bad") badCount++;
    }

    if (payload === null) {
      el.preflightSummary.textContent = "shell unreachable";
    } else {
      let summary = okCount + "/" + PREFLIGHT_ITEMS.length + " available";
      if (badCount > 0) summary += " · " + badCount + " unavailable";
      el.preflightSummary.textContent = summary;
    }
  }

  /* ------------------------------------------------------------------ *
   * Module cards
   * ------------------------------------------------------------------ */

  function metaRow(labelText) {
    const row = make("div", "meta-row");
    const dt = make("dt", "meta-label", labelText);
    const dd = make("dd", "meta-value", "—");
    row.appendChild(dt);
    row.appendChild(dd);
    return { row, value: dd };
  }

  function buildCards() {
    for (const mod of MODULES) {
      const card = make("article", "module-card");
      card.dataset.module = mod.id;

      const title = make("h2", "module-name", mod.name);
      const desc = make("p", "module-desc", mod.description);

      // State badge + reason
      const stateLine = make("div", "state-line");
      const badge = make("span", "badge badge-muted");
      const dot = make("span", "dot");
      dot.setAttribute("aria-hidden", "true");
      const stateText = make("span", "state-text", "Unknown");
      badge.appendChild(dot);
      badge.appendChild(stateText);
      const reason = make("span", "state-reason", "");
      stateLine.appendChild(badge);
      stateLine.appendChild(reason);

      // Meta rows
      const meta = make("dl", "module-meta");
      const lastCheckRow = metaRow("Last check");
      const endpointRow = metaRow("Endpoint");
      meta.appendChild(lastCheckRow.row);
      meta.appendChild(endpointRow.row);

      let extra = null;
      if (mod.id === "distillery") {
        const snapRow = metaRow("Snapshot");
        const qRow = metaRow("Open questions");
        meta.appendChild(snapRow.row);
        meta.appendChild(qRow.row);

        const linksRow = make("div", "distillery-links");
        linksRow.appendChild(make("span", "meta-label", "Handoff docs"));

        const note = make("p", "distillery-note", DISTILLERY_NOTE);

        extra = {
          snapshot: snapRow.value,
          questions: qRow.value,
          linksRow,
          note,
        };
      }

      // Action buttons
      const actions = make("div", "actions");
      const buttons = {};
      for (const pair of ACTION_LABELS) {
        const action = pair[0];
        const label = pair[1];
        const btn = make("button", "btn", label);
        btn.type = "button";
        btn.dataset.action = action;
        btn.setAttribute("aria-label", label + " — " + mod.name);
        btn.addEventListener("click", function () {
          onAction(mod.id, action);
        });
        actions.appendChild(btn);
        buttons[action] = btn;
      }

      card.appendChild(title);
      card.appendChild(desc);
      card.appendChild(stateLine);
      card.appendChild(meta);
      if (extra) {
        card.appendChild(extra.linksRow);
        card.appendChild(extra.note);
      }
      card.appendChild(actions);
      el.moduleGrid.appendChild(card);

      cards.set(mod.id, {
        badge,
        stateText,
        reason,
        lastCheck: lastCheckRow.value,
        endpoint: endpointRow.value,
        buttons,
        extra,
      });
    }
  }

  function applyModuleState(id, record) {
    const refs = cards.get(id);
    if (!refs) return;
    const mod = moduleById(id);
    record = record && typeof record === "object" ? record : {};

    let state = String(record.state || record.status || "").toUpperCase();
    if (!STATE_META[state] && !state) state = "";

    const meta = STATE_META[state] || { cls: "badge-muted", label: state || "Unknown" };
    refs.badge.className = "badge " + meta.cls;

    const reasonText = firstString(record.reason_code, record.reason, record.detail);
    if ((state === "FAILED" || state === "CONFIG_ERROR") && reasonText) {
      refs.stateText.textContent = meta.label + ": " + reasonText;
      refs.reason.textContent = "";
    } else {
      refs.stateText.textContent = meta.label;
      refs.reason.textContent = state === "READY" || state === "NOT_STARTED" ? "" : reasonText;
    }

    refs.lastCheck.textContent = formatTime(
      record.last_check !== undefined ? record.last_check : record.lastCheck
    );

    // Endpoint / URL
    const previous = moduleState.get(id) || {};
    const url = firstString(record.url, record.href);
    const port = record.port !== undefined && record.port !== null ? String(record.port) : "";
    const resolvedUrl = url || (port ? urlForPort(port) : previous._url || "");

    refs.endpoint.textContent = url || (port ? "port " + port : previous._endpointText || "—");

    // G18: leaving READY/EXTERNAL closes the shell-opened surface for this module.
    const prevState = previous.state;
    if ((prevState === "READY" || prevState === "EXTERNAL") &&
        (state !== "READY" && state !== "EXTERNAL")) {
      closeBrowserHandle(id);
    }
    moduleState.set(id, Object.assign({}, previous, record, {
      state: state || previous.state || "NOT_STARTED",
      _url: resolvedUrl,
      _endpointText: url || (port ? "port " + port : ""),
    }));

    refreshButtons(id);
  }

  /* G18: close only handles this shell opened; never touch any other browser. */
  function closeBrowserHandle(id) {
    const h = browserHandles.get(id);
    if (h && !h.closed) {
      try { h.close(); } catch (_e) { /* tab already gone */ }
    }
    browserHandles.delete(id);
  }

  function refreshButtons(id) {
    const refs = cards.get(id);
    if (!refs) return;
    const mod = moduleById(id);
    const st = (moduleState.get(id) || {}).state || "NOT_STARTED";

    for (const entry of Object.entries(refs.buttons)) {
      const action = entry[0];
      const btn = entry[1];
      let enabled;
      let tip = "";

      if (action === "logs") {
        enabled = true;
      } else if (mod && mod.noRuntime) {
        enabled = false;
        tip = DISTILLERY_TOOLTIP;
      } else if (st === "EXTERNAL" && action === "stop") {
        enabled = false;
        tip = "Process is not owned by this shell; stopping would only release the shell view of an external process.";
      } else {
        enabled = (ACTION_STATES[action] || []).indexOf(st) !== -1;
      }

      btn.disabled = !enabled;
      if (tip) btn.title = tip;
      else btn.removeAttribute("title");
    }
  }

  /* ------------------------------------------------------------------ *
   * State polling
   * ------------------------------------------------------------------ */

  function normalizeState(payload) {
    const out = new Map();
    if (!payload) return out;

    let list = null;
    if (Array.isArray(payload)) {
      list = payload;
    } else if (Array.isArray(payload.modules)) {
      list = payload.modules;
    } else if (payload.modules && typeof payload.modules === "object") {
      list = Object.entries(payload.modules).map(function (entry) {
        return Object.assign({ id: entry[0] }, entry[1]);
      });
    } else if (typeof payload === "object") {
      const entries = Object.entries(payload).filter(function (entry) {
        return entry[1] && typeof entry[1] === "object" && !Array.isArray(entry[1]);
      });
      if (entries.length) {
        list = entries.map(function (entry) {
          return Object.assign({ id: entry[0] }, entry[1]);
        });
      }
    }

    if (!list) return out;
    for (const rec of list) {
      if (rec && rec.id !== undefined && rec.id !== null) out.set(String(rec.id), rec);
    }
    return out;
  }

  function computePollInterval() {
    let fast = false;
    let slow = false;
    for (const mod of MODULES) {
      const st = (moduleState.get(mod.id) || {}).state;
      if (st === "READY" || st === "STARTING") fast = true;
      else if (st && st !== "NOT_STARTED") slow = true;
    }
    if (fast) return POLL_READY_MS;
    if (slow) return POLL_SETTLED_MS;
    return null; // everything NOT_STARTED -> never poll (spec 2)
  }

  function scheduleStatePoll(minNextMs) {
    if (statePollTimer !== null) {
      clearTimeout(statePollTimer);
      statePollTimer = null;
    }
    let interval = computePollInterval();
    if (interval === null && minNextMs) interval = minNextMs;
    if (interval === null) return;
    statePollTimer = setTimeout(function () {
      pollState();
    }, interval);
  }

  async function pollState(minNextMs) {
    try {
      const payload = await apiGet("/api/state");
      const states = normalizeState(payload);
      for (const mod of MODULES) {
        const record = states.get(mod.id);
        if (record) applyModuleState(mod.id, record);
        else applyModuleState(mod.id, moduleState.get(mod.id) || {});
      }
    } catch (err) {
      console.warn("SWS: /api/state poll failed:", err.message);
    }
    scheduleStatePoll(minNextMs);
  }

  /* ------------------------------------------------------------------ *
   * Actions
   * ------------------------------------------------------------------ */

  async function onAction(id, action) {
    const mod = moduleById(id);
    const name = mod ? mod.name : id;

    if (action === "logs") {
      openLogs(id);
      return;
    }

    if (action === "open") {
      const rec = moduleState.get(id) || {};
          if (rec._url) {
      // G18: retain and reuse the per-module handle; never spawn a second tab.
      let h = browserHandles.get(id);
      h = h && !h.closed ? h : window.open(rec._url, "_blank", "noopener");
      if (h) browserHandles.set(id, h);
    }
      else announce(name + ": no URL available");
      return;
    }

    const paths = {
      start: "/api/start",
      stop: "/api/stop",
      restart: "/api/restart",
    };

    try {
      if (action === "test") {
        await apiPost("/api/startup-test", { id: id, keep: false });
      } else {
        await apiPost(paths[action], { id: id });
      }
      announce(name + ": " + action + " requested");
    } catch (err) {
      announce(name + ": " + action + " failed — " + err.message);
      console.warn("SWS: action failed:", action, id, err.message);
    }

    // Re-sync immediately; guarantee a follow-up poll even if the state
    // has not transitioned yet.
    pollState(POLL_SETTLED_MS);
  }

  /* ------------------------------------------------------------------ *
   * Header: shell info + clock
   * ------------------------------------------------------------------ */

  async function loadShellInfo() {
    try {
      const info = await apiGet("/api/shell-info");
      if (!info || typeof info !== "object") return;

      const version = firstString(info.version, info.shell_version, info.sws_version);
      const build = firstString(info.build_id, info.build, info.commit);
      const host = firstString(info.host, info.hostname);

      if (version) el.version.textContent = "v " + version;
      if (build) el.build.textContent = "build " + build;
      if (host) el.host.textContent = host;

      setLink(el.linkDiscovery, firstString(info.discovery_url, info.discovery));
      setLink(el.linkTheme, firstString(info.theme_baseline_url, info.theme_baseline));
      setLink(el.linkDirective, firstString(info.directive_url, info.directive));
    } catch (err) {
      console.warn("SWS: /api/shell-info failed:", err.message);
    }
  }

  function setLink(anchor, href) {
    if (anchor && href) anchor.href = href;
  }

  function tickClock() {
    el.clock.textContent = new Date().toLocaleTimeString([], { hour12: false });
  }

  /* ------------------------------------------------------------------ *
   * Distillery card (no runtime)
   * ------------------------------------------------------------------ */

  async function loadDistillery() {
    const refs = cards.get("distillery");
    if (!refs || !refs.extra) return;

    let payload = null;
    try {
      payload = await apiGet("/api/distillery");
    } catch (err) {
      console.warn("SWS: /api/distillery failed:", err.message);
    }
    const data = payload && typeof payload === "object" ? payload : {};

    refs.extra.snapshot.textContent =
      (data.snapshot || {}).snapshot_id || "—";

    const q = data.questions || {};
    const openIds = Array.isArray(q.open_ids) ? q.open_ids : [];
    refs.extra.questions.textContent = openIds.length
      ? q.open_count + " (" + openIds.join(", ") + ")"
      : String(q.open_count);

    const linkMap = data.links || {};
    const links = Object.keys(linkMap).map(function (key) {
      return { name: key, path: linkMap[key] };
    });

    const row = refs.extra.linksRow;
    while (row.children.length > 1) row.removeChild(row.lastChild);

    if (!links.length) {
      row.appendChild(make("span", "distillery-nolinks", "none published"));
    }

    for (const link of links) {
      let anchor = null;
      if (typeof link === "string") {
        anchor = make("a", "distillery-link", link);
        anchor.href = link;
      } else if (link && typeof link === "object") {
        const href = firstString(link.url, link.href, link.path);
        if (!href) continue;
        anchor = make(
          "a",
          "distillery-link",
          firstString(link.title, link.name, link.label) || href
        );
        anchor.href = href;
      }
      if (!anchor) continue;
      anchor.target = "_blank";
      anchor.rel = "noopener";
      row.appendChild(anchor);
    }
  }

  /* ------------------------------------------------------------------ *
   * Log pane
   * ------------------------------------------------------------------ */

  function extractLogText(raw) {
    if (raw === undefined || raw === null) return "";
    const text = String(raw);
    const trimmed = text.trim();

    if (trimmed.charAt(0) === "{" || trimmed.charAt(0) === "[") {
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === "string") return parsed;
        if (Array.isArray(parsed)) {
          if (parsed.every(function (x) { return typeof x === "string"; })) {
            return parsed.join("\n");
          }
          return parsed
            .map(function (x) {
              if (x && typeof x === "object") {
                return firstString(x.line, x.message, x.text) || JSON.stringify(x);
              }
              return String(x);
            })
            .join("\n");
        }
        if (parsed && typeof parsed === "object") {
          const direct = firstString(
            parsed.log,
            parsed.content,
            parsed.text,
            parsed.output
          );
          if (direct) return direct;
          if (Array.isArray(parsed.lines)) {
            return parsed.lines
              .map(function (x) {
                return typeof x === "string" ? x : JSON.stringify(x);
              })
              .join("\n");
          }
        }
      } catch (err) {
        // Not JSON after all — fall through to raw text.
      }
    }
    return text;
  }

  async function refreshLogs() {
    if (!logModuleId) return;
    if (!el.logDetails.open) {
      stopLogTimer();
      return;
    }
    try {
      const res = await fetch(
        API_BASE + "/api/logs/" + encodeURIComponent(logModuleId),
        {
          method: "GET",
          headers: { Accept: "application/json, text/plain" },
          cache: "no-store",
        }
      );
      if (!res.ok) throw new Error("HTTP " + res.status);
      const raw = await res.text();

      const nearBottom =
        el.logOutput.scrollTop + el.logOutput.clientHeight >=
        el.logOutput.scrollHeight - 24;

      el.logOutput.textContent = extractLogText(raw);

      if (nearBottom) el.logOutput.scrollTop = el.logOutput.scrollHeight;
      el.logStatus.textContent =
        "updated " + new Date().toLocaleTimeString([], { hour12: false });
    } catch (err) {
      el.logStatus.textContent = "log fetch failed: " + err.message;
    }
  }

  function stopLogTimer() {
    if (logTimer !== null) {
      clearInterval(logTimer);
      logTimer = null;
    }
  }

  function restartLogTimer() {
    stopLogTimer();
    if (el.logDetails.open && logModuleId) {
      logTimer = setInterval(refreshLogs, LOG_REFRESH_MS);
    }
  }

  function openLogs(id) {
    logModuleId = id;
    const mod = moduleById(id);
    el.logModuleName.textContent = mod ? mod.name : id;
    el.logDetails.open = true;
    el.logStatus.textContent = "loading…";
    refreshLogs();
    restartLogTimer();
  }

  function closeLogs() {
    el.logDetails.open = false;
    stopLogTimer();
  }

  /* ------------------------------------------------------------------ *
   * Wiring & init
   * ------------------------------------------------------------------ */

  function wireEvents() {
    el.logDetails.addEventListener("toggle", function () {
      if (el.logDetails.open) restartLogTimer();
      else stopLogTimer();
    });

    el.logClose.addEventListener("click", closeLogs);

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && el.logDetails.open) closeLogs();
    });
  }

  function init() {
    buildPreflight();
    buildCards();

    // Default render before the first API response arrives.
    for (const mod of MODULES) applyModuleState(mod.id, {});

    wireEvents();
    tickClock();
    setInterval(tickClock, 1000);

    loadShellInfo();
    loadPreflight();
    setInterval(loadPreflight, PREFLIGHT_INTERVAL_MS);
    loadDistillery();
    pollState();
  }

  init();
})();
