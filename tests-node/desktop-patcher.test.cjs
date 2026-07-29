"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  DesktopPatchError,
  installDesktop,
  restoreDesktop,
  sha256File,
  statusDesktop,
} = require("../patchers/desktop-asar/index.cjs");


const PROJECT_ROOT = path.resolve(__dirname, "..");
const SAFE_SETTINGS_SOURCE = "Could not load app settings";
const SAFE_SAVE_SOURCE = "Save";
const DANGER_SOURCE =
  "You are not logged in. Please log in to access the extensions directory.";


async function createFixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "claude-zh-test-"));
  t.after(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });
  const appRoot = path.join(root, "AnthropicClaude", "app-1.18286.0");
  const resources = path.join(appRoot, "resources");
  const sourceRoot = path.join(root, "asar-source");
  const dataRoot = path.join(root, "data");
  await fs.mkdir(path.join(sourceRoot, ".vite", "build"), { recursive: true });
  await fs.mkdir(path.join(resources, "ion-dist", "assets", "v1"), {
    recursive: true,
  });
  await fs.writeFile(
    path.join(sourceRoot, "package.json"),
    JSON.stringify({
      name: "@ant/desktop",
      version: "1.18286.0",
      main: ".vite/build/index.js",
    }),
    "utf8",
  );
  await fs.writeFile(
    path.join(sourceRoot, ".vite", "build", "index.js"),
    [
      `const settingsError = ${JSON.stringify(SAFE_SETTINGS_SOURCE)};`,
      `const danger = ${JSON.stringify(DANGER_SOURCE)};`,
      "module.exports = { settingsError, danger };",
    ].join("\n"),
    "utf8",
  );
  const asar = await import("@electron/asar");
  await asar.createPackage(sourceRoot, path.join(resources, "app.asar"));
  await fs.writeFile(
    path.join(resources, "en-US.json"),
    `${JSON.stringify({
      settingsError: SAFE_SETTINGS_SOURCE,
      save: SAFE_SAVE_SOURCE,
      danger: DANGER_SOURCE,
    }, null, 2)}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(resources, "ion-dist", "assets", "v1", "chunk.js"),
    [
      `export const save = ${JSON.stringify(SAFE_SAVE_SOURCE)};`,
      `export const danger = ${JSON.stringify(DANGER_SOURCE)};`,
    ].join("\n"),
    "utf8",
  );
  await fs.writeFile(path.join(appRoot, "claude.exe"), "fixture", "utf8");

  const corpus = JSON.parse(
    await fs.readFile(
      path.join(PROJECT_ROOT, "corpus", "desktop", "1.18286.0.json"),
      "utf8",
    ),
  );
  const bySource = new Map(corpus.units.map((unit) => [unit.source, unit]));
  return {
    appRoot,
    dataRoot,
    resources,
    bySource,
    asar,
  };
}


async function originalHashes(fixture) {
  const files = [
    path.join(fixture.resources, "app.asar"),
    path.join(fixture.resources, "en-US.json"),
    path.join(fixture.resources, "ion-dist", "assets", "v1", "chunk.js"),
  ];
  const result = new Map();
  for (const filename of files) {
    result.set(filename, await sha256File(filename));
  }
  return result;
}


async function assertOriginalFiles(fixture, hashes) {
  for (const [filename, expected] of hashes) {
    assert.equal(await sha256File(filename), expected, filename);
  }
  await assert.rejects(
    fs.access(path.join(fixture.resources, "zh-CN.json")),
  );
}


test("installs, reports status, and restores with exact SHA-256", async (t) => {
  const fixture = await createFixture(t);
  const hashes = await originalHashes(fixture);
  const settingsTarget = fixture.bySource.get(SAFE_SETTINGS_SOURCE).target;
  const saveTarget = fixture.bySource.get(SAFE_SAVE_SOURCE).target;

  const installed = await installDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
    projectRoot: PROJECT_ROOT,
    mode: "zh",
    isRunning: () => false,
  });

  assert.equal(installed.mode, "zh");
  assert.equal(installed.asarStrategy, "read-only-integrity-safe");
  assert.equal(installed.localeReplacements, 2);
  assert.equal(installed.hardcodedReplacements, 1);
  assert.equal(installed.patchedFiles, 3);
  assert.ok(await fs.stat(installed.backupRoot));
  assert.equal(
    await sha256File(path.join(fixture.resources, "app.asar")),
    hashes.get(path.join(fixture.resources, "app.asar")),
  );

  const extracted = path.join(path.dirname(fixture.appRoot), "patched-extracted");
  fixture.asar.extractAll(path.join(fixture.resources, "app.asar"), extracted);
  const asarJavaScript = await fs.readFile(
    path.join(extracted, ".vite", "build", "index.js"),
    "utf8",
  );
  assert.match(asarJavaScript, new RegExp(SAFE_SETTINGS_SOURCE));
  assert.match(asarJavaScript, new RegExp(DANGER_SOURCE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  const locale = JSON.parse(
    await fs.readFile(path.join(fixture.resources, "en-US.json"), "utf8"),
  );
  const chineseLocale = JSON.parse(
    await fs.readFile(path.join(fixture.resources, "zh-CN.json"), "utf8"),
  );
  assert.equal(locale.settingsError, settingsTarget);
  assert.equal(locale.save, saveTarget);
  assert.equal(locale.danger, DANGER_SOURCE);
  assert.deepEqual(chineseLocale, locale);

  const ion = await fs.readFile(
    path.join(fixture.resources, "ion-dist", "assets", "v1", "chunk.js"),
    "utf8",
  );
  assert.match(ion, new RegExp(saveTarget));
  assert.match(ion, new RegExp(DANGER_SOURCE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  const status = await statusDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(status.state, "managed");
  assert.equal(status.installations[0].state, "installed");
  assert.deepEqual(status.installations[0].mismatches, []);

  const restored = await restoreDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
    isRunning: () => false,
  });
  assert.equal(restored.verified, true);
  await assertOriginalFiles(fixture, hashes);

  const finalStatus = await statusDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(finalStatus.state, "not-installed");
  await assert.rejects(
    fs.stat(fixture.dataRoot),
    (error) => error.code === "ENOENT",
  );
});


test("bilingual mode uses generated bilingual targets", async (t) => {
  const fixture = await createFixture(t);
  const expected = fixture.bySource.get(SAFE_SETTINGS_SOURCE).target_bilingual;

  await installDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
    projectRoot: PROJECT_ROOT,
    mode: "bilingual",
    isRunning: () => false,
  });

  const locale = JSON.parse(
    await fs.readFile(path.join(fixture.resources, "en-US.json"), "utf8"),
  );
  assert.equal(locale.settingsError, expected);
  await restoreDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
    isRunning: () => false,
  });
});


test("forced mid-install failure restores every original file", async (t) => {
  const fixture = await createFixture(t);
  const hashes = await originalHashes(fixture);

  await assert.rejects(
    installDesktop({
      appRoot: fixture.appRoot,
      dataRoot: fixture.dataRoot,
      projectRoot: PROJECT_ROOT,
      mode: "zh",
      isRunning: () => false,
      hooks: {
        afterApply(count) {
          if (count === 2) {
            throw new Error("forced test failure");
          }
        },
      },
    }),
    (error) => {
      assert.ok(error instanceof DesktopPatchError);
      assert.equal(error.code, "INSTALL_FAILED_RESTORED");
      assert.match(error.message, /SHA-256 verified/);
      return true;
    },
  );

  await assertOriginalFiles(fixture, hashes);
  const state = await statusDesktop({
    appRoot: fixture.appRoot,
    dataRoot: fixture.dataRoot,
  });
  assert.equal(state.state, "not-installed");
});


test("running Claude blocks installation without changing files", async (t) => {
  const fixture = await createFixture(t);
  const hashes = await originalHashes(fixture);

  await assert.rejects(
    installDesktop({
      appRoot: fixture.appRoot,
      dataRoot: fixture.dataRoot,
      projectRoot: PROJECT_ROOT,
      mode: "zh",
      isRunning: () => true,
    }),
    (error) => {
      assert.equal(error.code, "CLAUDE_RUNNING");
      return true;
    },
  );

  await assertOriginalFiles(fixture, hashes);
  await assert.rejects(fs.access(fixture.dataRoot));
});
