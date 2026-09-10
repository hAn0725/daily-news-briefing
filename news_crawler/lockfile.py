"""生成互斥锁：防止手动运行与定时任务同时生成（双份邮件 + 双份 AI 费用）。

实现为 `logs/run.lock` 文件，写入时间戳与 PID。
- 正常结束/异常退出都会释放（main.py 用 atexit 注册释放）。
- 断电等强杀留下的锁会在 `stale_minutes` 后自动失效，不会永久卡死。
- 锁文件创建失败（权限等）时返回 True，宁可放行也不阻塞日报生成。
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("news")


def acquire(path, stale_minutes: int = 90) -> bool:
    """尝试加锁；已被其它进程持有且未过期时返回 False。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log.warning("运行锁目录创建失败（跳过互斥保护）", exc_info=True)
        return True
    try:
        if path.exists():
            try:
                age = datetime.now() - datetime.fromtimestamp(
                    path.stat().st_mtime)
            except OSError:
                age = timedelta.max
            if age < timedelta(minutes=max(1, stale_minutes)):
                return False
            log.warning("发现过期运行锁（%.0f 分钟前创建），判定上次异常退出，"
                        "本次接管。", age.total_seconds() / 60)
            release(path)
        # O_EXCL 保证并发下只有一个进程能创建成功
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(f"{datetime.now().isoformat(timespec='seconds')} "
                         f"pid={os.getpid()}\n")
        return True
    except FileExistsError:
        return False
    except OSError:
        log.warning("运行锁创建失败（跳过互斥保护）", exc_info=True)
        return True


def release(path):
    """释放锁；文件不存在或删除失败都静默忽略。"""
    try:
        Path(path).unlink()
    except OSError:
        pass
