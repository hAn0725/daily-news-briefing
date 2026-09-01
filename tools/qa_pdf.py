"""Validate and render a generated report PDF for visual review."""
import argparse
from pathlib import Path

import pymupdf
from pypdf import PdfReader


def validate_and_render(pdf_path: Path, output_dir: Path, scale: float = 1.5):
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        raise ValueError("PDF has no pages")
    for page_number, page in enumerate(reader.pages, 1):
        if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
            raise ValueError(f"PDF page {page_number} has invalid dimensions")

    output_dir.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    try:
        for index, page in enumerate(document):
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), alpha=False)
            pixmap.save(output_dir / f"page-{index + 1:02d}.png")
    finally:
        document.close()

    title = (reader.metadata.title if reader.metadata else "") or ""
    print(f"PDF OK: {len(reader.pages)} pages, {pdf_path.stat().st_size} bytes")
    print(f"Title: {title}")
    print(f"Rendered PNGs: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--scale", type=float, default=1.5)
    args = parser.parse_args()
    output_dir = args.output_dir or Path("tmp/pdfs") / f"{args.pdf.stem}-render"
    validate_and_render(args.pdf, output_dir, args.scale)


if __name__ == "__main__":
    main()
