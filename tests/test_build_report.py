"""
测试 build_report 模块（工具函数 + build_report 核心逻辑）。
"""

import json
import re
from pathlib import Path
from typing import Any

from news_tools.build_report import (
    _fmt_short,
    _fmt_comma,
    _fmt_weekly,
    _highlight_summary,
    _build_item_block,
    build_report,
)

# ═══════════════════════════════════════════════════════════════════
# _fmt_short
# ═══════════════════════════════════════════════════════════════════


def test_fmt_short_million():
    assert _fmt_short(1_234_567) == "1.2M"
    assert _fmt_short(10_000_000) == "10.0M"


def test_fmt_short_thousand():
    assert _fmt_short(15_894) == "15.9k"
    assert _fmt_short(1_000) == "1.0k"
    assert _fmt_short(999) == "999"


def test_fmt_short_zero():
    assert _fmt_short(0) == "0"


# ═══════════════════════════════════════════════════════════════════
# _fmt_comma
# ═══════════════════════════════════════════════════════════════════


def test_fmt_comma():
    assert _fmt_comma(15894) == "15,894"
    assert _fmt_comma(1000) == "1,000"
    assert _fmt_comma(0) == "0"
    assert _fmt_comma(1_000_000) == "1,000,000"


# ═══════════════════════════════════════════════════════════════════
# _fmt_weekly
# ═══════════════════════════════════════════════════════════════════


def test_fmt_weekly():
    assert _fmt_weekly(13308) == "+13,308"
    assert _fmt_weekly(0) == "+0"
    assert _fmt_weekly(500) == "+500"
    assert _fmt_weekly(1_000_000) == "+1,000,000"


# ═══════════════════════════════════════════════════════════════════
# _highlight_summary
# ═══════════════════════════════════════════════════════════════════


def test_highlight_summary_digits():
    """数字应该被 <span class='hl'> 包裹。"""
    result = _highlight_summary("本周有 12345 个项目，涵盖 AI 等领域。")
    assert '<span class="hl">12345</span>' in result


def test_highlight_summary_fields():
    """涵盖后面的领域关键词应该被 <strong> 加粗（含末尾空格分隔符）。"""
    result = _highlight_summary("涵盖 AI · ML · 云计算 等领域")
    assert "<strong>AI </strong>" in result
    assert "<strong>ML </strong>" in result
    assert "<strong>云计算</strong>" in result


def test_highlight_summary_empty():
    assert _highlight_summary("") == ""


def test_highlight_summary_no_match():
    """没有数字或领域时，原样返回。"""
    text = "本周趋势平稳。"
    assert _highlight_summary(text) == text


# ═══════════════════════════════════════════════════════════════════
# _build_item_block
# ═══════════════════════════════════════════════════════════════════


def _make_repo(overrides: dict[str, Any] = None) -> dict:
    default = {
        "author": "testuser",
        "name": "test-repo",
        "url": "https://github.com/testuser/test-repo",
        "description": "A test repository",
        "language": "Python",
        "language_color": "#3572A5",
        "stars_total": 1234,
        "stars_today": 56,
        "forks": 99,
        "zh_desc": "一个测试仓库",
        "features": ["功能A", "功能B", "功能C"],
        "audience": "开发者、技术爱好者",
    }
    if overrides:
        default.update(overrides)
    return default


def test_build_item_block_basic():
    """验证基本 HTML 结构正确。"""
    r = _make_repo()
    html = _build_item_block(r, 1, "avatar")
    assert 'id="repo-01"' in html
    assert "testuser" in html
    assert "test-repo" in html
    assert "https://github.com/testuser/test-repo" in html
    assert "Python" in html
    assert "1,234" in html  # stars_total 逗号格式化
    assert "+56" in html  # stars_today
    assert "99" in html  # forks
    assert "一个测试仓库" in html
    assert "功能A" in html
    assert "开发者、技术爱好者" in html
    assert "avatar/testuser.png" in html


def test_build_item_block_rank_format():
    """验证不同排名编号（两位数）。"""
    r = _make_repo()
    html = _build_item_block(r, 12, "avatar")
    assert 'id="repo-12"' in html


def test_build_item_block_missing_fields():
    """缺失可选字段时应有合理的 fallback。"""
    r = _make_repo(
        {
            "zh_desc": "",
            "features": [],
            "audience": "",
            "language": None,
            "language_color": None,
        }
    )
    html = _build_item_block(r, 1, "avatar")
    # zh_desc fallback → description
    assert "A test repository" in html
    # language fallback → 破折号
    assert "—" in html


# ═══════════════════════════════════════════════════════════════════
# build_report（集成测试）
# ═══════════════════════════════════════════════════════════════════


