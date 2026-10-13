"""directory2md: Convert a directory tree into Markdown files preserving structure."""

from __future__ import annotations

from directory2md.cli import main
from directory2md.config import (
    AIConfig,
    Config,
    create_default_config_file,
    load_config,
    update_missing_config_keys,
)
from directory2md.converter import (
    ConversionStats,
    DirectoryConverter,
    convert_directory,
    should_exclude,
)
from directory2md.mapper import (
    CONTAINER_SUFFIX,
    MD_SUFFIX,
    PathMapping,
    get_md_path,
    get_original_path,
    resolve_mapping_details,
)

__version__ = "0.1.0"

__all__ = [
    "AIConfig",
    "CONTAINER_SUFFIX",
    "Config",
    "ConversionStats",
    "DirectoryConverter",
    "MD_SUFFIX",
    "PathMapping",
    "convert_directory",
    "create_default_config_file",
    "get_md_path",
    "get_original_path",
    "load_config",
    "main",
    "resolve_mapping_details",
    "should_exclude",
    "update_missing_config_keys",
]

