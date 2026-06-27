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
    print("  python -m news_tools.xwlb                     新闻联播摘要")
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