def _make_template() -> str:
    """生成一个最小可用模板用于测试。"""
    return """<!DOCTYPE html>
<html>
<head><title>{{WEEK_LABEL}}</title></head>
<body>
{{SIDEBAR}}
<nav class="index-nav">{{REPO_INDEX}}</nav>
<main>
<h1>{{WEEK_LABEL}}</h1>
<p>{{WEEK_INFO}}</p>
<p>{{REPO_COUNT}}个项目</p>
<p class="cover-summary">{{COVER_SUMMARY}}</p>
<table><tbody>{{RANK_TABLE_ROWS}}</tbody></table>
<section class="repo-section">{{REPO_ITEMS}}</section>
</main>
</body>
</html>"""


def test_build_report_creates_file(tmp_path):
    """验证 build_report 能正确生成文件。"""
    template = tmp_path / "template.html"
    template.write_text(_make_template(), encoding="utf-8")

    out_dir = tmp_path / "output"
    enriched = {
        "total_count": 3,
        "cover_summary": "本周有 3 个项目，涵盖 AI 等领域。",
        "repos": [
            {
                "author": "user1",
                "name": "repo1",
                "url": "https://github.com/user1/repo1",
                "language": "Python",
                "language_color": "#3572A5",
                "stars_total": 1500,
                "stars_today": 30,
                "forks": 100,
                "zh_desc": "项目一",
                "features": ["特点A1", "特点A2", "特点A3"],
                "audience": "开发者",
            },
            {
                "author": "user2",
                "name": "repo2",
                "url": "https://github.com/user2/repo2",
                "language": "Rust",
                "language_color": "#DEA584",
                "stars_total": 999,
                "stars_today": 10,
                "forks": 50,
                "zh_desc": "项目二",
                "features": ["特点B1", "特点B2", "特点B3"],
                "audience": "系统程序员",
            },
        ],
    }

    result_path = build_report(
        enriched=enriched,
        template_path=str(template),
        output_dir=str(out_dir),
        avatar_dir_name="avatar",
        download_avatars=False,
    )

    # 验证文件存在
    result_file = Path(result_path)
    assert result_file.exists()

    html = result_file.read_text(encoding="utf-8")

    # 验证模板占位符被正确替换
    assert "{{WEEK_LABEL}}" not in html
    assert "{{WEEK_INFO}}" not in html
    assert "{{REPO_COUNT}}" not in html
    assert "{{COVER_SUMMARY}}" not in html
    assert "{{RANK_TABLE_ROWS}}" not in html
    assert "{{REPO_ITEMS}}" not in html
    assert "{{REPO_INDEX}}" not in html
    assert "{{SIDEBAR}}" in html  # 保留给 build_site.py

    # 验证内容
    assert "2个项目" in html  # REPO_COUNT
    assert "repo1" in html
    assert "repo2" in html
    assert "user1" in html
    assert "user2" in html
    assert "项目一" in html
    assert "项目二" in html
    assert "Python" in html
    assert "Rust" in html
    assert "1.5k" in html  # stars_total formatted
    assert "999" in html  # stars_total < 1000
    assert "+30" in html  # stars_today
    assert "+10" in html

    # 验证 RANK_TABLE_ROWS 被正确生成（仅前10）
    assert '<span class="author"> / user1</span>' in html
    assert '<span class="author"> / user2</span>' in html

    # 验证索引
    assert 'href="#repo-01"' in html
    assert 'href="#repo-02"' in html


def test_build_report_empty_repos(tmp_path):
    """没有仓库时也能正常生成。"""
    template = tmp_path / "template.html"
    template.write_text(_make_template(), encoding="utf-8")

    out_dir = tmp_path / "output-empty"
    enriched = {
        "total_count": 0,
        "cover_summary": "本周无数据",
        "repos": [],
    }

    result_path = build_report(
        enriched=enriched,
        template_path=str(template),
        output_dir=str(out_dir),
        download_avatars=False,
    )

    html = Path(result_path).read_text(encoding="utf-8")
    assert "0个项目" in html
    assert "{{REPO_ITEMS}}" not in html


def test_build_report_no_cover_summary(tmp_path):
    """无 cover_summary 时也可以正常生成。"""
    template = tmp_path / "template.html"
    template.write_text(_make_template(), encoding="utf-8")

    out_dir = tmp_path / "output-nosummary"
    enriched = {
        "repos": [
            {
                "author": "u1",
                "name": "r1",
                "url": "https://github.com/u1/r1",
                "stars_total": 100,
                "stars_today": 5,
                "forks": 10,
            }
        ],
    }

    result_path = build_report(
        enriched=enriched,
        template_path=str(template),
        output_dir=str(out_dir),
        download_avatars=False,
    )

    html = Path(result_path).read_text(encoding="utf-8")
    assert "1个项目" in html
