"""
news_tools/wallstreet.py — 华尔街见闻 7x24 快讯获取工具

通过直接请求 API 获取指定时间范围（默认单日 0:00~24:00）的重要新闻，输出 JSON。

用法:
    python -m news_tools.wallstreet                          # 今日快讯
    python -m news_tools.wallstreet --date 2026-05-29        # 指定日期
    python -m news_tools.wallstreet --date 2026-05-28 -o news.json
    python -m news_tools.wallstreet --score 3                # 仅最重要的新闻
    python -m news_tools.wallstreet --compact                # 仅输出 items 数组
    python -m news_tools.wallstreet --start 2026-05-29T00:00 --end 2026-05-29T08:00  # 时间窗

作为模块调用:
    from news_tools.wallstreet import fetch_live_by_date, fetch_live_between
    result = fetch_live_by_date(target_date=datetime(2026, 5, 29))
    result = fetch_live_between(start_dt=datetime(2026, 5, 29, 0, 0),
                                end_dt=datetime(2026, 5, 29, 8, 0))
    print(result.model_dump_json(indent=2, ensure_ascii=False))
"""

import sys
import json
import re
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
# 栏目工具（华尔街见闻聚合栏目）
# ═══════════════════════════════════════════════════════════════════

# 栏目 → 标题匹配规则
#   breakfast: 前缀匹配 "华尔街见闻早餐"（每日含日期，如 "华尔街见闻早餐 | 2026年8月5日"）
#   morning:   精确匹配 "早间要闻汇总"（固定标题）
#   premarket: 包含 "美股盘前"（如 "周三美股盘前你需要了解的全球要闻"）
SECTION_PATTERNS: dict[str, str] = {
    "breakfast": "华尔街见闻早餐",
    "morning": "早间要闻汇总",
    "premarket": "美股盘前",
}

SECTION_LABELS: dict[str, str] = {
    "breakfast": "华尔街见闻早餐",
    "morning": "早间要闻汇总",
    "premarket": "美股盘前",
}

SECTION_ORDER: list[str] = ["breakfast", "morning", "premarket"]


def find_section_items(items: list[LiveItem], section: str) -> list[LiveItem]:
    """按标题匹配栏目条目，返回按 display_time 降序排列的命中列表。"""
    pattern = SECTION_PATTERNS.get(section)
    if not pattern:
        return []
    hits: list[LiveItem] = []
    for item in items:
        title = (item.title or "").strip()
        if section == "morning":
            matched = title == pattern
        elif section == "breakfast":
            matched = title.startswith(pattern)
        else:  # premarket
            matched = pattern in title
        if matched:
            hits.append(item)
    hits.sort(key=lambda x: x.display_time, reverse=True)
    return hits


def parse_content_points(content: str, content_text: str = "") -> list[str]:
    """将快讯 content（HTML）解析为纯文本要点列表。

    优先解析 <ul>/<li> 结构；无列表标签时回退到 content_text 按换行切分；
    仍为空时返回空列表。
    """
    if not content:
        content = ""

    # 1) 解析 <li>...</li>
    li_items = re.findall(r"<li[^>]*>(.*?)</li>", content, flags=re.DOTALL)
    if li_items:
        points: list[str] = []
        for li in li_items:
            # 去掉残留 HTML 标签与 br
            text = re.sub(r"<br\s*/?>", "\n", li)
            text = re.sub(r"<[^>]+>", "", text)
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    points.append(line)
        return points

    # 2) 回退：content_text 按换行切分
    text = (content_text or "").strip()
    if text:
        return [line.strip() for line in text.split("\n") if line.strip()]

    # 3) 最后回退：content 去标签
    text = re.sub(r"<br\s*/?>", "\n", content)
    text = re.sub(r"<[^>]+>", "", text)
    return [line.strip() for line in text.split("\n") if line.strip()]


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


