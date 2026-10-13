"""Tests for individual document parsers."""

import base64
from pathlib import Path
import pytest
from markdown_it import MarkdownIt

from directory2md.parsers.text_parser import TextParser
from directory2md.parsers.image_parser import ImageParser
from directory2md.parsers.spreadsheet_parser import SpreadsheetParser
from directory2md.parsers import get_parser_for_file
from directory2md.markdown_utils import validate_markdown, extract_title_from_markdown


def test_text_parser_markdown_heading(tmp_path: Path):
    md_file = tmp_path / "document.md"
    md_file.write_text("# Main Heading\n\nSome body paragraph text here.")

    parser = TextParser()
    meta, text = parser.parse(md_file)

    assert meta.title == "Main Heading"
    assert "Some body paragraph text here." in text
    assert meta.word_count > 0
    assert validate_markdown(text)


def test_markdown_utils_title_extraction():
    md_text = "Intro line\n\n## Section 2 Title\n\nContent..."
    title = extract_title_from_markdown(md_text)
    assert title == "Section 2 Title"


def test_image_parser(tmp_path: Path):
    img_file = tmp_path / "photo.png"
    # 1x1 transparent PNG bytes
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    img_file.write_bytes(png_bytes)

    parser = ImageParser()
    meta, text = parser.parse(img_file)

    assert meta.filename == "photo.png"
    assert "base64" not in text
    assert "data:image" not in text
    assert "# Image: photo.png" in text
    assert validate_markdown(text)


def test_spreadsheet_parser_csv(tmp_path: Path):
    csv_file = tmp_path / "table.csv"
    csv_file.write_text("col_a,col_b\nval1,val2\nval3,val4\n")

    parser = SpreadsheetParser()
    meta, text = parser.parse(csv_file)

    assert "col_a" in text
    assert "val1" in text
    assert validate_markdown(text)


def test_spreadsheet_parser_tsv(tmp_path: Path):
    tsv_file = tmp_path / "table.tsv"
    tsv_file.write_text("h1\th2\n10\t20\n")

    parser = SpreadsheetParser()
    meta, text = parser.parse(tsv_file)

    assert "h1" in text
    assert "10" in text


def test_pdf_parser_suppresses_warnings(tmp_path: Path):
    import logging
    from pypdf import PdfWriter
    from directory2md.parsers.pdf_parser import PDFParser

    # Create a minimal valid PDF
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    parser = PDFParser()
    meta, text = parser.parse(pdf_path)
    assert meta.filename == "sample.pdf"
    # Ensure pypdf logger is at ERROR level (suppressing warnings)
    assert logging.getLogger("pypdf").level == logging.ERROR


def test_html_parser_web_page(tmp_path: Path):
    from directory2md.parsers.html_parser import HTMLParser

    html_file = tmp_path / "webpage.html"
    html_file.write_text(
        """<!DOCTYPE html>
<html>
<head>
    <title>My Web Page</title>
    <meta name="description" content="A test web page for conversion">
    <meta name="author" content="Test Author">
    <style>body { color: blue; } h1 { font-size: 24px; }</style>
    <script>alert('noise');</script>
</head>
<body>
    <h1>My Web Page</h1>
    <p>This is a paragraph with <strong>bold text</strong> and <a href="https://example.com">a link</a>.</p>
    <blockquote>Wise words from the web.</blockquote>
    <h2>Features Table</h2>
    <table>
        <thead><tr><th>Col 1</th><th>Col 2</th></tr></thead>
        <tbody><tr><td>Val A</td><td>Val B</td></tr></tbody>
    </table>
    <pre><code class="language-python">print('hello world')</code></pre>
</body>
</html>""",
        encoding="utf-8",
    )

    parser = HTMLParser()
    meta, text = parser.parse(html_file)

    assert meta.title == "My Web Page"
    assert "My Web Page" in text
    assert "bold text" in text
    assert "[a link](https://example.com)" in text
    assert "> Wise words from the web." in text
    assert "Val A" in text
    assert "print('hello world')" in text
    # Styles and scripts must be completely stripped
    assert "color: blue" not in text
    assert "alert('noise')" not in text
    assert validate_markdown(text)


def test_html_parser_monolith_archive(tmp_path: Path):
    from directory2md.parsers.html_parser import HTMLParser
    from directory2md.converter import convert_directory

    html_file = tmp_path / "monolith_dump.html"
    # Monolith dump format with embedded base64 image and snapshot comment
    html_file.write_text(
        """<!DOCTYPE html>
<!-- Snapshot taken by Monolith from https://example.com/saved-article at 2026-10-13 10:00:00 -->
<html>
<head>
    <title>Monolith Preserved Article</title>
    <style>@media print { .hidden { display: none; } }</style>
</head>
<body>
    <h1>Monolith Preserved Article</h1>
    <p>Preserved with complete offline assets.</p>
    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=" alt="Preserved Diagram">
    <img src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=">
    <a href="javascript:void(0)">Javascript Link</a>
</body>
</html>""",
        encoding="utf-8",
    )

    parser = HTMLParser()
    meta, text = parser.parse(html_file)

    assert meta.title == "Monolith Preserved Article"
    # Rule 2: NEVER embed raw base64 binary strings!
    assert "data:image" not in text
    assert "base64" not in text
    assert "![Preserved Diagram](<embedded-image>)" in text
    assert "![Image](<embedded-image>)" in text
    assert "javascript:void(0)" not in text
    assert "Javascript Link" in text
    assert validate_markdown(text)

    # Test full converter integration: converts to .html.directory2md.md
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    (src_dir / "monolith_dump.html").write_text(html_file.read_text(encoding="utf-8"), encoding="utf-8")
    dst_dir = tmp_path / "out"
    convert_directory(src_dir, dst_dir)
    converted_file = dst_dir / "monolith_dump.html.directory2md.md"
    assert converted_file.exists()


