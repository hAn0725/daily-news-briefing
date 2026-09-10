"""清理超过保留天数的旧报告"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("news")


def cleanup_old(output_dir, keep_days: int):
    if keep_days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=keep_days)
    out = Path(output_dir)
    if not out.exists():
        return
    removed = 0
    for f in out.rglob("*"):
        if f.is_file() and f.suffix.lower() in {".html", ".pdf"}:
            try:
                if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
                    removed += 1
            except Exception:  # noqa: BLE001
                pass
    if removed:
        log.info("已清理 %d 个过期报告", removed)
    # 删除空目录
    for d in sorted((x for x in out.rglob("*") if x.is_dir()),
                    key=lambda x: len(str(x)), reverse=True):
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:  # noqa: BLE001
            pass


def cleanup_logs(logs_dir, keep_days: int):
    """清理超过保留天数的每日运行日志（report_YYYY-MM-DD.log）。

    scheduler.log / run.log / watchdog.log 是累积量很小的文本，保留不删，
    方便排查"几天前到底发生了什么"。
    """
    if keep_days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=keep_days)
    logs = Path(logs_dir)
    if not logs.exists():
        return
    removed = 0
    for f in logs.glob("report_*.log"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        except Exception:  # noqa: BLE001
            pass
    if removed:
        log.info("已清理 %d 个过期日志", removed)
