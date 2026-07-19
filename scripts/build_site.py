#!/usr/bin/env python3
"""
build_site.py — Assemble deployment directory for News Tools (SPA mode)

Changes from v2 (SPA refactor):
- No longer generates full HTML pages
- Outputs JSON data files only (site/data/{index,github/*,xwlb/*.json})
- SPA runtime (app.js + app.css) handles client-side rendering

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
DATA_DIR = SITE_DIR / "data"
GH_DATA_DIR = DATA_DIR / "github"
XWLB_DATA_DIR = DATA_DIR / "xwlb"


def clean_site():
    """Remove everything except app.css, app.js, index.html, assets/"""
    if not SITE_DIR.exists():
        return
    for item in SITE_DIR.iterdir():
        if item.name in ("app.css", "app.js", "index.html", "assets"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_fonts():
    """Copy fonts to site/ for monospace (JetBrains Mono)."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    src = ASSETS_DIR / "fonts"
    if src.exists():
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, FONTS_DIR / f.name)
                print(f"  📄 {f.name}")
    print(f"  ✅ Fonts → {FONTS_DIR.relative_to(PROJECT_ROOT)}")


# ── Shared helpers ──


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


def load_xwlb_data(rd: str) -> dict | None:
    """Load xwlb.json for a given date string."""
    json_path = REPORT_DIR / f"xwlb-{rd}" / "data" / "xwlb.json"
    if not json_path.exists():
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── GitHub JSON generation ──


def build_gh_json(rd: str) -> dict | None:
    """Generate a GitHub weekly JSON data file.

    Returns the data dict, or None if source data is missing.
    """
    enriched = load_enriched_json(rd)
    if not enriched:
        return None

    repos_raw = enriched.get("repos", [])
    repos = []
    for i, r in enumerate(repos_raw):
        repos.append({
            "rank": i + 1,
            "name": r.get("name", ""),
            "author": r.get("author", ""),
            "url": r.get("url", ""),
            "stars": r.get("stars_total", 0),
            "forks": r.get("forks", 0),
            "weeklyStars": r.get("stars_today", 0),
            "language": r.get("language", ""),
            "langColor": r.get("language_color", "#888"),
            "zhDesc": r.get("zh_desc") or r.get("description") or "",
            "features": r.get("features", []),
            "audience": r.get("audience", ""),
        })

    # Derive week info from date
    date_part = rd
    try:
        parts = date_part.split("-")
        if len(parts) >= 3 and parts[0].isdigit():
            dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            week_num = dt.isocalendar()[1]
            week_label = f"{dt.year}年第{week_num}周"
            week_info = f"{dt.year} 年第 {week_num} 周 / {dt.strftime('%Y-%m-%d')}"
        else:
            week_label = rd
            week_info = rd
    except (ValueError, IndexError):
        week_label = rd
        week_info = rd

    return {
        "weekLabel": week_label,
        "weekInfo": week_info,
        "date": rd,
        "count": len(repos),
        "totalCount": enriched.get("total_count", len(repos)),
        "coverSummary": enriched.get("cover_summary", ""),
        "repos": repos,
    }


def build_gh_data_files() -> list[str]:
    """Scan report/ dirs, generate JSON data files for GitHub weekly."""
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

        data = build_gh_json(date_part)
        if data is None:
            continue

        # Write JSON to site/data/github/YYYY-MM-DD.json
        out_path = GH_DATA_DIR / f"{date_part}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  ✅ {item.name} → {out_path.relative_to(PROJECT_ROOT)}")
        gh_dates.append(date_part)

    return sorted(gh_dates)


# ── XWLB JSON generation ──


def build_xwlb_data_files() -> list[str]:
    """Scan report/xwlb-* dirs and generate JSON data files in site/data/xwlb/."""
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

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            print(f"  ❌ {item.name}: failed to parse xwlb.json")
            continue

        # Build simplified JSON for SPA
        items = data.get("items", [])
        xwlb_out = {
            "title": data.get("title", ""),
            "date": data.get("date", ""),
            "url": data.get("url", ""),
            "count": len(items),
            "summary": data.get("summary", ""),
            "items": [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                }
                for item in items
            ],
        }

        out_path = XWLB_DATA_DIR / f"{date_part}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(xwlb_out, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  ✅ {item.name} → {out_path.relative_to(PROJECT_ROOT)}")
        xwlb_dates.append(date_part)

    return sorted(xwlb_dates)


