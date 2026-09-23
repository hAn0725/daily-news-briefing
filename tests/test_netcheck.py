from types import SimpleNamespace

import requests

from news_crawler.netcheck import check_online, foreign_coverage
from news_crawler.sources import NewsItem, Source


def _config(network):
    return SimpleNamespace(network=network)


def test_configured_proxy_never_falls_back_to_direct(monkeypatch):
    calls = []
    monkeypatch.setattr("news_crawler.netcheck.time.sleep", lambda s: None)

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
    # 每个探针默认尝试 2 次（应对节点随机抖动）
    assert calls == [{
        "http": "http://127.0.0.1:7892",
        "https": "http://127.0.0.1:7892",
    }] * 2


def test_probe_retries_then_succeeds(monkeypatch):
    """节点随机抖动：第一次超时、第二次 204 → 应判定联网成功。"""
    calls = []
    monkeypatch.setattr("news_crawler.netcheck.time.sleep", lambda s: None)
    ok = SimpleNamespace(status_code=204)

    def flaky(*args, **kwargs):
        calls.append(kwargs.get("proxies"))
        if len(calls) == 1:
            raise requests.Timeout("read timed out")
        return ok

    monkeypatch.setattr(requests, "get", flaky)
    config = _config({
        "proxy": "http://127.0.0.1:7892",
        "check_urls": ["https://www.google.com/generate_204"],
    })
    assert check_online(config, quiet=True) is True
    assert len(calls) == 2


def test_attempts_configurable(monkeypatch):
    calls = []
    monkeypatch.setattr("news_crawler.netcheck.time.sleep", lambda s: None)

    def fail(*args, **kwargs):
        calls.append(1)
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", fail)
    config = _config({
        "proxy": "http://127.0.0.1:7892",
        "check_attempts": 1,
        "check_urls": [
            "https://www.google.com/generate_204",
            "https://cp.cloudflare.com/generate_204",
        ],
    })
    assert check_online(config, quiet=True) is False
    # attempts=1：两个探针地址各试一次
    assert len(calls) == 2


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


def test_resolve_proxy_switches_to_working_candidate(monkeypatch):
    """配置端口未监听时，应自动切换到第一个“监听+探针通过”的候选。"""
    from news_crawler import netcheck

    def listening(proxy, timeout=2.0):
        # 配置的 7892 挂了，7897（系统代理）开着
        return "7892" not in proxy

    probed = []
    monkeypatch.setattr(netcheck, "_proxy_listening", listening)
    monkeypatch.setattr(netcheck, "_windows_system_proxy",
                        lambda: "http://127.0.0.1:7897")

    def probe(config, proxy, timeout=None):
        probed.append(proxy)
        return proxy.endswith(":7897")

    monkeypatch.setattr(netcheck, "_probe_proxy", probe)
    config = _config({
        "proxy": "http://127.0.0.1:7892",
        "check_urls": ["https://www.google.com/generate_204"],
    })

    assert netcheck.resolve_proxy(config) == "http://127.0.0.1:7897"
    # 进程内生效：后续抓取/检测都用新端口
    assert config.network["proxy"] == "http://127.0.0.1:7897"
    # 7892 端口没开，不应浪费探针；7897 通过后立即停止
    assert probed == ["http://127.0.0.1:7897"]


def test_resolve_proxy_keeps_config_when_all_candidates_fail(monkeypatch):
    """全都不可用时保持原配置（交给 netcheck 重试并诊断），不乱改。"""
    from news_crawler import netcheck

    monkeypatch.setattr(netcheck, "_proxy_listening",
                        lambda proxy, timeout=2.0: True)
    monkeypatch.setattr(netcheck, "_windows_system_proxy", lambda: "")
    monkeypatch.setattr(netcheck, "_probe_proxy",
                        lambda config, proxy, timeout=None: False)
    config = _config({"proxy": "http://127.0.0.1:7892",
                      "check_urls": ["https://www.google.com/generate_204"]})

    assert netcheck.resolve_proxy(config) == "http://127.0.0.1:7892"
    assert config.network["proxy"] == "http://127.0.0.1:7892"


def test_resolve_proxy_disabled_and_direct_mode(monkeypatch):
    """auto_detect_proxy=false 只试配置值；未配置 proxy（直连）不干预。"""
    from news_crawler import netcheck

    calls = []
    monkeypatch.setattr(netcheck, "_proxy_listening",
                        lambda proxy, timeout=2.0: calls.append(proxy) or False)
    monkeypatch.setattr(netcheck, "_windows_system_proxy",
                        lambda: "http://127.0.0.1:7897")

    off = _config({"proxy": "http://127.0.0.1:7892",
                   "auto_detect_proxy": False})
    assert netcheck.resolve_proxy(off) == "http://127.0.0.1:7892"
    # 关闭自动检测：只检查配置的端口，不碰系统代理/常见端口
    assert calls == ["http://127.0.0.1:7892"]
    assert off.network["proxy"] == "http://127.0.0.1:7892"

    calls.clear()
    direct = _config({"proxy": ""})
    assert netcheck.resolve_proxy(direct) == ""
    assert calls == []  # 直连/TUN 模式完全不探测


def test_candidate_proxies_dedup_and_order(monkeypatch):
    from news_crawler import netcheck

    monkeypatch.setattr(netcheck, "_windows_system_proxy",
                        lambda: "http://127.0.0.1:7897")
    config = _config({
        "proxy": "http://127.0.0.1:7897",  # 配置与系统代理相同 → 去重
        "proxy_candidates": ["http://127.0.0.1:10809"],
    })
    candidates = netcheck._candidate_proxies(config)

    assert candidates[0] == "http://127.0.0.1:7897"
    assert candidates.count("http://127.0.0.1:7897") == 1
    assert "http://127.0.0.1:10809" in candidates
    # 常见端口候选都跟随配置的 host（127.0.0.1）
    assert "http://127.0.0.1:7890" in candidates


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
