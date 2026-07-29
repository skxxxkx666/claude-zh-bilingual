# Claude Code B 层 PTY 输出桥

## 适用范围

当前实现只支持 Windows x64 Claude Code `2.1.220`。B 层不修改 Claude 二进制、
安装目录或用户配置，而是用 ConPTY 启动用户明确指定的程序，并在输出写回终端前做
保守替换。

```powershell
node .\bin\claude-zh.cjs run code --layer=b --binary=C:\path\to\claude.exe
```

`--` 后的参数不经解释，原样传给 Claude：

```powershell
node .\bin\claude-zh.cjs run code --layer=b --binary=C:\path\to\claude.exe -- --model=sonnet
```

## 数据流与安全边界

```text
键盘输入 ───────────────────────────────▶ Claude Code
                                            │
                                            │ PTY 输出
                                            ▼
终端 ◀── 等宽 SAFE 替换 ◀── chunk 缓冲 ◀── ANSI 流
```

- 输入只透传，不替换，不反馈到模型上下文；
- 输出中的 ANSI 控制序列、颜色、光标移动和清屏序列原样保留；
- 只读取 `corpus/cli/layer-b.json` 中 `SAFE` 且有 `target` 的 unit；
- 启动前用 `string-width` 再次计算 source 与 target 的终端宽度，不相等就拒绝运行；
- 流式缓冲能处理普通文本被拆在两个 PTY chunk 的情况；
- 不跨 ANSI 控制序列猜测匹配。真实页脚的 `manual mode on` 在单词之间插入光标移动
  序列，因此没有进入语料；
- 不发起额外网络请求，不记录会话原文，不收集遥测。

## B1 零替换透传

`mode=passthrough` 在真实 `2.1.220` 副本上完成：

- 欢迎页颜色和 Unicode 标志正常；
- `/help` 全屏对话框能打开、关闭并重绘；
- 键盘输入、Esc 和 `/exit` 正常；
- 终端 resize 事件会调用 ConPTY resize；
- Claude 退出后包装进程返回相同退出码。

Windows 上 `node-pty` 的 native worker 会在子进程退出后保留事件循环句柄，因此命令
入口在完成清理和输出 flush 后显式退出；库级 `runPtyBridge()` 仍返回正常 Promise，
便于测试和嵌入。

## B2 等宽替换

当前只放行一条真实界面文案：

| surface | source | target | source 宽度 | target 宽度 |
|---|---|---|---:|---:|
| `cli.pty.spinner` | `Thinking…` | `正在思考…` | 9 | 9 |

实测通过临时 `spinnerVerbs` 设置稳定触发原文，包装层显示 `正在思考…`，分隔线、输入
光标和页脚列位置未移动。随后通过 B 层执行规范中的 S1、S2、S3，三条均通过；该 unit
据此标记为 `verified_at = cli@2.1.220`。

这不是全局汉化。没有真实 surface 证据、宽度不等、文本被 ANSI 拆分或风险不是
`SAFE` 的条目全部保持英文。

## C 路线关系

C1 的 ASCII 原地修改和 S1–S3 虽然通过，但 `.bun` `tag = 9` 记录按单字节字符串
解释中文 UTF-8，帮助页会显示乱码。C 层已停止，原始副本的 SHA-256 与 Authenticode
均已还原。完整反证见 [binary-layout.md](binary-layout.md)。
