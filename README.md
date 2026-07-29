# claude-zh-bilingual

让 Claude 说中文，但留住英文。

| 其他汉化包 | claude-zh-bilingual |
|---|---|
| 按 Shift+Tab 切换模式 | 按 Shift+Tab 切换模式 |
| 压缩上下文 | 压缩上下文 (compact) |
| 权限被拒绝 | 权限被拒绝 (Permission denied) |

**看得懂中文，还能拿英文原文去查官方文档和搜报错。**

Claude Code / Claude Desktop 中文化 · 中英术语对照模式 · Claude 汉化 zh-CN localization with bilingual terminology

> W1–2 地基已完成，尚未发布可安装版本。

## 项目定位

本项目不是简单的全局字符串替换。核心资产是：

- 可跨版本继承的翻译语料
- 关键技术词的中英术语对照表
- 经过验证的 SAFE 风险白名单
- 提取、分类、校验和冒烟测试流水线

只有明确标记为 `SAFE` 的界面展示文案才允许翻译。tool description、system prompt、代码匹配字符串以及无法确认用途的内容均保持英文。

## 规划接口

以下命令属于规划接口，当前阶段尚不可用：

```bash
npx claude-zh install desktop
npx claude-zh install code --mode=bilingual
npx claude-zh restore code
npx claude-zh status
```

## 当前路线

- Claude Code：官方扩展点作为地基，PTY 拦截继续验证，二进制 patch 仅作为后期高风险增强。
- Claude Desktop：语言 JSON、asar 壳层与 Web chunks 的混合策略；非 MSIX 安装优先。
- 新版本：提取字符串后按规范化 hash 继承既有语料，新增项默认进入 UNKNOWN 待审队列。

M1 实测数据见 [`report/M1-勘测报告.md`](report/M1-勘测报告.md)。

## 开发验证

需要 Python 3.11+ 与 Node.js 22+。依赖只安装到项目环境，不需要全局安装 Claude 或修改本机 Claude：

```bash
python -m pip install .
npm ci --ignore-scripts
python -m unittest discover -s tests -v
python schema/validate.py corpus
```

## 安全边界

- 不修改鉴权、登录、凭证、计费、用量、限额或代理配置。
- 补丁脚本除下载官方原始包外不发起网络请求。
- 不收集遥测或用户数据。
- 修改用户文件前必须备份，失败时自动还原。
- 仓库不分发 Claude 原程序、二进制、asar 或打好补丁的成品。

本项目是非官方项目，与 Anthropic 无关。Claude 是 Anthropic, PBC 的商标。

## License

- 代码：MIT，见 [`LICENSE`](LICENSE)
- `corpus/` 翻译语料：CC0-1.0，见 [`corpus/LICENSE`](corpus/LICENSE)
