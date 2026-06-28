"""
news_tools/wallstreet.py — 华尔街见闻 7x24 快讯获取工具

通过直接请求 API 获取指定日期 0:00~24:00 的全部重要新闻，输出 JSON。

用法:
    python -m news_tools.wallstreet                          # 今日快讯
    python -m news_tools.wallstreet --date 2026-05-29        # 指定日期
    python -m news_tools.wallstreet --date 2026-05-28 -o news.json
    python -m news_tools.wallstreet --score 3                # 仅最重要的新闻
    python -m news_tools.wallstreet --compact                # 仅输出 items 数组

作为模块调用:
    from news_tools.wallstreet import fetch_live_by_date
    result = fetch_live_by_date(target_date=datetime(2026, 5, 29))
    print(result.model_dump_json(indent=2, ensure_ascii=False))
"""

import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from pydantic import BaseModel

# ── 时区 ───────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))

# ── API 配置 ───────────────────────────────────────────────────────
API_URL = "https://api-one-wscn.awtmt.com/apiv1/search/live"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),
    "Origin": "https://wallstreetcn.com",
    "Referer": "https://wallstreetcn.com/",
    "x-client-type": "pc",
    "x-ivanka-app": "wscn|web|0.40.40|0.0|0",
    "x-ivanka-platform": "wscn-platform",
}

DEFAULT_LIMIT = 100
REQUEST_INTERVAL = 0.3
BINARY_SEARCH_LIMIT = 20


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════


class LiveItem(BaseModel):
    """单条 7x24 快讯/日历数据"""

    id: int
    display_time: int
    content_text: str
    content: str
    title: str
    highlight_title: str
    score: int
    type: str
    uri: str
    is_calendar: bool
    channels: list[str]
    cover_images: list[dict]
    symbols: list
    tags: list
    reference: str
    article: Optional[dict] = None
    calendar_key: Optional[str] = None
    wscn_ticker: Optional[str] = None


class LiveResult(BaseModel):
    """完整结果（JSON 顶层结构）"""

    source: str = "wallstreet_live"
    date: str
    score: int
    fetched_at: str
    total_count: int
    items: list[LiveItem]


# ═══════════════════════════════════════════════════════════════════
# API 请求工具
# ═══════════════════════════════════════════════════════════════════


def _fetch_page(
    cursor: Optional[int] = None,
    limit: int = DEFAULT_LIMIT,
    score: int = 2,
) -> dict:
    """获取单页数据。"""
    params = {"channel": "global-channel", "limit": limit, "score": score}
    if cursor is not None:
        params["cursor"] = str(cursor)
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _get_first_page_data(
    limit: int = BINARY_SEARCH_LIMIT, score: int = 2
) -> tuple[list[dict], int, int]:
    """获取第一页（最新）数据，同时获取 total_count 和 next_cursor。"""
    data = _fetch_page(cursor=None, limit=limit, score=score)
    d = data.get("data", {})
    items = d.get("items", [])
    total_count = d.get("count", 0)
    next_cursor = int(d.get("next_cursor", 2))
    return items, total_count, next_cursor


def _get_first_item_time(cursor: int, limit: int, score: int) -> Optional[int]:
    """获取指定 cursor 页的第一条（最新）display_time。"""
    data = _fetch_page(cursor=cursor, limit=limit, score=score)
    items = data.get("data", {}).get("items", [])
    return items[0]["display_time"] if items else None


def _get_last_item_time(cursor: int, limit: int, score: int) -> Optional[int]:
    """获取指定 cursor 页的最后一条（最旧）display_time。"""
    data = _fetch_page(cursor=cursor, limit=limit, score=score)
    items = data.get("data", {}).get("items", [])
    return items[-1]["display_time"] if items else None


def _find_max_cursor(score: int = 2) -> int:
    """二分查找最大有效 cursor 值。"""
    lo, hi = 1, 1
    while True:
        ts = _get_first_item_time(hi, BINARY_SEARCH_LIMIT, score)
        if ts is None:
            break
        hi *= 2
        if hi > 50000:
            break
        time.sleep(REQUEST_INTERVAL)

    while lo < hi:
        mid = (lo + hi) // 2
        ts = _get_first_item_time(mid, BINARY_SEARCH_LIMIT, score)
        if ts is not None:
            lo = mid + 1
        else:
            hi = mid
        time.sleep(REQUEST_INTERVAL)

    return lo - 1


