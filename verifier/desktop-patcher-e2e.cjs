#!/usr/bin/env node
"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");

const {
  installDesktop,
  restoreDesktop,
  sha256File,
  statusDesktop,
} = require("../patchers/desktop-asar/index.cjs");


async function listFiles(root) {
  const result = [];
  const pending = [root];
  while (pending.length > 0) {
    const current = pending.pop();
    const entries = await fs.readdir(current, { withFileTypes: true });
    for (const entry of entries) {
      const filename = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(filename);
      } else if (entry.isFile()) {
        result.push(filename);
      }
    }
  }
  return result.sort();
}


async function snapshot(root) {
  const hashes = new Map();
  for (const filename of await listFiles(root)) {
    hashes.set(path.relative(root, filename), await sha256File(filename));
  }
  return hashes;
}


async function main(argv = process.argv.slice(2)) {
  const appRootArgument = argv.find((argument) =>
    argument.startsWith("--fixture-root="),
  );
  const dataRootArgument = argv.find((argument) =>
    argument.startsWith("--data-root="),
  );
  if (!appRootArgument || !dataRootArgument || argv.length !== 2) {
    throw new Error(
      "Usage: node verifier/desktop-patcher-e2e.cjs "
      + "--fixture-root=PATH --data-root=PATH",
    );
  }
  const appRoot = path.resolve(appRootArgument.slice("--fixture-root=".length));
  const dataRoot = path.resolve(dataRootArgument.slice("--data-root=".length));
  const normalized = appRoot.toLowerCase().replace(/\\/g, "/");
  if (!normalized.includes("/samples/desktop/")) {
    throw new Error("The E2E verifier only accepts a samples/desktop fixture.");
  }

  const before = await snapshot(appRoot);
  const installed = await installDesktop({
    appRoot,
    dataRoot,
    projectRoot: path.resolve(__dirname, ".."),
    mode: "zh",
    isRunning: () => false,
  });
  const status = await statusDesktop({ appRoot, dataRoot });
  if (
    status.state !== "managed"
    || status.installations[0].state !== "installed"
  ) {
    throw new Error("Installed fixture failed the managed status check.");
  }
  const restored = await restoreDesktop({
    appRoot,
    dataRoot,
    isRunning: () => false,
  });
  const after = await snapshot(appRoot);
  if (before.size !== after.size) {
    throw new Error("Restore left a different number of fixture files.");
  }
  for (const [relative, expectedHash] of before) {
    if (after.get(relative) !== expectedHash) {
      throw new Error(`Restore hash mismatch: ${relative}`);
    }
  }
  console.log(JSON.stringify({
    corpusVersion: installed.corpusVersion,
    asarStrategy: installed.asarStrategy,
    localeReplacements: installed.localeReplacements,
    hardcodedReplacements: installed.hardcodedReplacements,
    hardcodedFilesChanged: installed.hardcodedFilesChanged,
    patchedFiles: installed.patchedFiles,
    restoredFiles: restored.restoredFiles,
    sha256Verified: restored.verified,
    residueFree: before.size === after.size,
  }, null, 2));
}


if (require.main === module) {
  main().catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exitCode = 1;
  });
}
