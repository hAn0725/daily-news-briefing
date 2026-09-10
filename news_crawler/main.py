"""主流程：等待联网 → 采集 → 过滤 → 去重 → 全文 → AI/本地处理 → 生成报告 → 发送邮件 → 清理

计划任务模式（--wait-net）：生成前严格检测配置的代理/VPN，未通则每 5 分钟重试
直到当天截止时间（默认 23:00）；抓取后还会校验海外新闻覆盖，避免发送残缺日报。
"""
import argparse
import atexit
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from news_crawler import lockfile, nlp_local, watchdog  # noqa: E402
from news_crawler.ai import AIProcessor  # noqa: E402
from news_crawler.cleanup import cleanup_logs, cleanup_old  # noqa: E402
from news_crawler.config import Config  # noqa: E402
from news_crawler.dedup import dedup_items  # noqa: E402
from news_crawler.delivery import (  # noqa: E402
    already_sent,
    delivered_on,
    mark_sent,
    report_fingerprint,
)
from news_crawler.fetcher import Fetcher  # noqa: E402
from news_crawler.filter import filter_items  # noqa: E402
from news_crawler.fulltext import fetch_full_text  # noqa: E402
from news_crawler.mail import send_report_email  # noqa: E402
from news_crawler.market import fetch_market_data  # noqa: E402
from news_crawler.netcheck import foreign_coverage, wait_until_ready  # noqa: E402
from news_crawler.report import generate_report  # noqa: E402


def apply_ai_duplicate_groups(items, groups, max_group_size=4,
                              max_drop_ratio=0.30):
    """Apply only conservative, auditable cross-source duplicate groups."""
    accepted = []
    used = set()
    rejected = 0
    for raw_group in groups:
        group = []
        for value in raw_group:
            try:
                index = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(items) and index not in group:
                group.append(index)
        categories = {
            items[index].category for index in group
            if items[index].category and items[index].category != "other"
        }
        sources = {items[index].source for index in group}
        valid = (
            2 <= len(group) <= max_group_size
            and len(sources) == len(group)
            and len(categories) <= 1
            and not used.intersection(group)
        )
        if not valid:
            rejected += 1
            continue
        accepted.append(group)
        used.update(group)

    drop = set()
    for group in accepted:
        best = max(group, key=lambda i: (items[i].score, -i))
        drop.update(index for index in group if index != best)

    drop_ratio = len(drop) / len(items) if items else 0
    if drop_ratio > max_drop_ratio:
        return items, {
            "accepted": 0, "rejected": rejected + len(accepted),
            "dropped": 0, "guarded": True, "proposed_ratio": drop_ratio,
        }
    return [item for index, item in enumerate(items) if index not in drop], {
        "accepted": len(accepted), "rejected": rejected,
        "dropped": len(drop), "guarded": False,
        "proposed_ratio": drop_ratio,
    }


def select_diverse_items(items, limit, per_source_limit=3):
    """Prefer source diversity, then backfill so diversity never reduces count."""
    selected = []
    deferred = []
    source_counts = {}
    for item in items:
        count = source_counts.get(item.source, 0)
        if count < per_source_limit:
            selected.append(item)
            source_counts[item.source] = count + 1
        else:
            deferred.append(item)
    if len(selected) < limit:
        selected.extend(deferred[:limit - len(selected)])
    return selected[:limit]


