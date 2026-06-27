---
name: news-tools
description: >-
  使用 src/news_tools 下的工具获取新闻信息并导出 HTML 报告。
  触发时使用：
  (1) GitHub Trending 趋势榜单获取 (daily/weekly) — 原始 JSON
  (2) 华尔街见闻 7x24 快讯获取 (按日期/重要度)，
  (3) 新闻联播文字摘要获取 (按日期/Markdown 输出)，
  (4) HTML 报告渲染工具（从 enriched JSON 生成 HTML）
  (5) HTML 截图工具 (将周报/日报导出为高清 PNG)。
  当用户需要获取 GitHub 开源趋势、华尔街见闻实时快讯、新闻联播文字版内容，
  或将 HTML 报告导出为图片时使用此 skill。
---

# News Tools

本项目 [src/news_tools/](src/news_tools/) 提供多个工具，均支持 CLI 和 Python 模块两种调用方式。

所有工具需在项目根目录使用 `python -m` 运行。

### 目录结构

每个报告独占一个日期命名的目录，所有相关资源归入其下：

```
report/
├── github-trending-weekly-{date}/       # 按 项目-周期-日期 命名
│   ├── report.html                       # HTML 报告（固定命名）
│   ├── avatar/                           # 头像缓存（build_report.py 自动下载）
│   ├── data/
│   │   ├── trending-weekly.json          # 原始 JSON（trending.py 输出）
│   │   └── enriched-trending.json        # AI 增强 JSON（Agent 按原则生成）
│   └── images/                           # PNG 截图（screenshot.py 输出）
│
├── wallstreet-{date}/                   # 华尔街见闻（同层级结构）
│   ├── data/
│   │   └── wallstreet.json               # 原始 JSON
│   └── report.html                       # （未来）日报 HTML
│
├── xwlb-{date}/                         # 新闻联播（同层级结构）
│   ├── data/
│   │   └── xwlb.json                     # 原始 JSON
│   ├── xwlb.md                           # Markdown 输出
│   └── report.html                       # （未来）日报 HTML
│
└── template/
    ├── github-trending.html              # GitHub 周报模板（600×800 卡片）
    └── daily-news.html                   # 每日要闻模板（A4 一页纸，待建）
```

| 类型 | 默认路径 | 说明 |
|------|---------|------|
| HTML 报告 | `report/{项目}-{周期}/{date}/report.html` | 固定 `report.html` |
| 原始 JSON | `report/{项目}-{周期}/{date}/data/` | 各工具的原始输出 |
| enriched JSON | `report/github-trending-{周期}/{date}/data/enriched-*.json` | AI 增强后数据 |
| PNG 截图 | `report/{项目}-{周期}/{date}/images/` | screenshot.py 导出 |
| 头像缓存 | `report/{项目}-{周期}/{date}/avatar/` | build_report.py 自动下载 |
| 模板 | `report/template/` | 共享模板 |

**⚠️ 路径约定：所有输出必须写在 `report/` 下按日期命名的子目录中，禁止平铺到 `report/` 根目录。**

---

## GitHub Trending 趋势（四步工作流）

### 流程概览

```mermaid
flowchart LR
    A[trending.py<br/>Step 1: 数据获取] -->|raw JSON| B[AI Agent (你)<br/>Step 2: 内容增强]
    B -->|enriched JSON| C[build_report.py<br/>Step 3: HTML 渲染]
    C -->|report.html| D[screenshot.py<br/>Step 4: 截图导出]
```

| 步骤 | 工具 | 做什么 |
|------|------|--------|
| **Step 1** | `trending.py` | 抓取 GitHub Trending 原始数据 + README，输出 JSON |
| **Step 2** | **调用 skill 的 AI Agent（就是你）** | 读取 raw JSON，利用 README 为每个 repo 生成中文简介/特点/受众，写 enriched JSON |
| **Step 3** | `build_report.py` | 读取 enriched JSON，下载头像，填充模板 → report.html |
| **Step 4** | `screenshot.py` | 导出为高清 PNG |

### Step 1：获取原始数据

```bash
python -m news_tools.trending weekly --proxy http://127.0.0.1:7890 -o report/github-trending-weekly-{date}/data/trending-weekly.json
```

