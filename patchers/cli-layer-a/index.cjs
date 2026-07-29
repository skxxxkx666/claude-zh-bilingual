"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");


const MANAGED_STATE_VERSION = 1;
const SUPPORTED_CORPUS_VERSION = "2.1.201";
const REQUIRED_TRANSLATIONS = [
  "Layer A active",
  "Model",
  "Context",
  "Cost",
  "Directory",
  "Chinese response style",
  "Respond in Chinese while preserving searchable English terminology.",
  "Use Chinese for explanatory prose. Preserve code, commands, paths, identifiers, and official product names in their original form.",
  "Compact this conversation while preserving decisions, changed files, test results, and remaining tasks.",
  "Chinese alias for the built-in compact workflow.",
  "Show concise Chinese help for the current task, including available commands when relevant.",
  "Chinese help alias.",
  "Continue the most recent task from its saved context.",
  "Chinese resume alias.",
  "Claude Code Chinese Layer A plugin.",
  "Show the Chinese Layer A help message.",
];


class CodeLayerError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "CodeLayerError";
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
  throw new CodeLayerError(
    "UNSAFE_PATH",
    `Refusing to access a path outside ${root}: ${candidate}`,
  );
}


function defaultConfigRoot() {
  return path.join(os.homedir(), ".claude");
}


function defaultDataRoot() {
  const localAppData = process.env.LOCALAPPDATA;
  if (localAppData) {
    return path.join(localAppData, "claude-zh", "code-layer-a");
  }
  return path.join(os.homedir(), "AppData", "Local", "claude-zh", "code-layer-a");
}


function installKey(configRoot) {
  return crypto
    .createHash("sha256")
    .update(path.resolve(configRoot).toLowerCase())
    .digest("hex")
    .slice(0, 16);
}


function statePathFor(dataRoot, configRoot) {
  return path.join(dataRoot, "states", `${installKey(configRoot)}.json`);
}


function sha256Bytes(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}


async function sha256File(filename) {
  const hash = crypto.createHash("sha256");
  const input = fs.createReadStream(filename);
  for await (const chunk of input) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}


async function readJson(filename) {
  return JSON.parse(await fsp.readFile(filename, "utf8"));
}


async function writeFileAtomic(filename, value) {
  await fsp.mkdir(path.dirname(filename), { recursive: true });
  const incoming = `${filename}.claude-zh-new-${process.pid}`;
  const rollback = `${filename}.claude-zh-old-${process.pid}`;
  await fsp.writeFile(incoming, value);
  const existed = await pathExists(filename);
  try {
    if (existed) {
      await fsp.rename(filename, rollback);
    }
    await fsp.rename(incoming, filename);
    if (existed) {
      await fsp.rm(rollback, { force: true });
    }
  } catch (error) {
    await fsp.rm(incoming, { force: true }).catch(() => {});
    if (existed && (await pathExists(rollback)) && !(await pathExists(filename))) {
      await fsp.rename(rollback, filename).catch(() => {});
    }
    throw error;
  }
}


async function writeJsonAtomic(filename, value) {
  await writeFileAtomic(
    filename,
    Buffer.from(`${JSON.stringify(value, null, 2)}\n`, "utf8"),
  );
}


function deepEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}


function commandPath(filename) {
  const normalized = path.resolve(filename).replace(/\\/g, "/");
  return `node "${normalized.replace(/"/g, '\\"')}"`;
}


async function loadTranslations(projectRoot, mode) {
  if (!["zh", "bilingual"].includes(mode)) {
    throw new CodeLayerError(
      "INVALID_MODE",
      `Unsupported mode ${mode}; expected zh or bilingual.`,
    );
  }
  const corpusPath = path.join(
    projectRoot,
    "corpus",
    "cli",
    "layer-a.json",
  );
  const corpus = await readJson(corpusPath);
  if (corpus.version !== SUPPORTED_CORPUS_VERSION) {
    throw new CodeLayerError(
      "CORPUS_VERSION_MISMATCH",
      `Expected CLI corpus ${SUPPORTED_CORPUS_VERSION}.`,
    );
  }
  const field = mode === "zh" ? "target" : "target_bilingual";
  const translations = new Map();
  for (const unit of corpus.units) {
    if (unit.risk === "SAFE") {
      if (typeof unit[field] === "string") {
        translations.set(unit.source, unit[field]);
      }
    }
  }
  const missing = REQUIRED_TRANSLATIONS.filter((source) => !translations.has(source));
  if (missing.length > 0) {
    throw new CodeLayerError(
      "CORPUS_INCOMPLETE",
      `CLI Layer A corpus is missing ${missing.length} required translation(s).`,
    );
  }
  return translations;
}


