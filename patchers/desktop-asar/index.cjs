"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");


const SUPPORTED_CORPUS_VERSION = "1.18286.0";
const MANAGED_STATE_VERSION = 1;
const TEXT_EXTENSIONS = new Set([".js", ".mjs", ".cjs", ".html"]);


class DesktopPatchError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "DesktopPatchError";
    this.code = code;
  }
}


async function pathExists(candidate) {
  try {
    await fsp.access(candidate);
    return true;
  } catch {
    return false;
  }
}


function ensureInside(root, candidate) {
  const relative = path.relative(path.resolve(root), path.resolve(candidate));
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return;
  }
  throw new DesktopPatchError(
    "UNSAFE_PATH",
    `Refusing to access a path outside ${root}: ${candidate}`,
  );
}


async function sha256File(filename) {
  const hash = crypto.createHash("sha256");
  const input = fs.createReadStream(filename);
  for await (const chunk of input) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}


function installKey(appRoot) {
  return crypto
    .createHash("sha256")
    .update(path.resolve(appRoot).toLowerCase())
    .digest("hex")
    .slice(0, 16);
}


function defaultDataRoot() {
  const localAppData = process.env.LOCALAPPDATA;
  if (localAppData) {
    return path.join(localAppData, "claude-zh");
  }
  return path.join(os.homedir(), "AppData", "Local", "claude-zh");
}


function statePathFor(dataRoot, appRoot) {
  return path.join(dataRoot, "states", `${installKey(appRoot)}.json`);
}


async function readJson(filename) {
  return JSON.parse(await fsp.readFile(filename, "utf8"));
}


async function writeJsonAtomic(filename, value) {
  await fsp.mkdir(path.dirname(filename), { recursive: true });
  const temporary = `${filename}.tmp-${process.pid}`;
  await fsp.writeFile(
    temporary,
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
  await fsp.rename(temporary, filename);
}


async function walkFiles(root, predicate = () => true) {
  const result = [];
  if (!(await pathExists(root))) {
    return result;
  }
  const pending = [root];
  while (pending.length > 0) {
    const current = pending.pop();
    const entries = await fsp.readdir(current, { withFileTypes: true });
    entries.sort((left, right) => right.name.localeCompare(left.name));
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        pending.push(fullPath);
      } else if (entry.isFile() && predicate(fullPath)) {
        result.push(fullPath);
      }
    }
  }
  return result.sort();
}


function versionParts(name) {
  return (name.match(/\d+/g) || []).map(Number);
}


function compareVersionNames(left, right) {
  const a = versionParts(left);
  const b = versionParts(right);
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (b[index] || 0) - (a[index] || 0);
    if (difference !== 0) {
      return difference;
    }
  }
  return right.localeCompare(left);
}


async function validateAppRoot(appRoot, kind = "desktop") {
  const resolved = path.resolve(appRoot);
  const asarPath = path.join(resolved, "resources", "app.asar");
  if (!(await pathExists(asarPath))) {
    throw new DesktopPatchError(
      "INSTALL_NOT_FOUND",
      `Claude Desktop app.asar was not found under ${resolved}`,
    );
  }
  return { appRoot: resolved, asarPath, kind };
}


