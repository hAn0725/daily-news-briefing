"""重点源正文抓取：提取网页正文供 AI 做更准确的摘要，失败回退空串"""
import threading

import requests
import trafilatura


def _wall_timeout_guard(fn, limit: float):
    """在守护线程中执行 fn，强制墙钟超时，防止慢速/滴流服务器无限挂起。
    超时返回 None（守护线程被丢弃，不影响进程退出）。"""
    box = {}

    def worker():
        try:
            box["result"] = fn()
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(limit)
    if t.is_alive():
        return None
    if "err" in box:
        raise box["err"]
    return box.get("result")


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

        result = _wall_timeout_guard(_do, timeout + 8)
        if not result:
            return ""
        return result
    except Exception:  # noqa: BLE001
        return ""
