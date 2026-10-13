"""Document parsers registry and factory functions.

Maps file extensions to their corresponding specialized parser classes.
"""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Dict, Type

from directory2md.parsers.base import BaseParser
from directory2md.parsers.text_parser import TextParser
from directory2md.parsers.email_parser import EmailParser
from directory2md.parsers.pdf_parser import PDFParser
from directory2md.parsers.docx_parser import DocxParser
from directory2md.parsers.spreadsheet_parser import SpreadsheetParser
from directory2md.parsers.archive_parser import ArchiveParser
from directory2md.parsers.opendocument_parser import OpenDocumentParser
from directory2md.parsers.pptx_parser import PPTXParser
from directory2md.parsers.image_parser import ImageParser

PARSER_MAP: Dict[str, Type[BaseParser]] = {
    ".txt": TextParser,
    ".md": TextParser,
    ".markdown": TextParser,
    ".csv": SpreadsheetParser,
    ".tsv": SpreadsheetParser,
    ".log": TextParser,
    ".json": TextParser,
    ".eml": EmailParser,
    ".msg": EmailParser,
    ".pdf": PDFParser,
    ".docx": DocxParser,
    ".xlsx": SpreadsheetParser,
    ".ods": SpreadsheetParser,
    ".odt": OpenDocumentParser,
    ".odp": OpenDocumentParser,
    ".pptx": PPTXParser,
    ".potx": PPTXParser,
    ".ppsx": PPTXParser,
    ".ppt": PPTXParser,
    ".pot": PPTXParser,
    ".pps": PPTXParser,
    ".zip": ArchiveParser,
    ".tar": ArchiveParser,
    ".gz": ArchiveParser,
    ".tgz": ArchiveParser,
    ".bz2": ArchiveParser,
    ".tbz2": ArchiveParser,
    ".png": ImageParser,
    ".jpg": ImageParser,
    ".jpeg": ImageParser,
    ".gif": ImageParser,
    ".webp": ImageParser,
    ".svg": ImageParser,
    ".bmp": ImageParser,
    ".ico": ImageParser,
    ".tif": ImageParser,
    ".tiff": ImageParser,
}

ARCHIVE_EXTENSIONS = (
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".zip",
    ".tar",
)


def is_archive_file(filepath: Path) -> bool:
    """Check if the given file is an archive container (.zip, .tar, .tar.gz, etc.)."""
    name_lower = filepath.name.lower()
    return any(name_lower.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def is_email_file(filepath: Path) -> bool:
    """Check if the given file is an email message (.eml, .msg)."""
    suffix = filepath.suffix.lower()
    return suffix in (".eml", ".msg")


def email_has_attachments(filepath: Path) -> bool:
    """Check whether an email file (.eml or .msg) contains one or more attachments."""
    suffix = filepath.suffix.lower()
    if suffix == ".msg":
        try:
            import extract_msg

            msg = extract_msg.Message(str(filepath))
            return bool(msg.attachments)
        except Exception:
            return False
    elif suffix == ".eml":
        try:
            with open(filepath, "rb") as f:
                msg = BytesParser(policy=policy.default).parse(f)
            if not msg.is_multipart():
                return False
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", "")).lower()
                filename = part.get_filename()
                if filename or "attachment" in content_disposition:
                    return True
        except Exception:
            return False
    return False


def is_container_file(filepath: Path) -> bool:
    """Determine if a file behaves as a container (directory destination).

    Archives (.zip, .tar.gz, etc.) are always containers.
    Emails (.eml, .msg) are containers only if they contain attachments.
    """
    if is_archive_file(filepath):
        return True
    if is_email_file(filepath):
        return email_has_attachments(filepath)
    return False


def get_parser_for_file(filepath: Path) -> BaseParser:
    """Return the appropriate parser instance for the given file extension.

    If the extension is not explicitly mapped, falls back to :class:`TextParser`.

    Args:
        filepath: Path to the target file.

    Returns:
        An instantiated subclass of :class:`BaseParser`.
    """
    if is_archive_file(filepath):
        return ArchiveParser()

    suffix = filepath.suffix.lower()
    parser_cls = PARSER_MAP.get(suffix, TextParser)
    return parser_cls()
