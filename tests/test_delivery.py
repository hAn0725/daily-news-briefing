from news_crawler.delivery import already_sent, mark_sent, report_fingerprint
from news_crawler.sources import NewsItem


def test_delivery_state_is_content_aware(tmp_path):
    state = tmp_path / "delivery_state.json"
    item = NewsItem(title="A", url="https://example.com/a", source="source",
                    cn_summary="summary", category="tech")
    grouped = {"tech": [item]}
    first = report_fingerprint(grouped, "daily summary", [])

    assert not already_sent(state, "2026-08-31", first)
    mark_sent(state, "2026-08-31", first)
    assert already_sent(state, "2026-08-31", first)

    item.cn_summary = "updated"
    updated = report_fingerprint(grouped, "daily summary", [])
    assert updated != first
    assert not already_sent(state, "2026-08-31", updated)
