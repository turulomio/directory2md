"""Tests for container files (zip, tar.gz, eml with/without attachments)."""

from email.message import EmailMessage
import io
from pathlib import Path
import tarfile
import zipfile
import pytest

from directory2md.converter import convert_directory
from directory2md.markdown_utils import parse_frontmatter


def test_zip_container_conversion(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    # Create a zip archive with multiple files
    zip_path = src / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("notes.txt", "Important notes inside zip")
        zf.writestr("sub/data.csv", "col1,col2\na,1\nb,2\n")

    stats = convert_directory(src, dst)
    assert stats.converted == 1

    # Destination should be a directory named 'bundle.zip.directory2md'
    container_dir = dst / "bundle.zip.directory2md"
    assert container_dir.is_dir()

    # Primary summary file
    primary_md = container_dir / "bundle.zip.directory2md.md"
    assert primary_md.is_file()
    fm, body = parse_frontmatter(primary_md.read_text(encoding="utf-8"))
    assert fm["filename"] == "bundle.zip"
    assert "Archive Table of Contents" in body
    assert "conversion_time" in fm
    assert isinstance(fm["conversion_time"], (int, float))

    # Children files converted with .directory2md.md
    child1 = container_dir / "notes.txt.directory2md.md"
    assert child1.is_file()
    fm1, body1 = parse_frontmatter(child1.read_text(encoding="utf-8"))
    assert "Important notes inside zip" in body1
    assert fm1["archive_member"] == "notes.txt"
    assert "conversion_time" in fm1

    child2 = container_dir / "sub" / "data.csv.directory2md.md"
    assert child2.is_file()
    fm2, body2 = parse_frontmatter(child2.read_text(encoding="utf-8"))
    assert "col1" in body2
    assert fm2["archive_member"] == "sub/data.csv"


def test_tar_gz_container_conversion(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    tar_path = src / "archive.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        data = b"Hello from tar file"
        ti = tarfile.TarInfo("greeting.txt")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))

    stats = convert_directory(src, dst)
    assert stats.converted == 1

    container_dir = dst / "archive.tar.gz.directory2md"
    assert container_dir.is_dir()

    primary_md = container_dir / "archive.tar.gz.directory2md.md"
    assert primary_md.is_file()

    child = container_dir / "greeting.txt.directory2md.md"
    assert child.is_file()
    _, body = parse_frontmatter(child.read_text(encoding="utf-8"))
    assert "Hello from tar file" in body


