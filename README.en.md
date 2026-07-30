# Claude Code Chinese localization / Claude Desktop Chinese localization

`claude-zh-bilingual` is a safety-first, reversible Simplified Chinese
localization for Claude Code and Claude Desktop. Its bilingual mode keeps
searchable English terms such as `compact` and `Permission denied` next to the
Chinese UI text.

[简体中文](README.md) ·
[Latest release](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest) ·
[Windows EXE candidate](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2) ·
[Documentation](docs/README.md) ·
[Support matrix](docs/support-matrix.md) ·
[Roadmap](docs/ROADMAP.md) ·
[Changelog](CHANGELOG.md) ·
[Contributing](docs/CONTRIBUTING.md)

## Choose a path

| Goal | Entry point | Status |
|---|---|---|
| Double-click on Windows without installing Node | [`v0.2.0-rc.2` EXE](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2) | Unsigned candidate |
| Use the fully smoke-tested Desktop package | [stable `v0.1.0`](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest) | Stable |
| Diagnose installation or restore state | [`claude-zh doctor`](docs/diagnostics.md) | Read-only, offline |
| Contribute translations or code | [contributing guide](docs/CONTRIBUTING.md) | PR + CI review |

## Why this project

- Only reviewed `SAFE` UI strings can be translated.
- Authentication, credentials, billing, network settings, telemetry and model
  prompts are out of scope.
- Every persistent change is backed up and can be restored with SHA-256
  verification.
- The translation corpus is CC0-1.0 and can be reused by other projects.
- `bilingual` mode preserves up to two useful English terms for documentation
  and error searches.
- One risk policy covers both Claude Code and Claude Desktop.
- `doctor` reports the environment and managed-file state without changing it.

This is an unofficial community project and is not affiliated with Anthropic.
It never redistributes Claude executables, ASAR archives or patched upstream
artifacts.

## Current support

| Target | Version | Platform | Status |
|---|---|---|---|
| Claude Desktop | `1.18286.0` | Windows, non-MSIX | Stable, D1–D4 passed |
| Claude Code Layer A | `2.1.201` | Windows | Source implementation, S1–S3 passed |
| Claude Code Layer B | `2.1.220` | Windows x64 | Experimental, one equal-width spinner |
| Microsoft Store / enterprise MSIX | any | Windows | Detected but never modified |
| macOS | any | macOS | Not supported |

See the generated [support matrix](docs/support-matrix.md) for exact lifecycle
and verification evidence.

## Stable installation

Download `claude-zh-0.1.0.tgz` from the
[latest GitHub release](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest),
then run in an empty directory:

```powershell
npm install .\claude-zh-0.1.0.tgz
npx claude-zh status
npx claude-zh install desktop --mode=bilingual
```

Close Claude normally before installing or restoring:

```powershell
npx claude-zh restore desktop
```

## Windows single-file launcher

The
[`v0.2.0-rc.2` prerelease](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2)
includes a double-clickable `claude-zh-windows-x64.exe`. It embeds a pinned
Node runtime, validates every extracted file, and does not require a system
Node, npm, or .NET installation.

This candidate is not Authenticode-signed and may trigger Windows SmartScreen.
Download the EXE and `SHA256SUMS.windows` only from this repository's Release,
then compare:

```powershell
(Get-FileHash .\claude-zh-windows-x64.exe -Algorithm SHA256).Hash.ToLowerInvariant()
Get-Content .\SHA256SUMS.windows
```

The hashes must match exactly. The stable `v0.1.0` release remains unchanged;
this EXE is an explicitly unsigned prerelease built only by GitHub Actions.

See [Windows launcher design and limitations](docs/windows-launcher.md).

## Diagnostics

```powershell
npx claude-zh doctor
npx claude-zh doctor --json
```

The command checks the Node version, Desktop installation type and managed
files, and Claude Code Layer A state. It does not use the network or modify
Claude. See the [diagnostics guide](docs/diagnostics.md) for exit codes.

## Contributing and support

Read [CONTRIBUTING.md](docs/CONTRIBUTING.md) and the
[translation style guide](docs/style-guide.md) before opening a pull request.
Use [GitHub Discussions](https://github.com/skxxxkx666/claude-zh-bilingual/discussions)
for setup questions and private vulnerability reporting for security issues.

Code is MIT licensed. Translation corpus files under `corpus/` are CC0-1.0.

## Prior art

The project comparison credits
[taekchef/claude-code-zh-cn](https://github.com/taekchef/claude-code-zh-cn),
[KongBai1145/claude-code-zh-cn](https://github.com/KongBai1145/claude-code-zh-cn),
and
[Jyy1529/claude-desktop_win-zh_cn](https://github.com/Jyy1529/claude-desktop_win-zh_cn).
This repository adopts common user-flow and diagnostics ideas with original
code and wording; it does not copy their translation tables.
