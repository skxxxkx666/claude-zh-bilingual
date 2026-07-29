#!/usr/bin/env node
"use strict";

const fsp = require("node:fs/promises");
const path = require("node:path");
const { spawnSync } = require("node:child_process");


const SUPPORTED_CORPUS_VERSION = "2.1.220";


class CodeLayerBError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CodeLayerBError";
    this.code = code;
  }
}


async function readJson(filename) {
  return JSON.parse(await fsp.readFile(filename, "utf8"));
}


function readBinaryVersion(binaryPath) {
  const result = spawnSync(binaryPath, ["--version"], {
    cwd: path.dirname(binaryPath),
    encoding: "utf8",
    env: process.env,
    timeout: 30_000,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    throw new CodeLayerBError(
      "VERSION_CHECK_FAILED",
      `Could not read the Claude Code version from ${binaryPath}.`,
    );
  }
  const output = `${result.stdout || ""}\n${result.stderr || ""}`;
  const match = output.match(/\b(\d+\.\d+\.\d+)\b/);
  if (!match) {
    throw new CodeLayerBError(
      "VERSION_CHECK_FAILED",
      `Claude Code did not report a semantic version: ${binaryPath}.`,
    );
  }
  return match[1];
}


async function loadTranslations(projectRoot, mode) {
  if (mode === "passthrough") {
    return [];
  }
  if (mode !== "zh") {
    throw new CodeLayerBError(
      "INVALID_MODE",
      `Unsupported Layer B mode ${mode}; expected passthrough or zh.`,
    );
  }
  const corpus = await readJson(
    path.join(projectRoot, "corpus", "cli", "layer-b.json"),
  );
  if (corpus.version !== SUPPORTED_CORPUS_VERSION) {
    throw new CodeLayerBError(
      "CORPUS_VERSION_MISMATCH",
      `Expected CLI Layer B corpus ${SUPPORTED_CORPUS_VERSION}.`,
    );
  }
  const stringWidth = (await import("string-width")).default;
  const translations = [];
  for (const unit of corpus.units) {
    if (unit.risk !== "SAFE" || typeof unit.target !== "string") {
      continue;
    }
    const sourceWidth = stringWidth(unit.source);
    const targetWidth = stringWidth(unit.target);
    if (
      sourceWidth !== unit.display_width
      || targetWidth !== sourceWidth
    ) {
      throw new CodeLayerBError(
        "WIDTH_MISMATCH",
        `Layer B requires equal terminal width for unit ${unit.id}: ${sourceWidth} != ${targetWidth}.`,
      );
    }
    translations.push({
      id: unit.id,
      source: unit.source,
      target: unit.target,
      width: sourceWidth,
    });
  }
  if (translations.length === 0) {
    throw new CodeLayerBError(
      "EMPTY_CORPUS",
      "The Layer B corpus contains no equal-width SAFE translations.",
    );
  }
  translations.sort((left, right) => right.source.length - left.source.length);
  return translations;
}


function replaceAll(value, translations) {
  let replaced = value;
  for (const translation of translations) {
    replaced = replaced.split(translation.source).join(translation.target);
  }
  return replaced;
}


function createStreamingReplacer(translations) {
  if (translations.length === 0) {
    return {
      push: (value) => value,
      flush: () => "",
    };
  }
  const maximumLength = Math.max(
    ...translations.map((translation) => translation.source.length),
  );
  let pending = "";
  return {
    push(value) {
      pending += value;
      let splitAt = Math.max(0, pending.length - maximumLength + 1);
      let changed = true;
      while (changed && splitAt > 0) {
        changed = false;
        for (const translation of translations) {
          const start = pending.lastIndexOf(translation.source, splitAt - 1);
          if (
            start >= 0
            && start < splitAt
            && start + translation.source.length > splitAt
          ) {
            splitAt = start;
            changed = true;
          }
        }
      }
      const ready = pending.slice(0, splitAt);
      pending = pending.slice(splitAt);
      return replaceAll(ready, translations);
    },
    flush() {
      const ready = replaceAll(pending, translations);
      pending = "";
      return ready;
    },
  };
}


async function runPtyBridge(options = {}) {
  if (!options.binaryPath) {
    throw new CodeLayerBError(
      "BINARY_REQUIRED",
      "Layer B requires an explicit --binary path.",
    );
  }
  const platform = options.platform || process.platform;
  if (platform !== "win32") {
    throw new CodeLayerBError(
      "UNSUPPORTED_PLATFORM",
      "Layer B has only been verified on Windows and is disabled on this platform.",
    );
  }
  const projectRoot = path.resolve(
    options.projectRoot || path.join(__dirname, "..", ".."),
  );
  const binaryPath = path.resolve(options.binaryPath);
  const mode = options.mode || "zh";
  const versionReader = options.versionReader || readBinaryVersion;
  const version = await versionReader(binaryPath);
  if (version !== SUPPORTED_CORPUS_VERSION) {
    throw new CodeLayerBError(
      "UNSUPPORTED_VERSION",
      `Layer B supports Claude Code ${SUPPORTED_CORPUS_VERSION}; found ${version}.`,
    );
  }
  const translations = await loadTranslations(projectRoot, mode);
  const replacer = createStreamingReplacer(translations);
  const ptyModule = options.ptyModule || require("node-pty");
  const input = options.input || process.stdin;
  const output = options.output || process.stdout;
  const columns = Math.max(2, output.columns || 80);
  const rows = Math.max(1, output.rows || 24);
  const child = ptyModule.spawn(binaryPath, options.args || [], {
    name: process.env.TERM || "xterm-256color",
    cols: columns,
    rows,
    cwd: path.resolve(options.cwd || process.cwd()),
    env: { ...process.env },
    useConpty: true,
  });

  const wasRaw = input.isRaw === true;
  if (typeof input.setRawMode === "function") {
    input.setRawMode(true);
  }
  input.resume?.();
  const onInput = (data) => child.write(data.toString("utf8"));
  const onResize = () => {
    child.resize(
      Math.max(2, output.columns || 80),
      Math.max(1, output.rows || 24),
    );
  };
  input.on("data", onInput);
  output.on?.("resize", onResize);

  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      input.off?.("data", onInput);
      output.off?.("resize", onResize);
      if (typeof input.setRawMode === "function") {
        input.setRawMode(wasRaw);
      }
      input.pause?.();
    };
    child.onData((data) => {
      try {
        output.write(replacer.push(data));
      } catch (error) {
        if (!settled) {
          settled = true;
          cleanup();
          child.kill();
          reject(error);
        }
      }
    });
    child.onExit(({ exitCode, signal }) => {
      if (settled) {
        return;
      }
      settled = true;
      output.write(replacer.flush());
      cleanup();
      resolve({
        exitCode,
        signal,
        mode,
        version,
        translatedUnits: translations.length,
      });
    });
  });
}