def _find_cursor_for_time(
    target_ts: int,
    max_cursor: int,
    score: int = 2,
    find_newest: bool = True,
) -> int:
    """二分查找目标时间对应的 cursor。"""
    first_ts = _get_first_item_time(1, BINARY_SEARCH_LIMIT, score)
    if first_ts is not None and target_ts >= first_ts:
        return 1

    last_ts = _get_last_item_time(max_cursor, BINARY_SEARCH_LIMIT, score)
    if last_ts is not None and target_ts <= last_ts:
        return max_cursor + 1

    lo, hi = 1, max_cursor
    if find_newest:
        while lo < hi:
            mid = (lo + hi) // 2
            ts = _get_first_item_time(mid, BINARY_SEARCH_LIMIT, score)
            if ts is None or ts > target_ts:
                lo = mid + 1
            else:
                hi = mid
            time.sleep(REQUEST_INTERVAL)
        return lo
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            ts = _get_last_item_time(mid, BINARY_SEARCH_LIMIT, score)
            if ts is None or ts >= target_ts:
                lo = mid + 1
            else:
                hi = mid
            time.sleep(REQUEST_INTERVAL)
        return lo


# ═══════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════


def fetch_live_by_date(
    target_date: datetime,
    score: int = 2,
    limit: int = DEFAULT_LIMIT,
    max_retries: int = 3,
    verbose: bool = False,
) -> LiveResult:
    """获取指定日期 0:00~24:00 (CST, UTC+8) 的全部重要新闻。

    Args:
        target_date: 目标日期（将在 CST 时区解析）
        score: 新闻重要度 (2=重要, 3=更重要)
        limit: 每页大小
        max_retries: 单次请求最大重试次数
        verbose: 是否输出进度信息到 stderr

    Returns:
        LiveResult 包含所有符合条件条目
    """
    if target_date.tzinfo is None:
        target_date = target_date.replace(tzinfo=CST)
    else:
        target_date = target_date.astimezone(CST)

    target_start = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=CST
    )
    target_end_exclusive = datetime(
        target_date.year, target_date.month, target_date.day + 1, tzinfo=CST
    )

    start_ts = int(target_start.timestamp())
    end_ts_exclusive = int(target_end_exclusive.timestamp())
    date_str = target_date.strftime("%Y-%m-%d")

    def log(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr)

    log(f"目标日期: {date_str}")
    log(f"  时间戳范围: {start_ts} ~ {end_ts_exclusive}  (score={score})")

    # 1. 获取总条数
    first_items, total_count, _ = _get_first_page_data(limit=1, score=score)
    log(f"总数据量 (score={score}): {total_count} 条")

    if total_count == 0:
        log("无数据")
        return LiveResult(
            date=date_str,
            score=score,
            fetched_at=datetime.now(CST).isoformat(),
            total_count=0,
            items=[],
        )

    # 2. 二分查找最大 cursor
    log("正在确定最大 cursor...")
    max_cursor = _find_max_cursor(score=score)
    log(f"最大 cursor: {max_cursor}")

    # 3. 二分查找起始 cursor
    log("正在定位起始位置...")
    start_cursor = _find_cursor_for_time(
        target_ts=end_ts_exclusive, max_cursor=max_cursor, score=score, find_newest=True
    )

    check_ts = _get_first_item_time(start_cursor, limit, score)
    if check_ts is None or check_ts < start_ts:
        # 二分找到的 cursor 数据已早于目标日，但最新页（cursor 1）可能已跨越目标日范围
        first_page = _fetch_page(cursor=1, limit=limit, score=score)
        cursor1_items = first_page.get("data", {}).get("items", [])
        if any(
            start_ts <= item["display_time"] < end_ts_exclusive
            for item in cursor1_items
        ):
            start_cursor = 1
        else:
            log(f"目标日期 {date_str} 在该频道中无数据")
            return LiveResult(
                date=date_str,
                score=score,
                fetched_at=datetime.now(CST).isoformat(),
                total_count=0,
                items=[],
            )

    log(f"起始 cursor: {start_cursor}")
    if check_ts:
        log(
            f"  该页最新: {datetime.fromtimestamp(check_ts, tz=CST).strftime('%Y-%m-%d %H:%M:%S')}"
        )

    # 4. 顺序翻页收集数据
    all_items: list[dict] = []
    cursor = start_cursor
    consecutive_empty = 0
    page_num = 0

    log("正在获取数据...")

    while cursor <= max_cursor:
        try:
            data = _fetch_page(cursor=cursor, limit=limit, score=score)
        except requests.RequestException as e:
            log(f"  请求失败 (cursor={cursor}): {e}")
            consecutive_empty += 1
            if consecutive_empty >= max_retries:
                log("  连续失败，终止")
                break
            time.sleep(REQUEST_INTERVAL * 2)
            continue

        items = data.get("data", {}).get("items", [])
        next_cursor = int(data.get("data", {}).get("next_cursor", cursor + 1))

        if not items:
            log(f"  第 {page_num} 页 (cursor={cursor}): 空")
            consecutive_empty += 1
            if consecutive_empty >= max_retries:
                break
            cursor = next_cursor
            time.sleep(REQUEST_INTERVAL)
            continue

        consecutive_empty = 0
        page_num += 1

        first_ts = items[0]["display_time"]
        last_ts = items[-1]["display_time"]

        page_items = [
            item
            for item in items
            if start_ts <= item["display_time"] < end_ts_exclusive
        ]
        all_items.extend(page_items)

        log(
            f"  第 {page_num} 页 (cursor={cursor}): "
            f"范围 {datetime.fromtimestamp(first_ts, tz=CST).strftime('%H:%M')}"
            f"~{datetime.fromtimestamp(last_ts, tz=CST).strftime('%H:%M')}, "
            f"命中 {len(page_items)} 条, 累计 {len(all_items)} 条"
        )

        if last_ts < start_ts:
            log("  已超出目标日期范围，停止")
            break

        cursor = next_cursor
        time.sleep(REQUEST_INTERVAL)

    # 5. 按 display_time 降序排列
    all_items.sort(key=lambda x: x["display_time"], reverse=True)
    result_items = [LiveItem(**item) for item in all_items]

    log(f"\n完成! 共获取 {len(result_items)} 条")

    return LiveResult(
        source="wallstreet_live",
        date=date_str,
        score=score,
        fetched_at=datetime.now(CST).isoformat(),
        total_count=len(result_items),
        items=result_items,
    )


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI 入口函数。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="获取华尔街见闻 7x24 快讯（按日期筛选重要新闻），输出 JSON。",
    )
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天"
    )
    parser.add_argument(
        "--score",
        "-s",
        type=int,
        default=2,
        choices=[2, 3],
        help="新闻重要度: 2=重要 (默认), 3=最重要",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"每页条数 (默认 {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--output", "-o", default=None, help="输出文件路径（默认输出到终端）"
    )
    parser.add_argument(
        "--compact", action="store_true", help="紧凑模式：仅输出 items 数组"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="显示进度信息到 stderr"
    )

    args = parser.parse_args()

    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            err = {"error": f"日期格式无效 '{args.date}'，应为 YYYY-MM-DD"}
            print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        target = datetime.now(CST)

    try:
        result = fetch_live_by_date(
            target_date=target,
            score=args.score,
            limit=args.limit,
            verbose=args.verbose,
        )
    except requests.RequestException as e:
        print(
            json.dumps({"error": f"请求 API 失败: {e}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if args.compact:
        data = [r.model_dump() for r in result.items]
    else:
        data = result.model_dump()

    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
            f.write("\n")
        print(
            json.dumps(
                {"status": "saved", "path": args.output, "count": result.total_count},
                ensure_ascii=False,
            )
        )
    else:
        print(json_str)


if __name__ == "__main__":
    main()
