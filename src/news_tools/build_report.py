"""
news_tools/build_report.py — 从 enriched JSON 和 HTML 模板生成 GitHub Trending 周报

职责：
- 读取 enriched JSON（含 LLM 生成的中文内容）
- 下载头像到 avatar/ 子目录
- 填充模板生成 report.html
- 封面表格仅列前 10，详情页展示全部（每页 2 个）

用法:
    python -m news_tools.build_report enriched.json -o /path/to/output/dir
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from typing import Optional

import requests

# ── 时区 ───────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))

# ── HTTP 头（头像下载用） ────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/125.0.0.0 Safari/537.36"
    ),
}

_DEFAULT_TEMPLATE = None  # 在 main 中动态计算


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════


def _fmt_short(n: int) -> str:
    """格式化大数字为简洁 k 单位（如 15894 → 15.9k）。"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _fmt_comma(n: int) -> str:
    """格式化数字为带逗号的字符串（如 15894 → 15,894）。"""
    return f"{n:,}"


def _fmt_weekly(n: int) -> str:
    """格式化本周 Star 数（如 13308 → +13,308）。"""
    return f"+{n:,}"


def _highlight_summary(text: str) -> str:
    """处理封面摘要：数字用 <span class="hl"> 高亮，领域关键词用 <strong> 加粗。"""
    # 高亮数字（包括数字+万/千）
    text = re.sub(r"(\d+(?:\.\d+)?)(?=\s*(?:个|万|k|⭐|星))", r'<span class="hl">\1</span>', text)
    text = re.sub(r'(?<![.<>"])(\d+)(?![.\d]*<\/[^>]+>)(?!\s*\.\d)', r'<span class="hl">\1</span>', text)
    # 领域关键词加粗（用 · 分隔的领域列表）
    text = re.sub(
        r"(?<=涵盖\s)(.*?)(?=\s*等领域)", lambda m: re.sub(r"([^·\s][^·]*?)(?=·|$)", r"<strong>\1</strong>", m.group(1)), text
    )
    return text


def _download_avatars(repos: list[dict], avatar_dir: Path, proxies: Optional[dict] = None) -> None:
    """将每个仓库作者的头像下载到本地 avatar_dir。"""
    avatar_dir.mkdir(parents=True, exist_ok=True)
    for repo in repos:
        author = repo["author"]
        local_path = avatar_dir / f"{author}.png"
        if local_path.exists():
            continue
        url = f"https://github.com/{author}.png"
        try:
            resp = requests.get(url, headers=HEADERS, proxies=proxies, timeout=15)
            if resp.status_code == 200:
                local_path.write_bytes(resp.content)
            else:
                local_path.write_bytes(b"")
        except requests.RequestException:
            local_path.write_bytes(b"")


# ═══════════════════════════════════════════════════════════════════
# HTML 生成
# ═══════════════════════════════════════════════════════════════════


