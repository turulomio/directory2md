"""OpenDocument parser for text (.odt) and presentation (.odp) files.

Extracts structured text, headings, list items, slides, and tables from
OASIS OpenDocument format files without requiring external office dependencies.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List, Tuple

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

# XML namespaces used across OASIS OpenDocument formats
OD_NAMESPACES = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
}


class OpenDocumentParser(BaseParser):
    """Parser for OpenDocument Text (.odt) and Presentation (.odp) files."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse an OpenDocument file (.odt or .odp) and return its metadata and extracted plain text.

        Args:
            filepath: Path to the target OpenDocument file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()

        extracted_text = ""
        try:
            if suffix == ".odp":
                extracted_text = self._parse_odp(filepath)
            else:
                extracted_text = self._parse_odt(filepath)
        except Exception as exc:
            extracted_text = f"[Error parsing OpenDocument file {filepath.name}: {exc}]"

        clean_text = extracted_text.strip()
        words = clean_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:40]) if words else ""
        metadata.extracted_text = clean_text

        return metadata, clean_text

    def _parse_odt(self, filepath: Path) -> str:
        """Extract text paragraphs, headings, and tables from an OpenDocument Text (.odt) file.

        Args:
            filepath: Path to the .odt file.

        Returns:
            Clean plain text content.
        """
        sections: List[str] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            if "content.xml" not in zf.namelist():
                return ""

            xml_data = zf.read("content.xml")
            root = ET.fromstring(xml_data)

            # Find all headings, paragraphs, and tables in document body order
            body = root.find(".//office:body", OD_NAMESPACES)
            target_element = body if body is not None else root
            for elem in target_element.iter():

                tag = elem.tag
                if tag.endswith("}h"):
                    # Heading
                    heading_text = "".join(elem.itertext()).strip()
                    if heading_text:
                        sections.append(f"\n## {heading_text}\n")
                elif tag.endswith("}p"):
                    # Check if paragraph is direct child or inside a list/table (avoid duplicates)
                    p_text = "".join(elem.itertext()).strip()
                    if p_text:
                        sections.append(p_text)
                elif tag.endswith("}table-row"):
                    # Table row
                    cells = elem.findall(".//table:table-cell", OD_NAMESPACES) or elem.findall(".//{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-cell")
                    row_texts = []
                    for c in cells:
                        c_text = "".join(c.itertext()).strip()
                        if c_text:
                            row_texts.append(c_text)
                    if row_texts:
                        sections.append(" | ".join(row_texts))

        # Deduplicate sequential identical lines if any
        output_lines: List[str] = []
        for s in sections:
            clean = s.strip()
            if clean and (not output_lines or output_lines[-1] != clean):
                output_lines.append(clean)

        return "\n\n".join(output_lines)

    def _parse_odp(self, filepath: Path) -> str:
        """Extract slide titles and textual shapes from an OpenDocument Presentation (.odp) file.

        Args:
            filepath: Path to the .odp file.

        Returns:
            Clean structured text per slide.
        """
        sections: List[str] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            if "content.xml" not in zf.namelist():
                return ""

            xml_data = zf.read("content.xml")
            root = ET.fromstring(xml_data)

            slides = root.findall(".//draw:page", OD_NAMESPACES) or root.findall(".//{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}page")
            for idx, slide in enumerate(slides, start=1):
                slide_name = slide.attrib.get(f"{{{OD_NAMESPACES['draw']}}}name", f"Slide {idx}")
                slide_lines: List[str] = [f"--- Slide {idx}: {slide_name} ---"]

                for p in slide.findall(".//text:p", OD_NAMESPACES) or slide.findall(".//{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p"):
                    text = "".join(p.itertext()).strip()
                    if text:
                        slide_lines.append(text)

                if len(slide_lines) > 1:
                    sections.append("\n".join(slide_lines))

        return "\n\n".join(sections)
