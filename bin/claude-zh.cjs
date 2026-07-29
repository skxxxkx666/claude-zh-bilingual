#!/usr/bin/env node
"use strict";

const path = require("node:path");
const {
  DesktopPatchError,
  installDesktop,
  restoreDesktop,
  statusDesktop,
} = require("../patchers/desktop-asar/index.cjs");


function usage() {
  return [
    "Usage:",
    "  claude-zh install desktop [--mode=zh|bilingual] [--app-root=PATH]",
    "  claude-zh restore desktop [--app-root=PATH]",
    "  claude-zh status [desktop] [--app-root=PATH]",
    "  claude-zh --help",
  ].join("\n");
}


function parseArguments(argv) {
  const positional = [];
  const options = {};
  for (const argument of argv) {
    if (!argument.startsWith("--")) {
      positional.push(argument);
      continue;
    }
    const separator = argument.indexOf("=");
    if (separator < 0) {
      throw new DesktopPatchError(
        "INVALID_ARGUMENT",
        `Option requires a value: ${argument}`,
      );
    }
    const name = argument.slice(2, separator);
    const value = argument.slice(separator + 1);
    if (!value) {
      throw new DesktopPatchError(
        "INVALID_ARGUMENT",
        `Option requires a value: --${name}`,
      );
    }
    if (name === "mode") {
      options.mode = value;
    } else if (name === "app-root") {
      options.appRoot = path.resolve(value);
    } else if (name === "data-root") {
      options.dataRoot = path.resolve(value);
    } else {
      throw new DesktopPatchError(
        "INVALID_ARGUMENT",
        `Unknown option: --${name}`,
      );
    }
  }
  return { positional, options };
}


async function main(argv = process.argv.slice(2)) {
  if (
    argv.length === 0
    || (argv.length === 1 && (argv[0] === "--help" || argv[0] === "-h"))
  ) {
    console.log(usage());
    return 0;
  }
  const { positional, options } = parseArguments(argv);
  const [command, target] = positional;
  if (command === "install" && target === "desktop" && positional.length === 2) {
    const result = await installDesktop(options);
    console.log(`Installed Desktop ${result.mode} mode.`);
    console.log(`App: ${result.appRoot}`);
    console.log(`Backup: ${result.backupRoot}`);
    console.log(`ASAR: ${result.asarStrategy}`);
    console.log(
      `Patched ${result.patchedFiles} file(s), ${result.localeReplacements} locale value(s), `
      + `${result.hardcodedReplacements} hardcoded literal(s).`,
    );
    return 0;
  }
  if (command === "restore" && target === "desktop" && positional.length === 2) {
    const result = await restoreDesktop(options);
    console.log(
      `Restored ${result.restoredFiles} file(s); original SHA-256 values verified.`,
    );
    console.log(`App: ${result.appRoot}`);
    return 0;
  }
  if (
    command === "status"
    && (target === undefined || target === "desktop")
    && positional.length <= 2
  ) {
    const result = await statusDesktop(options);
    console.log(JSON.stringify(result, null, 2));
    return 0;
  }
  throw new DesktopPatchError("INVALID_ARGUMENT", usage());
}


if (require.main === module) {
  main().catch((error) => {
    if (error instanceof DesktopPatchError) {
      console.error(`[${error.code}] ${error.message}`);
    } else {
      console.error(error && error.stack ? error.stack : String(error));
    }
    process.exitCode = 1;
  });
}


module.exports = { main, parseArguments, usage };