async function discoverDesktopInstall(explicitAppRoot) {
  if (explicitAppRoot) {
    const resolved = path.resolve(explicitAppRoot);
    const isMsix = resolved.toLowerCase().includes(`${path.sep}windowsapps${path.sep}`);
    return validateAppRoot(resolved, isMsix ? "msix" : "desktop");
  }

  const candidates = [];
  const localAppData = process.env.LOCALAPPDATA;
  if (localAppData) {
    const squirrelRoot = path.join(localAppData, "AnthropicClaude");
    if (await pathExists(squirrelRoot)) {
      const entries = await fsp.readdir(squirrelRoot, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory() && entry.name.startsWith("app-")) {
          candidates.push(path.join(squirrelRoot, entry.name));
        }
      }
    }
    candidates.push(path.join(localAppData, "Programs", "Claude"));
  }

  const usable = [];
  for (const candidate of candidates) {
    if (await pathExists(path.join(candidate, "resources", "app.asar"))) {
      usable.push(candidate);
    }
  }
  usable.sort((left, right) => compareVersionNames(path.basename(left), path.basename(right)));
  if (usable.length > 0) {
    return validateAppRoot(usable[0], "desktop");
  }

  const programFiles = process.env.ProgramFiles || "C:\\Program Files";
  const windowsApps = path.join(programFiles, "WindowsApps");
  if (await pathExists(windowsApps)) {
    try {
      const entries = await fsp.readdir(windowsApps, { withFileTypes: true });
      const msixRoots = entries
        .filter((entry) => entry.isDirectory() && entry.name.startsWith("Claude_"))
        .map((entry) => path.join(windowsApps, entry.name, "app"))
        .sort((left, right) => compareVersionNames(path.basename(path.dirname(left)), path.basename(path.dirname(right))));
      for (const candidate of msixRoots) {
        if (await pathExists(path.join(candidate, "resources", "app.asar"))) {
          return validateAppRoot(candidate, "msix");
        }
      }
    } catch {
      // A standard user may not be able to enumerate WindowsApps.
    }
  }

  throw new DesktopPatchError(
    "INSTALL_NOT_FOUND",
    "No supported non-MSIX Claude Desktop installation was found.",
  );
}


function isClaudeRunning() {
  if (process.platform !== "win32") {
    return false;
  }
  const result = spawnSync(
    path.join(process.env.SystemRoot || "C:\\Windows", "System32", "tasklist.exe"),
    ["/NH", "/FI", "IMAGENAME eq claude.exe"],
    { encoding: "utf8", windowsHide: true },
  );
  if (result.status !== 0) {
    throw new DesktopPatchError(
      "PROCESS_CHECK_FAILED",
      "Could not determine whether Claude is running.",
    );
  }
  return /(^|\s)claude\.exe(\s|$)/im.test(result.stdout);
}


async function loadTranslations(projectRoot, mode) {
  if (!["zh", "bilingual"].includes(mode)) {
    throw new DesktopPatchError(
      "INVALID_MODE",
      `Unsupported mode ${mode}; expected zh or bilingual.`,
    );
  }
  const corpusPath = path.join(
    projectRoot,
    "corpus",
    "desktop",
    `${SUPPORTED_CORPUS_VERSION}.json`,
  );
  const corpus = await readJson(corpusPath);
  if (corpus.version !== SUPPORTED_CORPUS_VERSION) {
    throw new DesktopPatchError(
      "CORPUS_VERSION_MISMATCH",
      `Expected Desktop corpus ${SUPPORTED_CORPUS_VERSION}.`,
    );
  }
  const field = mode === "zh" ? "target" : "target_bilingual";
  const translations = new Map();
  for (const unit of corpus.units) {
    if (unit.risk === "SAFE" && typeof unit[field] === "string") {
      translations.set(unit.source, unit[field]);
    }
  }
  if (translations.size === 0) {
    throw new DesktopPatchError(
      "EMPTY_CORPUS",
      "The selected Desktop corpus contains no SAFE translations.",
    );
  }
  return { corpus, translations };
}


function escapeSingleQuoted(value) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/\t/g, "\\t")
    .replace(/\f/g, "\\f")
    .replace(/\v/g, "\\v")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029")
    .replace(/'/g, "\\'");
}


