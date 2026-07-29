#!/usr/bin/env node
"use strict";

const pty = require("node-pty");


const shell = process.env.ComSpec || "cmd.exe";
const child = pty.spawn(
  shell,
  ["/d"],
  {
    name: "xterm-256color",
    cols: 80,
    rows: 24,
    cwd: process.cwd(),
    env: { ...process.env },
    useConpty: true,
  },
);
let output = "";
let exitResult;
let finalTimer;
const timeout = setTimeout(() => {
  child.kill();
  console.error("PTY self-test timed out.");
  process.exit(1);
}, 10_000);
const inputTimer = setTimeout(() => {
  child.write("echo PTY_OK\r");
}, 100);
const exitTimer = setTimeout(() => {
  child.write("exit\r");
}, 250);

function finish() {
  clearTimeout(timeout);
  clearTimeout(inputTimer);
  clearTimeout(exitTimer);
  clearTimeout(finalTimer);
  const passed = exitResult.exitCode === 0 && /\bPTY_OK\b/.test(output);
  console.log(JSON.stringify({
    passed,
    exitCode: exitResult.exitCode,
    signal: exitResult.signal || null,
    marker: passed ? "PTY_OK" : null,
  }));
  process.exit(passed ? 0 : 1);
}

child.onData((data) => {
  output += data;
  if (exitResult && /\bPTY_OK\b/.test(output)) {
    finish();
  }
});
child.onExit((result) => {
  exitResult = result;
  if (/\bPTY_OK\b/.test(output)) {
    finish();
    return;
  }
  finalTimer = setTimeout(finish, 2_000);
});
