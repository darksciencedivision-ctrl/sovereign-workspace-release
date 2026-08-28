// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ModelSelector } from "../src/components/ModelSelector";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("editable model assignments", () => {
  it("populates selectors from local models and submits only changed roles", async () => {
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    const onSave = vi.fn().mockResolvedValue(true);

    await act(async () => {
      root.render(
        <ModelSelector
          models={[
            {
              id: "qwen2.5:14b-instruct",
              name: "qwen2.5:14b-instruct",
              source: "local",
              status: "available",
            },
            {
              id: "extra:latest",
              name: "extra:latest",
              source: "local",
              status: "available",
            },
          ]}
          profile={{
            name: "manifest-default",
            mutable: true,
            editableRoles: ["PRIMARY_REASONER"],
            restartRequired: false,
            assignments: [
              {
                role: "PRIMARY_REASONER",
                modelId: "qwen2.5:14b-instruct",
              },
              {
                role: "EMBEDDING_MODEL",
                modelId: "nomic-embed-text:latest",
              },
            ],
          }}
          loaded
          onRefresh={vi.fn()}
          onSave={onSave}
          onClose={vi.fn()}
        />
      );
    });

    const select = container.querySelector("select") as HTMLSelectElement;
    expect([...select.options].map((option) => option.value)).toEqual([
      "qwen2.5:14b-instruct",
      "extra:latest",
    ]);
    expect(container.textContent).toContain("Read-only: the local registry");

    await act(async () => {
      select.value = "extra:latest";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const apply = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "Apply Changes"
    ) as HTMLButtonElement;
    expect(apply.disabled).toBe(false);

    await act(async () => {
      apply.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onSave).toHaveBeenCalledWith([
      { role: "PRIMARY_REASONER", modelId: "extra:latest" },
    ]);

    await act(async () => root.unmount());
  });
});
