#!/usr/bin/env python3
"""
daily_update.py — GitHub Actions 每日新闻联播自动更新入口

不依赖 report/ 目录，直接操作 site/：
1. 获取当日新闻联播数据
2. 生成 HTML 页面到 site/xwlb/{date}/
3. 重新生成 site/index.html（保留 GitHub 部分）
4. 更新所有 xwlb 详情页的侧边栏导航

用法:
    python scripts/daily_update.py
    python scripts/daily_update.py --date 2026-06-27   # 指定日期
"""

import json
import re
import shutil
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保 src/ 可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from news_tools.xwlb import get_xwlb
from news_tools.build_xwlb_html import build_xwlb_page

ASSETS_DIR = PROJECT_ROOT / "assets"
SITE_DIR = PROJECT_ROOT / "site"
REPORT_DIR = PROJECT_ROOT / "report"
XWLB_DIR = SITE_DIR / "xwlb"
XWLB_TEMPLATE = ASSETS_DIR / "templates" / "xwlb-page.html"
LANDING_TEMPLATE = ASSETS_DIR / "templates" / "landing-news-tools.html"
FONTS_SRC = ASSETS_DIR / "fonts"
FONTS_DST = SITE_DIR / "assets" / "fonts"


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════


def ensure_fonts() -> None:
    """复制字体到 site/assets/fonts/（如不存在）。"""
    if not FONTS_SRC.exists():
        return
    FONTS_DST.mkdir(parents=True, exist_ok=True)
    for f in FONTS_SRC.iterdir():
        if f.is_file():
            dst = FONTS_DST / f.name
            if not dst.exists():
                shutil.copy2(f, dst)


def get_month_key(date_str: str) -> str:
    """从日期字符串提取年月 key，如 '2026-06-07' → '2026年06月'。"""
    parts = date_str.split("-")
    if len(parts) >= 2 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1]):02d}月"
    return "未知"


def month_sort_key(mk: str) -> tuple[int, int]:
    """年月 key 排序函数。"""
    m = re.match(r"(\d{4})年(\d{2})月", mk)
    if m:
        return int(m.group(1)), int(m.group(2))
    return (0, 0)


def format_date(date_str: str) -> str:
    """'2026-06-07' → '2026年6月7日'。"""
    parts = date_str.split("-")
    if len(parts) == 3 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return date_str


def get_xwlb_dates() -> list[str]:
    """扫描 site/xwlb/ 获取所有已有日期目录。"""
    if not XWLB_DIR.exists():
        return []
    return sorted(
        d.name for d in XWLB_DIR.iterdir()
        if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)
    )


def load_xwlb_data(date_str: str) -> dict | None:
    """从 report/xwlb-{date_str}/data/xwlb.json 读取数据。"""
    path = REPORT_DIR / f"xwlb-{date_str}" / "data" / "xwlb.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
# 着陆页生成（仅 XWLB 部分）
# ═══════════════════════════════════════════════════════════════════


def build_xwlb_card_html(date_str: str, data: dict | None) -> str:
    """生成着陆页中的单张时间线卡片 HTML。"""
    item_count = "?"
    preview = ""
    if data:
        items = data.get("items", [])
        item_count = str(len(items)) if items else "0"
        titles = [x.get("title", "") for x in items[:3]]
        clean_titles = []
        for t in titles:
            first = t.splitlines()[0].strip() if t else ""
            first = re.sub(r"[（\(]\d+[）\)].*", "", first).strip()
            first = first.rstrip("：:;；，, ") or t[:40]
            if first:
                clean_titles.append(first)
        if clean_titles:
            preview = " · ".join(clean_titles)
            if len(preview) > 180:
                preview = preview[:180] + "…"

    display_date = format_date(date_str)
    return f"""    <a href="xwlb/{date_str}/index.html" class="report-card">
      <p class="card-date">{display_date}</p>
      <p class="card-meta">{item_count} 条新闻</p>
      <p class="card-desc">{preview}</p>
    </a>"""


