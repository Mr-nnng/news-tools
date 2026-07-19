#!/usr/bin/env python3
"""
weekly_update.py — GitHub Actions 每周周榜自动更新入口 (SPA mode)

复用 trending.py 获取周榜原始数据，调用 LLM 为每个仓库生成中文简介/特点/受众，
输出 JSON 到 site/data/github/，与已有格式保持一致。
复用 build_site.py 中的 index 重建函数。

用法:
    python scripts/weekly_update.py
    python scripts/weekly_update.py --date 2026-07-18
    python scripts/weekly_update.py --proxy http://127.0.0.1:7890
"""

import json
import os
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

import httpx

# 确保 src/ 和 scripts/ 可导入
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from news_tools.trending import fetch_trending, TrendingRepo
import build_site  # 复用 data / month 工具函数

SITE_DIR = PROJECT_ROOT / "site"
DATA_DIR = SITE_DIR / "data"
GH_DATA_DIR = DATA_DIR / "github"

# ── LLM 配置 ───────────────────────────────────────────────────────
LLM_BASE_URL = "https://opencode.ai/zen/v1"
LLM_MODEL = "deepseek-v4-flash-free"


# ═══════════════════════════════════════════════════════════════════
# LLM 调用
# ═══════════════════════════════════════════════════════════════════


def _call_llm(prompt: str, system_prompt: str | None = None, max_retries: int = 3) -> str | None:
    """调用 LLM 并返回原始响应文本，失败重试直到 max_retries 次。

    使用 httpx 直接请求，不依赖 OpenAI SDK，避免强制 api_key 校验。
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0.1,
            }
            resp = httpx.post(
                f"{LLM_BASE_URL}/chat/completions",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content:
                return content
            print(f"  ⚠️  LLM 返回空内容（第{attempt}次）")
            last_exception = ValueError("Empty response")
        except Exception as e:
            print(f"  ⚠️  LLM 调用异常（第{attempt}次）: {e}")
            last_exception = e
            if attempt < max_retries:
                print(f"  🔄 准备重试...")

    print(f"  ❌ LLM 已重试 {max_retries} 次均失败，error={last_exception}")
    return None


def _call_llm_for_repo(repo: TrendingRepo, max_retries: int = 3) -> dict | None:
    """调用 LLM 为单个仓库生成中文增强内容，失败重试直到 max_retries 次。"""
    name = f"{repo.author}/{repo.name}"
    desc = repo.description or ""
    readme = repo.readme or ""

    system_prompt = """你是一个技术内容编辑，负责为 GitHub 仓库生成中文增强内容。

## 核心原则
1. 必须完整阅读 README 内容后再写 zh_desc，不可仅靠 description 字段
2. description 已用 zh_desc 替代，最终 JSON 中不得包含 description、readme 字段
3. 只输出 JSON，不包含任何其他内容（不要用 markdown 代码块包裹）

## 字段规范
- **zh_desc**：精炼的 2 句话中文简介（100字以内，50-90字最佳）。第一句讲清楚项目是什么，第二句讲为什么重要/解决什么问题。避免啰嗦。
- **features**：固定 3 条，每条 15-25 字，直接说明功能价值。
- **audience**：中文推荐受众，用顿号分隔 3-5 种用户身份。"""

    user_prompt = f"""仓库名称: {name}
英文描述: {desc}
README 内容:
{readme}

请严格按照以上规范输出 JSON。

