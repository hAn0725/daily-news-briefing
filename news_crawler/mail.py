"""邮件发送：把生成的 HTML 简报发送到 QQ 邮箱（SMTP SSL）。

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


def _as_list(v):
    if not v:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return [str(x).strip() for x in v if str(x).strip()]


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


def send_report_email(config, paths, date_str, summary="", cat_counts=None):
    """发送报告邮件；返回 (是否成功, 说明文字)。失败只记日志，不影响报告已保存。"""
    cfg = config.email or {}
    if not cfg.get("enabled", False):
        return False, "未启用（config.yaml: email.enabled=false）"

    host = (cfg.get("smtp_host") or "smtp.qq.com").strip()
    port = int(cfg.get("smtp_port", 465))
    sender = (cfg.get("from_addr") or "").strip()
    to_addrs = _as_list(cfg.get("to_addrs"))
    prefix = (cfg.get("subject_prefix") or "【每日新闻简报】").strip()
    password = config.smtp_password

    missing = [name for name, val in
               (("email.from_addr", sender), ("email.to_addrs", to_addrs),
                ("SMTP授权码(运行 tools/store_smtp.py 录入)", password))
               if not val]
    if missing:
        return False, "邮箱配置不完整，缺少: " + "、".join(missing)

    # HTML 报告既作正文也作附件
    html_path = next((Path(p) for p in paths if str(p).lower().endswith(".html")),
                     Path(paths[0]))
    html_str = html_path.read_text(encoding="utf-8")

    # ---- 纯文本摘要部分 ----
    plain = [f"这是 {date_str} 的每日新闻简报（程序自动生成）。"]
    if cat_counts:
        plain.append("收录情况：" + "，".join(
            f"{k} {v} 条" for k, v in cat_counts.items()))
    if summary:
        plain += ["", "—— 今日综述 ——", summary]
    plain += ["", "完整排版报告见下方 HTML 正文；若邮件客户端样式异常，请查看附件。"]
    plain_text = "\n".join(plain)

    subject = f"{prefix}{date_str}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("每日新闻简报", "utf-8")), sender))
    msg["To"] = ", ".join(to_addrs)
    msg["Date"] = formatdate(localtime=True)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_text, "plain", "utf-8"))
    alt.attach(MIMEText(html_str, "html", "utf-8"))
    msg.attach(alt)

    if cfg.get("attach_html", True):
        att = MIMEApplication(html_str.encode("utf-8"))
        att.add_header("Content-Disposition", "attachment",
                       filename=f"news_{date_str}.html")
        msg.attach(att)

    # 发送（带重试与端口回退）：实测网络偶发瞬断（Connection unexpectedly
    # closed），同一端口重试一次，465 失败再自动换 587 STARTTLS 兼一段
    attempts = [(port, port == 465), (port, port == 465)]
    attempts.append((587, False) if port == 465 else (465, True))
    last_err = None
    for i, (p, use_ssl) in enumerate(attempts, 1):
        try:
            _deliver(host, p, use_ssl, msg, sender, to_addrs, password)
            if i > 1:
                log.info("邮件在第 %d 次尝试发送成功", i)
            return True, f"已发送至 {', '.join(to_addrs)}"
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("SMTP 第 %d/%d 次尝试失败（%s:%s %s）: %s",
                        i, len(attempts), host, p,
                        "SSL" if use_ssl else "STARTTLS", e)
            if i < len(attempts):
                time.sleep(3)
    log.debug("邮件发送异常详情", exc_info=True)
    return False, (f"发送失败（已尝试 {len(attempts)} 次）: {last_err}"
                   "（若持续失败：检查授权码是否为 16 位、代理是否干扰 SMTP）")
