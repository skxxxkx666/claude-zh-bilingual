# claude-zh-bilingual · 技术规划

**项目名**:`claude-zh-bilingual`
**中文名**:Claude 中英对照汉化
**CLI 命令**:`claude-zh`
**版本**:v1.1
**日期**:2026-07-28
**状态**:待 M1 勘测验证
**维护者**:朱瑞彬(个人开源项目,不纳入融境科技商业计划)

**一句话定位**:让 Claude 说中文,但留住英文。

---

## 0. 项目标识

| 项 | 值 |
|---|---|
| GitHub 仓库 | `claude-zh-bilingual` |
| npm 包 | `claude-zh-bilingual` |
| CLI bin | `claude-zh` |
| 代码授权 | MIT |
| **语料授权** | **CC0-1.0** |

**CLI 接口**:

```bash
npx claude-zh install desktop
npx claude-zh install code --mode=bilingual
npx claude-zh restore code
npx claude-zh status
```

**GitHub 元数据**(直接影响搜索命中,与仓库名同等重要):

```
Description
  Claude Code / Claude Desktop 中文化 · 中英术语对照模式 ·
  Claude 汉化 zh-CN localization with bilingual terminology

Topics
  claude-code, claude-desktop, claude, chinese, zh-cn,
  i18n, localization, bilingual, 汉化
```

### 0.1 授权策略说明

**代码 MIT,语料 CC0,两者分开授权。这是战略决策,不是法务形式。**

语料采用 CC0(放弃全部权利,进入公共领域)意味着竞品项目可以直接取用你的翻译。这看似吃亏,但:

- 语料要成为**上游标准**,前提是零使用门槛。附加任何条件(哪怕只是署名要求),下游宁可自己重做,你的上游定位当场失效
- 翻译数据本身的可版权性在多数法域存在争议,强行主张权利反而增加不确定性
- 你的真实护城河不是译文,而是**风险分级白名单 + 自动化流水线 + 跨版本 hash 继承**,这些在代码侧,受 MIT 保护

`corpus/` 目录下单独放置 `LICENSE`(CC0-1.0),根目录 `LICENSE` 为 MIT,README 明确说明分界。

---

## 1. 现状调研

### 1.1 竞品盘点

| 项目 | 目标 | 完成度 | 关键特征 |
|---|---|---|---|
| taekchef/claude-code-zh-cn | CLI | 高 | 四层机制(设置注入 + Hook + 插件 + CLI Patch),版本支持矩阵,自动降级 |
| KongBai1145/claude-code-zh-cn | CLI | 中高 | 1742 条 UI 翻译,187 个 spinner 动词,一键安装/卸载 |
| Jyy1529/claude-desktop_win-zh_cn | Desktop | 中高 | 12700+ keys,Windows 双安装路径检测,JS chunk 硬编码文案修补 |

**结论**:纯汉化赛道饱和。所有项目均为「纯中文替换」,**无人做中英对照**,亦无人提供可被复用的开放语料层。本项目选择描述性命名正面竞争,因此**第一屏的差异化呈现是生死线**(见 §2.2)。

### 1.2 决定性技术变化

Claude Code v2.1.113(2026-04-17)起,npm 包分发形态从 JavaScript 构建产物切换为**平台原生二进制**(Bun 编译),入口由 `cli.js` 改为平台原生可执行文件,运行时不再依赖 Node.js。

**影响**:

- 传统「解包 cli.js → 字符串替换 → 重打包」路线在 ≥2.1.113 上失效
- v2.1.112 成为最后一个可做 AST 分析的 JS 版本,应作为**语料库冷启动的金标准样本**
- 二进制原地替换受**字节长度约束**:UTF-8 下汉字 3 字节、英文字母 1 字节。`Continue`(8B)→`继续`(6B)可补空格;`No`(2B)→`否`(3B)**超长**

### 1.3 附加环境事实

- 存在两种安装路径:npm 全局安装 与 native installer,补丁工具必须同时探测
- Claude Desktop 为 Electron 应用,**已内置 i18n JSON 资源体系与 zh-CN 资源位**,汉化成本显著低于 CLI

---

## 2. 战略定位

三个定位并非互斥,而是**分层依赖**:

```
        patch 工具(执行层)
              ↑ 消费
        术语对照(渲染策略)
              ↑ 是 unit 的一个字段
        翻译语料库(数据层)  ← 唯一真实资产
```

### 2.1 中英对照的可行形态

**终端内全文对照不可行**:行宽爆炸、CJK 双宽字符、Ink 局部重绘错位。

**可行形态是术语对照** —— 界面中文化,关键专业术语保留英文原文。用户既能看懂界面,又能拿英文原文检索官方文档、Google 报错、提交 issue。纯汉化项目恰恰切断了这条路径。

### 2.2 README 第一屏规范(强制)

选择描述性命名意味着与三个同名项目并排展示,用户三秒内决定点击。README 顶部**必须**是对照效果的直观呈现,不是徽章墙、不是功能列表:

```
其他汉化包                   claude-zh-bilingual
─────────────────────       ─────────────────────
按 Shift+Tab 切换模式        按 Shift+Tab 切换模式
压缩上下文                   压缩上下文 (compact)
权限被拒绝                   权限被拒绝 (Permission denied)
```

配语:**「看得懂中文,还能拿英文原文去查官方文档和搜报错。」**

---

## 3. 技术架构

### 3.1 三条路线与选型

| 路线 | 说明 | 风险 | 覆盖率 | 选用 |
|---|---|---|---|---|
| **A. 官方扩展点** | statusline、hooks、中文 slash 别名、output style | 零 | 20–30% | ✅ 双端地基 |
| **B. PTY 输出拦截** | 伪终端拦截 stdout 做替换,不改原程序 | 低 | 40–60% | ⚠️ CLI 候选 |
| **C. 二进制 / asar patch** | 直接修改分发产物 | 高 | 80–95% | ✅ Desktop 主力 / CLI 备选 |

**决策**:Desktop → A + C;CLI → A + B,C 由 M1 勘测结论决定。

**B 路线硬伤**:Claude Code TUI 由 Ink 渲染,CJK 双宽字符导致替换后宽度不等即画面错位。缓解手段为**等显示宽度替换**,代价是限制译文自由度。

### 3.2 核心数据结构:Translation Unit

```json
{
  "id": "5c21be5ac90305e2",
  "source": "Continue?",
  "target": "继续?",
  "target_bilingual": "继续 (Continue)?",
  "risk": "SAFE",
  "surface": "cli.tui.prompt",
  "byte_budget": 9,
  "display_width": 9,
  "placeholders": [],
  "seen_in": ["cli@2.1.113", "cli@2.1.116"],
  "verified_at": "cli@2.1.116",
  "notes": ""
}
```

| 字段 | 设计意图 |
|---|---|
| `id` | 规范化原文的 hash,非原文本身。diff 友好,规避原文的结构化复制 |
| `risk` | **默认 `UNKNOWN`,仅显式提升至 `SAFE` 才会被应用。fail-safe 而非 fail-open** |
| `byte_budget` / `display_width` | patcher 据此判断能否原地替换,超限则跳过该条而非崩溃 |
| `target_bilingual` | 对照模式与纯中文模式共用同一条 unit,避免语料分叉 |
| `placeholders` | `{0}` `%s` `${...}` 必须原样保留,CI 强制校验 |
| `seen_in` / `verified_at` | 支撑跨版本 hash 继承,自动化流水线的基础 |

### 3.3 风险分级体系(项目最高优先级)

| 等级 | 定义 | 处理 |
|---|---|---|
| **SAFE** | 纯展示:菜单、状态、spinner、帮助文本、错误提示 | 可翻译 |
| **DANGER** | 会进入 prompt 的:tool description、system prompt 片段、参数说明 | **禁止翻译** |
| **FRAGILE** | 被代码自身 `includes()` / `===` / `.match()` / `switch` 引用 | **禁止翻译** |
| **UNKNOWN** | 未判定 | 默认值,不应用 |

**误判后果**:翻译 DANGER 类 → agent 能力静默退化、工具调用错乱,**难以归因,是最危险的失败模式**;翻译 FRAGILE 类 → 直接崩溃,至少是显性失败。

> **本项目的核心资产不是译文,而是这份经过验证的白名单。**

#### 自动分类启发式规则

