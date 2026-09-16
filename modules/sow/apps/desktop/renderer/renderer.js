"use strict";
/**
 * Renderer (sandboxed view). No Node access — every action goes through window.sovereign
 * (the preload bridge) to a governed main-process handler. This file is a THIN VIEW over the
 * authoritative pane state pushed from main; it never owns session lifecycle, supervision, or
 * layout policy.
 *
 * TWO channels realize Plan §10.2's "restyle without reflow":
 *   - shell:state  (onState)  — chrome/content: focus, pin flag, title, session state, status
 *                               cards, minimized bar. Applied WITHOUT touching grid geometry.
 *   - shell:layout (onLayout) — the §10.2 layout PLAN computed in main by terminal/compositor/
 *                               tiling.js: which panes are tiled (grid + P0/P1 double cells) vs
 *                               collapsed to the status-card rail. Debounced + membership-gated
 *                               in main, so it arrives only on a real membership change → reflow.
 */
window.addEventListener("error", (e) => { window.__rendererLastError = String((e && (e.message || e.error)) || e); });
const S = window.sovereign;
const PaneFeed = window.PaneFeed; // pure scrollback/live merge (pane-feed.js, loaded before this)
const grid = document.getElementById("grid");
const rail = document.getElementById("rail");
const terms = new Map();      // paneId -> { term, fit, el, feed }  (GRID panes only)
const meta = new Map();       // paneId -> { title, sessionState } (from shell:state)
let focusedId = null;
let maximizedId = null;
let conductor = null;         // conductor-first pane state (badge + Resume→Select), from shell:conductor
//: Live session ids from the last `shell:state` push. Held because SW-ORCH-001 F-21's delegate
//: control must know whether any WORKER pane is up, and "a session that is not the conductor's" is
//: the only honest answer this surface can give — main owns the worker registry, not the renderer.
let liveSessionIds = [];

/** How many live panes are workers, i.e. not the conductor's own pane. */
function liveWorkerPaneCount() {
  const cid = conductor && conductor.paneId;
  return liveSessionIds.filter((id) => id !== cid).length;
}
const paneBadges = new Map(); // paneId -> chrome preview (Phase 16B picker selection)
let lastPicker = null;        // last fetched picker model {ok, picker, error}
let pickerTarget = null;      // pane id the next picker selection spawns into (null = a new pane)
let lastStatusModel = null;   // last status-bar model, so a pane's frontier n/2 reads the live count
let voiceModel = null;        // last voice-IN state {control:{engine}, badge, summary} (Phase 16E .wire)

const Terminal = window.Terminal;
const FitAddon = (window.FitAddon && window.FitAddon.FitAddon) || window.FitAddon;

function ensurePane(id) {
  if (terms.has(id)) return terms.get(id);
  const el = document.createElement("div");
  el.className = "pane";
  el.dataset.id = id;
  el.innerHTML = `
    <div class="bar">
      <span class="pnum"></span><span class="title"></span><span class="cbadge"></span><span class="cdispatch"></span><span class="mbadge"></span><span class="state"></span>
      <span class="spacer"></span>
      <button data-act="model" class="cmodel" title="Pick this pane's model (provider × model × role)">model ▾</button>
      <button data-act="ptt" class="cptt" title="Push to talk — speak to the conductor (STT-only, no TTS)">🎤 talk</button>
      <span class="cvoice" title="voice-IN engine + last utterance"></span>
      <span class="cturn" title="supervisor-owned voice turn"></span>
      <button data-act="clive" class="clive" title="Run the live interactive conductor session in this pane (governed spawn)">▶ live</button>
      <button data-act="succeed" class="csucc" title="Resume → Select conductor model (succession)">Resume→Select</button>
      <button data-act="pin">pin</button>
      <button data-act="min">_</button>
      <button data-act="max">▢</button>
      <button data-act="close" class="warn">✕</button>
    </div>
    <div class="term"></div>`;
  grid.appendChild(el);

  const term = new Terminal({ fontFamily: "ui-monospace, monospace", fontSize: 13, cursorBlink: true,
    theme: { background: "#000000" } });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.open(el.querySelector(".term"));
  fit.fit();
  // typed input is routed to exactly this pane's session (never crosses panes)
  term.onData((data) => S.input(id, data));
  term.onResize(({ cols, rows }) => S.resize(id, cols, rows));

  // Phase 16A: focus the terminal on click so keystrokes reach THIS pane's session (the old
  // renderer routed the focus MODEL but never gave the xterm textarea DOM focus — a "cannot type"
  // cause). Focus first, then record the model focus.
  el.addEventListener("mousedown", () => { term.focus(); S.focus(id); });
  el.querySelector('[data-act="pin"]').addEventListener("click", (e) => { e.stopPropagation(); S.pin(id, !el.classList.contains("pinned")); });
  el.querySelector('[data-act="min"]').addEventListener("click", (e) => { e.stopPropagation(); S.minimize(id); });
  el.querySelector('[data-act="max"]').addEventListener("click", (e) => { e.stopPropagation(); el.classList.contains("maximized") ? S.restore(id) : S.maximize(id); });
  el.querySelector('[data-act="close"]').addEventListener("click", (e) => { e.stopPropagation(); S.close(id); });
  // Resume→Select succession (§13.7): reachable from the conductor pane's chrome only. Forwards the
  // operator's request to the governed Python succession path — the renderer self-authorizes nothing.
  el.querySelector('[data-act="succeed"]').addEventListener("click", (e) => { e.stopPropagation(); S.succeedConductor(); });
  // Phase 17A `.pty`: the explicit pane-1 control that runs the REAL interactive conductor session
  // (the shell also attempts it on launch). The renderer only ASKS — the governed Python ticket
  // authorizes and the supervised session manager spawns; a refusal comes back with its reason.
  el.querySelector('[data-act="clive"]').addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      const res = await S.launchConductor();
      if (res && !res.launched) console.warn(`conductor launch: ${res.reason || "refused"}`);
    } catch (err) { console.warn(`conductor launch failed: ${(err && err.message) || err}`); }
  });
  // Push-to-talk (§13.5; Phase 16E `.wire`): reachable from the conductor pane's chrome only. CAPTURES
  // one utterance through the REAL Python ConductorVoiceBridge — the transcription + the
  // chat-vs-propose-vs-clarify routing are Python-side, so the renderer self-authorizes nothing: a CHAT
  // is delivered into the conductor input by main, a protected action is queued for approval, a
  // low-confidence transcript clarifies. Then it refreshes the voice badge (engine + last outcome). STT
  // only: there is no speak-back control (I-V2/D-VOICE-02, no TTS).
  // Phase 17C `.mic`: the button is now PUSH-TO-TALK for real. Press and HOLD opens the microphone;
  // release encodes the operator's speech to 16 kHz mono WAV and sends the BYTES to main, which
  // transcribes them with real WSL Parakeet and routes the result exactly as before. A click that is
  // not a hold (or a host with no usable microphone) falls back to the scripted stand-in ref so the
  // routing affordance still works — and says so in the button, never silently.
  const pttEl = el.querySelector('[data-act="ptt"]');
  wirePushToTalk(pttEl);
  // Phase 17C `.probe` (U74): the engine badge is the operator's RE-PROBE control. Directive §16 track
  // 17C requires "re-probe on demand" — an API with no affordance is not on demand. Clicking the badge
  // re-takes the WSL NeMo probe now, which is exactly what an operator who has just finished the NeMo
  // install needs, and what a stale/failed answer needs. Main rate-limits it; the renderer decides
  // nothing (invariant 1) and the badge repaints from main's pushed state, never from a local guess.
  const voiceBadgeEl = el.querySelector(".cvoice");
  if (voiceBadgeEl) {
    voiceBadgeEl.addEventListener("click", async (e) => {
      e.stopPropagation();
      try { await S.probeVoice({ force: true }); } catch { /* fail-closed; the push carries the truth */ }
      await refreshVoice();
    });
  }
  // Per-pane model picker (Phase 16B): open the picker targeting THIS pane. Selecting an option
  // dispatches the governed pane_node_spawn intent for this pane (records + previews the badge).
  el.querySelector('[data-act="model"]').addEventListener("click", (e) => { e.stopPropagation(); openPicker(id); });

  const rec = { term, fit, el, feed: new PaneFeed() };
  terms.set(id, rec);
  // Phase 16A: (re)attach the byte-exact scrollback BEFORE going live. The session survives in
  // main (RingBuffer, invariant 27); this replays it so a freshly-(re)created view is never blank.
  // Live chunks that arrive while this awaits are buffered by the feed and flushed in seq order,
  // dropping any already inside the snapshot — no gap, no duplication.
  attachFeed(id, rec);
  return rec;
}

// Replay scrollback then release the buffered live stream (Phase 16A). Fail-soft: a pane with no
// session (the conductor placeholder) or an unavailable channel yields {text:"",seq:-1} and the
// feed simply flushes whatever it buffered.
async function attachFeed(id, rec) {
  let sb = { text: "", seq: -1 };
  try { sb = await S.scrollback(id); } catch { /* channel down / no session — flush buffered only */ }
  if (!terms.has(id) || terms.get(id) !== rec) return; // pane was disposed while we awaited
  const writes = rec.feed.attach((sb && sb.text) || "", (sb && Number.isFinite(sb.seq)) ? sb.seq : -1);
  for (const w of writes) rec.term.write(w);
  try { rec.fit.fit(); } catch { /* not attached */ }
  if (id === focusedId) rec.term.focus();
}

/** Apply chrome only — never resizes/reflows (Plan §10.2). Safe to call on every state push. */
function applyChrome(id) {
  const rec = terms.get(id);
  if (!rec) return;
  const info = meta.get(id) || {};
  rec.el.classList.toggle("focused", id === focusedId);
  rec.el.classList.toggle("maximized", !!maximizedId && id === maximizedId);
  const n = String(id || "").match(/(\d+)$/);
  const pnum = rec.el.querySelector(".pnum");
  if (pnum) pnum.textContent = n ? "#" + n[1] : "";
  rec.el.querySelector(".title").textContent = info.title || id;
  const stEl = rec.el.querySelector(".state");
  stEl.textContent = info.sessionState || "";
  stEl.className = "state " + (info.sessionState || "");
  applyConductorChrome(id, rec);
  applyModelBadge(id, rec);
}

