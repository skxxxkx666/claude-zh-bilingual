"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  DesktopPatchError,
} = require("../patchers/desktop-asar/index.cjs");
const {
  main,
  nodeVersionSupported,
  parseArguments,
  usage,
} = require("../bin/claude-zh.cjs");


test("parses the documented Desktop install command", () => {
  const result = parseArguments([
    "install",
    "desktop",
    "--mode=bilingual",
    "--app-root=C:\\Apps\\Claude",
  ]);

  assert.deepEqual(result.positional, ["install", "desktop"]);
  assert.equal(result.options.mode, "bilingual");
  assert.match(result.options.appRoot, /Claude$/);
});


test("parses the documented Claude Code Layer A install command", () => {
  const result = parseArguments([
    "install",
    "code",
    "--layer=a",
    "--mode=zh",
    "--config-root=C:\\Fixtures\\.claude",
  ]);

  assert.deepEqual(result.positional, ["install", "code"]);
  assert.equal(result.options.layer, "a");
  assert.equal(result.options.mode, "zh");
  assert.match(result.options.configRoot, /\.claude$/);
});


test("parses the documented Claude Code Layer B run command", () => {
  const result = parseArguments([
    "run",
    "code",
    "--layer=b",
    "--binary=C:\\Fixtures\\claude.exe",
    "--",
    "--model",
    "sonnet",
  ]);

  assert.deepEqual(result.positional, ["run", "code"]);
  assert.equal(result.options.layer, "b");
  assert.match(result.options.binaryPath, /claude\.exe$/);
  assert.deepEqual(result.options.forwardArgs, ["--model", "sonnet"]);
});


test("rejects unknown options", () => {
  assert.throws(
    () => parseArguments(["status", "--force=true"]),
    (error) => {
      assert.ok(error instanceof DesktopPatchError);
      assert.equal(error.code, "INVALID_ARGUMENT");
      return true;
    },
  );
});


test("usage lists install, restore, and status", () => {
  assert.match(usage(), /install desktop/);
  assert.match(usage(), /install code --layer=a/);
  assert.match(usage(), /run code --layer=b --binary=PATH/);
  assert.match(usage(), /restore desktop/);
  assert.match(usage(), /restore code/);
  assert.match(usage(), /status/);
  assert.match(usage(), /doctor \[--json\]/);
});


test("help prints usage and exits successfully", async () => {
  const messages = [];
  const originalLog = console.log;
  console.log = (message) => messages.push(message);
  try {
    assert.equal(await main(["--help"]), 0);
  } finally {
    console.log = originalLog;
  }
  assert.match(messages.join("\n"), /Usage:/);
});


test("parses the doctor JSON flag", () => {
  const result = parseArguments(["doctor", "--json"]);

  assert.deepEqual(result.positional, ["doctor"]);
  assert.equal(result.options.json, true);
});


test("doctor enforces the documented Node.js minimum", () => {
  assert.equal(nodeVersionSupported("22.11.0"), false);
  assert.equal(nodeVersionSupported("22.12.0"), true);
  assert.equal(nodeVersionSupported("23.0.0"), true);
});


test("doctor emits a read-only machine-readable report", async () => {
  const temporaryRoot = await fs.mkdtemp(
    path.join(os.tmpdir(), "claude-zh-doctor-"),
  );
  const messages = [];
  const originalLog = console.log;
  console.log = (message) => messages.push(message);
  try {
    const exitCode = await main([
      "doctor",
      "--json",
      `--app-root=${path.join(temporaryRoot, "missing-desktop")}`,
      `--config-root=${path.join(temporaryRoot, "config")}`,
      `--data-root=${path.join(temporaryRoot, "data")}`,
    ]);
    assert.equal(exitCode, 0);
    await assert.rejects(
      fs.access(path.join(temporaryRoot, "config")),
      (error) => error.code === "ENOENT",
    );
    await assert.rejects(
      fs.access(path.join(temporaryRoot, "data")),
      (error) => error.code === "ENOENT",
    );
  } finally {
    console.log = originalLog;
    await fs.rm(temporaryRoot, { recursive: true, force: true });
  }

  const report = JSON.parse(messages.join("\n"));
  assert.equal(report.schemaVersion, 1);
  assert.equal(report.overall, "ok");
  assert.deepEqual(
    report.checks.map((check) => check.id),
    ["node", "desktop", "code-layer-a"],
  );
});
