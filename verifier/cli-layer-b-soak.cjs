#!/usr/bin/env node
"use strict";

const fsp = require("node:fs/promises");
const path = require("node:path");
const pty = require("node-pty");

const {
  SUPPORTED_CORPUS_VERSION,
  createStreamingReplacer,
  loadTranslations,
  readBinaryVersion,
} = require("../patchers/cli-layer-b/index.cjs");


function parseArguments(argv) {
  const options = {
    durationMinutes: 30,
  };
  for (const argument of argv) {
    const separator = argument.indexOf("=");
    if (!argument.startsWith("--") || separator < 0) {
      throw new Error(
        "Usage: cli-layer-b-soak --binary=PATH --report=PATH [--duration-minutes=30]",
      );
    }
    const name = argument.slice(2, separator);
    const value = argument.slice(separator + 1);
    if (name === "binary") {
      options.binaryPath = path.resolve(value);
    } else if (name === "report") {
      options.reportPath = path.resolve(value);
    } else if (name === "duration-minutes") {
      options.durationMinutes = Number(value);
    } else {
      throw new Error(`Unknown option: --${name}`);
    }
  }
  if (!options.binaryPath || !options.reportPath) {
    throw new Error("--binary and --report are required.");
  }
  if (
    !Number.isFinite(options.durationMinutes)
    || options.durationMinutes <= 0
  ) {
    throw new Error("--duration-minutes must be positive.");
  }
  return options;
}


function occurrences(value, needle) {
  let count = 0;
  let offset = 0;
  while (true) {
    const found = value.indexOf(needle, offset);
    if (found < 0) {
      return count;
    }
    count += 1;
    offset = found + needle.length;
  }
}


async function runSoak(options) {
  const projectRoot = path.resolve(__dirname, "..");
  const version = readBinaryVersion(options.binaryPath);
  if (version !== SUPPORTED_CORPUS_VERSION) {
    throw new Error(
      `Layer B soak supports ${SUPPORTED_CORPUS_VERSION}; found ${version}.`,
    );
  }
  const translations = await loadTranslations(projectRoot, "zh");
  const replacer = createStreamingReplacer(translations);
  const target = translations[0].target;
  const startedAt = new Date();
  const requestedMilliseconds = options.durationMinutes * 60_000;
  const sizes = [
    [100, 30],
    [72, 24],
    [120, 40],
  ];
  let sizeIndex = 0;
  let resizeEvents = 0;
  let helpCycles = 0;
  let ansiSequences = 0;
  let translatedHits = 0;
  let monitorTail = "";
  let sawHelp = false;
  let forcedKill = false;
  let ending = false;
  let cycleTimer;
  let endTimer;
  let killTimer;

  const child = pty.spawn(
    options.binaryPath,
    [
      "--model",
      "claude-sonnet-5",
      "--setting-sources",
      "user",
      "--settings",
      JSON.stringify({
        spinnerVerbs: {
          mode: "replace",
          verbs: ["Thinking"],
        },
      }),
    ],
    {
      name: "xterm-256color",
      cols: sizes[0][0],
      rows: sizes[0][1],
      cwd: projectRoot,
      env: { ...process.env },
      useConpty: process.platform === "win32",
    },
  );

  const observe = (value) => {
    const combined = monitorTail + value;
    translatedHits += occurrences(combined, target)
      - occurrences(monitorTail, target);
    sawHelp ||= combined.includes("For more help:");
    monitorTail = combined.slice(-256);
  };

  setTimeout(() => {
    if (!ending) {
      child.write("Reply with the single word OK.\r");
    }
  }, 4_000);

  cycleTimer = setInterval(() => {
    if (ending) {
      return;
    }
    sizeIndex = (sizeIndex + 1) % sizes.length;
    child.resize(sizes[sizeIndex][0], sizes[sizeIndex][1]);
    resizeEvents += 1;
    child.write("/help\r");
    helpCycles += 1;
    setTimeout(() => {
      if (!ending) {
        child.write("\u001b");
      }
    }, 2_000);
    process.stdout.write(
      `${JSON.stringify({
        elapsedMinutes: Number(
          ((Date.now() - startedAt.getTime()) / 60_000).toFixed(1),
        ),
        resizeEvents,
        helpCycles,
        translatedHits,
      })}\n`,
    );
  }, 60_000);

  endTimer = setTimeout(() => {
    ending = true;
    clearInterval(cycleTimer);
    child.write("\u001b");
    setTimeout(() => {
      child.write("/exit\r");
      killTimer = setTimeout(() => {
        forcedKill = true;
        child.kill();
      }, 15_000);
    }, 250);
  }, requestedMilliseconds);

  return new Promise((resolve) => {
    child.onData((data) => {
      ansiSequences += (data.match(/\u001b\[[0-?]*[ -/]*[@-~]/g) || []).length;
      observe(replacer.push(data));
    });
    child.onExit(async ({ exitCode, signal }) => {
      clearInterval(cycleTimer);
      clearTimeout(endTimer);
      clearTimeout(killTimer);
      observe(replacer.flush());
      const endedAt = new Date();
      const actualSeconds = (
        (endedAt.getTime() - startedAt.getTime()) / 1000
      );
      const protocolFailures = [];
      if (actualSeconds + 1 < requestedMilliseconds / 1000) {
        protocolFailures.push("child exited before requested duration");
      }
      if (translatedHits === 0) {
        protocolFailures.push("translated spinner was not observed");
      }
      if (helpCycles > 0 && !sawHelp) {
        protocolFailures.push("help redraw text was not observed");
      }
      if (exitCode !== 0) {
        protocolFailures.push(`child exit code was ${exitCode}`);
      }
      if (forcedKill) {
        protocolFailures.push("child required forced termination");
      }
      const report = {
        format_version: "1.0.0",
        target: "cli",
        version,
        mode: "zh",
        started_at: startedAt.toISOString(),
        ended_at: endedAt.toISOString(),
        requested_minutes: options.durationMinutes,
        actual_seconds: Number(actualSeconds.toFixed(3)),
        translated_unit_ids: translations.map((translation) => translation.id),
        translated_hits: translatedHits,
        resize_events: resizeEvents,
        help_cycles: helpCycles,
        ansi_sequences: ansiSequences,
        help_redraw_observed: sawHelp,
        forced_kill: forcedKill,
        exit_code: exitCode,
        signal: signal || null,
        protocol_failures: protocolFailures,
      };
      await fsp.mkdir(path.dirname(options.reportPath), { recursive: true });
      await fsp.writeFile(
        options.reportPath,
        `${JSON.stringify(report, null, 2)}\n`,
        "utf8",
      );
      resolve(report);
    });
  });
}


async function main(argv = process.argv.slice(2)) {
  const options = parseArguments(argv);
  const report = await runSoak(options);
  process.stdout.write(`${JSON.stringify(report)}\n`);
  process.exit(report.protocol_failures.length === 0 ? 0 : 1);
}


if (require.main === module) {
  main().catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  });
}


module.exports = {
  occurrences,
  parseArguments,
  runSoak,
};
