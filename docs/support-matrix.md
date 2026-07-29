# 支持矩阵

> 此文件由 `python scripts/release_status.py --write` 生成，数据源是 `release/desktop-v0.1.0.json`，不要手工修改。

## v0.1.0 状态

当前门禁：**可发布**。

| 断言 | 状态 | 证据 |
|---|---|---|
| D1 | pass | 补丁后复制环境进程存活超过 12 秒，无崩溃弹窗 |
| D2 | pass | 文件、编辑、查看、帮助菜单及新建对话、关闭窗口、退出可见 |
| D3 | pass | 已登录补丁副本发送“请只回复 D3 OK”，Claude 返回“D3 OK” |
| D4 | pass | 1202x801 基线中差异像素占 0.3802%，低于 5% 上限 |

## 平台与版本

| 平台 | 安装类型 | Claude Desktop | 状态 | 说明 |
|---|---|---|---|---|
| Windows | 官网个人安装器（非 MSIX） | 1.18286.0 | 支持 | D1–D4 全部通过，安装与还原哈希验证通过 |
| Windows | Microsoft Store / 企业 MSIX | 1.18286.0 | 不支持 | 只读检测并拒绝写入，不修改 WindowsApps |
| macOS | 全部 | 全部 | 不支持 | 尚未实现或验证签名安全的补丁路径 |

## 安装与还原

从 GitHub Release 下载 `claude-zh-0.1.0.tgz` 后，在空目录执行：

```powershell
npm install .\claude-zh-0.1.0.tgz
npx claude-zh status
npx claude-zh install desktop --mode=zh
npx claude-zh restore desktop
```

安装和还原前都要正常退出 Claude。补丁器不会结束进程，会在改动前打印并校验应用目录之外的备份路径；还原完成后逐文件核对原始 SHA-256。

MSIX 安装只返回 `msix-unsupported`，不写入 `WindowsApps`。macOS 当前不支持。