function translated(translations, source) {
  const value = translations.get(source);
  if (typeof value !== "string") {
    throw new CodeLayerError(
      "CORPUS_INCOMPLETE",
      `CLI Layer A translation is missing: ${source}`,
    );
  }
  return value;
}


function buildAssets(configRoot, translations) {
  const managedRoot = path.join(configRoot, "claude-zh");
  const statuslinePath = path.join(managedRoot, "statusline.cjs");
  const hookPath = path.join(managedRoot, "session-start.cjs");
  const catalogPath = path.join(managedRoot, "catalog.json");
  const pluginRoot = path.join(managedRoot, "plugin");
  const catalog = {
    active: translated(translations, "Layer A active"),
    model: translated(translations, "Model"),
    context: translated(translations, "Context"),
    cost: translated(translations, "Cost"),
    directory: translated(translations, "Directory"),
  };
  const statusline = [
    '"use strict";',
    'const fs = require("node:fs");',
    'const path = require("node:path");',
    'const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, "catalog.json"), "utf8"));',
    'let input = {};',
    'try { input = JSON.parse(fs.readFileSync(0, "utf8")); } catch {}',
    'const model = input.model?.display_name || input.model?.id || "-";',
    'const context = Math.round(input.context_window?.used_percentage || 0);',
    'const cost = Number(input.cost?.total_cost_usd || 0).toFixed(2);',
    'const directory = input.workspace?.current_dir || input.cwd || "-";',
    'process.stdout.write(`${catalog.active} | ${catalog.model}: ${model} | ${catalog.context}: ${context}% | ${catalog.cost}: $${cost} | ${catalog.directory}: ${directory}`);',
    "",
  ].join("\n");
  const sessionStart = [
    '"use strict";',
    'const fs = require("node:fs");',
    'const path = require("node:path");',
    'const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, "catalog.json"), "utf8"));',
    'process.stdout.write(JSON.stringify({ systemMessage: catalog.active }));',
    "",
  ].join("\n");
  const outputStyleName = translated(translations, "Chinese response style");
  const outputStyle = [
    "---",
    `name: ${outputStyleName}`,
    `description: ${translated(translations, "Respond in Chinese while preserving searchable English terminology.")}`,
    "keep-coding-instructions: true",
    "---",
    "",
    translated(
      translations,
      "Use Chinese for explanatory prose. Preserve code, commands, paths, identifiers, and official product names in their original form.",
    ),
    "",
  ].join("\n");
  const skills = [
    {
      directory: "zh-compact",
      description: translated(
        translations,
        "Chinese alias for the built-in compact workflow.",
      ),
      body: translated(
        translations,
        "Compact this conversation while preserving decisions, changed files, test results, and remaining tasks.",
      ),
    },
    {
      directory: "zh-help",
      description: translated(translations, "Chinese help alias."),
      body: translated(
        translations,
        "Show concise Chinese help for the current task, including available commands when relevant.",
      ),
    },
    {
      directory: "zh-resume",
      description: translated(translations, "Chinese resume alias."),
      body: translated(
        translations,
        "Continue the most recent task from its saved context.",
      ),
    },
  ];
  const pluginManifest = {
    name: "claude-zh-layer-a",
    description: translated(translations, "Claude Code Chinese Layer A plugin."),
    version: "0.1.0",
    author: {
      name: "claude-zh-bilingual",
    },
  };
  const pluginSkill = [
    "---",
    "name: zh-help",
    `description: ${translated(translations, "Show the Chinese Layer A help message.")}`,
    "disable-model-invocation: true",
    "---",
    "",
    translated(
      translations,
      "Show concise Chinese help for the current task, including available commands when relevant.",
    ),
    "",
  ].join("\n");

  const assets = [
    {
      path: catalogPath,
      content: `${JSON.stringify(catalog, null, 2)}\n`,
      kind: "catalog",
    },
    { path: statuslinePath, content: statusline, kind: "statusline" },
    { path: hookPath, content: sessionStart, kind: "hook" },
    {
      path: path.join(configRoot, "output-styles", "claude-zh.md"),
      content: outputStyle,
      kind: "output-style",
    },
    {
      path: path.join(pluginRoot, ".claude-plugin", "plugin.json"),
      content: `${JSON.stringify(pluginManifest, null, 2)}\n`,
      kind: "plugin-manifest",
    },
    {
      path: path.join(pluginRoot, "skills", "zh-help", "SKILL.md"),
      content: pluginSkill,
      kind: "plugin-skill",
    },
  ];
  for (const skill of skills) {
    assets.push({
      path: path.join(configRoot, "skills", skill.directory, "SKILL.md"),
      content: [
        "---",
        `description: ${skill.description}`,
        "disable-model-invocation: true",
        "---",
        "",
        skill.body,
        "",
      ].join("\n"),
      kind: `skill:${skill.directory}`,
    });
  }
  return {
    assets,
    statuslinePath,
    hookPath,
    pluginRoot,
    outputStyleName,
  };
}