function parseArguments(argv) {
  const options = {
    args: [],
    mode: "zh",
  };
  let passthrough = false;
  for (const argument of argv) {
    if (passthrough) {
      options.args.push(argument);
      continue;
    }
    if (argument === "--") {
      passthrough = true;
      continue;
    }
    const separator = argument.indexOf("=");
    if (!argument.startsWith("--") || separator < 0) {
      throw new CodeLayerBError(
        "INVALID_ARGUMENT",
        "Usage: cli-layer-b --binary=PATH [--mode=passthrough|zh] [-- ARGS...]",
      );
    }
    const name = argument.slice(2, separator);
    const value = argument.slice(separator + 1);
    if (!value) {
      throw new CodeLayerBError(
        "INVALID_ARGUMENT",
        `Option requires a value: --${name}`,
      );
    }
    if (name === "binary") {
      options.binaryPath = path.resolve(value);
    } else if (name === "mode") {
      options.mode = value;
    } else if (name === "cwd") {
      options.cwd = path.resolve(value);
    } else {
      throw new CodeLayerBError(
        "INVALID_ARGUMENT",
        `Unknown option: --${name}`,
      );
    }
  }
  if (!options.binaryPath) {
    throw new CodeLayerBError(
      "BINARY_REQUIRED",
      "Layer B requires an explicit --binary path.",
    );
  }
  return options;
}


async function main(argv = process.argv.slice(2)) {
  const options = parseArguments(argv);
  const result = await runPtyBridge(options);
  return result.exitCode;
}


if (require.main === module) {
  main().then(
    (exitCode) => {
      process.exit(exitCode);
    },
    (error) => {
      if (error instanceof CodeLayerBError) {
        console.error(`[${error.code}] ${error.message}`);
      } else {
        console.error(error && error.stack ? error.stack : String(error));
      }
      process.exit(1);
    },
  );
}


module.exports = {
  CodeLayerBError,
  SUPPORTED_CORPUS_VERSION,
  createStreamingReplacer,
  loadTranslations,
  main,
  parseArguments,
  readBinaryVersion,
  runPtyBridge,
};
