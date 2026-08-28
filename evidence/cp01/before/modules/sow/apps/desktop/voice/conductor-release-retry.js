"use strict";

/**
 * Keep durable-terminal release retries independent by session.
 *
 * A conductor may be relaunched while an older session's ledger release is retrying. A single
 * process-wide timer lets the newer session suppress that older retry (or vice versa), stranding a
 * live holder until Electron exits. One timer per durable session key preserves both obligations.
 */
function createReleaseRetryScheduler({
  retry,
  schedule = setTimeout,
  delayMs = 30_000,
} = {}) {
  if (typeof retry !== "function") {
    throw new Error("createReleaseRetryScheduler requires retry(sessionId)");
  }
  const timers = new Map();
  const scheduleSession = (sessionId) => {
    if (!sessionId || timers.has(sessionId)) return false;
    const timer = schedule(async () => {
      // Delete before retrying: an unsuccessful retry must be able to schedule itself again.
      timers.delete(sessionId);
      try {
        const result = await retry(sessionId);
        if (!result || result.ok !== true) scheduleSession(sessionId);
      } catch {
        scheduleSession(sessionId);
      }
    }, delayMs);
    timer?.unref?.();
    timers.set(sessionId, timer);
    return true;
  };

  return {
    schedule: scheduleSession,

    pendingSessions() {
      return [...timers.keys()];
    },
  };
}

async function releaseOrSchedule({
  sessionId,
  release,
  schedule,
} = {}) {
  if (typeof release !== "function" || typeof schedule !== "function") {
    throw new Error("releaseOrSchedule requires release() and schedule(sessionId)");
  }
  let result;
  try {
    result = await release();
  } catch (error) {
    result = { ok: false, released: false, error: `${error.name || "Error"}: ${error.message}` };
  }
  if (!result || result.ok !== true) schedule(sessionId);
  return result || { ok: false, released: false, error: "release returned no result" };
}

function createReleaseTargetStore() {
  const targets = new Map();
  return {
    mark(sessionId, state, reason) {
      if (!sessionId || !state) return false;
      targets.set(sessionId, { state, reason: reason || null });
      return true;
    },
    get(sessionId) {
      const target = targets.get(sessionId);
      return target ? { ...target } : null;
    },
    take(sessionId) {
      const target = targets.get(sessionId);
      if (!target) return null;
      targets.delete(sessionId);
      return { ...target };
    },
  };
}

module.exports = { createReleaseRetryScheduler, createReleaseTargetStore, releaseOrSchedule };
