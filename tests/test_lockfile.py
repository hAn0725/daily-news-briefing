"""生成互斥锁测试：加锁/释放、并发拒绝、过期接管、失败不阻塞。"""
import os
from datetime import datetime, timedelta

from news_crawler import lockfile


def test_acquire_then_release(tmp_path):
    path = tmp_path / "run.lock"
    assert lockfile.acquire(path) is True
    assert path.exists()
    assert lockfile.acquire(path) is False  # 已被持有
    lockfile.release(path)
    assert not path.exists()
    assert lockfile.acquire(path) is True  # 释放后可再次获取


def test_stale_lock_is_taken_over(tmp_path):
    path = tmp_path / "run.lock"
    path.write_text("old", encoding="utf-8")
    old = (datetime.now() - timedelta(minutes=200)).timestamp()
    os.utime(path, (old, old))
    assert lockfile.acquire(path, stale_minutes=90) is True


def test_fresh_lock_is_respected(tmp_path):
    path = tmp_path / "run.lock"
    path.write_text("x", encoding="utf-8")
    assert lockfile.acquire(path, stale_minutes=90) is False


def test_release_missing_file_is_silent(tmp_path):
    lockfile.release(tmp_path / "nope.lock")  # 不应抛错


def test_lock_write_failure_does_not_block(tmp_path):
    """锁目录建不出来时应放行（宁可重复生成，也不要整天不生成）。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    assert lockfile.acquire(blocker / "run.lock") is True
