"use strict";
/**
 * Node/Chromium IPC client for the desktop shell — mirrors control_plane/ipc/client.py.
 *
 * The shell's main process talks to the control plane over the SAME authenticated loopback
 * WebSocket the Python reference client uses: signed envelope@1.0 out, signed envelope back,
 * both integrity-verified. The transport differs (native WebSocket vs a hand-rolled socket),
 * the CONTRACT is identical — proven by the round-trip test against the real Python gateway.
 *
 * Fail-closed, exactly like the reference:
 *   - any transport fault  -> IpcDisconnected (never proceed on assumed control-plane state);
 *   - a response whose integrity does not verify -> IpcIntegrityError (treat as untrusted).
 *
 * Transport implementation (defect D-P14-1, found at first operator headed launch): the
 * global WebSocket exists in Node >= 21 — where all test runs executed — but Electron <= 34
 * embeds Node 20 in the MAIN process, where it is undefined, so the shell booted into its
 * (correct) fail-closed SUPERVISION DENIED state. Resolve the implementation once: prefer
 * the platform global (zero-dep path), fall back to the 'ws' package in browser-compatible
 * mode. Both expose the exact surface used here (addEventListener/{once}, ev.data,
 * readyState, OPEN). node:crypto supplies the HMAC.
 */
const env = require("./envelope");

const WSImpl = typeof globalThis.WebSocket !== "undefined"
  ? globalThis.WebSocket
  : require("ws").WebSocket;

class IpcDisconnected extends Error {}
class IpcIntegrityError extends Error {}
/**
 * The sequential control channel already has a request in flight. Distinct from `IpcDisconnected`
 * on purpose (Phase 17A `.roundtrip`): a BUSY channel is positive evidence that the channel is
 * ALIVE — something is talking on it — while a disconnect is evidence it is gone. Collapsing the
 * two scored a benign collision between the 5 s supervision heartbeat and a session-event notify as
 * "supervision LOST", which tore down every session including the operator's live conductor.
 * Bounded: an in-flight request always settles (its own timeout rejects and clears `_pending`), so
 * this condition cannot persist beyond one request timeout.
 */
class IpcBusy extends Error {}

const _LOOPBACK = new Set(["127.0.0.1", "::1", "localhost"]);

class IpcClient {
  constructor({ host, port, nodeId, token, key, scope = "project", timeoutMs = 10000 }) {
    // Enforce loopback IN THE TRANSPORT, not only in the caller (invariant 20, offline
    // honesty, fail-closed): the control channel is a loopback WebSocket by contract, so a
    // non-loopback host is refused here rather than trusted to be set correctly upstream.
    if (!_LOOPBACK.has(host)) {
      throw new IpcDisconnected(`refusing non-loopback IPC host ${host}`);
    }
    this._url = `ws://${host}:${port}/`;
    this._nodeId = nodeId;
    this._token = token;
    this._key = Buffer.isBuffer(key) ? key : Buffer.from(key, "hex");
    this._scope = scope;
    this._timeoutMs = timeoutMs;
    this._ws = null;
    this._pending = null; // single in-flight request (loopback control channel is sequential)
  }

  connect() {
    if (this._ws && this._ws.readyState === WSImpl.OPEN) return Promise.resolve();
    return new Promise((resolve, reject) => {
      let ws;
      try {
        ws = new WSImpl(this._url);
      } catch (e) {
        reject(new IpcDisconnected(`cannot construct WebSocket to ${this._url}: ${e.message}`));
        return;
      }
      const to = setTimeout(() => {
        try { ws.close(); } catch { /* ignore */ }
        reject(new IpcDisconnected(`timed out connecting to ${this._url}`));
      }, this._timeoutMs);
      ws.addEventListener("open", () => {
        clearTimeout(to);
        this._ws = ws;
        ws.addEventListener("message", (ev) => this._onMessage(ev));
        ws.addEventListener("close", (ev) => this._onClose(ev));
        ws.addEventListener("error", () => this._onClose({ reason: "socket error" }));
        resolve();
      }, { once: true });
      ws.addEventListener("error", () => {
        clearTimeout(to);
        reject(new IpcDisconnected(`cannot reach IPC gateway at ${this._url}`));
      }, { once: true });
    });
  }

  /** Send one control_event envelope; resolve with the verified response payload. */
  async controlEvent(payload, { taskId = null } = {}) {
    if (!this._ws || this._ws.readyState !== WSImpl.OPEN) await this.connect();
    if (this._pending) throw new IpcBusy("control channel is busy (one request in flight)");
    const request = env.makeEnvelope({
      fromNode: this._nodeId, to: ["control-plane"], msgType: "control_event",
      payload, nodeCredential: this._token, scope: this._scope, key: this._key, taskId,
    });
    return new Promise((resolve, reject) => {
      const to = setTimeout(() => {
        this._pending = null;
        reject(new IpcDisconnected("timed out awaiting control-plane response"));
      }, this._timeoutMs);
      this._pending = { resolve, reject, timer: to };
      try {
        this._ws.send(JSON.stringify(request));
      } catch (e) {
        clearTimeout(to);
        this._pending = null;
        reject(new IpcDisconnected(`send failed: ${e.message}`));
      }
    });
  }

  _onMessage(ev) {
    const p = this._pending;
    if (!p) return; // unsolicited frame; ignore on this sequential channel
    this._pending = null;
    clearTimeout(p.timer);
    let response;
    try {
      response = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString("utf8"));
    } catch (e) {
      p.reject(new IpcIntegrityError(`unparseable response: ${e.message}`));
      return;
    }
    // U458: the SAME ruled order the gateway applies to us — integrity first, then the signed `ts`.
    // Freshness is checked here rather than left as an exported rule nobody calls: a verification
    // function with no caller is not a check, and the shell is the only reader of these replies.
    // The `ts` is inside the signature, so this is a bound and not a claim the sender makes.
    if (!env.verifyIntegrity(this._key, response)) {
      p.reject(new IpcIntegrityError("response integrity did not verify"));
      return;
    }
    if (!env.envelopeIsFresh(response)) {
      p.reject(new IpcIntegrityError("response is outside the freshness window"));
      return;
    }
    p.resolve(response.payload);
  }

  _onClose(ev) {
    const p = this._pending;
    this._pending = null;
    if (p) {
      clearTimeout(p.timer);
      p.reject(new IpcDisconnected(`connection closed: ${ev && ev.reason ? ev.reason : "peer closed"}`));
    }
    this._ws = null;
  }

  close() {
    if (this._ws) {
      try { this._ws.close(); } catch { /* ignore */ }
      this._ws = null;
    }
  }
}

module.exports = { IpcClient, IpcDisconnected, IpcIntegrityError, IpcBusy };
