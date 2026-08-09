#!/usr/bin/env python3
"""
wallstreet_update.py — 华尔街见闻三栏目（早餐/早间汇总/盘前）更新入口

每个栏目使用独立的小时间窗抓取（score=3 重要级），避免整日抓取被 API 风控。
每次任务只抓自己的窗口，并 merge 进当日聚合文件 site/data/wallstreet/{date}.json
（幂等：重复更新同一栏目覆盖不叠加，不破坏其他栏目）。

用法:
    python scripts/wallstreet_update.py --section breakfast [--date 2026-08-05]
    python scripts/wallstreet_update.py --section morning
    python scripts/wallstreet_update.py --section premarket
    python scripts/wallstreet_update.py --section all --date 2026-08-05   # 全量重建
"""

import sys
import argparse
from pathlib import Path

# 确保 src/ 和 scripts/ 可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from news_tools.wallstreet import (
    fetch_live_between,
    find_section_items,
)
from news_tools.wallstreet_sections import (
    SECTION_ORDER,
    SECTION_LABELS,
    SECTION_SCORE,
    section_window,
    default_date_str,
    is_weekday,
    build_section_entry,
    load_daily_file,
    save_daily_file,
)
import build_site

SITE_DIR = PROJECT_ROOT / "site"
DATA_DIR = SITE_DIR / "data"
WALLSTREET_DATA_DIR = DATA_DIR / "wallstreet"


def update_section(section: str, date_str: str, verbose: bool = True) -> bool:
    """抓取并 merge 指定栏目到当日文件。返回是否写入新数据。"""
    if section not in SECTION_ORDER:
        print(f"  ⚠️  未知栏目: {section}，可用: {', '.join(SECTION_ORDER)} / all")
        return False

    start, end = section_window(section, date_str)
    label = SECTION_LABELS[section]
    print(f"📡 [{label}] 抓取窗口 {start.strftime('%H:%M')}~{end.strftime('%H:%M')} (score={SECTION_SCORE})")

    result = fetch_live_between(
        start_dt=start,
        end_dt=end,
        score=SECTION_SCORE,
        verbose=verbose,
    )
    print(f"  ℹ️  窗口内命中 {result.total_count} 条快讯")

    hits = find_section_items(result.items, section)
    print(f"  ℹ️  栏目 [{label}] 匹配 {len(hits)} 条")

    if not hits:
        print(f"  ⚠️  {date_str} [{label}] 尚未发布或窗口内未匹配到，跳过")
        return False

    # 取最新一条
    latest = hits[0]
    entry = build_section_entry(latest)

    data = load_daily_file(WALLSTREET_DATA_DIR, date_str)
    sections = data.setdefault("sections", {})
    prev_count = len(sections.get(section, {}).get("points", []))
    sections[section] = entry
    save_daily_file(WALLSTREET_DATA_DIR, date_str, data)

    print(f"  ✅ 已更新 [{label}] → {WALLSTREET_DATA_DIR / (date_str + '.json')}")
    print(f"     标题: {entry['title']}")
    print(f"     要点: {len(entry['points'])} 条 (原 {prev_count} 条)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="华尔街见闻三栏目更新脚本")
    parser.add_argument(
        "--section", "-s", required=True,
        help="栏目: breakfast / morning / premarket / all（all 为全量重建）",
    )
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天 (CST)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="忽略工作日检查强制更新（补历史数据用）",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="关闭抓取进度输出"
    )
    args = parser.parse_args()

    date_str = args.date or default_date_str()
    section = args.section.lower()
    verbose = not args.quiet

    print(f"🗓  目标日期: {date_str}")

    # 华尔街见闻三栏目仅在工作日发布；非工作日静默退出（exit 0，不报错）
    if not args.force and not is_weekday(date_str):
        print(f"  ⏭️  {date_str} 为周末，华尔街见闻三栏目不发布，跳过")
        return
    if args.force and not is_weekday(date_str):
        print(f"  ⚡ --force 指定，忽略周末检查强制更新")

    sections = SECTION_ORDER if section == "all" else [section]

    any_written = False
    for sec in sections:
        try:
            if update_section(sec, date_str, verbose=verbose):
                any_written = True
        except Exception as e:
            print(f"  ❌ [{SECTION_LABELS.get(sec, sec)}] 更新失败: {e}")

    # 重建 index.json
    print("\n🏠 重建 index.json...")
    try:
        build_site.build_index_data()
    except Exception as e:
        print(f"  ⚠️  index.json 重建失败: {e}")

    if any_written:
        print(f"\n✅ 华尔街见闻更新完成: {date_str}")
    else:
        print(f"\nℹ️  无新数据写入（栏目可能未发布或匹配失败）")


if __name__ == "__main__":
    main()
