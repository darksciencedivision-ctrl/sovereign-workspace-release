import { describe, expect, it } from "vitest";

import { longUnavailableReason } from "../../src/components/RouteSelector";
import {
  EMPTY_LONG_OPTIONS,
  MAX_INPUT_CHARACTERS,
  chunkLabel,
  composeLongRequest,
  normalizeLongRoute,
  normalizeLongRun,
} from "../../src/state/longRequest";

const opts = (patch: Partial<typeof EMPTY_LONG_OPTIONS> = {}) => ({
  ...EMPTY_LONG_OPTIONS,
  ...patch,
});

describe("LONG request composition (the server's line format)", () => {
  it("objective only: plan steps on the default model", () => {
    expect(composeLongRequest("  Draft a plan.  ", opts())).toEqual({
      ok: true,
      text: "Draft a plan.",
    });
  });

  it("chosen model goes on the first line", () => {
    const result = composeLongRequest("Draft a plan.", opts({ model: "qwen3:30b-a3b" }));
    expect(result).toEqual({ ok: true, text: "@model: qwen3:30b-a3b\nDraft a plan." });
  });

  it("pasted material follows a '---' line, with its own lines kept", () => {
    const result = composeLongRequest(
      "Summarize.",
      opts({ mode: "material", material: "\nline one\nline two\n\n" })
    );
    expect(result).toEqual({ ok: true, text: "Summarize.\n---\nline one\nline two" });
  });

  it("an inbox file becomes an @input reference", () => {
    const result = composeLongRequest(
      "Summarize.",
      opts({ mode: "inbox", inboxFile: " report v2.md " })
    );
    expect(result).toEqual({ ok: true, text: "Summarize.\n---\n@input: report v2.md" });
  });

  it.each([
    ["", opts(), "objective"],
    ["Summarize.", opts({ mode: "material", material: "   " }), "Paste the material"],
    ["Summarize.", opts({ mode: "inbox", inboxFile: "../secrets.txt" }), "plain file"],
    ["Summarize.", opts({ mode: "inbox", inboxFile: "C:\\x.txt" }), "plain file"],
    ["Part one\n---\nPart two", opts(), "'---'"],
  ])("refuses %j with a reason", (objective, options, reason) => {
    const result = composeLongRequest(objective, options);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain(reason);
  });

  it("refuses material above the product's input cap and points at the inbox", () => {
    const result = composeLongRequest(
      "Summarize.",
      opts({ mode: "material", material: "x".repeat(MAX_INPUT_CHARACTERS) })
    );
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("long_inputs");
  });
});

describe("LONG progress and run view", () => {
  it("labels chunk progress only when the run reports counts", () => {
    expect(chunkLabel({ percent: 50, current: 3, total: 7 })).toBe("3 of 7 chunks done");
    expect(chunkLabel({ percent: 10 })).toBeUndefined();
    expect(chunkLabel({ percent: 10, current: 0, total: 0 })).toBeUndefined();
    expect(chunkLabel({ percent: 99, current: 9, total: 7 })).toBe("7 of 7 chunks done");
  });

  it("reads the LONG route from health and says why it is unavailable", () => {
    const ready = normalizeLongRoute(true, {
      default_model: "qwen3.8:27b",
      models: [
        { model: "qwen3.8:27b", context: 131072, thinking: "off" },
        { model: "qwen3:30b-a3b", context: 32768, thinking: "on" },
        { nope: 1 },
      ],
    });
    expect(ready?.ready).toBe(true);
    expect(ready?.models.map((m) => m.model)).toEqual(["qwen3.8:27b", "qwen3:30b-a3b"]);
    expect(longUnavailableReason(ready)).toBeUndefined();
    expect(longUnavailableReason(normalizeLongRoute(false, { models: [] }))).toContain(
      "llama.cpp"
    );
    expect(longUnavailableReason(undefined)).toContain("unknown");
    expect(
      longUnavailableReason(normalizeLongRoute(false, { error: "no long_workload.json" }))
    ).toContain("no long_workload.json");
  });

  it("normalizes the ledger view and drops malformed parts", () => {
    const view = normalizeLongRun(
      {
        job_id: "job_1",
        started: true,
        mode: "input_shards",
        run_status: "running",
        model_calls: 3,
        completed: 2,
        total: 4,
        tasks: [
          { task_id: "map-0001", kind: "map", status: "completed", attempts: 1, summary: "s1" },
          { task_id: "map-0002", kind: "map", status: "weird", attempts: 2 },
          { kind: "no id" },
        ],
        ledger: {
          facts: ["f1", 7],
          decisions: [],
          open_questions: ["q?"],
          results: [{ task: "map-0001", summary: "s1" }, { task: "x" }],
        },
      },
      "job_1"
    );
    expect(view?.tasks.map((t) => [t.task_id, t.status])).toEqual([
      ["map-0001", "completed"],
      ["map-0002", "pending"],
    ]);
    expect(view?.ledger?.facts).toEqual(["f1"]);
    expect(view?.ledger?.results).toEqual([{ task: "map-0001", summary: "s1" }]);
    expect(normalizeLongRun("nope", "job_1")).toBeNull();
    expect(normalizeLongRun({ started: false }, "job_2")?.job_id).toBe("job_2");
  });
});