// ---- per-pane model badge (Phase 16B; Phase 17B `.spawn`): the picker-SELECTED model + role + n/2
// (frontier) or residency (local), plus the pane's LAUNCH STATE — which since 17B is a real one: a
// selection now launches a governed session, so the badge says `live` for a running node and names
// the outcome otherwise (refused / failed / exited). It said `selected` unconditionally, which
// under-claimed a running session and never changed when one ended (spec-audit MINOR-7,
// invariant 27). The state text comes from the chrome main pushed for that pane and is never
// synthesised here; n/2 is read from the SAME live governor status the status bar shows.
function applyModelBadge(id, rec) {
  const badgeEl = rec.el.querySelector(".mbadge");
  if (!badgeEl) return;
  const c = paneBadges.get(id);
  if (!c) { badgeEl.className = "mbadge"; badgeEl.textContent = ""; return; }
  let tail = "";
  if (c.locality === "frontier") {
    const inUse = statusInUse(c.provider);
    const cap = (c.subscription && c.subscription.allowance) || "?";
    tail = ` · ${inUse == null ? "?" : inUse}/${cap}`;
  } else if (c.residency) {
    tail = ` · ${c.residency}`;
  }
  badgeEl.className = "mbadge show";
  // a frontier slug is an unverified operator label until a live smoke (invariant 3) — mark it so
  const state = c.node_state === "running" ? "live"
    : c.node_state === "launch_refused" ? "refused"
      : c.node_state === "launch_failed" ? "failed"
        : c.node_state === "session_terminating" ? "terminating"
          : c.node_state === "session_killed" ? "ended (killed)"
          : c.node_state === "session_exited" ? "ended"
            // a pane restored from a snapshot the last shell died before it could revise: it WAS
            // running, it is not now, and the recovery fold rewrote it rather than let this badge
            // read `live` for a dead process (invariant 3; see layout-reconstruct)
            : c.node_state === "session_interrupted" ? "interrupted (last run)"
              : c.node_state === "launch_unavailable" ? "unavailable"
                : "selected";
  const operationalRole = c.operational_role ? ` · ${c.operational_role}` : "";
  const task = c.task_id ? ` · ${c.task_status || "ASSIGNED"}` : "";
  badgeEl.textContent = `${c.model_label}${c.model_verified ? "" : " (unverified)"} · ${c.role}`
    + `${operationalRole}${tail} · ${state}${task}`;
  badgeEl.title = c.task_id ? `task ${c.task_id} · ${c.progress_state || c.task_status || "assigned"}`
    : (c.launch_reason || c.governed_spawn || "");
}

// Look up the live in-use count for a provider from the last status-bar model (the same governor
// read the status bar renders). Returns null when the count is not readable (fail-closed).
function statusInUse(provider) {
  const rows = (lastStatusModel && Array.isArray(lastStatusModel.rows)) ? lastStatusModel.rows : [];
  const r = rows.find((x) => x.provider === provider);
  return r && typeof r.inUse === "number" ? r.inUse : null;
}

// ---- conductor-first pane chrome (§13/§12.4): CONDUCTOR badge + Resume→Select control ----------
// Only the conductor pane (main's pane 1) shows the model badge + succession button; every other
// pane hides them. The badge shows the SELECTION label (fable-5), marked unverified until a live
// reply — never a fabricated checkpoint id (invariant 3).
function applyConductorChrome(id, rec) {
  const isConductor = !!(conductor && conductor.paneId === id);
  rec.el.classList.toggle("conductor", isConductor);
  const badgeEl = rec.el.querySelector(".cbadge");
  const dispatchEl = rec.el.querySelector(".cdispatch");
  const succEl = rec.el.querySelector(".csucc");
  const pttEl = rec.el.querySelector(".cptt");
  const liveEl = rec.el.querySelector(".clive");
  const turnElOff = rec.el.querySelector(".cturn");
  if (!isConductor) { badgeEl.textContent = ""; badgeEl.className = "cbadge"; if (dispatchEl) { dispatchEl.textContent = ""; dispatchEl.className = "cdispatch"; } succEl.style.display = "none"; if (pttEl) pttEl.style.display = "none"; if (liveEl) liveEl.style.display = "none"; if (turnElOff) { turnElOff.style.display = "none"; turnElOff.textContent = ""; turnElOff.className = "cturn"; } return; }
  const b = conductor.badge || {};
  const shownModel = b.displayName || b.model || "—";
  const provider = b.provider ? ` · ${b.provider}` : "";
  const slug = b.modelSlug ? ` · ${b.modelSlug}` : "";
  badgeEl.textContent = `CONDUCTOR · ${shownModel}${provider}${slug}`
    + `${b.verified ? "" : " (unverified)"}${b.isFallback ? " (fallback)" : ""}`
    + ` · ${conductor.nodeState || ""}`;
  badgeEl.className = "cbadge" + (b.verified ? " verified" : " unverified");
  // Phase 16C .dispatch: the governed dispatch line (assignments by descriptor, accepted count, legs
  // verbatim, the OWED live-worker leg — U58). Sourced from Python (conductor.dispatch); never a literal.
  if (dispatchEl) {
    const d = conductor.dispatch || {};
    dispatchEl.textContent = d.text || "";
    dispatchEl.className = "cdispatch" + (d.dispatched ? " ran" : " unavailable") + (d.owed ? " owed" : "");
  }
  // Phase 17A `.pty`: the live-session control. Hidden while a live session is RUNNING (there is
  // nothing to start — one governed terminal per pane); shown, with the last honest reason as its
  // tooltip, whenever pane 1 is dark. It never reports a launch the shell did not make.
  if (liveEl) {
    const l = (conductor.launch || {});
    liveEl.style.display = conductor.live ? "none" : "";
    liveEl.textContent = l.state === "launching" ? "starting…" : "▶ live";
    liveEl.disabled = l.state === "launching";
    liveEl.title = l.reason
      ? `last attempt: ${l.reason}`
      : "Run the live interactive conductor session in this pane (governed spawn)";
  }
  // the succession control is only shown when the affordance says it is reachable (fail-closed)
  succEl.style.display = conductor.succession && conductor.succession.available ? "" : "none";
  // the push-to-talk mic (§13.5) is reachable from the conductor chrome (voice-IN only; no TTS)
  if (pttEl) pttEl.style.display = "";
  // Phase 16E `.wire`: the VISIBLE STT-engine indicator + last-utterance badge. The engine is ALWAYS
  // shown ("mock engine" until the WSL Parakeet path lands — never a silent pretend-to-hear); after a
  // capture the last outcome (delivered / queued / repeat) rides alongside it. Fail-closed to a mock tag.
  const voiceEl = rec.el.querySelector(".cvoice");
  if (voiceEl) {
    const vm = voiceModel;
    const eng = (vm && vm.control && vm.control.engine) || { mock: true, label: "mock engine" };
    // Phase 16E `.real`: the indicator's label already encodes the three states (real / "<name> ready"
    // when the real stack is installed but a stand-in used the mock / "mock engine"); trust it.
    const engTag = eng.label || (eng.mock ? "mock engine" : (eng.name || "STT engine"));
    const badge = vm && vm.badge;
    const last = badge && badge.ok ? ` · ${badge.label}` : (badge ? " · not understood — repeat" : "");
    voiceEl.textContent = `🎙 ${engTag}${last}`;
    // Phase 17C `.probe` (U74): "probing…" gets its OWN class. Before this, `mock ? mock : real` styled
    // an unanswered probe as `real` — the label said one thing and the colour said another.
    voiceEl.className = "cvoice" + (eng.probing ? " probing" : eng.mock ? " mock" : " real");
    voiceEl.title = `${eng.hint || (eng.mock ? "voice transcription is a MOCK engine — see docs/OPERATOR_NEMO_INSTALL.md" : "")}`
      + " — click to re-check now";
  }
  // Phase 17C `.disarm` (U166 / invariant 27): while a supervisor-owned voice turn is armed, this
  // session's CLI is denied every tool call AND the operator's own typed prompts are blocked. That
  // state was invisible and, until this sub-step, permanent — a live pane that had simply stopped
  // answering, with an undocumented chord as the only way back. It is drawn here from main's own
  // folded indicator (the renderer decides nothing), and it carries the recovery main implements.
  const turnEl = rec.el.querySelector(".cturn");
  if (turnEl) {
    const ti = (voiceModel && voiceModel.turnIndicator) || null;
    const show = !!(ti && ti.show);
    turnEl.style.display = show ? "" : "none";
    turnEl.textContent = show ? `⛔ ${ti.label}` : "";
    turnEl.className = "cturn" + (show ? ` show ${ti.phase}` : "");
    turnEl.title = show ? (ti.hint || "") : "";
  }
}

// ---- Phase 17C `.mic`: push-to-talk over the real microphone ------------------
// One recorder for the shell (there is one operator and one conductor). `pttLabel` is the operator's
// only feedback while the device is open and while a 20 s WSL transcription runs, so it always states
// what is actually happening — including, and especially, when it failed (U133 is the main-side half of
// the same problem; this is the renderer's).
let micRecorder = null;
let pttBusy = false;

function pttLabel(el, text, cls) {
  if (!el) return;
  el.textContent = text;
  el.className = `cptt${cls ? ` ${cls}` : ""}`;
}

/**
 * Press-and-hold wiring.
 *
 * THE ONE RULE, and it is absolute: **this control never routes anything but the operator's own
 * recorded speech.** An earlier revision of this function fell back to the scripted stand-in ref
 * whenever capture failed, on the theory that a visible "no mic" label made the substitution honest.
 * Both mandatory reviews of this unit found that independently and they were right: `captureVoice(null)`
 * resolves to `DEFAULT_AUDIO_REF` → the MockSTT script → `"show status"` → a CHAT verdict → a real write
 * into the conductor's ConPTY. So an operator who pressed, SPOKE, and happened to have a muted mic would
 * have had a command they never uttered typed into a live conductor session, with a transient label as
 * the only sign. That is the exact pretend-to-hear this whole track exists to eliminate (invariant 3),
 * and it puts unauthored content in the command path (invariant 1).
 *
 * So: a capture that fails is REPORTED and routes NOTHING. The stand-in path still exists — the
 * indicator poll and the honesty-negative self-check legs need a transcript without a microphone — but
 * it is no longer reachable from the operator's talk button.
 *
 * Press-and-hold works from the pointer AND the keyboard. The button is a real `<button>`, so it is
 * focusable; Enter/Space dispatch `click` with no pointer events at all, which is why keydown/keyup are
 * wired explicitly rather than left to a `click` handler that could only ever fire after the hold ended.
 */
