import { describe, expect, it } from "vitest";

import {
  retainDirectCompletedMessage,
  submissionJob,
} from "../../src/state/chatState";
import { normalizeSubmissionResult } from "../../src/services/httpTransport";
import type { ChatMessage, ChatSession } from "../../src/types/chat";


const message: ChatMessage = {
  id: "message-1",
  role: "sovereign",
  content: "answer",
  timestamp: "2026-09-15T00:00:00Z",
};


function session(messages: ChatMessage[] = []): ChatSession {
  return {
    session_id: "session-1",
    created_at: "2026-09-15T00:00:00Z",
    updated_at: "2026-09-15T00:00:00Z",
    title: "Session",
    messages,
    active_model_profile: "default",
    orchestration_mode: "AUTO",
  };
}


describe("CR-039 extracted UI state phases", () => {
  it("normalizes a completed direct response", () => {
    const result = normalizeSubmissionResult({
      ok: true,
      status: 200,
      data: { status: "completed", route: "quick", message },
    } as never);
    expect(result.ok).toBe(true);
    expect(result.status).toBe("completed");
    expect(result.route).toBe("QUICK");
    expect(result.message?.job_status).toBe("completed");
  });

  it("turns a status-only submission into a stable job projection", () => {
    const job = submissionJob(
      { ok: true, status: "running", route: "DEEP" },
      "session-1",
      42
    );
    expect(job).toEqual({
      job_id: "running-42",
      session_id: "session-1",
      status: "running",
      route: "DEEP",
      progress: { percent: 0 },
      message: undefined,
      evidence: undefined,
      error: undefined,
    });
  });

  it("retains a direct completed message once after refresh failure", () => {
    const first = retainDirectCompletedMessage([session()], "session-1", message);
    const second = retainDirectCompletedMessage(first, "session-1", message);
    expect(second[0].messages).toEqual([message]);
  });
});
