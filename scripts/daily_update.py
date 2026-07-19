#!/usr/bin/env python3
"""
daily_update.py — GitHub Actions 每日新闻联播自动更新入口 (SPA mode)

复用 build_site.py 中的 landing card / month group 生成函数。
不再生成 HTML 页面，仅写入 JSON 数据，由 SPA 运行时渲染。

用法:
    python scripts/daily_update.py
    python scripts/daily_update.py --date 2026-06-27
"""

import json
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保 src/ 和 scripts/ 可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from news_tools.xwlb import get_xwlb
import build_site  # 复用 data / month 工具函数

SITE_DIR = PROJECT_ROOT / "site"
DATA_DIR = SITE_DIR / "data"
XWLB_DATA_DIR = DATA_DIR / "xwlb"


# ═══════════════════════════════════════════════════════════════════
# XWLB 数据生成
# ═══════════════════════════════════════════════════════════════════


def get_xwlb_dates() -> list[str]:
    """扫描 data/xwlb/ 获取所有已有日期（不含 .json 后缀）。"""
    if not XWLB_DATA_DIR.exists():
        return []
    return sorted(
        f.stem
        for f in XWLB_DATA_DIR.iterdir()
        if f.is_file() and f.suffix == ".json" and re.match(r"^\d{4}-\d{2}-\d{2}$", f.stem)
    )


def save_xwlb_json(date_str: str, data: dict) -> Path:
    """保存 XWLB 数据为 SPA JSON 格式到 data/xwlb/{date}.json。"""
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
    XWLB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = XWLB_DATA_DIR / f"{date_str}.json"
    out_path.write_text(
        json.dumps(xwlb_out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path




# ═══════════════════════════════════════════════════════════════════
# 着陆页 Index JSON 重建
# ═══════════════════════════════════════════════════════════════════


def rebuild_index() -> None:
    """从 data/ 目录现有文件重建 site/data/index.json。"""
    build_site.build_index_data()


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="每日新闻联播自动更新脚本 (SPA mode)")
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天"
    )
    args = parser.parse_args()

    # —— 确定目标日期（北京时间） ——
    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)
    today_bj = now_bj.strftime("%Y-%m-%d")

    if args.date:
        dt = datetime.strptime(args.date, "%Y-%m-%d")
        # 如果传入的日期是今天，且当前北京时间 < 20:30，则使用昨天
        if args.date == today_bj and (now_bj.hour < 20 or (now_bj.hour == 20 and now_bj.minute < 30)):
            dt = dt - timedelta(days=1)
            print(f"  ℹ️  当前北京时间 {now_bj.hour:02d}:{now_bj.minute:02d}，尚未到 20:30")
            print(f"  ℹ️  回退到前一天: {dt.strftime('%Y-%m-%d')}")
    else:
        dt = now_bj
        # 19:00 之前新闻联播尚未播出，默认获取昨天
        if dt.hour < 19 or (dt.hour == 19 and dt.minute < 10):
            dt = dt - timedelta(days=1)

    date_str = dt.strftime("%Y-%m-%d")
    print(f"🔍 目标日期: {date_str}\n")

    # Step 1: 确保站点资源
    print("📁 确保站点资源...")
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("  ✅ 站点目录就绪")

    # Step 2: 获取新闻联播数据
    print(f"\n📡 获取 {date_str} 新闻联播数据...")
    result = get_xwlb(dt.year, dt.month, dt.day)

    if result is None:
        print(f"  ⚠️  {date_str} 暂无新闻联播数据（可能尚未发布）")
        print("\n🏠 重新构建 index.json...")
        rebuild_index()
        return

    # Step 3: 生成 SPA JSON 数据文件
    print(f"\n📄 生成 SPA JSON 数据...")
    out_path = save_xwlb_json(date_str, result.model_dump())
    print(f"  ✅ SPA JSON → {out_path.relative_to(PROJECT_ROOT)}")
    print(f"     共 {len(result.items)} 条新闻")

    # Step 4: 重建 index.json
    print(f"\n🏠 重建 index.json...")
    rebuild_index()

    print(f"\n{'=' * 50}")
    print(f"✅ 每日更新完成: {date_str}")
    print(f"   📄 site/data/xwlb/{date_str}.json")
    print(f"   🏠 site/data/index.json")
    print(f"   📊 累计 {len(get_xwlb_dates())} 天新闻联播")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
