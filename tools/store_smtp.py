"""录入 QQ 邮箱 SMTP 授权码，并用 Windows DPAPI 加密存入 .env（首次配置必须运行一次）。

用法：python tools/store_smtp.py
- 授权码输入不回显（不会出现在屏幕/日志/聊天记录里）
- 加密绑定当前 Windows 用户与本机，.env 中只保留密文 QQ_SMTP_AUTH_ENC
- 录入后会顺便做一次 SMTP 登录验证（需 config.yaml 已填 email.from_addr）
换授权码后重新运行本脚本即可覆盖。
"""
import base64
import getpass
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv  # noqa: E402

from news_crawler.secure import protect  # noqa: E402

load_dotenv(BASE / ".env")


def main():
    print("== QQ 邮箱 SMTP 授权码录入 ==")
    print("获取方式：QQ邮箱网页版 → 设置 → 账户 → POP3/SMTP服务 → 开启 → 生成授权码")
    pwd = getpass.getpass("请粘贴授权码（输入不回显）: ").strip()
    if not pwd:
        print("[错误] 未输入授权码。")
        return 1

    # 形态校验：QQ 授权码是 16 位纯字母数字（防止再次复制成 QQ 密码或其它字符串）
    if not (pwd.isascii() and pwd.isalnum() and len(pwd) == 16):
        kind = ("含空格或非字母数字字符" if not (pwd.isascii() and pwd.isalnum())
                else f"{len(pwd)} 位")
        print(f"[提醒] 你输入的内容为{kind}，而 QQ 邮箱授权码通常是"
              " 16 位纯字母数字（弹窗里那串，不是 QQ 密码）。")
        sure = input("确认仍要保存吗？(y=保存 / 直接回车=取消): ").strip().lower()
        if sure != "y":
            print("已取消，未做任何修改。请重新运行并粘贴正确的授权码。")
            return 1

    enc_b64 = base64.b64encode(protect(pwd.encode("utf-8"))).decode("ascii")

    env_path = BASE / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    out = [ln for ln in lines
           if not (ln.startswith("QQ_SMTP_AUTH=") or ln.startswith("QQ_SMTP_AUTH_ENC="))]
    out.append(f"QQ_SMTP_AUTH_ENC={enc_b64}")
    out.append("# QQ 邮箱授权码已加密（Windows DPAPI，绑定当前用户）。")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("[完成] 授权码已加密写入 .env 的 QQ_SMTP_AUTH_ENC，明文不落盘。")

    # ---- 登录验证（发件邮箱：.env 优先 → config.yaml 兼容 → 交互输入并写入 .env）----
    try:
        import smtplib

        import yaml
        cfg = yaml.safe_load(
            (BASE / "config.yaml").read_text(encoding="utf-8")) or {}
        mail = cfg.get("email", {}) or {}
        user = os.getenv("SMTP_FROM_ADDR", "").strip()
        if not user:
            user = (mail.get("from_addr") or "").strip()
        if not user:
            user = input("请输入你的 QQ 邮箱地址（如 123456789@qq.com）: ").strip()
            if not user:
                print("[提示] 未输入邮箱，跳过登录验证。")
                return 0
            lines = env_path.read_text(encoding="utf-8").splitlines()
            if not any(ln.startswith("SMTP_FROM_ADDR=") for ln in lines):
                lines.append(f"SMTP_FROM_ADDR={user}")
                env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("[完成] 发件邮箱已存入 .env 的 SMTP_FROM_ADDR（仅本地，不进公开仓库）。")
        host = (mail.get("smtp_host") or "smtp.qq.com").strip()
        port = int(mail.get("smtp_port", 465))
        print(f"正在验证登录 {host}:{port}（{user}）...")
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.login(user, pwd)
        print("[成功] SMTP 登录验证通过，邮件发送已就绪！")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[警告] 登录验证失败：{e}")
        print("       授权码已保存。请检查：① QQ邮箱是否已开启 SMTP 服务；"
              "② 授权码是否正确（注意没有空格）；")
        print("       ③ config.yaml 的 email.from_addr 是否与授权码所属账号一致。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
