# Claude Code 官方扩展点实测

> 实测环境：Windows 11、Claude Code `2.1.201`，2026-07-29。所有用户配置测试均在写入前备份，测试结束后恢复。

## 结论

| 扩展点 | 实测状态 | A 层采用方式 |
|---|---|---|
| statusline | 支持，已在真实 TUI 显示 | `settings.json` 的 `statusLine` 命令 |
| hooks | 支持，`SessionStart` 已在真实 TUI 显示 | 追加一个 `startup` 命令 hook |
| 自定义 slash command | ASCII 名称支持；中文名称在 `2.1.201` 未注册 | `/zh-compact`、`/zh-help`、`/zh-resume` |
| output style | 配置、选中状态已验证；模型响应受账号 403 阻塞 | `output-styles/claude-zh.md` |
| `CLAUDE.md` 注入 | 支持，但本阶段未采用 | 保持用户和项目 `CLAUDE.md` 不变 |
| 插件 | manifest 严格校验和临时加载均通过 | 生成可独立加载的 `claude-zh-layer-a` 插件 |

官方行为参考：[status line](https://code.claude.com/docs/en/statusline)、[hooks](https://code.claude.com/docs/en/hooks)、[skills / slash commands](https://code.claude.com/docs/en/slash-commands)、[output styles](https://code.claude.com/docs/en/output-styles)、[plugins](https://code.claude.com/docs/en/plugins) 和 [settings](https://code.claude.com/docs/en/settings)。

## 1. Statusline

A 层生成 `~/.claude/claude-zh/statusline.cjs`，从标准输入读取 Claude Code 提供的 JSON，并只向标准输出写一行状态。隔离配置中的确定性输入：

```text
{"model":{"display_name":"Fable 5"},"context_window":{"used_percentage":25},"cost":{"total_cost_usd":1.23},"workspace":{"current_dir":"F:/project"}}
```

实测输出：

```text
A 层已启用 | 模型: Fable 5 | 上下文: 25% | 费用: $1.23 | 目录: F:/project
```

在真实 Claude TUI 底部也显示：

```text
A 层已启用 | 模型: Fable 5 | 上下文: 0% | 费用: $0.00 | 目录: ...
```

如果用户已经有 `statusLine`，安装器记录为 `skippedSettings` 并保留原值，不覆盖。

## 2. Hooks

A 层只向现有 `hooks.SessionStart` 末尾追加一个 `matcher: "startup"` 的命令 hook。隔离执行生成脚本的输出：

```json
{"systemMessage":"A 层已启用"}
```

真实 TUI 启动时显示：

```text
SessionStart:startup says: A 层已启用
```

已有 hook 保持原顺序和内容。还原时只移除与安装记录完全相同的新增项。

## 3. 自定义 Slash Command

用户级 skills 位于 `~/.claude/skills/`。最终安装内容：

```text
zh-compact
zh-help
zh-resume
```

在真实 TUI 输入 `/zh-` 后，三项均出现在自动补全中并标记为 `(user)`。它们是中文描述的语义工作流别名，其中 `/zh-compact` 请求压缩并保留决策、改动、测试结果和待办。

### 中文命令名限制

阶段目标示例是 `/压缩` → `/compact`。对 `2.1.201` 分别测试：

- `~/.claude/skills/压缩/SKILL.md`
- 兼容旧格式的 `~/.claude/commands/压缩.md`

两种形式输入 `/压` 时都没有自动补全，运行时未注册中文标识符。因此最终实现没有伪装成已经支持 `/压缩`，而是使用当前版本可注册的 `/zh-compact`。自定义 skill 也没有官方的“转发到内置 slash command”机制，所以这里是语义工作流，不声称等同于内部 `/compact` 实现。

## 4. Output Style 与 `CLAUDE.md`

生成文件 `~/.claude/output-styles/claude-zh.md` 的关键内容：

```yaml
---
name: 中文回复样式
description: 用中文回复，并保留可检索的英文术语。
keep-coding-instructions: true
---
```

真实 TUI 的 `/config` 显示：

```text
Output style    中文回复样式
```

这证明文件已被发现并选中。需要模型响应的最终行为测试被当前账号的服务端错误阻塞：

```text
Failed to authenticate. API Error: 403 Request not allowed
```

同一命令在完整还原 A 层后仍返回相同 403，因此不是本次配置注入造成。A 层不写 `CLAUDE.md`，避免把个人回复偏好混入项目指令。

## 5. 插件机制

安装器生成：

```text
~/.claude/claude-zh/plugin/.claude-plugin/plugin.json
~/.claude/claude-zh/plugin/skills/zh-help/SKILL.md
```

严格校验：

```text
Validating plugin manifest: .../plugin/.claude-plugin/plugin.json
√ Validation passed
```

使用 `claude --plugin-dir <plugin-path>` 启动真实 TUI 后，自动补全显示：

```text
/zh-help (claude-zh-layer-a) 显示中文 A 层帮助信息。
```

调用后被展开为命名空间命令 `/claude-zh-layer-a:zh-help`。默认安装仍使用用户级 skills；生成插件用于官方插件机制的验证和后续打包，不修改用户的插件市场配置。

## 配置合并与还原证据

- 安装前 `settings.json` SHA-256：`F15275BA84B30889C3EA8C12DF973C7B2503B8D5BA0FF26D58078E200211C9DC`
- 真实安装、TUI 验证、S1–S3 尝试后执行 `claude-zh restore code`
- 还原后 SHA-256：`F15275BA84B30889C3EA8C12DF973C7B2503B8D5BA0FF26D58078E200211C9DC`
- `claude-zh status code`：`not-installed`
- 原始备份仍保留在用户配置目录之外

自动测试还覆盖：已有自定义 statusline 不被覆盖、已有 hooks 保持、全新配置还原后不残留 `settings.json`、安装后用户新增修改被保留、安装过程中发生并发配置修改时中止且保留新字节、安装中途失败自动回滚。