function mergeSettings(original, paths) {
  const merged = structuredClone(original);
  const additions = {
    statusLine: null,
    outputStyle: null,
    hook: null,
  };
  const skipped = [];

  if (!Object.prototype.hasOwnProperty.call(merged, "statusLine")) {
    additions.statusLine = {
      type: "command",
      command: commandPath(paths.statuslinePath),
      padding: 0,
    };
    merged.statusLine = additions.statusLine;
  } else {
    skipped.push("statusLine");
  }

  if (!Object.prototype.hasOwnProperty.call(merged, "outputStyle")) {
    additions.outputStyle = paths.outputStyleName;
    merged.outputStyle = additions.outputStyle;
  } else {
    skipped.push("outputStyle");
  }

  if (
    !Object.prototype.hasOwnProperty.call(merged, "hooks")
    || (merged.hooks && typeof merged.hooks === "object" && !Array.isArray(merged.hooks))
  ) {
    if (!Object.prototype.hasOwnProperty.call(merged, "hooks")) {
      merged.hooks = {};
    }
    const sessionStart = merged.hooks.SessionStart;
    if (sessionStart === undefined || Array.isArray(sessionStart)) {
      if (sessionStart === undefined) {
        merged.hooks.SessionStart = [];
      }
      additions.hook = {
        matcher: "startup",
        hooks: [
          {
            type: "command",
            command: commandPath(paths.hookPath),
            timeout: 5,
          },
        ],
      };
      if (!merged.hooks.SessionStart.some((entry) => deepEqual(entry, additions.hook))) {
        merged.hooks.SessionStart.push(additions.hook);
      } else {
        additions.hook = null;
        skipped.push("hooks.SessionStart");
      }
    } else {
      skipped.push("hooks.SessionStart");
    }
  } else {
    skipped.push("hooks");
  }
  return { merged, additions, skipped };
}


async function backupFile(source, destination) {
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  await fsp.copyFile(source, destination);
  const [sourceHash, backupHash] = await Promise.all([
    sha256File(source),
    sha256File(destination),
  ]);
  if (sourceHash !== backupHash) {
    throw new CodeLayerError(
      "BACKUP_VERIFICATION_FAILED",
      `Backup SHA-256 mismatch for ${source}`,
    );
  }
  return sourceHash;
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
}


