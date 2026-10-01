import { describe, expect, it } from "vitest";

import { stageLabel } from "../../src/state/stageLabel";

describe("stageLabel", () => {
  it("turns a bare identifier into words", () => {
    expect(stageLabel("exact_counting")).toBe("Exact counting");
    expect(stageLabel("local_evidence_retrieval_and_planning")).toBe(
      "Local evidence retrieval and planning",
    );
  });

  it("leaves text that is already readable, and any job id in it, alone", () => {
    expect(stageLabel("waiting for LONG job job_1a2b3c")).toBe(
      "waiting for LONG job job_1a2b3c",
    );
    expect(stageLabel("running")).toBe("running");
    expect(stageLabel("Plan step 3")).toBe("Plan step 3");
    expect(stageLabel(undefined)).toBeUndefined();
  });
});
