import os
import time

from news_crawler.cleanup import cleanup_old


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
