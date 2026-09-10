"""联网检测与等待：确认 VPN 已开启、能访问外网后才允许生成。

- check_online(): 配置了代理时只允许通过该代理访问国外探针，绝不回退直连；
  未配置代理时才用直连检测 TUN 模式 VPN。
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

# 默认探针必须是在中国大陆通常无法直连、且成功时明确返回 204 的地址。
# Cloudflare 在大陆可直连，不能用于判断 VPN 是否开启。
DEFAULT_CHECK_URLS = [
    "https://www.google.com/generate_204",
]

_UA = {"User-Agent": "Mozilla/5.0 (news-netcheck)"}


def check_online(config, quiet=False):
    """检测 VPN/外网是否可用。

    一旦配置 ``network.proxy``，该地址就是唯一允许的检测路径。此前的
    “代理失败后直连 Cloudflare”会把普通国内网络误判成 VPN，进而发送
    缺少全部海外源的残缺日报。
    """
    net = config.network or {}
    timeout = float(net.get("check_timeout", 6))
    urls = net.get("check_urls") or DEFAULT_CHECK_URLS
    proxy = (net.get("proxy") or "").strip()
    expected_statuses = {
        int(status) for status in (net.get("check_statuses") or [204])
    }

    if proxy:
        attempts = [("代理", {"http": proxy, "https": proxy})]
    else:
        # 只有未配置本地代理时，才用这条路径覆盖 TUN 模式 VPN。
        attempts = [("直连（TUN）", None)]

    # 每个探针地址尝试多次（2026-09-10：VPN 节点对 Google 系域名随机超时，
    # 单次尝试会让"时通时断"的节点整天被误判为未联网）。
    tries_per_url = max(1, int(net.get("check_attempts", 2)))
    backoff = max(0.0, float(net.get("check_retry_backoff", 1.5)))

    for label, proxies in attempts:
        for url in urls:
            for attempt in range(1, tries_per_url + 1):
                try:
                    if proxies:
                        r = requests.get(url, proxies=proxies, timeout=timeout,
                                         headers=_UA)
                    else:
                        with requests.Session() as s:
                            s.trust_env = False  # 忽略系统/环境代理，真正直连测试
                            r = s.get(url, timeout=timeout, headers=_UA)
                    if r.status_code in expected_statuses:
                        if not quiet:
                            log.info("联网检测通过（%s %s → HTTP %d）",
                                     label, url, r.status_code)
                        return True
                    log.debug("联网探针异常响应（%s %s 第%d次）: HTTP %d",
                              label, url, attempt, r.status_code)
                except Exception as exc:  # noqa: BLE001
                    log.debug("联网探针失败（%s %s 第%d/%d次）: %s: %.160s",
                              label, url, attempt, tries_per_url,
                              type(exc).__name__, str(exc))
                if attempt < tries_per_url and backoff > 0:
                    time.sleep(backoff)
    return False


def foreign_coverage(config, sources, items):
    """返回海外新闻覆盖是否达到发送日报的最低要求及统计值。"""
    net = config.network or {}
    if not net.get("require_foreign_news", True):
        return True, 0, 0

    foreign_source_names = {
        source.name for source in sources
        if source.language == "en" or source.via_proxy
    }
    if not foreign_source_names:
        return True, 0, 0

    foreign_items = [
        item for item in items if item.source in foreign_source_names
    ]
    present_sources = {item.source for item in foreign_items}
    min_sources = max(1, int(net.get("min_foreign_sources", 1)))
    min_items = max(1, int(net.get("min_foreign_items", 1)))
    ok = (len(present_sources) >= min_sources and
          len(foreign_items) >= min_items)
    return ok, len(present_sources), len(foreign_items)


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

    peak_note = "；已启用禁用时段" if peak_periods else ""
    log.info("联网检测开启：未联网每 %d 分钟重试一次，当天 %02d:%02d 截止%s",
             interval_min, dh, dm, peak_note)
    while True:
        now = datetime.now(tz)
        deadline = now.replace(hour=dh, minute=dm, second=0, microsecond=0)
        remain = (deadline - now).total_seconds()
        if remain <= 0:
            log.error("已达今日截止时间 %02d:%02d 仍未满足运行条件，"
                      "今天不再生成（明早计划任务会自动再试）。", dh, dm)
            return False

        peak, peak_end_min = _in_peak(now, peak_periods)
        if peak:
            # 分段等待而不是一次睡数小时，避免隐藏任务长时间无活动而被系统清理。
            now_min = now.hour * 60 + now.minute
            until_peak_end = peak_end_min * 60 - now_min * 60 - now.second
            wait_s = min(interval_min * 60, until_peak_end, remain)
            log.info("当前处于配置的禁用时段，暂不生成；%.0f 分钟后再次检查",
                     wait_s / 60)
        elif check_online(config):
            log.info("联网检测通过（VPN/外网可用），开始生成。")
            return True
        else:
            wait_s = min(interval_min * 60, remain)
            log.info("未检测到外网连接（请确认 VPN 已开启），"
                     "%d 分钟后重试（今日 %02d:%02d 截止）",
                     interval_min, dh, dm)

        time.sleep(max(wait_s, 1))