| 参数 | 说明 |
|------|------|
| `daily` / `weekly` | 趋势周期 |
| `-o FILE` | JSON 保存路径 |
| `--proxy URL` | 代理地址。如果系统环境变量 `HTTPS_PROXY` 已设置，可不传此参数 |
| `-l LANG` | 按语言过滤，如 `python`、`typescript` |
| `--compact` | 仅输出 repos 数组（不含顶层元信息） |
| `--no-readme` | 不抓取 README（默认抓取，**建议保留**，AI 需要 README 来生成中文内容） |
| `--readme-max-length N` | README 截断长度（0=不截断），超过 5000 字符时建议截断 |

**输出结构：**

```json
{
  "source": "github_trending",
  "period": "weekly",
  "total_count": 25,
  "repos": [
    {
      "author": "microsoft",
      "name": "markitdown",
      "url": "https://github.com/...",
      "description": "Python tool for converting files...",
      "language": "Python",
      "language_color": "#3572A5",
      "stars_total": 146432,
      "stars_today": 15015,
      "forks": 10024,
      "readme": "（完整 README 内容，AI 用完后丢弃）"
    }
  ]
}
```

### Step 2：Agent 内容增强（由调用 skill 的 AI 完成）

**你**作为 AI，必须读取 raw JSON，对**每个仓库**利用 `description` + `readme` 生成中文内容。

**工作流程：**
1. 读取 raw JSON（含每个 repo 的 description 和 readme）
2. 对每个仓库，根据 description 和 README 内容生成：
   - `zh_desc`：精炼 2 句话中文简介，60-90字最佳
   - `features`：固定 3 条特点，每条15-25字最佳
   - `audience`：推荐受众，至少3条，4或5条最佳
3. 生成全局 `cover_summary`
4. 将结果写为 **enriched JSON**

**输出结构：**

```json
{
  "cover_summary": "本周 GitHub Trending 收录 20 个仓库，涵盖 AI Agent · 安全 · 前端设计 等领域。",
  "total_count": 20,
  "repos": [
    {
      "author": "microsoft",
      "name": "markitdown",
      "stars_total": 146432,
      "stars_today": 15015,
      "forks": 10026,
      "language": "Python",
      "language_color": "#3572A5",
      "url": "https://github.com/microsoft/markitdown",
      "zh_desc": "微软开源的轻量级文件转换工具……",
      "features": ["多格式文档转换", "保留结构为 Markdown", "轻量无依赖"],
      "audience": "数据科学家、LLM 应用开发者"
    }
  ]
}
```

**⚠️ 原则（踩坑总结）：**

| 原则 | 说明 |
|------|------|
| **必须保留的原始字段** | `author` / `name` / `stars_total` / `stars_today` / `forks` / `language` / `language_color` / `url` |
| **不可保留的原始字段** | `readme`（仅供 AI 分析用，最终数据中必须移除）、`description`（已用 `zh_desc` 替代）、`built_by`、`author_avatar_url`（后两项 `build_report.py` 不会读取） |
| **`zh_desc`** | 精炼的 **2 句话**（100 字以内，50-90字最佳）。第一句讲清楚项目是什么，第二句讲为什么重要/解决什么问题。避免啰嗦 |
| **`features`** | **固定 3 条**，超出会超出页面边界。每条 15-25 字，直接说明功能价值 |
| **`audience`** | 中文推荐受众，用顿号分隔 3-5 种用户身份 |
| **`cover_summary`** | 封面摘要，格式为"本周 GitHub Trending 收录 N 个热门仓库，涵盖 ... 等领域。…"。数字将自动被高亮蓝色，· 之间的领域将自动加粗 |
| **README 使用** | README 仅用于分析项目功能和定位。**必须读完 README 后再写 `zh_desc`，不可仅靠 `description` 字段** |

### Step 3：渲染 HTML

```bash
python -m news_tools.build_report report/github-trending-weekly-{date}/data/enriched-trending.json
```

自动完成：
- 读取 enriched JSON
- 下载所有作者头像到 `avatar/` 子目录
- 封面排名表：仅列前 10
- 详情页：全部仓库（每页 2 个），展示中文描述/特点/受众
- 封面摘要中数字自动 `<span class="hl">` 蓝色高亮，领域自动 `<strong>` 加粗
- 输出 `report.html`

常用参数：