参考示例（来自历史仓库 Nutlope/hallmark）：
{{
  "zh_desc": "反AI模版化设计技能，专为Claude Code、Cursor等AI编程工具打造。它通过57项检测门和二十种主题，自动生成独特UI布局，彻底告别千篇一律的AI生成界面。",
  "features": [
    "二十种主题搭配57项抗模版检测门防止AI感",
    "支持审计、重构、学习四类命令覆盖设计全流程",
    "能从设计截图提取DNA生成跨项目可复用规范"
  ],
  "audience": "AI开发者、前端设计师、产品经理、提示工程师"
}}"""

    for attempt in range(1, max_retries + 1):
        content = _call_llm(user_prompt, system_prompt=system_prompt, max_retries=1)
        if content is None:
            if attempt < max_retries:
                print(f"  🔄 准备重试...")
            continue

        # 提取 JSON 对象
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if not json_match:
            print(f"  ⚠️  {name} LLM 返回无有效 JSON（第{attempt}次）")
            if attempt < max_retries:
                print(f"  🔄 准备重试...")
            continue

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  ⚠️  {name} JSON 解析失败（第{attempt}次）: {e}")
            if attempt < max_retries:
                print(f"  🔄 准备重试...")
            continue

        # 兼容 zhDesc（历史字段名）与 zh_desc（SKILL.md 规范）
        zh_desc = data.get("zh_desc") or data.get("zhDesc", "") or ""
        features = data.get("features") or data.get("features_list") or []
        audience = data.get("audience") or data.get("audience_list") or ""

        # 补足 / 截断 features
        while len(features) < 3:
            features.append("")
        features = features[:3]

        return {
            "zhDesc": zh_desc.strip(),
            "features": [f.strip() for f in features],
            "audience": (audience.strip() if isinstance(audience, str) else "、".join(audience)),
        }

    print(f"  ❌  {name} 已重试 {max_retries} 次均失败")
    return None


def _call_llm_for_cover_summary(repos_info: list[dict], max_retries: int = 3) -> str | None:
    """调用 LLM 生成周榜总览摘要，失败重试直到 max_retries 次。"""
    repo_lines = "\n".join(
        f"- {r['name']}（{r.get('zhDesc', '')[:60]}）"
        for r in repos_info
    )
    prompt = f"""以下是一周 GitHub Trending 热门仓库列表：
{repo_lines}

