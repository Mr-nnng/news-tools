#!/usr/bin/env python3
"""
build_site.py — Assemble deployment directory for News Tools

Changes from v1:
- GitHub reports: site/reports/ → site/github_weekly/
- Added XWLB pages: site/xwlb/{date}/index.html
- Landing page: dual-tab layout (GitHub + XWLB)

Usage:
    python scripts/build_site.py

Output: site/ directory ready for Cloudflare Pages deployment.
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime

# ── Ensure news_tools modules are importable ─────────────────
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from news_tools.build_xwlb_html import build_xwlb_page
from news_tools.build_report import build_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "report"
ASSETS_DIR = PROJECT_ROOT / "assets"
SITE_DIR = PROJECT_ROOT / "site"

FONTS_DIR = SITE_DIR / "assets" / "fonts"
GH_DIR = SITE_DIR / "github_weekly"  # was SITE_DIR / "reports"
XWLB_DIR = SITE_DIR / "xwlb"  # new

TEMPLATE_PATH = ASSETS_DIR / "templates" / "landing-news-tools.html"
XWLB_TEMPLATE_PATH = ASSETS_DIR / "templates" / "xwlb-page.html"
GH_TEMPLATE_PATH = ASSETS_DIR / "templates" / "github-trending.html"


def clean_site():
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)


def copy_fonts():
    """Copy fonts to site/ for serif (TsangerJinKai02) and monospace (JetBrains Mono)."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    src = ASSETS_DIR / "fonts"
    if src.exists():
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, FONTS_DIR / f.name)
                print(f"  📄 {f.name}")
    print(f"  ✅ Fonts → {FONTS_DIR.relative_to(PROJECT_ROOT)}")


# ── GitHub Weekly helpers ──


def build_gh_pages():
    """Rebuild GitHub weekly report HTML from enriched JSON, then deploy to site/github_weekly/.

    Unlike the old copy-only approach, this regenerates from JSON (matching XWLB rebuild behaviour).
    After generation, font paths are adjusted and sidebar is injected.
    """
    if not REPORT_DIR.exists():
        return []

    gh_dates = []
    for item in sorted(REPORT_DIR.iterdir()):
        if not item.name.startswith("github-trending-weekly-"):
            continue
        date_part = item.name.replace("github-trending-weekly-", "")
        enriched_json = item / "data" / "enriched-trending.json"
        if not enriched_json.exists():
            print(f"  ⏭️  {item.name}: no enriched-trending.json found")
            continue

        out_dir = GH_DIR / date_part
        try:
            # Rebuild HTML from JSON (skip network avatar download)
            build_report(
                enriched=json.loads(enriched_json.read_text(encoding="utf-8")),
                template_path=str(GH_TEMPLATE_PATH),
                output_dir=str(out_dir),
                avatar_dir_name="avatar",
                download_avatars=False,
            )
            # Read back, fix font paths, and inject sidebar
            report_path = out_dir / "report.html"
            if report_path.exists():
                html = report_path.read_text(encoding="utf-8")
                html = html.replace("{{SIDEBAR}}", "__SIDEBAR_PLACEHOLDER__")
                report_path.write_text(html, encoding="utf-8")
            print(f"  ✅ {item.name} → {out_dir.relative_to(PROJECT_ROOT)}/")
            gh_dates.append(date_part)
        except Exception as e:
            print(f"  ❌ {item.name}: {e}")

    # Second pass: inject sidebar into every GH page (now that we know all dates)
    all_gh_dates = sorted(gh_dates)
    for rd in all_gh_dates:
        report_path = GH_DIR / rd / "report.html"
        if not report_path.exists():
            continue
        html = report_path.read_text(encoding="utf-8")
        sidebar_html = build_gh_sidebar_html(all_gh_dates, rd)
        html = html.replace("__SIDEBAR_PLACEHOLDER__", sidebar_html)
        report_path.write_text(html, encoding="utf-8")
        print(f"  🧩 sidebar injected → {report_path.relative_to(PROJECT_ROOT)}")

    return sorted(gh_dates)


