# Windows 单文件启动器

## 结论

Windows x64 单文件 EXE 可行。推荐方案不是重写现有补丁器，而是用一个很小的
.NET Native AOT 引导器携带：

- 官方 Node.js `22.23.1` Windows x64 运行时；
- `npm ci --omit=dev --ignore-scripts` 安装的锁定生产依赖；
- npm 包允许发布的 `bin/`、`patchers/`、`corpus/` 和许可证文件。

用户只下载一个 `claude-zh-windows-x64.exe`。首次运行时，引导器把内部文件释放到
`%LOCALAPPDATA%\claude-zh\portable\v<版本>-<payload hash>`，逐文件核对 SHA-256
后再运行内置 Node。后续启动会重新校验，payload 变化时使用新的隔离目录。

这属于“单文件分发”，不是“永不落盘的单进程程序”。`node-pty` 依赖 `.node`、
DLL 和辅助 EXE，必须以普通文件形式由 Windows 加载。

## 实测原型

2026-07-30 的本地可行性构建：

| 项目 | 结果 |
|---|---:|
| 单文件大小 | 39,746,560 字节 |
| 内置 Node | 22.23.1 |
| 启动器运行时 | .NET 8 Native AOT |
| 内置 CLI `--help` | pass |
| 内置 `node-pty` / ConPTY | pass |
| PTY 子进程退出码 | 0 |
| 原生标记 | `PTY_OK` |

构建脚本会删除 Windows x64 运行不需要的其他架构 prebuild、PDB 调试符号和
`node-pty` 构建源文件。运行所需的 Windows x64 `.node`、DLL、辅助 EXE、JavaScript
和许可证保留，并在裁剪后执行真实 PTY 自检。

本地生成的 EXE 只是验证产物，不上传到 GitHub Release。公开资产必须由
`.github/workflows/launcher.yml` 构建并附 SHA-256。

## 方案比较

| 方案 | 优点 | 当前阻塞 | 决策 |
|---|---|---|---|
| Node SEA | 只携带一个 Node 运行时，可嵌入 assets | `node-pty` 还会使用原生文件、worker 和子 Node 进程，需要额外启动语义适配 | 暂缓 |
| Bun `--compile` | 官方支持单文件与嵌入 N-API addon | 会把已验证的 Node 运行时替换成 Bun，B 层尚无 S1–S3 与长测证据 | 暂缓 |
| .NET Native AOT 引导器 + Node payload | 保留现有 Node 行为，原生依赖可正常加载，菜单可双击打开 | 首次运行需要释放缓存；产物未签名 | **采用** |
| 完整 GUI 重写 | 可以提供按钮、文件选择器和进度条 | 重复补丁逻辑，扩大高风险写入代码和维护面 | 后续独立评估 |

Node SEA 允许把静态资源嵌入单文件，但注入脚本的 `require()` 默认只能加载内置模块；
原生 addon 仍需要写到临时文件后加载。参考
[Node.js SEA 文档](https://nodejs.org/download/release/latest-v22.x/docs/api/single-executable-applications.html)。

Bun 的编译器可以生成独立 EXE，也声明支持嵌入 `.node` addon；这只证明能打包，
不证明 Claude Code PTY 的 Node 行为完全兼容。参考
[Bun executable 文档](https://bun.sh/docs/bundler/executables)。

.NET Native AOT 生成不要求目标机器安装 .NET 的平台原生程序，适合作为只负责校验、
释放和启动的最小引导层。参考
[Microsoft Native AOT 文档](https://learn.microsoft.com/dotnet/core/deploying/native-aot/)。

## 双击体验

无参数启动时显示中文菜单：

1. Desktop 中英对照或纯中文安装；
2. Claude Code A 层中英对照或纯中文安装；
3. Desktop / Claude Code 状态；
4. Desktop / Claude Code 还原；
5. 实验性 CLI B 层入口。

B 层继续要求用户提供明确的 `claude.exe` 路径，不自动猜测或改写已安装程序。带参数
运行时，EXE 仍可作为自动化 CLI 使用：

```powershell
claude-zh-windows-x64.exe status desktop
claude-zh-windows-x64.exe install desktop --mode=bilingual
claude-zh-windows-x64.exe restore desktop
```

## 安全与发布边界

- EXE 不包含 Claude、ASAR、解包上游内容或用户配置；
- 运行时不下载依赖、不检查更新、不收集遥测；
- 缓存路径不请求管理员权限，不写入 WindowsApps；
- ZIP 路径经过越界检查，清单记录所有文件的长度和 SHA-256；
- 缓存中缺失、多出或被修改任何文件都会触发重新释放；
- Node 官方分发许可证和 npm 依赖许可证随 payload 保留；
- Release 只能使用 GitHub Actions 产物，并同时发布 `SHA256SUMS.windows`。

当前原型未做 Authenticode 代码签名。直接公开为稳定版会遇到 Windows SmartScreen
信誉提示；正式发布前需要明确选择“先发布带 SHA-256 的未签名候选版”或“取得代码
签名证书后再标记稳定”。
