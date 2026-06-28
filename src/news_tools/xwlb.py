"""
news_tools/xwlb.py — 新闻联播文字摘要获取工具

通过直接请求央视网 API/HTML 获取每日新闻联播内容，输出 JSON。

用法:
    python -m news_tools.xwlb                          # 今天（或昨天）的摘要
    python -m news_tools.xwlb --date 2026-05-29        # 指定日期
    python -m news_tools.xwlb --date 2026-05-29 -o xwlb.json
    python -m news_tools.xwlb --compact                # 仅输出 items 数组
    python -m news_tools.xwlb --markdown               # Markdown 格式输出
    python -m news_tools.xwlb --date 2026-05-29 --md -o xwlb.md

作为模块调用:
    from news_tools.xwlb import get_xwlb
    result = get_xwlb(2026, 5, 29)
    print(result.model_dump_json(indent=2, ensure_ascii=False))
    print(result.to_markdown())                        # 格式化为 Markdown
"""

import re
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════


class DetailItem(BaseModel):
    """单条新闻/视频信息"""

    name: str
    href: str
    index: int


class XwlbItem(BaseModel):
    """单条新闻内容（含标题、链接、正文）"""

    title: str
    url: str
    content: str


class XwlbResult(BaseModel):
    """新闻联播结果（JSON 顶层结构）"""

    source: str = "xwlb"
    title: str = ""  # 如 "5月30日周六《新闻联播》"
    date: str  # YYYY-MM-DD
    fetched_at: str  # ISO 8601
    url: str  # 央视网新闻联播完整版 URL
    summary: str  # 完整版编号摘要，以换行符连接
    items: list[XwlbItem]  # 独立新闻条目列表

    @staticmethod
    def _clean_xwlb_text(text: str) -> str:
        """清除固定前缀、尾部链接、编辑信息。"""
        cleaned = re.sub(r"^央视网消息\s*（新闻联播）\s*：\s*", "", text)
        cleaned = re.sub(r"\n*\[[^\]]*\]\([^)]*\)\s*$", "", cleaned)
        cleaned = re.sub(r"\n*编辑：.*?责任编辑：.*$", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _render_normal_news(text: str) -> str:
        """将普通正文中的单换行转为双换行，适配 Markdown 段落分隔。"""
        return re.sub(r"\n+", "\n\n", text)

    @staticmethod
    def _match_line_to_subtitle(
        line: str, titles: list[str]
    ) -> tuple[Optional[str], str]:
        """尝试将一行匹配到某个子标题。

        返回 (matched_title, rest_text)，无匹配时 (None, '')。
        匹配时先尝试精确/前缀匹配，再试去除前导编号后的匹配。
        """
        stripped = line.strip()
        for t in titles:
            if stripped == t or stripped.startswith(t):
                return t, stripped[len(t) :].strip()
            no_num = re.sub(r"^[（\(]?\d+[）\)]?\s*", "", stripped)
            if no_num == t or no_num.startswith(t):
                return t, no_num[len(t) :].strip()
        return None, ""

    @staticmethod
    def _render_express_news(text: str, sub_titles: list[str]) -> str:
        """将联播快讯格式化为 Markdown 列表。

        子标题作为列表项 ``- {title}``，说明正文缩进 4 空格。
        """
        clean_titles = [re.sub(r"[\uff1b;。，,\s]+$", "", t) for t in sub_titles]
        clean_titles = [t for t in clean_titles if t]

        lines = text.split("\n")
        result_md: list[str] = []
        pending: list[str] = []

        def _flush_pending() -> None:
            if not pending:
                return
            formatted = "\n\n    ".join(pending)
            result_md.append(f"    {formatted}")
            result_md.append("")
            pending.clear()

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            matched_title, rest_text = XwlbResult._match_line_to_subtitle(
                stripped, clean_titles
            )
            if matched_title:
                _flush_pending()
                result_md.append(f"- {matched_title}")
                result_md.append("")
                rest_text = re.sub(r"^[。：:\s]+", "", rest_text)
                if rest_text:
                    pending.append(rest_text)
            else:
                if pending or result_md:
                    pending.append(stripped)
                else:
                    result_md.append(stripped)
                    result_md.append("")

        _flush_pending()

        while result_md and not result_md[-1].strip():
            result_md.pop()

        return "\n".join(result_md) if result_md else ""

    def _format_content_for_md(self, content: str, sub_titles: list[str] = None) -> str:
        """清洗并格式化新闻正文，适配 Markdown 展示。"""
        cleaned = self._clean_xwlb_text(content)
        if not cleaned:
            return ""

        if sub_titles:
            rendered = self._render_express_news(cleaned, sub_titles)
            if rendered:
                return rendered

        return self._render_normal_news(cleaned)

    def to_markdown(self) -> str:
        """生成格式化的 Markdown 文本。"""
        lines: list[str] = []

        # title
        lines.append(f"# {self.title}\n")

        # metadata
        lines.append(f"> **来源**：[央视网]({self.url}) | **日期**：{self.date}\n")

        # summary
        if self.summary:
            lines.append("## 摘要\n")
            # 摘要保持原有的单换行列表结构，仅规范化换行符
            formatted_summary = self.summary.replace("\r\n", "\n").strip()
            lines.append(formatted_summary)
            lines.append("\n")

        # detailed news items
        if self.items:
            lines.append("## 详细内容\n")
            for i, item in enumerate(self.items, 1):
                # 1. 提取主标题和子标题
                raw_title = item.title.splitlines()[0].strip() if item.title else ""

                # 截断处理：在 "（1）" 或 "1." 处截断，获取纯净的主标题
                match = re.search(r"[（\(]\d+[）\)]|^\d+\.", raw_title)
                if match:
                    main_title = raw_title[: match.start()].strip()
                else:
                    main_title = raw_title

                clean_title = main_title.rstrip("：:。，, \n\r")
                if not clean_title:
                    clean_title = raw_title

                # 提取子标题（用于联播快讯）
                sub_titles = []
                if "联播快讯" in item.title or "快讯" in item.title:
                    parts = re.split(r"[（\(]\d+[）\)]", item.title)
                    for p in parts[1:]:
                        t = p.strip().rstrip("；;。，, \n\r")
                        if t:
                            sub_titles.append(t)

                # 2. 生成带链接的标题
                lines.append(f"### {i}. [{clean_title}]({item.url})\n")

                # 3. 格式化正文
                if item.content:
                    _content = self._format_content_for_md(item.content, sub_titles)
                    lines.append(_content)
                    lines.append("")

                if i < len(self.items):
                    lines.append("")

        return "\n".join(lines)


# ─── 公共 HTTP 头 ────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://tv.cctv.com/lm/xwlb/index.shtml",
}


