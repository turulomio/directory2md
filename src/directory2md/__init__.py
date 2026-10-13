"""directory2md: Convert a directory tree into Markdown files preserving structure."""

from __future__ import annotations

from directory2md.cli import main
from directory2md.converter import ConversionStats, DirectoryConverter, convert_directory
from directory2md.mapper import (
    PathMapping,
    get_md_path,
    get_original_path,
    resolve_mapping_details,
)

__version__ = "0.1.0"

__all__ = [
    "ConversionStats",
    "DirectoryConverter",
    "PathMapping",
    "convert_directory",
    "get_md_path",
    "get_original_path",
    "main",
    "resolve_mapping_details",
]
