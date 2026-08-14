"""主流程：采集 → 过滤 → 去重 → 全文 → AI/本地处理 → 生成报告 → 清理"""
import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from news_crawler.ai import AIProcessor  # noqa: E402
from news_crawler.cleanup import cleanup_old  # noqa: E402
from news_crawler.config import Config  # noqa: E402
from news_crawler.dedup import dedup_items  # noqa: E402
from news_crawler.fetcher import Fetcher  # noqa: E402
from news_crawler.filter import filter_items  # noqa: E402
from news_crawler.fulltext import fetch_full_text  # noqa: E402
from news_crawler.market import fetch_market_data  # noqa: E402
from news_crawler import nlp_local  # noqa: E402
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


def run(args):
    config = Config(args.config)
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    setup_logging(config, date_str)
    log = logging.getLogger("news")
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
        def _ft(it):
            it.full_text = fetch_full_text(it.url, config,
                                           src_map.get(it.source))
            return it

        with ThreadPoolExecutor(max_workers=12) as ex:
            list(ex.map(_ft, ft_items))
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

    # ---------- 9. 清理旧报告 ----------
    keep_days = int(config.report.get("keep_days", 30))
    cleanup_old(out_dir, keep_days)
    log.info("===== 完成 =====")
    return 0


def parse_args():
    p = argparse.ArgumentParser(description="每日新闻采集与 HTML 报告")
    p.add_argument("--date", default="", help="报告日期 YYYY-MM-DD（默认今天）")
    p.add_argument("--config", default="", help="配置文件路径")
    p.add_argument("--no-ai", action="store_true", help="强制使用本地处理")
    p.add_argument("--no-market", action="store_true", help="跳过财经数据")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
