"use strict";
/**
 * Phase 17C `.close` — did the conductor pane ECHO the utterance we just wrote into it?
 *
 * WHY THE SUBMIT KEY DEPENDS ON THIS. The voice delivery writes the transcript body and then the submit
 * key. Sending that key blind is not safe: the live `claude` session gates its own tool use with in-pane
 * prompts ("Do you want to proceed? ❯1. Yes  2. Yes, and don't ask again  3. No"), so a bare `\r`
 * arriving while one is open CONFIRMS ITS DEFAULT — a protected action executed from an ordinary spoken
 * sentence, with no CommandBroker and no approval queue. Invariant 25 exists to forbid exactly that.
 * Requiring the echo means the submit key follows an OBSERVATION rather than a hope, and it
 * simultaneously establishes that the body actually arrived (falsification F2 measured the opposite
 * case: a single `body\r` chunk that echoed but was never received as a message).
 *
 * WHAT THIS FILE IS *NOT*, corrected after `.close-revalidate` — the first draft of this header claimed
 * the echo requirement refused a prompt "BY CONSTRUCTION" because a prompt does not echo typed text.
 * That was an assumption about a vendor TUI stated as a construction, and both mandatory reviews found
 * it load-bearing and unproven. Two things are true instead, and they live elsewhere:
 *   • whether the pane is showing its text input at all is decided BEFORE anything is written, by
 *     `voice/pane-state.js` — that is the guard that keeps the operator's sentence out of a
 *     confirmation dialog, and it fails closed on any state it does not recognise;
 *   • whether the echo this function scans is really THIS utterance's echo is the caller's job: it must
 *     pass only the bytes appended AFTER the write (`RingBuffer.sliceFrom`, exact or null). Handed the
 *     whole scrollback, this function will happily match an earlier echo of the same sentence — it is a
 *     matcher, not a window.
 *
 * WHY IT IS NOT A SUBSTRING TEST. The evidence must come from main's own copy of what the ConPTY emitted
 * (the session ring buffer — invariant 29: the renderer is the least-trusted surface and must not be the
 * thing that authorises a keystroke into a live model session). But a ConPTY repaint of a full-screen TUI
 * is not a transcript: it is cursor moves, escape sequences, box borders, padding and status lines, and
 * the first version of this check — a plain "does the tail contain the utterance" — FAILED on a run whose
 * pane demonstrably rendered the utterance in full. The repaint had split it.
 *
 * So the comparison is: reduce to alphanumerics (escapes, borders, wrapping and punctuation vanish), cut
 * the utterance into consecutive fixed-length SEGMENTS, and count how many appear IN ORDER in what the
 * pane emitted after the write.
 *
 * WHAT THE THRESHOLD IS, AND WHY IT IS NOT "ALL OF THEM". Both stricter rules were tried against the
 * real thing and both refused a delivery the pane had visibly accepted. Measured on this host, the live
 * `claude` TUI's repaint stream carries the HEAD of a freshly-written utterance and not the tail
 * (`2/5` segments, `first_missing: "withonlyth"`), while the rendered screen shows the whole sentence in
 * the input box. That is a property of screen-diff repaints, not of the delivery: the bytes on the wire
 * are not a transcript of the screen, and reconstructing one from them is a terminal emulator's job.
 *
 * So this gate answers the question it CAN answer: **did the pane, in the bytes it emitted after the
 * write, send this utterance's own characters back?** A run of them coming back in order is yes.
 *
 * WHAT IT THEREFORE DOES NOT ESTABLISH, stated plainly because the difference matters: it does not prove
 * every character arrived. A delivery truncated inside the CLI's own ingest would echo its head and pass
 * here. Byte-level integrity is asserted instead from the RENDERED SCREEN by the in-Electron receipt
 * (`whole_transcript_echoed_in_pane`), which has a real emulator's screen model to read; U145 records the
 * residue for the production path.
 *
 * Pure and deterministic — no I/O, no Electron. The caller owns the buffer read and the polling.
 */

//: Segment length. Short enough that a repaint splitting the line every dozen characters still leaves
//: whole segments intact; long enough that finding them in order by coincidence is not realistic.
const SEGMENT_ALNUM_CHARS = 10;
//: How many of the utterance's own ten-character runs must come back before a submit key may follow.
//: TWO, i.e. twenty characters in order — far more than repaint noise produces by chance, and far less
//: than a screen-diff stream can be relied on to carry. A single-segment utterance (≤10 alphanumerics —
//: "hello there") must match its one segment: weaker evidence than the rule wants, noted by both
//: reviews, and there is nothing stronger available for an utterance that short. It is bounded by the
//: caller's window: 10 characters of coincidence inside just the bytes appended after the write.
const MIN_ECHO_SEGMENTS = 2;

/** Alphanumerics only, lowercased: ANSI escapes, box borders, padding and wrapping all disappear. */
function alnumOnly(text) {
  return String(text == null ? "" : text).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

/** The utterance as consecutive alnum segments (the final one may be shorter). */
function segmentsOf(body, segmentLen = SEGMENT_ALNUM_CHARS) {
  const n = alnumOnly(body);
  const out = [];
  for (let i = 0; i < n.length; i += segmentLen) out.push(n.slice(i, i + segmentLen));
  return out;
}

/**
 * Did `emitted` carry this utterance back, in order?
 * @param {string} emitted what the pane emitted AFTER the write (raw bytes are fine — reduced here)
 * @param {string} body the utterance that was written
 * @returns {{echoed:boolean, matchedSegments:number, totalSegments:number, ratio:number,
 *            firstMissingSegment:(string|null)}}
 *   The counts and the ratio are returned, not just the verdict, so a refusal says WHICH failure it was:
 *   0 of 5 is "the pane is not accepting text" (a prompt), 2 of 5 is "the delivery was truncated".
 */
function echoedInOrder(emitted, body, segmentLen = SEGMENT_ALNUM_CHARS, minSegments = MIN_ECHO_SEGMENTS) {
  const hay = alnumOnly(emitted);
  const segs = segmentsOf(body, segmentLen);
  if (segs.length === 0) {
    return { echoed: false, matchedSegments: 0, totalSegments: 0, ratio: 0, firstMissingSegment: null };
  }
  let cursor = 0;
  let matched = 0;
  let firstMissing = null;
  for (const seg of segs) {
    const at = hay.indexOf(seg, cursor);
    if (at < 0) {
      if (firstMissing === null) firstMissing = seg;
      continue;                       // a repaint break destroyed this run; the rest may still be intact
    }
    cursor = at + seg.length;
    matched += 1;
  }
  const ratio = matched / segs.length;
  return {
    echoed: matched >= Math.min(minSegments, segs.length),
    matchedSegments: matched,
    totalSegments: segs.length,
    ratio: Math.round(ratio * 100) / 100,
    firstMissingSegment: firstMissing,
  };
}

module.exports = { SEGMENT_ALNUM_CHARS, MIN_ECHO_SEGMENTS, alnumOnly, segmentsOf, echoedInOrder };
