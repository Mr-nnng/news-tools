"""
news_tools/screenshot.py — HTML 元素导出为图片工具

使用 ``Playwright`` + Google Chrome 将 HTML 文件中匹配 CSS 选择器的元素
**逐一定位并截取**为 PNG 图片，常用于周报/日报卡片批量导出。

用法::

    from news_tools.screenshot import element_screenshot, page_screenshot

    # ── 批量导出所有匹配 .page 的元素 ──────────────────────
    files = element_screenshot(
        "report/github-trending-weekly-2026-05-31.html",
        selector=".page",
        output_dir="output",
    )
    # → ["output/page_01.png", "output/page_02.png", …]

    # ── 整页长截图 ─────────────────────────────────────────
    page_screenshot(
        "report/daily-news-2026-05-29.html",
        output="output/fullpage.png",
    )

    # ── 指定 Chrome 路径 ───────────────────────────────────
    element_screenshot(
        "report/github-trending-weekly-2026-05-31.html",
        selector=".page",
        chrome_path=r"D:\\chrome\\chrome.exe",
    )
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

# ── 默认 Chrome 路径 ────────────────────────────────────────────────
_DEFAULT_CHROME = "/usr/bin/google-chrome"


# ═══════════════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════════════


def _resolve_path(html_path: str) -> str:
    """将本地 HTML 路径转为 ``file://`` URL（支持相对路径）。"""
    abs_path = os.path.abspath(html_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"HTML 文件不存在: {abs_path}")
    return f"file:///{abs_path.replace(os.sep, '/')}"


def _ensure_dir(dir_path: str) -> str:
    """确保输出目录存在，返回绝对路径。"""
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    return str(p.absolute())


def _wait_for_images(page, timeout: int = 15000) -> None:
    """等待页面上所有 img 元素加载完成（包括懒加载头像）。"""
    try:
        page.wait_for_function(
            """() => {
                const imgs = document.querySelectorAll('img');
                if (imgs.length === 0) return true;
                return Array.from(imgs).every(img => img.complete && img.naturalWidth > 0);
            }""",
            timeout=timeout,
        )
    except Exception:
        pass


def _wait_for_fonts(page, timeout: int = 10000) -> None:
    """等待所有 @font-face 字体加载完成，避免截图时 fallback 字体。

    使用 document.fonts.ready 确保自定义字体渲染完毕。
    """
    try:
        page.wait_for_function(
            """() => {
                if (!document.fonts || !document.fonts.ready) return true;
                return document.fonts.ready.then(() => {
                    // 额外检查每个 @font-face 是否已加载
                    for (const f of document.fonts) {
                        if (f.status !== 'loaded' && f.status !== 'ready') return false;
                    }
                    return true;
                });
            }""",
            timeout=timeout,
        )
    except Exception:
        pass


def _open_browser(chrome_path: Optional[str] = None):
    """启动 Playwright 浏览器实例，优先使用系统 Chrome，失败时回退内置 Chromium。"""
    p = sync_playwright().start()
    launch_opts: dict = {"headless": True}

    chrome_candidates = []
    if chrome_path:
        chrome_candidates.append(chrome_path)

    # Linux 常见 Chrome 路径
    if not chrome_path:
        for candidate in [
            _DEFAULT_CHROME,
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ]:
            if os.path.isfile(candidate):
                chrome_candidates.append(candidate)
                break

    for path in chrome_candidates:
        try:
            browser = p.chromium.launch(executable_path=path, **launch_opts)
            return p, browser
        except Exception:
            continue

    # 最后回退：Playwright 内置 Chromium
    browser = p.chromium.launch(**launch_opts)
    return p, browser


# ═══════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════


