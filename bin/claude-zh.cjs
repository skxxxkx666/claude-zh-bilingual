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
const packageMetadata = require("../package.json");


function usage() {
  return [
    "Usage:",
    "  claude-zh install desktop [--mode=zh|bilingual] [--app-root=PATH]",
    "  claude-zh install code --layer=a [--mode=zh|bilingual]",
    "  claude-zh run code --layer=b --binary=PATH [-- CLAUDE_ARGS...]",
    "  claude-zh restore desktop [--app-root=PATH]",
    "  claude-zh restore code",
    "  claude-zh status [desktop|code] [--app-root=PATH]",
    "  claude-zh doctor [--json] [--app-root=PATH]",
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
    if (argument === "--json") {
      options.json = true;
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


function nodeVersionSupported(version = process.versions.node) {
  const [major, minor] = version.split(".").map(Number);
  return major > 22 || (major === 22 && minor >= 12);
}


function desktopDoctorCheck(status) {
  if (status.state === "managed") {
    const changed = status.installations.filter(
      (installation) => installation.state !== "installed",
    );
    return changed.length === 0
      ? {
          id: "desktop",
          level: "pass",
          message: `${status.installations.length} managed installation(s) verified.`,
          details: status,
        }
      : {
          id: "desktop",
          level: "warning",
          message: `${changed.length} managed installation(s) changed after installation.`,
          details: status,
        };
  }
  if (status.state === "msix-unsupported") {
    return {
      id: "desktop",
      level: "warning",
      message: "MSIX installation detected; this project will not modify WindowsApps.",
      details: status,
    };
  }
  if (status.state === "not-installed") {
    return {
      id: "desktop",
      level: "info",
      message: "Supported Desktop installation found; localization is not installed.",
      details: status,
    };
  }
  return {
    id: "desktop",
    level: "info",
    message: "Claude Desktop was not found.",
    details: status,
  };
}


function codeDoctorCheck(status) {
  if (status.state === "not-installed") {
    return {
      id: "code-layer-a",
      level: "info",
      message: "Claude Code Layer A is not installed.",
      details: status,
    };
  }
  if (status.state === "installed" && status.mismatches.length === 0) {
    return {
      id: "code-layer-a",
      level: "pass",
      message: "Claude Code Layer A managed files verified.",
      details: status,
    };
  }
  return {
    id: "code-layer-a",
    level: "warning",
    message: status.mismatches.length > 0
      ? `${status.mismatches.length} managed Claude Code file(s) changed after installation.`
      : `Unexpected Claude Code Layer A state: ${status.state}.`,
    details: status,
  };
}


async function doctor(options = {}) {
  const supportedNode = nodeVersionSupported();
  const checks = [
    {
      id: "node",
      level: supportedNode ? "pass" : "error",
      message: supportedNode
        ? `Node.js ${process.versions.node} satisfies ${packageMetadata.engines.node}.`
        : `Node.js ${process.versions.node} does not satisfy ${packageMetadata.engines.node}.`,
    },
  ];

  try {
    checks.push(desktopDoctorCheck(await statusDesktop(options)));
  } catch (error) {
    checks.push({
      id: "desktop",
      level: "error",
      message: error instanceof Error ? error.message : String(error),
    });
  }
  try {
    checks.push(codeDoctorCheck(await statusCodeLayerA(options)));
  } catch (error) {
    checks.push({
      id: "code-layer-a",
      level: "error",
      message: error instanceof Error ? error.message : String(error),
    });
  }

  const overall = checks.some((check) => check.level === "error")
    ? "error"
    : checks.some((check) => check.level === "warning")
      ? "attention"
      : "ok";
  return {
    schemaVersion: 1,
    toolVersion: packageMetadata.version,
    platform: process.platform,
    arch: process.arch,
    overall,
    checks,
  };
}


function formatDoctorReport(report) {
  const labels = {
    pass: "PASS",
    info: "INFO",
    warning: "WARN",
    error: "ERROR",
  };
  return [
    `claude-zh doctor ${report.toolVersion}`,
    `Platform: ${report.platform} ${report.arch}`,
    "",
    ...report.checks.map(
      (check) => `[${labels[check.level]}] ${check.id}: ${check.message}`,
    ),
    "",
    `Result: ${report.overall.toUpperCase()}`,
    "Use --json for a machine-readable report.",
  ].join("\n");
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
  if (command === "doctor" && target === undefined && positional.length === 1) {
    const report = await doctor(options);
    console.log(
      options.json
        ? JSON.stringify(report, null, 2)
        : formatDoctorReport(report),
    );
    return report.overall === "error" ? 2 : report.overall === "attention" ? 1 : 0;
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


module.exports = {
  main,
  parseArguments,
  usage,
};
