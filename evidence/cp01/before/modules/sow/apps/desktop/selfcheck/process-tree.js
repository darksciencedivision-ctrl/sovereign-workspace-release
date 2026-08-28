"use strict";

const { execFile } = require("child_process");

function execFileText(file, args) {
  return new Promise((resolve, reject) => {
    execFile(file, args, { windowsHide: true, maxBuffer: 16 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        error.message = `${error.message}${stderr ? `: ${stderr.trim()}` : ""}`;
        reject(error);
      } else {
        resolve(stdout);
      }
    });
  });
}

async function snapshotProcesses() {
  if (process.platform === "win32") {
    const script = [
      "Get-CimInstance Win32_Process",
      "| Select-Object Name,ProcessId,ParentProcessId,CommandLine",
      "| ConvertTo-Json -Compress",
    ].join(" ");
    const raw = (await execFileText("powershell.exe", [
      "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script,
    ])).trim();
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return (Array.isArray(parsed) ? parsed : [parsed]).map((row) => ({
      pid: Number(row.ProcessId),
      parentPid: Number(row.ParentProcessId),
      name: String(row.Name || ""),
      commandLine: String(row.CommandLine || ""),
    }));
  }

  const raw = await execFileText("ps", ["-eo", "pid=,ppid=,comm=,args="]);
  return raw.split(/\r?\n/).filter(Boolean).map((line) => {
    const match = /^\s*(\d+)\s+(\d+)\s+(\S+)\s*(.*)$/.exec(line);
    return match ? {
      pid: Number(match[1]), parentPid: Number(match[2]), name: match[3], commandLine: match[4],
    } : null;
  }).filter(Boolean);
}

async function terminateProcessTree(pid) {
  if (process.platform === "win32") {
    try { await execFileText("taskkill.exe", ["/PID", String(pid), "/T", "/F"]); }
    catch (error) {
      if (!/not found|no running instance|not exist/i.test(error.message)) throw error;
    }
    return;
  }
  try { process.kill(-pid, "SIGTERM"); } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
}

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class WorkspaceProcessTree {
  constructor(rootPid, {
    snapshot = snapshotProcesses,
    terminate = terminateProcessTree,
    sampleIntervalMs = 1000,
    shutdownTimeoutMs = 10000,
  } = {}) {
    this.rootPid = Number(rootPid);
    this.snapshot = snapshot;
    this.terminate = terminate;
    this.sampleIntervalMs = sampleIntervalMs;
    this.shutdownTimeoutMs = shutdownTimeoutMs;
    this.tracked = new Set(Number.isInteger(this.rootPid) ? [this.rootPid] : []);
    this._timer = null;
    this._sampling = null;
    this._sampleError = null;
  }

  async sample() {
    if (this._sampling) return this._sampling;
    this._sampling = (async () => {
      const rows = await this.snapshot();
      let changed = true;
      while (changed) {
        changed = false;
        for (const row of rows) {
          if (!this.tracked.has(row.pid) && this.tracked.has(row.parentPid)) {
            this.tracked.add(row.pid);
            changed = true;
          }
        }
      }
      return rows;
    })();
    try { return await this._sampling; }
    finally { this._sampling = null; }
  }

  start() {
    if (this._timer) return;
    const sample = () => {
      void this.sample().catch((error) => { this._sampleError = error; });
    };
    sample();
    this._timer = setInterval(sample, this.sampleIntervalMs);
    this._timer.unref?.();
  }

  async waitForWorkspaceExit({
    timeoutMs,
    pollIntervalMs = 100,
  } = {}) {
    const deadline = Date.now() + (Number.isFinite(timeoutMs) ? timeoutMs : this.shutdownTimeoutMs);
    while (true) {
      const rows = await this.sample();
      if (this._sampleError) throw this._sampleError;
      const liveTracked = rows.filter((row) => this.tracked.has(row.pid));
      if (liveTracked.length === 0) {
        return {
          tracked: [...this.tracked].sort((a, b) => a - b),
          remaining: [],
          workspaceNodeRemaining: [],
        };
      }
      if (Date.now() >= deadline) {
        const error = new Error("hard timeout while tracked workspace processes were still running");
        error.code = "SELF_CHECK_TIMEOUT";
        error.remaining = liveTracked;
        error.workspaceNodeRemaining = liveTracked.filter(
          (row) => /^(node|electron)(\.exe)?$/i.test(row.name),
        );
        throw error;
      }
      await delay(pollIntervalMs);
    }
  }

  async cleanup() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    try {
      if (this._sampling) await this._sampling;
      if (this._sampleError) throw this._sampleError;
    } catch (error) {
      // A broken inventory must not strand the known root on a timeout/error path.
      if (Number.isInteger(this.rootPid)) await this.terminate(this.rootPid);
      throw error;
    }

    let rows = await this.sample();
    const livePids = new Set(rows.map((row) => row.pid));
    const liveTracked = [...this.tracked].filter((pid) => livePids.has(pid));
    const targets = liveTracked.includes(this.rootPid) ? [this.rootPid] : liveTracked;
    for (const pid of targets) await this.terminate(pid);

    const deadline = Date.now() + this.shutdownTimeoutMs;
    do {
      rows = await this.sample();
      if (![...this.tracked].some((pid) => rows.some((row) => row.pid === pid))) break;
      await delay(100);
    } while (Date.now() < deadline);

    rows = await this.sample();
    const remaining = rows.filter((row) => this.tracked.has(row.pid));
    const workspaceNodeRemaining = remaining.filter((row) => /^(node|electron)(\.exe)?$/i.test(row.name));
    return {
      tracked: [...this.tracked].sort((a, b) => a - b),
      remaining,
      workspaceNodeRemaining,
    };
  }
}

module.exports = { WorkspaceProcessTree, snapshotProcesses, terminateProcessTree };