def setup_logging(config, date_str):
    logs_dir = BASE_DIR / config.report.get("logs_dir", "logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"report_{date_str}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    # 静默 trafilatura 的解析噪声日志（"discarding data" 等属正常提示）
    for _name in ("trafilatura", "trafilatura.core", "trafilatura.settings"):
        logging.getLogger(_name).setLevel(logging.ERROR)


def run(args):
    config = Config(args.config)

    # 看门狗模式：只检查今天是否已发送并按需告警，不生成报告。
    if getattr(args, "watchdog", False):
        # 独立的轻量日志（stderr → bat 重定向到 logs\watchdog.log）
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s [%(levelname)s] %(message)s")
        return watchdog.run_watchdog(config)

    if args.date:
        try:
            date_str = datetime.strptime(args.date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("--date 必须是 YYYY-MM-DD 格式") from exc
    else:
        date_str = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    setup_logging(config, date_str)
    log = logging.getLogger("news")

    logs_dir = BASE_DIR / config.report.get("logs_dir", "logs")
    state_path = logs_dir / "delivery_state.json"

    # 定时模式幂等：当天已发送成功（含手动补发）就立刻退出，不再等网/重新生成。
    # 注意必须放在 waiting 之前——否则深夜（已过 23:00 截止）登录触发补跑时，
    # 会先判定"超时未联网"并误发一封失败通知，即使当天日报早已发送成功。
    if (args.wait_net and not args.resend_mail
            and delivered_on(state_path, date_str)):
        log.info("今天（%s）的日报已发送成功，跳过重复生成。", date_str)
        return 0

    # ---------- 0. 计划任务模式：等待 VPN/外网 ----------
    # 未联网每 5 分钟重试，直到生成或当天截止；生成后不再检测。
    if args.wait_net and not wait_until_ready(config, log):
        # 截止仍不联网：尽力发一封失败通知（同一天只发一次），再退出。
        try:
            watchdog.notify_failure_once(
                config, "【每日新闻】今天的日报没能生成",
                "到今天截止时间，VPN/外网检测始终未通过，今天的日报没有生成。\n"
                "建议：确认梯子开启后，双击桌面「每日新闻」手动补跑，\n"
                "或运行 schtasks /Run /TN DailyNewsReport。")
        except Exception:  # noqa: BLE001
            log.warning("失败通知邮件发送出错（不影响主流程）", exc_info=True)
        return 2

    # 生成互斥锁：防止手动运行与定时任务同时生成（双份邮件 + 双份 AI 费用）。
    # 放在联网等待之后加锁：等待期间不占用锁，手动刷新仍可正常生成。
    lock_enabled = bool(config.report.get("lock_enabled", True))
    lock_path = logs_dir / "run.lock"
    if lock_enabled:
        stale_min = int(config.report.get("lock_stale_minutes", 90))
        if not lockfile.acquire(lock_path, stale_min):
            log.warning("已有一次生成正在进行中（锁文件 %s），本次跳过。",
                        lock_path)
            return 0
        atexit.register(lockfile.release, lock_path)

    log.info("===== 开始生成 %s 的每日新闻简报 =====", date_str)

    hours_back = int(config.report.get("hours_back", 26))
    tz = ZoneInfo("Asia/Shanghai")
    cutoff = datetime.now(tz) - timedelta(hours=hours_back)
    dt_min = datetime.min.replace(tzinfo=tz)
    sources = config.sources
    log.info("新闻源共 %d 个", len(sources))

    # ---------- 1. 采集（并行）----------
    fetcher = Fetcher(config)
    all_items = []

    def _fetch(source):
        return source, fetcher.fetch_source(source)

    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(_fetch, s): s for s in sources}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                src, items = fut.result()
                all_items.extend(items)
                log.info("源[%s] 抓取 %d 条", src.name, len(items))
            except Exception as e:  # noqa: BLE001
                log.warning("源[%s] 失败: %s", s.name, e)
    log.info("共抓取 %d 条原始新闻", len(all_items))
    if not all_items:
        log.error("没有任何新闻源抓取成功，终止。")
        return 1

    # ---------- 2. 时间过滤 + 排除 ----------
    recent = [it for it in all_items
              if (it.published is None or it.published >= cutoff)]
    recent = filter_items(recent, config)
    log.info("时间过滤+排除后剩 %d 条", len(recent))

    # 第二道安全闸门：即使预检后 VPN 意外断开，也绝不生成或发送只有国内源的日报。
    coverage_ok, foreign_sources, foreign_items = foreign_coverage(
        config, sources, recent)
    if not coverage_ok:
        min_sources = int(config.network.get("min_foreign_sources", 1))
        min_items = int(config.network.get("min_foreign_items", 1))
        log.error(
            "海外新闻覆盖不足（成功来源 %d/%d，新闻 %d/%d），"
            "本次不生成、不发送；请开启 VPN 后重试。",
            foreign_sources, min_sources, foreign_items, min_items)
        return 3

    # ---------- 3. 去重 ----------
    items = dedup_items(recent)
    log.info("去重后剩 %d 条", len(items))

    # ---------- 4. 重点源抓全文（限量）----------
    ft_sources = {s.name for s in sources if s.full_text}
    src_map = {s.name: s for s in sources}
    ft_cap = int(config.report.get("fulltext_cap", 60))
    ft_items = [it for it in items if it.source in ft_sources][:ft_cap]
    if ft_items:
        ft_results = []

        def _ft(it):
            return it, fetch_full_text(it.url, config, src_map.get(it.source))

        def _run_ft_batch():
            executor = ThreadPoolExecutor(max_workers=12)
            futures = [executor.submit(_ft, item) for item in ft_items]
            done, pending = wait(futures, timeout=120)
            for future in done:
                try:
                    ft_results.append(future.result())
                except Exception as e:  # noqa: BLE001
                    log.warning("Full-text fetch failed: %s", e)
            for future in pending:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return len(pending)

        # 全文阶段整体设截止时间，个别病态页面再慢也不会拖死整个流程
        _ft_deadline = 120
        pending_count = _run_ft_batch()
        for item, full_text in ft_results:
            item.full_text = full_text
        if pending_count:
            log.warning("全文抓取超时（>%ds），跳过剩余以继续", _ft_deadline)
        n = sum(1 for it in ft_items if it.full_text)
        log.info("已抓取 %d 条正文全文", n)

    # ---------- 5. AI / 本地处理 ----------
    ai_ok = config.ai_enabled and not args.no_ai
    summary = ""
    ai_usage = None
    ai_cost = 0.0

    def _cross_dedup(items, ai_proc=None):
        """合并跨源同题新闻：AI 模式用语义去重（更准），本地/失败时退回摘要相似度"""
        if not items:
            return items
        if ai_proc is not None:
            try:
                groups = ai_proc.find_duplicates(items)
                if groups:
                    max_group = int(config.ai_cfg.get(
                        "dedup_max_group_size", 4))
                    max_ratio = float(config.ai_cfg.get(
                        "dedup_max_drop_ratio", 0.30))
                    items, stats = apply_ai_duplicate_groups(
                        items, groups, max_group, max_ratio)
                    if stats["guarded"]:
                        log.warning(
                            "AI 去重触发安全阀：拟删除 %.1f%%，超过 %.1f%%；本次跳过去重",
                            stats["proposed_ratio"] * 100, max_ratio * 100)
                    else:
                        log.info(
                            "AI 跨源去重：接受 %d 组、拒绝 %d 个可疑组、去除 %d 条",
                            stats["accepted"], stats["rejected"], stats["dropped"])
                return items
            except Exception as e:  # noqa: BLE001
                log.warning("AI 去重异常，回退摘要相似度: %s", e)
        # 兜底：标题+摘要字符相似度
        thr = float(config.report.get("post_dedup_threshold", 0.5))
        if thr <= 0:
            return items
        out = dedup_items(
            items, threshold=thr,
            key=lambda it: (it.cn_title or it.title) + " " + (it.cn_summary or ""),
            prefer_score=True)
        log.info("摘要相似度去重后剩 %d 条", len(out))
        return out

    if ai_ok:
        try:
            proc = AIProcessor(config)
            items = proc.process_items(items)
            items = _cross_dedup(items, ai_proc=proc)
            kept = [it for it in items if it.keep]
            summary = proc.generate_summary(kept)
            ai_usage = proc.get_usage()
            ai_cost = proc.estimate_cost()
            log.info("AI 处理完成（保留 %d 条）", len(kept))
            log.info("AI 用量: %s tokens，费用约 ¥%.4f",
                     ai_usage["total_tokens"], ai_cost)
        except Exception as e:  # noqa: BLE001
            if config.ai_cfg.get("required", False):
                log.error("AI 处理失败且已禁止本地降级，本次不生成、不发送: %s", e)
                return 4
            log.error("AI 处理失败，回退本地: %s", e)
            items = _cross_dedup(nlp_local.fallback_process(items, config))
    else:
        log.info("未启用 AI，使用本地处理")
        items = _cross_dedup(nlp_local.fallback_process(items, config))

    # ---------- 6. 分类组织与截断 ----------
    cats_cfg = config.categories
    grouped = {k: [] for k in cats_cfg}
    for it in items:
        if it.keep and it.category in grouped:
            grouped[it.category].append(it)
    for k, lst in grouped.items():
        lst.sort(key=lambda x: (x.score, x.published or dt_min),
                 reverse=True)
        limit = int(cats_cfg[k].get("max_items", 10))
        per_source_limit = int(config.report.get(
            "max_items_per_source_in_category", 3))
        grouped[k] = select_diverse_items(lst, limit, per_source_limit)
    log.info("分类数量: %s",
             {k: len(v) for k, v in grouped.items()})

    # ---------- 7. 财经数据（best-effort）----------
    market = fetch_market_data(config) if not args.no_market else []
    log.info("财经数据 %d 项", len(market))

    # ---------- 8. 生成报告 ----------
    out_dir = BASE_DIR / config.report.get("output_dir", "output")
    paths = generate_report(config, date_str, grouped, summary, market,
                            out_dir, ai_usage=ai_usage, ai_cost=ai_cost)
    for p in paths:
        log.info("已生成: %s", p)

    # ---------- 9. 发送邮件（失败时保留报告，但返回非零状态）----------
    exit_code = 0
    if args.no_mail:
        log.info("已跳过邮件发送（--no-mail）")
    else:
        counts = {}
        for k, lst in grouped.items():
            title = (config.categories.get(k) or {}).get("title") or k
            counts[title] = len(lst)
        pdf_path = next((Path(p) for p in paths
                         if str(p).lower().endswith(".pdf")), None)
        fingerprint = report_fingerprint(grouped, summary, market)
        if (pdf_path is not None and not args.resend_mail and
                already_sent(state_path, date_str, fingerprint)):
            ok, msg = True, "内容与上次成功发送的一致，已跳过重复发送"
        else:
            ok, msg = send_report_email(config, paths, date_str,
                                        summary=summary, cat_counts=counts)
            if ok and pdf_path is not None:
                mark_sent(state_path, date_str, fingerprint)
        (log.info if ok else log.error)("邮件发送: %s", msg)
        if not ok:
            exit_code = 5

    # ---------- 10. 清理旧报告 ----------
    keep_days = int(config.report.get("keep_days", 30))
    cleanup_old(out_dir, keep_days)
    cleanup_logs(logs_dir, int(config.report.get("keep_log_days", 90)))
    if exit_code:
        log.error("===== 报告已生成，但发送未完成（退出码 %d）=====", exit_code)
    else:
        log.info("===== 完成 =====")
    return exit_code


def parse_args():
    p = argparse.ArgumentParser(description="每日新闻采集与 PDF 报告")
    p.add_argument("--date", default="", help="报告日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--config", default="", help="配置文件路径")
    p.add_argument("--no-ai", action="store_true", help="强制使用本地处理")
    p.add_argument("--no-market", action="store_true", help="跳过财经数据")
    p.add_argument("--watchdog", action="store_true",
                   help="看门狗：检查今天是否已发送，未发送则发一次诊断告警邮件（计划任务用）")
    p.add_argument("--wait-net", action="store_true",
                   help="生成前检测 VPN/外网，未通每5分钟重试直到当天截止（计划任务用）")
    p.add_argument("--no-mail", action="store_true", help="跳过邮件发送")
    p.add_argument("--resend-mail", action="store_true",
                   help="忽略成功发送记录，强制重新发送 PDF")
    return p.parse_args()


if __name__ == "__main__":
    _args = parse_args()
    try:
        sys.exit(run(_args))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # 生成阶段崩溃：记全栈日志，并尽力发一封失败通知（配置读不出就放弃）。
        logging.getLogger("news").exception("生成过程发生未处理异常")
        try:
            watchdog.notify_failure_once(
                Config(_args.config), "【每日新闻】今天的日报生成失败",
                f"生成过程发生异常：{type(exc).__name__}: {exc}\n"
                "请查看 logs\\ 下当天日志（report_*.log / run.log）。\n"
                "修复后可双击桌面「每日新闻」手动重跑。")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