| 特征 | 判定 |
|---|---|
| 出现在 tool schema / JSON schema `description` 上下文 | DANGER |
| 被 `.includes(` / `===` / `.match(` / `switch` 引用 | FRAGILE |
| 长度 > 200 且为完整段落 | DANGER |
| 全大写 / snake_case / 含 `/` 或 `.` 的标识符样式 | 不翻译 |
| 含 `{0}` `%s` `${` 占位符 | SAFE,占位符必须保留 |
| 其余 | UNKNOWN,人工判定 |

Desktop(asar 内 JS 明文)可做 AST 分析,准确率高;CLI native binary 仅能靠启发式。**因此 CLI 的 SAFE 白名单必须比 Desktop 保守得多。**

---

## 4. 术语对照词表规范 🆕

这是项目的核心差异化,必须有明确判据,不能凭感觉。

### 4.1 保留英文原文的判据

满足**任意一条**即保留英文:

| 判据 | 说明 | 示例 |
|---|---|---|
| **产品专有功能名** | 官方文档中作为功能名出现 | `compact`、`Plan mode`、`thinking`、`subagent` |
| **可检索性关键** | 用户大概率会拿它去搜索或提 issue | `Permission denied`、`rate limit`、`context window` |
| **官方文档高频词** | 中文译名会导致查文档时对不上 | `hook`、`slash command`、`MCP`、`skill` |
| **生态通用术语** | 已有约定俗成的英文用法 | `commit`、`diff`、`token`、`prompt` |

### 4.2 不保留英文的判据

满足**任意一条**即纯中文:

| 判据 | 示例 |
|---|---|
| 通用 UI 动作 | `Cancel` → 取消 / `Save` → 保存 / `Retry` → 重试 |
| 常识性技术词 | `file` → 文件 / `directory` → 目录 / `copy` → 复制 |
| 状态副词与连接词 | `Loading` → 加载中 / `Done` → 完成 |
| 保留后显著超宽 | 受 `display_width` 约束时优先纯中文 |

### 4.3 格式规范

```
标准形式    中文 (English)
半角括号,括号前一个半角空格,括号内不加空格

✅ 压缩上下文 (compact)
✅ 权限被拒绝 (Permission denied)
❌ 压缩上下文(compact)        全角括号
❌ 压缩上下文 ( compact )      括号内多余空格
❌ 压缩上下文(Compact)         大小写未沿用原文
```

**大小写必须沿用原文**。`compact` 是小写命令名就写小写,`Plan mode` 是官方写法就照抄。这直接决定用户复制去搜索时能不能命中。

### 4.4 词表维护

- 位置:`corpus/glossary.json`
- 规模目标:W5–6 交付 **300 词**
- 每条含:`en`、`zh`、`keep_en`(布尔)、`reason`(判据编号)、`source_ref`(官方文档链接,若有)
- **术语一致性由 CI 强制**:同一 `en` 在所有 translation unit 中的处理必须与 glossary 一致,不一致即 CI 失败

---

## 5. 翻译风格指南 🆕

接受社区贡献的前提。没有这一节,十个 PR 会产出十种风格。

### 5.1 语气与人称

- **用「你」,不用「您」**。开发者工具,平等语气
- **陈述句,不加语气词**。禁止「哦」「呢」「啦」「~」
- **不加原文没有的解释**。原文简洁就译得简洁,禁止增译
- 错误提示保持中性,不道歉、不安慰

### 5.2 排版

| 规则 | 示例 |
|---|---|
| 中英文之间加半角空格 | `按 Shift+Tab 切换` |
| 中文用全角标点 | `,。:;「」` |
| 纯英文/代码片段内用半角 | `Permission denied` |
| 数字与中文之间加空格 | `剩余 20% 上下文` |
| 不使用全角括号 | 见 §4.3 |

### 5.3 一致性硬规则

- **同一英文词全局译法唯一**。`Cancel` 全项目统一为「取消」,不允许某处「撤销」
- **同一操作的动词统一**。CI 会检测同 `en` 不同 `zh` 的情况并报错
- **译文显示宽度尽量 ≤ 原文**。超出时优先改译法而非放弃该条

### 5.4 禁止事项

