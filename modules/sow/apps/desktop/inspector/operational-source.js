"use strict";
const { defaultPython, defaultPythonArgs } = require("../python-runtime");

const { spawn: realSpawn } = require("node:child_process");

const SCHEMA = "sovereign_operational_state@1.0";

class OperationalSourceError extends Error {}

function valid(feed) {
  return Boolean(feed && feed.schema === SCHEMA && typeof feed.project_id === "string"
    && Array.isArray(feed.tasks) && Array.isArray(feed.messages) && Array.isArray(feed.debates)
    && feed.summary && typeof feed.summary === "object");
}

function fetchOperationalFeed(opts = {}) {
  const spawn = opts.spawn || realSpawn;
  const args = [...(opts.pythonArgs || defaultPythonArgs()), "tools/live/emit_operational_state.py",
    "--project", opts.projectId || "proj", "--store-root", opts.storeRoot];
  return new Promise((resolve, reject) => {
    let child;
    try { child = spawn(opts.python || defaultPython(), args, { cwd: opts.cwd }); }
    catch (e) { reject(new OperationalSourceError(`could not launch operational-state emitter: ${e.message}`)); return; }
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { child.kill(); } catch { /* already gone */ }
      fn(value);
    };
    const timer = setTimeout(() => finish(reject,
      new OperationalSourceError("operational-state emitter timed out")), opts.timeoutMs || 15000);
    child.stdout.on("data", (d) => { stdout += String(d); });
    child.stderr.on("data", (d) => { stderr += String(d); });
    child.on("error", (e) => finish(reject,
      new OperationalSourceError(`operational-state emitter failed: ${e.message}`)));
    child.on("exit", (code) => {
      if (code !== 0) {
        finish(reject, new OperationalSourceError(
          `operational-state emitter exited ${code}: ${stderr.trim().slice(0, 200)}`));
        return;
      }
      let feed;
      try { feed = JSON.parse(stdout); }
      catch (e) {
        finish(reject, new OperationalSourceError(`operational-state emitter emitted non-JSON: ${e.message}`));
        return;
      }
      if (!valid(feed)) {
        finish(reject, new OperationalSourceError("operational-state emitter emitted malformed data"));
        return;
      }
      finish(resolve, feed);
    });
  });
}

/**
 * The display model for the inspector's LIVE ORCHESTRATION section.
 *
 * U336 (unit 19.7) — "I CANNOT SEE" MUST NOT RENDER AS "NOTHING HAPPENED". The failure branch used
 * to return a fully-shaped feed: `tasks: []`, `messages: []`, `debates: []` and a summary of four
 * zeroes, with `ok:false` and an error string beside them. Every consumer that read the counts —
 * the drawer paints them directly — was therefore told, in the shape it trusts, that the governed
 * store held nothing, when what had actually happened was that the emitter never ran. A shared
 * memory containing a failed task and one that could not be read are the same picture, and the
 * second one is the one where somebody needs to look.
 *
 * So the unreadable branch carries NO counts at all. `available:false` states it, `summary`,
 * `tasks`, `messages` and `debates` are **null** rather than empty (null is unreadable; empty is a
 * measurement), and the error says why. `nodes` survives, because that list is this shell's own
 * observation of its live sessions and does not come from the emitter — losing it would trade one
 * dishonesty for another.
 *
 * `available` rather than only `ok`: `ok` is the call's outcome and callers already coerce it in
 * places; `available` is a statement about the DATA and is what the renderer branches on.
 */
async function fetchOperationalState(opts = {}) {
  const nodes = Array.isArray(opts.nodes) ? opts.nodes : [];
  try {
    const feed = await fetchOperationalFeed(opts);
    // `available` and `ok` are set AFTER the spread: they are this call's verdict about itself, and
    // an emitter that shipped either key would otherwise overwrite it (spec-auditor, MINOR).
    return { ...feed, ok: true, available: true, nodes };
  } catch (e) {
    return {
      ok: false, available: false, schema: SCHEMA, project_id: opts.projectId || "proj",
      tasks: null, messages: null, debates: null, summary: null, nodes,
      error: `${e.name || "Error"}: ${e.message}`,
    };
  }
}

module.exports = { SCHEMA, OperationalSourceError, valid, fetchOperationalFeed, fetchOperationalState };
