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

