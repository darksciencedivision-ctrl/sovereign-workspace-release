"use strict";
/* Sequence-numbered synthetic streamer. Default ~1 MB/s. Any SEQ gap on the reader side = dropped output. */
const RATE = Number(process.env.SPIKE_RATE_BPS || 1048576);
const LINE_BYTES = 100; // "SEQ:<n>:" + pad + \n
let n = 0;
const PAD = "x".repeat(LINE_BYTES);
const TICK_MS = 50;
const perTick = Math.max(1, Math.round((RATE * TICK_MS) / 1000 / LINE_BYTES));
setInterval(() => {
  let out = "";
  for (let i = 0; i < perTick; i++) {
    n += 1;
    const head = `SEQ:${n}:`;
    out += head + PAD.slice(0, Math.max(0, LINE_BYTES - head.length - 1)) + "\n";
  }
  process.stdout.write(out);
}, TICK_MS);
process.on("SIGTERM", () => process.exit(0));