- 意译、发挥、加入译者主观表达
- 使用网络流行语、梗、表情符号
- 翻译任何 `risk != SAFE` 的 unit
- 修改或省略占位符

---

## 6. 自动化流水线

手工跟进版本无法持续。杠杆点:**每个新版本 90%+ 的字符串未变更**。hash 继承正确时,单次人工只需 review 数十条增量。

```
定时器(每 6h)
  ↓ 检测新版本:npm registry API + Desktop 更新源
  ↓ 隔离沙箱下载 → 提取字符串 → 规范化 → hash
  ↓ 与 corpus diff:
      未变更 → 自动继承 verified 状态,零人工
      新增   → 标记 UNKNOWN,进入待审队列
      消失   → 标记 deprecated,保留不删(支撑旧版)
  ↓ 风险自动分类器
  ↓ LLM 预翻译(仅处理候选 SAFE,产出 target + target_bilingual)
  ↓ 自动开 PR,人工仅 review 增量
  ↓ 合并 → 构建 patch → 冒烟测试 → 发布 release
```

---

## 7. 质量保障

### 7.1 语料层 CI 校验 🆕

每个 PR 强制通过,任一失败阻断合并:

| 检查项 | 规则 |
|---|---|
| JSON Schema | 全部 unit 符合 `schema/unit.schema.json` |
| 占位符一致性 | `source` 与 `target`/`target_bilingual` 的占位符集合完全相同 |
| 宽度约束 | `display_width(target) ≤ display_width(source)`,C 路线额外校验 `byte_budget` |
| 术语一致性 | 同一 `en` 的译法在全库唯一,且与 `glossary.json` 一致 |
| 风险字段完整 | 不存在 `risk == UNKNOWN` 却被标记 `verified_at` 的 unit |
| 风险降级审计 | `DANGER`/`FRAGILE` → `SAFE` 的变更必须有两人 approve |
| 禁用词检测 | 表情符号、语气词、流行语黑名单 |
| 格式规范 | 对照格式符合 §4.3,中英混排空格符合 §5.2 |

### 7.2 冒烟测试(打补丁后自动执行,任一失败立即回滚)

**CLI**:

```bash
claude --version                                     # 能启动
claude -p "1+1"                                      # 能对话
claude -p "read package.json, output the name field" # 工具链完好 ← 最关键
```

第三条是核心断言:验证未误翻 DANGER 类导致 agent 能力退化。

**Desktop**:启动 → 关键页面截图 diff → 核心交互路径断言。

### 7.3 分层降级机制

**A 层永远生效;B/C 层失败时静默跳过,该部分保持英文。**

> **唯一红线:用户的 Claude Code / Desktop 绝不能因为本工具而无法使用。**
> 补丁、重打包、启动自检任一环节失败,必须自动恢复原文件。

### 7.4 已知平台差异

- **macOS 最麻烦**:修改二进制后签名失效,Gatekeeper 拦截。需 ad-hoc 重签 + 引导处理隔离属性。**预期 Windows 先行、macOS 滞后**
- **Windows**:不得热改运行中的可执行文件,需引导关闭进程后执行
- **自动更新会覆盖补丁**:需提供更新后自动重打机制或明确提示

---

## 8. 供应链安全 🆕

**用户在运行你的脚本修改本地已安装程序,这是极高信任操作。汉化补丁历来是恶意软件的经典载体,因此安全承诺必须显式、可验证。**

### 8.1 强制要求

| 项 | 要求 |
|---|---|
| 可复现构建 | 所有 release 由 GitHub Actions 构建,**禁止本地打包上传** |
| 完整性校验 | 每个 release asset 附 SHA256,workflow 日志公开可查 |
| 零网络请求 | 补丁脚本除下载官方原始包外,**不发起任何网络请求** |
| 零遥测 | 不收集任何用户数据、不上报安装事件、不含分析 SDK |
| 强制备份 | 打补丁前自动备份原文件,备份路径在终端明示 |
| 依赖最小化 | 直接依赖数量设上限,全部锁定版本,启用 Dependabot |
| 权限最小化 | 不请求提权;需要管理员权限时停下来提示用户,不自动 sudo |

### 8.2 明确声明(写入 README 与 SECURITY.md)

本工具**不会**修改任何与以下相关的代码:

