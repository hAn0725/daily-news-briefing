"""主流程：等待联网 → 采集 → 过滤 → 去重 → 全文 → AI/本地处理 → 生成报告 → 发送邮件 → 清理

计划任务模式（--wait-net）：生成前检测 VPN/外网，未通则每 5 分钟重试直到当天截止
时间（默认 23:00），且只在空闲时段生成；生成后自动把报告发送到 QQ 邮箱。
"""
import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from news_crawler import nlp_local  # noqa: E402
from news_crawler.ai import AIProcessor  # noqa: E402
from news_crawler.cleanup import cleanup_old  # noqa: E402
from news_crawler.config import Config  # noqa: E402
from news_crawler.dedup import dedup_items  # noqa: E402
from news_crawler.delivery import (  # noqa: E402
    already_sent,
    mark_sent,
    report_fingerprint,
)
from news_crawler.fetcher import Fetcher  # noqa: E402
from news_crawler.filter import filter_items  # noqa: E402
from news_crawler.fulltext import fetch_full_text  # noqa: E402
from news_crawler.mail import send_report_email  # noqa: E402
from news_crawler.market import fetch_market_data  # noqa: E402
from news_crawler.netcheck import wait_until_ready  # noqa: E402
from news_crawler.report import generate_report  # noqa: E402


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
    if args.date:
        try:
            date_str = datetime.strptime(args.date, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("--date 必须是 YYYY-MM-DD 格式") from exc
    else:
        date_str = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    setup_logging(config, date_str)
    log = logging.getLogger("news")

    # ---------- 0. 计划任务模式：等待 VPN/外网 + 空闲时段 ----------
    # 未联网每 5 分钟重试、高峰时段自动延后，直到生成或当天截止；生成后不再检测。
    if args.wait_net and not wait_until_ready(config, log):
        return 2

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
                    drop = set()
                    for g in groups:
                        # 每组保留相关度最高（score 最高，相同取更靠前）的一条
                        best = max(g, key=lambda i: (items[i].score, -i))
                        drop.update(i for i in g if i != best)
                    items = [it for i, it in enumerate(items) if i not in drop]
                    log.info("AI 跨源去重：合并 %d 组，去除 %d 条",
                             len(groups), len(drop))
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
        grouped[k] = lst[: int(cats_cfg[k].get("max_items", 10))]
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

    # ---------- 9. 发送邮件（失败不影响报告已保存）----------
    if args.no_mail:
        log.info("已跳过邮件发送（--no-mail）")
    else:
        counts = {}
        for k, lst in grouped.items():
            title = (config.categories.get(k) or {}).get("title") or k
            counts[title] = len(lst)
        pdf_path = next((Path(p) for p in paths
                         if str(p).lower().endswith(".pdf")), None)
        state_path = (BASE_DIR / config.report.get("logs_dir", "logs") /
                      "delivery_state.json")
        fingerprint = report_fingerprint(grouped, summary, market)
        if (pdf_path is not None and not args.resend_mail and
                already_sent(state_path, date_str, fingerprint)):
            ok, msg = True, "PDF unchanged since successful delivery; skipped"
        else:
            ok, msg = send_report_email(config, paths, date_str,
                                        summary=summary, cat_counts=counts)
            if ok and pdf_path is not None:
                mark_sent(state_path, date_str, fingerprint)
        (log.info if ok else log.error)("邮件发送: %s", msg)

    # ---------- 10. 清理旧报告 ----------
    keep_days = int(config.report.get("keep_days", 30))
    cleanup_old(out_dir, keep_days)
    log.info("===== 完成 =====")
    return 0


def parse_args():
    p = argparse.ArgumentParser(description="每日新闻采集与 PDF 报告")
    p.add_argument("--date", default="", help="报告日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--config", default="", help="配置文件路径")
    p.add_argument("--no-ai", action="store_true", help="强制使用本地处理")
    p.add_argument("--no-market", action="store_true", help="跳过财经数据")
    p.add_argument("--wait-net", action="store_true",
                   help="生成前检测 VPN/外网，未通每5分钟重试直到当天截止（计划任务用）")
    p.add_argument("--no-mail", action="store_true", help="跳过邮件发送")
    p.add_argument("--resend-mail", action="store_true",
                   help="忽略成功发送记录，强制重新发送 PDF")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
