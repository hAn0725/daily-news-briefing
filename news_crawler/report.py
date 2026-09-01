"""报告生成：邮件 PDF 日报与本地护眼 HTML 备份。"""
import html
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

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
        generate_pdf_report(config, date_str, grouped, summary, market,
                            pdf_path, ai_usage=ai_usage, ai_cost=ai_cost)
        paths.append(pdf_path)
    if not pdf_cfg.get("keep_html", True):
        html_path.unlink(missing_ok=True)
        paths.remove(html_path)
    return paths


def _pdf_text(value) -> str:
    """Escape text for ReportLab's Paragraph markup without losing line breaks."""
    return xml_escape(_clean_text(value)).replace("\n", "<br/>")


_PDF_FONT_NAME = None


def _register_pdf_font() -> str:
    """Prefer an embedded Windows CJK font; fall back to a standard CID font."""
    global _PDF_FONT_NAME
    if _PDF_FONT_NAME:
        return _PDF_FONT_NAME

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("msyh.ttc", "simsun.ttc", "simhei.ttf"):
        font_path = fonts_dir / filename
        if not font_path.is_file():
            continue
        try:
            pdfmetrics.registerFont(
                TTFont("NewsCJK", str(font_path), subfontIndex=0))
            _PDF_FONT_NAME = "NewsCJK"
            return _PDF_FONT_NAME
        except Exception:  # noqa: BLE001
            continue

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _PDF_FONT_NAME = "STSong-Light"
    return _PDF_FONT_NAME


def _pdf_styles(font_name: str):
    """Build a small, self-contained Chinese PDF style system."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("NewsTitle", parent=base["Title"],
                                fontName=font_name, fontSize=19,
                                leading=27, textColor=colors.HexColor("#1f2937"),
                                spaceAfter=5),
        "meta": ParagraphStyle("NewsMeta", parent=base["Normal"],
                               fontName=font_name, fontSize=8.5, leading=13,
                               textColor=colors.HexColor("#64748b")),
        "section": ParagraphStyle("NewsSection", parent=base["Heading2"],
                                  fontName=font_name, fontSize=14,
                                  leading=20, textColor=colors.HexColor("#1e3a5f"),
                                  spaceBefore=15, spaceAfter=5),
        "item_title": ParagraphStyle("NewsItemTitle", parent=base["Heading3"],
                                     fontName=font_name, fontSize=11.5,
                                     leading=16, textColor=colors.HexColor("#1f2937"),
                                     spaceAfter=4),
        "body": ParagraphStyle("NewsBody", parent=base["BodyText"],
                               fontName=font_name, fontSize=9.5, leading=15,
                               textColor=colors.HexColor("#334155"),
                               spaceAfter=5),
        "small": ParagraphStyle("NewsSmall", parent=base["Normal"],
                                fontName=font_name, fontSize=8, leading=11,
                                textColor=colors.HexColor("#64748b")),
        "summary": ParagraphStyle("NewsSummary", parent=base["BodyText"],
                                  fontName=font_name, fontSize=10,
                                  leading=16, textColor=colors.HexColor("#1f2937"),
                                  borderColor=colors.HexColor("#93b4cf"),
                                  borderWidth=0.8, borderPadding=10,
                                  backColor=colors.HexColor("#f3f7fa"),
                                  spaceBefore=8, spaceAfter=10),
        "center": ParagraphStyle("NewsCenter", parent=base["Normal"],
                                 fontName=font_name, fontSize=8, leading=11,
                                 alignment=TA_CENTER,
                                 textColor=colors.HexColor("#64748b")),
    }


def _pdf_footer(canvas, doc):
    from reportlab.lib import colors

    font_name = _register_pdf_font()
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.line(doc.leftMargin, 30, doc.pagesize[0] - doc.rightMargin, 30)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.setFont(font_name, 8)
    canvas.drawString(doc.leftMargin, 18, "每日新闻简报")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 18,
                           f"第 {doc.page} 页")
    canvas.restoreState()


def generate_pdf_report(config, date_str, grouped, summary, market, pdf_path,
                        ai_usage=None, ai_cost=0.0):
    """Create the PDF sent by email; HTML remains an optional local backup."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("缺少 PDF 依赖，请运行 pip install -r requirements.txt") from exc

    font_name = _register_pdf_font()
    styles = _pdf_styles(font_name)
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=17 * mm, rightMargin=17 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm,
                            title=f"每日新闻简报 {date_str}",
                            author="news_crawler")
    story = [
        Paragraph("DAILY NEWS BRIEFING", styles["meta"]),
        Paragraph(f"每日新闻简报 - {date_str}", styles["title"]),
        Paragraph(f"生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                  "按关注领域自动整理", styles["meta"]),
        Spacer(1, 8),
    ]
    if market:
        story.append(Paragraph("财经数据速览", styles["section"]))
        data = [["名称", "最新", "涨跌", "涨跌幅"]]
        for item in market:
            pct = item.get("change_pct")
            chg = item.get("change")
            data.append([
                _pdf_text(item.get("name")),
                _pdf_text(item.get("price")),
                "-" if chg is None else f"{chg:+.2f}",
                "-" if pct is None else f"{pct:+.2f}%",
            ])
        table = Table(data, colWidths=[50 * mm, 34 * mm, 32 * mm, 32 * mm],
                      repeatRows=1)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("LEADING", (0, 0), (-1, -1), 12),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eef5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 4)])
    if summary:
        story.extend([
            Paragraph("今日要闻综述", styles["section"]),
            Paragraph(_pdf_text(summary), styles["summary"]),
        ])

    for cat, cfg in config.categories.items():
        items = grouped.get(cat, [])
        title = _pdf_text(cfg.get("title", cat))
        story.append(Paragraph(f"{title}（{len(items)} 条）", styles["section"]))
        if not items:
            story.append(Paragraph("今日暂无该分类新闻。", styles["body"]))
            continue
        for item in items:
            block = [Paragraph(_pdf_text(item.display_title),
                               styles["item_title"])]
            if item.en_original:
                block.append(Paragraph(_pdf_text(item.en_original),
                                       styles["small"]))
            block.append(Paragraph(_pdf_text(item.cn_summary), styles["body"]))
            meta = f"来源：{_pdf_text(item.source)}"
            if item.published:
                meta += f" | {item.published.strftime('%m-%d %H:%M')}"
            if item.score:
                meta += f" | 相关度：{item.score}/5"
            url = html.escape(item.url, quote=True)
            meta += f' | <link href="{url}">原文链接</link>'
            block.extend([Paragraph(meta, styles["small"]), Spacer(1, 5)])
            story.append(KeepTogether(block))

    total = sum(len(v) for v in grouped.values())
    usage = "本次未使用 AI（本地模式）"
    if ai_usage:
        usage = (f"本次 AI 用量 {ai_usage['total_tokens']} tokens，"
                 f"估算费用 ¥{ai_cost:.2f}")
    story.extend([
        Spacer(1, 8),
        Paragraph(f"共 {total} 条新闻 | 覆盖 {len(config.sources)} 个新闻源 | {usage}",
                  styles["center"]),
    ])
    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