请用一句话概括本周趋势，格式如下：
"本周 GitHub Trending 收录 N 个热门仓库，涵盖 ··· 等领域。"
其中 ··· 之间用中文领域关键词分隔。
不要包含其他内容。"""

    return _call_llm(prompt, max_retries=max_retries)


# ═══════════════════════════════════════════════════════════════════
# 增强处理
# ═══════════════════════════════════════════════════════════════════


def enrich_repos(repos: list[TrendingRepo], max_retries: int = 3) -> list[dict]:
    """对每个 repo 调用 LLM 生成中文增强内容，失败则回退 description。"""
    enriched: list[dict] = []
    total = len(repos)

    for idx, repo in enumerate(repos, 1):
        print(f"  [{idx}/{total}] {repo.author}/{repo.name} ...", end=" ", flush=True)
        llm_data = _call_llm_for_repo(repo, max_retries=max_retries)

        if llm_data:
            print("✅")
            enriched.append({
                "rank": idx,
                "name": repo.name,
                "author": repo.author,
                "url": repo.url,
                "stars": repo.stars_total,
                "forks": repo.forks,
                "weeklyStars": repo.stars_today,
                "language": repo.language or "",
                "langColor": repo.language_color or "",
                "zhDesc": llm_data["zhDesc"],
                "features": llm_data["features"],
                "audience": llm_data["audience"],
            })
        else:
            # 回退：用英文 description 填充
            desc = repo.description or "暂无描述"
            print(f"⚠️  回退")
            enriched.append({
                "rank": idx,
                "name": repo.name,
                "author": repo.author,
                "url": repo.url,
                "stars": repo.stars_total,
                "forks": repo.forks,
                "weeklyStars": repo.stars_today,
                "language": repo.language or "",
                "langColor": repo.language_color or "",
                "zhDesc": desc,
                "features": ["", "", ""],
                "audience": "",
            })

    return enriched


# ═══════════════════════════════════════════════════════════════════
# 数据保存
# ═══════════════════════════════════════════════════════════════════


def save_github_json(date_str: str, data: dict) -> Path:
    """保存周榜数据为 SPA JSON 到 site/data/github/{date}.json。"""
    GH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GH_DATA_DIR / f"{date_str}.json"
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


# ═══════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="每周 GitHub 周榜自动更新脚本 (SPA mode)")
    parser.add_argument("--date", "-d", default=None, help="日期 (YYYY-MM-DD)，默认本周六")
    parser.add_argument(
        "--proxy", default=None,
        help="代理地址，如 http://127.0.0.1:7890（默认读取 HTTPS_PROXY 环境变量）",
    )
    parser.add_argument(
        "--retries", "-r", type=int, default=3,
        help="LLM 调用失败最大重试次数（默认 3）",
    )
    args = parser.parse_args()

    # 确定代理：优先命令行参数，其次环境变量
    proxy = args.proxy
    if not proxy:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    if proxy:
        print(f"🔌 使用代理: {proxy}\n")

    # —— 确定目标日期 ——
    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)

    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=bj_tz)
    else:
        # 默认取最近一个周六（cron 在周六运行）
        days_since_saturday = (now_bj.weekday() - 5) % 7
        target = (now_bj - timedelta(days=days_since_saturday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    date_str = target.strftime("%Y-%m-%d")
    iso_year, iso_week, _ = target.isocalendar()
    week_label = f"{iso_year}年第{iso_week}周"
    week_info = f"{iso_year} 年第 {iso_week} 周 / {date_str}"

    print(f"🔍 目标日期: {date_str}  ({week_label})\n")

    # —— 确保站点目录 ——
    print("📁 确保站点目录...")
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("  ✅ 站点目录就绪\n")

    # —— Step 1: 获取 GitHub 周榜原始数据（不限制 README 长度） ——
    print("📡 获取 GitHub 周榜数据（含 README）...")
    try:
        result = fetch_trending(
            since="weekly",
            fetch_readme=True,
            proxy=proxy,
        )
    except Exception as e:
        print(f"  ❌ 获取周榜失败: {e}")
        sys.exit(1)

    if not result.repos:
        print("  ⚠️  未获取到任何仓库数据（可能尚未发布）")
        print("\n🏠 重新构建 index.json...")
        build_site.build_index_data()
        return

    print(f"  ✅ 获取到 {result.total_count} 个热门仓库\n")

    # —— Step 2: LLM 逐仓库增强 ——
    print(f"🤖 使用 LLM（{LLM_MODEL}）生成中文内容...")
    enriched_repos = enrich_repos(result.repos, max_retries=args.retries)
    print()

    # —— Step 3: 生成总览摘要 ——
    print("📝 生成周榜总览摘要...")
    cover_summary = _call_llm_for_cover_summary(enriched_repos, max_retries=args.retries)
    if not cover_summary:
        # 回退模板
        langs = sorted({r["language"] for r in enriched_repos if r["language"]})
        lang_str = "·".join(langs)
        cover_summary = (
            f"本周 GitHub Trending 收录 {len(enriched_repos)} 个热门仓库，"
            f"涵盖 {lang_str} 等领域。"
        )
    print(f"  ✅ {cover_summary}\n")

    # —— Step 4: 组装并保存 JSON ——
    print("📄 生成周榜 JSON...")
    output = {
        "weekLabel": week_label,
        "weekInfo": week_info,
        "date": date_str,
        "count": len(enriched_repos),
        "totalCount": len(enriched_repos),
        "coverSummary": cover_summary,
        "repos": enriched_repos,
    }
    out_path = save_github_json(date_str, output)
    print(f"  ✅ → {out_path.relative_to(PROJECT_ROOT)}\n")

    # —— Step 5: 重建 index.json ——
    print("🏠 重建 index.json...")
    build_site.build_index_data()

    print(f"\n{'=' * 50}")
    print(f"✅ 每周更新完成: {date_str}  ({week_label})")
    print(f"   📄 site/data/github/{date_str}.json")
    print(f"   🏠 site/data/index.json")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