function wirePushToTalk(el) {
  if (!el) return;
  const idle = () => pttLabel(el, "🎤 talk", "");
  // Set ONLY by a real `begin`. Without it a stray `pointerup` — released over this button after
  // dragging a divider or selecting text in a pane — reached `end` and routed an utterance.
  let held = false;

  const begin = async (e) => {
    if (e) e.stopPropagation();
    if (pttBusy || held || (micRecorder && micRecorder.recording)) return;
    held = true;
    if (!window.SovereignMic) { pttLabel(el, "🎤 no mic", "mock"); return; }
    try {
      micRecorder = micRecorder || new window.SovereignMic.MicRecorder();
      await micRecorder.start();
      // The release may have already happened: `getUserMedia` is asynchronous and a quick tap resolves
      // `end` first, which finds nothing recording and returns. Without this the device would then
      // open behind it and stay open — a HOT MICROPHONE with no press holding it, and the chrome
      // reading "listening…" indefinitely. Found by the receipt leg added for the stand-in defect.
      if (!held) { micRecorder.cancel(); idle(); return; }
      pttLabel(el, "🔴 listening…", "listening");
    } catch (err) {
      // permission denied / no device / no Web Audio. Say so and STOP — nothing is routed.
      pttLabel(el, "🎤 no mic", "mock");
      console.warn(`push-to-talk: ${(err && err.message) || err}`);
      micRecorder = null;
    }
  };

  const end = async (e) => {
    if (e) e.stopPropagation();
    if (!held || pttBusy) return;      // no matching press ⇒ this is not the operator talking
    held = false;
    if (!micRecorder || !micRecorder.recording) {
      // the mic never opened; the label already says why. Route NOTHING.
      pttLabel(el, "🎤 no mic", "mock");
      return;
    }
    let captured = null;
    try {
      captured = micRecorder.stop();
    } catch (err) {
      // a too-short hold, an empty buffer, a device that yielded nothing — all reported, none routed.
      pttLabel(el, `🎤 ${(err && err.message) || "nothing recorded"}`, "mock");
      console.warn(`push-to-talk: ${(err && err.message) || err}`);
      return;
    }
    pttBusy = true;
    // `.close-revalidate` (spec-audit MINOR-8): a hold that ran past MAX_CAPTURE_MS was silently
    // truncated — the recorder reported `capped` and the only caller dropped it, so the operator saw a
    // normal transcription of the first minutes of what they said. The cut is now visible.
    if (captured.capped) {
      pttLabel(el, "⏳ transcribing (hold was cut short)…", "listening");
      console.warn("push-to-talk: the hold hit the capture cap — only the first part was recorded");
    } else {
      pttLabel(el, "⏳ transcribing…", "listening");
    }
    try {
      // main writes the WAV, runs WSL Parakeet, routes the bridge's verdict, deletes the file.
      const r = await S.captureVoice({ pcm: captured.pcm, sampleRate: captured.sampleRate });
      if (r && r.sourced === false) pttLabel(el, "🎤 voice unavailable", "mock");
    } catch (err) {
      pttLabel(el, "🎤 voice unavailable", "mock");
      console.warn(`push-to-talk: ${(err && err.message) || err}`);
    } finally {
      pttBusy = false;
      await refreshVoice();
      // the transient failure labels above are left in place for a beat so they are actually readable;
      // any later repaint restores the idle label.
      setTimeout(() => { if (!held && !pttBusy) idle(); }, 2500);
    }
  };

  const cancel = (e) => {
    if (e) e.stopPropagation();
    if (!held) return;
    held = false;
    if (micRecorder) micRecorder.cancel();
    idle();
  };

  el.addEventListener("pointerdown", begin);
  el.addEventListener("pointerup", end);
  el.addEventListener("pointerleave", end);
  el.addEventListener("pointercancel", cancel);
  // Keyboard press-and-hold, so the control is reachable without a pointing device. `repeat` is
  // ignored: holding a key autorepeats keydown, and each one would otherwise re-enter `begin`.
  el.addEventListener("keydown", (e) => {
    if (e.key !== " " && e.key !== "Enter" || e.repeat) return;
    e.preventDefault();   // stop the browser synthesising a `click` from this activation
    begin(e);
  });
  el.addEventListener("keyup", (e) => {
    if (e.key !== " " && e.key !== "Enter") return;
    e.preventDefault();
    end(e);
  });
  el.addEventListener("blur", cancel);   // focus lost mid-hold: release the device, route nothing
  // A synthetic `click` (no pointer, no key) is NOT an utterance and must not become one.
  el.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); });
}

// Phase 16E `.wire`: pull the voice-IN state (engine indicator + last-utterance badge) and repaint the
// conductor chrome. Fail-closed: a fault leaves the last model (or the default mock indicator) in place.
async function refreshVoice() {
  try { voiceModel = await S.voiceState(); } catch { /* keep last; the default is a visible mock tag */ }
  if (conductor && conductor.paneId) applyChrome(conductor.paneId);
}

// ---- shell:layout — the ONLY place the grid reflows -------------------------
S.onLayout((plan) => {
  const cells = plan.grid.cells;
  const inGrid = new Set(cells.map((c) => c.id));

  // panes no longer tiled (collapsed to a card, minimized, or destroyed): drop their live view.
  // The session itself survives in main (byte-exact scrollback), so re-expansion reattaches.
  for (const [id, rec] of terms) {
    if (!inGrid.has(id)) { rec.term.dispose(); rec.el.remove(); terms.delete(id); }
  }

  grid.style.gridTemplateColumns = `repeat(${Math.max(1, plan.grid.cols)}, 1fr)`;
  grid.style.gridTemplateRows = `repeat(${Math.max(1, plan.grid.rows)}, 1fr)`;

  // (re)place panes in cell order; P0/P1 keep their double (span-2) cell.
  for (const c of cells) {
    const rec = ensurePane(c.id);
    rec.el.style.gridColumn = c.span === 2 ? "span 2" : "span 1";
    rec.el.classList.toggle("pinned", c.priority === "P0");
    rec.el.dataset.priority = c.priority;
    grid.appendChild(rec.el); // reorder to match the plan
    applyChrome(c.id);
  }

  // right-hand status-card rail: P2 overflow + P3/P4, never P0/P1 (§10.2 hard rule enforced in main).
  rail.innerHTML = plan.cards.length
    ? plan.cards.map((c) => {
        const info = meta.get(c.id) || {};
        // W-36 (R-54): every value here is model- or system-supplied — pane titles come from the
        // launch chrome, from provider/model identifiers, and from `spec.title` on the pane-creation
        // path. `esc()` is defined in this file and was already used by the inspector panels below;
        // these two sinks were simply missed. Escaped at the interpolation rather than at the
        // source, because this is the boundary where the text becomes markup.
        return `<div class="railcard" data-id="${esc(c.id)}" data-priority="${esc(c.priority)}">
          <div class="rc-id">${esc(info.title || c.id)}</div>
          <div class="rc-meta">${esc(c.priority)} · ${esc(info.sessionState || "—")}</div></div>`;
      }).join("")
    : `<div class="rail-empty">no collapsed panes</div>`;
  rail.querySelectorAll(".railcard").forEach((el) => el.addEventListener("click", () => S.focus(el.dataset.id)));

  for (const { fit } of terms.values()) { try { fit.fit(); } catch { /* not attached */ } }
});

// ---- shell:state — chrome/content restyle, no reflow ------------------------
S.onState((state) => {
  focusedId = state.focusedId;
  maximizedId = state.maximizedId;

  meta.clear();
  for (const p of state.visible) meta.set(p.id, { title: p.title, pinned: p.pinned });
  for (const s of state.sessions) {
    const m = meta.get(s.id) || {};
    m.sessionState = s.state;
    meta.set(s.id, m);
  }
  liveSessionIds = state.sessions.map((s) => s.id);
  // F-21: the delegate control is disabled with its reason whenever no worker pane is up, so it
  // has to be re-evaluated on the push that changes that — not only when the bar was built.
  if (window.__sovRefreshDelegate) window.__sovRefreshDelegate();

  for (const id of terms.keys()) applyChrome(id);

  // Phase 16A: keep DOM keyboard focus on the operator's focused pane so typing reaches its session
  // (the focus model is authoritative; the xterm textarea must actually hold focus to emit onData).
  if (focusedId) { const fr = terms.get(focusedId); if (fr) fr.term.focus(); }

  // status bar cards (shell is observable — invariant 27). The supervision card reflects the
  // recovery lifecycle: SUPERVISED (READY) / DEGRADED / RECOVERING, with the supervision epoch.
  const rec = state.recovery || { state: state.supervised ? "SUPERVISED" : "INIT", epoch: 0 };
  const sup = document.getElementById("card-sup");
  sup.textContent = state.supervised ? "READY" : (rec.state === "INIT" ? "DENIED" : rec.state);
  sup.className = "v" + (state.supervised ? "" : " bad");
  renderRecoveryBanner(rec);
  document.getElementById("card-sessions").textContent = String(state.sessions.length);
  document.getElementById("card-focus").textContent = state.focusedId || "—";

  const min = document.getElementById("minimized");
  min.innerHTML = state.minimized.length
    // W-36 (R-54): same sink class as the rail above — a minimized pane's title is the same
    // model-supplied string, rendered through innerHTML.
    ? "minimized: " + state.minimized.map((m) => `<span data-id="${esc(m.id)}">${esc(m.title || m.id)}</span>`).join("")
    : "";
  min.querySelectorAll("span").forEach((s) => s.addEventListener("click", () => S.focus(s.dataset.id)));
});

// ---- recovery banner (directive §9 track 14A) -------------------------------
// Live supervision state rides shell:state.recovery; interrupted sessions from a PRIOR shell run
// arrive once on shell:recovery. Both are surfaced honestly: a lost channel reads DEGRADED and
// blocks new sessions; interrupted sessions are reported for supervised relaunch, never respawned.
let interruptedNotice = null;
function renderRecoveryBanner(rec) {
  const el = document.getElementById("recovery");
  if (rec && rec.state === "DEGRADED") {
    el.className = "show degraded";
    el.textContent = `⚠ control-plane channel LOST — sessions torn down, new sessions blocked (fail-closed). Reconnecting…`;
    return;
  }
  if (rec && rec.state === "RECOVERING") {
    el.className = "show recovering";
    el.textContent = `↻ reconnecting to the control plane — admission stays closed until the channel re-verifies…`;
    return;
  }
  // healthy: show a lingering interrupted-session notice if one is pending, else hide.
  if (interruptedNotice) { el.className = "show interrupted"; el.innerHTML = interruptedNotice; }
  else el.className = "";
}

S.onRecovery((info) => {
  // Phase 15E .recovery: the conductor-first layout was reconstructed on boot (pinned CONDUCTOR
  // pane 1 + reattaching worker panes). Surface it honestly, plus any interrupted sessions that
  // need SUPERVISED relaunch (never auto-respawned).
  const layout = info && info.layout;
  // Phase 16D `.recovery` (U68): restore each worker pane's governed model BADGE from the
  // reconstructed chrome so a restarted shell repaints the exact selection instead of a blank pane
  // (paneBadges starts empty in a fresh renderer). Honest: this is a RECORDED selection restored,
  // and no live node is claimed — but that is the FOLD's doing, not this loop's. It used to say
  // "node_state stays awaiting-governed-spawn", which stopped being true at 17B `.spawn`: a
  // snapshot written by a shell that was killed carries `running`, and `applyModelBadge` renders
  // `running` as **live**. `reconstructLayout` now rewrites a stale live state to
  // `session_interrupted` before it ever reaches here (invariants 3/27).
  if (layout && Array.isArray(layout.panes)) {
    for (const w of layout.panes) {
      if (w && w.paneId && w.chrome && w.chrome.model_label) {
        paneBadges.set(w.paneId, w.chrome);
        if (terms.has(w.paneId)) applyChrome(w.paneId);
      }
    }
  }
  const list = (info && info.interrupted) || (layout ? layout.interrupted || [] : []);
  const relaunchIds = list.map((s) => (typeof s === "string" ? s : s.id));
  if (!relaunchIds.length && !layout) { interruptedNotice = null; return; }
  const parts = [];
  if (layout) {
    parts.push(`✓ conductor-first layout restored — CONDUCTOR pane 1 pinned, ${esc(layout.summary.workers)} worker pane(s), `
      + `admission ${layout.admissionOpen ? "OPEN" : "SHUT (awaiting a verified channel)"}`);
  }
  if (relaunchIds.length) {
    parts.push(`<span class="r-relaunch">↺ ${relaunchIds.length} pane(s)/session(s) need supervised relaunch (no naked re-spawn): `
      + relaunchIds.map((id) => esc(String(id))).join(", ") + `</span>`);
  }
  interruptedNotice = parts.join(" · ");
  const el = document.getElementById("recovery");
  el.className = "show interrupted";
  el.innerHTML = interruptedNotice;
});

