"""看门狗：当天日报未按时发送时，主动发一封"诊断 + 建议"告警邮件。

背景：2026-09-08 ~ 09-10 连续三天断发（电脑睡眠错过、启动器换行符损坏、
VPN 探针抖动），用户只能靠"没收到邮件"感知失败，却不知道原因。
看门狗计划任务（DailyNewsWatchdog，默认每天 20:30）检查 delivery_state.json，
若当天尚未发送成功，就从 scheduler.log / run.log / output 目录收集证据，
把"最可能的原因 + 建议操作"发到用户邮箱，而不是让用户面对沉默。

同一天的告警只发一次（记录在 logs/alert_state.json），避免重复轰炸。
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from news_crawler.mail import send_alert_email
from news_crawler.netcheck import _parse_hhmm

log = logging.getLogger("news")

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _lines_of_today(path: Path, prefix: str, encoding: str = "utf-8",
                    limit: int = 300) -> list:
    """读取日志中属于今天（以 prefix 开头）的最后若干行；失败返回空列表。

    scheduler.log 由 VBScript 以系统 ANSI(GBK) 写入，其余日志为 UTF-8。
    """
    try:
        text = path.read_text(encoding=encoding, errors="replace")
    except OSError:
        return []
    lines = [ln for ln in text.splitlines() if ln.startswith(prefix)]
    return lines[-limit:]


def _collect_findings(base_dir: Path, config, date_str: str,
                      sched_prefix: str) -> list:
    """按优先级收集今天未发送的可能原因（返回中文发现列表）。"""
    findings = []
    logs_dir = base_dir / config.report.get("logs_dir", "logs")

    # 1) 计划任务启动器（scheduler.log 为 GBK 编码）
    sched_lines = _lines_of_today(logs_dir / "scheduler.log", sched_prefix,
                                  encoding="gbk")
    if any("LAUNCH_ERROR" in ln for ln in sched_lines):
        findings.append(
            "计划任务启动器今天报错（LAUNCH_ERROR），启动脚本可能被改动损坏"
            "（例如换行符不是 Windows 的 CRLF），详见 logs\\scheduler.log")
    elif not any("START" in ln for ln in sched_lines):
        findings.append(
            "计划任务今天没有触发过：电脑可能一直睡眠/关机，或任务被禁用"
            "（查看：schtasks /Query /TN DailyNewsReport /V）")

    # 2) 联网检测（run.log，bat 重定向的运行日志）
    run_lines = _lines_of_today(logs_dir / "run.log",
                                date_str)
    net_fail = [ln for ln in run_lines if "未检测到外网连接" in ln]
    if net_fail:
        findings.append(
            f"VPN/外网检测今天失败 {len(net_fail)} 次"
            f"（最后一次 {net_fail[-1][:19]}）——最常见原因：梯子没开或节点不可用")

    # 3) 报告已生成但没发送（发送阶段失败）
    out_dir = base_dir / config.report.get("output_dir", "output")
    html_path = out_dir / date_str[:7] / f"{date_str}.html"
    if html_path.is_file():
        findings.append(f"报告文件其实已生成（output\\...\\{date_str}.html），"
                        "但邮件没有发出去——查看当天 report_*.log 的"
                        "「邮件发送」行")

    # 4) 当天主日志里的错误线索（取最后一条 ERROR）
    report_log = logs_dir / f"report_{date_str}.log"
    try:
        err_lines = [ln for ln in report_log.read_text(
            encoding="utf-8", errors="replace").splitlines()
            if "[ERROR]" in ln]
    except OSError:
        err_lines = []
    if err_lines:
        findings.append(f"当天日志最后的错误：{err_lines[-1][:200]}")

    if not findings:
        findings.append("未能自动判断原因；请查看 logs\\ 下当天的 "
                        "report_*.log 与 run.log")
    return findings


def _build_alert_body(date_str: str, now: datetime, findings: list,
                      past_deadline: bool) -> str:
    lines = [
        f"{date_str} 的每日新闻简报到现在还没有发送成功。",
    ]
    if past_deadline:
        lines.append("注意：已过今天 23:00 的截止时间，今天的报告不会再自动补发。")
    else:
        lines.append("现在修复后仍来得及：报告最晚今天 23:00 前都会自动重试。")
    lines += ["", "—— 自动诊断 ——"]
    lines += [f"{i}. {f}" for i, f in enumerate(findings, 1)]
    lines += [
        "",
        "—— 建议操作 ——",
        "1. 确认梯子（VPN）已开启且节点可用，这是最常见的原因。",
        "2. 修复后立即手动生成：双击桌面「每日新闻」快捷方式，或运行"
        " schtasks /Run /TN DailyNewsReport。",
        "3. 若某天的报告错过了，可用补发工具（不重复消耗 AI）补发：",
        "   python tools\\resend.py --date " + date_str,
        "",
        "（本邮件由看门狗自动发送，同一天最多提醒一次。）",
    ]
    return "\n".join(lines)


def run_watchdog(config, base_dir=None, now=None) -> int:
    """看门狗入口：检查今天是否已发送，未发送则发一次诊断告警邮件。

    返回退出码：0 = 无需告警或告警成功；1 = 需要告警但发送失败。
    """
    base = Path(base_dir) if base_dir else BASE_DIR
    sched = config.schedule or {}
    start_h, start_m = _parse_hhmm(sched.get("watchdog_start", "20:30"),
                                   (20, 30))
    dl_h, dl_m = _parse_hhmm(sched.get("deadline", "23:00"), (23, 0))

    if now is None:
        tz = ZoneInfo(sched.get("timezone", "Asia/Shanghai"))
        now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    # 注意：VBScript 的 Now 写出的日期不补零（如 2026/9/8），不能用 strftime
    sched_prefix = f"{now.year}/{now.month}/{now.day}"
    cur_min = now.hour * 60 + now.minute

    if cur_min < start_h * 60 + start_m:
        log.info("未到看门狗检查时间（%02d:%02d），跳过。", start_h, start_m)
        return 0

    logs_dir = base / config.report.get("logs_dir", "logs")
    state = _load_json(logs_dir / "delivery_state.json")
    if state.get(date_str):
        log.info("今日日报已发送成功（%s），无需告警。",
                 state[date_str].get("sent_at", ""))
        return 0

    alerts = _load_json(logs_dir / "alert_state.json")
    if alerts.get(date_str):
        log.info("今日已提醒过一次，不再重复发送告警。")
        return 0

    findings = _collect_findings(base, config, date_str, sched_prefix)
    past_deadline = cur_min >= dl_h * 60 + dl_m
    subject = f"【每日新闻】提醒：今天的日报尚未发送（{now:%H:%M}）"
    body = _build_alert_body(date_str, now, findings, past_deadline)

    ok, msg = send_alert_email(config, subject, body)
    log.info("看门狗告警邮件: %s", msg)
    if not ok:
        return 1

    alerts[date_str] = {"alerted_at": now.isoformat(timespec="seconds")}
    # 只保留最近 60 天记录，避免无限增长
    keep = sorted(alerts)[-60:]
    trimmed = {k: alerts[k] for k in keep}
    try:
        logs_dir.mkdir(exist_ok=True)
        (logs_dir / "alert_state.json").write_text(
            json.dumps(trimmed, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        log.warning("告警状态写入失败（不影响本次告警）", exc_info=True)
    return 0


def notify_failure_once(config, subject: str, body: str,
                        base_dir=None, now=None) -> bool:
    """发送一次性失败通知（供 --wait-net 超时、生成异常等路径复用）。

    同一天只发第一封（与看门狗共用 alert_state.json），尽力而为不抛错。
    """
    base = Path(base_dir) if base_dir else BASE_DIR
    logs_dir = base / config.report.get("logs_dir", "logs")
    if now is None:
        tz = ZoneInfo((config.schedule or {}).get("timezone",
                                                  "Asia/Shanghai"))
        now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    alerts = _load_json(logs_dir / "alert_state.json")
    if alerts.get(date_str):
        log.info("今天已发送过失败/告警通知，跳过重复提醒。")
        return False
    ok, msg = send_alert_email(config, subject, body)
    log.info("失败通知邮件: %s", msg)
    if ok:
        alerts[date_str] = {"alerted_at": now.isoformat(timespec="seconds"),
                            "type": "failure"}
        keep = sorted(alerts)[-60:]
        try:
            logs_dir.mkdir(exist_ok=True)
            (logs_dir / "alert_state.json").write_text(
                json.dumps({k: alerts[k] for k in keep},
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            log.warning("告警状态写入失败", exc_info=True)
    return ok
