"""
测试 build_xwlb_html 模块（格式化工具函数）。
"""

from news_tools.build_xwlb_html import (
    _clean_xwlb_text,
    _extract_sub_titles,
    _clean_item_title,
    _render_content_as_html,
    _build_summary_html,
    _build_index_html,
    _build_items_html,
)

# ═══════════════════════════════════════════════════════════════════
# _clean_xwlb_text
# ═══════════════════════════════════════════════════════════════════


def test_clean_xwlb_text_remove_prefix():
    raw = "央视网消息（新闻联播）：这是正文内容。"
    assert _clean_xwlb_text(raw) == "这是正文内容。"


def test_clean_xwlb_text_remove_trailing_link():
    raw = "正文内容\n[央视网](https://tv.cctv.com)"
    assert _clean_xwlb_text(raw) == "正文内容"


def test_clean_xwlb_text_editor_info():
    raw = "正文内容\n编辑：张三  责任编辑：李四"
    assert _clean_xwlb_text(raw) == "正文内容"


def test_clean_xwlb_text_empty():
    assert _clean_xwlb_text("") == ""
    assert _clean_xwlb_text("   ") == ""


# ═══════════════════════════════════════════════════════════════════
# _extract_sub_titles
# ═══════════════════════════════════════════════════════════════════


def test_extract_sub_titles_express():
    title = "联播快讯（1）广东首发（2）北京启动"
    result = _extract_sub_titles(title)
    assert result == ["广东首发", "北京启动"]


def test_extract_sub_titles_no_match():
    assert _extract_sub_titles("普通新闻标题") == []


def test_extract_sub_titles_empty():
    assert _extract_sub_titles("") == []


# ═══════════════════════════════════════════════════════════════════
# _clean_item_title
# ═══════════════════════════════════════════════════════════════════


def test_clean_item_title_plain():
    assert (
        _clean_item_title("习近平主持召开中央深改委会议")
        == "习近平主持召开中央深改委会议"
    )


def test_clean_item_title_with_numbered():
    assert _clean_item_title("联播快讯（1）内容") == "联播快讯"


def test_clean_item_title_with_leading_number():
    """以数字开头的不匹配条件时原样返回。"""
    title = _clean_item_title("1.测试标题")
    # 函数逻辑：当没有括号编号时，返回整行，不做特殊处理
    assert isinstance(title, str)
    assert "1.测试标题" in title


def test_clean_item_title_empty():
    assert _clean_item_title("") == ""


# ═══════════════════════════════════════════════════════════════════
# _render_content_as_html
# ═══════════════════════════════════════════════════════════════════


def test_render_content_as_html_plain():
    content = "第一段\n第二段"
    html = _render_content_as_html(content, [])
    assert "<p>" in html
    assert "第一段" in html
    assert "第二段" in html


def test_render_content_as_html_express():
    content = "广东发布新政策。\n北京启动新项目。"
    sub_titles = ["广东发布新政策", "北京启动新项目"]
    html = _render_content_as_html(content, sub_titles)
    assert 'class="express-title"' in html


def test_render_content_as_html_empty():
    assert _render_content_as_html("", []) == ""


# ═══════════════════════════════════════════════════════════════════
# _build_summary_html
# ═══════════════════════════════════════════════════════════════════


def test_build_summary_html_basic():
    summary = (
        "本期节目主要内容：\n1、习近平重要讲话\n2、国务院常务会议\n（《新闻联播》..."
    )
    html = _build_summary_html(summary)
    assert 'class="summary-label"' in html
    assert "习近平重要讲话" in html
    assert "国务院常务会议" in html
    assert "《新闻联播》" not in html  # 跳过


def test_build_summary_html_empty():
    assert _build_summary_html("") == ""


# ═══════════════════════════════════════════════════════════════════
# _build_index_html
# ═══════════════════════════════════════════════════════════════════


def test_build_index_html():
    items = [
        {"title": "习近平主持召开中央深改委会议"},
        {"title": "联播快讯（1）广东（2）北京"},
    ]
    html = _build_index_html(items)
    assert 'href="#item-01"' in html
    assert 'href="#item-02"' in html
    assert "习近平" in html
    assert "联播快讯" in html
    assert '<span class="idx-num">01</span>' in html
    assert '<span class="idx-num">02</span>' in html


def test_build_index_html_empty():
    assert _build_index_html([]) == ""


# ═══════════════════════════════════════════════════════════════════
# _build_items_html
# ═══════════════════════════════════════════════════════════════════


def test_build_items_html():
    items = [
        {
            "title": "习近平重要讲话",
            "url": "https://tv.cctv.com/1",
            "content": "央视网消息（新闻联播）：中共中央总书记习近平...",
        },
    ]
    html = _build_items_html(items)
    assert 'id="item-01"' in html
    assert 'class="item-title"' in html
    assert "习近平重要讲话" in html
    assert "tv.cctv.com" in html
    assert "<p>" in html
    assert "中共中央总书记习近平" in html
    # 前缀被 _clean_xwlb_text 清除
    assert "央视网消息" not in html


def test_build_items_html_empty():
    assert _build_items_html([]) == ""
