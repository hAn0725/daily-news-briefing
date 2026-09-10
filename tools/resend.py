"""补发某一天的简报邮件（默认今天）。

用法（在项目根目录运行）:
    python tools/resend.py              # 补发今天的报告
    python tools/resend.py 2026-09-03   # 补发指定日期的报告

说明：直接为已生成的 HTML 补出 PDF 附件并发送邮件，
不重新采集新闻、不调用 AI（零费用）。
适用场景：当天计划任务跑了一半（例如 PDF 阶段崩溃）导致邮件没发出时补发。
"""
import html as html_mod
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from news_crawler.config import Config  # noqa: E402
from news_crawler.delivery import record_delivery  # noqa: E402
from news_crawler.mail import send_report_email  # noqa: E402
from news_crawler.report import generate_pdf_from_html  # noqa: E402

SUMMARY_RE = re.compile(
    r"<div class='summary-box'><h3>📌 今日要闻综述</h3><p>(.*?)</p></div>",
    re.S)


def main() -> int:
    date_str = (sys.argv[1] if len(sys.argv) > 1 else
                datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d"))
    month_dir = BASE / "output" / date_str[:7]
    html_path = month_dir / f"{date_str}.html"
    if not html_path.is_file():
        print(f"未找到 {html_path}：该日期没有已生成的报告，无法补发")
        return 1

    summary = ""
    match = SUMMARY_RE.search(html_path.read_text(encoding="utf-8"))
    if match:
        summary = html_mod.unescape(match.group(1)).strip()

    pdf_path = month_dir / f"{date_str}.pdf"
    print(f"为 {html_path.name} 补生成 PDF ...")
    generate_pdf_from_html(html_path, pdf_path)
    print(f"PDF 已生成: {pdf_path}")

    cfg = Config()
    ok, msg = send_report_email(config=cfg, paths=[html_path, pdf_path],
                                date_str=date_str, summary=summary)
    print(("✅ 发送成功" if ok else "❌ 发送失败") + "：" + msg)
    if ok:
        # 记录发送状态：否则看门狗会以为这天没发出去，再发一封告警邮件
        state_path = (BASE / cfg.report.get("logs_dir", "logs") /
                      "delivery_state.json")
        record_delivery(state_path, date_str, note="tools/resend.py 手动补发")
        print(f"已记录发送状态: {state_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
