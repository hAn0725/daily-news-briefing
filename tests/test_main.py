from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from news_crawler import main
from news_crawler.main import apply_ai_duplicate_groups, select_diverse_items
from news_crawler.sources import NewsItem, Source


def test_run_returns_failure_when_report_is_saved_but_email_fails(
    monkeypatch, tmp_path
):
    source = Source(
        name="Example", category="tech", type="rss",
        url="https://example.com/feed",
    )
    config = SimpleNamespace(
        report={
            "hours_back": 26,
            "fulltext_cap": 0,
            "logs_dir": "logs",
            "keep_days": 30,
        },
        network={},
        ai_cfg={},
        schedule={},
        profile={},
        categories={"tech": {"title": "科技", "max_items": 8}},
        sources=[source],
        ai_enabled=False,
    )
    item = NewsItem(
        title="Test news",
        url="https://example.com/news",
        source=source.name,
        summary="Test summary",
        published=datetime.now(ZoneInfo("Asia/Shanghai")),
    )

    monkeypatch.setattr(main, "Config", lambda _path: config)
    monkeypatch.setattr(main, "setup_logging", lambda *_args: None)
    monkeypatch.setattr(
        main, "Fetcher", lambda _config: SimpleNamespace(
            fetch_source=lambda _source: [item]
        )
    )
    monkeypatch.setattr(main, "foreign_coverage", lambda *_args: (True, 1, 1))
    monkeypatch.setattr(main, "fetch_market_data", lambda _config: [])
    monkeypatch.setattr(
        main,
        "generate_report",
        lambda *_args, **_kwargs: [tmp_path / "report.html", tmp_path / "report.pdf"],
    )
    monkeypatch.setattr(main, "already_sent", lambda *_args: False)
    monkeypatch.setattr(main, "send_report_email", lambda *_args, **_kwargs: (False, "SMTP failed"))
    monkeypatch.setattr(main, "cleanup_old", lambda *_args: None)

    args = SimpleNamespace(
        config="",
        date="2026-09-07",
        wait_net=False,
        no_ai=True,
        no_market=True,
        no_mail=False,
        resend_mail=False,
    )

    assert main.run(args) == 5


def test_ai_dedup_accepts_small_disjoint_cross_source_group():
    items = [
        NewsItem(title="same event a", url="https://a", source="A",
                 category="world", score=2),
        NewsItem(title="same event b", url="https://b", source="B",
                 category="world", score=5),
        NewsItem(title="different", url="https://c", source="C",
                 category="world", score=3),
    ]

    result, stats = apply_ai_duplicate_groups(
        items, [[0, 1]], max_drop_ratio=0.50)

    assert result == [items[1], items[2]]
    assert stats["dropped"] == 1
    assert not stats["guarded"]


def test_ai_dedup_rejects_large_same_source_and_overlapping_groups():
    items = [
        NewsItem(title=str(i), url=f"https://example.com/{i}",
                 source=("A" if i < 2 else chr(65 + i)),
                 category="tech", score=i)
        for i in range(6)
    ]

    result, stats = apply_ai_duplicate_groups(
        items, [[0, 1], [2, 3], [3, 4]], max_group_size=4,
        max_drop_ratio=0.50)

    assert result == [items[0], items[1], items[3], items[4], items[5]]
    assert stats["accepted"] == 1
    assert stats["rejected"] == 2


def test_ai_dedup_safety_valve_rejects_excessive_total_deletion():
    items = [
        NewsItem(title=str(i), url=f"https://example.com/{i}",
                 source=f"S{i}", category="world", score=i)
        for i in range(10)
    ]

    result, stats = apply_ai_duplicate_groups(
        items, [[0, 1], [2, 3], [4, 5], [6, 7]], max_drop_ratio=0.30)

    assert result == items
    assert stats["guarded"]
    assert stats["dropped"] == 0


def test_report_selection_prefers_source_diversity_and_backfills():
    items = [
        NewsItem(title=f"A{i}", url=f"https://a/{i}", source="A")
        for i in range(5)
    ] + [
        NewsItem(title="B", url="https://b", source="B"),
        NewsItem(title="C", url="https://c", source="C"),
    ]

    result = select_diverse_items(items, limit=6, per_source_limit=2)

    assert [item.source for item in result[:4]] == ["A", "A", "B", "C"]
    assert len(result) == 6
