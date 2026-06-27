#!/usr/bin/env python3
"""
build_site.py — Assemble deployment directory for News Tools

Usage:
    python scripts/build_site.py

Output: site/ directory ready for Cloudflare Pages deployment.
"""

import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "report"
ASSETS_DIR = PROJECT_ROOT / "assets"
SITE_DIR = PROJECT_ROOT / "site"

FONTS_DIR = SITE_DIR / "assets" / "fonts"
REPORTS_DIR = SITE_DIR / "reports"

TEMPLATE_PATH = ASSETS_DIR / "templates" / "landing-news-tools.html"


def clean_site():
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)


def copy_fonts():
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    src = ASSETS_DIR / "fonts"
    if src.exists():
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, FONTS_DIR / f.name)
                print(f"  📄 {f.name}")
    print(f"  ✅ Fonts → {FONTS_DIR.relative_to(PROJECT_ROOT)}")


def copy_report(report_src: Path, report_dst: Path):
    report_dst.mkdir(parents=True, exist_ok=True)

    for item in report_src.iterdir():
        if not item.name.startswith("."):
            if item.is_file() and item.suffix == ".html":
                copy_html_with_font_path_fix(item, report_dst)
            else:
                dest = report_dst / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)


def copy_html_with_font_path_fix(src: Path, dst_dir: Path):
    html = src.read_text(encoding="utf-8")
    html = html.replace(
        '../../assets/fonts/',
        '../../../assets/fonts/',
    )
    dst_path = dst_dir / src.name
    dst_path.write_text(html, encoding="utf-8")
    print(f"  📄 {src.name} (font path adjusted)")


def copy_other_report(report_src: Path, report_dst: Path):
    report_dst.mkdir(parents=True, exist_ok=True)
    for item in report_src.iterdir():
        if not item.name.startswith("."):
            dest = report_dst / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    print(f"  ✅ {report_src.name} → {report_dst.relative_to(PROJECT_ROOT)}")


def load_enriched_json(rd: str) -> dict | None:
    """Load enriched JSON for a report directory, trying report/ then site/reports/."""
    enriched_json = REPORT_DIR / rd / "data" / "enriched-trending.json"
    if not enriched_json.exists():
        enriched_json = REPORTS_DIR / rd / "data" / "enriched-trending.json"
    if not enriched_json.exists():
        return None
    try:
        return json.loads(enriched_json.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_date(rd: str) -> str:
    """Format a report directory name into a human-readable Chinese date string."""
    # rd like "github-trending-weekly-2026-26" (year-week)
    if rd.startswith("github-trending-weekly-"):
        parts = rd.replace("github-trending-weekly-", "").split("-")
        if len(parts) >= 2 and parts[0].isdigit():
            return f"{parts[0]}年 第{parts[1]}周"
        return rd
    # rd like "2026-06-07" (date)
    parts = rd.split("-")
    if len(parts) == 3 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日"
    return rd


def get_month_key(rd: str) -> str:
    """Extract year-month key from a report directory name.
    Handles both '2026-06-07' and 'github-trending-weekly-2026-26' formats.
    Returns string like '2026年06月'.
    """
    if rd.startswith("github-trending-weekly-"):
        parts = rd.replace("github-trending-weekly-", "").split("-")
        if len(parts) >= 2 and parts[0].isdigit():
            return f"{parts[0]}年{int(parts[1]):02d}月"
        return "未知"
    parts = rd.split("-")
    if len(parts) >= 2 and parts[0].isdigit():
        return f"{parts[0]}年{int(parts[1]):02d}月"
    return "未知"


def month_sort_key(mk: str) -> tuple[int, int]:
    """Sort key for month labels like '2026年06月' -> (2026, 6)."""
    import re
    m = re.match(r"(\d{4})年(\d{2})月", mk)
    if m:
        return int(m.group(1)), int(m.group(2))
    return (0, 0)


def build_landing_page(report_dirs: list[str]) -> tuple[str, int]:
    """Generate month-grouped report card HTML and compute total project count."""
    total_projects = 0

    # Group reports by month
    month_groups: dict[str, list[str]] = {}
    for rd in sorted(report_dirs, reverse=True):
        mk = get_month_key(rd)
        if mk not in month_groups:
            month_groups[mk] = []
        month_groups[mk].append(rd)

    # Sort months descending
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
                if len(summary) > 120:
                    summary = summary[:120] + "…"

            display_date = format_date(rd)

            cards_html += f"""    <a href="reports/{rd}/report.html" class="report-card">
      <p class="card-date">{display_date}</p>
      <p class="card-meta">{total} 个项目</p>
      <p class="card-desc">{summary}</p>
    </a>
"""
        months_html += f"""  <div class="month-group">
    <h3 class="month-label">{mk}</h3>
    <div class="report-grid">
{cards_html}    </div>
  </div>
"""
    return months_html, total_projects


def main():
    if REPORT_DIR.exists():
        clean_site()
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    print("🔨 Building site directory...\n")

    print("📁 Copying fonts...")
    copy_fonts()

    print("\n📁 Copying weekly reports...")
    report_dirs = []

    if REPORT_DIR.exists():
        for item in sorted(REPORT_DIR.iterdir()):
            if item.name.startswith("github-trending-weekly-"):
                date_str = item.name.replace("github-trending-weekly-", "")
                report_dirs.append(date_str)
                report_dst = REPORTS_DIR / date_str
                print(f"  📁 {item.name} → {report_dst.relative_to(PROJECT_ROOT)}")
                copy_report(item, report_dst)
    if REPORTS_DIR.exists():
        for item in sorted(REPORTS_DIR.iterdir()):
            date_str = item.name
            if date_str not in report_dirs:
                report_dirs.append(date_str)
        print(f"  📁 {len(report_dirs)} reports available")

    print("\n📄 Generating landing page (Kami design)...")
    cards_html, total_projects = build_landing_page(report_dirs)

    # Load Kami template
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Replace placeholders
    index_html = template.replace("{{MONTH_GROUPS}}", cards_html)
    index_html = index_html.replace("{{REPORT_COUNT}}", str(len(report_dirs)))
    index_html = index_html.replace("{{PROJECT_COUNT}}", str(total_projects))

    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("  ✅ index.html generated (Kami design system)")

    print(f"\n✅ Build complete → {SITE_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"   📂 {len(report_dirs)} reports, {total_projects} total projects, {sum(1 for _ in FONTS_DIR.iterdir())} font files")


if __name__ == "__main__":
    main()