function escapeTemplateLiteral(value) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/\t/g, "\\t")
    .replace(/\f/g, "\\f")
    .replace(/\v/g, "\\v")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029")
    .replace(/`/g, "\\`")
    .replace(/\$\{/g, "\\${");
}


function regexEscape(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}


function buildLiteralReplacer(translations) {
  const literals = new Map();
  for (const [source, target] of translations) {
    literals.set(JSON.stringify(source), JSON.stringify(target));
    literals.set(`'${escapeSingleQuoted(source)}'`, `'${escapeSingleQuoted(target)}'`);
    literals.set(`\`${escapeTemplateLiteral(source)}\``, `\`${escapeTemplateLiteral(target)}\``);
  }
  const alternatives = [...literals.keys()]
    .sort((left, right) => right.length - left.length)
    .map(regexEscape);
  const pattern = new RegExp(alternatives.join("|"), "g");
  return (text) => {
    let replacements = 0;
    const patched = text.replace(pattern, (literal) => {
      replacements += 1;
      return literals.get(literal);
    });
    return { patched, replacements };
  };
}


function translateJsonTree(value, translations, counter) {
  if (typeof value === "string") {
    const translated = translations.get(value);
    if (translated !== undefined) {
      counter.count += 1;
      return translated;
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => translateJsonTree(item, translations, counter));
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      result[key] = translateJsonTree(item, translations, counter);
    }
    return result;
  }
  return value;
}


async function inspectAsar(installation) {
  const asar = await import("@electron/asar");
  const packageJson = JSON.parse(
    asar.extractFile(installation.asarPath, "package.json").toString("utf8"),
  );
  if (packageJson.version !== SUPPORTED_CORPUS_VERSION) {
    throw new DesktopPatchError(
      "UNSUPPORTED_VERSION",
      `Claude Desktop ${packageJson.version} is not supported; expected ${SUPPORTED_CORPUS_VERSION}.`,
    );
  }
  return {
    version: packageJson.version,
    strategy: "read-only-integrity-safe",
  };
}


async function stageExternalResources(
  installation,
  temporaryRoot,
  translations,
) {
  const resourcesRoot = path.join(installation.appRoot, "resources");
  const localePath = path.join(resourcesRoot, "en-US.json");
  if (!(await pathExists(localePath))) {
    throw new DesktopPatchError(
      "LOCALE_NOT_FOUND",
      `Desktop locale catalog was not found at ${localePath}`,
    );
  }

  const stageRoot = path.join(temporaryRoot, "external");
  const enStage = path.join(stageRoot, "resources", "en-US.json");
  const zhStage = path.join(stageRoot, "resources", "zh-CN.json");
  const locale = await readJson(localePath);
  const counter = { count: 0 };
  const translatedLocale = translateJsonTree(locale, translations, counter);
  if (counter.count === 0) {
    throw new DesktopPatchError(
      "NO_LOCALE_MATCHES",
      "The supported corpus did not match the installed Desktop locale catalog.",
    );
  }
  await fsp.mkdir(path.dirname(enStage), { recursive: true });
  const localeOutput = `${JSON.stringify(translatedLocale, null, 2)}\n`;
  await fsp.writeFile(enStage, localeOutput, "utf8");
  await fsp.writeFile(zhStage, localeOutput, "utf8");

  const stagedFiles = [
    { target: localePath, staged: enStage },
    {
      target: path.join(resourcesRoot, "zh-CN.json"),
      staged: zhStage,
    },
  ];
  let hardcodedReplacements = 0;
  let hardcodedFilesChanged = 0;
  const ionRoot = path.join(resourcesRoot, "ion-dist");
  const replaceLiterals = buildLiteralReplacer(translations);
  const ionFiles = await walkFiles(ionRoot, (filename) =>
    TEXT_EXTENSIONS.has(path.extname(filename).toLowerCase()),
  );
  for (const filename of ionFiles) {
    const original = await fsp.readFile(filename, "utf8");
    const result = replaceLiterals(original);
    if (result.replacements === 0) {
      continue;
    }
    const relative = path.relative(installation.appRoot, filename);
    const staged = path.join(stageRoot, relative);
    await fsp.mkdir(path.dirname(staged), { recursive: true });
    await fsp.writeFile(staged, result.patched, "utf8");
    stagedFiles.push({ target: filename, staged });
    hardcodedReplacements += result.replacements;
    hardcodedFilesChanged += 1;
  }

  return {
    stagedFiles,
    localeReplacements: counter.count,
    hardcodedReplacements,
    hardcodedFilesChanged,
  };
}


