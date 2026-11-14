"""
测试华尔街见闻三栏目聚合逻辑（纯逻辑测试，不触发网络请求）。

覆盖：
- find_section_items：栏目标题匹配
- parse_content_points：正文要点解析
- wallstreet_sections.section_window：时间窗计算
- wallstreet_sections.load/save_daily_file：同日多栏目合并、重复覆盖
- wallstreet_sections.build_wallstreet_summary：分组摘要
"""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from news_tools.wallstreet import (
    LiveItem,
    find_section_items,
    parse_content_points,
    SECTION_PATTERNS,
)
from news_tools.wallstreet_sections import (
    SECTION_ORDER,
    SECTION_LABELS,
    section_window,
    cst_date_of,
    is_weekday,
    load_daily_file,
    save_daily_file,
    build_wallstreet_summary,
)

CST = timezone(timedelta(hours=8))


def make_item(
    item_id: int, title: str, display_time: int, content: str = "", content_text: str = ""
) -> LiveItem:
    """构造测试用 LiveItem。"""
    return LiveItem(
        id=item_id,
        display_time=display_time,
        content_text=content_text,
        content=content,
        title=title,
        highlight_title=title,
        score=3,
        type="live",
        uri=f"https://wallstreetcn.com/livenews/{item_id}",
        is_calendar=False,
        channels=["global-channel"],
        cover_images=[],
        symbols=[],
        tags=[],
        reference="",
    )


# ── find_section_items ───────────────────────────────────────────────


def test_section_patterns():
    assert SECTION_PATTERNS["breakfast"] == "华尔街见闻早餐"
    assert SECTION_PATTERNS["morning"] == "早间要闻汇总"
    assert SECTION_PATTERNS["premarket"] == "美股盘前"


def test_find_breakfast_prefix_match():
    items = [
        make_item(1, "华尔街见闻早餐 | 2026年6月26日", 100),
        make_item(2, "普通快讯", 200),
        make_item(3, "华尔街见闻早餐FM-Radio | 2026年6月26日", 300),
    ]
    hits = find_section_items(items, "breakfast")
    assert len(hits) == 2
    # 按 display_time 降序
    assert [h.id for h in hits] == [3, 1]


def test_find_morning_exact_match():
    items = [
        make_item(1, "早间要闻汇总", 100),
        make_item(2, "早间要闻汇总 副标题", 200),  # 前缀但非精确，不应命中
        make_item(3, "早间要闻", 300),
    ]
    hits = find_section_items(items, "morning")
    assert len(hits) == 1
    assert hits[0].id == 1


def test_find_premarket_contains_match():
    items = [
        make_item(1, "周三美股盘前你需要了解的全球要闻", 100),
        make_item(2, "美股盘前：今日关注", 200),
        make_item(3, "美股盘后总结", 300),
    ]
    hits = find_section_items(items, "premarket")
    assert len(hits) == 2
    assert hits[0].id == 2  # 最新（display_time 更大）


def test_find_no_match_unknown_section():
    items = [make_item(1, "华尔街见闻早餐 | 2026年6月26日", 100)]
    assert find_section_items(items, "unknown") == []


# ── parse_content_points ─────────────────────────────────────────────


def test_parse_ul_li_content():
    content = (
        "<ul>\n"
        "<li>苹果微软拖累，标普500指数收平。<br/></li>\n"
        "<li>霍尔木兹海峡再起波澜。<br/></li>\n"
        "</ul>\n"
    )
    points = parse_content_points(content)
    assert points == ["苹果微软拖累，标普500指数收平。", "霍尔木兹海峡再起波澜。"]


def test_parse_plain_content_text():
    points = parse_content_points("", "第一行\n第二行\n第三行")
    assert points == ["第一行", "第二行", "第三行"]


def test_parse_empty():
    assert parse_content_points("", "") == []
    assert parse_content_points(None, "") == []


# ── section_window ───────────────────────────────────────────────────


def test_section_windows():
    start, end = section_window("breakfast", "2026-08-05")
    assert (start.hour, start.minute, end.hour, end.minute) == (0, 0, 8, 0)
    assert start.tzinfo is not None

    # 上游早间汇总偶发 12:35 才发，窗口留到 13:30
    start, end = section_window("morning", "2026-08-05")
    assert (start.hour, end.hour, end.minute) == (8, 13, 30)

    # 美国夏令时结束后盘前漂到 22:00 之后，窗口留到 23:30
    start, end = section_window("premarket", "2026-08-05")
    assert (start.hour, start.minute) == (13, 0)
    assert (end.hour, end.minute) == (23, 30)

    # 三段窗口首尾相接（morning 与 premarket 有意重叠 30 分钟兜底）
    b_start, b_end = section_window("breakfast", "2026-08-05")
    m_start, m_end = section_window("morning", "2026-08-05")
    p_start, p_end = section_window("premarket", "2026-08-05")
    assert b_end == m_start
    assert m_start <= p_start <= m_end <= p_end
    assert (m_end - p_start).total_seconds() == 30 * 60


