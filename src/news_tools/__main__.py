"""
python -m news_tools — 显示可用工具列表。
"""

import sys


def main() -> None:
    print("=" * 50)
    print("  News Tools — 新闻信息获取工具集")
    print("=" * 50)
    print()
    print("可用工具:")
    print()
    print("  python -m news_tools.trending [daily|weekly]  GitHub 趋势榜单")
    print("  python -m news_tools.wallstreet               华尔街见闻 7x24 快讯")
    print("  python -m news_tools.wallstreet --start ... --end ...  时间窗抓取")
    print("  python -m news_tools.xwlb                     新闻联播摘要")
    print()
    print("华尔街见闻三栏目更新:")
    print("  python scripts/wallstreet_update.py --section breakfast   早餐 07:25")
    print("  python scripts/wallstreet_update.py --section morning     早间要闻汇总 12:30")
    print("  python scripts/wallstreet_update.py --section premarket   美股盘前 21:30")
    print()
    print("每个工具均支持 --help 查看详细用法。")
    print()
    print("安装的 CLI 命令:")
    print("  news-trending   等价于 python -m news_tools.trending")
    print("  news-wallstreet 等价于 python -m news_tools.wallstreet")
    print("  news-xwlb       等价于 python -m news_tools.xwlb")
    print()


if __name__ == "__main__":
    main()
