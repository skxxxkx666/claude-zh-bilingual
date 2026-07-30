# 变更记录

本项目记录用户可见变化、支持边界和验证结果。版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)，预发布版本不替代稳定版。

## [Unreleased]

## [0.2.0-rc.2] - 2026-07-30

### 新增

- 增加只读 `claude-zh doctor` 与 `--json` 机器可读报告；
- Windows 单文件启动器菜单增加诊断入口；
- 增加文档导航、路线图、诊断指南和同类项目对比。

### 改进

- README 首屏按稳定版、候选 EXE、诊断和贡献场景提供入口；
- 增加功能建议 Issue Form 与依赖更新配置；
- Release 工作流禁止用新提交覆盖旧 tag 对应的发布资产。

## [0.2.0-rc.1] - 2026-07-29

### 新增

- 发布 Windows x64 单文件启动器候选版；
- EXE 内置 Node `22.23.1`，无需系统 Node、npm 或 .NET；
- 启动器逐文件校验长度与 SHA-256，并完成真实 ConPTY 自检；
- Release 同时提供 EXE、npm `.tgz`、`SHA256SUMS` 和
  `SHA256SUMS.windows`。

### 安全

- 候选 EXE 未做 Authenticode 签名，Release 与 README 明确展示 SmartScreen
  警告；
- 未签名启动器只允许作为 prerelease，稳定版仍为 `v0.1.0`；
- 发布资产只由 GitHub Actions 构建，不接受本地 EXE。

### 验证

- Desktop D1–D4、Claude Code A/B 层 S1–S3；
- 内置 CLI `--help` 与 `node-pty` / ConPTY `PTY_OK`；
- 发布后重新下载 EXE，复核 SHA-256 与 `NotSigned` 状态。

## [0.1.0] - 2026-07-29

### 新增

- 支持 Windows 非 MSIX Claude Desktop `1.18286.0`；
- 提供 `zh` 纯中文与 `bilingual` 中英对照模式；
- 安装前创建外部备份，失败自动还原，手动还原后校验原始 SHA-256；
- 提供 CC0-1.0 翻译语料、术语表、风险分类和支持矩阵。

### 安全

- MSIX 只读检测并拒绝写入 `WindowsApps`；
- 检测到 Claude 正在运行时停止，不自动结束进程；
- DANGER、FRAGILE 和 UNKNOWN 字符串不参与翻译。

[Unreleased]: https://github.com/skxxxkx666/claude-zh-bilingual/compare/v0.2.0-rc.2...HEAD
[0.2.0-rc.2]: https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.2
[0.2.0-rc.1]: https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.2.0-rc.1
[0.1.0]: https://github.com/skxxxkx666/claude-zh-bilingual/releases/tag/v0.1.0
