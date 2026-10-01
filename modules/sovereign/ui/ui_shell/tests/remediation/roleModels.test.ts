import { describe, expect, it } from "vitest";

import { roleModelsNote } from "../../src/state/roleModels";

const ready = {
  status: "ready",
  models: [{ model: "qwen3:14b", status: "ready", n_gpu_layers: 14 }],
};

describe("roleModelsNote", () => {
  it("says nothing while every model is served as planned or the report is missing", () => {
    expect(roleModelsNote(ready)).toBeUndefined();
    expect(roleModelsNote(undefined)).toBeUndefined();
    expect(roleModelsNote(null)).toBeUndefined();
    expect(roleModelsNote("degraded")).toBeUndefined();
    expect(roleModelsNote({ status: "unknown", models: [] })).toBeUndefined();
  });

  it("names the models that run on the slower default profile", () => {
    const degraded = {
      status: "degraded",
      models: [
        { model: "qwen3:14b", status: "ready" },
        { model: "qwen3:32b", status: "degraded", reason: "plan refused" },
        { model: "qwen3:8b", status: "degraded" },
        7,
      ],
    };
    expect(roleModelsNote(degraded)).toBe(
      "Slower default GPU profile: qwen3:32b, qwen3:8b",
    );
    expect(roleModelsNote({ status: "degraded" })).toBe(
      "Some models run on the slower default GPU profile",
    );
  });
});
