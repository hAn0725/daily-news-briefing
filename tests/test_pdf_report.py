from types import SimpleNamespace

from pypdf import PdfReader

from news_crawler.report import generate_pdf_report
from news_crawler.sources import NewsItem


def test_pdf_report_is_a_readable_pdf(tmp_path):
    config = SimpleNamespace(
        categories={"tech": {"title": "科技前沿"}},
        sources=[],
    )
    item = NewsItem(title="AI chip", url="https://example.com", source="Example",
                    cn_title="AI 芯片", cn_summary="用于验证 PDF 版式与中文字体。",
                    category="tech", score=5)
    pdf_path = tmp_path / "brief.pdf"

    generate_pdf_report(config, "2026-08-31", {"tech": [item]},
                        "今日摘要。", [], pdf_path)

    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 1
    assert pdf_path.read_bytes().startswith(b"%PDF-")
