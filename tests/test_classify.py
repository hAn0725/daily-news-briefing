from news_crawler.classify import classify_item
from news_crawler.sources import NewsItem


def test_science_news_has_its_own_category():
    item = NewsItem(
        title="Scientists report new optics experiment",
        url="https://example.com/research",
        source="Nature",
        summary="A university research paper describes the physics experiment.",
    )

    assert classify_item(item) == "science"
