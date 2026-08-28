"use strict";
/**
 * Pane / window state model (product code, terminal/).
 *
 * This is the deterministic UI-STATE core of the workspace canvas: pane create/destroy,
 * maximize/restore/minimize/pin, and — the load-bearing one for correctness — which pane
 * has focus, i.e. where typed input is routed. "Input crosses to the wrong pane" was an
 * explicit Phase-1 kill criterion; keeping focus a single, deterministic, always-valid
 * pointer is how the product avoids it.
 *
 * Deliberately geometry-free: the tiling GEOMETRY (Plan §10.2 near-square grid, pinned
 * double-cells) is the sibling sub-step `.tiling`. This model only produces the ordered set
 * of tiling members (`tilingMembers()`) that the geometry consumes, plus window state. That
 * separation keeps both pieces independently testable.
 *
 * All operations are pure state transitions with no time or I/O; every method returns the
 * model for chaining and asserts its own invariants (fail-closed on unknown ids).
 */
const WINDOW_STATES = new Set(["normal", "minimized", "maximized"]);

// Pane activity feeds the `.tiling` priority classes (Plan §10.2): awaiting_operator→P1,
// active→P2, background→P3, idle→P4 (pinned→P0 is a separate flag that overrides activity).
// This is semantic node state the tiling policy consumes; the model never computes geometry.
const ACTIVITIES = new Set(["awaiting_operator", "active", "background", "idle"]);

class PaneModel {
  constructor() {
    this.panes = new Map();      // id -> {id, sessionId, title, windowState, pinned, attention}
    this.order = [];             // creation / z-order (stable for layout slotting)
    this.focusedId = null;
    this.maximizedId = null;
    this._focusHistory = [];     // most-recent-last, used to pick a fallback on focus loss
  }

  createPane({ id, sessionId = null, title = "" }) {
    if (!id) throw new Error("createPane requires an id");
    if (this.panes.has(id)) throw new Error(`duplicate pane ${id}`);
    this.panes.set(id, { id, sessionId, title, windowState: "normal", pinned: false, attention: false, activity: "active" });
    this.order.push(id);
    this.focus(id); // a new pane takes focus
    return this;
  }

  destroyPane(id) {
    this._must(id);
    this.panes.delete(id);
    this.order = this.order.filter((x) => x !== id);
    this._focusHistory = this._focusHistory.filter((x) => x !== id);
    if (this.maximizedId === id) this.maximizedId = null;
    if (this.focusedId === id) this.focusedId = this._pickFocus();
    return this;
  }

  focus(id) {
    this._must(id);
    if (this.panes.get(id).windowState === "minimized") this.panes.get(id).windowState = "normal";
    this.focusedId = id;
    this._focusHistory = this._focusHistory.filter((x) => x !== id);
    this._focusHistory.push(id);
    return this;
  }

  maximize(id) {
    this._must(id);
    this.maximizedId = id;
    this.panes.get(id).windowState = "maximized";
    this.focus(id);
    return this;
  }

  /** Restore a maximized pane back into the tiled set. */
  restore(id) {
    this._must(id);
    if (this.maximizedId === id) this.maximizedId = null;
    this.panes.get(id).windowState = "normal";
    return this;
  }

  minimize(id) {
    this._must(id);
    this.panes.get(id).windowState = "minimized";
    if (this.maximizedId === id) this.maximizedId = null;
    if (this.focusedId === id) this.focusedId = this._pickFocus();
    return this;
  }

  /**
   * Bind a session to a pane that was created without one (Phase 17A `.pty`). The pinned CONDUCTOR
   * pane exists from first paint but carries no session until its governed live launch is
   * authorized — this records the binding so the pane snapshots (and recovers) as session-backed
   * rather than as a placeholder. Fail-closed on an unknown id like every other operation; it does
   * NOT create or authorize anything, it records a binding the supervised spawn already made.
   */
  attachSession(id, sessionId) {
    this._must(id);
    if (!sessionId) throw new Error("attachSession requires a sessionId — a pane is bound to a real session or to none");
    this.panes.get(id).sessionId = sessionId;
    return this;
  }

  pin(id) { this._must(id); this.panes.get(id).pinned = true; return this; }
  unpin(id) { this._must(id); this.panes.get(id).pinned = false; return this; }
  setAttention(id, on) { this._must(id); this.panes.get(id).attention = !!on; return this; }

  /** Set the pane's activity (drives the `.tiling` priority class). Fail-closed on an
   *  unknown activity — an invalid priority must never silently default. */
  setActivity(id, activity) {
    this._must(id);
    if (!ACTIVITIES.has(activity)) throw new Error(`unknown activity ${JSON.stringify(activity)}`);
    this.panes.get(id).activity = activity;
    return this;
  }

  /** Panes that should currently be laid out. Under maximize, only the maximized pane is
   *  visible; otherwise every non-minimized pane, in stable creation order. */
  visible() {
    if (this.maximizedId && this.panes.has(this.maximizedId)) {
      return [this._snapshot(this.maximizedId)];
    }
    return this.order
      .filter((id) => this.panes.get(id).windowState !== "minimized")
      .map((id) => this._snapshot(id));
  }

  /** Shape the `.tiling` policy consumes: {id, pinned, attention, activity} in layout order. */
  tilingMembers() {
    return this.visible().map(({ id, pinned, attention, activity }) => ({ id, pinned, attention, activity }));
  }

  minimized() {
    return this.order.filter((id) => this.panes.get(id).windowState === "minimized").map((id) => this._snapshot(id));
  }

  get(id) { this._must(id); return this._snapshot(id); }
  size() { return this.panes.size; }

  // -- internals -------------------------------------------------------------
  _pickFocus() {
    // Prefer the most-recently-focused still-present, non-minimized pane; else last visible; else null.
    for (let i = this._focusHistory.length - 1; i >= 0; i--) {
      const id = this._focusHistory[i];
      if (this.panes.has(id) && this.panes.get(id).windowState !== "minimized") return id;
    }
    const vis = this.visible();
    return vis.length ? vis[vis.length - 1].id : null;
  }

  _snapshot(id) { return { ...this.panes.get(id) }; }

  _must(id) { if (!this.panes.has(id)) throw new Error(`unknown pane ${id}`); }
}

module.exports = { PaneModel, WINDOW_STATES };
