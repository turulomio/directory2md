"""PDF document parser using pypdf.

Extracts text content page-by-page from Portable Document Format (.pdf) files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple
import warnings

# Suppress noisy pypdf fontTools and parser warning messages
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser


class PDFParser(BaseParser):
    """Parser implementation for PDF files."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Extract text from all pages in a PDF document formatted as Markdown.

        Args:
            filepath: Path to the target PDF file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)
        text_parts = []

        try:
            logging.getLogger("pypdf").setLevel(logging.ERROR)
            from pypdf import PdfReader

            reader = PdfReader(str(filepath))
            total_pages = len(reader.pages)
            for idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    if total_pages > 1:
                        text_parts.append(f"## Page {idx}\n\n{page_text.strip()}")
                    else:
                        text_parts.append(page_text.strip())
        except Exception as e:
            text_parts.append(f"[Error reading PDF: {e}]")

        full_text = "\n\n".join(text_parts).strip()
        words = full_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:60]) + ("..." if len(words) > 60 else "")
        metadata.extracted_text = full_text

        return metadata, full_text

