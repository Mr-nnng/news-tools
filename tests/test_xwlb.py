"""
测试 xwlb 模块（本地解析测试，不触发网络请求）。
"""

import json
from datetime import datetime

from news_tools.xwlb import (
    XwlbItem,
    XwlbResult,
)

# ── XwlbItem JSON 序列化 ────────────────────────────────────────


def test_xwlb_item_json():
    """验证 XwlbItem 能正确序列化为 JSON。"""
    item = XwlbItem(
        title="习近平主持召开中央全面深化改革委员会第五次会议",
        url="https://tv.cctv.com/example",
        content="央视网消息（新闻联播）：中共中央总书记、国家主席、中央军委主席习近平...",
    )
    data = json.loads(item.model_dump_json())
    assert data["title"] == "习近平主持召开中央全面深化改革委员会第五次会议"
    assert data["url"] == "https://tv.cctv.com/example"
    assert "习近平" in data["content"]


# ── XwlbResult JSON 序列化 ─────────────────────────────────────


def test_xwlb_result_json():
    """验证新 XwlbResult 能正确序列化为 JSON（含 title 字段）。"""
    result = XwlbResult(
        title="5月29日周五《新闻联播》",
        date="2026-05-29",
        url="https://tv.cctv.com/xwlb",
        fetched_at=datetime.now().isoformat(),
        summary="1、习近平主持召开中央全面深化改革委员会第五次会议\n2、习近平向联合国贸易和发展会议成立60周年庆祝活动开幕式发表视频致辞\n3、xxx",
        items=[
            XwlbItem(
                title="习近平主持召开中央全面深化改革委员会第五次会议",
                url="https://tv.cctv.com/1",
                content="央视网消息（新闻联播）：中共中央总书记...",
            ),
            XwlbItem(
                title="习近平向联合国贸易和发展会议成立60周年庆祝活动开幕式发表视频致辞",
                url="https://tv.cctv.com/2",
                content="央视网消息（新闻联播）：6月29日...",
            ),
        ],
    )
    data = json.loads(result.model_dump_json())
    assert data["source"] == "xwlb"
    assert data["title"] == "5月29日周五《新闻联播》"
    assert data["date"] == "2026-05-29"
    assert data["summary"].startswith("1、习近平")
    assert len(data["items"]) == 2
    assert data["items"][0]["title"].startswith("习近平")
    assert data["items"][0]["url"] == "https://tv.cctv.com/1"
    assert data["items"][1]["title"].startswith("习近平")
    assert data["items"][1]["url"] == "https://tv.cctv.com/2"


# ── XwlbResult to_markdown ─────────────────────────────────


def test_xwlb_result_to_markdown():
    """验证 to_markdown() 输出格式正确。"""
    result = XwlbResult(
        title="5月29日周五《新闻联播》",
        date="2026-05-29",
        url="https://tv.cctv.com/xwlb",
        fetched_at="2026-05-29T19:20:00",
        summary="1、习近平主持召开中央全面深化改革委员会第五次会议\n2、习近平向联合国贸易和发展会议成立60周年庆祝活动开幕式发表视频致辞\n3、xxx",
        items=[
            XwlbItem(
                title="习近平主持召开中央全面深化改革委员会第五次会议",
                url="https://tv.cctv.com/1",
                content="央视网消息（新闻联播）：中共中央总书记...",
            ),
            XwlbItem(
                title="习近平向联合国贸易和发展会议成立60周年庆祝活动开幕式发表视频致辞",
                url="https://tv.cctv.com/2",
                content="央视网消息（新闻联播）：6月29日...",
            ),
        ],
    )
    md = result.to_markdown()

    # 应包含标题和元信息
    assert "# 5月29日周五《新闻联播》" in md
    assert "**来源**：" in md and "tv.cctv.com" in md
    assert "**日期**：2026-05-29" in md

    # 应包含摘要部分
    assert "## 摘要" in md
    assert "习近平主持召开中央全面深化改革委员会第五次会议" in md
    assert "习近平向联合国贸易和发展会议" in md

    # 应包含详细内容部分
    assert "## 详细内容" in md
    assert "### 1." in md
    assert "### 2." in md
    assert "习近平主持召开" in md
    assert "中共中央总书记" in md
    assert (
        "[习近平主持召开中央全面深化改革委员会第五次会议](https://tv.cctv.com/1)" in md
    )
    assert (
        "[习近平向联合国贸易和发展会议成立60周年庆祝活动开幕式发表视频致辞](https://tv.cctv.com/2)"
        in md
    )

    # 不应有空列表当 items 非空时
    assert "### 0." not in md
    assert "央视网消息" not in md  # 前缀已被去掉

    # 标题是点击链接
    assert "习近平主持召开" in md
    assert "tv.cctv.com" in md  # URL 在标题链接中

    # summary items 应保持原样（编号）
    assert md.index("1、习近平") < md.index("2、习近平")
