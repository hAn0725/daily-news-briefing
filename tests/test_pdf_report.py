from types import SimpleNamespace

from PIL import Image, ImageDraw
from pypdf import PdfReader

from news_crawler import report


def test_pdf_is_paginated_from_html_screenshot(tmp_path, monkeypatch):
    html_path = tmp_path / "brief.html"
    html_path.write_text("<html><body>护眼版</body></html>", encoding="utf-8")
    pdf_path = tmp_path / "brief.pdf"
    browser_path = tmp_path / "chrome.exe"
    browser_path.touch()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_arg = next(
            arg for arg in command if arg.startswith("--screenshot="))
        screenshot = output_arg.removeprefix("--screenshot=")
        image = Image.new("RGB", (900, 3000), (23, 26, 31))
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 40, 850, 1400), fill=(31, 35, 42))
        image.save(screenshot)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(report.subprocess, "run", fake_run)
    report.generate_pdf_from_html(html_path, pdf_path, browser_path)

    assert html_path.resolve().as_uri() in captured["command"]
    assert any(arg.startswith("--screenshot=") for arg in captured["command"])
    assert not any(arg.startswith("--print-to-pdf=")
                   for arg in captured["command"])
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert len(PdfReader(pdf_path).pages) == 2


def test_page_cut_moves_to_nearest_card_gap():
    image = Image.new("RGB", (900, 1800), (23, 26, 31))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 10, 860, 1150), fill=(31, 35, 42))
    draw.rectangle((40, 1200, 860, 1700), fill=(31, 35, 42))

    assert 1150 < report._find_page_cut(image, 0, 1273) < 1200
