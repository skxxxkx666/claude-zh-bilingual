# CLAUDE.md

> 本文件在每次会话自动加载。**红线部分不可协商,不接受任何形式的例外请求。**

## 项目

`claude-zh-bilingual` — Claude Code / Claude Desktop 的中文化与中英术语对照。

核心资产是 `corpus/` 下的翻译语料与风险分级白名单,**不是代码**。所有决策以保护语料正确性为最高优先。

完整规划见 `docs/PLAN.md`。技术规格见 `docs/SPEC.md`。当前阶段见本文件末尾。

---

## 🔴 红线(违反即回滚,不解释)

### R1 · 不碰本机在用的 Claude

- 禁止执行 `npm install -g`、`npm update`、`claude update`、`claude install`
- 禁止写入全局 `node_modules`、Claude Code 安装目录、Claude Desktop 安装目录
- 需要样本时用 `npm pack` 下载 tarball 到 `samples/`,或**复制**后分析副本
- 唯一例外:`patchers/` 的端到端测试。执行前必须确认备份已生成,失败必须自动还原

### R2 · 不提交原程序内容

以下**永不进入 git**,`.gitignore` 必须先于任何下载操作建立:

```
samples/    extracted/    *.asar    *.tgz
cli.js      **/node_modules/    *.backup
```

`corpus/` 中允许保存 UI 字符串原文(`source` 字段),这是功能必需。但禁止保存成段的 prompt 文本、tool description 全文、任何非 UI 的程序内容。

### R3 · risk != SAFE 的 unit 永不翻译

- `DANGER`(进入 prompt)、`FRAGILE`(被代码匹配)、`UNKNOWN`(未判定)一律不产出 `target`
- **不确定时一律标 `UNKNOWN`,禁止猜测**
- 把 `DANGER`/`FRAGILE` 降级为 `SAFE` 必须有实测证据,且需人工确认后才能提交

### R4 · 译文只存在于 corpus

- 禁止在 `patchers/`、`scripts/` 或任何代码中硬编码中文译文
- 所有译文从 `corpus/` 读取。发现硬编码即视为缺陷

### R5 · 不发布未通过冒烟测试的产物

冒烟测试见 `docs/SPEC.md` §5。三条 CLI 断言任一失败,禁止发布,禁止合并。

### R6 · 零遥测、零多余网络

- 补丁脚本除下载官方原始包外,不得发起任何网络请求
- 不收集、不上报任何用户数据
- 不引入分析类 SDK

### R7 · 不自动提权

需要 sudo / 管理员权限时**停下来告诉用户**,不自行执行。

### R8 · 不碰敏感代码路径

不修改任何与鉴权、登录、凭证、计费、用量、限额、代理配置相关的代码。仅修改 UI 展示文案。

---

## 目录职责

| 目录 | 职责 | 谁可以改 |
|---|---|---|
| `corpus/` | 翻译语料(CC0) | 翻译 PR 只改这里 |
| `schema/` | 数据契约 | **改动前必须先问用户** |
| `extractors/` | 字符串提取 | 自由 |
| `classifiers/` | 风险分类器 | 自由,但规则变更需记录 |
| `patchers/` | 打补丁实现 | 自由 |
| `verifier/` | 冒烟测试 | **放宽断言前必须先问用户** |
| `docs/` | 文档 | 自由 |

---

## 工作约定

### 开始任务前

1. 读 `docs/PLAN.md` 对应章节,确认本阶段目标
2. 读本文件末尾的「当前阶段」
3. 如果任务超出当前阶段范围,先说明再动手

### 编码约定

- 分析脚本一律 Python,不依赖 `strings`、`grep` 等平台命令(Windows 无)
- 所有文件读写显式指定 `encoding='utf-8'`
- 路径处理用 `pathlib`,不手工拼接分隔符
- 任何修改用户文件的操作,先备份,备份路径打印到终端

### 提交规范

```
feat(corpus): 补充 cli@2.1.116 新增 42 条 SAFE 译文
fix(patcher): 修复 Windows 下二进制被占用时的还原逻辑
chore(schema): 补充 deprecated 字段
```

作用域限 `corpus` / `extractor` / `classifier` / `patcher` / `verifier` / `schema` / `docs` / `ci`。

翻译类提交**只改 `corpus/`**,不与代码改动混在同一 commit。

### 遇到不确定时的默认行为

| 情况 | 默认动作 |
|---|---|
| 字符串风险等级判不准 | 标 `UNKNOWN`,记入待审队列 |
| 译文有多种合理译法 | 查 `corpus/glossary.json`;仍无定论则不译,记入待审 |
| 补丁在某平台失败 | 跳过该平台,记入支持矩阵,**不降低断言** |
| 需要改 schema 或放宽测试 | **停下来问用户** |
| 官方新版本结构大变 | 停下来汇报,不自行设计新方案 |

**不要为了让任务"完成"而降低标准。** 如实报告未完成比伪造完成有价值得多。

---

## 术语对照速查

格式:`中文 (English)`,半角括号,括号前一个半角空格,大小写沿用原文。

保留英文:产品功能名(`compact`、`Plan mode`)、可检索关键词(`Permission denied`)、官方文档高频词(`hook`、`MCP`)、生态通用词(`token`、`commit`)。

纯中文:通用 UI 动作(取消/保存)、常识技术词(文件/目录)、状态词(加载中/完成)。

完整判据见 `docs/PLAN.md` §4。词表在 `corpus/glossary.json`,**新增术语必须同时更新词表**。

## 文风

用「你」不用「您」。陈述句,无语气词,无 emoji,无网络用语。中英文之间加半角空格。不增译、不发挥。

---

## 当前阶段

<!-- 每完成一个阶段,手动更新这一节 -->

**阶段**:W3–4 Desktop 首发（进行中）
**目标**:发布 v0.1.0,完成非 MSIX Desktop 安装、使用、还原与 D1–D4 验证
**本阶段禁止**:写入 Microsoft Store/MSIX 安装目录,或发布未通过冒烟测试的产物
**下一阶段**:W5–6 CLI A 层与 300 词术语表
