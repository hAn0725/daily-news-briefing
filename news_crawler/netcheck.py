"""联网检测与等待：确认 VPN 已开启、能访问外网后才允许生成。

- check_online(): 依次尝试「配置代理 → 直连」访问若干国外探针地址，
  任一成功即视为已联通外网（未开 VPN 时这些地址通常无法访问，
  因此可以准确判断"梯子是否打开"）。
- wait_until_ready(): 计划任务专用等待循环——
  * 未联网：每隔 N 分钟（默认 5 分钟）重试一次，直到当天截止时间（默认 23:00）；
  * 已联网但处于高峰时段：睡到空闲时段边界再继续（生成只发生在空闲时段）；
  * 一旦"已联网 + 空闲时段"即返回 True，主流程开始生成（生成后不再检测）。
"""
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger("news")

# 默认探针：中国大陆无法直连的地址，连通即说明 VPN 生效
DEFAULT_CHECK_URLS = [
    "https://www.google.com/generate_204",
    "https://cp.cloudflare.com/generate_204",
]

_UA = {"User-Agent": "Mozilla/5.0 (news-netcheck)"}


def check_online(config, quiet=False):
    """检测能否访问外网（走配置代理或直连，任一路径成功即通过）"""
    net = config.network or {}
    timeout = float(net.get("check_timeout", 6))
    urls = net.get("check_urls") or DEFAULT_CHECK_URLS
    proxy = (net.get("proxy") or "").strip()

    attempts = []
    if proxy:
        attempts.append(("代理", {"http": proxy, "https": proxy}))
    attempts.append(("直连", None))  # 覆盖 TUN 模式 VPN / 直连场景

    for label, proxies in attempts:
        for url in urls:
            try:
                if proxies:
                    r = requests.get(url, proxies=proxies, timeout=timeout,
                                     headers=_UA)
                else:
                    with requests.Session() as s:
                        s.trust_env = False  # 忽略系统/环境代理，真正直连测试
                        r = s.get(url, timeout=timeout, headers=_UA)
                if r.status_code < 500:
                    if not quiet:
                        log.info("联网检测通过（%s %s → HTTP %d）",
                                 label, url, r.status_code)
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def _parse_hhmm(text, default):
    try:
        h, m = str(text).strip().split(":")
        return int(h), int(m)
    except Exception:  # noqa: BLE001
        return default


def _in_peak(now, peak_periods):
    """判断 now 是否处于高峰时段。

    返回 (是否高峰, 高峰段结束的当日分钟数)。
    peak_periods 每段形如 {days: [0..6](0=周一), start: "09:00", end: "12:00"}
    """
    for p in peak_periods or []:
        days = p.get("days")
        if days is None:
            days = [0, 1, 2, 3, 4]
        if now.weekday() not in days:
            continue
        sh, sm = _parse_hhmm(p.get("start", "09:00"), (9, 0))
        eh, em = _parse_hhmm(p.get("end", "12:00"), (12, 0))
        cur = now.hour * 60 + now.minute
        if sh * 60 + sm <= cur < eh * 60 + em:
            return True, eh * 60 + em
    return False, 0


def wait_until_ready(config, log):
    """阻塞直到「已联网 + 空闲时段」；超过当天截止时间则返回 False（今天不生成）。"""
    sched = config.schedule or {}
    tz = ZoneInfo(sched.get("timezone", "Asia/Shanghai"))
    interval_min = max(1, int(sched.get("retry_interval_minutes", 5)))
    dh, dm = _parse_hhmm(sched.get("deadline", "23:00"), (23, 0))
    peak_periods = sched.get("peak_periods") or []

    log.info("联网检测开启：未联网每 %d 分钟重试一次，当天 %02d:%02d 截止；"
             "仅空闲时段生成", interval_min, dh, dm)
    while True:
        now = datetime.now(tz)
        deadline = now.replace(hour=dh, minute=dm, second=0, microsecond=0)
        remain = (deadline - now).total_seconds()
        if remain <= 0:
            log.error("已达今日截止时间 %02d:%02d 仍未满足联网+空闲条件，"
                      "今天不再生成（明早计划任务会自动再试）。", dh, dm)
            return False

        peak, peak_end_min = _in_peak(now, peak_periods)
        if peak:
            # 高峰时段肯定不生成，直接睡到空闲边界，期间不探测外网（省时省流量）
            now_min = now.hour * 60 + now.minute
            wait_s = min(peak_end_min * 60 - now_min * 60 - now.second, remain)
            log.info("当前为高峰时段（工作日 09:00-12:00 / 14:00-18:00），"
                     "%.0f 分钟后进入空闲时段再检测", wait_s / 60)
        elif check_online(config):
            log.info("联网检测通过（VPN/外网可用），且处于空闲时段，开始生成。")
            return True
        else:
            wait_s = min(interval_min * 60, remain)
            log.info("未检测到外网连接（请确认 VPN 已开启），"
                     "%d 分钟后重试（今日 %02d:%02d 截止）",
                     interval_min, dh, dm)

        time.sleep(max(wait_s, 1))
