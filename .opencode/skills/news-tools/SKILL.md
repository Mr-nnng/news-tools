---
name: news-tools
description: 使用 src/news_tools 下的工具获取新闻信息并导出 HTML 报告。当用户需要获取 GitHub 开源趋势、华尔街见闻实时快讯、新闻联播文字版内容，或将 HTML 报告导出为图片时使用此 skill。
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
├── xwlb-{date}/                         # 新闻联播（同层级结构）
│
└── template/
    └── github-trending.html              # GitHub 周报模板（600×800 卡片）
```

**⚠️ 路径约定：所有输出必须写在 `report/` 下按日期命名的子目录中，禁止平铺到 `report/` 根目录。**

---

## GitHub Trending 趋势（四步工作流）

```mermaid
flowchart LR
    A[trending.py<br/>Step 1: 数据获取] -->|raw JSON| B[AI Agent (你)<br/>Step 2: 内容增强]
    B -->|enriched JSON| C[build_report.py<br/>Step 3: HTML 渲染]
    C -->|report.html| D[screenshot.py<br/>Step 4: 截图导出]
```

### Step 1：获取原始数据

```bash
python -m news_tools.trending weekly --proxy http://127.0.0.1:7890 -o report/github-trending-weekly-{date}/data/trending-weekly.json
```

| 参数 | 说明 |
|------|------|
| `daily` / `weekly` | 趋势周期 |
| `-o FILE` | JSON 保存路径 |
| `--proxy URL` | 代理地址 |
| `-l LANG` | 按语言过滤 |
| `--compact` | 仅输出 repos 数组 |
| `--no-readme` | 不抓取 README |
| `--readme-max-length N` | README 截断长度 |

### Step 2：Agent 内容增强（由调用 skill 的 AI 完成）

**你**必须读取 raw JSON，对**每个仓库**利用 `description` + `readme` 生成中文内容。

**工作流程：**
1. 读取 raw JSON
2. 对每个仓库生成：
   - `zh_desc`：精炼 2 句话中文简介，60-90字最佳
   - `features`：固定 3 条特点，每条15-25字
   - `audience`：推荐受众，至少3条
3. 生成全局 `cover_summary`
4. 写为 **enriched JSON**

**⚠️ 原则（踩坑总结）：**

| 原则 | 说明 |
|------|------|
| **必须保留的原始字段** | `author` / `name` / `stars_total` / `stars_today` / `forks` / `language` / `language_color` / `url` |
| **不可保留的原始字段** | `readme`（仅供分析用，最终数据中必须移除）、`description`、`built_by`、`author_avatar_url` |
| **`zh_desc`** | 精炼的 **2 句话**（100 字以内，50-90字最佳） |
| **`features`** | **固定 3 条**，每条 15-25 字 |
| **`audience`** | 中文推荐受众，用顿号分隔 3-5 种用户身份 |
| **`cover_summary`** | 格式："本周 GitHub Trending 收录 N 个热门仓库，涵盖 ... 等领域。" |
| **README 使用** | 必须读完 README 后再写 `zh_desc`，不可仅靠 `description` 字段 |

### Step 3：渲染 HTML

```bash
python -m news_tools.build_report report/github-trending-weekly-{date}/data/enriched-trending.json
```

### Step 4：截图导出

```bash
python -m news_tools.screenshot report/github-trending-weekly-{date}/report.html -s .page -o report/github-trending-weekly-{date}/images
```

---

## 2. 华尔街见闻 7x24 快讯

```bash
python -m news_tools.wallstreet --date 2026-05-29 --score 3 -o report/wallstreet-{date}/data/wallstreet.json
```

---

## 3. 新闻联播摘要

```bash
python -m news_tools.xwlb --date 2026-05-29 --markdown -o report/xwlb-{date}/xwlb.md
```

---

## 4. HTML 截图工具

```bash
python -m news_tools.screenshot report.html -s .page -o output/ --scale 3
```
