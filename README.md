# News Tools

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一站式新闻信息获取与报告生成工具集。支持 **GitHub Trending**、**华尔街见闻三栏目**（早餐 / 早间要闻汇总 / 美股盘前）、**新闻联播** 三个数据源，提供 SPA 静态站点一键部署能力。

> 🌐 在线站点：<https://news-tools.pages.dev> — GitHub Trending 中文周报（每周更新）+ 华尔街见闻要闻（每日三档）+ 新闻联播文字摘要（每日更新），SPA 单页应用，客户端动态渲染。

---

## 功能特性

- **GitHub Trending** — 获取每日/每周趋势仓库，支持语言过滤和代理
- **华尔街见闻三栏目** — 早餐（07:25）/ 早间要闻汇总（12:30）/ 美股盘前（21:30），每日聚合、按日期分组
- **时间窗抓取** — 每栏目独立小时间窗抓取（score=3 重要级），避免整日抓取被 API 风控
- **新闻联播** — 获取文字摘要，支持 JSON / Markdown 输出
- **周报加工** — LLM 增强生成中文描述、特点、受众标签
- **JSON 数据输出** — 所有数据以 JSON 格式组织到 `site/data/`，由 SPA 运行时渲染
- **SPA 静态站点** — `app.js` + `app.css` 实现客户端路由和数据驱动的动态页面
- **Cloudflare Pages 部署** — 零构建步骤，直接部署 `site/` 目录即可

---

## 目录结构

```
news/
├── src/news_tools/                # Python 主包
│   ├── trending.py                # GitHub Trending 获取
│   ├── wallstreet.py              # 华尔街见闻 7x24 快讯（时间窗抓取）
│   ├── wallstreet_sections.py     # 华尔街见闻三栏目聚合逻辑
│   ├── xwlb.py                    # 新闻联播摘要
│   ├── __init__.py
│   └── __main__.py
├── site/                          # 构建输出的静态站点（可直接部署到 CF Pages）
│   ├── index.html                 # SPA 入口页（\<div id="app"\> 由 app.js 接管）
│   ├── app.js                     # SPA 运行时：路由、数据加载、渲染
│   ├── app.css                    # 全局样式（响应式、明/暗主题）
│   ├── _redirects                 # Cloudflare Pages SPA fallback 规则
│   ├── assets/fonts/              # 自托管字体
│   └── data/                      # JSON 数据层
│       ├── index.json             # 聚合索引（三 Tab 列表 + 统计）
│       ├── github/                # GitHub 周报数据
│       │   └── YYYY-MM-DD.json
│       ├── wallstreet/            # 华尔街见闻每日聚合（三栏目）
│       │   └── YYYY-MM-DD.json
│       └── xwlb/                  # 新闻联播数据
│           └── YYYY-MM-DD.json
├── assets/
│   ├── fonts/                     # 网页字体（woff2）
│   └── templates/                 #（已清空，v1.0 遗留模板已移除）
├── scripts/
│   ├── build_site.py              # 构建部署目录：输出 JSON + SPA 静态资源
│   ├── daily_update.py            # GitHub Actions 每日更新入口（SPA 模式）
│   └── wallstreet_update.py       # 华尔街见闻三栏目更新入口
├── skills/news-tools/             # Agent 配置（报告生成工作流）
│   ├── SKILL.md
│   ├── agents/                    # 各平台 agent 配置
│   ├── references/                # 参考文档
│   └── scripts/
├── tests/                         # 单元测试
├── .opencode/                     # opencode 配置
├── .gitattributes
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
├── uv.lock
└── wrangler.toml                  # Cloudflare Pages 配置
```

---

## 安装

```bash
git clone https://github.com/Mr-nnng/news-tools.git
cd news-tools

# 使用 uv 安装依赖
uv sync

# 可编辑模式安装（推荐，启用 CLI 命令）
uv pip install -e .
```

### 依赖说明

| 包 | 用途 |
|-----|------|
| `requests>=2.31.0` | HTTP 请求 |
| `beautifulsoup4>=4.12.0` | HTML 解析 |
| `pydantic>=2.0.0` | 数据建模与 JSON 序列化 |

---

## 命令行使用

### GitHub Trending

