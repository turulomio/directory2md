"""Base interfaces and filesystem utilities for document parsers.

Defines the abstract :class:`BaseParser` interface and common helper functions
such as SHA-256 hash calculation and initial metadata extraction.
"""

from __future__ import annotations

import abc
import hashlib
from pathlib import Path
from typing import Tuple

from directory2md.models import DocumentMetadata
from directory2md.extractors.filename_parser import parse_filename


def calculate_sha256(filepath: Path) -> str:
    """Calculate the hexadecimal SHA-256 hash of a file on disk.

    Args:
        filepath: Path to the target file.

    Returns:
        Hexadecimal SHA-256 string, or empty string if file cannot be read.
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class BaseParser(abc.ABC):
    """Abstract base class for all file format parsers in directory2md."""

    @abc.abstractmethod
    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse a document file and return its metadata and extracted plain text.

        Args:
            filepath: Path to the document file.

        Returns:
            A tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        pass

    def build_initial_metadata(self, filepath: Path) -> DocumentMetadata:
        """Extract baseline metadata from filename patterns and filesystem stats.

        Args:
            filepath: Path to the document file.

        Returns:
            A populated :class:`DocumentMetadata` object.
        """
        date_str, time_str, dt, clean_title = parse_filename(filepath)
        size = filepath.stat().st_size if filepath.exists() else 0
        sha = calculate_sha256(filepath) if filepath.exists() else ""

        return DocumentMetadata(
            filepath=filepath.name,
            relative_path=filepath.name,
            filename=filepath.name,
            extension=filepath.suffix.lower(),
            date_str=date_str,
            time_str=time_str,
            timestamp=dt,
            title=clean_title,
            file_size_bytes=size,
            sha256_hash=sha,
        )
