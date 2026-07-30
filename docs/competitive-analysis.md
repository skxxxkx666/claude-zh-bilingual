# 同类项目对比与借鉴

> 核验日期：2026-07-30。此文档比较公开仓库当日可见的 README、目录、Release、
> 许可证和 GitHub Community Profile。条目数量和版本窗口是各项目自己的公开口径，
> 不代表本项目对其完整性或安全性的背书。

## 对比对象

| 项目 | 公开定位 | 2026-07-30 快照 | 许可证 |
|---|---|---|---|
| [`taekchef/claude-code-zh-cn`](https://github.com/taekchef/claude-code-zh-cn) | Claude Code 四层中文本地化 | README 声明 1895 条翻译、版本支持矩阵、doctor 与自动降级；最新 Release `v2.6.1` | [MIT](https://github.com/taekchef/claude-code-zh-cn/blob/main/LICENSE) |
| [`KongBai1145/claude-code-zh-cn`](https://github.com/KongBai1145/claude-code-zh-cn) | Claude Code 一键汉化 | README 声明 1742 条 UI 翻译、187 个 spinner 动词、Windows 可视化安装器与 doctor；最新 Release `v2.5.0` | [MIT](https://github.com/KongBai1145/claude-code-zh-cn/blob/main/LICENSE) |
| [`Jyy1529/claude-desktop_win-zh_cn`](https://github.com/Jyy1529/claude-desktop_win-zh_cn) | Windows Claude Desktop 中文补丁与桌面助手 | README 声明 12700+ keys、Tauri 便携 GUI、进度日志、手动选目录、诊断与恢复；最新 Release `v0.1.0` | [MIT](https://github.com/Jyy1529/claude-desktop_win-zh_cn/blob/master/LICENSE.md) |
| 本项目 | Claude Code + Desktop 安全中文化与中英对照 | 340 / 740 条 SAFE 语料有译文、双模式、CC0 语料、风险门禁、Windows 单文件启动器 | 代码 MIT；语料 CC0-1.0 |

数据来源：
[taekchef README](https://github.com/taekchef/claude-code-zh-cn#readme)、
[KongBai1145 README](https://github.com/KongBai1145/claude-code-zh-cn#readme)、
[Jyy1529 README](https://github.com/Jyy1529/claude-desktop_win-zh_cn#readme)及各自
Release 页面。本项目数据来自 [`metrics.md`](metrics.md)。

## 能力与工程取向

| 维度 | taekchef | KongBai1145 | Jyy1529 | 本项目 |
|---|---|---|---|---|
| 主要产品 | Claude Code | Claude Code | Claude Desktop | Claude Code + Desktop |
| 用户入口 | shell / PowerShell 安装器 | 批处理可视化菜单 + shell | Tauri GUI + PowerShell | 单文件 EXE 菜单 + npm CLI |
| 显示策略 | 纯中文为主 | 纯中文为主 | 纯中文为主 | 纯中文或中英对照 |
| 更新兼容 | 四层机制与自动降级 | 上游同步与自动修复 | 更新后重跑补丁 | 版本门禁、精确匹配、低继承率停手 |
| 自助排障 | doctor、日志、支持矩阵 | doctor、备份状态 | GUI 进度、实时日志、诊断面板 | status、支持矩阵；本轮补齐 doctor |
| 恢复策略 | 备份、失败降级、卸载 | 验证备份后恢复 | 备份与恢复脚本 | 外部备份、失败自动回滚、还原后 SHA-256 |
| 翻译数据复用 | 项目内 JSON | 项目内 JSON | 项目内资源 JSON | 独立 CC0 corpus + glossary |
| 风险边界 | 分层跳过失败项 | 备份与自动修复 | 混合资源和运行时注入 | SAFE 白名单；DANGER / FRAGILE 永不翻译 |
| 开源协作 | README、CHANGELOG、贡献指南、CI | README、CHANGELOG、贡献指南、CI | README 与源码 | Community Profile 100%、Issue Forms、PR 门禁、双许可证 |

GitHub Community Profile 只衡量社区文件是否存在，不衡量软件质量。2026-07-30
快照中，本项目为 100%，taekchef 与 KongBai1145 为 71%，Jyy1529 为 42%。因此本轮
重点不是堆更多模板，而是让已有规范更容易被用户找到和使用。

## 值得融合的优点

### 1. 第一屏直接回答“它是什么、我该下哪个”

taekchef 和 KongBai1145 都把一句定位、安装承诺、版本徽章和安装入口集中在 README
首屏。Jyy1529 直接把便携 EXE、SHA-256 和运行要求放在前面。

本项目采用：

- 首屏突出“Claude Code + Desktop”“纯中文 + 中英对照”“可诊断 + 可还原”；
- 用选择表区分稳定 `.tgz`、候选 EXE、源码贡献和问题诊断；
- 候选 EXE 继续明确展示未签名状态，不用“装完即用”掩盖 SmartScreen 与支持范围。

### 2. doctor 式自助诊断

两个 CLI 项目都提供 doctor，Jyy1529 则把诊断状态和日志放进 GUI。它们共同解决了
Issue 中最常见的“用户不知道该贴什么信息”问题。

本项目采用只读 `claude-zh doctor`：

- 检查 Node 版本、Desktop 安装形态、Desktop 管理文件、Claude Code A 层状态；
- `--json` 输出稳定结构，便于 Issue 模板和自动化采集；
- 不联网、不结束进程、不修改 Claude 或用户配置；
- 单文件 EXE 菜单直接提供诊断入口。

### 3. 可见的变更记录与路线

taekchef 和 KongBai1145 都维护 CHANGELOG。三个项目的 README 都会明确当前版本与
支持边界。

本项目采用：

- 根目录 [`CHANGELOG.md`](../CHANGELOG.md) 按 Release 记录用户可见变化和验证；
- [`ROADMAP.md`](ROADMAP.md) 分“当前、下一步、以后、明确不做”；
- [`README.md`](README.md) 作为文档入口，避免关键规范散落后无法发现。

### 4. 覆盖证据而不是模糊口号

三个项目都会展示条目数、验证版本或测试数。Jyy1529 还单独生成 i18n 覆盖报告。

本项目继续使用更保守的口径：

- [`metrics.md`](metrics.md) 记录 SAFE、已翻译、UNKNOWN 和事故数；
- [`support-matrix.md`](support-matrix.md) 记录平台、版本与冒烟证据；
- README 只引用有来源的快照，不把语料条目数等同于实际可见覆盖率。

## 明确不照搬的做法

| 做法 | 不采用的原因 |
|---|---|
| 自动翻译会参与模型触发判断的 skill / tool description | 可能改变 agent 行为，违反 DANGER 边界 |
| 为安装方便自动结束 Claude 进程 | 可能造成未保存状态丢失；本项目只提示用户正常退出 |
| 未经支持矩阵验证就声称“完整支持” | 新版本结构变化可能让部分规则失效 |
| 修改 WindowsApps、全局 Node 或关闭系统安全功能 | 超出最小权限与可恢复边界 |
| 把条目总数直接宣传成界面覆盖率 | 资源 key、候选字符串和真实可见 UI 不是同一指标 |
| 为追求 GUI 功能复制会话管理、DOM 注入或第三方网关功能 | 偏离中文化核心，也扩大敏感代码和维护面 |

## 许可与致谢规则

三个对比项目均使用 MIT 许可证。当前改造只借鉴常见的项目结构、用户旅程和诊断
思路，文案与实现均为本项目原创，没有复制其源代码或翻译表。

以后如果确实复用 MIT 代码，PR 必须：

1. 列出原仓库、文件、commit 和许可证；
2. 保留原版权与许可声明；
3. 说明本项目做了哪些修改；
4. 确认没有把对方提取的上游专有内容带入本仓库。

感谢三个项目公开其实现和使用经验。对比是为了明确取舍，不代表它们是本项目的
上游，也不暗示任何合作或背书关系。

## 本项目最终定位

> 为 Claude Code 与 Claude Desktop 提供可诊断、可还原、可复用的简体中文本地化；
> 用户可以选择纯中文或保留可检索英文术语的中英对照模式。覆盖率服从安全边界，
> 未验证内容保持英文。

每次准备稳定版本前复核一次本文；竞品数字只作为带日期的快照，不持续追逐。
