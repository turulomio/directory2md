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
