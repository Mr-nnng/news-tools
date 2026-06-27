"""
news_tools/build_xwlb_html.py — 从 XWLB JSON 生成新闻联播 HTML 页面

职责：
- 读取 xwlb.json（XwlbResult 格式）
- 读取 HTML 模板 assets/templates/xwlb-page.html
- 填充模板占位符
- 输出到 site/xwlb/{date}/index.html

用法：
    python -m news_tools.build_xwlb_html report/xwlb-2026-06-27/data/xwlb.json -o site/xwlb/2026-06-27

作为模块调用：
    from news_tools.build_xwlb_html import build_xwlb_page
    html_path = build_xwlb_page("report/xwlb-2026-06-27/data/xwlb.json", "site/xwlb/2026-06-27")
"""

import json
import re
import argparse
import sys
from pathlib import Path
from typing import Optional

# ── 项目根路径 ────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATE_PATH = _PROJECT_ROOT / "assets" / "templates" / "xwlb-page.html"


# ═══════════════════════════════════════════════════════════════════
# 格式化工具
# ═══════════════════════════════════════════════════════════════════


def _clean_xwlb_text(text: str) -> str:
    """清除固定前缀、尾部链接、编辑信息。"""
    cleaned = re.sub(r"^央视网消息\s*（新闻联播）\s*：\s*", "", text)
    cleaned = re.sub(r"\n*\[[^\]]*\]\([^)]*\)\s*$", "", cleaned)
    cleaned = re.sub(r"\n*编辑：.*?责任编辑：.*$", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _extract_sub_titles(title: str) -> list[str]:
    """从联播快讯类标题中提取子标题列表。

    例如: "联播快讯（1）广东…（2）北京…" → ["广东…", "北京…"]
    """
    if "联播快讯" not in title and "快讯" not in title:
        return []
    parts = re.split(r"[（\(]\d+[）\)]", title)
    sub_titles = []
    for p in parts[1:]:
        t = p.strip().rstrip("；;。，, \n\r")
        if t:
            sub_titles.append(t)
    return sub_titles


def _clean_item_title(raw_title: str) -> str:
    """从原始标题中提取纯净主标题。"""
    first_line = raw_title.splitlines()[0].strip() if raw_title else ""
    match = re.search(r"[（\(]\d+[）\)]|^\d+\.", first_line)
    if match:
        main_title = first_line[: match.start()].strip()
    else:
        main_title = first_line
    return main_title.rstrip("：:。，, \n\r") or first_line


def _render_content_as_html(content: str, sub_titles: list[str]) -> str:
    """将新闻正文渲染为 HTML 段落。

    对于联播快讯类，子标题加粗渲染为缩进列表。
    普通新闻每行独立一段（每个 <p> 都享受 text-indent）。
    """
    cleaned = _clean_xwlb_text(content)
    if not cleaned:
        return ""

    if sub_titles:
        return _render_express_as_html(cleaned, sub_titles)

    # 普通新闻：每个换行都切为独立段落，保证每个 <p> 首行缩进
    lines = cleaned.split("\n")
    html_parts = []
    for line in lines:
        line = line.strip()
        if line:
            html_parts.append(f"      <p>\n        {line}\n      </p>")
    return "\n".join(html_parts)


def _render_express_as_html(text: str, sub_titles: list[str]) -> str:
    """将联播快讯类正文渲染为带子标题缩进结构的 HTML。

    子标题匹配优先级：精确匹配 → 去除前导编号后匹配。
    """
    clean_titles = [re.sub(r"[\uff1b;。，,\s]+$", "", t) for t in sub_titles]
    clean_titles = [t for t in clean_titles if t]

    lines = text.split("\n")
    html_parts: list[str] = []
    current_title: Optional[str] = None
    current_bodies: list[str] = []

    def _flush():
        nonlocal current_title, current_bodies
        if current_title:
            body_html = ""
            for b in current_bodies:
                if b.strip():
                    body_html += f'        <div class="express-body">{b.strip()}</div>\n'
            if body_html:
                html_parts.append(
                    f'      <p><span class="express-title">{current_title}</span></p>\n{body_html}'
                )
            else:
                html_parts.append(f'      <p><span class="express-title">{current_title}</span></p>')
            current_title = None
            current_bodies = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        matched = None
        for t in clean_titles:
            if stripped == t or stripped.startswith(t):
                matched = t
                break
            no_num = re.sub(r"^[（\(]?\d+[）\)]\s*", "", stripped)
            if no_num == t or no_num.startswith(t):
                matched = t
                break

        if matched:
            _flush()
            current_title = matched
            rest = stripped[len(matched):].strip()
            rest = re.sub(r"^[。：:\s]+", "", rest)
            if rest:
                current_bodies.append(rest)
        else:
            if current_title:
                current_bodies.append(stripped)
            else:
                html_parts.append(f"      <p>{stripped}</p>")

    _flush()

    return "\n".join(html_parts) if html_parts else ""


def _build_summary_html(summary_text: str) -> str:
    """将摘要文本（行分隔）渲染为 HTML。

    特殊行处理：
    - "本期节目主要内容：" → 摘要标签（summary-label）
    - "国内联播快讯：" / "国际联播快讯：" → 类别标签（summary-label）
    - "（《新闻联播》..." → 来源注脚（summary-source）
    - 其余 → <li> 项目
    """
    if not summary_text:
        return ""

    lines = summary_text.replace("\r\n", "\n").strip().split("\n")
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # "本期节目主要内容：" 作为标签
        if stripped.startswith("本期节目主要内容"):
            parts.append(f'      <div class="summary-label">{stripped}</div>')
        # "联播快讯" 类别标签
        elif "联播快讯" in stripped:
            cleaned = re.sub(r"^\d+[.、]\s*", "", stripped)
            parts.append(f'      <div class="summary-label">{cleaned}</div>')
        # "（《新闻联播》..." 跳过，不显示
        elif stripped.startswith("（《新闻联播》") or stripped.startswith("(《新闻联播》"):
            continue
        # "（..." 开头的都是子项
        elif stripped.startswith("（") or stripped.startswith("("):
            parts.append(f'      <li class="summary-subitem">{stripped}</li>')
        # 其他项目
        else:
            cleaned = re.sub(r"^\d+[.、]\s*", "", stripped)
            parts.append(f"      <li>{cleaned}</li>")
    return "\n".join(parts)


def _build_index_html(items: list[dict]) -> str:
    """生成新闻标题索引（可点击跳转）。"""
    parts = []
    for i, item in enumerate(items, 1):
        raw_title = item.get("title", "")
        clean_title = _clean_item_title(raw_title)
        # Truncate very long titles for the index
        if len(clean_title) > 60:
            display_title = clean_title[:58] + "…"
        else:
            display_title = clean_title
        parts.append(
            f'      <a class="index-item" href="#item-{i:02d}">'
            f'<span class="idx-num">{i:02d}</span> {display_title}</a>'
        )
    return "\n".join(parts)


def _build_items_html(items: list[dict]) -> str:
    """将 items 列表渲染为新闻详情区块 HTML。

    每条新闻包含编号、标题（链接）、正文（支持联播快讯子标题）。
    """
    html_parts = []
    for i, item in enumerate(items, 1):
        raw_title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")

        clean_title = _clean_item_title(raw_title)
        sub_titles = _extract_sub_titles(raw_title)
        content_html = _render_content_as_html(content, sub_titles)

        if not content_html:
            content_html = "      <p>（暂无详细文字内容）</p>"

        title_html = f'<a href="{url}" target="_blank" rel="noopener">{clean_title}</a>' if url else clean_title

        html_parts.append(
                f"""    <div class="news-item" id="item-{i:02d}">
          <div class="item-number">第 {i:02d} 条</div>
          <h3 class="item-title">{title_html}</h3>
          <div class="item-content">
    {content_html}
          </div>
        </div>"""
            )

    return "\n".join(html_parts)


# ═══════════════════════════════════════════════════════════════════
# 主构建函数
# ═══════════════════════════════════════════════════════════════════


def build_xwlb_page(
    json_path: str,
    output_dir: str,
    template_path: Optional[str] = None,
) -> str:
    """从 xwlb.json 生成新闻联播 HTML 页面。

    Args:
        json_path: xwlb.json 文件路径
        output_dir: 输出目录（如 site/xwlb/2026-06-27）
        template_path: 模板路径（默认 assets/templates/xwlb-page.html）

    Returns:
        生成的 HTML 文件绝对路径
    """
    # ── 读取 JSON ───────────────────────────────────────────
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ── 填充模板 ────────────────────────────────────────────
    if template_path is None:
        template_path = str(_TEMPLATE_PATH)
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Title
    title = data.get("title", "")
    html = html.replace("{{XWLB_TITLE}}", title)

    # Date
    date_str = data.get("date", "")
    html = html.replace("{{XWLB_DATE}}", date_str)

    # URL
    url = data.get("url", "")
    html = html.replace("{{XWLB_URL}}", url)

    # Item count
    items = data.get("items", [])
    item_count = str(len(items))
    html = html.replace("{{XWLB_ITEM_COUNT}}", item_count)

    # Summary
    summary = data.get("summary", "")
    summary_html = _build_summary_html(summary)
    html = html.replace("{{XWLB_SUMMARY}}", summary_html)

    # Items detail
    items_html = _build_items_html(items)
    html = html.replace("{{XWLB_ITEMS}}", items_html)

    # News index (clickable titles)
    index_html = _build_index_html(items)
    html = html.replace("{{XWLB_INDEX}}", index_html)

    # Sidebar placeholder — kept as {{SIDEBAR}} for build_site.py to inject
    pass

    # ── 写入输出 ────────────────────────────────────────────
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    return str(out_path)


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="从 xwlb.json 生成新闻联播 HTML 页面",
    )
    parser.add_argument("json_path", help="xwlb.json 文件路径")
    parser.add_argument("-o", "--output-dir", default=None, help="输出目录（默认与 JSON 同目录的上级）")
    parser.add_argument("--template", default=None, help="HTML 模板路径（默认 assets/templates/xwlb-page.html）")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}", file=sys.stderr)
        sys.exit(1)

    if args.output_dir:
        out_dir = args.output_dir
    else:
        # 默认：JSON 所在目录的父目录 → 如 report/xwlb-2026-06-27/
        out_dir = str(json_path.parent.parent)

    print(f"📄 生成新闻联播 HTML...")
    out = build_xwlb_page(
        json_path=str(json_path),
        output_dir=out_dir,
        template_path=args.template,
    )
    print(f"✅ HTML 已生成: {out}")


if __name__ == "__main__":
    main()
