"""Plain text and Markdown document parser.

Handles plain text files (.txt, .md, .markdown, .csv, .log) with robust
multi-encoding detection (UTF-8, Latin-1, CP1252).
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser


class TextParser(BaseParser):
    """Parser implementation for plain text, markdown, and log files."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Read text and markdown files with multi-encoding support and Markdown-It processing.

        Args:
            filepath: Path to the target text file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)
        text = ""

        # Attempt multiple encodings to handle legacy or Windows-encoded text files
        for enc in ["utf-8", "latin-1", "cp1252"]:
            try:
                text = filepath.read_text(encoding=enc, errors="replace")
                break
            except Exception:
                continue

        # If it's a Markdown file, use markdown-it-py to validate structure and extract title
        if filepath.suffix.lower() in (".md", ".markdown"):
            try:
                from markdown_it import MarkdownIt
                md_parser = MarkdownIt()
                tokens = md_parser.parse(text)
                for i, token in enumerate(tokens):
                    if token.type == "heading_open" and token.tag in ("h1", "h2") and i + 1 < len(tokens):
                        heading_text = tokens[i + 1].content.strip()
                        if heading_text and metadata.title == Path(metadata.filename).stem:
                            metadata.title = heading_text
                        break
            except Exception:
                pass

        words = text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:50]) + ("..." if len(words) > 50 else "")
        metadata.extracted_text = text

        return metadata, text