# 星期映射（datetime.weekday(): 0=周一 ... 6=周日）
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ═══════════════════════════════════════════════════════════════════
# 获取视频列表
# ═══════════════════════════════════════════════════════════════════


def get_video_list_by_date(year: int, month: int, day: int) -> list[DetailItem]:
    """获取指定日期的新闻联播视频列表。"""
    date_str = f"{year:04d}{month:02d}{day:02d}"
    url = f"https://tv.cctv.com/lm/xwlb/day/{date_str}.shtml"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    lis = soup.find_all("li")

    details: list[DetailItem] = []
    for i, li in enumerate(lis):
        a_tag = li.find("a")
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        if not href or "tv.cctv.com" not in href:
            continue
        title = a_tag.get("title", "").strip() or a_tag.get_text(strip=True)
        title = re.sub(r"\s+", " ", title)
        details.append(DetailItem(name=title, href=href, index=i))

    return details


# ═══════════════════════════════════════════════════════════════════
# 页面内容提取
# ═══════════════════════════════════════════════════════════════════


def _find_full_version(details: list[DetailItem]) -> Optional[DetailItem]:
    """从视频列表中找出《新闻联播》完整版条目。"""
    for d in details:
        if "《新闻联播》" in d.name and "完整版" in d.name:
            return d
    for d in details:
        if "新闻联播" in d.name:
            return d
    return details[0] if details else None


