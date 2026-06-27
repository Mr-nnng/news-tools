"""
测试 wallstreet 模块（数据模型和 JSON 序列化测试）。
"""

import json

from news_tools.wallstreet import LiveItem, LiveResult


def test_live_item_serialization():
    """验证 LiveItem 能正确序列化为 JSON。"""
    item = LiveItem(
        id=3111525,
        display_time=1780066393,
        content_text="测试内容",
        content="<p>测试内容</p>",
        title="测试标题",
        highlight_title="",
        score=2,
        type="live",
        uri="https://wallstreetcn.com/livenews/3111525",
        is_calendar=False,
        channels=["global-channel"],
        cover_images=[],
        symbols=[],
        tags=[],
        reference="",
    )
    data = json.loads(item.model_dump_json())
    assert data["id"] == 3111525
    assert data["score"] == 2
    assert data["type"] == "live"


def test_live_result_json():
    """验证完整 LiveResult JSON 结构。"""
    result = LiveResult(
        date="2026-05-29",
        score=2,
        fetched_at="2026-05-29T22:00:00+08:00",
        total_count=1,
        items=[
            LiveItem(
                id=1,
                display_time=1780066393,
                content_text="test",
                content="<p>test</p>",
                title="",
                highlight_title="",
                score=2,
                type="live",
                uri="https://wallstreetcn.com/livenews/1",
                is_calendar=False,
                channels=[],
                cover_images=[],
                symbols=[],
                tags=[],
                reference="",
            ),
        ],
    )
    data = json.loads(result.model_dump_json())
    assert data["source"] == "wallstreet_live"
    assert data["date"] == "2026-05-29"
    assert len(data["items"]) == 1
