# 支持矩阵

> 此文件由 `python scripts/release_status.py --write` 生成，数据源是 `release/desktop-v0.2.0-rc.1.json`，不要手工修改。

## v0.2.0-rc.1 状态

当前门禁：**候选可发布**。

| 断言 | 状态 | 证据 |
|---|---|---|
| D1 | pass | 补丁后复制环境进程存活超过 12 秒，无崩溃弹窗 |
| D2 | pass | 文件、编辑、查看、帮助菜单及新建对话、关闭窗口、退出可见 |
| D3 | pass | 已登录补丁副本发送“请只回复 D3 OK”，Claude 返回“D3 OK” |
| D4 | pass | 1202x801 基线中差异像素占 0.3802%，低于 5% 上限 |

## Windows 单文件启动器（预发布）

> **SmartScreen 提示：** 此候选 EXE 未做 Authenticode 代码签名，Windows 可能显示“Windows 已保护你的电脑”。只从本仓库的 GitHub Release 下载，并在运行前核对 SHA-256；无法确认来源或哈希不一致时不要运行。

| 项目 | 值 |
|---|---|
| 平台 | Windows x64 |
| 文件 | `claude-zh-windows-x64.exe` |
| 内置 Node | `22.23.1` |
| Authenticode | 未签名 |
| embedded_cli | pass：GitHub Actions 从 EXE 运行内置 CLI --help |
| conpty | pass：GitHub Actions 从 EXE 加载 node-pty 并验证 PTY_OK |

下载同一 Release 中的 EXE 与 `SHA256SUMS.windows`，然后核对：

```powershell
(Get-FileHash .\claude-zh-windows-x64.exe -Algorithm SHA256).Hash.ToLowerInvariant()
Get-Content .\SHA256SUMS.windows
```

两处哈希必须完全一致。确认后双击 EXE，按中文菜单执行安装、状态检查或还原。此候选版不替代稳定版 `v0.1.0`。

## 平台与版本

| 平台 | 安装类型 | Claude Desktop | 状态 | 说明 |
|---|---|---|---|---|
| Windows | 官网个人安装器（非 MSIX） | 1.18286.0 | 支持 | D1–D4 全部通过，安装与还原哈希验证通过 |
| Windows | Microsoft Store / 企业 MSIX | 1.18286.0 | 不支持 | 只读检测并拒绝写入，不修改 WindowsApps |
| macOS | 全部 | 全部 | 不支持 | 尚未实现或验证签名安全的补丁路径 |

## 语料版本生命周期

> 支持范围：最近 3 个 minor 版本，以及最后一个 JS 版本 `cli@2.1.112`。超出范围的版本保留语料但标记 EOL。

| 目标 | 版本 | 生命周期 | 原因 |
|---|---|---|---|
| cli | 2.1.220 | 支持范围 | 最近 3 个 minor 版本 |
| cli | 2.1.201 | 支持范围 | 最近 3 个 minor 版本 |
| cli | 2.1.112 | 支持范围 | 最后一个 JS 版本，长期保留 |
| desktop | 1.18286.0 | 支持范围 | 最近 3 个 minor 版本 |

## 安装与还原

从 GitHub Release 下载 `claude-zh-0.2.0-rc.1.tgz` 后，在空目录执行：

```powershell
npm install .\claude-zh-0.2.0-rc.1.tgz
npx claude-zh status
npx claude-zh install desktop --mode=zh
npx claude-zh restore desktop
```

安装和还原前都要正常退出 Claude。补丁器不会结束进程，会在改动前打印并校验应用目录之外的备份路径；还原完成后逐文件核对原始 SHA-256。

MSIX 安装只返回 `msix-unsupported`，不写入 `WindowsApps`。macOS 当前不支持。