def build_xwlb_landing_html(xwlb_dates: list[str]) -> tuple[str, int]:
    """生成着陆页 XWLB Tab 的完整 HTML。"""
    total_days = len(xwlb_dates)
    month_groups: dict[str, list[str]] = {}
    for rd in sorted(xwlb_dates, reverse=True):
        mk = get_month_key(rd)
        if mk not in month_groups:
            month_groups[mk] = []
        month_groups[mk].append(rd)

    sorted_months = sorted(month_groups.keys(), key=month_sort_key, reverse=True)
    months_html = ""
    for mk in sorted_months:
        rds = month_groups[mk]
        cards_html = ""
        for rd in rds:
            data = load_xwlb_data(rd)
            cards_html += build_xwlb_card_html(rd, data) + "\n"
        months_html += f"""  <div class="month-group">
    <div class="month-toggle" onclick="this.parentElement.classList.toggle('is-collapsed')">
      <span class="month-arrow">▾</span>
      <span class="month-label">{mk}</span>
    </div>
    <div class="report-grid">
{cards_html}    </div>
  </div>
"""
    return months_html, total_days


# ═══════════════════════════════════════════════════════════════════
# 侧边栏导航
# ═══════════════════════════════════════════════════════════════════


def build_xwlb_sidebar_html(xwlb_dates: list[str], current_date: str) -> str:
    """生成 xwlb 详情页侧边栏导航 HTML。"""
    month_groups: dict[str, list[str]] = {}
    for rd in sorted(xwlb_dates, reverse=True):
        mk = get_month_key(rd)
        if mk not in month_groups:
            month_groups[mk] = []
        month_groups[mk].append(rd)

    sorted_months = sorted(month_groups.keys(), key=month_sort_key, reverse=True)
    sections_html = ""
    for mk in sorted_months:
        rds = month_groups[mk]
        items_html = ""
        for rd in rds:
            display_date = format_date(rd)
            active = ' is-active' if rd == current_date else ""
            items_html += f"""
          <a href="../{rd}/index.html" class="sidebar-item{active}">{display_date}</a>"""
        sections_html += f"""
      <div class="sidebar-month-group">
        <div class="sidebar-month-toggle">
          <span class="arrow">▾</span>
          {mk}
        </div>
        <div class="sidebar-month-items">
          {items_html}
        </div>
      </div>"""

    return f"""<nav class="sidebar">
    <a class="sidebar-home" href="../../index.html"><span class="icon">🏠</span> 返回主页</a>
    <div class="sidebar-section">
      {sections_html}
    </div>
    <div class="sidebar-footer">
      <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener"><span class="icon">📂</span> GitHub</a>
    </div>
  </nav>"""


def rebuild_xwlb_sidebars(xwlb_dates: list[str]) -> None:
    """为所有 xwlb 详情页重新生成侧边栏导航。"""
    for rd in xwlb_dates:
        page_path = XWLB_DIR / rd / "index.html"
        if not page_path.exists():
            continue
        html = page_path.read_text(encoding="utf-8")
        sidebar_html = build_xwlb_sidebar_html(xwlb_dates, rd)

        if "{{SIDEBAR}}" in html:
            html = html.replace("{{SIDEBAR}}", sidebar_html)
        else:
            # 替换已有的侧边栏
            html = re.sub(
                r'<nav class="sidebar">.*?</nav>\s*',
                sidebar_html,
                html,
                flags=re.DOTALL,
            )

        page_path.write_text(html, encoding="utf-8")
        print(f"  🧩 sidebar → site/xwlb/{rd}/index.html")


# ═══════════════════════════════════════════════════════════════════
# 着陆页重建
# ═══════════════════════════════════════════════════════════════════


def _load_enriched_json(rd: str) -> dict | None:
    """从 report/github-trending-weekly-{rd}/data/enriched-trending.json 读取。"""
    path = REPORT_DIR / f"github-trending-weekly-{rd}" / "data" / "enriched-trending.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_gh_landing_cards(report_dirs: list[str]) -> tuple[str, int]:
    """生成 GitHub 周报着陆卡片 HTML（复制自 build_site.py）。"""
    total_projects = 0
    month_groups: dict[str, list[str]] = {}
    for rd in sorted(report_dirs, reverse=True):
        mk = get_month_key(rd)
        if mk not in month_groups:
            month_groups[mk] = []
        month_groups[mk].append(rd)

    sorted_months = sorted(month_groups.keys(), key=month_sort_key, reverse=True)

    months_html = ""
    for mk in sorted_months:
        rds = month_groups[mk]
        cards_html = ""
        for rd in rds:
            data = _load_enriched_json(rd)
            total = "?"
            summary = ""
            if data:
                count = data.get("total_count", 0)
                total = str(count) if count else "?"
                if isinstance(count, int):
                    total_projects += count
                summary = data.get("cover_summary", "")
                if len(summary) > 280:
                    summary = summary[:280] + "…"

            display_date = format_date(rd)
            cards_html += f"""    <a href="github_weekly/{rd}/report.html" class="report-card">
      <p class="card-date">{display_date}</p>
      <p class="card-meta">{total} 个项目</p>
      <p class="card-desc">{summary}</p>
    </a>
"""
        months_html += f"""  <div class="month-group">
    <div class="month-toggle" onclick="this.parentElement.classList.toggle('is-collapsed')">
      <span class="month-arrow">▾</span>
      <span class="month-label">{mk}</span>
    </div>
    <div class="report-grid">
{cards_html}    </div>
  </div>
"""
    return months_html, total_projects