```bash
# 每日趋势
python -m news_tools.trending
python -m news_tools.trending -l python          # 按语言过滤
python -m news_tools.trending -o daily.json      # 保存到文件

# 每周趋势
python -m news_tools.trending weekly
python -m news_tools.trending weekly -l javascript
```

### 华尔街见闻

```bash
python -m news_tools.wallstreet                    # 今日快讯
python -m news_tools.wallstreet --date 2026-05-29  # 指定日期
python -m news_tools.wallstreet --date 2026-05-28 -o news.json
python -m news_tools.wallstreet --compact          # 仅输出 items 数组
python -m news_tools.wallstreet -v                 # 显示进度

# 时间窗抓取（避免整日抓取被风控）
python -m news_tools.wallstreet --start 2026-05-29T00:00 --end 2026-05-29T08:00
```

**三栏目更新**（由外部网站通过 GitHub Actions `repository_dispatch` 触发）：

```bash
python scripts/wallstreet_update.py --section breakfast   # 华尔街见闻早餐 07:25
python scripts/wallstreet_update.py --section morning     # 早间要闻汇总 12:30
python scripts/wallstreet_update.py --section premarket   # 美股盘前 21:30
python scripts/wallstreet_update.py --section all         # 全量重建当日
```

三个栏目使用互补不重叠的小时间窗抓取（00:00~08:00 / 08:00~13:00 / 13:00~22:00），
每日聚合写入 `site/data/wallstreet/YYYY-MM-DD.json`，幂等可重复执行。

### 新闻联播

```bash
python -m news_tools.xwlb                          # 今天（或昨天）
python -m news_tools.xwlb --date 2026-05-29
python -m news_tools.xwlb --date 2026-05-29 -o xwlb.json
python -m news_tools.xwlb --compact                # 仅输出 items 数组
python -m news_tools.xwlb --markdown               # Markdown 格式输出
```

### CLI 命令（安装后可用）

```bash
news-trending
news-trending weekly -l python
news-wallstreet --date 2026-05-29
news-xwlb --date 2026-05-29
```

---

## 作为模块调用

```python
from news_tools.trending import fetch_trending
from news_tools.wallstreet import fetch_live_by_date, fetch_live_between
from news_tools.xwlb import get_xwlb
from datetime import datetime

# GitHub Trending
result = fetch_trending(since="daily")
print(result.model_dump_json(indent=2, ensure_ascii=False))

# 华尔街见闻（整日）
result = fetch_live_by_date(target_date=datetime(2026, 5, 29))

# 华尔街见闻（时间窗）
result = fetch_live_between(
    start_dt=datetime(2026, 5, 29, 0, 0),
    end_dt=datetime(2026, 5, 29, 8, 0),
)

# 新闻联播
result = get_xwlb(2026, 5, 29)
```

---

## 数据构建

### 构建全站（JSON + SPA 静态资源）

```bash
python scripts/build_site.py
```

此命令扫描 `site/data/github/*.json`、`site/data/xwlb/*.json`、`site/data/wallstreet/*.json` 下的现有数据，重建 `index.json` 聚合索引。不生成 HTML 页面 —— 所有页面由 SPA 运行时在客户端动态渲染。

幂等安全：重复运行不会破坏已有数据。

### 每日更新（新闻联播）

```bash
python scripts/daily_update.py
```

从央视网 API 获取当日新闻联播数据，直接写入 `site/data/xwlb/YYYY-MM-DD.json`，然后重建 `index.json`。

### 每日更新（华尔街见闻三栏目）

```bash
python scripts/wallstreet_update.py --section breakfast   # 07:25 早餐
python scripts/wallstreet_update.py --section morning     # 12:30 早间要闻汇总
python scripts/wallstreet_update.py --section premarket   # 21:30 美股盘前
```

每次只抓取对应小时间窗（score=3 重要级），merge 进 `site/data/wallstreet/YYYY-MM-DD.json`，
同一栏目重复更新覆盖不叠加，其他栏目不受影响。随后自动重建 `index.json`。

### 外部网站触发（GitHub Actions repository_dispatch）

三个华尔街见闻 workflow（`wallstreet-breakfast` / `wallstreet-morning` / `wallstreet-premarket`）
**不配置 schedule**（GitHub 调度有延迟），由你的外部网站通过 GitHub API 手动触发：

