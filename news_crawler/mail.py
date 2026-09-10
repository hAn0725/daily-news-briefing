"""邮件发送：把生成的 PDF 简报发送到 QQ 邮箱（SMTP SSL）。

授权码优先读取 .env 中 DPAPI 加密的 QQ_SMTP_AUTH_ENC
（由 tools/store_smtp.py 录入生成，绑定当前 Windows 用户与本机），
兼容旧明文 QQ_SMTP_AUTH。
"""
import logging
import smtplib
import time
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path

log = logging.getLogger("news")


def _deliver(host, port, use_ssl, msg, sender, to_addrs, password):
    """建立 SMTP 连接并发送（465 用 SSL，其它端口用 STARTTLS）"""
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(sender, password)
            s.send_message(msg, from_addr=sender, to_addrs=to_addrs)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(sender, password)
            s.send_message(msg, from_addr=sender, to_addrs=to_addrs)


def _deliver_with_retry(host, port, msg, sender, to_addrs, password):
    """带重试与端口回退的发送：同一端口重试一次，465 失败再自动换 587。

    实测网络偶发瞬断（Connection unexpectedly closed）。返回 (是否成功, 最后错误)。
    """
    attempts = [(port, port == 465), (port, port == 465)]
    attempts.append((587, False) if port == 465 else (465, True))
    last_err = None
    for i, (p, use_ssl) in enumerate(attempts, 1):
        try:
            _deliver(host, p, use_ssl, msg, sender, to_addrs, password)
            if i > 1:
                log.info("邮件在第 %d 次尝试发送成功", i)
            return True, None
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("SMTP 第 %d/%d 次尝试失败（%s:%s %s）: %s",
                        i, len(attempts), host, p,
                        "SSL" if use_ssl else "STARTTLS", e)
            if i < len(attempts):
                time.sleep(3)
    log.debug("邮件发送异常详情", exc_info=True)
    return False, last_err


def _smtp_settings(config):
    """从配置取出发送所需字段；返回 (host, port, sender, to_addrs, password, 缺失项)"""
    cfg = config.email or {}
    host = (cfg.get("smtp_host") or "smtp.qq.com").strip()
    port = int(cfg.get("smtp_port", 465))
    sender = config.email_from
    to_addrs = config.email_to or ([sender] if sender else [])
    password = config.smtp_password
    missing = [name for name, val in
               (("发件邮箱(.env: SMTP_FROM_ADDR)", sender),
                ("SMTP授权码(运行 tools/store_smtp.py 录入)", password))
               if not val]
    return host, port, sender, to_addrs, password, missing


def _build_plain_message(sender, to_addrs, subject, plain_text):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("每日新闻简报", "utf-8")), sender))
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    return msg


def send_alert_email(config, subject, plain_text):
    """发送纯文本告警邮件（看门狗/失败通知用）；返回 (是否成功, 说明)。"""
    cfg = config.email or {}
    if not cfg.get("enabled", False):
        return False, "未启用（config.yaml: email.enabled=false）"
    host, port, sender, to_addrs, password, missing = _smtp_settings(config)
    if missing:
        return False, "邮箱配置不完整，缺少: " + "、".join(missing)
    msg = _build_plain_message(sender, to_addrs, subject, plain_text)
    ok, err = _deliver_with_retry(host, port, msg, sender, to_addrs, password)
    if ok:
        return True, f"已发送至 {', '.join(to_addrs)}"
    return False, (f"发送失败（已重试）: {err}"
                   "（若持续失败：检查授权码是否为 16 位、代理是否干扰 SMTP）")


def send_report_email(config, paths, date_str, summary="", cat_counts=None):
    """发送 PDF 和 HTML 双附件报告；返回 (是否成功, 说明文字)。

    PDF 方便直接预览；HTML 保留原始排版、可复制文字和原文链接。
    """
    cfg = config.email or {}
    if not cfg.get("enabled", False):
        return False, "未启用（config.yaml: email.enabled=false）"

    host, port, sender, to_addrs, password, missing = _smtp_settings(config)
    prefix = (cfg.get("subject_prefix") or "【每日新闻简报】").strip()
    if missing:
        return False, "邮箱配置不完整，缺少: " + "、".join(missing)

    pdf_path = next((Path(p) for p in paths if str(p).lower().endswith(".pdf")),
                    None)
    if pdf_path is None or not pdf_path.is_file():
        return False, "PDF 报告未生成，已跳过邮件发送"
    html_path = next((Path(p) for p in paths if str(p).lower().endswith(".html")),
                     None)
    if html_path is None or not html_path.is_file():
        return False, "HTML 报告未生成，已跳过邮件发送"

    # ---- 纯文本摘要部分 ----
    plain = [f"这是 {date_str} 的每日新闻简报（程序自动生成）。"]
    if cat_counts:
        plain.append("收录情况：" + "，".join(
            f"{k} {v} 条" for k, v in cat_counts.items()))
    if summary:
        plain += ["", "—— 今日综述 ——", summary]
    plain += ["", "邮件含 PDF 和 HTML 两个附件；HTML 阅读效果最佳。"]
    plain_text = "\n".join(plain)

    subject = f"{prefix}{date_str}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("每日新闻简报", "utf-8")), sender))
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    pdf_att = MIMEApplication(pdf_path.read_bytes(), _subtype="pdf")
    pdf_att.add_header("Content-Disposition", "attachment",
                       filename=f"news_{date_str}.pdf")
    msg.attach(pdf_att)
    html_att = MIMEText(html_path.read_text(encoding="utf-8"), "html", "utf-8")
    html_att.add_header("Content-Disposition", "attachment",
                        filename=f"news_{date_str}.html")
    msg.attach(html_att)

    # 发送（带重试与端口回退）：实测网络偶发瞬断（Connection unexpectedly
    # closed），同一端口重试一次，465 失败再自动换 587 STARTTLS。
    ok, err = _deliver_with_retry(host, port, msg, sender, to_addrs, password)
    if ok:
        return True, f"已发送至 {', '.join(to_addrs)}"
    return False, (f"发送失败（已重试）: {err}"
                   "（若持续失败：检查授权码是否为 16 位、代理是否干扰 SMTP）")
