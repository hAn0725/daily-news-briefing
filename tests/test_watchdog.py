"""看门狗测试：窗口判断、已发送跳过、去重、诊断发现与失败通知。"""
import json
from datetime import datetime
from types import SimpleNamespace

import news_crawler.watchdog as wd


def _config():
    return SimpleNamespace(
        report={"logs_dir": "logs", "output_dir": "output"},
        schedule={"watchdog_start": "20:30", "deadline": "23:00"},
        email={"enabled": True},
    )


def _base(tmp_path):
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "output" / "2026-09").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _mark_sent(tmp_path, date_str):
    (tmp_path / "logs" / "delivery_state.json").write_text(
        json.dumps({date_str: {"content_sha256": "x",
                               "sent_at": date_str + "T08:00:00"}}),
        encoding="utf-8")


class _Recorder:
    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def __call__(self, config, subject, body):
        self.calls.append((subject, body))
        return self.ok, "ok" if self.ok else "fail"


def test_skips_before_window(tmp_path, monkeypatch):
    base = _base(tmp_path)
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 12, 0)  # 未到 20:30
    assert wd.run_watchdog(_config(), base_dir=base, now=now) == 0
    assert rec.calls == []


def test_no_alert_when_already_sent(tmp_path, monkeypatch):
    base = _base(tmp_path)
    _mark_sent(base, "2026-09-10")
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 21, 0)
    assert wd.run_watchdog(_config(), base_dir=base, now=now) == 0
    assert rec.calls == []


def test_alerts_once_with_launcher_finding(tmp_path, monkeypatch):
    base = _base(tmp_path)
    (base / "logs" / "scheduler.log").write_text(
        "2026/9/8 7:24:06 START command=\r\n"
        "2026/9/8 7:24:06 LAUNCH_ERROR code=5 message=bad\r\n"
        "2026/9/10 7:24:06 START command=\r\n"
        "2026/9/10 7:24:06 LAUNCH_ERROR code=5 message=x\r\n",
        encoding="gbk")
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 21, 0)
    assert wd.run_watchdog(_config(), base_dir=base, now=now) == 0
    assert len(rec.calls) == 1
    subject, body = rec.calls[0]
    assert "尚未发送" in subject
    assert "LAUNCH_ERROR" in body  # 诊断发现包含启动器报错

    # 同一天第二次检查不再发送
    now2 = datetime(2026, 9, 10, 22, 0)
    assert wd.run_watchdog(_config(), base_dir=base, now=now2) == 0
    assert len(rec.calls) == 1
    # 告警状态已记录
    state = json.loads((base / "logs" / "alert_state.json")
                       .read_text(encoding="utf-8"))
    assert "2026-09-10" in state


def test_alert_mention_netcheck_failures(tmp_path, monkeypatch):
    base = _base(tmp_path)
    (base / "logs" / "run.log").write_text(
        "2026-09-10 11:57:56,680 [INFO] 未检测到外网连接（请确认 VPN 已开启），"
        "5 分钟后重试（今日 23:00 截止）\n"
        "2026-09-10 12:03:02,795 [INFO] 未检测到外网连接（请确认 VPN 已开启），"
        "5 分钟后重试（今日 23:00 截止）\n",
        encoding="utf-8")
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 21, 0)
    wd.run_watchdog(_config(), base_dir=base, now=now)
    assert rec.calls and "VPN/外网检测今天失败 2 次" in rec.calls[0][1]


def test_alert_failure_returns_1(tmp_path, monkeypatch):
    base = _base(tmp_path)
    rec = _Recorder(ok=False)
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 21, 0)
    assert wd.run_watchdog(_config(), base_dir=base, now=now) == 1


def test_notify_failure_once_dedups(tmp_path, monkeypatch):
    base = _base(tmp_path)
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 23, 5)
    assert wd.notify_failure_once(_config(), "s1", "b1",
                                  base_dir=base, now=now) is True
    assert wd.notify_failure_once(_config(), "s2", "b2",
                                  base_dir=base, now=now) is False
    assert len(rec.calls) == 1


def test_notify_and_watchdog_share_state(tmp_path, monkeypatch):
    """失败通知发过后，看门狗同一天不再重复提醒。"""
    base = _base(tmp_path)
    rec = _Recorder()
    monkeypatch.setattr(wd, "send_alert_email", rec)
    now = datetime(2026, 9, 10, 23, 5)
    wd.notify_failure_once(_config(), "s", "b", base_dir=base, now=now)
    assert wd.run_watchdog(_config(), base_dir=base, now=now) == 0
    assert len(rec.calls) == 1
