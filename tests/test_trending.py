"""
测试 trending 模块（本地解析测试，不触发网络请求）。
"""

import json
from pathlib import Path

from news_tools.trending import (
    _parse_stars_count,
    _extract_language_color,
    parse_trending_page,
    TrendingResult,
)

# ── _parse_stars_count ──────────────────────────────────────────


def test_parse_stars_count_normal():
    assert _parse_stars_count("12.3k stars") == 12300


def test_parse_stars_count_thousands():
    assert _parse_stars_count("1,234 stars") == 1234


def test_parse_stars_count_plain():
    assert _parse_stars_count("450 stars today") == 450


def test_parse_stars_count_weekly():
    assert _parse_stars_count("2.1k stars this week") == 2100


def test_parse_stars_count_zero():
    assert _parse_stars_count("0 stars") == 0


def test_parse_stars_count_empty():
    assert _parse_stars_count("") == 0


def test_parse_stars_count_none():
    assert _parse_stars_count(None) == 0


# ── _extract_language_color ─────────────────────────────────────


def test_language_color_normal():
    assert _extract_language_color("background-color: #3572A5") == "#3572A5"


def test_language_color_none():
    assert _extract_language_color(None) is None


def test_language_color_empty():
    assert _extract_language_color("") is None


# ── parse_trending_page ─────────────────────────────────────────


def test_parse_trending_page_from_fixture():
    """使用本地 fixture HTML 文件测试解析逻辑。"""
    fixture_path = Path(__file__).parent / "fixtures" / "trending_sample.html"
    if not fixture_path.exists():
        # 无 fixture 时跳过（CI 环境可放置）
        return

    html = fixture_path.read_text(encoding="utf-8")
    repos = parse_trending_page(html)
    assert len(repos) > 0

    repo = repos[0]
    assert repo.author
    assert repo.name
    assert repo.url.startswith("https://github.com/")


# ── TrendingResult JSON 序列化 ──────────────────────────────────


def test_trending_result_json_serialization():
    """验证 TrendingResult 能正确序列化为 JSON。"""
    result = TrendingResult(
        period="daily",
        fetched_at="2026-05-29T12:00:00+08:00",
        total_count=0,
        repos=[],
    )
    data = json.loads(result.model_dump_json())
    assert data["source"] == "github_trending"
    assert data["period"] == "daily"
    assert data["total_count"] == 0
    assert data["repos"] == []
