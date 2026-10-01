import { describe, expect, it } from "vitest";

import { LONG_SWAP_WARNING, longSwapWarning } from "../../src/state/longSwapWarning";

describe("LONG queue notice", () => {
  it("notes the wait for every route except LONG and STATUS while a LONG job is active", () => {
    for (const route of ["AUTO", "QUICK", "DEEP", "RESEARCH", "CONTINUITY"]) {
      expect(longSwapWarning(route, "job-long-1")).toBe(LONG_SWAP_WARNING);
    }
    expect(LONG_SWAP_WARNING).toContain("will run after the LONG job finishes");
  });

  it("is silent for LONG and STATUS, and when no LONG job is active", () => {
    expect(longSwapWarning("LONG", "job-long-1")).toBeNull();
    expect(longSwapWarning("STATUS", "job-long-1")).toBeNull();
    expect(longSwapWarning("QUICK", null)).toBeNull();
    expect(longSwapWarning("DEEP", undefined)).toBeNull();
    expect(longSwapWarning("QUICK", "")).toBeNull();
  });
});
