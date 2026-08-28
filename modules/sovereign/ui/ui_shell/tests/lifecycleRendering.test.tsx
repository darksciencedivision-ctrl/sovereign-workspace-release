// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  ChatWindow,
  formatElapsedTime,
} from "../src/components/ChatWindow";
import { RunStatus } from "../src/components/RunStatus";

describe("lifecycle rendering", () => {
  it("renders actual task tokens and compact backend time beneath unchanged output", () => {
    const answer = "MODEL ANSWER REMAINS EXACT";
    const html = renderToStaticMarkup(
      <ChatWindow
        messages={[
          {
            id: "accepted",
            role: "sovereign",
            content: answer,
            timestamp: "2026-01-01T00:00:00Z",
            job_status: "completed",
            metrics: { tokens: 12_438, elapsed_seconds: 222 },
          },
        ]}
      />
    );

    expect(html).toContain(answer);
    expect(html).toContain("Tokens: 12,438 • Time: 3m 42s");
    expect(html.indexOf(answer)).toBeLessThan(html.indexOf("Tokens: 12,438"));
    expect((html.match(new RegExp(answer, "g")) ?? [])).toHaveLength(1);
  });

  it("formats compact elapsed backend durations and unavailable tokens", () => {
    expect(formatElapsedTime(0.85)).toBe("850ms");
    expect(formatElapsedTime(4.2)).toBe("4.2s");
    expect(formatElapsedTime(38)).toBe("38s");
    expect(formatElapsedTime(134)).toBe("2m 14s");
    expect(formatElapsedTime(4_920)).toBe("1h 22m");

    const html = renderToStaticMarkup(
      <ChatWindow
        messages={[
          {
            id: "missing-tokens",
            role: "sovereign",
            content: "Answer",
            timestamp: "2026-01-01T00:00:00Z",
            job_status: "completed",
            metrics: { tokens: null, elapsed_seconds: 4.2 },
          },
        ]}
      />
    );
    expect(html).toContain("Tokens: unavailable • Time: 4.2s");
  });

  it("does not render rejected model text as an answer", () => {
    const html = renderToStaticMarkup(
      <ChatWindow
        messages={[
          {
            id: "candidate",
            role: "sovereign",
            content: "MODEL CANDIDATE MUST NOT BE SHOWN",
            timestamp: "2026-01-01T00:00:00Z",
            job_status: "rejected",
            error: "Concurrence was not reached.",
          },
        ]}
      />
    );

    expect(html).not.toContain("MODEL CANDIDATE MUST NOT BE SHOWN");
    expect(html).toContain("REJECTED: no answer was accepted.");
    expect(html).toContain("Concurrence was not reached.");
  });

  it("shows route, progress, cancellation, and evidence for an active run", () => {
    const html = renderToStaticMarkup(
      <RunStatus
        job={{
          job_id: "job-1",
          session_id: "session-1",
          status: "running",
          route: "RESEARCH",
          progress: {
            percent: 42,
            stage: "retrieval",
            detail: "Checkpoint 2",
          },
          evidence: {
            pointer: "sovereign://runtime/evidence/job-1.json",
          },
        }}
        onCancel={vi.fn()}
      />
    );

    expect(html).toContain("Running");
    expect(html).toContain("RESEARCH");
    expect(html).toContain("42%");
    expect(html).toContain("retrieval");
    expect(html).toContain("Cancel");
    expect(html).toContain("Evidence");
  });
});
