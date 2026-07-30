# 贡献指南

感谢你帮助完善 Claude Code / Claude Desktop 的简体中文界面。本项目首先保护
Claude 的功能正确性，其次才追求翻译覆盖率。拿不准的字符串保持英文。

## 开始之前

- 阅读 [`CLAUDE.md`](../CLAUDE.md) 的安全红线和
  [`docs/RUNBOOK.md`](RUNBOOK.md) §1.2 的风险决策树。
- 翻译风格以 [`docs/style-guide.md`](style-guide.md) 和
  [`corpus/glossary.json`](../corpus/glossary.json) 为准。
- 代码使用 MIT；提交到 `corpus/` 的翻译语料使用 CC0-1.0。
- 遵守 [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md)。
- 先查看 [`ROADMAP.md`](ROADMAP.md) 和
  [`competitive-analysis.md`](competitive-analysis.md)，避免重复实现已明确不做
  的高风险功能。

## 本地环境

需要 Python 3.11+、Node.js 22.12+ 和 Git。

```powershell
git clone https://github.com/skxxxkx666/claude-zh-bilingual.git
cd claude-zh-bilingual
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install '.[dev]'
npm ci --ignore-scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe schema/validate.py corpus
npm test
npm run validate:support
npx claude-zh doctor --json
```

macOS / Linux 将 Python 路径换成 `.venv/bin/python`。这些命令不会安装或修改
Claude。

Windows 单文件启动器需要 .NET 8 SDK 与官方 Node `22.23.1` Windows x64 分发目录：

```powershell
.\scripts\build_windows_launcher.ps1 -NodeRoot C:\path\to\node-v22.23.1-win-x64
.\artifacts\claude-zh-windows-x64.exe --launcher-version
.\artifacts\claude-zh-windows-x64.exe --launcher-self-test
```

本地 EXE 只能用于验证。Release 资产必须来自 GitHub Actions，不能手工上传。

## 提交翻译

1. 从带有 `translation` 标签的 issue 选择条目；若同时有 `good first issue`，优先
   选择该条目。
2. 在 `corpus/` 中按 unit `id` 找到原文和上下文。
3. 按 RUNBOOK 风险决策树判断。只有 `risk == SAFE` 才能填写 `target`。
4. 术语必须复用 `corpus/glossary.json`；新增术语时同步更新词表并注明判据。
5. 保留全部占位符，满足显示宽度和字节预算。
6. 运行上面的完整校验，再提交 PR。

翻译 PR 只修改 `corpus/`。不要同时修改 patcher、脚本或文档。一个 PR 处理一个
主题，便于审阅和回滚。

## 风险等级变更

- `UNKNOWN → SAFE`：附 UI 位置、版本和人工核验依据。
- `DANGER` / `FRAGILE → SAFE`：附可复现的运行证据，并取得两名独立审阅者批准。
- `SAFE → DANGER` / `FRAGILE`：立即清空译文并在 PR 中说明触发的规则。

风险降级不能通过拆分提交、关闭 CI 或直接推送绕过。证据不足时维持更保守的等级。

## 代码贡献

- patcher 不得硬编码中文译文，运行时只读取 `corpus/`。
- 不提交 Claude 原程序、二进制、ASAR、解包内容或大段非 UI 原文。
- 不修改鉴权、凭证、计费、代理、遥测或官方更新机制。
- 修改用户文件前必须备份；任何失败必须自动还原。
- 新平台支持必须附对应的冒烟测试结果。
- 不放宽 `verifier/` 断言，不自行修改 `schema/`。

提交信息使用项目约定的作用域，例如：

```text
feat(corpus): 补充 cli@2.1.220 状态栏译文
fix(patcher): 修复 Windows 二进制还原校验
docs(docs): 补充新版本适配说明
```

## Pull Request 检查

PR 必须：

- 说明变更范围和不在范围内的事项；
- 列出实际执行的测试；
- 对风险等级变化提供证据；
- 通过 `Tests` 和 `Validate corpus`；
- 不包含凭证、用户数据或上游专有产物。

用户可见功能需要在 [`CHANGELOG.md`](../CHANGELOG.md) 的 `Unreleased` 记录；改变
支持范围时同步更新 release manifest 并重新生成支持矩阵。不要用新提交覆盖已有 tag
的 Release 资产。

安全问题不要提交公开 issue，请按 [`SECURITY.md`](../SECURITY.md) 使用 GitHub
私密漏洞报告。
