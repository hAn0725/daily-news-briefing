from types import SimpleNamespace

import requests

from news_crawler.netcheck import check_online, foreign_coverage
from news_crawler.sources import NewsItem, Source


def _config(network):
    return SimpleNamespace(network=network)


def test_configured_proxy_never_falls_back_to_direct(monkeypatch):
    calls = []

    def fail_proxy(*args, **kwargs):
        calls.append(kwargs.get("proxies"))
        raise requests.ConnectionError("proxy is closed")

    class ForbiddenSession:
        def __enter__(self):
            raise AssertionError("configured proxy must not fall back to direct")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(requests, "get", fail_proxy)
    monkeypatch.setattr(requests, "Session", ForbiddenSession)

    config = _config({
        "proxy": "http://127.0.0.1:7892",
        "check_urls": ["https://www.google.com/generate_204"],
    })
    assert check_online(config, quiet=True) is False
    assert calls == [{
        "http": "http://127.0.0.1:7892",
        "https": "http://127.0.0.1:7892",
    }]


def test_probe_requires_expected_status(monkeypatch):
    response = SimpleNamespace(status_code=200)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    config = _config({
        "proxy": "http://127.0.0.1:7892",
        "check_urls": ["https://www.google.com/generate_204"],
        "check_statuses": [204],
    })

    assert check_online(config, quiet=True) is False


def test_foreign_coverage_blocks_domestic_only_report():
    sources = [
        Source(name="国内", category="tech", type="rss",
               url="https://cn.example/feed", language="zh"),
        Source(name="海外一", category="world", type="rss",
               url="https://one.example/feed", language="en"),
        Source(name="海外二", category="world", type="rss",
               url="https://two.example/feed", language="en"),
    ]
    items = [NewsItem(title="国内新闻", url="https://cn.example/1",
                      source="国内", language="zh")]
    config = _config({"require_foreign_news": True,
                      "min_foreign_sources": 2,
                      "min_foreign_items": 2})

    assert foreign_coverage(config, sources, items) == (False, 0, 0)


def test_foreign_coverage_accepts_required_sources_and_items():
    sources = [
        Source(name="海外一", category="world", type="rss",
               url="https://one.example/feed", language="en"),
        Source(name="海外二", category="world", type="rss",
               url="https://two.example/feed", language="en"),
    ]
    items = [
        NewsItem(title="A", url="https://one.example/1",
                 source="海外一", language="en"),
        NewsItem(title="B", url="https://two.example/1",
                 source="海外二", language="en"),
    ]
    config = _config({"require_foreign_news": True,
                      "min_foreign_sources": 2,
                      "min_foreign_items": 2})

    assert foreign_coverage(config, sources, items) == (True, 2, 2)