S.onData((id, data, seq) => {
  const rec = terms.get(id);
  if (!rec) return; // no view for this pane right now; scrollback replays it on next (re)attach
  // While (re)attaching, the feed buffers the chunk (returns null); once scrollback is replayed it
  // passes straight through. This is what stops early PTY output (the banner) being dropped.
  const w = rec.feed.live(seq, data);
  if (w !== null) rec.term.write(w);
});

S.onLog((line) => console.log(line));

// conductor-first pane (§13/§12.4): store the CONDUCTOR badge + Resume→Select state and restyle the
// panes that already exist (chrome-only; no reflow). The conductor pane may not be built yet on the
// first push — applyChrome re-reads `conductor` when the pane's view is created by the layout plan.
S.onConductor((state) => {
  conductor = state;
  for (const id of terms.keys()) applyChrome(id);
  refreshVoice();
  // F-21: `conductor.live` gates the delegate control, so this push must re-evaluate it too.
  if (window.__sovRefreshDelegate) window.__sovRefreshDelegate();
});
// Phase 17C `.probe` (U74): main pushes the voice state when the ASYNCHRONOUS STT probe settles. The
// badge flips from "probing…" to the real answer with no operator action — the probe answers on its own
// schedule (7–18 s here), and a chrome that only repainted on click would keep showing a stale question.
S.onVoice((state) => {
  if (!state) return;
  voiceModel = state;
  if (conductor && conductor.paneId) applyChrome(conductor.paneId);
});
// Phase 17B `.spawn`: main revised a worker pane's governed chrome (its session ended) — repaint the
// badge from what main sent, never from what this renderer last assumed (invariant 3/27).
S.onPaneChrome((id, chrome) => {
  if (!id || !chrome) return;
  paneBadges.set(id, chrome);
  if (terms.has(id)) applyChrome(id);
});

document.getElementById("btn-new").addEventListener("click", async () => {
  // G20/S-11: "+ Terminal" creates a session CONTAINER - no process, no PTY.
  try { await S.createEmptyPane({}); }
  catch (e) { console.error("empty pane refused:", e); }
});

// ---- G25: persistent Conductor typing surface ------------------------------
function workspaceViewNotice(turn) {
  return turn && turn.dir === "out" && turn.workspace_view
    ? String(turn.workspace_view.notice || "") : "";
}
function workspaceViewSummary(turn) {
  if (!workspaceViewNotice(turn)) return "";
  const state = turn.workspace_view.state;
  if (state === "journal_unavailable") return "Journal unavailable";
  if (state === "attached_empty") return "View attached but empty";
  if (state === "budget_unmeasurable") return "Sent · no context (budget unmeasured)";
  if (state === "attached") return turn.workspace_view.truncated ? "View TRUNCATED" : "View attached";
  return "No view · /workspace";
}
(function wireConductorBar() {
  const input = document.getElementById("conductor-input");
  const sendBtn = document.getElementById("conductor-send");
  const list = document.getElementById("conductor-transcript");
  const transcriptToggle = document.getElementById("conductor-transcript-toggle");
  if (!input || !sendBtn || !list || !transcriptToggle) {
    // THE WHOLE BAR WAS DEAD, and had been since G25 shipped. `index.html` loads this script at
    // line 236 and declares `#conductor-bar` at line 281 — the markup this block wires does not
    // exist yet when the block runs, so all three lookups returned null and the guard below
    // returned every time. Nothing here was ever attached: not the submit handler, not the
    // transcript subscription, not the delegate control added on top of it later.
    //
    // The guard itself is right and stays — a surface that cannot find its elements must not
    // half-wire itself. What was missing is that "not yet" is not "not at all": during parsing the
    // elements are merely still ahead of us in the document. Re-run once the DOM is complete, and
    // keep returning for the genuinely-absent case (a harness that loads this script with no bar).
    //
    // Found only after the operator pressed Delegate five times and the durable log stayed silent:
    // every static check passed because the code IS correct, and none of it ever ran.
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", wireConductorBar, { once: true });
    }
    return;
  }

  // Both explicit toggles and other bar height changes refit the existing terminal addons.
  let fitPending = false;
  function refitConductorTerminals() {
    if (fitPending) return;
    fitPending = true;
    requestAnimationFrame(() => {
      fitPending = false;
      for (const { fit } of terms.values()) { try { fit.fit(); } catch { /* pane may be closing */ } }
    });
  }
  const conductorBar = document.getElementById("conductor-bar");
  if (conductorBar && typeof ResizeObserver === "function") {
    const barResize = new ResizeObserver(refitConductorTerminals);
    barResize.observe(conductorBar);
  }

  let transcriptCollapsed = true;
  let transcriptResults = 0, transcriptRefusals = 0, transcriptNotices = 0, transcriptLines = 0;
  let transcriptChatRefusals = 0, transcriptChatNotices = 0;
  let latestWorkspaceSummary = "";
  // A single optional preference, never journal authority. Storage denial keeps the launch default.
  try { transcriptCollapsed = localStorage.getItem("conductor-transcript-state") !== "expanded"; }
  catch { /* default collapsed */ }
  function updateTranscriptSummary() {
    transcriptToggle.textContent = (latestWorkspaceSummary ? latestWorkspaceSummary + " | " : "")
      + `${transcriptResults} results | ${transcriptRefusals + transcriptChatRefusals} refused | `
      + `${transcriptNotices + transcriptChatNotices} notices | Transcript (${transcriptLines} lines) | `
      + (transcriptCollapsed ? "Expand: more details + markers" : "Collapse: details + markers below");
    transcriptToggle.title = transcriptToggle.textContent;
  }
  function setTranscriptCollapsed(collapsed) {
    transcriptCollapsed = collapsed;
    list.hidden = collapsed;
    transcriptToggle.setAttribute("aria-expanded", String(!collapsed));
    updateTranscriptSummary();
    refitConductorTerminals();
  }
  transcriptToggle.addEventListener("click", () => {
    setTranscriptCollapsed(!transcriptCollapsed);
    try { localStorage.setItem("conductor-transcript-state", transcriptCollapsed ? "collapsed" : "expanded"); }
    catch { /* preference persistence is optional */ }
  });
  setTranscriptCollapsed(transcriptCollapsed);

  let lastTranscriptTurns = [];
  const delegationTurns = [];
  function render(turns) {
    lastTranscriptTurns = turns;
    list.textContent = "";
    const combined = [...turns, ...delegationTurns].sort((a, b) =>
      String(a.utc || "").localeCompare(String(b.utc || "")));
    for (const turn of combined) {
      if (turn.row) { list.appendChild(turn.row); continue; }
      const row = document.createElement("div");
      row.className = "turn " + (turn.dir === "in" ? "in" : turn.dir === "sys" ? "sys" : "out");
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = "[" + String(turn.utc || "").replace("T", " ").slice(0, 19) + "] "
        + (turn.dir === "in" ? "Conductor:" : turn.dir === "sys" ? "system:" : "you:");
      const body = document.createElement("span");
      body.textContent = " " + String(turn.text || "");
      row.appendChild(who);
      row.appendChild(body);
      const notice = workspaceViewNotice(turn);
      if (notice) {
        const contextLine = document.createElement("div");
        contextLine.className = "readfrom";
        contextLine.textContent = notice;
        row.appendChild(contextLine);
      }
      list.appendChild(row);
    }
    const latestOut = [...turns].reverse().find(t => t.dir === "out");
    latestWorkspaceSummary = workspaceViewSummary(latestOut);
    const contextNotice = document.getElementById("conductor-context-notice");
    if (contextNotice) contextNotice.textContent = workspaceViewNotice(latestOut);
    transcriptChatRefusals = turns.filter(t => t.dir === "out" && t.error && t.submitted !== true).length;
    transcriptChatNotices = turns.filter(t => t.dir === "sys").length;
    transcriptLines = combined.length;
    updateTranscriptSummary();
    list.scrollTop = list.scrollHeight;
  }

  S.onConductorTranscript(render);

  document.getElementById("conductor-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    try { await S.sendOperatorText(text); }
    catch (e) { console.error("operator text refused:", e); }
  });

  // ---- EPC-03 / SW-ORCH-001 F-21: the DELEGATE affordance -----------------------------------
  //
  // `runObjective` has been implemented, registered on `conductor:run-objective`, and exposed in
  // the preload since EPC-03. Nothing in this renderer ever called it — the only reference was
  // `channel-sweep.js`, a channel-closure probe — so the loop main.js describes as joined had no
  // operator-reachable entry point, and `delegateToPane` sat wired and uninvoked. That is the
  // whole of F-21: the policy was right and the button was missing.
  //
  // EXPLICIT, NOT AUTOMATIC, and that is preserved deliberately. This is a separate button with
  // `type="button"`, so Enter in the composer still SENDS. Most messages are conversation, and
  // decomposing each one would spend model time on the operator's behalf without being asked.
  //
  // It adds no delegation semantics. Every governed decision — whether a dispatch runs, which
  // node an assignment names, whether a pane write is permitted — stays in main and Python. This
  // reads the operator's text, calls the existing channel, and paints what comes back.
  const delegateBtn = document.getElementById("conductor-delegate");
  const whyEl = document.getElementById("conductor-delegate-why");
  let delegateInFlight = false;

  /** Why the control is unavailable right now, or null. Derived from state the renderer already
   *  holds — never a guess, and never a reason invented here. */
  function delegateBlockedReason() {
    // Each reason names the REMEDY, not just the condition. "the conductor is not running" is
    // true and useless; the operator's next question is always "so what do I press?", and the
    // answer is knowable from this state. The deferred-conductor case in particular is easy to
    // mistake for a broken control: pane 1 exists and looks ready, but `session deferred
    // (option C)` means nothing spawned yet because no message has been sent to it.
    if (delegateInFlight) return "a delegation is already in flight — wait for it to finish";
    if (!conductor || conductor.live !== true) {
      return "the conductor is not running — send it a message with Send, or press ▶ live in "
        + "pane 1, then delegate";
    }
    if (liveWorkerPaneCount() < 1) {
      return "no live worker pane is registered — open a pane and pick a model for it first";
    }
    return null;
  }

  function refreshDelegateControl() {
    if (!delegateBtn) return;
    const why = delegateBlockedReason();
    // DELIBERATELY NOT `delegateBtn.disabled`. A disabled button dispatches no click event, so the
    // handler below — including its refusal line — never runs, and pressing the control produces
    // absolutely nothing. That is what the operator hit: "I put two plus two in the objective and
    // press delegate, but nothing happens", with the conductor unstarted and the reason parked in
    // a title attribute. §7.4 asks for the reason STATED; a tooltip is not stated, and silence is
    // the one answer a governed surface must never give. The control stays clickable, carries
    // `aria-disabled` for assistive tech, and the reason is rendered beside it.
    delegateBtn.setAttribute("aria-disabled", why !== null ? "true" : "false");
    delegateBtn.title = why
      ? `Delegate unavailable — ${why}`
      : "Run this message as an OBJECTIVE: governed dispatch, then delegate to the live worker panes";
    if (whyEl) whyEl.textContent = why ? `— ${why}` : "";
  }
  // Re-evaluated on every state and conductor push, so the control reflects the shell rather than
  // whatever was true when the bar was built.
  window.__sovRefreshDelegate = refreshDelegateControl;
  refreshDelegateControl();

  function line(cls, text, refused = false) {
    if (refused) transcriptRefusals += 1;
    if (cls === "warn" || cls === "bad") transcriptNotices += 1;
    const row = document.createElement("div");
    row.className = "turn sys dg";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = "Conductor workspace · observed: ";
    row.appendChild(who);
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = text;
    row.appendChild(span);
    delegationTurns.push({ utc: new Date().toISOString(), row });
    if (delegationTurns.length > 200) delegationTurns.shift();
    render(lastTranscriptTurns);
    return row;
  }

  const clearBtn = document.getElementById("btn-clear");
  if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
      const ok = window.confirm("Clear starts a new session. Live worker terminals will be torn down. The journal is kept.");
      if (ok !== true) return;
      const cid = conductor && conductor.paneId;
      const ids = [...terms.keys()].filter((id) => id !== cid);
      const failed = [];
      for (const id of ids) {
        try { await S.close(id); }
        catch { failed.push(id); }
      }
      try { await S.runObjective({ options: { new_session: true } }); }
      catch { /* rotation uses the existing objective channel; teardown used pane:close */ }
      transcriptResults = 0; transcriptRefusals = 0; transcriptNotices = 0; transcriptLines = 0;
      transcriptChatRefusals = 0; transcriptChatNotices = 0;
      lastTranscriptTurns = [];
      delegationTurns.length = 0;
      setTranscriptCollapsed(true);
      try { localStorage.setItem("conductor-transcript-state", "collapsed"); }
      catch { /* preference persistence is optional */ }
      render([]);
      if (failed.length) line("warn", "Clear partial: panes that would not tear down: " + failed.join(", "));
      refitConductorTerminals();
    });
  }

  function renderDelegationResult(res) {
    transcriptResults += (res && res.delegations || []).filter(d => d.answered === true).length;
    line("warn", "source: observed_pane_output; self_published: false; U58 OWED");
    if (!res || res.ok !== true) {
      // A governed non-dispatch is a well-formed answer with a reason, not an error. Surface it
      // verbatim (s7.6) — never collapsed into "delegation failed".
      line("warn", `not dispatched — ${(res && res.reason) || "no reason reported"}`, true);
      return;
    }
    line("", `objective dispatched — ${res.assigned} assignment(s), ${res.answered} answered`);
    for (const d of res.delegations || []) {
      const node = d.node_id || "(unnamed node)";
      if (d.journal_error) line("warn", d.journal_error);
      if ((d.candidate && d.candidate.truncated) || (d.observation && d.observation.truncated)) {
        line("warn", `  ${node}: TRUNCATED observed pane output`);
      }
      if (d.candidate) line("warn", `  ${node}: redactions=${d.candidate.redactions || 0}; `
        + `kinds=${JSON.stringify(d.candidate.redaction_kinds || [])}`);
      if (d.refused) {
        line("bad", `  ${node}: pane write REFUSED — ${d.refused.reason}`, true);
        continue;
      }
      if (d.delivered !== true) {
        line("warn", `  ${node}: not delivered — ${d.reason || "no reason reported"}`, true);
        continue;
      }
      if (d.answered !== true) {
        line("warn", `  ${node}: delivered, no answer — ${d.reason || "the pane produced nothing"}`);
        continue;
      }
      const row = line("node", `  ${node} answered:`);
      const body = document.createElement("div");
      body.textContent = "    " + String((d.candidate && d.candidate.content) || "").trim();
      row.appendChild(body);
      // s7.5. `self_published:false` / `source:"observed_pane_output"` are the two fields that keep
      // this honest, and they must survive to the surface: a candidate the shell READ off a screen
      // is not a candidate the node ASSERTED, and a reviewer looking at this pane must be able to
      // tell which one they are reading.
      if (d.candidate && d.candidate.self_published === false) {
        const note = document.createElement("div");
        note.className = "readfrom";
        note.textContent = `    ↳ read from the pane's output (self_published: false, source: `
          + `${d.candidate.source}) — weaker evidence than the node's own publication`;
        row.appendChild(note);
      }
    }
    // The OWED live-worker leg is not discharged by a delegation and keeps saying so (s7.7).
    if (res.live_workers_owed && res.live_workers_owed.owed === true) {
      line("warn", `  live worker leg still OWED (${res.live_workers_owed.issue})`);
    }
  }

  delegateBtn.addEventListener("click", async () => {
    const why = delegateBlockedReason();
    if (why) { line("warn", `delegate unavailable — ${why}`, true); return; }
    const text = input.value.trim();
    if (!text) {
      // The empty box is not an edge case here, it is the COMMON mistake: the Delegate control
      // reads the same field as Send, and an operator looking for a separate "objective" line
      // presses Delegate against an empty box. Saying so in the strip was not enough — the strip
      // is above the composer and easy to miss. Put the cursor where the text has to go, so the
      // answer is where the operator is already looking.
      line("warn", "delegate needs an objective — type it in the message box below, then press "
        + "Delegate (it reads the same box as Send)", true);
      try { input.focus(); } catch { /* focus is a convenience, never a failure */ }
      return;
    }
    input.value = "";
    delegateInFlight = true;
    refreshDelegateControl();
    line("", `▸ objective: ${text}`);
    try {
      renderDelegationResult(await S.runObjective({ objective: text }));
    } catch (e) {
      line("bad", `delegation channel refused: ${(e && e.message) || e}`, true);
    } finally {
      delegateInFlight = false;
      refreshDelegateControl();
    }
  });
})();

