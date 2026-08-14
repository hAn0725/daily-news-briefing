"""重点源正文抓取：提取网页正文供 AI 做更准确的摘要，失败回退空串"""
import requests
import trafilatura


def fetch_full_text(url: str, config, source=None, max_len: int = 1800) -> str:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        proxies = config.proxy_dict
        if source is not None and not (source.language == "en" or source.via_proxy):
            proxies = None
        resp = requests.get(url, headers=headers,
                            timeout=int(config.network.get("request_timeout", 20)),
                            proxies=proxies)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False,
                                   include_tables=False)
        if not text:
            return ""
        return text.strip()[:max_len]
    except Exception:  # noqa: BLE001
        return ""
