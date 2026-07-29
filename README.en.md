# Claude Code Chinese localization / Claude Desktop Chinese localization

`claude-zh-bilingual` is a safety-first, reversible Simplified Chinese
localization for Claude Code and Claude Desktop. Its bilingual mode keeps
searchable English terms such as `compact` and `Permission denied` next to the
Chinese UI text.

[简体中文](README.md) ·
[Latest release](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest) ·
[Support matrix](docs/support-matrix.md) ·
[Contributing](docs/CONTRIBUTING.md)

## Why this project

- Only reviewed `SAFE` UI strings can be translated.
- Authentication, credentials, billing, network settings, telemetry and model
  prompts are out of scope.
- Every persistent change is backed up and can be restored with SHA-256
  verification.
- The translation corpus is CC0-1.0 and can be reused by other projects.
- `bilingual` mode preserves up to two useful English terms for documentation
  and error searches.

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

A double-clickable `claude-zh-windows-x64.exe` has passed local feasibility
tests and is built by public CI as a candidate artifact. It embeds a pinned
Node runtime, validates every extracted file, and does not require a system
Node/npm installation. It is not yet part of the stable v0.1.0 release.

See [Windows launcher design and limitations](docs/windows-launcher.md).

## Contributing and support

Read [CONTRIBUTING.md](docs/CONTRIBUTING.md) and the
[translation style guide](docs/style-guide.md) before opening a pull request.
Use [GitHub Discussions](https://github.com/skxxxkx666/claude-zh-bilingual/discussions)
for setup questions and private vulnerability reporting for security issues.

Code is MIT licensed. Translation corpus files under `corpus/` are CC0-1.0.
