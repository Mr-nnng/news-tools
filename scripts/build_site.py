#!/usr/bin/env python3
"""
build_site.py — Assemble deployment directory for News Tools (SPA mode)

Reads existing JSON data from site/data/ (github/*.json, xwlb/*.json)
and rebuilds site/data/index.json for the SPA landing page.

Idempotent: safe to run multiple times — never destroys existing data.

Usage:
    python scripts/build_site.py

Output: site/data/index.json
"""

import json
import re
import shutil
from pathlib import Path
from datetime import datetime

# ── Ensure news_tools modules are importable ─────────────────
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
SITE_DIR = PROJECT_ROOT / "site"

FONTS_DIR = SITE_DIR / "assets" / "fonts"
DATA_DIR = SITE_DIR / "data"
GH_DATA_DIR = DATA_DIR / "github"
XWLB_DATA_DIR = DATA_DIR / "xwlb"


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


def get_month_key(rd: str) -> str:
    """Extract year-month key from a date string like '2026-06-07'."""
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


def load_gh_data(rd: str) -> dict | None:
    """Load GitHub weekly JSON from site/data/github/{rd}.json."""
    path = GH_DATA_DIR / f"{rd}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_xwlb_data(rd: str) -> dict | None:
    """Load XWLB JSON from site/data/xwlb/{rd}.json."""
    path = XWLB_DATA_DIR / f"{rd}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def scan_data_dates(data_dir: Path) -> list[str]:
    """Scan a data directory for date-stamped JSON files."""
    if not data_dir.exists():
        return []
    return sorted(
        f.stem for f in data_dir.iterdir()
        if f.is_file() and f.suffix == ".json"
        and re.match(r"^\d{4}-\d{2}-\d{2}$", f.stem)
    )


# ── Index JSON generation ──


def build_index_data() -> dict:
    """Generate site/data/index.json from existing site/data/ files.

    Scans site/data/github/*.json and site/data/xwlb/*.json,
    groups them by month, and writes index.json for the SPA landing page.
    """
    gh_dates = scan_data_dates(GH_DATA_DIR)
    xwlb_dates = scan_data_dates(XWLB_DATA_DIR)

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

        for mk in month_groups:
            month_groups[mk].sort(key=lambda x: x["date"], reverse=True)

        sorted_months = sorted(month_groups.keys(), key=month_sort_key, reverse=True)
        return [
            {"label": mk, "items": month_groups[mk]}
            for mk in sorted_months
        ]

    gh_months = build_month_groups(
        gh_dates, lambda rd: load_gh_data(rd), "项目"
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
    print(f"     📊 {len(gh_dates)} GitHub reports, {len(xwlb_dates)} XWLB days")

    return index_data


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main():
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    print("🔨 Building site (SPA mode)...\n")

    print("📁 Copying fonts...")
    copy_fonts()

    print("\n📄 Building index.json from existing data...")
    build_index_data()

    print(f"\n✅ Build complete → {SITE_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"   📂 SPA shell: index.html + app.css + app.js")
    print(f"   📂 Data: data/index.json + data/github/*.json + data/xwlb/*.json")


if __name__ == "__main__":
    main()