- 鉴权、登录、凭证存储
- 计费、用量统计、限额
- 网络请求目标、代理配置
- 遥测与数据上报

仅修改用户界面展示文案。任何超出此范围的改动均视为严重缺陷。

### 8.3 安全响应

- 提供 `SECURITY.md` 与私密漏洞报告渠道
- 发现语料被投毒或 patcher 被篡改,立即撤回对应 release 并公告

---

## 9. 版本支持策略 🆕

| 项 | 策略 |
|---|---|
| 支持范围 | 最近 **3 个 minor 版本** + 最后一个 JS 版本(2.1.112) |
| 超出范围 | 标记 EOL,语料保留但不再验证,支持矩阵中显式标注 |
| 新版本响应 | 目标 6h 内自动开 PR,72h 内发布适配 release |
| 无法适配 | 支持矩阵标注「不支持」,不发布未经冒烟测试的 patch |
| 支持矩阵 | `docs/support-matrix.md`,由脚本自动生成,禁止手工维护 |

**不承诺全版本覆盖。** 明确的支持边界比虚假的全覆盖承诺更能建立信任。

---

## 10. 贡献流程 🆕

| 类型 | 要求 |
|---|---|
| 翻译 PR | **只允许修改 `corpus/`**,必须通过全部 CI 校验 |
| 风险降级 | `DANGER`/`FRAGILE` → `SAFE` 需两人 approve + 实测证据 |
| 硬编码翻译 | **不接受**在 patcher 内直接写死译文的 PR,一律要求走语料 |
| 新增术语 | 需同时更新 `glossary.json` 并注明判据编号 |
| 新平台支持 | 需附冒烟测试结果 |

首次贡献者引导:`good first issue` 标记 UNKNOWN 待审队列中的低风险条目。

---

## 11. 仓库结构

```
claude-zh-bilingual/
├─ corpus/                    # 翻译语料(核心资产,CC0)
│  ├─ LICENSE                 # CC0-1.0
│  ├─ glossary.json           # 术语对照词表
│  ├─ cli/
│  │  ├─ 2.1.112.json         # JS 金标准
│  │  └─ 2.1.x.json
│  └─ desktop/
│     └─ 1.x.json
├─ schema/                    # JSON Schema + 风险分级定义
├─ extractors/
│  ├─ js-ast/                 # AST 分析(Desktop / CLI 旧版)
│  └─ binary/                 # 二进制字符串提取
├─ classifiers/               # 风险自动分类器
├─ patchers/
│  ├─ cli-layer-a/            # 官方扩展点
│  ├─ cli-layer-b/            # PTY 拦截
│  ├─ cli-layer-c/            # 二进制 patch
│  └─ desktop-asar/
├─ verifier/                  # 冒烟测试
├─ scripts/                   # install / restore / status
├─ docs/
│  ├─ support-matrix.md       # 自动生成
│  ├─ style-guide.md          # §5 展开
│  └─ CONTRIBUTING.md
├─ SECURITY.md
├─ LICENSE                    # MIT(代码)
└─ .github/workflows/
```

---

## 12. 里程碑排期(12 周)

| 周 | 阶段 | 交付物 | 验收标准 |
|---|---|---|---|
| **M1** | 0(勘测) | 勘测报告、可行性判定 | 明确 CLI C 路线是否可行 |
| 1–2 | 地基 | schema 定稿、双端提取器、CI 骨架、**License 与 SECURITY.md** | 能从两端提取并 hash 全量字符串 |
| **3–4** | **Desktop 首发** | zh-CN 资源填充、install/restore、v0.1 release | Windows 端可用,一键还原可靠 |
| 5–6 | CLI A 层 | 官方扩展点全覆盖 + **300 词术语对照词表** | 零修改前提下可见中文化效果 |
| **7–8** | **自动化流水线** | 版本探测、hash 继承、自动 PR、冒烟测试 | 新版本 6h 内自动开 PR |
| 9–10 | CLI 深度 | PTY 拦截 或 二进制 patch(取 M1 可行者) | 冒烟测试全绿 |
| 11–12 | 稳定化 | 支持矩阵、贡献指南、社区流程 | 外部贡献者可独立提交翻译 PR |