// ---- routing/artifact inspector drawer (Plan §10.3) -------------------------
// A THIN VIEW: it pulls governed MCP state on demand via the read-only bridge and renders the
// per-task model (context routed / artifacts published / gate chain) the pure core already
// folded. It computes nothing and decides nothing. Operator-run surface — headlessly the DATA
// path is proven (apps/desktop/test/inspector-source.test.js); this painting is operator-verified.
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function renderInspector(res) {
  const body = document.getElementById("insp-body");
  // U336 (19.7): `ok` is now the AND of the two reads, so a FALSE `ok` no longer means "nothing to
  // show" — one half may be perfectly readable. Bail only when there is nothing readable at all;
  // otherwise paint what there is, under a banner naming what could not be read. What must never
  // happen again is the third case: a failure painted as counts.
  const readable = Boolean(res && (res.model || (res.operational && res.operational.available === true)));
  if (!res || !readable) {
    body.innerHTML = `<div class="insp-err">inspector unavailable — ${esc(res && res.error) || "fail-closed"}</div>`;
    return;
  }
  const degraded = res.ok === true ? "" : `<div class="insp-err">partially unreadable — ${esc(res.error) || "fail-closed"}</div>`;
  // Both halves obey the same rule: null is unreadable, and an unreadable half prints no counts.
  const legacyAvailable = Boolean(res.model && res.summary);
  const model = res.model || { tasks: [], unattributed: { artifacts: [], gates: [] }, anomalies: [] };
  const summary = res.summary || {};
  const routingReadable = res.routingReadable;
  // An unreadable live-orchestration feed carries NO counts (operational-source.js): `summary`,
  // `tasks`, `messages` and `debates` are null, not empty. Nothing below may substitute a zero.
  const op = res.operational || { available: false, nodes: [], error: "no live orchestration feed" };
  const opAvailable = op.available === true;
  const opNodes = Array.isArray(op.nodes) ? op.nodes : [];
  const opTasks = opAvailable && Array.isArray(op.tasks) ? op.tasks : [];
  const nodeRow = (n) => `<div class="ins-node"><span class="k">${esc(n.role)}</span> ${esc(n.provider_id || "?")}/${esc(n.model_id || "?")}
    <span class="st st-${n.ready ? "ACCEPTED" : "CANDIDATE"}">${n.ready ? "READY" : esc(n.mcp_state || n.node_state)}</span>
    <div class="dim">${esc(n.node_id)} · ${esc(n.pane_id)} · pid ${esc(n.pid)} · MCP ${esc(n.mcp_state)}</div></div>`;
  const msgRow = (m) => `<div class="ins-msg"><span class="k">${esc(m.message_kind)}</span> ${esc(m.sender_node_id)} → ${esc((m.recipient_node_ids || []).join(", "))}
    <div>${esc(m.body)}</div><div class="dim">${esc(m.message_id)}</div></div>`;
  const debateRow = (d) => `<div class="ins-debate"><span class="st st-${d.state === "OPEN" ? "CANDIDATE" : "ACCEPTED"}">${esc(d.state)}</span> ${esc(d.proposition)}
    <div class="dim">${esc(d.debate_id)} · ${(d.turns || []).length} turns · max ${esc(d.max_rounds)} rounds per participant</div>
    ${d.decision ? `<div>decision: ${esc(d.decision)}</div>` : ""}
    ${(d.dissent || []).length ? `<div class="warn-t">dissent: ${esc(d.dissent.join("; "))}</div>` : ""}</div>`;
  const operationalTask = (t) => {
    const messages = (opAvailable && op.messages ? op.messages : []).filter((m) => m.task_id === t.task_id);
    const debates = (opAvailable && op.debates ? op.debates : []).filter((d) => d.task_id === t.task_id);
    return `<div class="ins-task"><div class="ins-title">${esc(t.task_id)} · <span class="st st-${esc(t.status)}">${esc(t.status)}</span></div>
      <div>${esc(t.objective)}</div><div class="dim">owners: ${esc((t.owner_node_ids || []).join(", "))}</div>
      ${messages.map(msgRow).join("")}${debates.map(debateRow).join("")}</div>`;
  };
  const gateRow = (g) => `<div class="ins-gate">gate ${esc(g.verdict || "—")}${g.derived ? ' <span class="badge">derived</span>' : ""}
    <span class="dim">${esc(g.author || "")} ${esc(g.entryStatus || "")}</span></div>`;
  const artRow = (a) => `<div class="ins-art"><span class="k">${esc(a.kind)}</span> <span class="st st-${esc(a.status)}">${esc(a.status)}</span>
    <span class="dim">${esc((a.hash || "").slice(0, 16))}</span> <span class="dim">${esc(a.author || "")}</span></div>`;
  const taskCard = (t) => `<div class="ins-task"><div class="ins-title">${esc(t.taskId)}</div>
    <div class="ins-ctx">${t.contextRouted
      ? `routed: ${esc(t.contextRouted.role || "?")} · ${esc(t.contextRouted.count)} entries`
      : `<span class="dim">context routed: not readable (ephemeral)</span>`}</div>
    ${t.gateChain.map(gateRow).join("") || '<div class="dim">no gate events</div>'}
    ${t.artifacts.map(artRow).join("") || '<div class="dim">no artifacts</div>'}</div>`;

  const unatt = model.unattributed;
  body.innerHTML = `
    ${degraded}
    <div class="ins-section">LIVE ORCHESTRATION</div>
    <div class="ins-sum">${opNodes.length} nodes · ${opAvailable
      ? `${esc(op.summary.task_count)} tasks · ${esc(op.summary.message_count)} messages · ${esc(op.summary.debate_count)} debates`
      : `<span class="warn-t">shared governed state UNREADABLE — ${esc(op.error) || "fail-closed"}</span>`}</div>
    ${opNodes.map(nodeRow).join("") || '<div class="dim">no live governed nodes</div>'}
    ${opAvailable
      ? (opTasks.map(operationalTask).join("") || '<div class="dim">no operational assignments</div>')
      : '<div class="dim">assignments, messages and debates could not be read — this is not a count of zero</div>'}
    <div class="ins-section">ARTIFACT / GATE EVIDENCE</div>
    <div class="ins-sum">${legacyAvailable
      ? `${esc(summary.taskCount)} tasks · ${esc(summary.artifactCount)} artifacts · ${esc(summary.gateCount)} gates
      · ${esc(summary.unattributedCount)} unattributed · ${esc(summary.anomalyCount)} anomalies
      ${routingReadable ? "" : '· <span class="warn-t">routing not readable</span>'}`
      : `<span class="warn-t">artifact/gate evidence UNREADABLE — ${esc(res.legacyError) || "fail-closed"}</span>`}</div>
    ${legacyAvailable
      ? (model.tasks.map(taskCard).join("") || '<div class="dim">no tasks in shared memory</div>')
      : '<div class="dim">the control-plane channel could not be read — this is not a count of zero</div>'}
    ${(unatt.artifacts.length || unatt.gates.length)
      ? `<div class="ins-task ins-unatt"><div class="ins-title">unattributed (inv 27)</div>
          ${unatt.gates.map(gateRow).join("")}${unatt.artifacts.map(artRow).join("")}</div>` : ""}
    ${model.anomalies.length
      ? `<div class="ins-anom">${model.anomalies.map((a) => `<div>⚠ ${esc(a.kind)} ${esc(a.entryId || a.taskId || "")}</div>`).join("")}</div>` : ""}`;
}

