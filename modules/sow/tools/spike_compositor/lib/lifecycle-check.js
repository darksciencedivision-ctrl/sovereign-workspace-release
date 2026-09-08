"use strict";
/** Automated form of kill criterion 8 ("process lifecycle not supervisable").
 *  After teardown, every session must be fully accounted for in the event log:
 *  a spawn event, a terminal state (EXITED/KILLED), and a matching terminal event
 *  (exit for EXITED; kill/kill-on-quit for KILLED). Pure function — testable headless. */
function lifecycleCheck(events, sessions) {
  const spawned = new Set(events.filter((e) => e.kind === "spawn").map((e) => e.detail.id));
  const exited = new Set(events.filter((e) => e.kind === "exit").map((e) => e.detail.id));
  const killed = new Set(events.filter((e) => e.kind === "kill" || e.kind === "kill-on-quit").map((e) => e.detail.id));
  const missing = [];
  for (const s of sessions) {
    if (!spawned.has(s.id)) missing.push({ id: s.id, problem: "no spawn event" });
    if (s.state === "RUNNING" || s.state === "SPAWNING") missing.push({ id: s.id, problem: `still ${s.state} after teardown` });
    else if (s.state === "EXITED" && !exited.has(s.id)) missing.push({ id: s.id, problem: "EXITED without exit event" });
    else if (s.state === "KILLED" && !killed.has(s.id) && !exited.has(s.id)) missing.push({ id: s.id, problem: "KILLED without kill event" });
  }
  return { ok: missing.length === 0, checked: sessions.length, missing };
}
module.exports = { lifecycleCheck };
