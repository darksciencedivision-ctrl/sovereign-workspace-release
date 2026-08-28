"use strict";
/**
 * W-40 (second disposition) — MEASURED / PREMISE NARROWED / NO TRANSPORT REPAIR REQUIRED.
 *
 * The alleged defect was that `run_gateway.py` prints `IPC_TOKEN=`/`IPC_KEY=` "to stdout", where
 * they would be logged and mirrored to the renderer. Execution narrowed it:
 *
 *   Gateway bootstrap credentials traverse the spawned child's private stdout pipe to
 *   `resolveGateway`. That pipe is not a console stream, is not mirrored to the renderer, and is
 *   not written to `main-process.log`; stderr is the log-mirrored child stream. The originally
 *   alleged stdout -> log/renderer exposure does not reproduce on the live architecture.
 *
 * R-69 is NOT refuted — its Origin/Host half was a real defect and is repaired in this same unit.
 * What was narrowed is the credential-stream half specifically.
 *
 * SO THIS FILE PINS THE PROPERTY, NOT THE TRANSPORT. What makes the current design acceptable is
 * that the secret is transient on a private parent-child bootstrap channel and reaches nothing
 * observational or persistent. That is a property a future refactor can silently destroy — flipping
 * `stdio` to `"inherit"`, or adding a `log()` call to the stdout handler while debugging. Then this
 * goes red. Relocating the token today would have protected nothing and cost a durable secret
 * medium.
 *
 * The synthetic credential is deliberately conspicuous, so a match anywhere is unmistakable and
 * greppable, and so no real credential is ever involved in this test.
 *
 * `IPC_ALLOW_FIXED_CRED` is used HERE AS A TEST SEAM, which is what it is for: an explicit,
 * fail-closed opt-in to supply a credential instead of minting one. The operator ruling forbids
 * repurposing it for the NORMAL startup path, which this does not do.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");

const REPO = path.resolve(__dirname, "..", "..", "..");

const TOKEN = "TOKEN_W40_DO_NOT_LOG_7F3A9C2E";
const KEY_HEX = "9a5b7c1d3e4f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9";

const MAIN = fs.readFileSync(path.resolve(__dirname, "..", "main.js"), "utf8");
const slice = (source, from, to) => {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start > 0 && end > start, `could not locate ${from} … ${to}`);
  return source.slice(start, end);
};
const executableOnly = (region) =>
  region.replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n").filter((line) => !/^\s*\/\//.test(line)).join("\n");
const resolveGatewayRegion = () =>
  executableOnly(slice(MAIN, "function resolveGateway()", "\n// ---- "));

/** Run the REAL gateway with a synthetic fixed credential; capture the two streams separately. */
function runGateway() {
  return new Promise((resolve) => {
    const proc = spawn("py", ["-3.12", "-m", "control_plane.ipc.run_gateway"], {
      cwd: REPO,
      env: {
        ...process.env,
        SOVEREIGN_IPC_NODE: "w40-probe", SOVEREIGN_IPC_ROLE: "shell", SOVEREIGN_IPC_PROJECT: "proj",
        IPC_ALLOW_FIXED_CRED: "1", IPC_FIXED_TOKEN: TOKEN, IPC_FIXED_KEY: KEY_HEX,
      },
    });
    let stdout = "";
    let stderr = "";
    const done = (result) => { try { proc.kill(); } catch { /* already gone */ } resolve(result); };
    const timer = setTimeout(() => done({ stdout, stderr, argv: proc.spawnargs }), 25000);
    proc.stdout.on("data", (d) => {
      stdout += String(d);
      if (/IPC_TOKEN=/.test(stdout) && /IPC_KEY=/.test(stdout) && /IPC_PORT=/.test(stdout)) {
        clearTimeout(timer);
        done({ stdout, stderr, argv: proc.spawnargs });
      }
    });
    proc.stderr.on("data", (d) => { stderr += String(d); });
    proc.on("error", () => { clearTimeout(timer); done({ stdout, stderr, argv: proc.spawnargs }); });
  });
}

test("W-40: the bootstrap credential is on the child's PRIVATE stdout pipe and nowhere else",
  { timeout: 60000 }, async () => {
    const before = new Set(fs.readdirSync(os.tmpdir()));
    const { stdout, stderr, argv } = await runGateway();

    // (1) resolveGateway's input: both values arrive, parseable by the same regex main.js uses.
    const parsed = {};
    for (const line of stdout.split(/\r?\n/)) {
      const m = /^(IPC_PORT|IPC_TOKEN|IPC_KEY)=(.+)$/.exec(line.trim());
      if (m) parsed[m[1]] = m[2];
    }
    assert.strictEqual(parsed.IPC_TOKEN, TOKEN, `token not delivered; stderr=${stderr.slice(0, 300)}`);
    assert.strictEqual(parsed.IPC_KEY, KEY_HEX, "key not delivered over the bootstrap pipe");

    // (2) not on stderr — the ONLY child stream main.js mirrors into the log.
    assert.ok(!stderr.includes(TOKEN) && !stderr.includes(KEY_HEX),
      "the credential reached stderr, which main.js forwards to log() verbatim");

    // (5) not in the spawned argv, where any other local process could read it.
    assert.ok(!argv.join(" ").includes(TOKEN) && !argv.join(" ").includes(KEY_HEX),
      "the credential is in the child's command line");

    // (6) no credential file created.
    const created = fs.readdirSync(os.tmpdir()).filter((f) => !before.has(f));
    for (const name of created) {
      assert.ok(!/ipc|token|cred|key/i.test(name),
        `the gateway created what looks like a credential file: ${name}`);
    }
  });

test("W-40: main.js mirrors STDERR to the log and never the stdout the credential rides on", () => {
  const region = resolveGatewayRegion();
  // (3) + (7): the raw bootstrap line must not be handed to a generic logger, before or after
  // parsing. The stdout handler is where a debugging `log(...)` would most naturally be added.
  const stdoutHandler = slice(region, 'proc.stdout.on("data"', 'proc.stderr.on("data"');
  assert.ok(!/\blog\(/.test(stdoutHandler),
    "the gateway's stdout handler calls log() — that stream carries the bootstrap credential, and "
    + "log() persists to main-process.log AND mirrors to the renderer");
  assert.match(region, /proc\.stderr\.on\("data",\s*\(d\)\s*=>\s*log\(/,
    "stderr is the child stream that is meant to be logged; if this moved, the premise this unit "
    + "narrowed no longer holds");
});

test("W-40: the gateway is spawned with PIPED stdio, not an inherited console", () => {
  const region = resolveGatewayRegion();
  // The whole narrowing rests on this. `stdio: "inherit"` would put the credential on the shell's
  // own console — the exposure originally alleged — and every assertion above would still pass,
  // because they measure the child in isolation.
  assert.ok(!/stdio:\s*"inherit"/.test(region) && !/stdio:\s*'inherit'/.test(region),
    "the gateway's stdio is inherited: the credential now reaches a real console stream");
  assert.match(region, /proc\.stdout\.on\("data"/,
    "stdout must be consumed as a pipe by this process — that is what makes it private");
});

test("W-40: the renderer log sink is never handed the bootstrap line", () => {
  // (4). The renderer receives whatever `log()` produces (`rendererSink` in the logger). Since the
  // stdout handler never calls log(), the bootstrap line cannot reach it — this asserts the
  // remaining path, that nothing else in resolveGateway sends to the renderer directly.
  const region = resolveGatewayRegion();
  assert.ok(!/webContents\.send/.test(region),
    "resolveGateway sends directly to the renderer; the bootstrap credential is in scope there");
});
