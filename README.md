# News Tools

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一站式新闻信息获取与报告生成工具集。支持 **GitHub Trending**、**华尔街见闻 7x24 快讯**、**新闻联播** 三个数据源，并提供 HTML 周报生成与静态网站部署能力。

> 🌐 在线站点：自动生成并部署 GitHub Trending 中文周报（每周更新）。

---

## 功能特性

- **GitHub Trending** — 获取每日/每周趋势仓库，支持语言过滤和代理
- **华尔街见闻** — 按日期和重要度获取 7x24 快讯
- **新闻联播** — 获取文字摘要，支持 JSON / Markdown 输出
- **HTML 周报生成** — 从模板自动生成中文 GitHub Trending 周报（封面 + 排名表 + 详情页）
- **截图工具** — 基于 Playwright 的 HTML 元素截图，适用于报告封面/卡片导出
- **静态网站部署** — 一键构建可部署到 Cloudflare Pages 的静态站点

---

## 目录结构

```
news/
├── src/news_tools/            # Python 主包
│   ├── trending.py            # GitHub Trending 获取
│   ├── wallstreet.py          # 华尔街见闻 7x24 快讯
│   ├── xwlb.py                # 新闻联播摘要
│   ├── screenshot.py          # HTML 元素导出图片
│   ├── build_report.py        # HTML 周报生成
│   ├── __init__.py
│   └── __main__.py
├── site/                      # 构建输出的静态站点（可直接部署）
│   ├── index.html             # 项目主页，列出所有周报
│   ├── assets/fonts/          # 自托管字体
│   └── reports/               # 各期周报
├── assets/fonts/              # 网页字体（woff2）
├── scripts/
│   └── build_site.py          # 构建部署目录
├── skills/news-tools/         # Agent 配置（报告生成工作流）
├── tests/                     # 单元测试
├── .opencode/                 # opencode 配置
├── .gitattributes
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
├── uv.lock
└── wrangler.toml              # Cloudflare Pages 配置
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
| `playwright>=1.60.0` | 截图工具（可选） |

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
```

### 新闻联播

```bash
python -m news_tools.xwlb                          # 今天（或昨天）
python -m news_tools.xwlb --date 2026-05-29
python -m news_tools.xwlb --date 2026-05-29 -o xwlb.json
python -m news_tools.xwlb --compact                # 仅输出 items 数组
python -m news_tools.xwlb --markdown               # Markdown 格式输出
```

### 截图工具

```bash
# 按选择器批量导出为 PNG
python -m news_tools.screenshot report.html --selector .page -o screenshots/

# 整页截图
python -m news_tools.screenshot report.html --full-page -o page.png
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
from news_tools.wallstreet import fetch_live_by_date
from news_tools.xwlb import get_xwlb
from datetime import datetime

# GitHub Trending
result = fetch_trending(since="daily")
print(result.model_dump_json(indent=2, ensure_ascii=False))

# 华尔街见闻
result = fetch_live_by_date(target_date=datetime(2026, 5, 29))

# 新闻联播
result = get_xwlb(2026, 5, 29)
```

---

## 生成周报

从 enriched JSON 生成 HTML 周报：

```bash
python -m news_tools.build_report data/enriched-trending.json
```

生成流程：

1. `fetch_trending()` → 获取原始趋势数据
2. LLM 加工 → enriched JSON（中文描述、特点、受众）
3. `build_report()` → 填充模板 → `report.html` + 下载头像

---

## 部署到 Cloudflare Pages

构建静态站点：

```bash
python scripts/build_site.py
```

输出目录结构：

```
site/
├── index.html               ← 项目主页，列出所有周报
├── assets/fonts/            ← 自托管字体
└── reports/
    └── YYYY-MM-DD/report.html ← 各期周报
```

### 方式一：Git 集成（推荐）

1. 将代码推送到 GitHub
2. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/) → Build → Compute → Workers & Pages
3. 点击 **Create application** → **Connect to Git** → **Looking to deploy Pages? Get started**
4. 选择你的仓库
5. 配置：
   - **Build command**（构建命令）：`python scripts/build_site.py`
   - **Build output directory**（输出目录）：`site`
6. 点击 **Save and Deploy**

之后每次推送代码，Cloudflare Pages 会自动重新构建。

### 方式二：Wrangler CLI

```bash
npm install -g wrangler
wrangler login
python scripts/build_site.py
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

每周自动生成 GitHub Trending 中文周报并部署上线。查看 [`site/reports/`](site/reports/) 目录获取最新报告。
