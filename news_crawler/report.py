"""报告生成：护眼 HTML，以及由浏览器直接打印该 HTML 得到的 PDF。"""
import html
import shutil
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

CAT_META = {
    "finance": {"icon": "📈", "sub": "行情 · 持仓板块 · 宏观政策"},
    "tech": {"icon": "💡", "sub": "半导体 · AI · 光电 · 学术科研"},
    "world": {"icon": "🌍", "sub": "地缘 · 贸易 · 国际大事"},
}

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
       color:#c7ccd4; background:#171a1f; line-height:1.75; }
.page { max-width:800px; margin:0 auto; padding:10px 6px; }
.header { border-bottom:3px solid #5b7f9e; padding-bottom:16px; margin-bottom:22px; }
.header .brand { color:#7ba0bf; font-size:12px; letter-spacing:3px; font-weight:600; }
.header h1 { font-size:25px; color:#e2e6ec; margin-top:6px; }
.header .meta { color:#7d828c; font-size:12px; margin-top:6px; }
.summary-box { background:#20242b; border-left:4px solid #5b7f9e;
               padding:14px 18px; border-radius:0 8px 8px 0;
               margin:18px 0 26px; page-break-inside:avoid; }
.summary-box h3 { color:#8fb2d0; font-size:15px; margin-bottom:6px; }
.summary-box p { font-size:14px; color:#b8bec8; }
table.market { width:100%; border-collapse:collapse; margin:12px 0 26px; font-size:13px; }
table.market th { background:#2a3340; color:#d9dee6; padding:8px 10px; text-align:left; }
table.market td { padding:7px 10px; border-bottom:1px solid #2b2f37; }
table.market tr:nth-child(even) td { background:#1d2127; }
.up { color:#e2827a; } .down { color:#82bd9e; } .flat { color:#8b909a; }
h2.section { font-size:19px; color:#e2e6ec; border-left:5px solid #5b7f9e;
             padding-left:12px; margin:30px 0 4px; page-break-after:avoid; }
h2.section .icon { margin-right:6px; }
.section-sub { color:#7d828c; font-size:12px; margin-bottom:14px; padding-left:17px; }
.item { border:1px solid #2e333c; border-radius:8px; padding:12px 16px;
        margin-bottom:12px; page-break-inside:avoid; background:#1f232a; }
.item .t { font-size:15px; color:#e2e6ec; font-weight:600; }
.item .t .en { display:block; color:#6f757f; font-size:12px; font-weight:400;
               margin-top:2px; }
.item .s { font-size:13.5px; color:#b8bec8; margin-top:6px; }
.item .m { font-size:11.5px; color:#7d828c; margin-top:8px; display:flex;
           gap:12px; flex-wrap:wrap; }
.tag { display:inline-block; background:#2a3340; color:#8fb2d0;
       padding:1px 9px; border-radius:10px; font-size:11px; }
.tag.hot { background:#3a2a27; color:#e89a87; }
.item .m a { color:#8fb2d0; text-decoration:none; }
.footer { margin-top:34px; padding-top:14px; border-top:1px solid #2b2f37;
          color:#5f646d; font-size:11px; text-align:center; }
.empty { color:#5f646d; font-size:13px; padding:8px 0 20px; }
@page { size:A4; margin:10mm 9mm; }
@media print {
  html, body { background:#171a1f !important; }
  body { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  .page { max-width:none; padding:0; }
  .footer { display:none; }
}
"""


def _clean_text(value) -> str:
    """Decode feed entities and normalize punctuation for HTML and PDF output."""
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    return text.replace("’", "'").replace("‘", "'")


def _esc(value) -> str:
    return html.escape(_clean_text(value), quote=True)


def _fmt_time(item):
    if item.published:
        return item.published.strftime("%m-%d %H:%M")
    return ""


def _market_html(market) -> str:
    if not market:
        return ("<div class='empty'>财经数据暂不可用。</div>")
    rows = []
    for m in market:
        pct = m.get("change_pct")
        cls = "flat"
        if pct is not None:
            cls = "up" if pct >= 0 else "down"
        pct_txt = f"{pct:+.2f}%" if pct is not None else "—"
        chg_txt = f"{m['change']:+.2f}" if m.get("change") is not None else "—"
        rows.append(
            f"<tr><td>{_esc(m['name'])}</td><td>{m['price']}</td>"
            f"<td class='{cls}'>{chg_txt}</td><td class='{cls}'>{pct_txt}</td></tr>"
        )
    return (
        "<table class='market'><thead><tr><th>名称</th><th>最新</th>"
        "<th>涨跌</th><th>涨跌幅</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _item_html(item) -> str:
    t = _esc(item.display_title)
    en = ""
    if item.en_original:
        en = f"<span class='en'>{_esc(item.en_original)}</span>"
    summary = _esc(item.cn_summary)
    source = _esc(item.source)
    ttime = _esc(_fmt_time(item))
    link = html.escape(item.url, quote=True)
    hot_tag = ""
    if item.score >= 5:
        hot_tag = "<span class='tag hot'>★ 重点</span>"
    elif item.score >= 4:
        hot_tag = "<span class='tag'>相关</span>"
    meta = [f"<span class='tag'>{source}</span>"]
    if ttime:
        meta.append(f"<span>{ttime}</span>")
    if hot_tag:
        meta.append(hot_tag)
    meta.append(f"<a href='{link}'>原文链接 ↗</a>")
    return (
        f"<div class='item'><div class='t'>{t}{en}</div>"
        f"<div class='s'>{summary}</div>"
        f"<div class='m'>{' '.join(meta)}</div></div>"
    )


def build_html(config, date_str, grouped, summary, market,
               ai_usage=None, ai_cost=0.0) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cats_cfg = config.categories

    parts = [f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
             f"<title>每日新闻简报 {date_str}</title>"
             f"<style>{CSS}</style></head><body><div class='page'>"]

    # 头部
    parts.append(
        f"<div class='header'><div class='brand'>DAILY NEWS BRIEFING</div>"
        f"<h1>每日新闻简报 · {date_str}</h1>"
        f"<div class='meta'>生成时间 {now} · 按你的关注领域整理 · 国外新闻双语对照</div>"
        "</div>"
    )

    # 财经数据速览
    parts.append("<h2 class='section'><span class='icon'>📊</span>财经数据速览</h2>")
    parts.append(_market_html(market))

    # 今日要闻综述
    if summary:
        parts.append(
            "<div class='summary-box'><h3>📌 今日要闻综述</h3>"
            f"<p>{_esc(summary)}</p></div>"
        )

    # 各分类
    for cat, cfg in cats_cfg.items():
        meta = CAT_META.get(cat, {"icon": "📰", "sub": ""})
        title = cfg.get("title", cat)
        items = grouped.get(cat, [])
        parts.append(
            f"<h2 class='section'><span class='icon'>{meta['icon']}</span>{_esc(title)}"
            f"<span style='color:#7d828c;font-size:12px;'>（{len(items)} 条）</span></h2>"
        )
        if meta.get("sub"):
            parts.append(f"<div class='section-sub'>{_esc(meta['sub'])}</div>")
        if not items:
            parts.append("<div class='empty'>今日暂无该分类新闻。</div>")
        else:
            for it in items:
                parts.append(_item_html(it))

    # 页脚
    total = sum(len(v) for v in grouped.values())
    src_count = len(config.sources)
    if ai_usage:
        usage_txt = (f"本次消耗 {ai_usage['total_tokens']} tokens"
                     f"（输入 {ai_usage['prompt_tokens']} / "
                     f"输出 {ai_usage['completion_tokens']}），约 ¥{ai_cost:.2f}")
    else:
        usage_txt = "本次未使用 AI（本地模式）"
    parts.append(
        f"<div class='footer'>共 {total} 条新闻 · 覆盖 {src_count} 个新闻源 · "
        f"由 AI 自动整理 · {usage_txt}</div>"
    )

    parts.append("</div></body></html>")
    return "".join(parts)


def generate_report(config, date_str, grouped, summary, market, out_dir,
                    ai_usage=None, ai_cost=0.0):
    month_dir = Path(out_dir) / date_str[:7]
    month_dir.mkdir(parents=True, exist_ok=True)
    html_str = build_html(config, date_str, grouped, summary, market,
                          ai_usage=ai_usage, ai_cost=ai_cost)
    html_path = month_dir / f"{date_str}.html"
    html_path.write_text(html_str, encoding="utf-8")
    paths = [html_path]
    pdf_cfg = config.report.get("pdf", {}) or {}
    if pdf_cfg.get("enabled", True):
        pdf_path = month_dir / f"{date_str}.pdf"
        generate_pdf_from_html(html_path, pdf_path)
        paths.append(pdf_path)
    if not pdf_cfg.get("keep_html", True):
        html_path.unlink(missing_ok=True)
        paths.remove(html_path)
    return paths


def _find_browser() -> Path:
    """Return a Chromium browser that supports headless PDF printing."""
    candidates = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    ]
    for name in (
            "chrome", "google-chrome", "chromium", "chromium-browser",
            "msedge"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "无法生成 PDF：未找到 Chrome、Edge 或 Chromium 浏览器。")


def generate_pdf_from_html(html_path, pdf_path, browser_path=None):
    """Capture the HTML as a long image and paginate it into an A4 PDF."""
    html_path = Path(html_path).resolve()
    pdf_path = Path(pdf_path).resolve()
    if not html_path.is_file():
        raise FileNotFoundError(html_path)
    browser = Path(browser_path).resolve() if browser_path else _find_browser()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="news-pdf-browser-") as folder:
        folder_path = Path(folder)
        screenshot_path = _capture_long_screenshot(
            browser, html_path, folder_path)
        rendered_pdf = folder_path / "rendered.pdf"
        _image_to_paginated_pdf(screenshot_path, rendered_pdf, html_path.stem)
        if (rendered_pdf.stat().st_size < 1000 or
                not rendered_pdf.read_bytes().startswith(b"%PDF-")):
            raise RuntimeError(f"图片分页生成的 PDF 无效：{rendered_pdf}")
        shutil.copy2(rendered_pdf, pdf_path)


def _capture_long_screenshot(browser: Path, html_path: Path,
                             folder: Path) -> Path:
    """Capture the complete report, growing the viewport if necessary."""
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("缺少图片型 PDF 依赖，请运行 pip install -r requirements.txt") from exc

    scale = 2
    screenshot_path = folder / "report.png"
    for viewport_height in (8000, 12000, 16000):
        screenshot_path.unlink(missing_ok=True)
        profile = folder / f"profile-{viewport_height}"
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--force-device-scale-factor={scale}",
            f"--user-data-dir={profile}",
            f"--window-size=900,{viewport_height}",
            f"--screenshot={screenshot_path}",
            html_path.as_uri(),
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, check=False)
        if result.returncode != 0 or not screenshot_path.is_file():
            detail = (result.stderr or result.stdout or "未知错误").strip()
            raise RuntimeError(
                f"浏览器截取 HTML 长图失败（退出码 {result.returncode}）："
                f"{detail}")

        with Image.open(screenshot_path) as source:
            image = source.convert("RGB")
            background = Image.new("RGB", image.size, (23, 26, 31))
            bbox = ImageChops.difference(image, background).getbbox()
            if bbox is None:
                raise RuntimeError("浏览器截图为空，未检测到日报内容")
            content_bottom = min(image.height, bbox[3] + 80 * scale)
            if content_bottom < image.height - 100 * scale:
                cropped = image.crop((0, 0, image.width, content_bottom))
                cropped.save(screenshot_path, format="PNG", optimize=True)
                return screenshot_path

    raise RuntimeError("HTML 内容超过截图上限，请减少单日新闻条数")


def _find_page_cut(image, start: int, target: int,
                   background=(23, 26, 31)) -> int:
    """Move a page cut upward to the nearest gap between report cards."""
    pixels = image.load()
    width = image.width
    lower = start + int((target - start) * 0.65)
    min_blank_run = max(8, width // 180)

    def row_is_blank(y):
        for x in range(0, width, 8):
            pixel = pixels[x, y]
            if any(abs(pixel[i] - background[i]) > 3 for i in range(3)):
                return False
        return True

    run_end = None
    for y in range(target - 1, lower - 1, -1):
        if row_is_blank(y):
            if run_end is None:
                run_end = y
        elif run_end is not None:
            run_start = y + 1
            if run_end - run_start + 1 >= min_blank_run:
                return (run_start + run_end) // 2
            run_end = None
    return target


def _image_to_paginated_pdf(screenshot_path: Path, pdf_path: Path,
                            title: str):
    """Slice a long screenshot at visual gaps and place slices on A4 pages."""
    try:
        import pymupdf
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少图片型 PDF 依赖，请运行 pip install -r requirements.txt") from exc

    with Image.open(screenshot_path) as source:
        image = source.convert("RGB")
    page_height = round(image.width * 297 / 210)
    slices = []
    start = 0
    while image.height - start > page_height:
        target = start + page_height
        cut = _find_page_cut(image, start, target)
        slices.append((start, cut))
        start = cut
    slices.append((start, image.height))

    document = pymupdf.open()
    try:
        for top, bottom in slices:
            page_image = Image.new(
                "RGB", (image.width, page_height), (23, 26, 31))
            segment = image.crop((0, top, image.width, bottom))
            page_image.paste(segment, (0, 0))
            buffer = BytesIO()
            page_image.save(buffer, format="PNG", optimize=True)
            page = document.new_page(width=595.28, height=841.89)
            page.insert_image(page.rect, stream=buffer.getvalue())
        document.set_metadata({"title": f"每日新闻简报 {title}"})
        document.save(pdf_path, garbage=4, deflate=True)
    finally:
        document.close()


def generate_pdf_report(config, date_str, grouped, summary, market, pdf_path,
                        ai_usage=None, ai_cost=0.0):
    """Compatibility wrapper that also uses HTML as the sole PDF source."""
    html_str = build_html(config, date_str, grouped, summary, market,
                          ai_usage=ai_usage, ai_cost=ai_cost)
    pdf_path = Path(pdf_path)
    temp_root = Path(__file__).resolve().parents[1] / "tmp" / "pdfs"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="report-", dir=temp_root) as folder:
        html_path = Path(folder) / f"{date_str}.html"
        html_path.write_text(html_str, encoding="utf-8")
        generate_pdf_from_html(html_path, pdf_path)
