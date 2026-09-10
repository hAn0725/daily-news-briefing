import os
import time

from news_crawler.cleanup import cleanup_logs, cleanup_old


def test_cleanup_removes_old_html_and_pdf(tmp_path):
    old_html = tmp_path / "old.html"
    old_pdf = tmp_path / "old.pdf"
    keep = tmp_path / "keep.txt"
    for path in (old_html, old_pdf, keep):
        path.write_text("x", encoding="utf-8")
        os.utime(path, (time.time() - 10 * 86400,) * 2)

    cleanup_old(tmp_path, keep_days=5)

    assert not old_html.exists()
    assert not old_pdf.exists()
    assert keep.exists()


def test_cleanup_logs_keeps_cumulative_logs(tmp_path):
    old_report = tmp_path / "report_2026-06-01.log"
    new_report = tmp_path / "report_2026-09-09.log"
    cumulative = tmp_path / "scheduler.log"
    for path in (old_report, new_report, cumulative):
        path.write_text("x", encoding="utf-8")
    os.utime(old_report, (time.time() - 120 * 86400,) * 2)
    os.utime(new_report, (time.time() - 2 * 86400,) * 2)
    os.utime(cumulative, (time.time() - 120 * 86400,) * 2)

    cleanup_logs(tmp_path, keep_days=90)

    assert not old_report.exists()   # 过期日报日志被清理
    assert new_report.exists()       # 保留期内不动
    assert cumulative.exists()       # 累积型日志永不删（排查历史要用）


def test_cleanup_logs_disabled_when_zero(tmp_path):
    old_report = tmp_path / "report_2026-06-01.log"
    old_report.write_text("x", encoding="utf-8")
    os.utime(old_report, (time.time() - 400 * 86400,) * 2)

    cleanup_logs(tmp_path, keep_days=0)

    assert old_report.exists()