async function atomicReplace(staged, target) {
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const incoming = `${target}.claude-zh-new-${process.pid}`;
  const rollback = `${target}.claude-zh-old-${process.pid}`;
  await fsp.copyFile(staged, incoming);
  const targetExists = await pathExists(target);
  try {
    if (targetExists) {
      await fsp.rename(target, rollback);
    }
    await fsp.rename(incoming, target);
    if (targetExists) {
      await fsp.rm(rollback, { force: true });
    }
  } catch (error) {
    await fsp.rm(incoming, { force: true }).catch(() => {});
    if (targetExists && (await pathExists(rollback)) && !(await pathExists(target))) {
      await fsp.rename(rollback, target).catch(() => {});
    }
    throw error;
  }
}


async function removeEmptyParents(start, stop) {
  let current = path.resolve(start);
  const boundary = path.resolve(stop);
  ensureInside(boundary, current);
  while (current !== boundary) {
    try {
      await fsp.rmdir(current);
    } catch {
      return;
    }
    current = path.dirname(current);
  }
  await fsp.rmdir(boundary).catch(() => {});
}


async function restoreFromState(statePath, options = {}) {
  const state = await readJson(statePath);
  if (state.schemaVersion !== MANAGED_STATE_VERSION) {
    throw new DesktopPatchError(
      "STATE_VERSION_UNSUPPORTED",
      `Unsupported backup state version ${state.schemaVersion}.`,
    );
  }
  if (!options.skipRunningCheck && (options.isRunning || isClaudeRunning)()) {
    throw new DesktopPatchError(
      "CLAUDE_RUNNING",
      "Claude is running. Close Claude and run restore again; no process was terminated.",
    );
  }

  const dataRoot = path.resolve(state.dataRoot);
  const backupRoot = path.resolve(state.backupRoot);
  ensureInside(dataRoot, backupRoot);
  for (const entry of state.files) {
    const target = path.join(state.appRoot, entry.relativePath);
    ensureInside(state.appRoot, target);
    if (entry.originalSha256 === null) {
      await fsp.rm(target, { force: true });
      continue;
    }
    const backup = path.join(backupRoot, entry.relativePath);
    ensureInside(backupRoot, backup);
    if (!(await pathExists(backup))) {
      throw new DesktopPatchError(
        "BACKUP_MISSING",
        `Backup file is missing: ${backup}`,
      );
    }
    const backupHash = await sha256File(backup);
    if (backupHash !== entry.originalSha256) {
      throw new DesktopPatchError(
        "BACKUP_HASH_MISMATCH",
        `Backup hash mismatch for ${entry.relativePath}`,
      );
    }
    await atomicReplace(backup, target);
  }

  for (const entry of state.files) {
    if (entry.originalSha256 === null) {
      if (await pathExists(path.join(state.appRoot, entry.relativePath))) {
        throw new DesktopPatchError(
          "RESTORE_VERIFICATION_FAILED",
          `Generated file remains after restore: ${entry.relativePath}`,
        );
      }
      continue;
    }
    const restoredHash = await sha256File(
      path.join(state.appRoot, entry.relativePath),
    );
    if (restoredHash !== entry.originalSha256) {
      throw new DesktopPatchError(
        "RESTORE_VERIFICATION_FAILED",
        `Restored SHA-256 mismatch for ${entry.relativePath}`,
      );
    }
  }

  await fsp.rm(backupRoot, { recursive: true, force: true });
  await removeEmptyParents(path.dirname(backupRoot), dataRoot);
  await fsp.rm(statePath, { force: true });
  await removeEmptyParents(path.dirname(statePath), dataRoot);
  return {
    appRoot: state.appRoot,
    restoredFiles: state.files.length,
    verified: true,
  };
}


