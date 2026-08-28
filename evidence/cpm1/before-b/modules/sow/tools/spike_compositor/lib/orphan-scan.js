"use strict";
/** Automated form of kill criterion 9 ("ConPTY ownership not safely containable").
 *  After teardown: (a) every recorded PTY pid must be dead; (b) no conhost.exe /
 *  OpenConsole.exe process may remain whose parent is this process or one of the
 *  recorded PTY pids. findOrphans is pure (testable headless); the caller supplies
 *  the live process list (from CIM) and liveness results. Caveat recorded in the
 *  report: pid-liveness via signal-0 is subject to PID reuse (treated as acceptable
 *  for a spike; a hit fails safe, i.e. toward NOT containable). */
function findOrphans(procList, ownPid, knownPtyPids) {
  const suspectParents = new Set([ownPid, ...knownPtyPids]);
  return (procList || [])
    .filter((p) => /^(conhost|openconsole)(\.exe)?$/i.test(String(p.Name || "")))
    .filter((p) => suspectParents.has(Number(p.ParentProcessId)))
    .map((p) => ({ pid: Number(p.ProcessId), name: p.Name, ppid: Number(p.ParentProcessId) }));
}
/** Normalize PowerShell ConvertTo-Json output: null/empty -> [], single object -> [obj]. */
function parseCimJson(raw) {
  const t = String(raw || "").trim();
  if (!t) return [];
  const v = JSON.parse(t);
  return Array.isArray(v) ? v : [v];
}
module.exports = { findOrphans, parseCimJson };
