# SPEC · 技术规格

> 本文件定义所有**必须精确一致**的算法。任何实现偏差都会导致跨版本继承失效或语料损坏。
> 修改本文件中的算法等同于破坏性变更,必须同时升级 `corpus/` 的格式版本号。

---

## 1. 字符串规范化与 ID 计算

`id` 是跨版本继承的唯一依据。规范化必须**严格按以下顺序**执行,不得增删步骤。

### 1.1 规范化步骤

| 步 | 操作 | 理由 |
|---|---|---|
| 1 | 移除 ANSI 转义序列 `\x1b\[[0-9;]*[a-zA-Z]` | 同一文案在不同上下文着色不同 |
| 2 | Unicode NFC 归一 | 消除等价编码差异 |
| 3 | 占位符归一(见 1.2) | 占位符编号变动不应影响身份 |
| 4 | 首尾空白 strip | 布局调整常改动首尾空白 |
| 5 | **内部空白保持原样,不压缩** | 压缩会让不同 `byte_budget` 的字符串碰撞成同一 id |
| 6 | SHA-256,取 hexdigest 前 16 位 | |

**第 5 步是刻意的取舍**:不压缩会略微降低跨版本继承率,但保证 id 与 unit 严格一对一。宁可多审几条,不可让语料出现歧义。

### 1.2 占位符归一

按下表顺序依次替换为 `\x00PH\x00`(顺序不可调换,长模式必须先于短模式):

| 模式 | 正则 |
|---|---|
| `${...}` | `\$\{[^}]*\}` |
| `%1$s` 型 | `%\d+\$[sdifx]` |
| `{name}` / `{0}` | `\{[a-zA-Z0-9_]*\}` |
| `%s` `%d` 型 | `%[sdifx]` |

原始占位符文本按出现顺序存入 `placeholders` 字段。

### 1.3 参考实现

```python
import hashlib, re, unicodedata

_ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
_PH_PATTERN = re.compile(
    r'\$\{[^}]*\}'
    r'|%\d+\$[sdifx]'
    r'|\{[a-zA-Z0-9_]*\}'
    r'|%[sdifx]'
)
_PH_TOKEN = '\x00PH\x00'


def extract_placeholders(s: str) -> list[str]:
    """按出现顺序返回占位符原文,保留重复项。"""
    return [m.group() for m in _PH_PATTERN.finditer(s)]


def normalize(s: str) -> str:
    s = _ANSI.sub('', s)
    s = unicodedata.normalize('NFC', s)
    s = _PH_PATTERN.sub(_PH_TOKEN, s)
    return s.strip()


def unit_id(s: str) -> str:
    return hashlib.sha256(normalize(s).encode('utf-8')).hexdigest()[:16]
```

**测试向量**(实现必须复现,写入单元测试):

| 输入 | id |
|---|---|
| `Continue?` | `5c21be5ac90305e2` |
| `  Continue?  ` | `5c21be5ac90305e2` |
| `{0} files changed` | `91e30b891f6098b1` |
| `{count} files changed` | `91e30b891f6098b1` |
| `%s files changed` | `91e30b891f6098b1` |
| `\x1b[32mDone\x1b[0m` | `11a6767d5674c7e4` |
| `Done` | `11a6767d5674c7e4` |

**占位符测试向量**:`extract_placeholders("${name} {0} %1$s %s {0}")`
必须返回 `["${name}", "{0}", "%1$s", "%s", "{0}"]`。`${name}` 不得被
重复识别为 `{name}`,同一占位符重复出现时不得去重。

---

## 2. 显示宽度计算

终端宽度约束的依据。**不要用 `len()`**,CJK 字符占两列。

| 字符类别 | 宽度 |
|---|---|
| East Asian Width 为 `W` 或 `F` | 2 |
| Unicode 类别 `Mn`(非间距标记)、`Me`(封闭标记) | 0 |
| Unicode 类别 `Cc`(控制字符) | 0 |
| 其余 | 1 |

```python
import unicodedata

def display_width(s: str) -> int:
    w = 0
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ('Mn', 'Me', 'Cc'):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
    return w
```

**约束**:`display_width(target) <= display_width(source)`。超出时优先改译法,其次降级为不翻译。对照模式(`target_bilingual`)豁免此约束,因为它本就更长——但仅在 Desktop 与 A 层生效,B/C 层强制使用 `target`。

