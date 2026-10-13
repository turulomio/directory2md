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
from directory2md.parsers.media_parser import AudioParser, VideoParser
from directory2md.parsers.html_parser import HTMLParser

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
    # Image formats
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
    # Audio formats
    ".mp3": AudioParser,
    ".wav": AudioParser,
    ".m4a": AudioParser,
    ".ogg": AudioParser,
    ".flac": AudioParser,
    ".aac": AudioParser,
    ".wma": AudioParser,
    # Video formats
    ".mp4": VideoParser,
    ".mkv": VideoParser,
    ".avi": VideoParser,
    ".mov": VideoParser,
    ".webm": VideoParser,
    ".flv": VideoParser,
    ".wmv": VideoParser,
    # Web / HTML formats (including Monolith and SingleFile)
    ".html": HTMLParser,
    ".htm": HTMLParser,
    ".xhtml": HTMLParser,
    ".mhtml": HTMLParser,
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


def is_html_file(filepath: Path) -> bool:
    """Check if the given file is an HTML or web document (.html, .htm, .xhtml, .mhtml)."""
    suffix = filepath.suffix.lower()
    return suffix in (".html", ".htm", ".xhtml", ".mhtml")


def is_pdf_file(filepath: Path) -> bool:
    """Check if the given file is a PDF document (.pdf)."""
    return filepath.suffix.lower() == ".pdf"


def is_docx_file(filepath: Path) -> bool:
    """Check if the given file is a Microsoft Word (.docx) document."""
    return filepath.suffix.lower() == ".docx"


def is_pptx_file(filepath: Path) -> bool:
    """Check if the given file is a Microsoft PowerPoint (.pptx, .potx, .ppsx) presentation."""
    return filepath.suffix.lower() in (".pptx", ".potx", ".ppsx")


def is_xlsx_file(filepath: Path) -> bool:
    """Check if the given file is an Excel spreadsheet (.xlsx)."""
    return filepath.suffix.lower() == ".xlsx"


def is_opendocument_file(filepath: Path) -> bool:
    """Check if the given file is an OpenDocument format (.odt, .odp, .ods)."""
    return filepath.suffix.lower() in (".odt", ".odp", ".ods")


def is_markdown_file(filepath: Path) -> bool:
    """Check if the given file is a Markdown document (.md, .markdown)."""
    return filepath.suffix.lower() in (".md", ".markdown")


def is_container_file(filepath: Path) -> bool:
    """Determine if a file behaves as a container (directory destination).

    Containers include:
    - Archives (.zip, .tar.gz, etc.)
    - Emails (.eml, .msg) with attachments
    - Documents with embedded images:
      - PDF (.pdf) with embedded images
      - HTML/web pages (.html, .htm, .xhtml, .mhtml) with embedded images
      - Word (.docx) with embedded images
      - PowerPoint (.pptx, .potx, .ppsx) with embedded images
      - Excel (.xlsx) with embedded images
      - OpenDocument (.odt, .odp, .ods) with embedded images
      - Markdown (.md, .markdown) with embedded images
    """
    if is_archive_file(filepath):
        return True
    if is_email_file(filepath):
        return email_has_attachments(filepath)
    suffix = filepath.suffix.lower()
    if suffix in (".html", ".htm", ".xhtml", ".mhtml"):
        from directory2md.parsers.html_parser import html_has_embedded_images

        return html_has_embedded_images(filepath)
    if suffix == ".pdf":
        from directory2md.parsers.pdf_parser import pdf_has_images

        return pdf_has_images(filepath)
    if suffix == ".docx":
        from directory2md.parsers.embedded_images import docx_has_images

        return docx_has_images(filepath)
    if suffix in (".pptx", ".potx", ".ppsx"):
        from directory2md.parsers.embedded_images import pptx_has_images

        return pptx_has_images(filepath)
    if suffix == ".xlsx":
        from directory2md.parsers.embedded_images import xlsx_has_images

        return xlsx_has_images(filepath)
    if suffix in (".odt", ".odp", ".ods"):
        from directory2md.parsers.embedded_images import opendocument_has_images

        return opendocument_has_images(filepath)
    if suffix in (".md", ".markdown"):
        from directory2md.parsers.embedded_images import markdown_has_embedded_images

        return markdown_has_embedded_images(filepath)
    return False


def get_parser_for_file(filepath: Path, config: Optional[Any] = None) -> BaseParser:
    """Return the appropriate parser instance for the given file extension.

    If the extension is not explicitly mapped, falls back to :class:`TextParser`.

    Args:
        filepath: Path to the target file.
        config: Optional Config instance for AI and media parsers.

    Returns:
        An instantiated subclass of :class:`BaseParser`.
    """
    if is_archive_file(filepath):
        return ArchiveParser()

    suffix = filepath.suffix.lower()
    parser_cls = PARSER_MAP.get(suffix, TextParser)
    if parser_cls in (ImageParser, AudioParser, VideoParser, HTMLParser):
        return parser_cls(config=config)
    return parser_cls()

