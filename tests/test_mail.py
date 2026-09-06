from types import SimpleNamespace

from news_crawler import mail


def test_email_contains_html_and_pdf_attachments(tmp_path, monkeypatch):
    pdf_path = tmp_path / "brief.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    html_path = tmp_path / "brief.html"
    html_path.write_text("<html>日报</html>", encoding="utf-8")
    captured = {}

    def fake_deliver(host, port, use_ssl, msg, sender, to_addrs, password):
        captured["msg"] = msg

    monkeypatch.setattr(mail, "_deliver", fake_deliver)
    config = SimpleNamespace(
        email={"enabled": True, "smtp_host": "smtp.example.com",
               "smtp_port": 465, "subject_prefix": "Daily "},
        email_from="sender@example.com",
        email_to=["reader@example.com"],
        smtp_password="secret",
    )

    ok, _ = mail.send_report_email(
        config, [html_path, pdf_path], "2026-09-01")

    assert ok
    attachments = [part for part in captured["msg"].walk()
                   if part.get_content_disposition() == "attachment"]
    assert len(attachments) == 2
    assert {(part.get_content_type(), part.get_filename())
            for part in attachments} == {
        ("application/pdf", "news_2026-09-01.pdf"),
        ("text/html", "news_2026-09-01.html"),
    }
