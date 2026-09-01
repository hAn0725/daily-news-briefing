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
        timeout = int(config.network.get("request_timeout", 20))

        def _do():
            # 流式下载，只取前 150KB，防止超大/病态页面拖垮解析
            with requests.get(url, headers=headers, proxies=proxies,
                              timeout=timeout, stream=True) as resp:
                resp.raise_for_status()
                chunks = []
                size = 0
                for chunk in resp.iter_content(chunk_size=32768):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > 150_000:
                        break
                html = b"".join(chunks)
                html = html.decode(resp.encoding or "utf-8", errors="replace")
                text = trafilatura.extract(html, include_comments=False,
                                           include_tables=False)
                return (text or "").strip()[:max_len]

        return _do() or ""
    except Exception:  # noqa: BLE001
        return ""