# ── Index JSON generation ──


def build_index_data(gh_dates: list[str], xwlb_dates: list[str]) -> dict:
    """Generate site/data/index.json for the landing page."""

    def build_month_groups(dates: list[str], loader_fn, count_label: str):
        """Build month-grouped item list."""
        month_groups: dict[str, list[dict]] = {}
        for rd in sorted(dates, reverse=True):
            mk = get_month_key(rd)
            if mk not in month_groups:
                month_groups[mk] = []

            data = loader_fn(rd)
            item_count = 0
            summary = ""
            if data:
                if count_label == "项目":
                    item_count = data.get("totalCount", 0) or data.get("count", 0)
                    summary = data.get("coverSummary", "")
                else:
                    items = data.get("items", [])
                    item_count = len(items)
                    # Build preview from first few item titles
                    titles = [x.get("title", "") for x in items[:3]]
                    clean_titles = []
                    for t in titles:
                        first = t.splitlines()[0].strip() if t else ""
                        first = re.sub(r"[（\(]\d+[）\)].*", "", first).strip()
                        first = first.rstrip("：:;；，, ") or t[:40]
                        if first:
                            clean_titles.append(first)
                    if clean_titles:
                        summary = " · ".join(clean_titles)
                        if len(summary) > 180:
                            summary = summary[:180] + "…"

            display_summary = (summary[:280] + "…") if len(summary) > 280 else summary
            month_groups[mk].append({
                "date": rd,
                "count": item_count if isinstance(item_count, int) else 0,
                "summary": display_summary,
            })

        # Sort items within each month
        for mk in month_groups:
            month_groups[mk].sort(key=lambda x: x["date"], reverse=True)

        # Sort months
        sorted_months = sorted(month_groups.keys(), key=month_sort_key, reverse=True)
        return [
            {"label": mk, "items": month_groups[mk]}
            for mk in sorted_months
        ]

    gh_months = build_month_groups(
        gh_dates, lambda rd: build_gh_json(rd), "项目"
    )
    xwlb_months = build_month_groups(
        xwlb_dates, lambda rd: load_xwlb_data(rd), "新闻"
    )

    index_data = {
        "gh": {
            "count": len(gh_dates),
            "months": gh_months,
        },
        "xwlb": {
            "count": len(xwlb_dates),
            "months": xwlb_months,
        },
    }

    # Write index.json
    out_path = DATA_DIR / "index.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  ✅ index.json → {out_path.relative_to(PROJECT_ROOT)}")

    # Print stats
    total_projects = 0
    for rd in gh_dates:
        data = load_enriched_json(rd)
        if data:
            total_projects += data.get("total_count", 0) or len(data.get("repos", []))
    print(f"     📊 {len(gh_dates)} GitHub reports, {total_projects} total projects")
    print(f"     📊 {len(xwlb_dates)} XWLB days")

    return index_data


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main():
    if REPORT_DIR.exists():
        clean_site()
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    print("🔨 Building site (SPA mode)...\n")

    print("📁 Copying fonts...")
    copy_fonts()

    print("\n📁 Building GitHub weekly JSON data...")
    gh_dates = build_gh_data_files()
    print(f"  📁 {len(gh_dates)} GitHub weekly data files")

    print("\n📁 Building XWLB JSON data...")
    xwlb_dates = build_xwlb_data_files()
    print(f"  📁 {len(xwlb_dates)} XWLB data files")

    print("\n📄 Generating index.json...")
    build_index_data(gh_dates, xwlb_dates)

    print(f"\n✅ Build complete → {SITE_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"   📂 SPA shell: index.html + app.css + app.js")
    print(f"   📂 Data: data/index.json + data/github/*.json + data/xwlb/*.json")


if __name__ == "__main__":
    main()