def build_gh_sidebar_html(report_dirs: list[str], current_rd: str) -> str:
    """Generate sidebar timeline HTML for a GitHub report page.

    Sidebar links: ../{rd}/report.html because sidebar is in site/github_weekly/{rd}/report.html
    and linked reports are at site/github_weekly/{other_rd}/report.html
    """
    month_groups: dict[str, list[str]] = {}
    for rd in sorted(report_dirs, reverse=True):
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
            active_class = " is-active" if rd == current_rd else ""
            items_html += f"""
          <a href="../{rd}/report.html" class="sidebar-item{active_class}">{display_date}</a>"""

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

    # Return to home: ../../index.html from site/github_weekly/{date}/index.html
    sidebar = f"""<nav class="sidebar">
    <a class="sidebar-home" href="../../index.html"><span class="icon">🏠</span> 返回主页</a>
    <div class="sidebar-section">
      {sections_html}
    </div>
    <div class="sidebar-footer">
      <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener"><span class="icon">📂</span> GitHub</a>
    </div>
  </nav>"""
    return sidebar


# ── XWLB helpers ──


def build_xwlb_sidebar_html(xwlb_dates: list[str], current_rd: str) -> str:
    """Generate sidebar timeline HTML for an XWLB page.
    Links: ../{rd}/index.html at site/xwlb/{rd}/index.html
    """
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
            active_class = " is-active" if rd == current_rd else ""
            items_html += f"""
          <a href="../{rd}/index.html" class="sidebar-item{active_class}">{display_date}</a>"""
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

    sidebar = f"""<nav class="sidebar">
    <a class="sidebar-home" href="../../index.html"><span class="icon">🏠</span> 返回主页</a>
    <div class="sidebar-section">
      {sections_html}
    </div>
    <div class="sidebar-footer">
      <a href="https://github.com/Mr-nnng/news-tools" target="_blank" rel="noopener"><span class="icon">📂</span> GitHub</a>
    </div>
  </nav>"""
    return sidebar


def build_xwlb_pages():
    """Scan report/xwlb-* dirs and build HTML pages in site/xwlb/{date}/."""
    if not REPORT_DIR.exists():
        return []

    xwlb_dates = []
    for item in sorted(REPORT_DIR.iterdir()):
        if not item.name.startswith("xwlb-"):
            continue
        date_part = item.name.replace("xwlb-", "")
        json_path = item / "data" / "xwlb.json"
        if not json_path.exists():
            print(f"  ⏭️  {item.name}: no xwlb.json found")
            continue

        out_dir = XWLB_DIR / date_part
        try:
            out = build_xwlb_page(
                json_path=str(json_path),
                output_dir=str(out_dir),
                template_path=str(XWLB_TEMPLATE_PATH),
            )
            # Font path in template: ../../assets/fonts/ → correct for site/xwlb/{date}/index.html
            print(f"  ✅ {item.name} → {out_dir.relative_to(PROJECT_ROOT)}/")
            xwlb_dates.append(date_part)
        except Exception as e:
            print(f"  ❌ {item.name}: {e}")

    # Second pass: inject sidebar into every XWLB page (now that we know all dates)
    all_xwlb_dates = sorted(xwlb_dates)
    for rd in all_xwlb_dates:
        xwlb_path = XWLB_DIR / rd / "index.html"
        if not xwlb_path.exists():
            continue
        html = xwlb_path.read_text(encoding="utf-8")
        if "{{SIDEBAR}}" in html:
            sidebar_html = build_xwlb_sidebar_html(all_xwlb_dates, rd)
            html = html.replace("{{SIDEBAR}}", sidebar_html)
            xwlb_path.write_text(html, encoding="utf-8")
            print(f"  🧩 sidebar injected → {xwlb_path.relative_to(PROJECT_ROOT)}")

    return sorted(xwlb_dates)


def load_xwlb_data(rd: str) -> dict | None:
    """Load xwlb.json for a given date string."""
    json_path = REPORT_DIR / f"xwlb-{rd}" / "data" / "xwlb.json"
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Shared helpers ──