async function installDesktop(options = {}) {
  const projectRoot = path.resolve(
    options.projectRoot || path.join(__dirname, "..", ".."),
  );
  const installation = await discoverDesktopInstall(options.appRoot);
  if (installation.kind === "msix") {
    throw new DesktopPatchError(
      "MSIX_UNSUPPORTED",
      `Microsoft Store/MSIX installation detected at ${installation.appRoot}. It is read-only and was not modified.`,
    );
  }
  const runningCheck = options.isRunning || isClaudeRunning;
  if (runningCheck()) {
    throw new DesktopPatchError(
      "CLAUDE_RUNNING",
      "Claude is running. Close Claude and retry; no process was terminated.",
    );
  }

  const mode = options.mode || "zh";
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  const statePath = statePathFor(dataRoot, installation.appRoot);
  if (await pathExists(statePath)) {
    throw new DesktopPatchError(
      "ALREADY_INSTALLED",
      "A Desktop patch is already installed. Restore it before changing modes.",
    );
  }

  const { translations } = await loadTranslations(projectRoot, mode);
  await fsp.mkdir(dataRoot, { recursive: true });
  const temporaryRoot = await fsp.mkdtemp(
    path.join(os.tmpdir(), "claude-zh-desktop-"),
  );
  let stateWritten = false;
  try {
    const asarInspection = await inspectAsar(installation);
    const externalStage = await stageExternalResources(
      installation,
      temporaryRoot,
      translations,
    );
    const stagedFiles = externalStage.stagedFiles;
    const backupRoot = path.join(
      dataRoot,
      "backups",
      installKey(installation.appRoot),
    );
    const files = [];
    for (const item of stagedFiles) {
      ensureInside(installation.appRoot, item.target);
      const relativePath = path.relative(installation.appRoot, item.target);
      const existed = await pathExists(item.target);
      let originalSha256 = null;
      if (existed) {
        originalSha256 = await sha256File(item.target);
        const backup = path.join(backupRoot, relativePath);
        ensureInside(backupRoot, backup);
        await fsp.mkdir(path.dirname(backup), { recursive: true });
        await fsp.copyFile(item.target, backup);
        if ((await sha256File(backup)) !== originalSha256) {
          throw new DesktopPatchError(
            "BACKUP_VERIFICATION_FAILED",
            `Backup SHA-256 mismatch for ${relativePath}`,
          );
        }
      }
      files.push({
        relativePath,
        originalSha256,
        patchedSha256: null,
        staged: item.staged,
      });
    }

    const state = {
      schemaVersion: MANAGED_STATE_VERSION,
      status: "installing",
      appRoot: installation.appRoot,
      dataRoot,
      backupRoot,
      corpusVersion: SUPPORTED_CORPUS_VERSION,
      asarStrategy: asarInspection.strategy,
      mode,
      installedAt: new Date().toISOString(),
      files: files.map(({ staged, ...entry }) => entry),
    };
    await writeJsonAtomic(statePath, state);
    stateWritten = true;

    let appliedFiles = 0;
    for (const entry of files) {
      await atomicReplace(entry.staged, path.join(installation.appRoot, entry.relativePath));
      entry.patchedSha256 = await sha256File(
        path.join(installation.appRoot, entry.relativePath),
      );
      appliedFiles += 1;
      if (options.hooks && typeof options.hooks.afterApply === "function") {
        await options.hooks.afterApply(appliedFiles, entry.relativePath);
      }
    }

    state.status = "installed";
    state.files = files.map(({ staged, ...entry }) => entry);
    await writeJsonAtomic(statePath, state);
    return {
      appRoot: installation.appRoot,
      backupRoot,
      statePath,
      mode,
      corpusVersion: SUPPORTED_CORPUS_VERSION,
      asarStrategy: asarInspection.strategy,
      translatedUnits: translations.size,
      localeReplacements: externalStage.localeReplacements,
      hardcodedReplacements: externalStage.hardcodedReplacements,
      hardcodedFilesChanged: externalStage.hardcodedFilesChanged,
      patchedFiles: files.length,
    };
  } catch (error) {
    if (stateWritten && await pathExists(statePath)) {
      try {
        await restoreFromState(statePath, {
          skipRunningCheck: true,
          isRunning: () => false,
        });
      } catch (rollbackError) {
        throw new DesktopPatchError(
          "INSTALL_AND_ROLLBACK_FAILED",
          `${error.message}; automatic restore also failed: ${rollbackError.message}`,
        );
      }
      throw new DesktopPatchError(
        "INSTALL_FAILED_RESTORED",
        `${error.message}; original files were restored and SHA-256 verified.`,
      );
    }
    throw error;
  } finally {
    await fsp.rm(temporaryRoot, { recursive: true, force: true });
  }
}