---

## 3. 字节预算与原地替换

仅用于 C 路线(二进制 / asar 原地 patch)。

### 3.1 规则

- `byte_budget = len(source.encode('utf-8'))`
- 候选译文必须满足 `len(target.encode('utf-8')) <= byte_budget`
- 不足部分的填充方式**取决于字符串在容器中的存储形式**,不可想当然

### 3.2 填充策略判定(C 路线第一步必须做的实验)

| 存储形式 | 判定方法 | 填充 |
|---|---|---|
| C 风格 null 结尾 | 字符串后紧跟 `\x00` | 补 `\x00` |
| 长度前缀 | 字符串前 2/4 字节等于其长度 | **必须同步改长度字段,否则崩溃** |
| 定长字段 | 前后被 `\x00` 或空格填充至固定边界 | 补空格 |

### 3.3 强制的最小改动验证

**在写任何批量 patcher 之前,必须先完成这一步:**

1. 选一条完全无关紧要的字符串(如某个 spinner 动词)
2. 用等字节数的 ASCII 替换(如 `Thinking` → `Thnkng!!`,严格 8 字节)
3. 运行三条冒烟测试

- 全部通过 → 继续验证「补 `\x00`」和「补空格」两种缩短方案
- 任一失败 → **C 路线不可行,立即停止,转 A + B**

跳过这一步直接批量改,失败时无法定位是哪条字符串导致的,会浪费数天。

---

## 4. 跨版本 diff 与继承

流水线的核心,决定人工审阅量。

```
输入:corpus(现有语料)、new_strings(新版本提取结果)、new_version

对 new_strings 中每条 s:
    i = unit_id(s)
    若 i 在 corpus:
        u = corpus[i]
        u.seen_in 追加 new_version(去重后升序)
        u.deprecated = False
        若 u.risk == SAFE 且 u.target 非空:
            u.verified_at = new_version      # 自动继承,零人工
        # byte_budget / display_width 按新版本 source 重算
    否则:
        新建 unit,risk = UNKNOWN,进入待审队列

对 corpus 中未出现在 new_strings 的 unit:
    u.deprecated = True                       # 保留不删,支撑旧版
```

**继承的前提是 `risk` 判定在版本间稳定。** 若某条 unit 的 `surface` 发生变化(例如原本在状态栏的文案挪进了 tool description),继承会把错误的 SAFE 带到新版本。因此:

> **surface 变化的 unit 必须重新走风险分类,不得直接继承。**

分类器每次运行时对所有 SAFE 的 unit 复检,发现 DANGER/FRAGILE 特征立即降级并告警。

---

## 5. 冒烟测试规格

### 5.1 CLI(三条,全部必过)

```bash
# S1 能启动
claude --version

# S2 能对话
claude -p "1+1"

# S3 工具链完好 ← 最关键
claude -p "read package.json, output the name field"
```

**S3 是核心断言**。它验证的不是"能不能跑",而是**有没有因为误翻 DANGER 类字符串导致 agent 能力退化**。判定标准:输出中包含 package.json 里真实的 name 值。

**禁止放宽这三条断言。** 需要修改时先问用户(CLAUDE.md R5)。

### 5.2 Desktop

| 断言 | 判定 |
|---|---|
| D1 启动 | 进程存活 > 10s,无崩溃弹窗 |
| D2 主界面渲染 | 关键元素可见 |
| D3 发送消息 | 能收到回复 |
| D4 视觉回归 | 与基线截图 diff,布局错位面积 < 5% |

### 5.3 失败处理

任一失败 → **立即自动还原备份** → 记录失败版本与条目 → 禁止发布。

---

## 6. 风险分类器规则表

按顺序匹配,**首次命中即判定**,规则编号写入 `risk_reason`。

