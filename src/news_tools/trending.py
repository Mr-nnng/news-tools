"""
news_tools/trending.py — GitHub Trending 趋势榜单获取工具

仅做数据获取，不涉及任何内容生成或 HTML 渲染。
输出为标准 JSON 格式，支持每日/每周趋势。

用法:
    python -m news_tools.trending                    # 每日趋势（终端输出 JSON）
    python -m news_tools.trending weekly             # 每周趋势
    python -m news_tools.trending -o daily.json      # 保存到文件
    python -m news_tools.trending --proxy http://127.0.0.1:7890
    python -m news_tools.trending -l python          # 仅 Python 项目
    python -m news_tools.trending --compact          # 仅输出 repos 数组

作为模块调用:
    from news_tools.trending import fetch_trending
    result = fetch_trending(since="weekly")
    print(result.model_dump_json(indent=2))
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

# ── 时区 ───────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════


class Contributor(BaseModel):
    """贡献者信息"""

    username: str
    avatar_url: str
    profile_url: str


class TrendingRepo(BaseModel):
    """单个 GitHub 趋势仓库"""

    author: str
    name: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    language_color: Optional[str] = None
    stars_total: int = 0
    forks: int = 0
    stars_today: int = 0
    built_by: list[Contributor] = []
    author_avatar_url: Optional[str] = None
    readme: Optional[str] = None


class TrendingResult(BaseModel):
    """完整趋势结果（JSON 顶层结构）"""

    source: str = "github_trending"
    period: str  # "daily" | "weekly"
    language: Optional[str] = None
    fetched_at: str  # ISO 8601
    total_count: int
    repos: list[TrendingRepo]


# ═══════════════════════════════════════════════════════════════════
# HTTP 配置
# ═══════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

TRENDING_URL = "https://github.com/trending"


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════


def _parse_stars_count(text: str) -> int:
    """将 Star / Fork 数字符串转为整数。"""
    if not text:
        return 0
    text = text.strip().lower()
    for word in ["stars", "star", "today", "this week", "this month"]:
        text = text.replace(word, "")
    text = text.strip().replace(",", "")
    m = re.match(r"^([\d.]+)\s*k$", text)
    if m:
        return int(float(m.group(1)) * 1000)
    m = re.match(r"^(\d+)$", text)
    if m:
        return int(m.group(1))
    return 0


def _extract_language_color(style_attr: Optional[str]) -> Optional[str]:
    """从 style 属性提取语言颜色 hex 值。"""
    if not style_attr:
        return None
    m = re.search(r"#([0-9a-fA-F]{6})", style_attr)
    if m:
        return f"#{m.group(1).upper()}"
    return None


def _get_proxies(proxy_arg: Optional[str] = None) -> Optional[dict]:
    """获取代理配置，优先命令行参数，其次环境变量。"""
    if proxy_arg:
        return {"http": proxy_arg, "https": proxy_arg}
    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if env_proxy:
        return {"http": env_proxy, "https": env_proxy}
    return None


# ═══════════════════════════════════════════════════════════════════
# HTML 解析
# ═══════════════════════════════════════════════════════════════════


def parse_trending_page(html_text: str) -> list[TrendingRepo]:
    """解析 GitHub Trending 页面 HTML，返回仓库列表。"""
    soup = BeautifulSoup(html_text, "html.parser")
    articles = soup.select("article.Box-row")
    repos: list[TrendingRepo] = []
    for article in articles:
        try:
            repo = _parse_article(article)
            if repo:
                repos.append(repo)
        except Exception:
            continue
    return repos


def _parse_article(article) -> Optional[TrendingRepo]:
    """解析单个 article.Box-row 元素。"""
    h2_link = article.select_one("h2.h3 a")
    if not h2_link:
        return None
    href = h2_link.get("href", "").strip()
    full_name_raw = h2_link.get_text(" ", strip=True)
    full_name = re.sub(r"\s*/\s*", "/", full_name_raw)
    if "/" not in full_name:
        return None
    author, name = full_name.split("/", 1)
    url = f"https://github.com{href}" if href.startswith("/") else href

    desc_elem = article.select_one("p.col-9")
    description = desc_elem.get_text(strip=True) if desc_elem else None
    if description and not description.strip():
        description = None

    lang_elem = article.select_one("span[itemprop='programmingLanguage']")
    language = lang_elem.get_text(strip=True) if lang_elem else None
    color_elem = article.select_one("span.repo-language-color")
    language_color = (
        _extract_language_color(color_elem.get("style")) if color_elem else None
    )

    stars_total = 0
    forks = 0
    stars_today = 0
    stats_div = article.select_one("div.f6.color-fg-muted.mt-2")
    if stats_div:
        for link in stats_div.select("a.Link--muted"):
            link_href = link.get("href", "")
            link_text = link.get_text(strip=True)
            if "/forks" in link_href:
                forks = _parse_stars_count(link_text)
            else:
                if stars_total == 0:
                    stars_total = _parse_stars_count(link_text)
        today_span = stats_div.select_one("span.d-inline-block.float-sm-right")
        if today_span:
            stars_today = _parse_stars_count(today_span.get_text(strip=True))

    built_by: list[Contributor] = []
    for avatar_link in article.select("a.avatar-mb"):
        img = avatar_link.select_one("img.avatar")
        if not img:
            continue
        username = img.get("alt", "").replace("@", "").strip()
        avatar_url = img.get("src", "").strip()
        if username and avatar_url:
            profile_url = f"https://github.com/{username}"
            built_by.append(
                Contributor(
                    username=username, avatar_url=avatar_url, profile_url=profile_url
                )
            )

    return TrendingRepo(
        author=author,
        name=name,
        url=url,
        description=description,
        language=language,
        language_color=language_color,
        stars_total=stars_total,
        forks=forks,
        stars_today=stars_today,
        built_by=built_by,
    )


# ═══════════════════════════════════════════════════════════════════
# README 抓取
# ═══════════════════════════════════════════════════════════════════

_README_ATTEMPTS = [
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/main/README.md",
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/master/README.md",
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/main/README.rst",
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/master/README.rst",
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/main/README",
    lambda owner, name: f"https://raw.githubusercontent.com/{owner}/{name}/master/README",
]


def _fetch_readme_via_api(
    owner: str,
    name: str,
    proxies: Optional[dict] = None,
    timeout: int = 20,
    max_length: int = 0,
) -> Optional[str]:
    """通过 GitHub REST API 的 /readme 端点抓取 README。

    该端点会自动解析仓库的默认分支与 README 文件名（支持任意分支名、
    任意大小写文件名），比逐个猜测 raw 分支/文件名更可靠。
    """
    api_url = f"https://api.github.com/repos/{owner}/{name}/readme"
    headers = {**HEADERS, "Accept": "application/vnd.github.raw"}
    try:
        resp = requests.get(api_url, headers=headers, proxies=proxies, timeout=timeout)
        if resp.status_code == 200:
            text = resp.text.strip()
            if text:
                if max_length and max_length > 0 and len(text) > max_length:
                    return text[:max_length]
                return text
    except requests.RequestException:
        pass
    return None


def _fetch_readme(
    owner: str,
    name: str,
    proxies: Optional[dict] = None,
    timeout: int = 8,
    max_length: int = 0,
    retries: int = 2,
) -> Optional[str]:
    """尝试抓取仓库 README 内容。

    策略（按顺序）：
    1. 依次尝试 main/master 分支下的 README.md / README.rst / README（含重试）；
    2. 全部失败时回退到 GitHub REST API 的 /readme 端点（自动解析默认分支与文件名，
       可覆盖非 main/master 默认分支或非常规文件名的仓库）。

    max_length=0 表示不截断（完整保留）。
    """
    for _ in range(max(1, retries)):
        for url_builder in _README_ATTEMPTS:
            try:
                url = url_builder(owner, name)
                resp = requests.get(url, headers=HEADERS, proxies=proxies, timeout=timeout)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    if text:
                        if max_length and max_length > 0 and len(text) > max_length:
                            return text[:max_length]
                        return text
            except requests.RequestException:
                continue

    # 回退：GitHub API /readme 端点
    return _fetch_readme_via_api(
        owner, name, proxies=proxies, timeout=max(20, timeout), max_length=max_length
    )


def _enrich_repos(
    repos: list[TrendingRepo],
    proxies: Optional[dict] = None,
    timeout: int = 8,
    fetch_readme: bool = True,
    readme_max_length: int = 0,
) -> list[TrendingRepo]:
    """对解析后的仓库列表补充额外信息（头像链接、README）。"""
    for repo in repos:
        repo.author_avatar_url = f"https://github.com/{repo.author}.png"

    if fetch_readme:
        for repo in repos:
            readme = _fetch_readme(
                owner=repo.author,
                name=repo.name,
                proxies=proxies,
                timeout=timeout,
                max_length=readme_max_length,
            )
            repo.readme = readme

    return repos


# ═══════════════════════════════════════════════════════════════════
# 主请求函数
# ═══════════════════════════════════════════════════════════════════


def fetch_trending(
    since: str = "daily",
    language: Optional[str] = None,
    proxy: Optional[str] = None,
    fetch_readme: bool = True,
    readme_max_length: int = 0,
    timeout: int = 15,
) -> TrendingResult:
    """获取 GitHub 趋势榜单。

    Args:
        since: "daily" 或 "weekly"
        language: 可选语言过滤，如 "python"
        proxy: 代理地址，如 "http://127.0.0.1:7890"
        fetch_readme: 是否抓取每个仓库的 README（默认 True）
        readme_max_length: README 最大截取字符数（0=不截断）
        timeout: 请求超时秒数

    Returns:
        TrendingResult 包含完整趋势信息

    Raises:
        requests.RequestException: HTTP 请求失败
        ValueError: since 参数不合法
    """
    since = since.lower()
    if since not in ("daily", "weekly"):
        raise ValueError("since 参数必须为 'daily' 或 'weekly'")

    url = TRENDING_URL
    params: dict[str, str] = {"since": since}
    if language:
        url = f"{TRENDING_URL}/{language.lower()}"

    proxies = _get_proxies(proxy)
    resp = requests.get(
        url, params=params, headers=HEADERS, proxies=proxies, timeout=timeout
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"

    repos = parse_trending_page(resp.text)

    repos = _enrich_repos(
        repos,
        proxies=proxies,
        timeout=max(8, timeout),
        fetch_readme=fetch_readme,
        readme_max_length=readme_max_length,
    )

    now_cst = datetime.now(CST)
    fetched_at = now_cst.isoformat()

    return TrendingResult(
        period=since,
        language=language,
        fetched_at=fetched_at,
        total_count=len(repos),
        repos=repos,
    )


# ═══════════════════════════════════════════════════════════════════
# CLI 入口（支持 python -m news_tools.trending）
# ═══════════════════════════════════════════════════════════════════


def build_parser(period: str = "daily") -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    label = "每日" if period == "daily" else "每周"
    parser = argparse.ArgumentParser(
        description=f"获取 GitHub {label}趋势榜单，输出 JSON。",
    )
    parser.add_argument(
        "period",
        nargs="?",
        default=period,
        choices=["daily", "weekly"],
        help=f"趋势周期: daily / weekly (默认: {period})",
    )
    parser.add_argument(
        "-o", "--output", default=None, help="输出文件路径（默认输出到终端）"
    )
    parser.add_argument(
        "--proxy", default=None, help="代理地址，如 http://127.0.0.1:7890"
    )
    parser.add_argument(
        "-l", "--language", default=None, help="按语言过滤，如 python、javascript"
    )
    parser.add_argument(
        "--compact", action="store_true", help="紧凑模式：只输出 repos 数组"
    )
    parser.add_argument(
        "--timeout", type=int, default=15, help="请求超时秒数（默认 15）"
    )
    parser.add_argument("--no-readme", action="store_true", help="不抓取 README 内容")
    parser.add_argument(
        "--readme-max-length",
        type=int,
        default=0,
        help="README 最大截取字符数（0=不截断，默认 0）",
    )
    return parser


def main() -> None:
    """CLI 入口函数。"""
    # Windows GBK 控制台编码兼容
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()

    try:
        result = fetch_trending(
            since=args.period,
            language=args.language,
            fetch_readme=not args.no_readme,
            readme_max_length=args.readme_max_length,
            proxy=args.proxy,
            timeout=args.timeout,
        )
    except requests.RequestException as e:
        print(f'{{"error": "请求 GitHub Trending 失败: {e}"}}', file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f'{{"error": "{e}"}}', file=sys.stderr)
        sys.exit(1)

    # 序列化
    if args.compact:
        data = [r.model_dump() for r in result.repos]
    else:
        data = result.model_dump()

    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
            f.write("\n")
        print(
            json.dumps(
                {"status": "saved", "path": args.output, "count": result.total_count},
                ensure_ascii=False,
            )
        )
    else:
        print(json_str)


if __name__ == "__main__":
    main()