async function listStatePaths(dataRoot) {
  const statesRoot = path.join(dataRoot, "states");
  return walkFiles(statesRoot, (filename) => filename.endsWith(".json"));
}


async function restoreDesktop(options = {}) {
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  let statePath;
  if (options.appRoot) {
    statePath = statePathFor(dataRoot, path.resolve(options.appRoot));
  } else {
    const states = await listStatePaths(dataRoot);
    if (states.length === 0) {
      throw new DesktopPatchError(
        "NOT_INSTALLED",
        "No managed Desktop patch backup was found.",
      );
    }
    if (states.length > 1) {
      throw new DesktopPatchError(
        "MULTIPLE_INSTALLS",
        "Multiple managed Desktop patches exist; specify --app-root.",
      );
    }
    [statePath] = states;
  }
  if (!(await pathExists(statePath))) {
    throw new DesktopPatchError(
      "NOT_INSTALLED",
      "No managed Desktop patch backup was found for this installation.",
    );
  }
  return restoreFromState(statePath, {
    isRunning: options.isRunning || isClaudeRunning,
  });
}


async function statusDesktop(options = {}) {
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  const states = options.appRoot
    ? [statePathFor(dataRoot, path.resolve(options.appRoot))]
    : await listStatePaths(dataRoot);
  const existingStates = [];
  for (const statePath of states) {
    if (await pathExists(statePath)) {
      existingStates.push(statePath);
    }
  }
  if (existingStates.length > 0) {
    const installations = [];
    for (const statePath of existingStates) {
      const state = await readJson(statePath);
      let valid = state.status === "installed";
      const mismatches = [];
      for (const entry of state.files) {
        const target = path.join(state.appRoot, entry.relativePath);
        if (!(await pathExists(target))) {
          valid = false;
          mismatches.push(entry.relativePath);
          continue;
        }
        const currentHash = await sha256File(target);
        if (currentHash !== entry.patchedSha256) {
          valid = false;
          mismatches.push(entry.relativePath);
        }
      }
      installations.push({
        appRoot: state.appRoot,
        mode: state.mode,
        corpusVersion: state.corpusVersion,
        asarStrategy: state.asarStrategy,
        state: valid ? "installed" : "modified-after-install",
        mismatches,
        backupRoot: state.backupRoot,
      });
    }
    return { state: "managed", installations };
  }

  try {
    const installation = await discoverDesktopInstall(options.appRoot);
    if (installation.kind === "msix") {
      return {
        state: "msix-unsupported",
        appRoot: installation.appRoot,
        message: "MSIX installation detected; no files were modified.",
      };
    }
    return {
      state: "not-installed",
      appRoot: installation.appRoot,
      message: "Supported non-MSIX installation detected.",
    };
  } catch (error) {
    if (error instanceof DesktopPatchError && error.code === "INSTALL_NOT_FOUND") {
      return { state: "not-found", message: error.message };
    }
    throw error;
  }
}


module.exports = {
  DesktopPatchError,
  SUPPORTED_CORPUS_VERSION,
  buildLiteralReplacer,
  discoverDesktopInstall,
  installDesktop,
  isClaudeRunning,
  loadTranslations,
  restoreDesktop,
  sha256File,
  statusDesktop,
  translateJsonTree,
};