def fetch_live_between(
    start_dt: datetime,
    end_dt: datetime,
    score: int = 2,
    limit: int = DEFAULT_LIMIT,
    max_retries: int = 3,
    verbose: bool = False,
) -> LiveResult:
    """获取指定时间范围 [start_dt, end_dt) 内 (CST, UTC+8) 的重要新闻。

    相比整日抓取，按小时间窗抓取可显著减少分页请求量，降低被 API 风控的概率。

    Args:
        start_dt: 起始时间（含），将在 CST 时区解析
        end_dt: 结束时间（不含），将在 CST 时区解析
        score: 新闻重要度 (2=重要, 3=更重要)
        limit: 每页大小
        max_retries: 单次请求最大重试次数
        verbose: 是否输出进度信息到 stderr

    Returns:
        LiveResult 包含所有符合条件条目（date 字段取 start_dt 所在日期）
    """
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=CST)
    else:
        start_dt = start_dt.astimezone(CST)

    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=CST)
    else:
        end_dt = end_dt.astimezone(CST)

    if end_dt <= start_dt:
        raise ValueError("end_dt 必须晚于 start_dt")

    start_ts = int(start_dt.timestamp())
    end_ts_exclusive = int(end_dt.timestamp())
    date_str = start_dt.strftime("%Y-%m-%d")

    def log(msg: str) -> None:
        if verbose:
            print(msg, file=sys.stderr)

    log(f"目标时间窗: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ "
        f"{end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  时间戳范围: {start_ts} ~ {end_ts_exclusive}  (score={score})")

    # 1. 获取总条数
    _, total_count, _ = _get_first_page_data(limit=1, score=score)
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

    # 3. 二分查找起始 cursor（以窗口结束时间为目标）
    log("正在定位起始位置...")
    start_cursor = _find_cursor_for_time(
        target_ts=end_ts_exclusive, max_cursor=max_cursor, score=score, find_newest=True
    )

    check_ts = _get_first_item_time(start_cursor, limit, score)
    if check_ts is None or check_ts < start_ts:
        # 二分找到的 cursor 数据已早于窗口起点，但最新页（cursor 1）可能已跨越窗口范围
        first_page = _fetch_page(cursor=1, limit=limit, score=score)
        cursor1_items = first_page.get("data", {}).get("items", [])
        if any(
            start_ts <= item["display_time"] < end_ts_exclusive
            for item in cursor1_items
        ):
            start_cursor = 1
        else:
            log(f"时间窗 {date_str} 在该频道中无数据")
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
            log("  已超出目标时间窗范围，停止")
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


def fetch_live_by_date(
    target_date: datetime,
    score: int = 2,
    limit: int = DEFAULT_LIMIT,
    max_retries: int = 3,
    verbose: bool = False,
) -> LiveResult:
    """获取指定日期 0:00~24:00 (CST, UTC+8) 的全部重要新闻。

    内部委托给 fetch_live_between（整日窗口），保持向后兼容。

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

    start = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=CST
    )
    end_exclusive = datetime(
        target_date.year, target_date.month, target_date.day + 1, tzinfo=CST
    )
    return fetch_live_between(
        start_dt=start,
        end_dt=end_exclusive,
        score=score,
        limit=limit,
        max_retries=max_retries,
        verbose=verbose,
    )


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI 入口函数。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "获取华尔街见闻 7x24 快讯，支持整日或时间窗抓取，输出 JSON。"
        ),
    )
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天"
    )
    parser.add_argument(
        "--start", default=None,
        help="起始时间 (YYYY-MM-DDTHH:MM 或 YYYY-MM-DD HH:MM)，与 --end 搭配",
    )
    parser.add_argument(
        "--end", default=None,
        help="结束时间（不含），与 --start 搭配",
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

    def _parse_dt(s: str, label: str) -> datetime:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt).replace(tzinfo=CST)
            except ValueError:
                continue
        err = {"error": f"{label} 格式无效 '{s}'，应为 YYYY-MM-DDTHH:MM"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if (args.start is None) != (args.end is None):
        err = {"error": "--start 与 --end 必须同时提供"}
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    try:
        if args.start:
            result = fetch_live_between(
                start_dt=_parse_dt(args.start, "--start"),
                end_dt=_parse_dt(args.end, "--end"),
                score=args.score,
                limit=args.limit,
                verbose=args.verbose,
            )
        else:
            if args.date:
                try:
                    target = datetime.strptime(args.date, "%Y-%m-%d")
                except ValueError:
                    err = {"error": f"日期格式无效 '{args.date}'，应为 YYYY-MM-DD"}
                    print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
                    sys.exit(1)
            else:
                target = datetime.now(CST)
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