def test_section_window_invalid():
    try:
        section_window("unknown", "2026-08-05")
        assert False, "应抛出 ValueError"
    except ValueError:
        pass


# ── load / save daily file ───────────────────────────────────────────


def test_save_daily_merges_sections():
    """同一日期先写 breakfast 再写 morning，最终文件包含两者且顺序固定。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)

        data1 = load_daily_file(data_dir, "2026-08-05")
        data1["sections"]["breakfast"] = {
            "title": "华尔街见闻早餐 | 2026年8月5日",
            "uri": "https://wallstreetcn.com/livenews/1",
            "fetched_at": "2026-08-05T07:30:00+08:00",
            "points": ["a", "b"],
        }
        save_daily_file(data_dir, "2026-08-05", data1)

        data2 = load_daily_file(data_dir, "2026-08-05")
        data2["sections"]["morning"] = {
            "title": "早间要闻汇总",
            "uri": "https://wallstreetcn.com/livenews/2",
            "fetched_at": "2026-08-05T12:30:00+08:00",
            "points": ["c", "d", "e"],
        }
        save_daily_file(data_dir, "2026-08-05", data2)

        saved = json.loads((data_dir / "2026-08-05.json").read_text(encoding="utf-8"))
        assert list(saved["sections"].keys()) == ["breakfast", "morning"]
        assert saved["count"] == 2
        assert saved["sections"]["breakfast"]["points"] == ["a", "b"]


def test_save_daily_overwrites_same_section():
    """重复更新同一栏目应覆盖而非叠加。"""
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)

        data1 = load_daily_file(data_dir, "2026-08-05")
        data1["sections"]["premarket"] = {"title": "旧", "points": ["x"]}
        save_daily_file(data_dir, "2026-08-05", data1)

        data2 = load_daily_file(data_dir, "2026-08-05")
        data2["sections"]["premarket"] = {"title": "新", "points": ["y", "z"]}
        save_daily_file(data_dir, "2026-08-05", data2)

        saved = json.loads((data_dir / "2026-08-05.json").read_text(encoding="utf-8"))
        assert saved["sections"]["premarket"]["title"] == "新"
        assert saved["sections"]["premarket"]["points"] == ["y", "z"]
        assert saved["count"] == 1


def test_load_daily_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        data = load_daily_file(Path(tmp), "2026-01-01")
        assert data["sections"] == {}
        assert data["count"] == 0


# ── 常量 ─────────────────────────────────────────────────────────────


def test_section_constants():
    assert SECTION_ORDER == ["breakfast", "morning", "premarket"]
    assert SECTION_LABELS["breakfast"] == "华尔街见闻早餐"


# ── build_site.build_wallstreet_summary ──────────────────────────────


def test_build_wallstreet_summary_labels():
    """验证首页摘要文案：早餐→见闻早餐，盘前→美股盘前。"""
    data = {
        "sections": {
            "breakfast": {"points": ["a"] * 14},
            "morning": {"points": ["b"] * 12},
            "premarket": {"points": ["c"] * 15},
        }
    }
    count, summary = build_wallstreet_summary(data)
    assert count == 3
    assert "见闻早餐 14 条" in summary
    assert "早间汇总 12 条" in summary
    assert "美股盘前 15 条" in summary


# ── is_weekday ───────────────────────────────────────────────────────


def test_is_weekday_workdays():
    # 2026-08-03 周一 / 08-05 周三 / 08-07 周五
    assert is_weekday("2026-08-03") is True
    assert is_weekday("2026-08-05") is True
    assert is_weekday("2026-08-07") is True


def test_is_weekday_weekends():
    # 2026-08-01 周六 / 08-02 周日 / 08-08 周六 / 08-09 周日
    assert is_weekday("2026-08-01") is False
    assert is_weekday("2026-08-02") is False
    assert is_weekday("2026-08-08") is False
    assert is_weekday("2026-08-09") is False


def test_cst_date_of():
    # 2026-08-05 07:00 CST == 2026-08-04 23:00 UTC，必须按 CST 归日
    ts = int(datetime(2026, 8, 5, 7, 0, tzinfo=CST).timestamp())
    assert cst_date_of(ts) == "2026-08-05"
    ts_prev = int(datetime(2026, 8, 4, 23, 59, tzinfo=CST).timestamp())
    assert cst_date_of(ts_prev) == "2026-08-04"


# ── wait_for_publish（等发布轮询）─────────────────────────────────────


def test_wait_for_publish_disabled_returns_none():
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import wallstreet_update as wu

    assert wu.wait_for_publish("premarket", "2026-11-13", wait_minutes=0) is None


def test_wait_for_publish_polls_until_appears():
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import wallstreet_update as wu

    pub = int(datetime(2026, 11, 13, 21, 52, tzinfo=CST).timestamp())
    item = make_item(1, "周五美股盘前你需要了解的全球要闻", pub)
    calls = {"n": 0}

    def fake_latest(limit=100, score=3):
        calls["n"] += 1
        return [] if calls["n"] < 3 else [item]

    orig_fetch, orig_sleep = wu.fetch_latest_page, wu.time.sleep
    wu.fetch_latest_page = fake_latest
    wu.time.sleep = lambda _s: None
    try:
        with redirect_stdout(io.StringIO()):
            hit = wu.wait_for_publish("premarket", "2026-11-13", wait_minutes=5, poll_seconds=1)
    finally:
        wu.fetch_latest_page, wu.time.sleep = orig_fetch, orig_sleep

    assert hit is not None and hit.id == 1
    assert calls["n"] == 3, f"应轮询到第 3 次才命中，实际 {calls['n']}"


def test_wait_for_publish_ignores_other_day():
    """上一交易日的同名条目不能被当成今天的。"""
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import wallstreet_update as wu

    yesterday = int(datetime(2026, 11, 12, 22, 0, tzinfo=CST).timestamp())
    item = make_item(2, "周四美股盘前你需要了解的全球要闻", yesterday)

    orig_fetch, orig_sleep = wu.fetch_latest_page, wu.time.sleep
    wu.fetch_latest_page = lambda limit=100, score=3: [item]
    wu.time.sleep = lambda _s: None
    try:
        with redirect_stdout(io.StringIO()):
            hit = wu.wait_for_publish("premarket", "2026-11-13", wait_minutes=0.02, poll_seconds=1)
    finally:
        wu.fetch_latest_page, wu.time.sleep = orig_fetch, orig_sleep

    assert hit is None


def test_is_weekday_invalid_returns_true():
    # 无法解析时保守放行（避免误拦截）
    assert is_weekday("") is True
    assert is_weekday("invalid") is True


# ── 主入口 ───────────────────────────────────────────────────────────


def main() -> None:
    tests = [
        (test_section_patterns, "栏目匹配常量"),
        (test_find_breakfast_prefix_match, "早餐前缀匹配"),
        (test_find_morning_exact_match, "早间汇总精确匹配"),
        (test_find_premarket_contains_match, "盘前包含匹配"),
        (test_find_no_match_unknown_section, "未知栏目无匹配"),
        (test_parse_ul_li_content, "HTML 要点解析"),
        (test_parse_plain_content_text, "纯文本要点解析"),
        (test_parse_empty, "空内容解析"),
        (test_section_windows, "时间窗计算"),
        (test_section_window_invalid, "时间窗非法栏目"),
        (test_save_daily_merges_sections, "同日多栏目 merge"),
        (test_save_daily_overwrites_same_section, "同栏目覆盖"),
        (test_load_daily_missing_file, "缺失文件骨架"),
        (test_section_constants, "栏目常量"),
        (test_build_wallstreet_summary_labels, "首页摘要文案"),
        (test_cst_date_of, "CST 日期归日"),
        (test_wait_for_publish_disabled_returns_none, "等发布（关闭时不等待）"),
        (test_wait_for_publish_polls_until_appears, "等发布（轮询命中）"),
        (test_wait_for_publish_ignores_other_day, "等发布（跨日不误判）"),
        (test_is_weekday_workdays, "工作日判断（工作日）"),
        (test_is_weekday_weekends, "工作日判断（周末）"),
        (test_is_weekday_invalid_returns_true, "工作日判断（非法日期放行）"),
    ]

    failed = 0
    for fn, name in tests:
        try:
            fn()
            print(f"  ✅ {name}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {name}: {e}")

    print(f"\n{'=' * 40}")
    print(f"通过 {len(tests) - failed}/{len(tests)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
