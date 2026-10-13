"""Tests for converter engine and incremental update logic."""

from datetime import datetime, timedelta
import os
from pathlib import Path
import pytest

from directory2md.converter import DirectoryConverter, convert_directory
from directory2md.markdown_utils import parse_frontmatter


def test_convert_directory_basic(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    # Create test source structure
    (src / "sub1").mkdir()
    f1 = src / "sub1" / "hello.txt"
    f1.write_text("Hello world text content", encoding="utf-8")

    f2 = src / "notes.md"
    f2.write_text("# Meeting Notes\n\nDiscussion points here.", encoding="utf-8")

    f3 = src / "data.csv"
    f3.write_text("id,name,val\n1,Alice,100\n2,Bob,200\n", encoding="utf-8")

    stats = convert_directory(src, dst)
    assert stats.total_scanned == 3
    assert stats.converted == 3
    assert stats.skipped == 0
    assert not stats.has_errors

    # Check that destinations exist with .md suffix added
    dst_f1 = dst / "sub1" / "hello.txt.md"
    dst_f2 = dst / "notes.md.md"
    dst_f3 = dst / "data.csv.md"

    assert dst_f1.exists()
    assert dst_f2.exists()
    assert dst_f3.exists()

    # Verify frontmatter in dst_f1
    fm, body = parse_frontmatter(dst_f1.read_text(encoding="utf-8"))
    assert fm["filename"] == "hello.txt"
    assert "Hello world" in body
    assert "conversion_date" in fm
    assert fm["original_path"] == str(f1.resolve())


def test_incremental_skip_when_recent(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    f1 = src / "doc.txt"
    f1.write_text("Initial text")

    # First run
    stats1 = convert_directory(src, dst)
    assert stats1.converted == 1
    assert stats1.skipped == 0

    # Second run without modifications
    stats2 = convert_directory(src, dst)
    assert stats2.converted == 0
    assert stats2.skipped == 1


def test_incremental_update_when_source_modified(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    f1 = src / "doc.txt"
    f1.write_text("Version 1")

    # Run 1
    convert_directory(src, dst)
    dst_file = dst / "doc.txt.md"

    # Set dst_file mtime back 10 seconds
    past_mtime = (datetime.now() - timedelta(seconds=10)).timestamp()
    os.utime(dst_file, (past_mtime, past_mtime))

    # Modify source file (newer mtime)
    f1.write_text("Version 2 updated content")

    # Run 2
    stats = convert_directory(src, dst)
    assert stats.converted == 1
    assert stats.skipped == 0

    _, body = parse_frontmatter(dst_file.read_text(encoding="utf-8"))
    assert "Version 2 updated content" in body


def test_incremental_update_when_older_than_threshold(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    f1 = src / "doc.txt"
    f1.write_text("Untouched content")

    convert_directory(src, dst)
    dst_file = dst / "doc.txt.md"

    # Set dst_file to 200 days old (default threshold is 180)
    old_time = (datetime.now() - timedelta(days=200)).timestamp()
    os.utime(dst_file, (old_time, old_time))
    os.utime(f1, (old_time - 100, old_time - 100))  # source even older

    # Run with default 180 days -> should re-convert because dst > 180 days old
    stats = convert_directory(src, dst, max_age_days=180)
    assert stats.converted == 1
    assert stats.skipped == 0


def test_force_flag_re_converts(tmp_path: Path):
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()

    f1 = src / "doc.txt"
    f1.write_text("Content")

    convert_directory(src, dst)

    # Re-run with force=True
    stats = convert_directory(src, dst, force=True)
    assert stats.converted == 1
    assert stats.skipped == 0
