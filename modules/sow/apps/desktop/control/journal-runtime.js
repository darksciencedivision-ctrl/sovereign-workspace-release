"use strict";
/** Runtime-only local adapter. Requiring this module starts nothing and writes nothing. */
const path = require("node:path");
const { spawn } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const { resolvePython } = require("../python-runtime");
const { scrubCredentialEnv } = require("../conductor/launch-source");
const { createWorkspaceJournal } = require("./workspace-journal");
const ROOT = path.resolve(__dirname, "../../..");
function callStore(request, { spawnProcess = spawn, cwd = ROOT } = {}) {
  return new Promise((resolve, reject) => {
    let child, timer, bytes = 0, stdout = "";
    let settled = false;
    function finish(error, result) {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) { try { child && child.kill(); } catch {} reject(error); }
      else resolve(result);
    }
    try {
      const py = resolvePython(cwd);
      child = spawnProcess(py.python, [...py.pythonArgs, "-B",
        path.join(__dirname, "journal-store.py")], { cwd, windowsHide: true,
        env: { ...scrubCredentialEnv(process.env), PYTHONDONTWRITEBYTECODE: "1" },
        stdio: ["pipe", "pipe", "pipe"] });
      timer = setTimeout(() => finish(new Error("journal operation timed out")), 15000);
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", d => {
        bytes += Buffer.byteLength(d, "utf8");
        if (bytes > 9 * 1024 * 1024) return finish(new Error("journal response over budget"));
        stdout += d.toString("utf8");
      });
      child.stderr.on("data", () => {}); // never persist host paths or diagnostics containing secrets
      child.on("error", () => finish(new Error("journal helper unavailable")));
      child.stdin.on("error", () => finish(new Error("journal helper input unavailable")));
      child.on("close", code => {
        if (code !== 0) return finish(new Error("journal helper failed"));
        try {
          const response = JSON.parse(stdout);
          if (response.ok !== true) return finish(new Error(response.error || "journal unavailable"));
          finish(null, response.result);
        } catch { finish(new Error("journal response unreadable")); }
      });
      child.stdin.end(JSON.stringify(request));
    } catch { finish(new Error("journal helper unavailable")); }
  });
}
function createStore({ storeRoot = path.join(ROOT, ".sovereign_store"), projectId = "proj",
  call = callStore } = {}) {
  const invoke = (op, args = {}) => call({ op, store_root: storeRoot, project_id: projectId, ...args });
  return {
    append: entry => invoke("append", { entry }),
    appendPrivate: entry => invoke("append_private", { entry }),
    entries: ({ sessionId, limit }) => invoke("entries", { session_id: sessionId, limit }),
    privateEntries: ({ nodeId, sessionId, limit }) => invoke("private_entries",
      { node_id: nodeId, session_id: sessionId, limit }),
    budget: (profile) => invoke("budget", profile ? { profile } : {}),
  };
}
let runtime = null;
let modelSource = () => null;
function configureJournalModelSource(source) { modelSource = source; }
function startJournalSession() {
  const previous = runtime ? runtime.sessionId : null;
  if (!process.env.LOCALAPPDATA) throw new Error("journal state root unavailable");
  runtime = createWorkspaceJournal({ store: createStore(), installRoot: path.resolve(ROOT, "../.."),
    stateRoot: path.join(process.env.LOCALAPPDATA, "SovereignWorkspace", "sow"),
    sessionId: randomUUID() });
  runtime.modelFor = modelSource;
  runtime.workerBudget = () => createStore().budget({ worker: true });
  return { previous_session_id: previous, session_id: runtime.sessionId, deleted: false };
}
async function clearSession({ confirm, teardownPane, paneIds = [], journal }) {
  if (confirm !== true) return { changed: false, reason: "confirmation required", deleted: false };
  const results = [];
  for (const id of paneIds) {
    try {
      await teardownPane(id);
      results.push({ pane_id: id, ok: true });
    } catch (err) {
      results.push({ pane_id: id, ok: false,
        reason: String((err && err.message) || err || "teardown refused") });
    }
  }
  const previous = journal.sessionId;
  journal.startSession();
  return {
    changed: true, deleted: false, complete: results.every(row => row.ok),
    previous_session_id: previous, session_id: journal.sessionId, results,
  };
}
function runtimeJournal() {
  if (!runtime) {
    if (!process.env.LOCALAPPDATA) throw new Error("journal state root unavailable");
    runtime = createWorkspaceJournal({ store: createStore(), installRoot: path.resolve(ROOT, "../.."),
      stateRoot: path.join(process.env.LOCALAPPDATA, "SovereignWorkspace", "sow"),
      sessionId: randomUUID() });
  }
  runtime.modelFor = modelSource;
  runtime.workerBudget = () => createStore().budget({ worker: true });
  return runtime;
}
// Pure delegation tests never activate the host adapter. Electron uses the same instance as chat.
function journalFor(io) {
  return io.journal || (process.versions.electron ? runtimeJournal() : null);
}
module.exports = { callStore, createStore, runtimeJournal, journalFor, configureJournalModelSource,
  startJournalSession, clearSession };
