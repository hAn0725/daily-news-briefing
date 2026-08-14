"""财经数据速览：从腾讯行情接口获取指数/汇率/金价（best-effort）"""
import logging

import requests

log = logging.getLogger("news")

# (symbol, 显示名)
SYMBOLS = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("hkHSI", "恒生指数"),
    ("usDJI", "道琼斯"),
    ("usIXIC", "纳斯达克"),
    ("usINX", "标普500"),
    ("USDCNY", "美元/人民币"),
    ("hf_GC", "黄金 COMEX"),
]


def _num(fields, idx):
    """安全取数值字段"""
    try:
        v = fields[idx].strip()
        return float(v) if v else None
    except Exception:  # noqa: BLE001
        return None


def fetch_market_data(config):
    """返回 [{'name','price','change','change_pct'}]，失败返回空列表"""
    result = []
    q = ",".join(s for s, _ in SYMBOLS)
    url = f"https://qt.gtimg.cn/q={q}"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
            timeout=10,
            proxies=None,  # 腾讯行情为国内接口，直连
        )
        resp.raise_for_status()
        resp.encoding = "gbk"
        for line in resp.text.splitlines():
            line = line.strip()
            if "=" not in line:
                continue
            var, val = line.split("=", 1)
            code = var.replace("v_", "").strip()
            val = val.strip().strip('";').strip('"')
            fields = val.split("~")
            if len(fields) < 5:
                continue
            name = fields[1].strip() or next(
                (n for s, n in SYMBOLS if s == code), code)
            price = _num(fields, 3)
            prev = _num(fields, 4)
            if price is None:
                continue
            change = change_pct = None
            if prev:
                change = price - prev
                change_pct = change / prev * 100
            if change is None and len(fields) > 32:
                change = _num(fields, 31)
                change_pct = _num(fields, 32)
            result.append({
                "name": name,
                "price": round(price, 2) if price and price < 100000 else price,
                "change": round(change, 2) if change is not None else None,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            })
        log.info("财经数据获取 %d 项", len(result))
    except Exception as e:  # noqa: BLE001
        log.warning("财经数据获取失败: %s", e)
    return result
