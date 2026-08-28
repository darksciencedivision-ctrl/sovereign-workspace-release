// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "../src/components/Sidebar";
import { StatusBar } from "../src/components/StatusBar";

// jsdom does not give this file a file: URL, so resolve from the vitest root.
const readStyles = (name: string) =>
  readFileSync(resolve(process.cwd(), "src/styles", name), "utf-8");

const layoutCss = readStyles("layout.css");
const themeCss = readStyles("theme.css");

/** Extract a single rule body by selector so assertions cannot match a
 *  declaration that happens to live in some unrelated rule. */
function ruleBody(css: string, selector: string): string {
  const index = css.indexOf(selector + " {");
  if (index === -1) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", index);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("shell viewport containment", () => {
  // Regression guard for the page-level scrolling defect: the document itself
  // grew past the viewport, so the whole app column scrolled with the page and
  // the composer drifted mid-page with dead space beneath it.
  it("clips page-level scrolling on the document", () => {
    expect(ruleBody(themeCss, "html,\nbody")).toContain("overflow: hidden");
  });

  it("binds the app frame to the viewport height", () => {
    const app = ruleBody(layoutCss, ".app");
    expect(app).toContain("height: 100dvh");
    expect(app).toContain("overflow: hidden");
  });

  it("gives every scroll region a min-height:0 flex parent", () => {
    // Without min-height:0 a flex child refuses to shrink below its content,
    // which is what lets an overflow:auto region overflow its parent anyway.
    for (const selector of [".sidebar", ".workspace"]) {
      expect(ruleBody(layoutCss, selector)).toContain("min-height: 0");
    }
    for (const selector of [".sidebar .session-list", ".conversation"]) {
      const body = ruleBody(layoutCss, selector);
      expect(body).toContain("min-height: 0");
      expect(body).toContain("overflow-y: auto");
    }
  });

  it("pins the docks and status bar as non-shrinking footer rows", () => {
    for (const selector of [".run-dock", ".input-dock", ".statusbar"]) {
      expect(ruleBody(layoutCss, selector)).toContain("flex: 0 0 auto");
    }
  });
});

describe("sidebar", () => {
  const sessions = Array.from({ length: 40 }, (_, index) => ({
    session_id: `session-${index}`,
    title: `Session ${index}`,
    messages: [],
  }));

  it("puts session history in its own scroll container", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        sessions={sessions as never}
        activeId="session-0"
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    );

    // The New Chat button must stay outside the scroll region so it stays
    // pinned; the session buttons must be inside it.
    const listStart = html.indexOf('class="session-list"');
    expect(listStart).toBeGreaterThan(-1);
    expect(html.indexOf("+ New Chat")).toBeLessThan(listStart);
    expect(html.indexOf("Session 0")).toBeGreaterThan(listStart);
    expect(html.indexOf("Session 39")).toBeGreaterThan(listStart);
  });

  it("still renders the empty note inside the scroll container", () => {
    const html = renderToStaticMarkup(
      <Sidebar
        sessions={[]}
        activeId=""
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(html).toContain('class="session-list"');
    expect(html).toContain("No previous sessions");
  });

  it("keeps rows readable, non-shrinking, and visibly selected", () => {
    const item = ruleBody(layoutCss, ".sidebar .session-item");
    expect(item).toContain("flex: 0 0 auto");
    expect(item).toContain("font-size: 14px");
    expect(item).toContain("font-weight: 500");
    expect(item).toContain("line-height: 1.35");
    expect(item).toContain("border-left: 2px solid transparent");
    expect(ruleBody(layoutCss, ".sidebar .session-item.active")).toContain(
      "border-left-color: var(--accent)"
    );

    const html = renderToStaticMarkup(
      <Sidebar
        sessions={sessions as never}
        activeId="session-0"
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />
    );
    expect(html).toContain('class="session-item active"');
    expect(html).toContain('aria-current="page"');
  });

  it("keeps long server titles inside one ellipsized row", () => {
    const title = ruleBody(
      layoutCss,
      ".sidebar .session-item > span:first-child"
    );
    expect(title).toContain("white-space: nowrap");
    expect(title).toContain("overflow: hidden");
    expect(title).toContain("text-overflow: ellipsis");

    const longTitle = "A very long server-provided conversation title ".repeat(8);
    const html = renderToStaticMarkup(
      <Sidebar
        sessions={[{ ...sessions[0], title: longTitle }] as never}
        activeId=""
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />
    );
    expect(html).toContain(`title="${longTitle}"`);
  });
});

describe("status strip", () => {
  const health = {
    reachable: true,
    status: "ok",
    engineVersion: "3.1.2",
    orchestrationMode: "OBSERVE",
  };

  it("reads engine, privacy, orchestration mode, and route", () => {
    const html = renderToStaticMarkup(
      <StatusBar
        privacyMode="local-only"
        settingsAvailable
        engineHealth={health as never}
        routeOverride="AUTO"
      />,
    );

    expect(html).toContain("Engine connected");
    expect(html).toContain("3.1.2");
    expect(html).toContain("Local-only");
    expect(html).toContain("OBSERVE");
    expect(html).toContain("AUTO");
    // Order matters: engine, privacy, mode, route.
    expect(html.indexOf("Engine connected")).toBeLessThan(
      html.indexOf("Local-only"),
    );
    expect(html.indexOf("Local-only")).toBeLessThan(html.indexOf("OBSERVE"));
    expect(html.indexOf("OBSERVE")).toBeLessThan(html.indexOf("AUTO"));
  });

  it("does not claim a connected engine when the service is unreachable", () => {
    const html = renderToStaticMarkup(
      <StatusBar
        privacyMode="local-only"
        settingsAvailable
        engineHealth={{ reachable: false } as never}
        routeOverride="AUTO"
      />,
    );
    expect(html).toContain("Engine not reachable");
    expect(html).not.toContain("Engine connected");
  });

  it("does not claim a privacy state when settings are unavailable", () => {
    const html = renderToStaticMarkup(
      <StatusBar
        privacyMode="local-only"
        settingsAvailable={false}
        engineHealth={health as never}
        routeOverride="AUTO"
      />,
    );
    expect(html).toContain("Privacy state unavailable");
    expect(html).not.toContain("Local-only");
  });
});
