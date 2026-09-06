from types import SimpleNamespace

import pytest

from news_crawler import ai
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


def test_bigmodel_compatible_request(monkeypatch):
    sent = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"items": []}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3,
                          "total_tokens": 5},
            }

    def fake_post(url, **kwargs):
        sent["url"] = url
        sent["payload"] = kwargs["json"]
        sent["authorization"] = kwargs["headers"]["Authorization"]
        return Response()

    monkeypatch.setattr(ai.requests, "post", fake_post)
    config = SimpleNamespace(
        ai_cfg={
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4.7-flash",
            "thinking": "disabled",
            "batch_size": 10,
            "concurrency": 1,
            "max_retries": 1,
        },
        api_key="secret-test-key",
        profile={},
    )

    processor = AIProcessor(config)
    assert processor._chat("system", "user") == {"items": []}
    assert sent["url"].endswith("/api/paas/v4/chat/completions")
    assert sent["payload"]["model"] == "glm-4.7-flash"
    assert sent["payload"]["thinking"] == {"type": "disabled"}
    assert sent["payload"]["response_format"] == {"type": "json_object"}
    assert sent["authorization"] == "Bearer secret-test-key"
    assert processor.get_usage()["total_tokens"] == 5


def test_required_ai_refuses_local_batch_fallback(monkeypatch):
    config = SimpleNamespace(
        ai_cfg={"batch_size": 10, "concurrency": 1, "max_retries": 1,
                "required": True},
        api_key="test",
        profile={},
    )
    processor = AIProcessor(config)
    monkeypatch.setattr(
        processor, "_chat",
        lambda *_: (_ for _ in ()).throw(RuntimeError("rate limited")))
    item = NewsItem(title="AI news", url="https://example.com",
                    source="source")

    with pytest.raises(RuntimeError, match="禁止本地降级"):
        processor.process_items([item])