async function rollbackInstall(state) {
  const settingsPath = path.join(state.configRoot, "settings.json");
  if (
    state.installedSettingsSha256 !== null
    && (await pathExists(settingsPath))
    && (await sha256File(settingsPath)) === state.installedSettingsSha256
  ) {
    if (state.originalSettingsSha256 === null) {
      await fsp.rm(settingsPath, { force: true });
    } else {
      const backup = path.join(state.backupRoot, "settings.json");
      if (await pathExists(backup)) {
        await writeFileAtomic(settingsPath, await fsp.readFile(backup));
      }
    }
  }
  for (const asset of [...state.assets].reverse()) {
    if (await pathExists(asset.path)) {
      const currentHash = await sha256File(asset.path);
      if (asset.installedSha256 === null || currentHash === asset.installedSha256) {
        await fsp.rm(asset.path, { force: true });
        await removeEmptyParents(path.dirname(asset.path), state.configRoot);
      }
    }
  }
}


async function installCodeLayerA(options = {}) {
  const projectRoot = path.resolve(
    options.projectRoot || path.join(__dirname, "..", ".."),
  );
  const configRoot = path.resolve(options.configRoot || defaultConfigRoot());
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  const statePath = statePathFor(dataRoot, configRoot);
  if (await pathExists(statePath)) {
    throw new CodeLayerError(
      "ALREADY_INSTALLED",
      "CLI Layer A is already installed for this configuration root.",
    );
  }
  const mode = options.mode || "zh";
  const translations = await loadTranslations(projectRoot, mode);
  const built = buildAssets(configRoot, translations);
  const settingsPath = path.join(configRoot, "settings.json");
  let originalSettings = {};
  let originalSettingsBytes = null;
  if (await pathExists(settingsPath)) {
    originalSettingsBytes = await fsp.readFile(settingsPath);
    try {
      originalSettings = JSON.parse(originalSettingsBytes.toString("utf8"));
    } catch (error) {
      throw new CodeLayerError(
        "INVALID_SETTINGS",
        `Claude settings are not valid JSON: ${error.message}`,
      );
    }
    if (!originalSettings || typeof originalSettings !== "object" || Array.isArray(originalSettings)) {
      throw new CodeLayerError(
        "INVALID_SETTINGS",
        "Claude settings must contain a JSON object.",
      );
    }
  }
  const merge = mergeSettings(originalSettings, built);
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupRoot = path.join(
    dataRoot,
    "backups",
    `${installKey(configRoot)}-${timestamp}`,
  );
  const state = {
    schemaVersion: MANAGED_STATE_VERSION,
    status: "installing",
    mode,
    configRoot,
    dataRoot,
    backupRoot,
    installedAt: new Date().toISOString(),
    originalSettingsSha256: originalSettingsBytes
      ? sha256Bytes(originalSettingsBytes)
      : null,
    installedSettingsSha256: null,
    additions: merge.additions,
    assets: [],
  };
  const installedSettingsBytes = Buffer.from(
    `${JSON.stringify(merge.merged, null, 2)}\n`,
    "utf8",
  );
  await fsp.mkdir(backupRoot, { recursive: true });
  if (originalSettingsBytes) {
    const backupHash = await backupFile(
      settingsPath,
      path.join(backupRoot, "settings.json"),
    );
    if (backupHash !== state.originalSettingsSha256) {
      throw new CodeLayerError(
        "BACKUP_VERIFICATION_FAILED",
        "Original settings backup did not match the source.",
      );
    }
  }

  const conflicts = [];
  for (const asset of built.assets) {
    ensureInside(configRoot, asset.path);
    if (await pathExists(asset.path)) {
      conflicts.push(path.relative(configRoot, asset.path));
      continue;
    }
    state.assets.push({
      path: asset.path,
      relativePath: path.relative(configRoot, asset.path),
      kind: asset.kind,
      installedSha256: null,
    });
  }
  await writeJsonAtomic(statePath, state);

  try {
    let applied = 0;
    for (const assetState of state.assets) {
      const asset = built.assets.find((candidate) => candidate.path === assetState.path);
      await writeFileAtomic(asset.path, Buffer.from(asset.content, "utf8"));
      assetState.installedSha256 = await sha256File(asset.path);
      applied += 1;
      if (options.hooks?.afterApply) {
        await options.hooks.afterApply(applied);
      }
    }
    const currentSettingsSha256 = (await pathExists(settingsPath))
      ? await sha256File(settingsPath)
      : null;
    if (currentSettingsSha256 !== state.originalSettingsSha256) {
      throw new CodeLayerError(
        "SETTINGS_CHANGED_DURING_INSTALL",
        "Claude settings changed during installation; current user settings were preserved.",
      );
    }
    state.installedSettingsSha256 = sha256Bytes(installedSettingsBytes);
    await writeFileAtomic(settingsPath, installedSettingsBytes);
    state.status = "installed";
    state.skippedSettings = merge.skipped;
    state.skippedAssets = conflicts;
    await writeJsonAtomic(statePath, state);
  } catch (error) {
    await rollbackInstall(state).catch(() => {});
    await fsp.rm(statePath, { force: true }).catch(() => {});
    throw new CodeLayerError(
      "INSTALL_FAILED",
      `CLI Layer A installation failed; managed changes were rolled back without overwriting current settings: ${error.message}`,
    );
  }

  return {
    mode,
    configRoot,
    dataRoot,
    backupRoot,
    statePath,
    pluginRoot: built.pluginRoot,
    installedAssets: state.assets.length,
    skippedAssets: conflicts,
    skippedSettings: merge.skipped,
  };
}


