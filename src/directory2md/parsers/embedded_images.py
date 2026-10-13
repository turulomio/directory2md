"""Utilities for detecting and extracting embedded images across document formats.

Supports detecting and extracting embedded images in:
- Microsoft Word (.docx)
- Microsoft PowerPoint (.pptx, .potx, .ppsx)
- Microsoft Excel (.xlsx)
- OpenDocument (.odt, .odp, .ods)
- Markdown (.md, .markdown) containing base64 data URIs
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import List, Optional, Set, Tuple
import zipfile

logger = logging.getLogger("directory2md.parsers.embedded_images")

IMAGE_EXTENSIONS: Set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".ico",
    ".tif",
    ".tiff",
    ".emf",
    ".wmf",
}

DATA_URI_IMAGE_PATTERN = re.compile(
    r"data:image/(?P<format>[a-zA-Z0-9\+\-\.]+);base64,(?P<b64>[A-Za-z0-9+/= \r\n]+)",
    re.IGNORECASE,
)

MIME_TO_EXT = {
    "png": ".png",
    "jpeg": ".jpg",
    "jpg": ".jpg",
    "webp": ".webp",
    "gif": ".gif",
    "svg+xml": ".svg",
    "bmp": ".bmp",
    "x-icon": ".ico",
    "tiff": ".tif",
}


@dataclass
class ExtractedImage:
    """An image extracted from a document container."""

    filename: str
    raw_bytes: bytes
    format: str = "png"


def zip_has_media_images(filepath: Path, prefix: str) -> bool:
    """Check if a zip archive contains any image files under the specified prefix.

    Args:
        filepath: Path to the target zip-compatible archive.
        prefix: Subdirectory prefix inside the archive (e.g. 'word/media/').

    Returns:
        True if at least one image file is found under the prefix.
    """
    try:
        if not zipfile.is_zipfile(filepath):
            return False
        with zipfile.ZipFile(filepath, "r") as zf:
            prefix_lower = prefix.lower()
            for name in zf.namelist():
                name_lower = name.lower()
                if name_lower.startswith(prefix_lower) and not name.endswith("/"):
                    ext = Path(name_lower).suffix
                    if ext in IMAGE_EXTENSIONS:
                        return True
    except Exception as exc:
        logger.debug("Error checking zip images for %s: %s", filepath, exc)
        return False
    return False


def extract_zip_media_images(filepath: Path, prefix: str) -> List[ExtractedImage]:
    """Extract all embedded images located under prefix in a zip-compatible archive.

    Args:
        filepath: Path to the archive.
        prefix: Subdirectory prefix inside the archive.

    Returns:
        List of :class:`ExtractedImage` instances.
    """
    images: List[ExtractedImage] = []
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            prefix_lower = prefix.lower()
            matching_names = [
                n
                for n in zf.namelist()
                if n.lower().startswith(prefix_lower)
                and not n.endswith("/")
                and Path(n.lower()).suffix in IMAGE_EXTENSIONS
            ]
            matching_names.sort()

            seen_names: Set[str] = set()
            for idx, member_name in enumerate(matching_names, start=1):
                raw_data = zf.read(member_name)
                ext = Path(member_name).suffix.lower()
                base_name = Path(member_name).name
                if base_name in seen_names or not base_name:
                    base_name = f"image_{idx:03d}{ext}"
                seen_names.add(base_name)

                images.append(
                    ExtractedImage(
                        filename=base_name,
                        raw_bytes=raw_data,
                        format=ext.lstrip("."),
                    )
                )
    except Exception as exc:
        logger.warning("Error extracting embedded images from %s: %s", filepath, exc)
    return images


# Format-specific detection helpers
def docx_has_images(filepath: Path) -> bool:
    """Check if a Word (.docx) document has embedded images."""
    return zip_has_media_images(filepath, "word/media/")


def extract_docx_images(filepath: Path) -> List[ExtractedImage]:
    """Extract embedded images from a Word (.docx) document."""
    return extract_zip_media_images(filepath, "word/media/")


def pptx_has_images(filepath: Path) -> bool:
    """Check if a PowerPoint (.pptx, .potx, .ppsx) presentation has embedded images."""
    return zip_has_media_images(filepath, "ppt/media/")


def extract_pptx_images(filepath: Path) -> List[ExtractedImage]:
    """Extract embedded images from a PowerPoint presentation."""
    return extract_zip_media_images(filepath, "ppt/media/")


def xlsx_has_images(filepath: Path) -> bool:
    """Check if an Excel (.xlsx) spreadsheet has embedded images or charts."""
    return zip_has_media_images(filepath, "xl/media/")


def extract_xlsx_images(filepath: Path) -> List[ExtractedImage]:
    """Extract embedded images from an Excel spreadsheet."""
    return extract_zip_media_images(filepath, "xl/media/")


def opendocument_has_images(filepath: Path) -> bool:
    """Check if an OpenDocument (.odt, .odp, .ods) file has embedded images."""
    return zip_has_media_images(filepath, "Pictures/")


def extract_opendocument_images(filepath: Path) -> List[ExtractedImage]:
    """Extract embedded images from an OpenDocument file."""
    return extract_zip_media_images(filepath, "Pictures/")


def markdown_has_embedded_images(filepath: Path) -> bool:
    """Check if a Markdown document contains embedded base64 data URI images."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        return bool(DATA_URI_IMAGE_PATTERN.search(text))
    except Exception:
        return False


def extract_markdown_embedded_images(filepath: Path) -> Tuple[str, List[ExtractedImage]]:
    """Extract base64 embedded images from a Markdown document and replace with relative links.

    Args:
        filepath: Path to the markdown file.

    Returns:
        Tuple of (modified_markdown_text, list_of_extracted_images).
    """
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "", []

    extracted: List[ExtractedImage] = []
    counter = 0

    def replacer(match: re.Match) -> str:
        nonlocal counter
        counter += 1
        fmt_raw = match.group("format").lower()
        ext = MIME_TO_EXT.get(fmt_raw, f".{fmt_raw}")
        filename = f"image_{counter:03d}{ext}"
        b64_str = match.group("b64").replace("\n", "").replace("\r", "").replace(" ", "")

        try:
            raw_bytes = base64.b64decode(b64_str)
            extracted.append(
                ExtractedImage(
                    filename=filename,
                    raw_bytes=raw_bytes,
                    format=ext.lstrip("."),
                )
            )
            return filename
        except Exception:
            return match.group(0)

    modified_text = DATA_URI_IMAGE_PATTERN.sub(replacer, text)
    return modified_text, extracted