```bash
# 触发早餐更新（event_type 对应 workflow 的 repository_dispatch.types）
curl -X POST https://api.github.com/repos/Mr-nnng/news-tools/dispatches \
  -H "Authorization: Bearer $PAT" \
  -H "Accept: application/vnd.github+json" \
  -d '{"event_type":"wallstreet-breakfast","client_payload":{"date":"2026-08-05"}}'
```

- `$PAT` 为具有 `repo` 权限的 GitHub Personal Access Token
- `client_payload.date` 可省略，省略时默认更新今天（CST）
- 触发后 Actions 拉取最新代码、运行对应栏目更新脚本、自动提交并推送 `site/` 变更
- 三个 workflow 均保留了注释掉的 `schedule` cron，如需切换为自动可取消注释

### 数据目录结构

所有数据文件位于 `site/data/` 下，构建脚本自动从中读取：

```
site/data/
├── index.json              # ← 自动生成：聚合索引
├── github/                 # ← GitHub 周报 JSON
│   └── YYYY-MM-DD.json    #    含 summary, repos 等字段
├── wallstreet/             # ← 华尔街见闻每日聚合（三栏目）
│   └── YYYY-MM-DD.json    #    含 sections.{breakfast,morning,premarket}
└── xwlb/                   # ← 新闻联播 JSON
    └── YYYY-MM-DD.json    #    含 date, items 等字段
```

---

## 部署到 Cloudflare Pages

SPA 架构下，`site/` 目录即为可直接部署的静态站点。无需构建步骤。

### 方式一：Git 集成（推荐）

1. 在本地执行构建命令生成 JSON 数据：
   ```bash
   python scripts/build_site.py
   ```
2. 将代码（包含 `site/` 目录）推送到 GitHub
3. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/) → Workers & Pages
4. 点击 **Create application** → **Connect to Git** → 选择仓库
5. 配置：
   - **Build command**（构建命令）：留空
   - **Build output directory**（输出目录）：`site`
6. 点击 **Save and Deploy**

部署后，`site/_redirects` 文件确保所有前端路由（如 `/xwlb/2026-07-18`）回退到 `index.html`，由 SPA 处理。

### 方式二：Wrangler CLI

```bash
python scripts/build_site.py
npm install -g wrangler
wrangler login
wrangler pages deploy site/
```

### 方式三：手动上传

将 `site/` 文件夹拖拽到 Cloudflare Pages 上传页面即可。

### 自定义域名

在 Cloudflare Pages 项目设置中 → **Custom domains** → **Set up a custom domain**，可以使用 Cloudflare 管理的任意域名。

---

## 运行测试

```bash
uv pip install -e .
uv run pytest tests/ -v
```

---

## 许可证

[MIT](LICENSE)

---

## 项目状态

每周自动生成 GitHub Trending 中文周报并部署上线，每日自动生成新闻联播文字摘要。查看在线站点 [news-tools.pages.dev](https://news-tools.pages.dev) 获取最新内容。

| Tab | 数据来源 | 更新频率 | 说明 |
|-----|----------|----------|------|
| **GitHub 周报** | GitHub Trending | 每周（周日） | LLM 增强中文描述、特点、受众标签 |
| **新闻联播** | 央视网 API | 每日 21:00 | 文字摘要 + 原始 JSON 数据归档 |

---

## GitHub Actions 自动化

### 每日新闻联播自动更新

[`.github/workflows/daily-xwlb.yml`](.github/workflows/daily-xwlb.yml) 工作流实现：

| 配置项 | 说明 |
|--------|------|
| **触发时间** | 每晚 21:00（北京时间 `UTC 13:00`） |
| **手动触发** | 支持 `workflow_dispatch` 在 GitHub 页面手动运行 |
| **流程** | 获取数据 → 写入 JSON → 重建 index.json → 自动提交 |
| **部署** | 提交后自动触发 Cloudflare Pages 重新部署 |

工作流执行步骤：
1. 检出代码 → 安装 Python + uv 依赖
2. 运行 [`scripts/daily_update.py`](scripts/daily_update.py)：
   - 调用央视网 API 获取当日《新闻联播》文字数据
   - 以 JSON 格式写入 `site/data/xwlb/{date}.json`
   - 重建 `site/data/index.json` 聚合索引
3. 自动 `git commit + push`，触发 Cloudflare Pages 部署

> 💡 若当日新闻联播尚未发布（如遇周末或节假日），脚本跳过数据获取，仅重建索引，不产生空提交。
