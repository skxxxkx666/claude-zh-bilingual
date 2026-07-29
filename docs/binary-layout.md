# Claude Code 2.1.220 原生二进制布局

## 适用范围

本记录只适用于 Windows x64 `@anthropic-ai/claude-code-win32-x64@2.1.220`：

- 文件大小：265,720,480 字节；
- SHA-256：`AF5BF1F1B2AADFFC768ECCD787084C6FDF9BA81624CBE96C1C6D9AC1A1550231`；
- 格式：PE32+，原始 Authenticode 状态为 `Valid`；
- 所有实验均修改 `samples/` 下的隔离副本，没有修改本机安装。

任何版本或平台变化都必须重新执行本文件的最小实验，不能沿用偏移。

## PE section

二进制共有 12 个 section。与 CLI JavaScript snapshot 相关的是：

| section | 文件偏移 | 原始大小 | 属性 |
|---|---:|---:|---|
| `.bun` | 83,666,432 | 182,043,648 | initialized data、read-only、non-executable |

已知 UI 文案都落在 `.bun`，不在可执行 `.text` section。裸字符串扫描仍会命中
标识符、长文本子串和其他非 UI 内容，因此 `.bun` 只能作为第一层过滤，不能直接
授予 `SAFE`。

## Bun 字符串记录

经过验证的独立字符串记录布局为：

```text
offset - 8  uint32 little-endian  tag = 9
offset - 4  uint32 little-endian  UTF-8 byte length
offset      byte[length]          string bytes
```

大小写精确搜索 `Thinking` 得到 241 个字节子串，但只有 3 个同时满足：

- 位于 `.bun`；
- 前置 tag 为 9；
- 前置长度为 8；
- 记录内容与 `Thinking` 完全相等。

有效记录偏移为：

```text
142165816
225290600
225299128
```

M1 报告中的 76 次“完全匹配”使用了 `casefold()`，其中包含小写 `thinking`。
原生 patcher 必须使用大小写敏感匹配，并验证完整记录头。

## C1 最小实验

对 3 个有效 `Thinking` 记录应用三种隔离修改：

| 实验 | 内容 | 长度字段 | 文件大小 | S1 | S2 | S3 |
|---|---|---:|---:|---|---|---|
| 等字节 | `Thinking` → `Thnkng!!` | 8 | 不变 | pass | pass | pass |
| NUL 填充 | `Thinking` → `Think\0\0\0` | 5 | 不变 | pass | pass | pass |
| 空格填充 | `Thinking` → `Think   ` | 8 | 不变 | pass | pass | pass |

S2 输出 `2`，S3 输出 `claude-zh`。原始 `2.1.220` 副本也运行了同一组对照测试。
三个补丁副本均能启动、对话和调用 Read 工具。

NUL 方案同步修改长度字段，剩余分配空间补 `\x00`；运行时只读取新长度。空格方案
保持原长度，可能在界面留下尾随空格。因此后续中文承载实验使用 NUL 方案，空格只
保留为兼容性探针。

### 运行时 surface 反证

仅通过 S1–S3 不能证明修改过的记录就是界面实际使用的记录。后续补了两组可视验证：

1. 把 3 个合法 `Thinking` 记录改为 `Thnkng!!`，并通过临时
   `spinnerVerbs` 设置强制界面显示 `Thinking`。界面仍显示 `Thinking…`，说明
   这 3 个记录不是该 spinner 的渲染源，不能据此把 `cli.ast.literal` 提升为
   `SAFE`。
2. 把 `Output the version number` 的已审阅帮助记录改为较短 ASCII
   `SHOW VERSION NUMBER`。`claude --help` 随即显示新文本，退出码为 0，证明
   surface mapper 找到的帮助记录确实参与运行时渲染。

第二组实验把“可修改的记录”和“真实 UI surface”连了起来，但还不能证明该记录类型
可以承载中文。

### 中文编码失败

在隔离副本上把 5 个已审阅的 `cli.help` 记录替换为符合 `byte_budget` 的中文，并
按 UTF-8 字节数更新长度字段。S1–S3 仍然通过，文件大小不变，但帮助页显示乱码。
例如：

```text
期望：输出版本号
实际：è¾åºçæ¬å·
```

这正是把 `输出版本号` 的 UTF-8 字节逐字节解释为 Latin-1 后再输出 UTF-8 的结果。
因此 `tag = 9` 的记录虽然以字节长度为前缀，却具有单字节字符串语义，不能直接存放
中文 UTF-8。ASCII 成功不代表中文可用。

测试后已通过备份还原原始副本，并确认：

- SHA-256 恢复为
  `AF5BF1F1B2AADFFC768ECCD787084C6FDF9BA81624CBE96C1C6D9AC1A1550231`；
- Authenticode 恢复为 `Valid`；
- 文件大小仍为 265,720,480 字节。

## 签名影响

任意字节修改都会使 Authenticode 从 `Valid` 变为 `HashMismatch`。Windows 11
本次仍允许隔离副本执行，但这不等于所有安全策略和杀毒软件都会接受。

因此：

- 仓库和 release 永不分发修改后的 Claude 二进制；
- patcher 只能在用户本地明确执行；
- 安装前必须显示原始签名、版本和 SHA-256；
- 必须在应用目录之外备份原文件；
- 失败立即还原并验证原始 SHA-256；
- 企业策略拒绝签名失效二进制时，C 层标记为不支持，A 层继续可用；
- 不引导用户关闭 Smart App Control、Defender 或其他系统安全功能。

## C 路线结论

`2.1.220` 的 `.bun` `tag = 9` 记录可以安全执行 ASCII 等长或缩短替换，但不能
正确承载中文。CLI 中文 C 层据此判定为**不可交付**，不实现批量 patcher，也不把
试验条目标成 `verified_at`。W9–10 按预定决策树转入 B 路线；无法证明 surface 的
字符串继续保持 `UNKNOWN`。