def build_report(
    enriched: dict,
    template_path: str,
    output_dir: str,
    avatar_dir_name: str = "avatar",
    proxies: Optional[dict] = None,
    download_avatars: bool = True,
) -> str:
    """生成 HTML 报告并写出到 output_dir/report.html。

    Args:
        download_avatars: 是否下载 GitHub 头像。site 构建时设为 False 以加速（头像已预复制）。
    
    Returns:
        HTML 文件的绝对路径。
    """
    repos = enriched["repos"]
    total_count = enriched.get("total_count", len(repos))
    cover_summary = enriched.get("cover_summary", "")

    # ── 输出目录 ──────────────────────────────────────────
    out_dir = Path(output_dir).resolve()
    avatar_abs = out_dir / avatar_dir_name

    # ── 下载头像 ──────────────────────────────────────────
    if download_avatars:
        _download_avatars(repos, avatar_abs, proxies=proxies)

    # ── 日期信息（从输出目录名推断） ──────────────────────
    out_dir = Path(output_dir).resolve()
    dir_name = out_dir.name  # e.g. "2026-06-07" or "github-trending-weekly-2026-06-07"
    date_part = dir_name.replace("github-trending-weekly-", "")
    try:
        # Try parsing as YYYY-MM-DD
        parts = date_part.split("-")
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
            report_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=CST)
        elif len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            # YYYY-WW format (year-week)
            from datetime import date
            iso_date = date.fromisocalendar(int(parts[0]), int(parts[1]), 1)
            report_date = datetime(iso_date.year, iso_date.month, iso_date.day, tzinfo=CST)
        else:
            report_date = datetime.now(CST)
    except (ValueError, IndexError):
        report_date = datetime.now(CST)
    week_num = report_date.isocalendar()[1]
    week_label = f"{report_date.year}年第{week_num}周"
    week_info = f"{report_date.year} 年第 {week_num} 周 / {report_date.strftime('%Y-%m-%d')}"

    # ── 封面排名表（仅前 10） ─────────────────────────────
    rank_rows = ""
    for i, r in enumerate(repos[:10], 1):
        lang = r.get("language") or "—"
        rank_rows += f"""                <tr>
                    <td class="td-rank">{i}</td>
                    <td class="td-repo">{r["name"]}<span class="author"> / {r["author"]}</span></td>
                    <td>{lang}</td>
                    <td class="td-stars">{_fmt_short(r["stars_total"])}</td>
                    <td class="td-forks">{_fmt_short(r["forks"])}</td>
                </tr>\n"""
    rank_rows = rank_rows.rstrip("\n")

    # ── 连续滚动：逐个项目块（新版模板 {{REPO_ITEMS}}） ──
    repo_items = ""
    for idx, r in enumerate(repos):
        rank = idx + 1
        repo_items += _build_item_block(r, rank, avatar_dir_name)

    # ── 翻页卡片：详情块（旧版模板 {{REPO_DETAIL_PAGES}}） ──
    total_pages = (len(repos) + 1) // 2 + 1  # 封面 + 详情页数
    detail_pages = ""
    page_idx = 2
    for i in range(0, len(repos), 2):
        r1 = repos[i]
        r2 = repos[i + 1] if i + 1 < len(repos) else None

        b1 = _build_block(r1, i + 1, avatar_dir_name)
        if r2:
            b2 = _build_block(r2, i + 2, avatar_dir_name)
            detail_pages += f"""    <!-- PAGE {page_idx}: #{i+1} {r1['name']} + #{i+2} {r2['name']} -->
    <div class="page page-detail" id="page-{page_idx:02d}">
        {b1}
        <hr class="divider">
        {b2}
        <div class="page-num">{page_idx:02d} / {total_pages:02d}</div>
    </div>\n\n"""
        else:
            detail_pages += f"""    <!-- PAGE {page_idx}: #{i+1} {r1['name']} -->
    <div class="page page-detail" style="justify-content:flex-start" id="page-{page_idx:02d}">
        {b1}
        <div class="page-num">{page_idx:02d} / {total_pages:02d}</div>
    </div>\n\n"""
        page_idx += 1
    detail_pages = detail_pages.rstrip()

    repo_count = len(repos)

    # ── 生成右侧索引（兼容新旧模板） ─────────────────
    # 旧版索引：指向翻页卡片
    index_items_old = ""
    index_items_old += f'      <a class="index-item" href="#page-cover"><span class="idx-num">✦</span> 封面</a>\n'
    for idx, r in enumerate(repos):
        rank = idx + 1
        page_idx = idx // 2 + 2
        index_items_old += f'      <a class="index-item" href="#page-{page_idx:02d}"><span class="idx-num">#{rank:02d}</span> {r["name"]}</a>\n'

    # 新版索引：指向连续滚动 repo
    index_items_new = ""
    index_items_new += f'      <a class="index-item" href="#gh-cover"><span class="idx-num">✦</span> 排行榜</a>\n'
    index_items_new += '      <div class="index-divider"></div>\n'
    for idx, r in enumerate(repos):
        rank = idx + 1
        index_items_new += f'      <a class="index-item" href="#repo-{rank:02d}"><span class="idx-num">#{rank:02d}</span> {r["name"]}</a>\n'

    # ── 读取模板并填充 ────────────────────────────────────
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{{WEEK_LABEL}}", week_label)
    html = html.replace("{{WEEK_INFO}}", week_info)
    html = html.replace("{{REPO_COUNT}}", str(repo_count))
    html = html.replace("{{COVER_SUMMARY}}", _highlight_summary(cover_summary))
    html = html.replace("{{RANK_TABLE_ROWS}}", rank_rows)
    html = html.replace("{{REPO_ITEMS}}", repo_items)
    html = html.replace("{{REPO_DETAIL_PAGES}}", detail_pages)
    html = html.replace("{{PAGE_NUM}}", f"01 / {total_pages:02d}")
    html = html.replace("{{REPO_INDEX}}", index_items_new)
    # {{SIDEBAR}} is left for build_site.py to inject

    # ── 写入输出 ──────────────────────────────────────────
    out_path = out_dir / "report.html"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(out_path)


def _build_block(r: dict, rank: int, avatar_rel: str) -> str:
    """构建单个卡片翻页 repo-block HTML（旧版模板用）。"""
    zh_desc = r.get("zh_desc") or r.get("description") or ""
    features = r.get("features", [])
    audience = r.get("audience", "")
    lang = r.get("language") or ""
    lang_color = r.get("language_color") or "#888"
    stars_fmt = _fmt_comma(r["stars_total"])
    weekly_fmt = _fmt_weekly(r["stars_today"])
    forks_fmt = _fmt_comma(r["forks"])
    avatar_path = f"{avatar_rel}/{r['author']}.png"
    repo_url = r["url"]

    feat_lines = ""
    for feat in features[:3]:
        feat_lines += f"                <li>{feat}</li>\n"

    lang_metric = (
        f'                <div class="repo-metric"><span class="lang-dot" style="background:{lang_color}"></span>'
        f'<span class="lbl">{lang or "—"}</span></div>\n'
    )

    return f"""        <div class="repo-block">
            <div class="repo-number">#{rank}</div>
            <div class="repo-header">
                <div class="repo-avatar"><img src="{avatar_path}" alt="{r['author']}" loading="lazy" onerror="this.src='https://github.com/{r['author']}.png'"></div>
                <div class="repo-name">{r["name"]}<span class="author-name">{r["author"]}</span></div>
            </div>
            <div class="repo-metrics">
                {lang_metric}                <div class="repo-metric"><span class="val">{stars_fmt}</span><span class="lbl">Star</span></div>
                <div class="repo-metric"><span class="val" style="color:var(--near-black)">{weekly_fmt}</span><span class="lbl">本周</span></div>
                <div class="repo-metric"><span class="val">{forks_fmt}</span><span class="lbl">Fork</span></div>
            </div>
            <div class="repo-desc">{zh_desc}</div>
            <ul class="repo-features">
{feat_lines}            </ul>
            <div class="repo-audience"><strong>推荐：</strong>{audience}</div>
            <div class="repo-url"><a href="{repo_url}" target="_blank">{repo_url}</a></div>
        </div>"""