| 参数 | 说明 |
|------|------|
| `enriched_json` | enriched JSON 路径（**必填**） |
| `-o / --output-dir` | 输出目录（默认与 JSON 同级的父目录） |
| `--avatar-dir` | 头像子目录名（默认 `avatar`） |
| `--template` | 自定义模板路径 |

> **注意**：头像下载默认不使用代理。如果在代理环境下工作且头像无法加载，可考虑为 `build_report.py` 增加 `--proxy` 支持（当前未实现）。

### Step 4：截图导出

```bash
# ✅ 推荐：逐页截图（每页独立 PNG）
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html -s .page -o report/github-trending-weekly-{date}/images

# 备选：整页长截图（某些场景需要）
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html --full-page -o report/github-trending-weekly-{date}/images/fullpage.png
```

- **逐页截图**（`-s .page`）是标准做法，匹配 HTML 中每张卡片的 `.page` 元素，输出 `page_01.png`、`page_02.png` …
- **整页截图**（`--full-page`）导出完整页面为一张长图，仅作为备选
- 截图前会等待 `networkidle` **并且** 等待所有 `<img>` 加载完成，确保头像渲染完毕
- 输出文件名格式：`{prefix}_01.png`、`{prefix}_02.png` …

---

## 2. 华尔街见闻 7x24 快讯

`src/news_tools/wallstreet.py` — 获取华尔街见闻 7x24 实时快讯，支持按日期和重要度筛选。

### CLI 用法

```bash
# 基本用法
python -m news_tools.wallstreet                                         # 今日快讯
python -m news_tools.wallstreet --date 2026-05-29                       # 指定日期
python -m news_tools.wallstreet --date 2026-05-29 --score 3             # 仅最重要新闻
python -m news_tools.wallstreet --date 2026-05-28 -o report/wallstreet-2026-05-28/data/wallstreet.json

# 调试辅助
python -m news_tools.wallstreet --verbose                               # 显示抓取进度
python -m news_tools.wallstreet --compact                               # 仅 items 数组
```

### 输出结构

JSON 顶层包含 `source`, `date`, `score`, `fetched_at`, `total_count`, `items[]`。
每条 item 包含 `id`, `display_time`, `content_text`, `title`, `score`, `type`, `uri`, `channels` 等字段。

`display_time` 为 Unix 时间戳（秒）：

```python
from datetime import datetime, timezone, timedelta
CST = timezone(timedelta(hours=8))
datetime.fromtimestamp(item.display_time, tz=CST).strftime("%H:%M")
```

### 输出目录约定

```
report/wallstreet-{date}/
└── data/
    └── wallstreet.json
```

将原始 JSON 写入 `report/wallstreet-{date}/data/wallstreet.json`。如需生成日报 HTML，沿用 `report/wallstreet-{date}/report.html` 的路径约定。

---

## 3. 新闻联播摘要

`src/news_tools/xwlb.py` — 从央视网获取每日《新闻联播》文字摘要。

### CLI 用法

```bash
# 基本用法
python -m news_tools.xwlb                                             # 今天（或昨天）新闻
python -m news_tools.xwlb --date 2026-05-29                           # 指定日期
python -m news_tools.xwlb --date 2026-05-29 -o report/xwlb-2026-05-29/data/xwlb.json

# Markdown 输出
python -m news_tools.xwlb --date 2026-05-29 --markdown -o report/xwlb-2026-05-29/xwlb.md
python -m news_tools.xwlb --date 2026-05-29 --md                       # 简写

# 紧凑模式
python -m news_tools.xwlb --compact                                   # 仅 items 数组
```

### 输出目录约定

```
report/xwlb-{date}/
├── data/
│   └── xwlb.json         # JSON 输出
└── xwlb.md               # Markdown 输出（--markdown 时）
```

---

## 4. HTML 截图工具

`src/news_tools/screenshot.py` — 使用 Playwright + Google Chrome 将 HTML 中匹配 CSS 选择器的元素逐一导出为高清 PNG。

### CLI 用法

```bash
# 逐页截图（推荐）
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html -s .page -o report/github-trending-weekly-{date}/images

# 整页截图
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html --full-page -o report/github-trending-weekly-{date}/images/fullpage.png

# 调整清晰度
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html -s .page -o output/ --scale 3
```

### 关键参数

