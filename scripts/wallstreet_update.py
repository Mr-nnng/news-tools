#!/usr/bin/env python3
"""
wallstreet_update.py — 华尔街见闻三栏目（早餐/早间汇总/盘前）更新入口

每个栏目使用独立的小时间窗抓取（score=3 重要级），避免整日抓取被 API 风控。
每次任务只抓自己的窗口，并 merge 进当日聚合文件 site/data/wallstreet/{date}.json
（幂等：重复更新同一栏目覆盖不叠加，不破坏其他栏目）。

「等发布」机制：
    上游发布时刻会漂移（例如美国夏令时结束后，美股盘前从 20:45~21:05 漂到
    21:48~22:01）。若抓取时条目还没发出来，脚本会用单请求探测最新一页并
    轮询等待，直到条目出现或超出等待预算，然后再做一次完整的窗口抓取。

    轮询只在「目标日期 == 今天」时启用（补历史数据没有等待意义）。

用法:
    python scripts/wallstreet_update.py --section breakfast [--date 2026-08-05]
    python scripts/wallstreet_update.py --section morning
    python scripts/wallstreet_update.py --section premarket
    python scripts/wallstreet_update.py --section all --date 2026-08-05   # 全量重建
    python scripts/wallstreet_update.py --section premarket --wait-minutes 45

退出码:
    0 = 有数据写入，或目标日为非工作日（正常跳过）
    1 = 未取到任何数据（栏目未发布/匹配失败/抓取异常），用于让 CI 变红告警
"""

import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

# 确保 src/ 和 scripts/ 可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from news_tools.wallstreet import (
    fetch_live_between,
    fetch_latest_page,
    find_section_items,
)
from news_tools.wallstreet_sections import (
    CST,
    SECTION_ORDER,
    SECTION_LABELS,
    SECTION_SCORE,
    SECTION_WAIT_MINUTES,
    section_window,
    default_date_str,
    cst_date_of,
    is_weekday,
    build_section_entry,
    load_daily_file,
    save_daily_file,
)
import build_site

SITE_DIR = PROJECT_ROOT / "site"
DATA_DIR = SITE_DIR / "data"
WALLSTREET_DATA_DIR = DATA_DIR / "wallstreet"


def wait_for_publish(
    section: str,
    date_str: str,
    wait_minutes: int,
    poll_seconds: int = 60,
) -> dict | None:
    """轮询最新一页，直到该栏目当日条目出现或等待超时。

    每次轮询只发 1 个请求（cursor=1 的最新页覆盖最近数周该 score 的全部条目），
    比反复做时间窗二分定位省一个数量级的请求量。

    Returns:
        命中的 LiveItem；超时或始终未发布时返回 None。
    """
    if wait_minutes <= 0:
        return None

    label = SECTION_LABELS[section]
    deadline = time.monotonic() + wait_minutes * 60
    attempt = 0

    while True:
        attempt += 1
        try:
            items = fetch_latest_page(score=SECTION_SCORE)
            hits = [
                h for h in find_section_items(items, section)
                if cst_date_of(h.display_time) == date_str
            ]
        except Exception as e:  # 探测失败不致命，继续等到预算耗尽
            print(f"  ⚠️  第 {attempt} 次探测失败: {e}")
            hits = []

        if hits:
            if attempt > 1:
                published = datetime.fromtimestamp(hits[0].display_time, tz=CST)
                print(f"  ⏳ 等待 {attempt - 1} 轮后已发布（{published.strftime('%H:%M')}）")
            return hits[0]

        remain = deadline - time.monotonic()
        if remain <= 0:
            print(f"  ⏰ 已等待 {wait_minutes} 分钟，[{label}] 仍未发布")
            return None

        print(f"  ⏳ [{label}] 尚未发布，{int(remain)}s 后重试…")
        time.sleep(min(poll_seconds, remain))


def update_section(
    section: str,
    date_str: str,
    verbose: bool = True,
    wait_minutes: int | None = None,
    poll_seconds: int = 60,
) -> bool:
    """抓取并 merge 指定栏目到当日文件。返回是否写入新数据。"""
    if section not in SECTION_ORDER:
        print(f"  ⚠️  未知栏目: {section}，可用: {', '.join(SECTION_ORDER)} / all")
        return False

    start, end = section_window(section, date_str)
    label = SECTION_LABELS[section]
    print(f"📡 [{label}] 抓取窗口 {start.strftime('%H:%M')}~{end.strftime('%H:%M')} (score={SECTION_SCORE})")

    # 「等发布」：仅对今天的目标日期启用，补历史数据时跳过
    if wait_minutes is None:
        wait_minutes = SECTION_WAIT_MINUTES.get(section, 0)
    probed = None
    if wait_minutes > 0 and date_str == default_date_str():
        probed = wait_for_publish(section, date_str, wait_minutes, poll_seconds)
    elif wait_minutes > 0:
        print(f"  ⏭️  目标日期非今天（{date_str}），跳过等待发布")

    result = fetch_live_between(
        start_dt=start,
        end_dt=end,
        score=SECTION_SCORE,
        verbose=verbose,
    )
    print(f"  ℹ️  窗口内命中 {result.total_count} 条快讯")

    hits = find_section_items(result.items, section)
    print(f"  ℹ️  栏目 [{label}] 匹配 {len(hits)} 条")

    latest = hits[0] if hits else probed
    if latest is None:
        print(f"  ⚠️  {date_str} [{label}] 尚未发布或窗口内未匹配到，跳过")
        return False
    if not hits:
        print("  ⚠️  窗口抓取未命中，回退使用探测到的条目")

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
        "--wait-minutes", type=int, default=None,
        help="栏目未发布时最多等待多少分钟（默认按栏目预设，0 表示不等待）",
    )
    parser.add_argument(
        "--poll-seconds", type=int, default=60,
        help="等待发布时的轮询间隔秒数（默认 60）",
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
            if update_section(
                sec,
                date_str,
                verbose=verbose,
                wait_minutes=args.wait_minutes,
                poll_seconds=args.poll_seconds,
            ):
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
        return

    print(f"\n❌ 未获取到任何数据: {date_str}（栏目可能未发布或匹配失败）")
    sys.exit(1)


if __name__ == "__main__":
    main()
