#!/usr/bin/env node
"use strict";

const path = require("node:path");
const {
  DesktopPatchError,
  installDesktop,
  restoreDesktop,
  statusDesktop,
} = require("../patchers/desktop-asar/index.cjs");
const {
  CodeLayerError,
  installCodeLayerA,
  restoreCodeLayerA,
  statusCodeLayerA,
} = require("../patchers/cli-layer-a/index.cjs");
const {
  CodeLayerBError,
  runPtyBridge,
} = require("../patchers/cli-layer-b/index.cjs");


function usage() {
  return [
    "Usage:",
    "  claude-zh install desktop [--mode=zh|bilingual] [--app-root=PATH]",
    "  claude-zh install code --layer=a [--mode=zh|bilingual]",
    "  claude-zh run code --layer=b --binary=PATH [-- CLAUDE_ARGS...]",
    "  claude-zh restore desktop [--app-root=PATH]",
    "  claude-zh restore code",
    "  claude-zh status [desktop|code] [--app-root=PATH]",
    "  claude-zh --help",
  ].join("\n");
}


function parseArguments(argv) {
  const positional = [];
  const options = { forwardArgs: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--") {
      options.forwardArgs = argv.slice(index + 1);
      break;
    }
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
    } else if (name === "config-root") {
      options.configRoot = path.resolve(value);
    } else if (name === "layer") {
      options.layer = value;
    } else if (name === "binary") {
      options.binaryPath = path.resolve(value);
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
  if (
    command === "install"
    && target === "code"
    && positional.length === 2
    && options.layer === "a"
  ) {
    const result = await installCodeLayerA(options);
    console.log(`Installed Claude Code Layer A in ${result.mode} mode.`);
    console.log(`Config: ${result.configRoot}`);
    console.log(`Backup: ${result.backupRoot}`);
    console.log(`Plugin: ${result.pluginRoot}`);
    if (result.skippedSettings.length > 0) {
      console.log(`Preserved existing settings: ${result.skippedSettings.join(", ")}`);
    }
    if (result.skippedAssets.length > 0) {
      console.log(`Preserved existing files: ${result.skippedAssets.join(", ")}`);
    }
    return 0;
  }
  if (
    command === "run"
    && target === "code"
    && positional.length === 2
    && options.layer === "b"
  ) {
    const result = await runPtyBridge({
      ...options,
      args: options.forwardArgs,
      mode: "zh",
    });
    return result.exitCode;
  }
  if (command === "restore" && target === "desktop" && positional.length === 2) {
    const result = await restoreDesktop(options);
    console.log(
      `Restored ${result.restoredFiles} file(s); original SHA-256 values verified.`,
    );
    console.log(`App: ${result.appRoot}`);
    return 0;
  }
  if (command === "restore" && target === "code" && positional.length === 2) {
    const result = await restoreCodeLayerA(options);
    console.log(
      result.exactSettingsRestore
        ? "Restored the original Claude Code settings byte-for-byte."
        : "Removed managed settings and preserved later user changes.",
    );
    console.log(`Config: ${result.configRoot}`);
    console.log(`Backup retained at: ${result.backupRoot}`);
    if (result.preservedSettings.length > 0) {
      console.log(`Preserved changed settings: ${result.preservedSettings.join(", ")}`);
    }
    if (result.preservedAssets.length > 0) {
      console.log(`Preserved changed files: ${result.preservedAssets.join(", ")}`);
    }
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
  if (command === "status" && target === "code" && positional.length === 2) {
    const result = await statusCodeLayerA(options);
    console.log(JSON.stringify(result, null, 2));
    return 0;
  }
  throw new DesktopPatchError("INVALID_ARGUMENT", usage());
}


if (require.main === module) {
  const isPtyRun = process.argv.slice(2).includes("--layer=b");
  main().then((exitCode) => {
    if (isPtyRun) {
      process.exit(exitCode);
    }
    process.exitCode = exitCode;
  }).catch((error) => {
    if (
      error instanceof DesktopPatchError
      || error instanceof CodeLayerError
      || error instanceof CodeLayerBError
    ) {
      console.error(`[${error.code}] ${error.message}`);
    } else {
      console.error(error && error.stack ? error.stack : String(error));
    }
    if (isPtyRun) {
      process.exit(1);
    }
    process.exitCode = 1;
  });
}


module.exports = { main, parseArguments, usage };
