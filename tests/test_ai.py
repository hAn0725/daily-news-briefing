from types import SimpleNamespace

from news_crawler.ai import AIProcessor
from news_crawler.sources import NewsItem


def test_partial_ai_response_preserves_local_classification(monkeypatch):
    config = SimpleNamespace(
        ai_cfg={"batch_size": 10, "concurrency": 1, "max_retries": 1},
        api_key="test",
        profile={},
    )
    processor = AIProcessor(config)
    monkeypatch.setattr(processor, "_chat", lambda *_: {"items": []})
    item = NewsItem(title="New AI chip announced", url="https://example.com",
                    source="source", summary="GPU performance improves")

    result = processor.process_items([item])

    assert result == [item]
    assert item.category == "tech"
    assert item.score > 0