async function refreshInspector() {
  const body = document.getElementById("insp-body");
  body.innerHTML = '<div class="dim">reading MCP state…</div>';
  try { renderInspector(await S.inspector()); }
  catch (e) { renderInspector({ ok: false, error: (e && e.message) || "read failed" }); }
}

document.getElementById("btn-inspector").addEventListener("click", () => {
  const drawer = document.getElementById("inspector");
  const open = drawer.classList.toggle("open");
  if (open) refreshInspector();
});
document.getElementById("insp-refresh").addEventListener("click", refreshInspector);
document.getElementById("insp-close").addEventListener("click", () => document.getElementById("inspector").classList.remove("open"));

// ---- operator command surface: approval-queue drawer (Phase 15E .objective; §12.5 item 5) ----
// A THIN VIEW of the unified approval queue pulled over the read-only bridge. Rows are plan
// approvals / protected actions / clarifications with a badge count. The Approve/Reject buttons only
// RECORD the operator's request (invariant 1 — the governed resolve is Python-side); Approve is shown
// only for an approvable row (a gate-failed plan is not approvable — invariant 16). Fail-closed: an
// unavailable feed renders "unavailable", never a fabricated pending item. The pure fold that
// produced these rows is headlessly proven (terminal/test/approval-drawer.test.js).
function setApprovalBadge(count) {
  const b = document.getElementById("appr-badge");
  if (!b) return;
  b.textContent = count > 0 ? String(count) : "";
  b.style.display = count > 0 ? "inline-block" : "none";
}

function renderApprovals(res) {
  const body = document.getElementById("appr-body");
  if (!res || res.ok !== true) {
    body.innerHTML = `<div class="insp-err">approvals unavailable — ${esc(res && res.error) || "fail-closed"}</div>`;
    setApprovalBadge(0);
    return;
  }
  setApprovalBadge(res.badgeCount || 0);
  const row = (r) => `<div class="appr-item appr-${esc(r.kind)}">
    <div class="ins-title">${esc(r.kindLabel)} <span class="dim">${esc(r.origin)}</span></div>
    <div class="ins-ctx">${esc(r.summary)}</div>
    <div class="appr-actions">
      ${r.approvable ? `<button class="appr-approve" data-id="${esc(r.id)}">Approve</button>` : ""}
      <button class="appr-reject" data-id="${esc(r.id)}">${r.approvable ? "Reject" : "Dismiss"}</button>
    </div></div>`;
  body.innerHTML = `<div class="ins-sum">${esc(res.summary)}</div>`
    + approvalOutcomeLine()
    + (res.rows.map(row).join("") || '<div class="dim">no pending approvals</div>');
  for (const btn of body.querySelectorAll(".appr-approve")) {
    btn.addEventListener("click", () => decideApproval(btn.dataset.id, "approve"));
  }
  for (const btn of body.querySelectorAll(".appr-reject")) {
    btn.addEventListener("click", () => decideApproval(btn.dataset.id, "reject"));
  }
}

// What the last decide actually did, shown above the rows. Phase 17D `.events` made a resolve
// PERSIST, and that turned a silent return value into a lie: the operator clicked Approve on
// "protected command: spawn worker", the row disappeared for good, and nothing executed — the drawer
// would have taught them they had authorized a spawn that never happened. The governed outcome is
// now rendered, including what is still owed, and a governed REFUSAL says why the row stayed.
let lastApprovalOutcome = null;

function approvalOutcomeLine() {
  if (!lastApprovalOutcome) return "";
  const o = lastApprovalOutcome;
  return `<div class="ins-ctx appr-outcome">${esc(o)}</div>`;
}

async function decideApproval(itemId, decision) {
  // The shell records the operator's intent; the governed resolve is Python-side (invariant 1).
  try {
    const res = await S.decideApproval(itemId, decision, "");
    const g = res && res.governed;
    if (!res || res.routed !== true || !g) {
      lastApprovalOutcome = `${decision} of ${itemId} could not be routed to the authority — nothing was decided (${(res && res.error) || "fail-closed"})`;
    } else if (g.resolved === true) {
      const owed = g.side_effects_owed && g.side_effects_owed.note;
      lastApprovalOutcome = `${decision}d ${itemId} — recorded by the governed authority`
        + (decision === "approve" && owed ? `. NOT YET EXECUTED: ${owed}` : ".");
    } else if (g.refused === true) {
      lastApprovalOutcome = `${decision} of ${itemId} was REFUSED by the authority — ${g.reason || "no reason given"}`;
    } else {
      lastApprovalOutcome = `${decision} of ${itemId} is unresolved — ${g.reason || "the authority was unavailable"}`;
    }
  } catch (e) {
    lastApprovalOutcome = `${decision} of ${itemId} failed at the shell boundary — nothing was decided (${(e && e.message) || "error"})`;
  }
  refreshApprovals();
}

async function refreshApprovals() {
  const body = document.getElementById("appr-body");
  body.innerHTML = '<div class="dim">reading approvals…</div>';
  try { renderApprovals(await S.approvals()); }
  catch (e) { renderApprovals({ ok: false, error: (e && e.message) || "read failed" }); }
}

document.getElementById("btn-approvals").addEventListener("click", () => {
  const drawer = document.getElementById("approvals");
  const open = drawer.classList.toggle("open");
  if (open) refreshApprovals();
});
document.getElementById("appr-refresh").addEventListener("click", refreshApprovals);
document.getElementById("appr-close").addEventListener("click", () => document.getElementById("approvals").classList.remove("open"));
S.onApprovals((model) => setApprovalBadge((model && model.badgeCount) || 0));

// ---- subscription-concurrency status bar (directive §11/15A; Phase 16D `.statusbar`) --------
// A THIN VIEW of the governor n/allowance count. Phase 16D sources it from the REAL governor via the
// bounded emitter (statusbar:fetch → apps/desktop/statusbar/governor-source.js), so it shows one chip
// per live provider — since 18B `.picker` that is all four (claude_code / openai_codex_cli at 2, the
// OP-12 pair at 1) — with each provider's OWN allowance cap visible. Fail-closed: an unreadable
// governor renders an em-dash "—/allowance" unknown chip per provider, NEVER a fabricated 0/n. It computes nothing — the
// pure fold (terminal/statusbar/statusbar-model) already produced these rows, proven by
// apps/desktop/test/statusbar-governor-source.test.js + the in-Electron self-check
// (docs/evidence/receipts/PHASE16D_STATUSBAR_SELFCHECK.json); this painting is operator-verified.
// The chip label per provider lives in picker-chrome.js (UMD), where the desktop suite can reach it:
// while it was a literal in this file, pointing one provider's label at another's name left all 640
// tests green (18B `.picker` review, validator mutation E5). The OP-12 pair joins the bar at 18B
// `.picker` with its own per-provider ceiling (grok/agy read n/1, not n/2 — U255).
const PickerChrome = window.PickerChrome; // pure picker/status-bar chrome (loaded before this)

function renderStatusBar(model) {
  lastStatusModel = model || null; // cached so a pane's frontier n/2 badge reads the same live count
  const bar = document.getElementById("statusbar");
  if (model && (model.source === "local_only_policy" || model.local_only === true)) {
    bar.innerHTML = `<span class="sb-label">local-only</span><span class="dim">commercial cloud subscriptions disabled</span>`;
    return;
  }
  const rows = (model && Array.isArray(model.rows)) ? model.rows : [];
  const chips = rows.map((r) => {
    const label = PickerChrome.providerLabel(r.provider);
    return `<span class="sb-chip ${esc(r.state)}" title="${esc(r.subscriptionRef || r.provider)}">`
      + `<span class="sb-prov">${esc(label)}</span><span class="sb-count">${esc(r.label)}</span></span>`;
  }).join("");
  const warn = (model && model.readable === false)
    ? `<span class="sb-warn">⚠ concurrency count unavailable (fail-closed)</span>` : "";
  bar.innerHTML = `<span class="sb-label">subscriptions</span>${chips || '<span class="dim">…</span>'}${warn}`;
}

