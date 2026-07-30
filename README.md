# Claude Code 中文汉化 / Claude Desktop 中文化

**`claude-zh-bilingual`：Claude Code 与 Claude Desktop 的安全中文化和中英
对照。**

一份可复用语料，两种显示模式；安装可诊断、改动可验证、结果可还原。

[English](README.en.md) ·
[下载稳定版](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest) ·
[Windows EXE 候选版](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2) ·
[文档](docs/README.md) ·
[支持矩阵](docs/support-matrix.md) ·
[路线图](docs/ROADMAP.md) ·
[变更记录](CHANGELOG.md) ·
[参与贡献](docs/CONTRIBUTING.md)

[![Tests](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/test.yml/badge.svg)](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/test.yml)
[![Validate corpus](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/validate.yml/badge.svg)](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/validate.yml)
[![Windows launcher](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/launcher.yml/badge.svg)](https://github.com/skxxxkx666/claude-zh-bilingual/actions/workflows/launcher.yml)
[![Stable release](https://img.shields.io/github/v/release/skxxxkx666/claude-zh-bilingual?display_name=tag&sort=semver)](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest)
[![License: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Corpus: CC0](https://img.shields.io/badge/corpus-CC0-green.svg)](corpus/LICENSE)

看得懂中文，也能保留 `compact`、`Permission denied` 等英文关键词去查官方文档和
搜索报错。项目只翻译经过审核的界面文案，不修改鉴权、网络或模型提示。

## 先选你的路径

| 你的目标 | 推荐入口 | 状态 |
|---|---|---|
| Windows 上双击使用，不安装 Node | [`v0.2.0-rc.2` 单文件 EXE](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2) | 候选版，未签名 |
| 使用经过完整 Desktop 冒烟的稳定包 | [`v0.1.0` `.tgz`](https://github.com/skxxxkx666/claude-zh-bilingual/releases/latest) | 稳定版 |
| 判断安装、版本或还原问题 | [`claude-zh doctor`](docs/diagnostics.md) | 只读、不联网 |
| 提交翻译或代码 | [贡献指南](docs/CONTRIBUTING.md) | PR + CI 审核 |

> 稳定版 `v0.1.0` 支持 Windows 非 MSIX Claude Desktop `1.18286.0`，
> D1–D4 已全部通过。
> 当前源码另含 Claude Code `2.1.201` 的 A 层，以及 `2.1.220` 的实验性 B 层；
> 两层均已通过 S1–S3。
>
> `v0.2.0-rc.2` 提供 Windows x64 单文件 EXE 候选版。它未经
> Authenticode 签名，可能触发 SmartScreen；稳定版 `v0.1.0` 保持不变。

![Claude Desktop 中文菜单](docs/screenshots/desktop-menu-zh.png)

## 项目有什么不同

| 能力 | 本项目的做法 |
|---|---|
| 两种显示模式 | `zh` 显示“压缩上下文”；`bilingual` 显示“压缩上下文 (compact)” |
| 双产品 | 同一套风险规则和术语服务 Claude Code 与 Claude Desktop |
| 可复用数据 | 翻译语料使用 CC0-1.0，代码使用 MIT |
| 风险门禁 | 只有 `SAFE` UI 文案能翻译；prompt、tool description 和代码匹配字符串保持英文 |
| 失败方式 | 新版本、结构或哈希不匹配时停止，不用“尽量写入”换取表面覆盖率 |
| 诊断与还原 | `doctor` 只读检查；持久改动先备份，失败自动回滚，还原后验证 SHA-256 |

Claude Code 与 Claude Desktop 的产品名、命令、报错关键词和官方文档高频术语可以
保留英文。语料采用 CC0-1.0，其他项目也可以复用。

当前量化基线是 340 / 740 条 SAFE 语料有译文（45.9%），Desktop 已验证 320 条，
Claude Code A 层使用 19 条，B 层验证 1 条等宽 spinner；这不等同于界面可见
覆盖率。完整口径见 [`docs/metrics.md`](docs/metrics.md)，同类项目取舍见
[`docs/competitive-analysis.md`](docs/competitive-analysis.md)。

## 当前能力

- `zh`：仅把人工确认的 SAFE 界面文案替换为中文。
- `bilingual`：中文后按术语优先级保留最多两个可检索英文词。
- Claude Code A 层：中文 statusline、启动提示、回复样式和 `/zh-*` skills，不修改 Claude Code 程序。
- Claude Code B 层：通过 PTY 只改终端输出，当前仅替换 1 条已实测的等宽 spinner 文案，不修改二进制或用户配置。
- 安装前在应用目录之外创建并校验逐文件备份。
- 安装中途失败自动还原；手动还原后逐文件验证原始 SHA-256。
- 检测到正在运行的 Claude 时拒绝修改，不会结束进程。
- Microsoft Store / 企业 MSIX 只读检测并拒绝写入。
- 每 6 小时检查官方版本源；结构稳定时自动继承并开 review PR，低于 80% 继承率时停止并开 issue。

补丁只处理外部语言资源与 SAFE UI 字面量。`app.asar` 仅用于读取版本，不会被重打包；鉴权、登录、凭证、计费、限额和代理路径不在修改范围内。

## 最快上手

### Windows 单文件启动器（候选）

从
[`v0.2.0-rc.2` 预发布页](https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2)
下载 `claude-zh-windows-x64.exe` 和 `SHA256SUMS.windows`。此 EXE 未做
Authenticode 代码签名，只从本仓库 Release 下载，并在运行前核对：

```powershell
(Get-FileHash .\claude-zh-windows-x64.exe -Algorithm SHA256).Hash.ToLowerInvariant()
Get-Content .\SHA256SUMS.windows
```

两处哈希必须完全一致。SmartScreen 仍可能显示“Windows 已保护你的电脑”；确认下载
来源和哈希后，可选择“更多信息”→“仍要运行”。无法确认或哈希不一致时不要运行。

双击 EXE 后可从中文菜单完成 Desktop、Claude Code A 层的安装、状态检查和还原；
实验性 B 层放在高级选项中。EXE 内含锁定的 Node 运行时，用户不需要另装 Node、
npm 或 .NET。

Release 中的候选启动器只由 GitHub Actions 构建，本地构建不会上传。架构、缓存
目录、完整性校验、体积和签名限制见
[`docs/windows-launcher.md`](docs/windows-launcher.md)。

### 当前稳定版

从 GitHub Release 下载 `claude-zh-0.1.0.tgz`，在空目录执行：

```powershell
npm install .\claude-zh-0.1.0.tgz
npx claude-zh status
npx claude-zh install desktop --mode=zh
```

双语模式：

```powershell
npx claude-zh install desktop --mode=bilingual
```

安装前先正常退出 Claude。补丁器会打印备份目录；如果发现 MSIX、版本不匹配、Claude 仍在运行或资源结构不匹配，会在写入前停止。

### Claude Code A 层（当前源码）

```powershell
npm ci --ignore-scripts
node .\bin\claude-zh.cjs status code
node .\bin\claude-zh.cjs install code --layer=a --mode=zh
claude
node .\bin\claude-zh.cjs restore code
```

双语模式把安装命令改为 `--mode=bilingual`。安装器只合并缺失设置；已有 statusline、output style、hooks 和同名文件不会被覆盖。当前 Claude Code `2.1.201` 不注册中文命令名，因此提供 `/zh-compact`、`/zh-help`、`/zh-resume`，不声称 `/压缩` 已受支持。

### Claude Code B 层（实验性，当前源码）

B 层只支持经过实测的 Claude Code `2.1.220` Windows x64 原生程序，并要求显式传入
二进制路径：

```powershell
npm ci --ignore-scripts
node .\bin\claude-zh.cjs run code --layer=b --binary=C:\path\to\claude.exe
```

需要向 Claude 转发参数时放在 `--` 后：

```powershell
node .\bin\claude-zh.cjs run code --layer=b --binary=C:\path\to\claude.exe -- --model=sonnet
```

B 层不安装文件，没有单独的还原命令；退出包装进程即恢复原始行为。它严格要求译文与
原文终端显示宽度相等，不等宽条目直接拒绝加载。`2.1.220` 的 C 层二进制实验因
单字节字符串无法正确承载中文而停止，项目不会分发乱码或签名失效的补丁。

## 状态与还原

```powershell
npx claude-zh doctor
npx claude-zh doctor --json
npx claude-zh status
npx claude-zh restore desktop
```

`doctor` 会只读检查 Node、Desktop 安装形态与受管理文件、Claude Code A 层状态。
退出码和 Issue 提交方式见 [`docs/diagnostics.md`](docs/diagnostics.md)。

还原前同样先退出 Claude。还原成功后，生成的 `zh-CN.json`、状态文件和已使用的备份会被清理。

从 [`docs/README.md`](docs/README.md) 进入完整文档。平台状态见
[`docs/support-matrix.md`](docs/support-matrix.md)，阶段证据和勘测记录也从文档导航
访问。

## 从源码验证

需要 Python 3.11+ 与 Node.js 22.12+。依赖只安装到项目环境，不需要全局安装 Claude，也不会修改本机 MSIX：

```powershell
python -m pip install '.[dev]'
npm ci --ignore-scripts
python -m unittest discover -s tests -v
python schema/validate.py corpus
npm test
npm run validate:support
npm pack --dry-run
```

Windows 启动器还需要 .NET 8 SDK 与官方 Node `22.23.1` Windows x64 分发目录：

```powershell
.\scripts\build_windows_launcher.ps1 -NodeRoot C:\path\to\node-v22.23.1-win-x64
.\artifacts\claude-zh-windows-x64.exe --launcher-self-test
```

## 项目定位

本项目不是全局字符串替换。核心资产是可跨版本继承的翻译语料、中英术语表、经过验证的 SAFE 风险白名单，以及提取、分类、校验和冒烟测试流水线。

只有明确标记为 `SAFE` 的界面展示文案才允许翻译。tool description、system prompt、代码匹配字符串以及无法确认用途的内容均保持英文。

M1 实测数据见 [`report/M1-勘测报告.md`](report/M1-勘测报告.md)。

## 参与贡献

欢迎提交翻译、术语、平台验证和工具改进。首次参与请先阅读
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) 和
[`docs/style-guide.md`](docs/style-guide.md)。

- 翻译 PR 只修改 `corpus/`，且只有 `SAFE` 文案可以翻译。
- `DANGER` / `FRAGILE` 降为 `SAFE` 需要实测证据和两名独立审阅者。
- 不接受在 patcher 或脚本中硬编码译文。
- Bug、翻译建议和新版本请求请使用对应的 Issue 模板。
- 安全问题按 [`SECURITY.md`](SECURITY.md) 私密报告。
- 使用问题优先发到 [`SUPPORT.md`](SUPPORT.md) 指向的 Discussions。

当前路线和量化基线见 [`docs/metrics.md`](docs/metrics.md)。社区参与遵守
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 同类项目与致谢

感谢
[`taekchef/claude-code-zh-cn`](https://github.com/taekchef/claude-code-zh-cn)、
[`KongBai1145/claude-code-zh-cn`](https://github.com/KongBai1145/claude-code-zh-cn)
和
[`Jyy1529/claude-desktop_win-zh_cn`](https://github.com/Jyy1529/claude-desktop_win-zh_cn)
公开其中文化、安装、诊断与恢复经验。本项目借鉴常见的用户旅程与工程模式，没有
复制它们的代码或翻译表。详细比较、许可证和明确不采用的做法见
[`docs/competitive-analysis.md`](docs/competitive-analysis.md)。

## FAQ

### 补丁失效怎么办？

先运行 `npx claude-zh status`。Desktop 或 A 层显示文件被后续修改时，不会覆盖新
内容；先执行对应还原，再用受支持版本重新安装。B 层没有持久补丁，退出后重新运行
包装命令即可。

### Claude 更新后怎么办？

不要自动重打补丁，也不要阻止官方更新。等待支持矩阵列出新版本；结构或 surface
发生变化时，流水线会停止继承并要求重新审阅。

### 如何完全卸载？

先运行 `npx claude-zh restore desktop` 或 `npx claude-zh restore code`，再删除
安装 `claude-zh` 的本地目录。B 层只需退出进程，不写入 Claude 安装目录。

### 为什么有些地方还是英文？

默认 `UNKNOWN`、会进入模型提示的 `DANGER`、被程序比较的 `FRAGILE` 和没有实际
surface 证据的文案都不会翻译。少翻一条比让 agent 静默退化更安全。

### 为什么保留英文术语？

产品功能名、报错关键词和官方文档高频术语保留英文，便于查文档、搜索报错和提交
issue；纯中文模式仍会保留不可安全翻译的标识符与命令。

## 安全边界

- 不修改鉴权、登录、凭证、计费、用量、限额或代理配置。
- 补丁脚本不发起网络请求。
- 不收集遥测或用户数据。
- 修改前必须备份，失败时自动还原。
- 仓库和 release 不分发 Claude 原程序、二进制、ASAR 或打好补丁的成品。

本项目是非官方项目，与 Anthropic 无关。Claude 是 Anthropic, PBC 的商标。官方安装入口见 [Claude 下载页](https://claude.com/download)。

## License

- 代码：MIT，见 [`LICENSE`](LICENSE)
- `corpus/` 翻译语料：CC0-1.0，见 [`corpus/LICENSE`](corpus/LICENSE)
