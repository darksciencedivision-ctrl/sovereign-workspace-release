"use strict";
/** SW-JOURNAL-001 F-27. Store-first observations; markdown is never read as authority. */
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { observePanes } = require("./pane-observation");
const { redactPaneText } = require("../../../terminal/observe/pane-redaction");
const { isCredentialEnvName } = require("../conductor/launch-source");
const SCHEMA = "workspace_journal@1.0";
const SOURCE = "observed_pane_output";
const MAX_ENTRY_CHARS = 24000;
const MAX_SESSION_ENTRIES = 256;
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_RECENT_ENTRIES = 128;
const safeId = (s) => typeof s === "string" && /^[a-zA-Z0-9-]{1,100}$/.test(s);
function inside(root, target) {
  const rel = path.relative(root, target);
  return rel === "" || (!path.isAbsolute(rel) && rel !== ".." && !rel.startsWith(".." + path.sep));
}
function cleanText(value) {
  const r = redactPaneText(typeof value === "string" ? value : "");
  let extra = 0;
  // A durable journal must also remove credential-classified NAMES, which the pane redactor
  // intentionally preserves. Reuse its classifier rather than maintain another list.
  let text = r.text.replace(/\b[A-Za-z_][A-Za-z0-9_]*\b/g, (name) => {
    if (!isCredentialEnvName(name)) return name;
    extra++; return "[REDACTED:name]";
  });
  // Withhold absolute host paths, including the workspace root itself: no path is needed to
  // attribute a pane. This is stricter than the permitted workspace-root exception.
  text = text.replace(/(?:[A-Za-z]:[\\/]|\\\\)[^\r\n"'<>|]*/g, () => {
    extra++; return "[REDACTED:path]";
  }).replace(/(^|[\s("'])\/(?!\/)[^\s"'<>]*/g, (_m, prefix) => {
    extra++; return prefix + "[REDACTED:path]";
  });
  return { text, redactions: r.redactions + extra,
    kinds: [...new Set([...r.kinds, ...(extra ? ["journal_privacy"] : [])])], failed: r.failed };
}
function validEntry(e) {
  return !!(e && e.schema === SCHEMA && e.self_published === false && e.source === SOURCE
    && safeId(e.session_id) && safeId(e.event_id) && typeof e.pane_id === "string"
    && typeof e.node_id === "string" && typeof e.model === "string"
    && typeof e.utc === "string" && !Number.isNaN(Date.parse(e.utc))
    && typeof e.status === "string" && typeof e.prompt === "string"
    && typeof e.answer === "string" && typeof e.reason === "string"
    && typeof e.objective === "string" && typeof e.task_id === "string"
    && Number.isSafeInteger(e.redactions) && e.redactions >= 0
    && Array.isArray(e.redaction_kinds) && typeof e.truncated === "boolean");
}
function prepareEntry(raw, sessionId, now) {
  if (!raw || raw.self_published !== false || raw.source !== SOURCE)
    throw new Error("journal provenance missing: observed_pane_output / self_published:false required");
  const e = { schema: SCHEMA, session_id: sessionId, event_id: raw.event_id || randomUUID(),
    utc: raw.utc || now(), self_published: false, source: SOURCE,
    redactions: Number.isSafeInteger(raw.redactions) && raw.redactions >= 0 ? raw.redactions : 0,
    redaction_kinds: Array.isArray(raw.redaction_kinds) ? [...raw.redaction_kinds] : [],
    truncated: raw.truncated === true };
  let left = MAX_ENTRY_CHARS;
  for (const key of ["node_id", "pane_id", "model", "status", "task_id", "objective", "prompt",
    "answer", "reason"]) {
    const cleaned = cleanText(raw[key] || (["node_id", "pane_id", "model"].includes(key)
      ? "(not reported)" : ""));
    e[key] = cleaned.text.slice(0, left);
    left -= e[key].length;
    e.truncated ||= e[key].length < cleaned.text.length;
    e.redactions += cleaned.redactions;
    e.redaction_kinds.push(...cleaned.kinds);
    if (cleaned.failed) throw new Error("journal redaction failed; content withheld");
  }
  e.redaction_kinds = [...new Set(e.redaction_kinds)].sort();
  if (!validEntry(e)) throw new Error("journal entry unreadable");
  return e;
}
function entryMarkdown(e) {
  // JSON string literals keep untrusted text from making markdown headings or forged metadata.
  return "\n## " + e.event_id + "\n" + Object.entries(e)
    .map(([k, v]) => k + ": " + JSON.stringify(v)).join("\n") + "\n";
}
function paneNumber(id) {
  const m = String(id || "").match(/(\d+)$/);
  return m ? m[1] : "";
}
function composeOwnDigest(entries, { budgetChars, nodeId, absence = "" } = {}) {
  const marker = "\nTRUNCATED: prior work omitted to fit the computed worker budget.";
  if (absence) {
    return { text: "YOUR PRIOR WORK could not be retrieved: " + absence
      + " Continuing without it.\n", attached: false, truncated: false, entry_ids: [] };
  }
  if (!Number.isFinite(budgetChars) || budgetChars < 0) {
    return { text: "YOUR PRIOR WORK could not be retrieved: budget_unmeasurable. Continuing without it.\n",
      attached: false, truncated: false, entry_ids: [] };
  }
  const header = "YOUR PRIOR WORK — observed_pane_output; self_published: false.\n"
    + "Screen-read history of YOUR earlier turns in this session, not a published result.\n";
  if (budgetChars < header.length + marker.length) {
    return { text: "YOUR PRIOR WORK TRUNCATED: no room in the worker budget; prior work withheld.\n",
      attached: false, truncated: true, entry_ids: [] };
  }
  const own = [];
  for (const e of Array.isArray(entries) ? entries : []) {
    if (!e || e.node_id !== nodeId) continue;
    own.push(e);
  }
  if (!own.length) {
    return { text: header + "No prior work of yours is recorded in this session.\n",
      attached: true, truncated: false, entry_ids: [] };
  }
  let view = header, truncated = false;
  const ids = [];
  let left = budgetChars - view.length - marker.length;
  for (const e of own) {
    const line = cleanText("time=" + (e.utc || "") + " pane=" + (e.pane_id || "")
      + " terminal=#" + paneNumber(e.pane_id) + " status=" + (e.status || "")
      + " source=" + SOURCE + " self_published=false"
      + "\nprompt: " + (e.prompt || "") + "\nanswer: " + (e.answer || "") + "\n").text;
    if (line.length > left) { view += line.slice(0, Math.max(0, left)); truncated = true; break; }
    view += line; left -= line.length;
    if (e.event_id) ids.push(e.event_id);
  }
  if (truncated) view += marker;
  if (view.length > budgetChars) {
    view = view.slice(0, Math.max(0, budgetChars - marker.length)) + marker; truncated = true;
  }
  return { text: view, attached: true, truncated, entry_ids: ids };
}
function renderNodeMemory(entries, nodeId) {
  let out = "# Worker memory — " + nodeId + "\n"
    + "Projection of private_node tier. Never an authority or a worker publication.\n"
    + "source: observed_pane_output; self_published: false; U58 OWED.\n"
    + "Cap: " + MAX_SESSION_ENTRIES + " entries / " + MAX_FILE_BYTES
    + " UTF-8 bytes. Additional entries remain in the store.\n";
  let count = 0;
  for (const e of entries) {
    if (!validEntry(e) || e.node_id !== nodeId)
      throw new Error("unreadable private journal entry for node " + String(nodeId));
    const block = entryMarkdown(prepareEntry(e, e.session_id, () => e.utc));
    if (count >= MAX_SESSION_ENTRIES || Buffer.byteLength(out + block) > MAX_FILE_BYTES - 100)
      return out + "\nTRUNCATED: node projection cap reached; later entries remain in the store.\n";
    out += block; count++;
  }
  return out;
}
function renderSession(entries, sessionId) {
  if (!safeId(sessionId)) throw new Error("invalid journal session");
  let out = "# Workspace journal — " + sessionId + "\n"
    + "Projection of the project MCP store. Never an authority or a worker publication.\n"
    + "source: observed_pane_output; self_published: false; U58 OWED.\n"
    + "Cap: " + MAX_SESSION_ENTRIES + " entries / " + MAX_FILE_BYTES
    + " UTF-8 bytes per session. Additional entries remain in the store.\n";
  let count = 0;
  for (const e of entries) {
    if (!validEntry(e) || e.session_id !== sessionId)
      throw new Error("unreadable journal entry for pane " + String(e && e.pane_id || "(unknown)"));
    const block = entryMarkdown(prepareEntry(e, sessionId, () => e.utc));
    if (count >= MAX_SESSION_ENTRIES || Buffer.byteLength(out + block) > MAX_FILE_BYTES - 100)
      return out + "\nTRUNCATED: session projection cap reached; later entries remain in the store.\n";
    out += block; count++;
  }
  return out;
}
function createWorkspaceJournal({ store, stateRoot, installRoot, sessionId = randomUUID(),
  now = () => new Date().toISOString() }) {
  let session = sessionId;
  if (!safeId(session)) throw new Error("invalid journal session");
  // Resolve existing parents as well: a state directory symlink must not write into the install.
  function canonical(p) {
    p = path.resolve(p);
    return fs.existsSync(p) ? fs.realpathSync(p)
      : path.join(canonical(path.dirname(p)), path.basename(p));
  }
  function destination() {
    const state = canonical(stateRoot), install = canonical(installRoot);
    if (inside(install, state)) throw new Error("journal state root is inside install root");
    const dir = canonical(path.join(state, "journal"));
    if (!inside(state, dir) || inside(install, dir)) throw new Error("journal path escapes state root");
    const file = path.join(dir, session + ".md");
    if (fs.existsSync(file) && fs.lstatSync(file).isSymbolicLink())
      throw new Error("journal file is a symbolic link");
    return file;
  }
  function nodeDestination(nodeId) {
    if (!safeId(nodeId)) throw new Error("invalid journal node");
    const state = canonical(stateRoot), install = canonical(installRoot);
    if (inside(install, state)) throw new Error("journal state root is inside install root");
    const dir = canonical(path.join(state, "journal", "nodes"));
    if (!inside(state, dir) || inside(install, dir)) throw new Error("journal path escapes state root");
    const file = path.join(dir, nodeId + ".md");
    if (fs.existsSync(file) && fs.lstatSync(file).isSymbolicLink())
      throw new Error("journal file is a symbolic link");
    return file;
  }
  let queue = Promise.resolve();
  function serial(fn) {
    const work = queue.then(fn);
    queue = work.catch(() => {});
    return work;
  }
  async function projectNow() {
    const entries = await store.entries({ sessionId: session, limit: MAX_SESSION_ENTRIES + 1 });
    if (!Array.isArray(entries)) throw new Error("journal store unavailable");
    const bytes = Buffer.from(renderSession(entries, session));
    const file = destination();
    fs.mkdirSync(path.dirname(file), { recursive: true });
    // Existing bytes are checked only for rendering consistency, never used for retrieval.
    const previous = fs.existsSync(file) ? fs.readFileSync(file) : Buffer.alloc(0);
    if (!bytes.subarray(0, previous.length).equals(previous) || previous.length > bytes.length)
      throw new Error("journal projection mismatch; delete the rendering to rebuild from the store");
    if (previous.length < bytes.length) fs.appendFileSync(file, bytes.subarray(previous.length));
    return { file, entries: entries.length, bytes: bytes.length };
  }
  async function projectNodeNow(nodeId) {
    if (!store.privateEntries) throw new Error("journal store unavailable");
    const entries = await store.privateEntries({ nodeId, limit: MAX_SESSION_ENTRIES + 1 });
    if (!Array.isArray(entries)) throw new Error("journal store unavailable");
    const own = entries.filter(e => e && e.node_id === nodeId);
    const bytes = Buffer.from(renderNodeMemory(own, nodeId));
    const file = nodeDestination(nodeId);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const previous = fs.existsSync(file) ? fs.readFileSync(file) : Buffer.alloc(0);
    if (!bytes.subarray(0, previous.length).equals(previous) || previous.length > bytes.length)
      throw new Error("journal projection mismatch; delete the rendering to rebuild from the store");
    if (previous.length < bytes.length) fs.appendFileSync(file, bytes.subarray(previous.length));
    return { file, entries: own.length, bytes: bytes.length };
  }
  return {
    get sessionId() { return session; },
    startSession(next = randomUUID()) {
      if (!safeId(next)) throw new Error("invalid journal session");
      session = next;
      return session;
    },
    project: () => serial(projectNow),
    projectNode: (nodeId) => serial(() => projectNodeNow(nodeId)),
    record: (raw) => serial(async () => {
      destination(); // refuse an install-root destination BEFORE the store write
      const entry = prepareEntry(raw, session, now);
      await store.append(entry);
      const projection = await projectNow();
      return { entry, projection };
    }),
    recordPrivate: (raw) => serial(async () => {
      if (typeof store.appendPrivate !== "function") return null;
      nodeDestination(raw && raw.node_id);
      const entry = prepareEntry(raw, session, now);
      await store.appendPrivate(entry);
      const projection = await projectNodeNow(entry.node_id);
      return { entry, projection };
    }),
    async entries() {
      await queue;
      const entries = await store.entries({ sessionId: session, limit: MAX_RECENT_ENTRIES });
      if (!Array.isArray(entries)) throw new Error("journal store unavailable");
      return entries;
    },
    async privateEntries(nodeId) {
      await queue;
      if (typeof store.privateEntries !== "function") return [];
      const entries = await store.privateEntries({ nodeId, sessionId: session, limit: MAX_RECENT_ENTRIES });
      if (!Array.isArray(entries)) throw new Error("journal store unavailable");
      return entries.filter(e => e && e.node_id === nodeId);
    },
    async observe(window, panes, totalMaxChars) {
      if (!Number.isSafeInteger(totalMaxChars) || totalMaxChars <= 0)
        throw new Error("budget_unmeasurable: pane observation withheld");
      const rows = observePanes(window, panes.map(p => p.pane_id), { totalMaxChars });
      const result = [];
      let remaining = totalMaxChars;
      for (const row of rows) {
        const meta = panes.find(p => p.pane_id === row.pane_id) || {};
        // observePanes has a documented per-pane floor; apply the aggregate ceiling here.
        const text = String(row.text || "").slice(0, remaining);
        remaining -= text.length;
        result.push(await this.record({ ...meta, self_published: false, source: SOURCE,
          status: row.answerable ? "observed" : "unreadable", answer: text,
          reason: row.reason || "", redactions: row.redactions || 0,
          redaction_kinds: row.redaction_kinds || [], truncated: row.truncated
            || text.length < String(row.text || "").length }));
      }
      return result;
    },
  };
}
module.exports = { SCHEMA, SOURCE, MAX_SESSION_ENTRIES, MAX_FILE_BYTES, MAX_RECENT_ENTRIES,
  cleanText, validEntry, prepareEntry, renderSession, renderNodeMemory, composeOwnDigest,
  paneNumber, createWorkspaceJournal };
