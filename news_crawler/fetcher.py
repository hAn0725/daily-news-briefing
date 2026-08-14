"""抓取模块：RSS + JSON 热榜，支持代理、超时、重试、单源容错"""
import logging
import time
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

import feedparser
import requests
from bs4 import BeautifulSoup

from .sources import NewsItem, Source

TZ = ZoneInfo("Asia/Shanghai")
log = logging.getLogger("news")


def strip_html(s: str) -> str:
    if not s:
        return ""
    return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)


def parse_dt(struct_time):
    """把 feedparser 的 struct_time（UTC）转成上海时区的 datetime"""
    if not struct_time:
        return None
    try:
        dt = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return dt.astimezone(TZ)
    except Exception:
        return None


class Fetcher:
    def __init__(self, config):
        self.timeout = int(config.network.get("request_timeout", 20))
        self.retries = int(config.network.get("retries", 2))
        self.proxies = config.proxy_dict
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _get(self, url, source=None, headers=None, **kw):
        h = {**self.headers, **(headers or {})}
        proxies = self._proxies_for(source)
        return requests.get(url, headers=h, timeout=self.timeout,
                            proxies=proxies, **kw)

    def _proxies_for(self, source):
        """国外源（en 或显式标记 via_proxy）走代理，国内源直连"""
        if not self.proxies:
            return None
        if source is None:
            return None
        if source.language == "en" or source.via_proxy:
            return self.proxies
        return None

    def _retry(self, fn):
        last = None
        for i in range(self.retries + 1):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                last = e
                if i < self.retries:
                    time.sleep(1.5)  # 重试前短暂退避，缓解瞬时超时
        raise last

    # ---------------- 入口 ----------------
    def fetch_source(self, source: Source):
        if source.type == "rss":
            return self._retry(lambda: self.fetch_rss(source))
        if source.type == "json":
            return self._retry(lambda: self.fetch_json(source))
        raise ValueError(f"未知源类型: {source.type}")

    # ---------------- RSS ----------------
    def fetch_rss(self, source: Source):
        resp = self._get(source.url, source=source)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            summary = strip_html(e.get("summary") or e.get("description") or "")
            published = parse_dt(e.get("published_parsed") or e.get("updated_parsed"))
            items.append(NewsItem(
                title=title, url=link, source=source.name,
                summary=summary, language=source.language, published=published,
            ))
        return items

    # ---------------- JSON 热榜 ----------------
    def fetch_json(self, source: Source):
        resp = self._get(source.url, source=source)
        resp.raise_for_status()
        data = resp.json()

        if "zhihu.com" in source.url:
            return self._parse_zhihu(data, source)
        if "baidu.com" in source.url:
            return self._parse_baidu(data, source)
        if "weibo.com" in source.url:
            return self._parse_weibo(data, source)
        return []

    def _parse_zhihu(self, data, source):
        items = []
        for row in data.get("data", []) or []:
            t = row.get("target", {}) or {}
            title = (t.get("title") or "").strip()
            if not title:
                continue
            link = t.get("url") or f"https://www.zhihu.com/question/{t.get('id', '')}"
            summary = strip_html(t.get("excerpt") or "")
            try:
                hot = int((row.get("detail_text") or "0").replace("万", "0000"))
            except Exception:
                hot = 0
            items.append(NewsItem(title=title, url=link, source=source.name,
                                  summary=summary, language="zh", hot_score=hot))
        return items

    def _parse_baidu(self, data, source):
        items = []
        cards = (data.get("data") or {}).get("cards") or []
        for card in cards:
            for c in card.get("content") or []:
                title = (c.get("word") or "").strip()
                if not title:
                    continue
                link = c.get("url") or f"https://www.baidu.com/s?wd={quote(title)}"
                items.append(NewsItem(title=title, url=link, source=source.name,
                                      language="zh"))
        return items

    def _parse_weibo(self, data, source):
        items = []
        realtime = (data.get("data") or {}).get("realtime") or []
        for row in realtime:
            title = (row.get("word") or "").strip()
            if not title:
                continue
            link = row.get("url") or f"https://s.weibo.com/weibo?q={quote(title)}"
            items.append(NewsItem(title=title, url=link, source=source.name,
                                  language="zh"))
        return items
