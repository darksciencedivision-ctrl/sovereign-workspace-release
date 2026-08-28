"use strict";

/**
 * Reduce conductor PTY lifecycle without confusing a termination request with
 * confirmation that the process is gone.
 */
function advanceConductorSessionLifecycle(launch, event, paneId, now = new Date().toISOString()) {
  const unchanged = {
    action: "ignore",
    launch,
    releaseAuthority: false,
    releaseLease: false,
  };
  if (!event || event.id !== paneId) return unchanged;
  // Pane ids are reusable view identities, not process identities. Authority and an I-X3 lease may
  // move only for the exact PTY generation + OS pid recorded at launch; a delayed callback from an
  // older process that once occupied pane 1 is otherwise capable of releasing the replacement.
  if (!Number.isInteger(launch.sessionGeneration) || !Number.isInteger(event.generation)
      || launch.sessionGeneration !== event.generation
      || !Number.isInteger(launch.pid) || !Number.isInteger(event.pid)
      || launch.pid !== event.pid) return unchanged;

  if (event.kind === "kill" && event.processExited === false && launch.state === "running") {
    return {
      action: "await_process_exit",
      launch: { ...launch, state: "terminating", reason: "session termination requested" },
      releaseAuthority: false,
      releaseLease: false,
    };
  }

  if (event.kind !== "exit" || event.processExited !== true
      || !["running", "terminating"].includes(launch.state)) {
    return unchanged;
  }

  return {
    action: "process_exited",
    launch: {
      ...launch,
      state: "release_pending",
      processExited: true,
      endedAt: now,
      exitCode: Number.isFinite(event.exitCode) ? event.exitCode : null,
      reason: `session exited (${event.exitCode})`,
    },
    releaseAuthority: true,
    releaseLease: true,
  };
}

module.exports = { advanceConductorSessionLifecycle };
