"""Compressed archive parser for ZIP, TAR, TAR.GZ, TGZ, and TAR.BZ2 files.

Inspects nested archive contents, extracts directory trees and metadata,
and recursively extracts text from supported inner documents.
"""

from __future__ import annotations

import io
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import List, Tuple

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser


class ArchiveParser(BaseParser):
    """Parser for compressed archives (.zip, .tar, .tar.gz, .tgz, .tar.bz2)."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse compressed archive and extract structure and text of contained files.

        Args:
            filepath: Path to the archive file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata, text, _ = self.parse_with_children(filepath)
        return metadata, text

    def parse_with_children(
        self, filepath: Path
    ) -> Tuple[DocumentMetadata, str, List[Tuple[DocumentMetadata, str]]]:
        """Parse compressed archive, extract structure, and return child documents.

        Args:
            filepath: Path to the archive file.

        Returns:
            Tuple of (parent_metadata, archive_text, list_of_child_tuples).
        """
        metadata = self.build_initial_metadata(filepath)
        filename_lower = filepath.name.lower()

        extracted_text = ""
        children: List[Tuple[DocumentMetadata, str]] = []
        try:
            if filename_lower.endswith(".zip"):
                extracted_text, children = self._parse_zip_with_children(filepath, metadata)
            elif (
                filename_lower.endswith(".tar.gz")
                or filename_lower.endswith(".tgz")
                or filename_lower.endswith(".tar.bz2")
                or filename_lower.endswith(".tbz2")
                or filename_lower.endswith(".tar")
            ):
                extracted_text, children = self._parse_tar_with_children(filepath, metadata)
            else:
                extracted_text, children = self._parse_zip_with_children(filepath, metadata)
        except Exception as exc:
            extracted_text = f"[Error reading archive {filepath.name}: {exc}]"

        clean_text = extracted_text.strip()
        words = clean_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:40]) if words else ""
        metadata.extracted_text = clean_text
        metadata.contained_files = [child_meta.filename for child_meta, _ in children]

        return metadata, clean_text, children

    def _parse_zip_with_children(
        self, filepath: Path, parent_meta: DocumentMetadata
    ) -> Tuple[str, List[Tuple[DocumentMetadata, str]]]:
        """Extract structure and individual child documents of a .zip archive."""
        from directory2md.extractors.filename_parser import parse_filename
        from directory2md.parsers.base import calculate_sha256

        sections: List[str] = []
        children: List[Tuple[DocumentMetadata, str]] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            file_list = [info for info in zf.infolist() if not info.is_dir()]
            sections.append(f"=== Archive: {filepath.name} ({len(file_list)} files) ===")
            sections.append("Archive Table of Contents:")
            for item in file_list:
                sections.append(f" - {item.filename} ({item.file_size} bytes)")

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                for item in file_list:
                    if ".." in item.filename or item.filename.startswith("/"):
                        continue

                    safe_inner_name = Path(item.filename).name
                    suffix = Path(item.filename).suffix.lower()
                    if suffix in (
                        ".txt", ".md", ".csv", ".json", ".log",
                        ".pdf", ".docx", ".eml", ".msg", ".xlsx", ".ods",
                        ".odt", ".odp", ".pptx", ".potx", ".ppsx", ".ppt", ".pot", ".pps",
                        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                        ".bmp", ".ico", ".tif", ".tiff"
                    ):
                        try:
                            extracted_file = zf.extract(item, tmp_path)
                            inner_path = Path(extracted_file)
                            if inner_path.is_file():
                                from directory2md.parsers import get_parser_for_file
                                inner_parser = get_parser_for_file(inner_path)
                                child_meta, inner_text = inner_parser.parse(inner_path)

                                # Calculate SHA-256 for child file
                                child_sha = calculate_sha256(inner_path)

                                # Parse child filename or inherit parent metadata
                                child_d_str, child_t_str, child_dt, child_title = parse_filename(inner_path)
                                if not child_d_str:
                                    child_d_str = parent_meta.date_str
                                    child_t_str = parent_meta.time_str
                                    child_dt = parent_meta.timestamp

                                child_meta.filepath = f"{filepath.name}::{item.filename}"
                                child_meta.relative_path = f"{filepath.name}::{item.filename}"
                                child_meta.filename = safe_inner_name
                                child_meta.title = child_title or safe_inner_name
                                child_meta.date_str = child_d_str
                                child_meta.time_str = child_t_str
                                child_meta.timestamp = child_dt
                                child_meta.sha256_hash = child_sha
                                child_meta.parent_document = filepath.name
                                child_meta.origin_type = "archive_member"
                                child_meta.extracted_text = inner_text.strip()
                                child_meta.file_size_bytes = item.file_size

                                children.append((child_meta, inner_text.strip()))

                                if inner_text.strip():
                                    sections.append(f"\n--- Contained File: {item.filename} ---")
                                    sections.append(inner_text.strip())
                        except Exception as exc:
                            sections.append(f"\n[Could not parse contained file {item.filename}: {exc}]")

        return "\n".join(sections), children

    def _parse_tar_with_children(
        self, filepath: Path, parent_meta: DocumentMetadata
    ) -> Tuple[str, List[Tuple[DocumentMetadata, str]]]:
        """Extract structure and individual child documents of a TAR archive."""
        from directory2md.extractors.filename_parser import parse_filename
        from directory2md.parsers.base import calculate_sha256

        sections: List[str] = []
        children: List[Tuple[DocumentMetadata, str]] = []

        mode = "r:*"
        with tarfile.open(filepath, mode) as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            sections.append(f"=== Archive: {filepath.name} ({len(members)} files) ===")
            sections.append("Archive Table of Contents:")
            for m in members:
                sections.append(f" - {m.name} ({m.size} bytes)")

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                for m in members:
                    if ".." in m.name or m.name.startswith("/"):
                        continue

                    safe_inner_name = Path(m.name).name
                    suffix = Path(m.name).suffix.lower()
                    if suffix in (
                        ".txt", ".md", ".csv", ".json", ".log",
                        ".pdf", ".docx", ".eml", ".msg", ".xlsx", ".ods",
                        ".odt", ".odp", ".pptx", ".potx", ".ppsx", ".ppt", ".pot", ".pps",
                        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                        ".bmp", ".ico", ".tif", ".tiff"
                    ):
                        try:
                            tf.extract(m, tmp_path, filter="data" if hasattr(tarfile, "data_filter") else None)
                            inner_path = tmp_path / m.name
                            if inner_path.is_file():
                                from directory2md.parsers import get_parser_for_file
                                inner_parser = get_parser_for_file(inner_path)
                                child_meta, inner_text = inner_parser.parse(inner_path)

                                child_sha = calculate_sha256(inner_path)
                                child_d_str, child_t_str, child_dt, child_title = parse_filename(inner_path)
                                if not child_d_str:
                                    child_d_str = parent_meta.date_str
                                    child_t_str = parent_meta.time_str
                                    child_dt = parent_meta.timestamp

                                child_meta.filepath = f"{filepath.name}::{m.name}"
                                child_meta.relative_path = f"{filepath.name}::{m.name}"
                                child_meta.filename = safe_inner_name
                                child_meta.title = child_title or safe_inner_name
                                child_meta.date_str = child_d_str
                                child_meta.time_str = child_t_str
                                child_meta.timestamp = child_dt
                                child_meta.sha256_hash = child_sha
                                child_meta.parent_document = filepath.name
                                child_meta.origin_type = "archive_member"
                                child_meta.extracted_text = inner_text.strip()
                                child_meta.file_size_bytes = m.size

                                children.append((child_meta, inner_text.strip()))

                                if inner_text.strip():
                                    sections.append(f"\n--- Contained File: {m.name} ---")
                                    sections.append(inner_text.strip())
                        except Exception as exc:
                            sections.append(f"\n[Could not parse contained file {m.name}: {exc}]")

        return "\n".join(sections), children
