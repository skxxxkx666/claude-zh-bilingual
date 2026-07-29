"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  installCodeLayerA,
  restoreCodeLayerA,
  statusCodeLayerA,
} = require("../patchers/cli-layer-a/index.cjs");


const PROJECT_ROOT = path.resolve(__dirname, "..");


async function createFixture(t, settings) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "claude-zh-code-test-"));
  t.after(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });
  const configRoot = path.join(root, ".claude");
  const dataRoot = path.join(root, "data");
  await fs.mkdir(configRoot, { recursive: true });
  let originalBytes = null;
  if (settings !== undefined) {
    originalBytes = Buffer.from(`${JSON.stringify(settings, null, 4)}\r\n`, "utf8");
    await fs.writeFile(path.join(configRoot, "settings.json"), originalBytes);
  }
  return { configRoot, dataRoot, originalBytes };
}


async function readSettings(fixture) {
  return JSON.parse(
    await fs.readFile(path.join(fixture.configRoot, "settings.json"), "utf8"),
  );
}


test("installs Layer A by merging settings and restores original bytes", async (t) => {
  const customStatusLine = {
    type: "command",
    command: "node custom-statusline.cjs",
  };
  const fixture = await createFixture(t, {
    model: "sonnet",
    statusLine: customStatusLine,
    hooks: {
      SessionStart: [
        {
          matcher: "resume",
          hooks: [{ type: "command", command: "node custom-hook.cjs" }],
        },
      ],
    },
  });

  const installed = await installCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
    projectRoot: PROJECT_ROOT,
    mode: "zh",
  });
  assert.ok(await fs.stat(installed.backupRoot));
  assert.ok(installed.skippedSettings.includes("statusLine"));

  const settings = await readSettings(fixture);
  assert.deepEqual(settings.statusLine, customStatusLine);
  assert.equal(typeof settings.outputStyle, "string");
  assert.equal(settings.hooks.SessionStart.length, 2);
  assert.equal(settings.hooks.SessionStart[0].matcher, "resume");
  assert.equal(settings.hooks.SessionStart[1].matcher, "startup");
  assert.ok(await fs.stat(path.join(fixture.configRoot, "claude-zh", "statusline.cjs")));
  assert.ok(await fs.stat(path.join(fixture.configRoot, "skills")));

  const status = await statusCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(status.state, "installed");
  assert.deepEqual(status.mismatches, []);

  const restored = await restoreCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(restored.exactSettingsRestore, true);
  assert.deepEqual(
    await fs.readFile(path.join(fixture.configRoot, "settings.json")),
    fixture.originalBytes,
  );
  assert.deepEqual(
    (await statusCodeLayerA({
      configRoot: fixture.configRoot,
      dataRoot: fixture.dataRoot,
    })).state,
    "not-installed",
  );
});


test("fresh config receives visible settings and restores to no settings file", async (t) => {
  const fixture = await createFixture(t);
  await installCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
    projectRoot: PROJECT_ROOT,
    mode: "bilingual",
  });
  const settings = await readSettings(fixture);
  assert.equal(settings.statusLine.type, "command");
  assert.match(settings.statusLine.command, /statusline\.cjs/);
  assert.equal(typeof settings.outputStyle, "string");
  assert.equal(settings.hooks.SessionStart.length, 1);

  await restoreCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
  });
  await assert.rejects(
    fs.access(path.join(fixture.configRoot, "settings.json")),
    (error) => error.code === "ENOENT",
  );
});


test("restore removes only unchanged managed values and preserves later edits", async (t) => {
  const fixture = await createFixture(t, { effortLevel: "high" });
  await installCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
    projectRoot: PROJECT_ROOT,
    mode: "zh",
  });
  const settings = await readSettings(fixture);
  settings.statusLine = {
    type: "command",
    command: "node user-replacement.cjs",
  };
  settings.outputStyle = "User Style";
  settings.userAddedAfterInstall = true;
  await fs.writeFile(
    path.join(fixture.configRoot, "settings.json"),
    `${JSON.stringify(settings, null, 2)}\n`,
    "utf8",
  );
  const editedAsset = path.join(fixture.configRoot, "claude-zh", "catalog.json");
  await fs.appendFile(editedAsset, "\n", "utf8");

  const restored = await restoreCodeLayerA({
    configRoot: fixture.configRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(restored.exactSettingsRestore, false);
  assert.ok(restored.preservedSettings.includes("statusLine"));
  assert.ok(restored.preservedSettings.includes("outputStyle"));
  assert.ok(restored.preservedAssets.includes(path.join("claude-zh", "catalog.json")));
  const finalSettings = await readSettings(fixture);
  assert.equal(finalSettings.userAddedAfterInstall, true);
  assert.equal(finalSettings.statusLine.command, "node user-replacement.cjs");
  assert.equal(finalSettings.outputStyle, "User Style");
  assert.equal(finalSettings.hooks, undefined);
  assert.ok(await fs.stat(editedAsset));
});


test("forced installation failure restores settings and generated files", async (t) => {
  const fixture = await createFixture(t, { model: "opus" });
  await assert.rejects(
    installCodeLayerA({
      configRoot: fixture.configRoot,
      dataRoot: fixture.dataRoot,
      projectRoot: PROJECT_ROOT,
      mode: "zh",
      hooks: {
        afterApply(count) {
          if (count === 3) {
            throw new Error("forced test failure");
          }
        },
      },
    }),
    /managed changes were rolled back/,
  );
  assert.deepEqual(
    await fs.readFile(path.join(fixture.configRoot, "settings.json")),
    fixture.originalBytes,
  );
  await assert.rejects(
    fs.access(path.join(fixture.configRoot, "claude-zh", "catalog.json")),
    (error) => error.code === "ENOENT",
  );
  assert.equal(
    (await statusCodeLayerA({
      configRoot: fixture.configRoot,
      dataRoot: fixture.dataRoot,
    })).state,
    "not-installed",
  );
});


test("concurrent settings edits abort installation and preserve the new bytes", async (t) => {
  const fixture = await createFixture(t, { model: "opus" });
  const changedBytes = Buffer.from(
    `${JSON.stringify({ model: "sonnet", changedDuringInstall: true }, null, 2)}\n`,
    "utf8",
  );
  await assert.rejects(
    installCodeLayerA({
      configRoot: fixture.configRoot,
      dataRoot: fixture.dataRoot,
      projectRoot: PROJECT_ROOT,
      mode: "zh",
      hooks: {
        async afterApply(count) {
          if (count === 3) {
            await fs.writeFile(
              path.join(fixture.configRoot, "settings.json"),
              changedBytes,
            );
          }
        },
      },
    }),
    /current user settings were preserved/,
  );
  assert.deepEqual(
    await fs.readFile(path.join(fixture.configRoot, "settings.json")),
    changedBytes,
  );
  await assert.rejects(
    fs.access(path.join(fixture.configRoot, "claude-zh", "catalog.json")),
    (error) => error.code === "ENOENT",
  );
  assert.equal(
    (await statusCodeLayerA({
      configRoot: fixture.configRoot,
      dataRoot: fixture.dataRoot,
    })).state,
    "not-installed",
  );
});
