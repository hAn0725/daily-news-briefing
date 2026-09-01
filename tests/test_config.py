import pytest

from news_crawler.config import Config, ConfigError


def test_config_rejects_non_http_source(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "report: {}\nnetwork: {}\nai: {}\nemail: {}\nschedule: {}\n"
        "user_profile: {}\nsources:\n  - type: rss\n    url: file:///tmp/feed.xml\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="HTTP"):
        Config(str(path))
