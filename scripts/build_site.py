#!/usr/bin/env python3
"""
build_site.py — Assemble deployment directory for News Tools

Usage:
    python scripts/build_site.py

Output: site/ directory ready for Cloudflare Pages deployment.
"""

import json
import os
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = PROJECT_ROOT / "report"
ASSETS_DIR = PROJECT_ROOT / "assets"
SITE_DIR = PROJECT_ROOT / "site"

FONTS_DIR = SITE_DIR / "assets" / "fonts"
REPORTS_DIR = SITE_DIR / "reports"


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


def build_landing_page(report_dirs: list[str]):
    cards = ""
    for rd in sorted(report_dirs, reverse=True):
        date_str = rd
        enriched_json = (REPORT_DIR / rd / "data" / "enriched-trending.json")
        if not enriched_json.exists():
            enriched_json = (REPORTS_DIR / rd / "data" / "enriched-trending.json")
        total = "?"
        summary = ""
        if enriched_json.exists():
            try:
                data = json.loads(enriched_json.read_text(encoding="utf-8"))
                total = str(data.get("total_count", "?"))
                summary = data.get("cover_summary", "")
                if len(summary) > 120:
                    summary = summary[:120] + "…"
            except Exception:
                pass

        if rd.startswith("github-trending-weekly-"):
            # rd like "github-trending-weekly-2026-26" (year-week)
            parts = rd.replace("github-trending-weekly-", "").split("-")
            display_date = f"{parts[0]}年 第{parts[1]}周" if len(parts) >= 2 and parts[0].isdigit() else rd
        else:
            # rd like "2026-06-07" (date)
            parts = rd.split("-")
            display_date = f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 and parts[0].isdigit() else rd

        cards += f"""    <a href="reports/{date_str}/report.html" class="card">
      <div class="card-title">{display_date}</div>
      <div class="card-meta">{total} 个项目</div>
      <div class="card-desc">{summary}</div>
    </a>
"""
    return cards


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

    print("\n📄 Generating landing page...")
    cards_html = build_landing_page(report_dirs)
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>News Tools · GitHub Trending Weekly Reports</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
      background: #f5f4ed;
      color: #141413;
      min-height: 100vh;
    }}
    header {{
      background: #1B365D;
      color: #fff;
      padding: 48px 24px 36px;
      text-align: center;
    }}
    header h1 {{ font-size: 28px; margin-bottom: 8px; }}
    header p {{ font-size: 14px; opacity: .85; max-width: 600px; margin: 0 auto; }}
    .badge {{
      display: inline-block;
      background: rgba(255,255,255,.15);
      border-radius: 4px;
      padding: 2px 10px;
      font-size: 12px;
      margin-top: 10px;
    }}
    .content {{ max-width: 720px; margin: 0 auto; padding: 32px 20px; }}
    .section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 20px; }}
    .cards {{ display: flex; flex-direction: column; gap: 12px; }}
    .card {{
      display: block;
      background: #faf9f5;
      border: 1px solid #e8e6dc;
      border-radius: 8px;
      padding: 16px 20px;
      text-decoration: none;
      color: inherit;
      transition: box-shadow .15s;
    }}
    .card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
    .card-title {{ font-size: 16px; font-weight: 600; margin-bottom: 4px; }}
    .card-meta {{ font-size: 13px; color: #6b6a64; margin-bottom: 6px; }}
    .card-desc {{ font-size: 13px; color: #3d3d3a; line-height: 1.6; }}
    footer {{
      text-align: center;
      padding: 32px 20px;
      font-size: 13px;
      color: #6b6a64;
    }}
    footer a {{ color: #1B365D; }}
  </style>
</head>
<body>
  <header>
    <h1>GitHub Trending 周报</h1>
    <p>每周自动生成的 GitHub Trending 中文报告，覆盖当日最热开源项目。</p>
    <span class="badge">📅 2026年6月</span>
  </header>
  <div class="content">
    <div class="section-title">📊 各期报告</div>
    <div class="cards">
{cards_html}
    </div>
  </div>
  <footer>
    <a href="https://github.com/Mr-nnng/news-tools">News Tools</a> · MIT License
  </footer>
</body>
</html>"""

    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("  ✅ index.html generated")

    print(f"\n✅ Build complete → {SITE_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"   📂 {len(report_dirs)} reports, {sum(1 for _ in FONTS_DIR.iterdir())} font files")


if __name__ == "__main__":
    main()
