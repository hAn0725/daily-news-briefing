from news_crawler.delivery import (
    already_sent,
    delivered_on,
    mark_sent,
    record_delivery,
    report_fingerprint,
)
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


def test_delivered_on_and_manual_resend_record(tmp_path):
    """手动补发（无内容指纹）也要算作已送达，否则看门狗会误报告警。"""
    state = tmp_path / "delivery_state.json"

    assert not delivered_on(state, "2026-09-10")
    record_delivery(state, "2026-09-10", note="tools/resend.py 手动补发")

    assert delivered_on(state, "2026-09-10")
    assert not delivered_on(state, "2026-09-11")
    # 手动补发记录的指纹是哨兵值，不冒充真实内容指纹
    assert not already_sent(state, "2026-09-10", "some-real-fingerprint")