def element_screenshot(
    html_path: str,
    selector: str = ".page",
    output_dir: str = ".",
    output_prefix: str = "page",
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    device_scale_factor: float = 3,
    full_page: bool = False,
    chrome_path: Optional[str] = None,
) -> list[str]:
    """将 HTML 文件中匹配 *selector* 的**每一个元素**分别导出为 PNG 图片。

    Parameters
    ----------
    html_path:
        本地 HTML 文件路径（支持相对路径）。
    selector:
        CSS 选择器，匹配需要截图的元素。
    output_dir:
        图片输出目录（自动创建）。
    output_prefix:
        输出文件的前缀，最终文件名为 ``{prefix}_01.png``、``{prefix}_02.png`` …
    viewport_width:
        浏览器视口宽度（CSS 像素）。
    viewport_height:
        浏览器视口高度（CSS 像素）。
    device_scale_factor:
        设备像素比（默认 2），值越大截图越清晰（2 对应 Retina 级别，3 对应极高清）。\n
        注意：图片文件大小会随该值平方级增长。
    full_page:
        是否对整个页面（含滚动区域）截图。\n
        - ``True`` → 对整个页面截图，忽略 selector 匹配的单个元素边界；\n
        - ``False``（默认）→ 对每个匹配元素逐一截图（**推荐**）。
    chrome_path:
        Google Chrome 可执行文件路径。\n
        省略时默认尝试 ``C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe``，\n
        若不可用则回退到 Playwright 内置 Chromium。

    Returns
    -------
    list[str]
        生成的 PNG 图片路径列表。

    Raises
    ------
    FileNotFoundError
        ``html_path`` 指向的文件不存在。
    ValueError
        页面中未找到匹配 ``selector`` 的元素。
    """
    url = _resolve_path(html_path)
    out_dir = _ensure_dir(output_dir)

    p, browser = _open_browser(chrome_path)
    page = browser.new_page(
        viewport={"width": viewport_width, "height": viewport_height},
        device_scale_factor=device_scale_factor,
    )

    try:
        page.goto(url)
        page.wait_for_load_state("networkidle")
        _wait_for_images(page)

        if full_page:
            # ── 整页截图（忽略 selector） ────────────────
            out_path = os.path.join(out_dir, f"{output_prefix}.png")
            page.screenshot(path=out_path, full_page=True)
            return [out_path]

        # ── 逐个元素截图 ────────────────────────────────
        elements = page.query_selector_all(selector)
        if not elements:
            raise ValueError(
                f"页面中未找到匹配选择器 {selector!r} 的元素，请检查 HTML 结构。"
            )

        result: list[str] = []
        for i, el in enumerate(elements, start=1):
            out_path = os.path.join(out_dir, f"{output_prefix}_{i:02d}.png")
            el.screenshot(path=out_path)
            result.append(out_path)

        return result

    finally:
        page.close()
        browser.close()
        p.stop()


def page_screenshot(
    html_path: str,
    output: str = "page.png",
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    device_scale_factor: float = 3,
    full_page: bool = True,
    chrome_path: Optional[str] = None,
) -> str:
    """对整个 HTML 页面截图（功能简化版，适合快速导出）。

    Parameters
    ----------
    html_path:
        本地 HTML 文件路径（支持相对路径）。
    output:
        输出 PNG 文件路径。
    viewport_width:
        浏览器视口宽度（CSS 像素）。
    viewport_height:
        浏览器视口高度（CSS 像素）。
    device_scale_factor:
        设备像素比（默认 2），值越大截图越清晰。
    full_page:
        是否截取完整滚动区域（默认 ``True``）。
    chrome_path:
        Chrome 可执行文件路径，省略时自动探测。

    Returns
    -------
    str
        生成的 PNG 文件绝对路径。
    """
    url = _resolve_path(html_path)
    out_path = str(Path(output).absolute())
    _ensure_dir(str(Path(output).parent or "."))

    p, browser = _open_browser(chrome_path)
    page = browser.new_page(
        viewport={"width": viewport_width, "height": viewport_height},
        device_scale_factor=device_scale_factor,
    )

    try:
        page.goto(url)
        page.wait_for_load_state("networkidle")
        _wait_for_images(page)
        page.screenshot(path=out_path, full_page=full_page)
        return out_path
    finally:
        page.close()
        browser.close()
        p.stop()


# ═══════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    """命令行入口。

    用法::

        python -m news_tools.screenshot report.html --selector .page -o screenshots/
        python -m news_tools.screenshot report.html --full-page -o fullpage.png
    """
    parser = argparse.ArgumentParser(
        description="将 HTML 中指定元素导出为 PNG 图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\\n"
            "  python -m news_tools.screenshot report.html --selector .page -o output/\\n"
            "  python -m news_tools.screenshot report.html --full-page -o fullpage.png\\n"
        ),
    )
    parser.add_argument("html", help="HTML 文件路径")
    parser.add_argument(
        "-s", "--selector", default=".page", help="CSS 选择器（默认 .page）"
    )
    parser.add_argument(
        "-o",
        "--output",
        default=".",
        help="输出目录（元素模式）或文件路径（整页模式）",
    )
    parser.add_argument(
        "--prefix", default="page", help="输出文件前缀（元素模式，默认 page）"
    )
    parser.add_argument("--full-page", action="store_true", help="整页截图模式")
    parser.add_argument("--width", type=int, default=1920, help="视口宽度（默认 1920）")
    parser.add_argument(
        "--height", type=int, default=1080, help="视口高度（默认 1080）"
    )
    parser.add_argument(
        "--scale", type=float, default=3.0, help="设备像素比，越高越清晰（默认 3.0）"
    )
    parser.add_argument("--chrome", default=None, help="Chrome 可执行文件路径")

    args = parser.parse_args()

    try:
        if args.full_page:
            out = page_screenshot(
                args.html,
                output=args.output,
                viewport_width=args.width,
                viewport_height=args.height,
                device_scale_factor=args.scale,
                chrome_path=args.chrome,
            )
            print(f"✅ 整页截图已保存: {out}")
        else:
            files = element_screenshot(
                args.html,
                selector=args.selector,
                output_dir=args.output,
                output_prefix=args.prefix,
                viewport_width=args.width,
                viewport_height=args.height,
                device_scale_factor=args.scale,
                chrome_path=args.chrome,
            )
            for f in files:
                print(f"✅ {f}")
            print(f"---\\n共导出 {len(files)} 张图片")
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
