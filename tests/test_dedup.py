from news_crawler.dedup import dedup_items
from news_crawler.sources import NewsItem


def test_dedup_keeps_higher_scored_duplicate():
    lower = NewsItem(title="Nvidia launches new AI chip", url="https://a", source="a",
                     score=2)
    higher = NewsItem(title="Nvidia launches a new AI chip", url="https://b", source="b",
                      score=5)

    result = dedup_items([lower, higher], threshold=0.85, prefer_score=True)

    assert result == [higher]


def test_dedup_keeps_short_titles_without_comparison():
    items = [NewsItem(title="AI", url="https://a", source="a"),
             NewsItem(title="AI", url="https://b", source="b")]

    assert dedup_items(items) == items
