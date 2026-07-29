"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  DesktopPatchError,
} = require("../patchers/desktop-asar/index.cjs");
const {
  main,
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
  assert.match(usage(), /restore desktop/);
  assert.match(usage(), /status/);
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
