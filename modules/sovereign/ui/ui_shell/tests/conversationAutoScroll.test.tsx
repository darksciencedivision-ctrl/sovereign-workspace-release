// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatWindow } from "../src/components/ChatWindow";
import type { ChatMessage } from "../src/types/chat";

function message(id: string): ChatMessage {
  return {
    id,
    role: "sovereign",
    content: `answer ${id}`,
    timestamp: "2026-01-01T00:00:00Z",
    job_status: "completed",
  } as ChatMessage;
}

/** Drive the conversation element's scroll geometry, which jsdom otherwise
 *  reports as zero for everything. */
function setScrollGeometry(
  element: HTMLElement,
  geometry: { scrollHeight: number; clientHeight: number; scrollTop: number },
) {
  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    value: geometry.scrollHeight,
  });
  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    value: geometry.clientHeight,
  });
  element.scrollTop = geometry.scrollTop;
}

let container: HTMLDivElement;
let root: Root;
let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

function render(messages: ChatMessage[]) {
  act(() => {
    root.render(<ChatWindow messages={messages} />);
  });
  return container.querySelector(".conversation") as HTMLElement;
}

describe("conversation auto-scroll threshold", () => {
  it("follows new output while the reader is at the bottom", () => {
    render([message("a")]);
    scrollIntoView.mockClear();

    render([message("a"), message("b")]);

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("does not yank the reader down when they have scrolled up", () => {
    const conversation = render([message("a")]);
    // 2000px of content, a 500px window, parked near the top: the reader is
    // 1500px from the bottom, far outside the threshold.
    setScrollGeometry(conversation, {
      scrollHeight: 2000,
      clientHeight: 500,
      scrollTop: 0,
    });
    act(() => {
      conversation.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    scrollIntoView.mockClear();

    render([message("a"), message("b")]);

    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("resumes following once the reader scrolls back near the bottom", () => {
    const conversation = render([message("a")]);
    setScrollGeometry(conversation, {
      scrollHeight: 2000,
      clientHeight: 500,
      scrollTop: 0,
    });
    act(() => {
      conversation.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    // Back within 120px of the bottom.
    setScrollGeometry(conversation, {
      scrollHeight: 2000,
      clientHeight: 500,
      scrollTop: 1450,
    });
    act(() => {
      conversation.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    scrollIntoView.mockClear();

    render([message("a"), message("b")]);

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });
});
