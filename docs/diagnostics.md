# 诊断指南

`doctor` 是只读诊断入口。它不联网、不结束 Claude 进程、不写入 Claude 安装目录或
用户配置。

## 运行

使用 npm 包：

```powershell
npx claude-zh doctor
```

使用 Windows 单文件启动器：

- 双击 EXE，选择“运行只读诊断”；或
- 在 PowerShell 执行：

```powershell
.\claude-zh-windows-x64.exe doctor
```

提交 Issue 时使用机器可读输出：

```powershell
npx claude-zh doctor --json
```

如果自动发现了错误的 Desktop 路径，可以只读检查指定目录：

```powershell
npx claude-zh doctor --json --app-root=C:\path\to\Claude\app
```

## 检查内容

| 检查 | 结果含义 |
|---|---|
| `node` | 当前 Node 是否满足 `package.json` 的最低版本 |
| `desktop` | Desktop 安装形态、补丁状态、受管理文件是否被后续修改 |
| `code-layer-a` | A 层是否安装、settings 和生成文件是否仍与安装记录一致 |

实验性 B 层不会自动探测 Claude 二进制。它仍要求用户显式传入已验证版本的路径，
因此不包含在默认 doctor 中。

## 退出码

| 退出码 | 含义 |
|---:|---|
| `0` | 检查通过，或目标尚未安装但没有发现风险 |
| `1` | 需要注意，例如 MSIX 不受支持、受管理文件在安装后发生变化 |
| `2` | 环境或读取过程发生错误 |

`INFO` 不是失败。比如没有安装 Claude Code A 层时，doctor 会如实报告但仍可返回
`0`。

## 常见结果

### `MSIX installation detected`

项目不会写入 `WindowsApps`。安装官网个人安装器（非 MSIX）后重新诊断，或者继续
使用英文版。不要修改目录权限，也不要取得所有权后强行写入。

### `changed after installation`

Claude 可能已经更新，或文件被其他工具修改。先正常退出 Claude，再执行对应还原：

```powershell
npx claude-zh restore desktop
npx claude-zh restore code
```

不要直接覆盖新文件。还原成功后等待支持矩阵列出当前版本，再重新安装。

### `does not satisfy >=22.12.0`

仅 npm 使用路径需要升级 Node。Windows 单文件 EXE 内置锁定运行时，不依赖系统
Node。

## 提交问题

公开 Bug Issue 可以附：

- `doctor --json` 输出；
- Claude 产品与版本；
- 操作系统和安装形态；
- 最小复现步骤；
- 还原是否成功。

先检查输出中是否包含用户名或自定义路径。安全漏洞、凭证或可利用细节使用
[GitHub 私密漏洞报告](https://github.com/skxxxkx666/claude-zh-bilingual/security/advisories/new)，
不要提交公开 Issue。
