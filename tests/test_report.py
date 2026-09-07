from types import SimpleNamespace

from news_crawler.report import _safe_link, build_html
from news_crawler.sources import NewsItem


def test_html_escapes_external_content():
    config = SimpleNamespace(categories={"tech": {"title": "科技"}}, sources=[])
    item = NewsItem(title="<script>alert(1)</script>", url="https://example.com?a=1&b=2",
                    source="<bad>", cn_summary="<b>unsafe</b>", category="tech")

    result = build_html(config, "2026-08-31", {"tech": [item]}, "", [])

    assert "&lt;script&gt;" in result
    assert "https://example.com?a=1&amp;b=2" in result


def test_html_decodes_nested_feed_entities():
    config = SimpleNamespace(categories={"tech": {"title": "Tech"}}, sources=[])
    item = NewsItem(title="Debian won&#8217;t ban AI", url="https://example.com",
                    source="source", cn_summary="summary", category="tech")

    result = build_html(config, "2026-09-01", {"tech": [item]}, "", [])

    assert "won&amp;#8217;t" not in result
    assert "Debian won&#x27;t ban AI" in result


def test_safe_link_rejects_non_web_schemes():
    assert _safe_link("https://example.com/news?a=1&b=2") == (
        "https://example.com/news?a=1&amp;b=2"
    )
    assert _safe_link("javascript:alert(1)") == "#"
    assert _safe_link("file:///C:/secret.txt") == "#"


def test_footer_reports_sources_actually_used():
    config = SimpleNamespace(
        categories={"tech": {"title": "Tech"}},
        sources=[SimpleNamespace(name=name) for name in ("A", "B", "C")],
    )
    item = NewsItem(title="news", url="https://example.com", source="A",
                    cn_summary="summary", category="tech")

    result = build_html(config, "2026-09-07", {"tech": [item]}, "", [])

    assert "实际采用 1 个来源（配置 3 个）" in result
