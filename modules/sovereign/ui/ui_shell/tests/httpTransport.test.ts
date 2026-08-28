// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpTransport } from "../src/services/httpTransport";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("canonical HTTP transport", () => {
  it("submits an explicit route and exposes an accepted job immediately", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response(
        {
          job_id: "job-1",
          session_id: "session-1",
          status: "accepted",
          route: "RESEARCH",
          progress: { percent: 0, stage: "accepted" },
        },
        202
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await createHttpTransport().sendMessage(
      "research this",
      "session-1",
      "RESEARCH"
    );

    expect(result.ok).toBe(true);
    expect(result.job).toMatchObject({
      job_id: "job-1",
      status: "accepted",
      route: "RESEARCH",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/message",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          input: "research this",
          session_id: "session-1",
          route_override: "RESEARCH",
        }),
      })
    );
  });

  it("never promotes rejected candidate output to an accepted message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            job_id: "job-rejected",
            status: "rejected",
            route: "DEEP",
            error: "Concurrence was not reached.",
            message: {
              id: "candidate",
              role: "sovereign",
              content: "Unaccepted candidate text",
              timestamp: "2026-01-01T00:00:00Z",
            },
          },
          422
        )
      )
    );

    const result = await createHttpTransport().sendMessage(
      "hard prompt",
      "session-1",
      "DEEP"
    );

    expect(result.ok).toBe(false);
    expect(result.status).toBe("rejected");
    expect(result.job?.message).toBeUndefined();
    expect(result.message).toBeUndefined();
    expect(result.error).toBe("Concurrence was not reached.");
  });

  it("treats API progress percent as a 0-100 value", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          job_id: "job-progress",
          session_id: "session-1",
          status: "running",
          route: "DEEP",
          progress: { percent: 1, stage: "engine_start" },
        })
      )
    );

    const result = await createHttpTransport().getJob("job-progress");

    expect(result.ok).toBe(true);
    expect(result.job?.progress).toMatchObject({
      percent: 1,
      stage: "engine_start",
    });
  });

  it("normalizes durable session envelopes and active-job recovery fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          sessions: [
            {
              session_id: "session-1",
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:01:00Z",
              title: "Durable session",
              messages: [
                {
                  id: "message-1",
                  role: "assistant",
                  content: "Accepted",
                  timestamp: "2026-01-01T00:01:00Z",
                  status: "completed",
                },
              ],
              active_model_profile: "default",
              orchestration_mode: "AUTO",
              active_job_id: "job-1",
            },
          ],
        })
      )
    );

    const result = await createHttpTransport().getChatHistory();

    expect(result.ok).toBe(true);
    expect(result.sessions[0]).toMatchObject({
      session_id: "session-1",
      active_job_id: "job-1",
    });
    expect(result.sessions[0].messages[0]).toMatchObject({
      role: "sovereign",
      job_status: "completed",
    });
  });

  it("accepts direct completion only when the terminal state is completed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          ok: true,
          status: "completed",
          route: "STATUS",
          message: {
            id: "message-1",
            role: "sovereign",
            content: "Machine-observable status.",
            timestamp: "2026-01-01T00:00:00Z",
            evidence_pointer: "sovereign://runtime/evidence/status.json",
          },
        })
      )
    );

    const result = await createHttpTransport().sendMessage(
      "status",
      "session-1",
      "STATUS"
    );

    expect(result.ok).toBe(true);
    expect(result.status).toBe("completed");
    expect(result.message).toMatchObject({
      content: "Machine-observable status.",
      route: "STATUS",
      job_status: "completed",
      evidence: {
        pointer: "sovereign://runtime/evidence/status.json",
      },
    });
  });

  it("saves role assignments and uses the authoritative returned profile", async () => {
    const profile = {
      name: "manifest-default",
      mutable: true,
      editableRoles: ["PRIMARY_REASONER"],
      restartRequired: false,
      assignments: [
        { role: "PRIMARY_REASONER", modelId: "extra:latest" },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      response({ ok: true, profile })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await createHttpTransport().setModelAssignments([
      { role: "PRIMARY_REASONER", modelId: "extra:latest" },
    ]);

    expect(result).toEqual({ ok: true, error: undefined, profile });
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/models/active",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          assignments: [
            { role: "PRIMARY_REASONER", modelId: "extra:latest" },
          ],
        }),
      })
    );
  });

  it("surfaces an authoritative rejection without changing browser state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          { error: "model assignment rejected; model is not installed: fake" },
          400
        )
      )
    );

    const result = await createHttpTransport().setModelAssignments([
      { role: "PRIMARY_REASONER", modelId: "fake" },
    ]);

    expect(result).toEqual({
      ok: false,
      error: "model assignment rejected; model is not installed: fake",
    });
  });
});
