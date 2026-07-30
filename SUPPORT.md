# 获取帮助

使用问题、安装确认和设计讨论请发到
[GitHub Discussions](https://github.com/skxxxkx666/claude-zh-bilingual/discussions)。
这样回答可以被后续用户搜索和复用。

以下情况请使用对应入口：

- 可复现的安装、运行或还原故障：提交
  [Bug issue](https://github.com/skxxxkx666/claude-zh-bilingual/issues/new?template=bug.yml)；
- 翻译建议：提交
  [翻译 issue](https://github.com/skxxxkx666/claude-zh-bilingual/issues/new?template=translation.yml)；
- Claude 新版本适配：提交
  [上游版本 issue](https://github.com/skxxxkx666/claude-zh-bilingual/issues/new?template=upstream-version.yml)；
- 安全漏洞：使用
  [私密漏洞报告](https://github.com/skxxxkx666/claude-zh-bilingual/security/advisories/new)，
  不要公开利用细节。

提问前请查看 [`docs/support-matrix.md`](docs/support-matrix.md)。不在支持矩阵中的
平台或版本可以讨论，但维护者不会要求用户关闭系统安全功能来完成适配。

提交安装问题前运行：

```powershell
npx claude-zh doctor --json
```

附上输出前先检查其中的用户名和自定义路径。诊断命令只读且不联网；结果解释见
[`docs/diagnostics.md`](docs/diagnostics.md)。
