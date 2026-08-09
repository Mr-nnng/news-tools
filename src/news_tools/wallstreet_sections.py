"""
news_tools/wallstreet_sections.py — 华尔街见闻三栏目聚合逻辑

定义栏目常量、抓取时间窗、当日聚合文件的读取/合并/保存。
纯逻辑无网络请求，便于单元测试。

时间窗设计：三个栏目互补覆盖全天且互不重叠，末端留缓冲容忍发布延迟：
    breakfast  00:00~08:00  期望 07:25
    morning    08:00~13:00  期望 12:30
    premarket  13:00~22:00  期望 21:30 前
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

# score=3（最重要）——三个栏目均为重要级新闻，缩小抓取范围
SECTION_SCORE = 3

# 栏目顺序（固定展示顺序）
SECTION_ORDER: list[str] = ["breakfast", "morning", "premarket"]

# 栏目展示名
SECTION_LABELS: dict[str, str] = {
    "breakfast": "华尔街见闻早餐",
    "morning": "早间要闻汇总",
    "premarket": "美股盘前",
}

# 栏目 → 抓取时间窗（CST，小时，[start, end)）
SECTION_WINDOWS: dict[str, tuple[int, int]] = {
    "breakfast": (0, 8),
    "morning": (8, 13),
    "premarket": (13, 22),
}

# 首页卡片摘要用短标签
SECTION_SUMMARY_LABELS: dict[str, str] = {
    "breakfast": "见闻早餐",
    "morning": "早间汇总",
    "premarket": "美股盘前",
}


def build_wallstreet_summary(data: dict) -> tuple[int, str]:
    """华尔街见闻：返回 (栏目数, 栏目摘要)。

    摘要格式如 "见闻早餐 14 条 · 早间汇总 12 条 · 美股盘前 15 条"，缺失栏目跳过。
    """
    sections = data.get("sections", {}) or {}
    parts: list[str] = []
    for key in SECTION_ORDER:
        sec = sections.get(key)
        if not sec:
            continue
        n = len(sec.get("points", []))
        parts.append(f"{SECTION_SUMMARY_LABELS[key]} {n} 条")
    count = len(sections)
    if parts:
        return count, " · ".join(parts)
    return count, "今日暂无内容"


def section_window(section: str, date_str: str) -> tuple[datetime, datetime]:
    """计算栏目在指定日期的抓取时间窗（CST）。"""
    if section not in SECTION_WINDOWS:
        raise ValueError(f"未知栏目: {section}")
    start_h, end_h = SECTION_WINDOWS[section]
    y, m, d = (int(x) for x in date_str.split("-"))
    start = datetime(y, m, d, start_h, 0, tzinfo=CST)
    end = datetime(y, m, d, end_h, 0, tzinfo=CST)
    return start, end


def default_date_str() -> str:
    """默认目标日期：今天（CST）。"""
    return datetime.now(CST).strftime("%Y-%m-%d")


def is_weekday(date_str: str) -> bool:
    """判断日期是否为工作日（周一~周五）。

    华尔街见闻三栏目仅在工作日发布（周末休市无盘前/早餐）。
    """
    try:
        y, m, d = (int(x) for x in date_str.split("-"))
    except (ValueError, AttributeError):
        return True  # 无法解析时保守放行
    weekday = datetime(y, m, d, tzinfo=CST).weekday()  # 0=周一 ... 6=周日
    return weekday < 5


def build_section_entry(item) -> dict:
    """将命中的 LiveItem 转为栏目存储结构。"""
    article = item.article or {}
    entry = {
        "title": item.title.strip() or item.highlight_title.strip() or "华尔街见闻",
        "uri": item.uri or "",
        "fetched_at": datetime.now(CST).isoformat(),
        "points": _parse_points(item),
    }
    if article:
        entry["article"] = {
            "id": article.get("id"),
            "title": article.get("title", ""),
            "uri": article.get("uri", ""),
            "image": article.get("image") or None,
        }
    return entry


def _parse_points(item) -> list[str]:
    """复用 wallstreet.parse_content_points 解析要点（延迟导入避免循环依赖）。"""
    from news_tools.wallstreet import parse_content_points

    return parse_content_points(item.content, item.content_text)


def load_daily_file(data_dir: Path, date_str: str) -> dict:
    """读取当日聚合文件，不存在时返回空骨架。"""
    path = data_dir / f"{date_str}.json"
    skeleton = {"source": "wallstreet_daily", "date": date_str, "count": 0, "sections": {}}
    if not path.exists():
        return skeleton
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return skeleton
    if not isinstance(data, dict) or "sections" not in data:
        return skeleton
    return data


def save_daily_file(data_dir: Path, date_str: str, data: dict) -> Path:
    """保存当日聚合文件，sections 按键顺序排列。"""
    data_dir.mkdir(parents=True, exist_ok=True)
    ordered: dict[str, dict] = {}
    for key in SECTION_ORDER:
        if key in data.get("sections", {}):
            ordered[key] = data["sections"][key]
    data["sections"] = ordered
    data["count"] = len(ordered)

    out_path = data_dir / f"{date_str}.json"
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