def get_gh_dates() -> list[str]:
    """扫描 report/ 获取所有 GitHub 周报日期。"""
    if not REPORT_DIR.exists():
        return []
    return sorted(
        d.name.replace("github-trending-weekly-", "")
        for d in REPORT_DIR.iterdir()
        if d.name.startswith("github-trending-weekly-")
    )


def rebuild_landing_page() -> None:
    """重新生成 site/index.html，从 report/ 数据重建两个 Tab。"""
    index_path = SITE_DIR / "index.html"

    # —— GitHub 部分 ——
    gh_dates = get_gh_dates()
    gh_cards_html, total_projects = build_gh_landing_cards(gh_dates)

    # —— XWLB 部分 ——
    xwlb_dates = get_xwlb_dates()
    xwlb_cards_html, total_xwlb_days = build_xwlb_landing_html(xwlb_dates)

    # —— 从模板生成着陆页 ——
    template = LANDING_TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("{{GH_MONTH_GROUPS}}", gh_cards_html)
    html = template.replace("{{XWLB_MONTH_GROUPS}}", xwlb_cards_html)
    html = template.replace("{{REPORT_COUNT}}", str(len(gh_dates)))
    html = template.replace("{{XWLB_COUNT}}", str(total_xwlb_days))

    index_path.write_text(html, encoding="utf-8")
    print(f"  ✅ Landing page → site/index.html (GH: {len(gh_dates)}, XWLB: {total_xwlb_days})")


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="每日新闻联播自动更新脚本")
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天"
    )
    args = parser.parse_args()

    # —— 确定目标日期（北京时间） ——
    if args.date:
        dt = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        bj_tz = timezone(timedelta(hours=8))
        dt = datetime.now(bj_tz)

    date_str = dt.strftime("%Y-%m-%d")
    print(f"🔍 目标日期: {date_str}")
    print()

    # Step 1: 确保站点资源
    print("📁 确保站点资源...")
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_fonts()
    print("  ✅ 站点目录就绪")

    # Step 2: 获取新闻联播数据
    print(f"\n📡 获取 {date_str} 新闻联播数据...")
    result = get_xwlb(dt.year, dt.month, dt.day)

    if result is None:
        print(f"  ⚠️  {date_str} 暂无新闻联播数据（可能尚未发布）")
        # 即使没有新数据，也重新构建着陆页（用于补全已有历史页面）
        print("\n🏠 重新构建着陆页...")
        rebuild_landing_page()
        return

    # 保存数据到 site/xwlb/{date}/xwlb.json
    data_dir = XWLB_DIR / date_str
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "xwlb.json"
    data_path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✅ 数据保存 → site/xwlb/{date_str}/xwlb.json")
    print(f"     共 {len(result.items)} 条新闻")

    # Step 3: 生成 HTML 页面
    print(f"\n📄 生成 HTML 页面...")
    out = build_xwlb_page(
        json_path=str(data_path),
        output_dir=str(data_dir),
        template_path=str(XWLB_TEMPLATE),
    )
    print(f"  ✅ HTML 页面 → {Path(out).relative_to(PROJECT_ROOT)}")

    # Step 4: 重建所有 xwlb 页面的侧边栏
    print(f"\n🧩 重建侧边栏...")
    all_dates = get_xwlb_dates()
    rebuild_xwlb_sidebars(all_dates)

    # Step 5: 重建着陆页
    print(f"\n🏠 重建着陆页...")
    rebuild_landing_page()

    print(f"\n{'=' * 50}")
    print(f"✅ 每日更新完成: {date_str}")
    print(f"   📄 site/xwlb/{date_str}/index.html")
    print(f"   🏠 site/index.html")
    print(f"   📊 累计 {len(all_dates)} 天新闻联播")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