function removeAddedSettings(current, additions) {
  const result = structuredClone(current);
  const preserved = [];
  if (additions.statusLine !== null) {
    if (deepEqual(result.statusLine, additions.statusLine)) {
      delete result.statusLine;
    } else if (Object.prototype.hasOwnProperty.call(result, "statusLine")) {
      preserved.push("statusLine");
    }
  }
  if (additions.outputStyle !== null) {
    if (deepEqual(result.outputStyle, additions.outputStyle)) {
      delete result.outputStyle;
    } else if (Object.prototype.hasOwnProperty.call(result, "outputStyle")) {
      preserved.push("outputStyle");
    }
  }
  if (additions.hook !== null) {
    const hooks = result.hooks;
    if (hooks && typeof hooks === "object" && Array.isArray(hooks.SessionStart)) {
      const index = hooks.SessionStart.findIndex((entry) =>
        deepEqual(entry, additions.hook));
      if (index >= 0) {
        hooks.SessionStart.splice(index, 1);
        if (hooks.SessionStart.length === 0) {
          delete hooks.SessionStart;
        }
        if (Object.keys(hooks).length === 0) {
          delete result.hooks;
        }
      } else {
        preserved.push("hooks.SessionStart");
      }
    } else {
      preserved.push("hooks.SessionStart");
    }
  }
  return { settings: result, preserved };
}


