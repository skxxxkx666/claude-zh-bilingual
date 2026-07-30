# 路线图

> 路线图表达优先级，不承诺日期。安全门禁、支持矩阵和实际维护能力高于功能数量。
> 当前量化状态见 [`metrics.md`](metrics.md)。

## 当前：v0.2 候选阶段

- [x] Windows 非 MSIX Claude Desktop `1.18286.0` 稳定支持；
- [x] Claude Code A 层与实验性 B 层完成 S1–S3；
- [x] Windows x64 单文件 EXE 由 GitHub Actions 构建并附 SHA-256；
- [x] 中英文 README、贡献指南、Issue Forms、支持与安全入口；
- [x] 自动版本侦测、语料继承门禁与支持矩阵；
- [x] 只读 `doctor` 与 JSON 诊断报告；
- [ ] 收集未签名 EXE 候选版的真实用户反馈。

## 下一步

1. 解决或明确关闭
   [CLI `2.1.220` 上游结构阻塞](https://github.com/skxxxkx666/claude-zh-bilingual/issues/2)；
2. 提升 SAFE 语料有译文比例，同时保持 DANGER / FRAGILE 零误翻；
3. 用真实 Issue 验证 `doctor --json` 是否足够定位安装问题；
4. 确定 Authenticode 签名成本、证书保管和 CI 签名方案；
5. 满足稳定门禁后再评估 `v0.2.0`，不把预发布自动转为稳定版。

## 以后再评估

- 在不重复补丁逻辑的前提下，为启动器增加图形进度、日志复制和目录选择；
- 新增 macOS 安全补丁路径，前提是不要求关闭 SIP 或全局 Gatekeeper；
- 把 CC0 语料导出为其他本地化项目易复用的格式；
- 建立由真实社区需求驱动的 `good first issue`，不为数字制造任务。

## 明确不做

- 修改鉴权、凭证、计费、代理、遥测或模型提示；
- 自动结束 Claude 进程或静默请求管理员权限；
- 修改 WindowsApps、全局 Node 或 Claude 官方更新机制；
- 为提高覆盖率翻译 UNKNOWN、DANGER 或 FRAGILE 字符串；
- 分发 Claude 二进制、ASAR、安装包或打好补丁的上游成品；
- 在没有验证证据时承诺“支持所有版本”。

如果官方推出完整中文界面，项目将按 [`PLAN.md`](PLAN.md) 的退出条件归档，并优先把
CC0 语料贡献给仍有复用价值的上游。