async function refreshStatusBar() {
  try { renderStatusBar(await S.statusBar()); }
  catch (e) { renderStatusBar({ readable: false, rows: [], error: (e && e.message) || "read failed" }); }
}
refreshStatusBar();
setInterval(refreshStatusBar, 5000); // low-frequency poll on its own read channel (main-side)

// ---- per-pane model picker drawer (Phase 16B; OP-7 §12.2 / OP-10 §15 track 16B) --------------
// A THIN VIEW of the LIVE host enumeration pulled over the read-only bridge (window.sovereign.picker
// → main → tools/live/enumerate_pane_picker --emit-picker). It renders provider groups with their
// probed model options: an unauthorized/absent frontier provider appears GREYED with its specific
// reason (never hidden, never fabricated — invariant 20 spirit); each local Ollama model shows its
// live residency state (invariant 22). Selecting an available option dispatches the governed
// pane_node_spawn intent (records + previews the badge); the live worker spawn is operator-run/16F.
// It computes nothing and self-authorizes nothing (invariant 1). The Kimi/Qwen ask (OP-10) is
// answered PURELY by what `ollama list` really offers here — a pulled qwen3 tag appears; a cloud-only
// model simply is not in the list (skip-with-record, not a defect).
let lastSpawnResult = null; // last governed spawn-intent result (for the in-Electron self-check)

function openPicker(targetPaneId) {
  pickerTarget = targetPaneId || null;
  document.getElementById("picker").classList.add("open");
  refreshPicker();
}

async function refreshPicker() {
  const body = document.getElementById("picker-body");
  body.innerHTML = '<div class="dim">enumerating host models…</div>';
  try { lastPicker = await S.picker(); }
  catch (e) { lastPicker = { ok: false, error: (e && e.message) || "read failed", picker: null }; }
  renderPicker(lastPicker);
}

function residencyChip(o) {
  if (o.locality !== "local" || !o.residency) return "";
  return `<span class="pk-res ${esc(o.residency)}">${esc(o.residency)}</span>`;
}

function optionRow(o, oidx, conductorTarget = false) {
  const greyed = !o.available;
  const roleSel = greyed || conductorTarget ? "" :
    `<select class="pk-role" data-oidx="${oidx}">${(o.roles || []).map((r) => `<option value="${esc(r)}">${esc(r)}</option>`).join("")}</select>`;
  const action = greyed
    ? `<span class="pk-reason" title="${esc(o.unavailable_reason)}">unavailable</span>`
    : `<button class="pk-spawn" data-oidx="${oidx}">${conductorTarget ? "select" : "spawn"}</button>`;
  const slug = o.model_slug ? `<span class="pk-slug">${esc(o.model_slug)}</span>` : (o.is_fallback ? `<span class="pk-slug">CLI default</span>` : "");
  return `<div class="pk-opt${greyed ? " greyed" : ""}" data-oidx="${oidx}" title="${esc(o.unavailable_reason || o.note || "")}">
    <span class="pk-label">${esc(o.label)} ${slug}</span>${residencyChip(o)}${roleSel}${action}</div>`;
}

function renderPicker(model) {
  const body = document.getElementById("picker-body");
  if (!model || model.ok !== true) {
    body.innerHTML = `<div class="insp-err">picker unavailable — ${esc(model && model.error) || "fail-closed"}</div>`;
    return;
  }
  const picker = model.picker || { providers: [], options: [], authorization: {}, counts: {} };
  const auth = picker.authorization || {};
  const counts = picker.counts || {};
  // flat, stable index the buttons map back to (grouped order == options order, per the contract)
  const conductorTarget = Boolean(conductor && pickerTarget === conductor.paneId);
  const flat = (picker.options || []).filter((o) => !conductorTarget
    || (o.registered === true && o.conductor_capable === true
      && Array.isArray(o.roles) && o.roles.includes("conductor")));
  // `picker.options` and each provider group's `options` are separately decoded objects. Object
  // identity therefore cannot join them; use the provider/model identity from the source contract.
  const idxOf = new Map(flat.map((o, i) => [PickerChrome.optionKey(o), i]));
  const localOnly = auth.mode === "local_only";
  const authLine = `<div class="pk-auth ${auth.authorized ? "ok" : "denied"}">${localOnly ? "LOCAL-ONLY (cloud disabled)" : (auth.authorized ? "live authorized" : "live DENIED (fail-closed)")} — ${esc(auth.reason || "")}</div>`;
  const target = pickerTarget ? `target pane: ${esc(pickerTarget)}` : "target: new pane";
  const groups = (picker.providers || []).filter((g) => !conductorTarget
    || (g.options || []).some((o) => idxOf.has(PickerChrome.optionKey(o)))).map((g) => {
    const opts = (g.options || []).filter((o) => idxOf.has(PickerChrome.optionKey(o)))
      .map((o) => optionRow(o, idxOf.get(PickerChrome.optionKey(o)), conductorTarget)).join("");
    // The group's OWN availability reason is painted here, not merely carried in the model: a
    // provider that enumerated nothing used to render the bare words "no options" (18B `.picker`
    // review — validator BLOCKING-1 / spec-audit M-3), which is the silent gap §14 forbids.
    return PickerChrome.providerGroupHtml(g, opts, esc);
  }).join("");
  body.innerHTML = `<div class="pk-head-row"><span class="dim">${target}</span>`
    + `<span class="dim">${esc(counts.available || 0)}/${esc(counts.total || 0)} available</span></div>`
    + authLine + (groups || '<div class="dim">no options enumerated</div>')
    + `<div id="pk-result"></div>`;
  wirePickerButtons(flat);
}

function wirePickerButtons(flat) {
  const body = document.getElementById("picker-body");
  for (const btn of body.querySelectorAll(".pk-spawn")) {
    btn.addEventListener("click", () => {
      const oidx = Number(btn.dataset.oidx);
      const opt = flat[oidx];
      const sel = body.querySelector(`select.pk-role[data-oidx="${oidx}"]`);
      const conductorTarget = Boolean(conductor && pickerTarget === conductor.paneId);
      const role = conductorTarget ? "conductor" : (sel ? sel.value : (opt.roles && opt.roles[0]));
      doSpawnFromPicker(opt, role);
    });
  }
}

async function doSpawnFromPicker(opt, role) {
  let res;
  const conductorTarget = Boolean(conductor && pickerTarget === conductor.paneId && role === "conductor");
  try {
    res = conductorTarget
      ? await S.selectConductor({ option: opt, role, mode: "attended", targetPaneId: pickerTarget })
      : await S.spawnFromSelection({ option: opt, role, mode: "autonomous", targetPaneId: pickerTarget });
  }
  catch (e) { res = { recorded: false, error: (e && e.message) || "refused" }; }
  lastSpawnResult = res;
  showPickerResult(res, opt, role);
  // Badge the pane the launch actually targeted (`res.target`), which for a "+ Terminal node"
  // selection is a pane that did not exist when the click fired — badging `pickerTarget` alone left
  // every newly-launched pane blank (Phase 17B `.spawn`).
  const badged = (res && res.target) || pickerTarget;
  if (res && res.recorded && res.chrome && badged) {
    paneBadges.set(badged, res.chrome);
    const rec = terms.get(badged);
    if (rec) applyChrome(badged);
  }
  return res;
}

function showPickerResult(res, opt, role) {
  const el = document.getElementById("pk-result");
  if (!el) return;
  // Phase 17B `.spawn`: a selection now LAUNCHES a governed session, so the result line says which
  // of the three things happened — launched, refused by a gate, or not recorded at all. The old line
  // ("spawn deferred to operator-run/16F") described a shell that no longer exists, and a UI that
  // reports a deferral for a launch that really was attempted is the F3 defect wearing new words.
  if (res && res.selected) {
    el.className = "pk-result ok";
    el.textContent = `✓ selected ${opt.provider}/${opt.label} as pane-1 conductor; launch remains operator-controlled`;
  } else if (res && res.launched) {
    el.className = "pk-result ok";
    el.textContent = `✓ LIVE ${opt.provider}/${opt.label} · ${role} — governed session running in `
      + `${res.target}${res.argv ? ` (${res.argv.join(" ")})` : ""}`;
  } else if (res && res.recorded) {
    el.className = "pk-result bad";
    el.textContent = `✗ not launched — ${res.reason || res.error || "fail-closed"}`
      + `${res.refusedBy ? ` [gate: ${res.refusedBy}]` : ""}`;
  } else {
    el.className = "pk-result bad";
    el.textContent = `✗ refused — ${(res && res.error) || "fail-closed"}`;
  }
}

document.getElementById("btn-picker").addEventListener("click", () => openPicker(null));
document.getElementById("pk-refresh").addEventListener("click", refreshPicker);
document.getElementById("pk-close").addEventListener("click", () => document.getElementById("picker").classList.remove("open"));

window.addEventListener("resize", () => { for (const { fit } of terms.values()) { try { fit.fit(); } catch { /* */ } } });

