"""报告生成：简约护眼风 HTML 报告"""
import html
from datetime import datetime
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
"""


def _esc(s) -> str:
    return html.escape(s or "", quote=True)


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
    return [html_path]