| 序 | 编号 | 特征 | 判定 |
|---|---|---|---|
| 1 | `R-TOOLDESC` | 位于 tool schema / JSON schema 的 `description` 或 `parameters` 上下文内 | DANGER |
| 2 | `R-CODEMATCH` | 被 `.includes(` / `=== "` / `.startsWith(` / `.match(` / `switch` 引用 | FRAGILE |
| 3 | `R-LONGPROSE` | 长度 > 200 且含 ≥ 2 个句号且无 UI 特征 | DANGER |
| 4 | `R-SYSPROMPT` | 含 `You are` / `Your task` / `IMPORTANT:` / `<example>` 等 prompt 特征 | DANGER |
| 5 | `R-IDENTIFIER` | 全大写、snake_case、含 `/` 或 `::` 或 `.` 的标识符样式、URL、文件路径 | 不翻译(FRAGILE) |
| 6 | `R-UITEXT` | 长度 4–120,含空格,首字母大写或为常见 UI 词,不含上述特征 | **UNKNOWN**(候选 SAFE,待人工确认) |
| 7 | `R-DEFAULT` | 其余 | UNKNOWN |

### 关键设计

**规则 6 命中后是 `UNKNOWN` 而非 `SAFE`。** 分类器只负责**排除**危险项,不负责**授予** SAFE。SAFE 只能由人工确认或通过冒烟测试后授予。这是 fail-safe 的核心。

分类器输出三个队列:

- `excluded` — DANGER / FRAGILE,永不翻译
- `candidates` — 规则 6 命中,进入人工审阅(优先级最高)
- `unknown` — 规则 7,低优先级

### 复检机制

每次流水线运行时,对所有 `risk == SAFE` 的 unit 重跑规则 1–5。任一命中 → 立即降级为对应等级 + 清空 `target` + 告警。

---

## 7. 对照译文生成规则

`target_bilingual` 由 `target` 与 `glossary.json` 推导,但**存储为静态字段**,不在运行时计算(运行时计算会导致版本间行为漂移)。

### 生成算法

```
对 target 中出现的每个 glossary 术语 t(按 en 长度降序匹配,避免子串误伤):
    若 t.keep_en == True:
        将 target 中的 t.zh 替换为 f"{t.zh} ({t.en})"
    否则:
        不处理
每条 target 中同一术语只标注首次出现
```

### 硬规则

- 同一条译文中,**同一术语只标注一次**(首次出现)
- 单条 `target_bilingual` 中标注不超过 **2 个**术语,超过则只保留最重要的两个(按 glossary 中 `reason` 优先级:PRODUCT_NAME > SEARCHABILITY > DOC_FREQUENCY > ECOSYSTEM)
- 英文大小写严格沿用 `glossary.en`
- 格式:`中文 (English)`,半角括号,括号前一个半角空格

超过 2 个标注会让一行文案变得不可读,这条限制没有商量余地。

---

## 8. LLM 预翻译 Prompt(流水线用)

流水线中只对 `candidates` 队列调用,**永不对 DANGER / FRAGILE 调用**。

```
你是 claude-zh-bilingual 项目的翻译器。将给定的 Claude Code 界面英文文案翻译为简体中文。

严格遵守:
1. 用「你」不用「您」。陈述句,无语气词,无 emoji,无网络用语。
2. 中英文之间加半角空格。中文用全角标点,纯英文片段内用半角。
3. 不增译、不发挥、不加原文没有的解释。原文简洁则译文简洁。
4. 占位符必须原样保留,数量和写法完全一致:{0} %s ${name} 等。
5. 译文的终端显示宽度不得超过原文(中文字符按 2 列计算)。超出时改用更短的译法。
6. 严格遵循术语表。术语表中存在的词,必须使用表中给定的中文译法。

术语表(节选):
<glossary>
{{GLOSSARY_JSON}}
</glossary>

待翻译条目:
<items>
{{ITEMS_JSON}}
</items>

只输出 JSON 数组,不要 markdown 代码块,不要任何解释。格式:
[{"id": "...", "target": "...", "confidence": 0.0-1.0, "note": ""}]

confidence 低于 0.8 的条目,在 note 中说明原因。
如果某条你无法确定合适译法,将 target 设为 null 并说明。
```

**输出必须人工过一遍。** LLM 输出直接进入 PR 但不自动合并,`confidence < 0.8` 的条目在 PR 中高亮标出。

---

## 9. corpus 文件格式

```json
{
  "format_version": "1.0.0",
  "target": "cli",
  "version": "2.1.116",
  "generated_at": "2026-08-15T10:00:00Z",
  "units": [ /* Translation Unit 数组,按 id 字典序排列 */ ]
}
```

**units 必须按 id 字典序排列**,否则 diff 会产生大量噪音,导致 PR 无法审阅。写入前强制排序,由 CI 校验。