def test_eml_without_attachments_is_single_file(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    # Create plain email without attachments
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Simple Email"
    msg["Date"] = "Mon, 13 Oct 2026 10:00:00 +0000"
    msg.set_content("This is a simple email without any attachments.")

    eml_path = src / "simple.eml"
    eml_path.write_bytes(msg.as_bytes())

    convert_directory(src, dst)

    # Should NOT be a directory; should be a single file with .directory2md.md suffix added
    dst_file = dst / "simple.eml.directory2md.md"
    assert dst_file.is_file()
    assert not (dst / "simple.eml.directory2md").is_dir()

    fm, body = parse_frontmatter(dst_file.read_text(encoding="utf-8"))
    assert fm["filename"] == "simple.eml"
    assert "alice@example.com" in body
    assert "This is a simple email without any attachments." in body


def test_eml_with_attachments_is_container_directory(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    # Create email WITH an attachment
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Subject"] = "Email With Attachment"
    msg.set_content("Check the attached report.")
    msg.add_attachment(
        b"Invoice content details",
        maintype="text",
        subtype="plain",
        filename="invoice.txt",
    )

    eml_path = src / "with_attachment.eml"
    eml_path.write_bytes(msg.as_bytes())

    convert_directory(src, dst)

    # Should be a container directory named 'with_attachment.eml.directory2md'
    container_dir = dst / "with_attachment.eml.directory2md"
    assert container_dir.is_dir()

    # Primary email markdown
    primary_md = container_dir / "with_attachment.eml.directory2md.md"
    assert primary_md.is_file()
    fm, body = parse_frontmatter(primary_md.read_text(encoding="utf-8"))
    assert "Check the attached report." in body
    assert "invoice.txt" in fm["contained_files"]

    # Attachment converted to markdown
    att_md = container_dir / "invoice.txt.directory2md.md"
    assert att_md.is_file()
    fm_att, body_att = parse_frontmatter(att_md.read_text(encoding="utf-8"))
    assert "Invoice content details" in body_att
    assert fm_att["attachment_name"] == "invoice.txt"


def test_container_error_cleans_entire_directory(tmp_path: Path):
    from unittest.mock import patch
    from directory2md.converter import DirectoryConverter

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Subject"] = "Broken Email Attachment"
    msg.set_content("Check attached.")
    msg.add_attachment(b"broken content", maintype="text", subtype="plain", filename="broken.txt")

    eml_path = src / "fail.eml"
    eml_path.write_bytes(msg.as_bytes())

    # Cause attachment conversion to crash
    orig_convert = DirectoryConverter._convert_single_file

    def failing_convert(self, s_file, r_file, d_file, extra_frontmatter=None):
        if "broken.txt" in str(r_file):
            raise ValueError("Failure converting attachment broken.txt")
        return orig_convert(self, s_file, r_file, d_file, extra_frontmatter)

    logged = []
    with patch.object(DirectoryConverter, "_convert_single_file", failing_convert):
        stats = convert_directory(src, dst, log_callback=logged.append)

    assert stats.has_errors
    container_dir = dst / "fail.eml.directory2md"
    assert not container_dir.exists()
    assert len(list(dst.rglob("*.md"))) == 0


def test_docx_with_and_without_images_container_conversion(tmp_path: Path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()

    # 1. DOCX with embedded images -> container directory
    docx_with_img = src / "document_with_img.docx"
    with zipfile.ZipFile(docx_with_img, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Doc text</w:t></w:r></w:p></w:body></w:document>")
        zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\nfake_image_data")

    # 2. DOCX without images -> regular file
    docx_no_img = src / "plain.docx"
    with zipfile.ZipFile(docx_no_img, "w") as zf:
        zf.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Plain text</w:t></w:r></w:p></w:body></w:document>")

    stats = convert_directory(src, dst)
    assert stats.converted == 2

    # Container check for document_with_img
    container_dir = dst / "document_with_img.docx.directory2md"
    assert container_dir.is_dir()
    primary_md = container_dir / "document_with_img.docx.directory2md.md"
    assert primary_md.is_file()
    assert "image1.png" in primary_md.read_text(encoding="utf-8")
    member_md = container_dir / "image1.png.directory2md.md"
    assert member_md.is_file()

    # Regular single file check for plain.docx
    assert (dst / "plain.docx.directory2md.md").is_file()
    assert not (dst / "plain.docx.directory2md").exists()


def test_pptx_with_and_without_images_container_conversion(tmp_path: Path):
    src = tmp_path / "src_ppt"
    dst = tmp_path / "dst_ppt"
    src.mkdir()

    # 1. PPTX with embedded images
    pptx_with_img = src / "slides_img.pptx"
    with zipfile.ZipFile(pptx_with_img, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<p:presentation/>")
        zf.writestr("ppt/slides/slide1.xml", "<p:sld><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide 1</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>")
        zf.writestr("ppt/media/photo.jpg", b"\xff\xd8\xff\xe0fake_jpeg_data")

    # 2. PPTX without images
    pptx_no_img = src / "slides_plain.pptx"
    with zipfile.ZipFile(pptx_no_img, "w") as zf:
        zf.writestr("ppt/presentation.xml", "<p:presentation/>")
        zf.writestr("ppt/slides/slide1.xml", "<p:sld><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Slide plain</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>")

    stats = convert_directory(src, dst)
    assert stats.converted == 2

    container_dir = dst / "slides_img.pptx.directory2md"
    assert container_dir.is_dir()
    assert (container_dir / "slides_img.pptx.directory2md.md").is_file()
    assert (container_dir / "photo.jpg.directory2md.md").is_file()

    # Plain file
    assert (dst / "slides_plain.pptx.directory2md.md").is_file()
    assert not (dst / "slides_plain.pptx.directory2md").exists()


def test_xlsx_and_opendocument_with_images_container_conversion(tmp_path: Path):
    src = tmp_path / "src_office"
    dst = tmp_path / "dst_office"
    src.mkdir()

    # XLSX with images
    xlsx_img = src / "financial.xlsx"
    with zipfile.ZipFile(xlsx_img, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
        zf.writestr("xl/media/chart.png", b"\x89PNG\r\n\x1a\nchart_data")

    # ODT with images
    odt_img = src / "report.odt"
    with zipfile.ZipFile(odt_img, "w") as zf:
        zf.writestr("content.xml", "<office:document-content/>")
        zf.writestr("Pictures/figure.png", b"\x89PNG\r\n\x1a\nfigure_data")

    stats = convert_directory(src, dst)
    assert stats.converted == 2

    # XLSX container
    xlsx_container = dst / "financial.xlsx.directory2md"
    assert xlsx_container.is_dir()
    assert (xlsx_container / "financial.xlsx.directory2md.md").is_file()
    assert (xlsx_container / "chart.png.directory2md.md").is_file()

    # ODT container
    odt_container = dst / "report.odt.directory2md"
    assert odt_container.is_dir()
    assert (odt_container / "report.odt.directory2md.md").is_file()
    assert (odt_container / "figure.png.directory2md.md").is_file()


def test_markdown_with_embedded_images_container_conversion(tmp_path: Path):
    src = tmp_path / "src_md"
    dst = tmp_path / "dst_md"
    src.mkdir()

    # Minimal 1x1 png base64
    b64_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    md_with_img = src / "article.md"
    md_with_img.write_text(
        f"# Article with Data URI\n\nInline chart:\n![Chart](data:image/png;base64,{b64_png})\n\nEnd text.",
        encoding="utf-8",
    )

    md_no_img = src / "simple.md"
    md_no_img.write_text("# Simple Article\n\nNo embedded images here.", encoding="utf-8")

    stats = convert_directory(src, dst)
    assert stats.converted == 2

    # Article container
    container_dir = dst / "article.md.directory2md"
    assert container_dir.is_dir()
    primary_md = container_dir / "article.md.directory2md.md"
    assert primary_md.is_file()
    text = primary_md.read_text(encoding="utf-8")
    assert "data:image" not in text
    assert "image_001.png" in text

    member_md = container_dir / "image_001.png.directory2md.md"
    assert member_md.is_file()

    # Simple plain markdown
    assert (dst / "simple.md.directory2md.md").is_file()
    assert not (dst / "simple.md.directory2md").exists()