def _extract_page_text(url: str, solo: bool = True) -> tuple[str, str]:
    """从单个新闻联播视频详情页提取标题和纯文本内容。"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 提取标题 ──────────────────────────────────────────────
    title = ""
    if solo:
        brief = soup.select_one(".phone_content .video_brief")
        if brief:
            title = brief.get_text(strip=True)

    # ── 提取正文 ──────────────────────────────────────────────
    content_area = soup.select_one("#content .content_area")
    if solo and content_area:
        body = content_area.get_text(separator="\n", strip=True)
        zebian = soup.select_one("#content .zebian")
        if zebian:
            zb_text = zebian.get_text(separator=" ", strip=True)
            if zb_text:
                body = f"{body}\n\n{zb_text}"
        return title, body

    # 降级：完整版页面的摘要简介
    p_text: Optional[str] = None
    shadow = soup.select_one(".nrjianjie_shadow")
    if shadow:
        p_tag = shadow.select_one(".con li:first-child p")
        if p_tag:
            p_text = p_tag.get_text(separator="\n", strip=True)

    if not p_text:
        brief = soup.select_one(".phone_content .video_brief")
        if brief:
            p_text = brief.get_text(separator="\n", strip=True)

    return title, p_text or ""


# ═══════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════


def get_xwlb(year_num: int, month_num: int, day_num: int) -> Optional[XwlbResult]:
    """获取指定日期的《新闻联播》内容。"""
    details = get_video_list_by_date(year_num, month_num, day_num)
    if not details:
        return None

    full_entry = _find_full_version(details)
    individual_items = [d for d in details if d is not full_entry]

    summary = ""
    if full_entry:
        _, summary = _extract_page_text(full_entry.href, solo=False)

    items: list[XwlbItem] = []
    for item in individual_items:
        title, content = _extract_page_text(item.href)
        if not title:
            title = item.name
        items.append(
            XwlbItem(
                title=title,
                url=item.href,
                content=content,
            )
        )

    dt_local = datetime(year_num, month_num, day_num)
    weekday_str = WEEKDAY_NAMES[dt_local.weekday()]
    result_title = f"{month_num}月{day_num}日{weekday_str}《新闻联播》"

    return XwlbResult(
        source="xwlb",
        title=result_title,
        date=f"{year_num:04d}-{month_num:02d}-{day_num:02d}",
        fetched_at=datetime.now().isoformat(),
        url=full_entry.href if full_entry else "",
        summary=summary,
        items=items,
    )


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """CLI 入口函数。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="获取《新闻联播》文字摘要，输出 JSON。",
    )
    parser.add_argument(
        "--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认今天"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="输出文件路径（默认输出到终端）"
    )
    parser.add_argument(
        "--markdown", "--md", action="store_true", help="Markdown 格式输出（替代 JSON）"
    )
    parser.add_argument(
        "--compact", action="store_true", help="紧凑模式：仅输出 items 数组"
    )

    args = parser.parse_args()

    if args.date:
        try:
            dt = datetime.strptime(args.date, "%Y-%m-%d")
            year_num, month_num, day_num = dt.year, dt.month, dt.day
        except ValueError:
            err = {"error": f"日期格式无效 '{args.date}'，应为 YYYY-MM-DD"}
            print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
    else:
        today = datetime.now()
        year_num, month_num, day_num = today.year, today.month, today.day
        if today.hour < 19 or (today.hour == 19 and today.minute < 10):
            yesterday = datetime.fromtimestamp(time.time() - 86400)
            year_num, month_num, day_num = (
                yesterday.year,
                yesterday.month,
                yesterday.day,
            )

    result = get_xwlb(year_num, month_num, day_num)

    if result is None:
        err = {"error": f"{year_num}年{month_num}月{day_num}日暂无新闻联播数据"}
        print(json.dumps(err, ensure_ascii=False))
        sys.exit(1)

    if args.markdown:
        output_str = result.to_markdown()
    elif args.compact:
        data = [r.model_dump() for r in result.items]
        output_str = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        data = result.model_dump()
        output_str = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
            f.write("\n")
        print(
            json.dumps(
                {"status": "saved", "path": args.output, "count": len(result.items)},
                ensure_ascii=False,
            )
        )
    else:
        print(output_str)


if __name__ == "__main__":
    main()