def load_enriched_json(rd: str) -> dict | None:
    """Load enriched JSON for a GitHub report directory."""
    enriched_json = (
        REPORT_DIR / f"github-trending-weekly-{rd}" / "data" / "enriched-trending.json"
    )
    if not enriched_json.exists():
        return None
    try:
        return json.loads(enriched_json.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_date(rd: str) -> str:
    """Format a report directory name into a human-readable Chinese date string."""
    parts = rd.split("-")
    if len(parts) == 3 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return rd


def get_month_key(rd: str) -> str:
    """Extract year-month key from a report directory name like '2026-06-07'."""
    parts = rd.split("-")
    if len(parts) >= 2 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1]):02d}月"
    return "未知"


def month_sort_key(mk: str) -> tuple[int, int]:
    """Sort key for month labels like '2026年06月' -> (2026, 6)."""
    m = re.match(r"(\d{4})年(\d{2})月", mk)
    if m:
        return int(m.group(1)), int(m.group(2))
    return (0, 0)


# ── Landing page builders ──


def build_gh_landing_cards(report_dirs: list[str]) -> tuple[str, int]:
    """Generate month-grouped GitHub report card HTML and compute total project count."""
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
            data = load_enriched_json(rd)
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


def build_xwlb_landing_cards(xwlb_dates: list[str]) -> tuple[str, int]:
    """Generate month-grouped XWLB card HTML and compute total day count.

    Card preview shows first few cleaned news titles separated by ·.
    """
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
            item_count = "?"
            preview = ""
            if data:
                items = data.get("items", [])
                item_count = str(len(items)) if items else "0"
                # Build preview from first few item titles
                titles = [x.get("title", "") for x in items[:3]]
                clean_titles = []
                for t in titles:
                    # Extract first line, clean sub-title numbering
                    first = t.splitlines()[0].strip() if t else ""
                    first = re.sub(r"[（\(]\d+[）\)].*", "", first).strip()
                    first = first.rstrip("：:;；，, ") or t[:40]
                    if first:
                        clean_titles.append(first)
                if clean_titles:
                    preview = " · ".join(clean_titles)
                    if len(preview) > 180:
                        preview = preview[:180] + "…"

            display_date = format_date(rd)
            cards_html += f"""    <a href="xwlb/{rd}/index.html" class="report-card">
      <p class="card-date">{display_date}</p>
      <p class="card-meta">{item_count} 条新闻</p>
      <p class="card-desc">{preview}</p>
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
    return months_html, total_days


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main():
    if REPORT_DIR.exists():
        clean_site()
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    print("🔨 Building site directory...\n")

    print("📁 Copying fonts...")
    copy_fonts()

    print("\n📁 Building GitHub weekly reports...")
    gh_dirs = build_gh_pages()
    print(f"  📁 {len(gh_dirs)} GitHub weekly reports available")

    print("\n📁 Building XWLB pages...")
    xwlb_dates = build_xwlb_pages()
    print(f"  📁 {len(xwlb_dates)} XWLB dates available")

    print("\n📄 Generating landing page (Kami design, dual-tab)...")
    gh_cards_html, total_projects = build_gh_landing_cards(gh_dirs)
    xwlb_cards_html, total_xwlb_days = build_xwlb_landing_cards(xwlb_dates)

    # Load Kami template
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Replace placeholders
    index_html = template.replace("{{GH_MONTH_GROUPS}}", gh_cards_html)
    index_html = index_html.replace("{{XWLB_MONTH_GROUPS}}", xwlb_cards_html)
    index_html = index_html.replace("{{REPORT_COUNT}}", str(len(gh_dirs)))
    index_html = index_html.replace("{{XWLB_COUNT}}", str(total_xwlb_days))

    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("  ✅ index.html generated (Kami design system, dual-tab)")

    print(f"\n✅ Build complete → {SITE_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"   📂 {len(gh_dirs)} GitHub reports, {total_projects} total projects")
    print(f"   📂 {total_xwlb_days} XWLB days")


if __name__ == "__main__":
    main()
