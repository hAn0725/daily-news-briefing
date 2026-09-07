from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from news_crawler import main
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