// ---- in-Electron self-check hook (Phase 16A / D-P16-0) ----------------------
// A READ-ONLY observability surface over what is ACTUALLY on screen (invariant 27) — it reads the
// live xterm buffer and can focus a pane. It grants NO new authority (no Node, no PTY, no socket):
// everything here is already reachable from this renderer. Armed ONLY for the diagnostic run (the
// main process passes ?selfcheck=1 under SHELL_SELFCHECK), so it is absent in a normal operator
// launch. The main-process self-check drives it via executeJavaScript to assert the banner/echo
// really rendered into the pane buffer.
if (new URLSearchParams(window.location.search).get("selfcheck") === "1") {
  // The U177 channel sweep, fetched only when a receipt asks for it. `script-src 'self'` allows this
  // exactly as it allows the tags in index.html; the module registers itself on `window` and needs a
  // bridge INJECTED before it can do anything, so loading it grants nothing either way — the reason
  // it is not in index.html is that a normal launch has no consumer for it.
  let channelSweepLoad = null;
  const loadChannelSweep = () => {
    if (window.SovereignChannelSweep) return Promise.resolve(window.SovereignChannelSweep);
    if (!channelSweepLoad) {
      channelSweepLoad = new Promise((resolve, reject) => {
        const el = document.createElement("script");
        el.src = "channel-sweep.js";
        el.onload = () => (window.SovereignChannelSweep
          ? resolve(window.SovereignChannelSweep)
          : reject(new Error("channel-sweep.js loaded but registered nothing")));
        el.onerror = () => reject(new Error("channel-sweep.js could not be loaded"));
        document.head.appendChild(el);
      });
    }
    return channelSweepLoad;
  };
  window.__sovereignSelfCheck = {
    hasTerm(id) { return terms.has(id); },
    focusPane(id) { const r = terms.get(id); if (r) r.term.focus(); return !!r; },
    // Drive the REAL renderer input wiring: term.input(data) fires the same onData path a physical
    // keystroke does (term.onData → S.input → pane:input → manager.write → PTY), so the self-check
    // proves keystrokes-reach-the-session without depending on synthetic OS key delivery.
    typeInto(id, data) { const r = terms.get(id); if (!r) return false; r.term.input(data, true); return true; },
    paneText(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const b = rec.term.buffer.active;
      const lines = [];
      for (let i = 0; i < b.length; i++) { const ln = b.getLine(i); lines.push(ln ? ln.translateToString(true) : ""); }
      return lines.join("\n");
    },
    // ---- Phase 16B picker hooks (read-only; grant no authority) ----
    // Drive the REAL picker path: open it, read what actually rendered, and dispatch a selection
    // through the SAME governed intent a click does — so the self-check proves the wired UI, not a mock.
    async openPicker(targetPaneId) { openPicker(targetPaneId || null); await new Promise((r) => setTimeout(r, 0)); return true; },
    pickerModel() { return lastPicker; },
    // compact, transfer-safe summary of what the picker enumerated (avoids shipping 49 options)
    pickerSummary() {
      const m = lastPicker;
      const p = (m && m.picker) || {};
      const opts = p.options || [];
      return {
        ok: !!(m && m.ok),
        total: opts.length,
        available: opts.filter((o) => o.available).length,
        greyedWithReason: opts.filter((o) => !o.available).every((o) => !!o.unavailable_reason),
        authReadable: !!(p.authorization && typeof p.authorization.authorized === "boolean"),
        authAuthorized: !!(p.authorization && p.authorization.authorized),
        firstAvailable: opts.findIndex((o) => o.available),
        firstConductor: opts.findIndex((o) => Array.isArray(o.roles) && o.roles.includes("conductor")),
      };
    },
    pickerRendered() {
      const body = document.getElementById("picker-body");
      return {
        open: document.getElementById("picker").classList.contains("open"),
        optionEls: body.querySelectorAll(".pk-opt").length,
        spawnBtns: body.querySelectorAll(".pk-spawn").length,
        greyedEls: body.querySelectorAll(".pk-opt.greyed").length,
        groupEls: body.querySelectorAll(".pk-group").length,
        authClass: (body.querySelector(".pk-auth") || {}).className || null,
      };
    },
    firstAvailableIndex() {
      const opts = (lastPicker && lastPicker.picker && lastPicker.picker.options) || [];
      return opts.findIndex((o) => o.available);
    },
    async selectOption(oidx, role) {
      const opts = (lastPicker && lastPicker.picker && lastPicker.picker.options) || [];
      const opt = opts[oidx];
      if (!opt) return { recorded: false, error: "no such option" };
      return doSpawnFromPicker(opt, role || (opt.roles && opt.roles[0]));
    },
    lastSpawnResult() { return lastSpawnResult; },
    paneBadgeText(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".mbadge");
      return el ? { text: el.textContent, shown: el.classList.contains("show") } : null;
    },
    // ---- Phase 19 unit 19.7 hook (U336; read-only, grants no authority) ----
    // Paint a model through the PRODUCTION `renderInspector` and hand back what landed in the DOM,
    // so a receipt can show that an unreadable half is drawn as unreadable rather than as counts.
    // It renders, it does not decide: the model comes from the caller and the HTML comes from the
    // same function an operator's refresh calls.
    renderInspectorModel(model) {
      renderInspector(model);
      const body = document.getElementById("insp-body");
      return body ? body.innerHTML : null;
    },
    // …and the real bridge read, so the same receipt can show what THIS shell answers right now.
    async inspectorFetch() { return S.inspector(); },
    // ---- Phase 16D `.recovery` hook (U68; read-only, grants no authority) ----
    // Simulate a fresh shell-process renderer: drop the in-memory picker badges + repaint blank, so
    // the subsequent shell:recovery must REBUILD the badge from the persisted/reconstructed chrome
    // (not from this session's memory). Load-bearing: reverted U68 wiring ⇒ snapshot carries no
    // chrome ⇒ recovery cannot restore the badge ⇒ paneBadgeText stays blank ⇒ the self-check FAILS.
    resetBadges() {
      const ids = Array.from(paneBadges.keys());
      paneBadges.clear();
      for (const id of ids) { if (terms.has(id)) applyChrome(id); }
      return ids;
    },
    // ---- Phase 16C conductor-selection hooks (read-only; grant no authority) ----
    // The conductor state the renderer received over shell:conductor (the SOURCED badge + succession),
    // and the text of the CONDUCTOR badge actually rendered into pane 1's chrome. Together they prove
    // the badge is drawn from the authoritative Python feed, not a local literal (U65).
    conductorState() { return conductor; },
    // Phase 17A `.pty`: what the CHROME actually shows for the live-session control (read-only).
    conductorLiveControl(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".clive");
      return el ? { text: el.textContent, hidden: el.style.display === "none", title: el.title } : null;
    },
    conductorBadgeText(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".cbadge");
      return el ? { text: el.textContent, cls: el.className, isConductor: rec.el.classList.contains("conductor") } : null;
    },
    // Phase 16C .dispatch: the text of the DISPATCH line actually rendered into pane 1's chrome — so
    // the self-check proves the dispatch summary is drawn from the sourced Python feed, not a literal.
    conductorDispatchText(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".cdispatch");
      return el ? { text: el.textContent, cls: el.className, isConductor: rec.el.classList.contains("conductor") } : null;
    },
    // ---- Phase 16E `.wire` voice-IN hooks (U67; read-only, grant no authority) ----
    // Drive the REAL talk-button path (S.captureVoice → voice:capture → the Python bridge), read what
    // rendered into the conductor chrome, and read the voice state — so the self-check proves the wired
    // engine indicator + outcome are drawn from the sourced feed, not a literal.
    async captureVoice(ref) { const r = await S.captureVoice(ref || null); await refreshVoice(); return r; },
    // ---- Phase 17C `.mic` hooks (U137; read-only, grant no authority) ----
    // Drive the REAL capture handler with REAL PCM. The microphone itself is operator hardware and
    // cannot be exercised here, so the check supplies a fixture WAV's samples at exactly the point
    // `MicRecorder.stop()` hands its encoding over — everything downstream (the IPC payload shape,
    // main's CaptureStore write, the real-engine selection, the WSL Parakeet transcription, the
    // bridge routing, the guaranteed discard) is then the production path, unmodified.
    async captureVoicePcm(byteArray, sampleRate) {
      const pcm = Uint8Array.from(byteArray || []);
      const r = await S.captureVoice({ pcm, sampleRate: sampleRate || 16000 });
      await refreshVoice();
      return r;
    },
    // The encoder as the RENDERER holds it — so a receipt leg can prove the shipped encode path
    // produces the exact container the transcription accepts, rather than trusting main's copy.
    encodeCapturePcm(floatSamples, inputRate) {
      const enc = window.SovereignWav.encodeCapture([Float32Array.from(floatSamples || [])], inputRate || 16000);
      return { bytes: Array.from(enc.bytes), samples: enc.samples, sampleRate: enc.sampleRate, seconds: enc.seconds };
    },
    /**
     * Fire raw UI events at a pane's REAL talk button and report whether anything was routed.
     * This exists for one leg: an earlier revision of `wirePushToTalk` routed the scripted stand-in
     * ref whenever real capture failed or never began, so a stray `pointerup` (released over the
     * button after dragging a divider) or a synthetic `click` typed `"show status"` into the live
     * conductor's ConPTY as though the operator had said it. `voiceModel` is the shell's own state, so
     * "nothing was routed" is measured against what main actually holds, not against a promise.
     */
    async fireTalkEvents(id, kinds) {
      const rec = terms.get(id);
      if (!rec) return null;
      const btn = rec.el.querySelector('[data-act="ptt"]');
      if (!btn) return null;
      const before = JSON.stringify((voiceModel && voiceModel.badge) || null);
      for (const kind of kinds || []) {
        const ev = kind === "click"
          ? new MouseEvent("click", { bubbles: true, cancelable: true })
          : new PointerEvent(kind, { bubbles: true, cancelable: true });
        btn.dispatchEvent(ev);
      }
      await new Promise((r) => setTimeout(r, 1500));   // give any routing time to land
      await refreshVoice();
      return { before, after: JSON.stringify((voiceModel && voiceModel.badge) || null), label: btn.textContent };
    },
    // Is the push-to-talk recorder actually present and wired in this runtime? (A regression that
    // dropped the <script> tag would leave the button routing stand-ins forever, silently.)
    micWired() {
      return {
        recorder: Boolean(window.SovereignMic && window.SovereignMic.MicRecorder),
        encoder: Boolean(window.SovereignWav && window.SovereignWav.encodeCapture),
        button: Boolean(document.querySelector('.pane [data-act="ptt"]')),
      };
    },
    voiceModel() { return voiceModel; },
    voiceBadgeText(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".cvoice");
      return el ? { text: el.textContent, cls: el.className, isConductor: rec.el.classList.contains("conductor") } : null;
    },
    // Phase 17C `.disarm` (U166 / invariant 27): what the OPERATOR can see about the restriction —
    // read from the painted chrome, not from the model behind it. A state that is only in a receipt
    // is not visible, which is exactly what this sub-step is correcting.
    voiceTurnBadge(id) {
      const rec = terms.get(id);
      if (!rec) return null;
      const el = rec.el.querySelector(".cturn");
      if (!el) return null;
      return {
        text: el.textContent, cls: el.className, title: el.title,
        hidden: el.style.display === "none",
        isConductor: rec.el.classList.contains("conductor"),
      };
    },
    // Repaint on demand: main pushes `shell:voice` on every turn transition, and this lets a receipt
    // leg read the chrome at a chosen instant without racing that push.
    async refreshVoiceChrome() { await refreshVoice(); if (conductor && conductor.paneId) applyChrome(conductor.paneId); return voiceModel; },
    // Phase 17C `.receipt` (U177): drive EVERY intent this renderer can send to main, so the receipt
    // can assert an admitted voice turn is still admitted afterwards. The static wiring guard cannot
    // see a callee reached through a getter or a Proxy trap, or a reference stored on one channel and
    // invoked from another — this is the runtime assertion the register owes in its place. It grants
    // nothing: every call goes through the same bridge this renderer already holds, and the sweep is
    // fail-closed on any intent it does not name (channel-sweep.js).
    //
    // The driver is fetched HERE rather than by a <script> tag in index.html, so a normal operator
    // launch never carries it: it is diagnostic machinery with one consumer, and this block is the
    // consumer (invariant 30 — minimal necessary control; spec-audit F5).
    async driveEveryRendererChannel(opts) {
      const paneId = (opts && opts.conductorPaneId) || (conductor && conductor.paneId) || null;
      const rec = terms.get(paneId);
      const sweep = await loadChannelSweep();
      // the pane's CURRENT geometry — the sweep's `resize` must not repaint the live conductor TUI
      return sweep.runChannelSweep(S, {
        conductorPaneId: paneId,
        cols: rec ? rec.term.cols : undefined,
        rows: rec ? rec.term.rows : undefined,
      });
    },
  };
}