def _build_item_block(r: dict, rank: int, avatar_rel: str) -> str:
    """构建单个 repo 连续滚动 HTML 块。

    数据取自 enriched JSON：
    - zh_desc: 中文简介
    - features: 特点列表（3-5 条）
    - audience: 推荐受众
    """
    zh_desc = r.get("zh_desc") or r.get("description") or ""
    features = r.get("features", [])
    audience = r.get("audience", "")
    lang = r.get("language") or ""
    lang_color = r.get("language_color") or "#888"
    stars_fmt = _fmt_comma(r["stars_total"])
    weekly_fmt = _fmt_weekly(r["stars_today"])
    forks_fmt = _fmt_comma(r["forks"])
    avatar_path = f"{avatar_rel}/{r['author']}.png"
    repo_url = r["url"]

    # 生成特点列表 HTML
    feat_lines = ""
    for feat in features[:3]:  # 固定 3 条
        feat_lines += f"            <li>{feat}</li>\n"

    lang_metric = (
        f'          <div class="repo-metric"><span class="lang-dot" style="background:{lang_color}"></span>'
        f'<span class="lbl">{lang or "—"}</span></div>\n'
    )

    return f"""    <div class="repo-item" id="repo-{rank:02d}">
      <div class="repo-number">#{rank}</div>
      <div class="repo-header">
        <div class="repo-avatar"><img src="{avatar_path}" alt="{r['author']}" loading="lazy" onerror="this.src='https://github.com/{r['author']}.png'"></div>
        <div class="repo-name">{r["name"]}<span class="author-name">{r["author"]}</span></div>
      </div>
      <div class="repo-metrics">
        {lang_metric}        <div class="repo-metric"><span class="val">{stars_fmt}</span><span class="lbl">Star</span></div>
        <div class="repo-metric"><span class="val" style="color:var(--near-black)">{weekly_fmt}</span><span class="lbl">本周</span></div>
        <div class="repo-metric"><span class="val">{forks_fmt}</span><span class="lbl">Fork</span></div>
      </div>
      <div class="repo-desc">{zh_desc}</div>
      <ul class="repo-features">
{feat_lines}      </ul>
      <div class="repo-audience"><strong>推荐：</strong>{audience}</div>
      <div class="repo-url"><a href="{repo_url}" target="_blank">{repo_url}</a></div>
    </div>"""


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def _detect_project_root() -> Path:
    """从当前文件位置推算项目根目录。"""
    return Path(__file__).resolve().parent.parent.parent


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="从 enriched JSON 生成 GitHub Trending HTML 周报",
    )
    parser.add_argument("enriched_json", help="enriched JSON 文件路径")
    parser.add_argument("-o", "--output-dir", default=None, help="输出目录（默认与 JSON 同目录）")
    parser.add_argument("--avatar-dir", default="avatar", help="头像子目录名（默认 avatar）")
    parser.add_argument("--template", default=None, help="HTML 模板路径")
    parser.add_argument("--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890")
    args = parser.parse_args()

    # ── 读取 enriched JSON ───────────────────────────────
    json_path = Path(args.enriched_json)
    if not json_path.exists():
        print(f"❌ 文件不存在: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        enriched = json.load(f)

    # ── 输出目录 ──────────────────────────────────────────
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = json_path.parent.parent  # data/ 的上级

    # ── 模板路径 ──────────────────────────────────────────
    if args.template:
        template_path = args.template
    else:
        root = _detect_project_root()
        template_path = str(root / "assets" / "templates" / "github-trending.html")

    # ── 代理设置 ──────────────────────────────────────────
    proxies = None
    if args.proxy:
        proxies = {"http": args.proxy, "https": args.proxy}

    # ── 生成报告 ──────────────────────────────────────────
    print(f"📄 生成 HTML 报告（{enriched.get('total_count', 0)} 个仓库）...")
    out = build_report(
        enriched=enriched,
        template_path=template_path,
        output_dir=str(out_dir),
        avatar_dir_name=args.avatar_dir,
        proxies=proxies,
    )
    print(f"✅ 报告已生成: {out}")


if __name__ == "__main__":
    main()
