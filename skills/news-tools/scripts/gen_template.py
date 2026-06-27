"""Generate Github Trending report template from existing report."""
import re

HTML_PATH = r"D:\code\news\report\github-trending-weekly-2026-05-31.html"
TEMPLATE_PATH = r"D:\code\news\report\template\github-trending.html"

html = open(HTML_PATH, "r", encoding="utf-8").read()

# Replace title
html = html.replace("2026年第22周", "{{WEEK_LABEL}}")

# Replace week info line
html = html.replace("2026 年第 22 周 / 2026-05-31", "{{WEEK_INFO}}")

# Replace cover summary (the paragraph after cover-sub, bound by <p class=cover-summary>)
html = re.sub(
    r'<p class="cover-summary">.*?</p>',
    '<p class="cover-summary">{{COVER_SUMMARY}}</p>',
    html,
    count=1,
    flags=re.DOTALL,
)

# Replace rank table rows
rank_start = html.find("<tbody>") + len("<tbody>")
rank_end = html.find("</tbody>", rank_start)
html = (
    html[:rank_start]
    + "\n                {{RANK_TABLE_ROWS}}\n            "
    + html[rank_end:]
)

# Replace detail pages with placeholder
detail_start = html.find("<!-- PAGE 2:")
detail_end = html.find("</body>")
placeholder = (
    '    <!-- CONTENT: Detail pages (2 repos per page).\n'
    '         Repeat the page-detail block for each pair.\n'
    '         See references/detail-page-example.md for the block structure. -->\n'
    '    {{REPO_DETAIL_PAGES}}\n'
)
html = html[:detail_start] + placeholder + html[detail_end:]

# Replace page numbers
html = html.replace("01 / 11", "{{PAGE_NUM}}")

open(TEMPLATE_PATH, "w", encoding="utf-8").write(html)
print(f"Template created: {TEMPLATE_PATH}  ({len(html)} bytes)")
