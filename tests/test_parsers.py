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
    assert "data:image/png;base64," in text
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