async function restoreCodeLayerA(options = {}) {
  const configRoot = path.resolve(options.configRoot || defaultConfigRoot());
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  const statePath = statePathFor(dataRoot, configRoot);
  if (!(await pathExists(statePath))) {
    throw new CodeLayerError(
      "NOT_INSTALLED",
      "No managed CLI Layer A installation was found.",
    );
  }
  const state = await readJson(statePath);
  if (state.schemaVersion !== MANAGED_STATE_VERSION) {
    throw new CodeLayerError(
      "STATE_VERSION_UNSUPPORTED",
      `Unsupported backup state version ${state.schemaVersion}.`,
    );
  }
  if (path.resolve(state.configRoot) !== configRoot) {
    throw new CodeLayerError(
      "STATE_MISMATCH",
      "The managed state belongs to a different configuration root.",
    );
  }
  const settingsPath = path.join(configRoot, "settings.json");
  let currentBytes = null;
  let currentSettings = {};
  if (await pathExists(settingsPath)) {
    currentBytes = await fsp.readFile(settingsPath);
    try {
      currentSettings = JSON.parse(currentBytes.toString("utf8"));
    } catch (error) {
      throw new CodeLayerError(
        "INVALID_SETTINGS",
        `Current Claude settings are not valid JSON; no files were changed: ${error.message}`,
      );
    }
  }

  const preRestoreBackup = path.join(state.backupRoot, "pre-restore-settings.json");
  if (currentBytes) {
    await backupFile(settingsPath, preRestoreBackup);
  }
  const currentHash = currentBytes ? sha256Bytes(currentBytes) : null;
  const preservedSettings = [];
  let exactSettingsRestore = false;
  if (currentHash === state.installedSettingsSha256) {
    exactSettingsRestore = true;
    if (state.originalSettingsSha256 === null) {
      await fsp.rm(settingsPath, { force: true });
    } else {
      const originalBackup = path.join(state.backupRoot, "settings.json");
      if (!(await pathExists(originalBackup))) {
        throw new CodeLayerError(
          "BACKUP_MISSING",
          `Original settings backup is missing: ${originalBackup}`,
        );
      }
      if ((await sha256File(originalBackup)) !== state.originalSettingsSha256) {
        throw new CodeLayerError(
          "BACKUP_HASH_MISMATCH",
          "Original settings backup SHA-256 does not match managed state.",
        );
      }
      await writeFileAtomic(settingsPath, await fsp.readFile(originalBackup));
    }
  } else {
    const cleaned = removeAddedSettings(currentSettings, state.additions);
    preservedSettings.push(...cleaned.preserved);
    if (
      state.originalSettingsSha256 === null
      && Object.keys(cleaned.settings).length === 0
    ) {
      await fsp.rm(settingsPath, { force: true });
    } else {
      await writeJsonAtomic(settingsPath, cleaned.settings);
    }
  }

  const preservedAssets = [];
  let removedAssets = 0;
  for (const asset of [...state.assets].reverse()) {
    ensureInside(configRoot, asset.path);
    if (!(await pathExists(asset.path))) {
      continue;
    }
    const hash = await sha256File(asset.path);
    if (hash === asset.installedSha256) {
      await fsp.rm(asset.path, { force: true });
      await removeEmptyParents(path.dirname(asset.path), configRoot);
      removedAssets += 1;
    } else {
      preservedAssets.push(asset.relativePath);
    }
  }
  await fsp.rm(statePath, { force: true });
  await removeEmptyParents(path.dirname(statePath), dataRoot);

  if (
    exactSettingsRestore
    && state.originalSettingsSha256 !== null
    && (await sha256File(settingsPath)) !== state.originalSettingsSha256
  ) {
    throw new CodeLayerError(
      "RESTORE_VERIFICATION_FAILED",
      "Restored settings SHA-256 does not match the original backup.",
    );
  }
  return {
    configRoot,
    backupRoot: state.backupRoot,
    exactSettingsRestore,
    removedAssets,
    preservedAssets,
    preservedSettings,
  };
}


async function statusCodeLayerA(options = {}) {
  const configRoot = path.resolve(options.configRoot || defaultConfigRoot());
  const dataRoot = path.resolve(options.dataRoot || defaultDataRoot());
  const statePath = statePathFor(dataRoot, configRoot);
  if (!(await pathExists(statePath))) {
    return {
      state: "not-installed",
      configRoot,
    };
  }
  const managed = await readJson(statePath);
  const mismatches = [];
  const settingsPath = path.join(configRoot, "settings.json");
  if (!(await pathExists(settingsPath))) {
    mismatches.push("settings.json is missing");
  } else if ((await sha256File(settingsPath)) !== managed.installedSettingsSha256) {
    mismatches.push("settings.json changed after installation");
  }
  for (const asset of managed.assets) {
    if (!(await pathExists(asset.path))) {
      mismatches.push(`${asset.relativePath} is missing`);
    } else if ((await sha256File(asset.path)) !== asset.installedSha256) {
      mismatches.push(`${asset.relativePath} changed after installation`);
    }
  }
  return {
    state: managed.status,
    mode: managed.mode,
    configRoot,
    backupRoot: managed.backupRoot,
    pluginRoot: path.join(configRoot, "claude-zh", "plugin"),
    mismatches,
    skippedSettings: managed.skippedSettings || [],
    skippedAssets: managed.skippedAssets || [],
  };
}


module.exports = {
  CodeLayerError,
  installCodeLayerA,
  restoreCodeLayerA,
  sha256File,
  statusCodeLayerA,
};
