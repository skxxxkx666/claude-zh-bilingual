"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  CodeLayerBError,
  createStreamingReplacer,
  loadTranslations,
  parseArguments,
  runPtyBridge,
} = require("../patchers/cli-layer-b/index.cjs");
const LAYER_B_CORPUS = require("../corpus/cli/layer-b.json");


const PROJECT_ROOT = path.resolve(__dirname, "..");
const VERSION = "2.1.220";
const SPINNER = LAYER_B_CORPUS.units.find(
  (unit) => unit.surface === "cli.pty.spinner",
);


class FakeInput extends EventEmitter {
  constructor() {
    super();
    this.isRaw = false;
    this.paused = false;
  }

  setRawMode(value) {
    this.isRaw = value;
  }

  resume() {
    this.paused = false;
  }

  pause() {
    this.paused = true;
  }
}


class FakeOutput extends EventEmitter {
  constructor() {
    super();
    this.columns = 80;
    this.rows = 24;
    this.value = "";
  }

  write(value) {
    this.value += value;
    return true;
  }
}


function fakePty() {
  let dataHandler;
  let exitHandler;
  let resolveSpawned;
  const spawned = new Promise((resolve) => {
    resolveSpawned = resolve;
  });
  const child = {
    writes: [],
    resizes: [],
    killed: false,
    write(value) {
      this.writes.push(value);
    },
    resize(columns, rows) {
      this.resizes.push([columns, rows]);
    },
    kill() {
      this.killed = true;
    },
    onData(handler) {
      dataHandler = handler;
    },
    onExit(handler) {
      exitHandler = handler;
    },
    emitData(value) {
      dataHandler(value);
    },
    emitExit(exitCode = 0, signal = 0) {
      exitHandler({ exitCode, signal });
    },
  };
  return {
    child,
    spawned,
    module: {
      spawn() {
        resolveSpawned(child);
        return child;
      },
    },
  };
}


test("streaming replacement survives chunk boundaries and preserves ANSI", () => {
  const replacer = createStreamingReplacer([
    {
      source: SPINNER.source,
      target: SPINNER.target,
    },
  ]);
  const output = [
    replacer.push("\u001b[32mThink"),
    replacer.push("ing…\u001b[0m"),
    replacer.flush(),
  ].join("");
  assert.equal(output, `\u001b[32m${SPINNER.target}\u001b[0m`);
});


test("passthrough mode forwards bytes, input, and terminal resize", async () => {
  const input = new FakeInput();
  const output = new FakeOutput();
  const pty = fakePty();
  const running = runPtyBridge({
    binaryPath: "C:\\Fixtures\\claude.exe",
    mode: "passthrough",
    platform: "win32",
    versionReader: () => VERSION,
    ptyModule: pty.module,
    input,
    output,
  });
  const child = await pty.spawned;
  child.emitData("\u001b[2Jhello");
  child.emitData("\u001b[H");
  input.emit("data", Buffer.from("/help\r", "utf8"));
  output.columns = 120;
  output.rows = 40;
  output.emit("resize");
  child.emitExit(0, 0);

  const result = await running;
  assert.equal(output.value, "\u001b[2Jhello\u001b[H");
  assert.deepEqual(child.writes, ["/help\r"]);
  assert.deepEqual(child.resizes, [[120, 40]]);
  assert.equal(input.isRaw, false);
  assert.equal(input.paused, true);
  assert.equal(result.translatedUnits, 0);
});


test("zh mode loads only equal-width SAFE translations", async () => {
  const translations = await loadTranslations(PROJECT_ROOT, "zh");
  assert.deepEqual(
    translations.map((translation) => translation.source),
    ["Thinking…"],
  );
  assert.ok(
    translations.every((translation) => translation.width > 0),
  );
});


test("zh bridge replaces reviewed text and leaves other output unchanged", async () => {
  const input = new FakeInput();
  const output = new FakeOutput();
  const pty = fakePty();
  const running = runPtyBridge({
    binaryPath: "C:\\Fixtures\\claude.exe",
    mode: "zh",
    platform: "win32",
    projectRoot: PROJECT_ROOT,
    versionReader: () => VERSION,
    ptyModule: pty.module,
    input,
    output,
  });
  const child = await pty.spawned;
  child.emitData("· Think");
  child.emitData("ing… | manual ");
  child.emitData("mode on | unchanged");
  child.emitExit(0, 0);
  const result = await running;

  assert.equal(
    output.value,
    `· ${SPINNER.target} | manual mode on | unchanged`,
  );
  assert.equal(result.translatedUnits, 1);
});


test("load rejects a target with a different terminal width", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "claude-zh-width-test-"));
  t.after(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });
  const corpusPath = path.join(root, "corpus", "cli", "layer-b.json");
  await fs.mkdir(path.dirname(corpusPath), { recursive: true });
  await fs.writeFile(
    corpusPath,
    `${JSON.stringify({
      version: VERSION,
      units: [
        {
          id: "a02f1cea3c1d6c6e",
          source: "Thinking…",
          target: "x",
          risk: "SAFE",
          display_width: 9,
        },
      ],
    })}\n`,
    "utf8",
  );
  await assert.rejects(
    loadTranslations(root, "zh"),
    (error) => {
      assert.ok(error instanceof CodeLayerBError);
      assert.equal(error.code, "WIDTH_MISMATCH");
      return true;
    },
  );
});


test("parses wrapper options and forwards arguments after separator", () => {
  const options = parseArguments([
    "--binary=C:\\Fixtures\\claude.exe",
    "--mode=passthrough",
    "--",
    "--model",
    "sonnet",
  ]);
  assert.match(options.binaryPath, /claude\.exe$/);
  assert.equal(options.mode, "passthrough");
  assert.deepEqual(options.args, ["--model", "sonnet"]);
});


test("bridge refuses to discover or guess a Claude binary", async () => {
  await assert.rejects(
    runPtyBridge({}),
    (error) => {
      assert.equal(error.code, "BINARY_REQUIRED");
      return true;
    },
  );
});


test("bridge fails closed on an unverified platform", async () => {
  await assert.rejects(
    runPtyBridge({
      binaryPath: "/tmp/claude",
      platform: "linux",
    }),
    (error) => {
      assert.equal(error.code, "UNSUPPORTED_PLATFORM");
      return true;
    },
  );
});