| 参数 | 说明 |
|------|------|
| `-s, --selector` | CSS 选择器（默认 `.page`） |
| `-o, --output` | 输出目录（元素模式）或文件路径（整页模式） |
| `--full-page` | 整页截图模式 |
| `--scale` | 设备像素比（默认 3），值越大截图越清晰，文件大小也越大 |
| `--chrome` | 自定义 Chrome 路径，省略时自动探测 |

### 注意事项

- 截图前等待 `networkidle` + 所有 `<img>` 加载完成
- 输出文件名格式：`{prefix}_01.png`、`{prefix}_02.png` …（可配置 `--prefix`）

---

## 附录：踩坑记录 / 经验总结

以下是从实际使用中收集的注意事项，**每次使用前建议快速浏览**：

### enriched JSON 常见错误
1. ❌ **忘了删 `readme`** — raw JSON 中的 `readme` 字段**仅供 AI 分析用**，enriched JSON 中必须删除
2. ❌ **features 写了 5 条** — 页面只能容纳 3 条，超出的会被截断
3. ❌ **zh_desc 太长** — 超过 2 句话会超出卡片区域，必须精炼到 100 字以内
4. ❌ **漏掉原始字段** — `language_color` 和 `url` 容易被漏掉，但模板需要它们

### build_report.py 注意事项
- 头像下载不经过代理，如果在代理环境下遇到 GitHub 头像加载失败，需手动添加 `--proxy` 支持
- 封面摘要中的数字高亮和领域加粗由 `_highlight_summary()` 自动处理

### 截图注意事项
- **必须先渲染 HTML，再截图**
- 如果 Chrome 未安装在默认路径，需用 `--chrome` 指定路径
- 截图文件约 200KB-500KB/张（scale=3），批量导出注意磁盘空间

### 路径约定
- 所有输出必须位于 `report/` 下按日期命名的子目录
- **禁止**平铺在 `report/` 根目录（如 `report/wallstreet-2026-05-28.json`）
- 统一格式：`report/{项目}-{标识}/{date}/`

### 小红书/社交媒体发布内容审核避坑（2026-06 实战经验）

将技术周报/开源项目内容发布到小红书等平台时，以下 5 类风控机制最常触发限流或折叠，**发布前必须检查**：

#### 🚨 风险一：站外引流与外部链接（极高风险）
| 触发词 | 修改方案 |
|--------|----------|
| `https://github.com/...` 直链 | 正文中**彻底删除所有链接**；在图片中隐晦引导"GitHub 搜：项目名"；在评论区引导"需要链接扣'求分享'" |

#### 🚨 风险二：爬虫/泄露/破解类敏感词（高风险）
| 触发词 | 修改方案 |
|--------|----------|
| 爬虫、抓取数据、破解、泄露 | "爬虫" → **"网页自动化"** 或 **"RPA工具"**、**"数据采集测试"** |
| Leaks、泄露、逆向（AI 提示词相关） | "提示词泄露" → **"AI底层逻辑拆解"**、**"大模型系统指令研究"** |

#### 🚨 风险三：广告法绝对化用语（中高风险）
| 触发词 | 修改方案 |
|--------|----------|
| 最大、最快、第一、第一份 | "最大" → **"全球知名"**、"最快" → **"超快"**、"第一份工作" → **"成功入行"** / **"提升技术栈"** |

#### 🚨 风险四：教培卖课误判（中风险）
| 触发词 | 修改方案 |
|--------|----------|
| 免费课程、转行、包就业、就业率 | "免费课程" → **"免费自学"**、"转行开发者" → **"自学转行开发者"**、"就业" → **"技术提升入行"** |

#### ⚠️ 风险五：竞品拉踩（低风险）
| 触发词 | 修改方案 |
|--------|----------|
| "XX的替代品"、"XX免费替代" | → **"对标XX的开源方案"** 或 **"开源平替"** |

> **注意**：上述词库来自 2026-06 实战经验，平台审核规则持续变化。发布前建议再用当月的关键词做一次全文搜索（`grep` / `search_files`）确认无遗漏。
>
> 对应 HTML 文件修改步骤：`search_files` 查找所有风险词 → `apply_diff` 逐一替换 → `search_files` 复查。

### 虚拟环境
- 使用项目目录下的 `.venv` 虚拟环境
- 命令前缀：`.venv\Scripts\python -m news_tools.{module} ...`