**排期逻辑**:W3–4 先出 Desktop 是刻意安排,成功率最高,需要早期 release 验证需求真实存在。W7–8 流水线优先级高于 W9–10 的深度 patch —— 没有流水线,前期成果会在两个月内腐烂。

---

## 13. 成功指标与退出条件 🆕

### 13.1 六个月成功指标

| 指标 | 目标 |
|---|---|
| SAFE 类语料覆盖率 | ≥ 90% |
| 新版本自动 PR 响应 | < 6h |
| 外部贡献者 | ≥ 3 人 |
| 双端可用性 | Desktop + CLI 均有稳定 release |
| **严重事故** | **0 起「打补丁导致 Claude 不可用」的 issue** |
| 术语词表 | ≥ 300 词,CI 一致性 100% |

最后一项是硬指标。发生一起即视为质量体系失效,须暂停发布并复盘。

### 13.2 退出条件(满足任一即启动评估)

| 条件 | 处置 |
|---|---|
| Anthropic 官方发布中文界面 | **成功退出**。语料以 CC0 形式贡献上游,归档仓库 |
| 连续 2 个版本无法适配且无解决路径 | 降级为「仅支持已适配版本」,停止跟进新版 |
| 周投入持续 > 25 小时超过 1 个月 | 缩减范围:砍掉 CLI C 层,或暂停 Desktop |
| 收到官方法务通知 | **立即下架**,不抗辩 |
| 6 个月后外部贡献者 = 0 | 上游定位证伪,降级为个人自用工具 |

**明确写下退出条件的目的**:这是一个无终点的高投入项目,预设 kill criteria 是防止它拖成烂尾、而非主动收尾的唯一手段。

---

## 14. 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 误翻 DANGER 字符串致 agent 退化 | 中 | **极高** | 默认 UNKNOWN + 三级冒烟测试 + 保守白名单 |
| 二进制格式变更致 C 层失效 | 高 | 中 | 分层降级,A 层永远兜底 |
| macOS 签名 / Gatekeeper | 高 | 中 | Windows 先行,macOS 提供明确指引 |
| **维护强度不可持续** | **高** | 高 | 自动化流水线是唯一解;§13.2 退出条件兜底 |
| 被误认为恶意软件 | 中 | 高 | §8 供应链安全全部落实 |
| 语料被投毒 | 低 | 高 | 风险降级需两人 review + CI 强制校验 |
| 官方发出 DMCA | 低 | 高 | 严守补丁分发形态;不纳入商业计划 |
| 官方推出正式 i18n | 中 | 高 | 视为成功退出;CC0 语料可直接贡献上游 |

**资源现实**:双端并行 + 跟进每个版本 ≈ **每周 15–20 小时长期投入,无终点**。需与融境科技、智阅 AI、幼儿园官网项目做明确的优先级权衡。

---

## 15. 合规边界

**必须遵守**:

- 仓库内**只放翻译数据与打补丁脚本**,绝不上传 `cli.js`、`app.asar`、二进制或任何原程序代码
- 补丁在用户本地执行 —— 分发的是「改法」,不是「改好的成品」
- README 显著声明:非官方项目,与 Anthropic 无关;Claude 是 Anthropic, PBC 的商标
- 不涉及任何鉴权、计费、限额、网络代理相关代码(见 §8.2)
- 提供可靠的一键还原

**必须清醒认识**:

这是 IDEA 汉化包、游戏汉化补丁的通行做法,可显著降低风险,但**不能消除风险**。Anthropic 使用条款通常含禁止逆向工程条目,官方随时可能发出 DMCA。

> **不将本项目纳入融境科技的商业计划,以个人开源项目形态运作。**

---

## 16. 下一步

执行 M1 勘测(见《M1 勘测任务提示词》),**在勘测结论产出前不编写任何生产代码**。

**判定门槛**:

- 二进制 `strings` 可读 UI 英文句子占比高 → CLI C 路线可行
- 字符串被 bytecode 化或压缩 → 放弃 CLI C 层,资源全押 A + B
- Desktop i18n 结构清晰 → W3–4 首发计划成立

**M1 完成后立即冻结**:`schema/` 的 `$id`、包名、bin 名、License 文件,不再变更。
