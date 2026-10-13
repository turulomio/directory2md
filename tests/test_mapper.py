"""Tests for bidirectional path mapping functions."""

from pathlib import Path
import pytest

from directory2md.mapper import (
    get_md_path,
    get_original_path,
    resolve_mapping_details,
)


def test_mapper_normal_files(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    # Create dummy original files
    sub = src_dir / "docs" / "finance"
    sub.mkdir(parents=True)
    f1 = sub / "report.pdf"
    f1.write_text("Dummy content")

    # Forward mapping
    md_p = get_md_path(f1, src_dir, dst_dir)
    assert md_p == dst_dir / "docs" / "finance" / "report.pdf.directory2md.md"

    # Reverse mapping
    orig_p = get_original_path(md_p, src_dir, dst_dir)
    assert orig_p == f1

    # Mapping details
    details = resolve_mapping_details(md_p, src_dir, dst_dir)
    assert details.original_path == f1
    assert not details.is_container
    assert not details.is_container_member


def test_mapper_archive_container(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    # Container archive in source
    archive_file = src_dir / "archives" / "bundle.zip"
    archive_file.parent.mkdir(parents=True)
    archive_file.write_bytes(b"PK...")

    # Forward mapping to container directory
    md_container = get_md_path(archive_file, src_dir, dst_dir)
    assert md_container == dst_dir / "archives" / "bundle.zip.directory2md"

    # Forward mapping to container primary file
    md_primary = get_md_path(archive_file, src_dir, dst_dir, primary_file=True)
    assert md_primary == dst_dir / "archives" / "bundle.zip.directory2md" / "bundle.zip.directory2md.md"

    # Reverse mapping from primary file
    orig_from_primary = get_original_path(md_primary, src_dir, dst_dir)
    assert orig_from_primary == archive_file

    # Reverse mapping from inner member
    member_md = dst_dir / "archives" / "bundle.zip.directory2md" / "inner" / "file.txt.directory2md.md"
    orig_from_member = get_original_path(member_md, src_dir, dst_dir)
    assert orig_from_member == archive_file

    # Mapping details for member
    details = resolve_mapping_details(member_md, src_dir, dst_dir)
    assert details.original_path == archive_file
    assert details.is_container_member
    assert details.container_original_path == archive_file
    assert details.member_subpath == "inner/file.txt.directory2md.md"


def test_mapper_tar_gz_container(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    tar_file = src_dir / "data.tar.gz"
    tar_file.write_bytes(b"dummy")

    md_dir = get_md_path(tar_file, src_dir, dst_dir)
    assert md_dir == dst_dir / "data.tar.gz.directory2md"

    member_path = dst_dir / "data.tar.gz.directory2md" / "nested" / "script.py.directory2md.md"
    orig = get_original_path(member_path, src_dir, dst_dir)
    assert orig == tar_file


def test_mapper_frontmatter_resolution(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    real_source = src_dir / "special" / "source_doc.txt"
    real_source.parent.mkdir(parents=True)
    real_source.write_text("hello")

    md_file = dst_dir / "renamed_output.md"
    md_file.write_text(
        f"---\noriginal_path: {real_source}\nfilename: source_doc.txt\n---\n\nBody",
        encoding="utf-8",
    )

    # Should read frontmatter to identify original path
    orig = get_original_path(md_file, src_dir, dst_dir)
    assert orig == real_source


def test_mapper_html_container(tmp_path: Path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    # 1. HTML with embedded images -> container
    html_with_img = src_dir / "page.html"
    html_with_img.write_text(
        '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=">',
        encoding="utf-8",
    )

    md_dir = get_md_path(html_with_img, src_dir, dst_dir)
    assert md_dir == dst_dir / "page.html.directory2md"

    member_p = dst_dir / "page.html.directory2md" / "image_001.png.directory2md.md"
    orig = get_original_path(member_p, src_dir, dst_dir)
    assert orig == html_with_img

    details = resolve_mapping_details(member_p, src_dir, dst_dir)
    assert details.is_container_member is True
    assert details.container_original_path == html_with_img

    # 2. HTML without images -> regular file
    html_plain = src_dir / "plain.html"
    html_plain.write_text("<p>Hello</p>", encoding="utf-8")

    plain_md = get_md_path(html_plain, src_dir, dst_dir)
    assert plain_md == dst_dir / "plain.html.directory2md.md"


SAMPLE_PDF_WITH_IMAGE = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /ASCIIHexDecode /Length 7 >>
stream
FF0000>
endstream
endobj
5 0 obj
<< /Length 20 >>
stream
BT /F1 12 Tf ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000284 00000 n 
0000000442 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
512
%%EOF"""


def test_mapper_pdf_container(tmp_path: Path):
    src_dir = tmp_path / "src_pdf"
    dst_dir = tmp_path / "dst_pdf"
    src_dir.mkdir()
    dst_dir.mkdir()

    # 1. PDF with embedded images -> container
    pdf_with_img = src_dir / "slides.pdf"
    pdf_with_img.write_bytes(SAMPLE_PDF_WITH_IMAGE)

    md_dir = get_md_path(pdf_with_img, src_dir, dst_dir)
    assert md_dir == dst_dir / "slides.pdf.directory2md"

    member_p = dst_dir / "slides.pdf.directory2md" / "page_001_img_01.png.directory2md.md"
    orig = get_original_path(member_p, src_dir, dst_dir)
    assert orig == pdf_with_img

    details = resolve_mapping_details(member_p, src_dir, dst_dir)
    assert details.is_container_member is True
    assert details.container_original_path == pdf_with_img

    # 2. PDF without images -> regular file
    pdf_plain = src_dir / "plain.pdf"
    pdf_plain.write_bytes(b"%PDF-1.4 \n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")

    plain_md = get_md_path(pdf_plain, src_dir, dst_dir)
    assert plain_md == dst_dir / "plain.pdf.directory2md.md"

