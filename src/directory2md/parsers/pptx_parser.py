"""Microsoft PowerPoint presentation parser (.pptx, .potx, .ppsx, .ppt, .pot, .pps).

Extracts structured slide contents, shapes, notes, and tables from modern OpenXML (.pptx)
and legacy Microsoft PowerPoint 97-2003 binary compound documents (.ppt).
"""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List, Tuple

import olefile

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

# DrawingML and PresentationML namespaces
PPTX_NAMESPACES = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class PPTXParser(BaseParser):
    """Parser for Microsoft PowerPoint Presentation files (.pptx, .potx, .ppsx, .ppt, .pot, .pps)."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse PowerPoint file and return metadata and extracted slide texts.

        Args:
            filepath: Path to the target presentation file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)

        extracted_text = ""
        ext = filepath.suffix.lower()
        try:
            if ext in (".ppt", ".pot", ".pps"):
                extracted_text = self._parse_ppt_binary(filepath)
            else:
                extracted_text = self._parse_pptx(filepath)
        except Exception as exc:
            extracted_text = f"[Error parsing PowerPoint presentation {filepath.name}: {exc}]"

        clean_text = extracted_text.strip()
        words = clean_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:40]) if words else ""
        metadata.extracted_text = clean_text

        return metadata, clean_text

    def _parse_ppt_binary(self, filepath: Path) -> str:
        """Extract structured slide text from legacy Microsoft PowerPoint 97-2003 binary files (.ppt, .pot, .pps).

        Args:
            filepath: Path to the target .ppt binary file.

        Returns:
            Structured text grouped by slide.
        """
        if not olefile.isOleFile(filepath):
            return self._fallback_extract_strings(filepath.read_bytes())

        output_sections: List[str] = []
        with olefile.OleFileIO(filepath) as ole:
            # Main presentation content stream
            if ole.exists("PowerPoint Document"):
                stream_bytes = ole.openstream("PowerPoint Document").read()
                slides = self._extract_slides_from_ppt_stream(stream_bytes)
                for idx, slide_texts in enumerate(slides, start=1):
                    clean_lines = [t.strip() for t in slide_texts if t.strip()]
                    if clean_lines:
                        output_sections.append(f"--- Slide {idx} ---\n" + "\n".join(clean_lines))

            # Check for additional text streams if nothing found
            if not output_sections:
                for stream_name in ole.listdir():
                    if isinstance(stream_name, list):
                        stream_path = "/".join(stream_name)
                    else:
                        stream_path = str(stream_name)
                    try:
                        data = ole.openstream(stream_name).read()
                        extracted = self._fallback_extract_strings(data)
                        if extracted:
                            output_sections.append(f"=== Stream: {stream_path} ===\n{extracted}")
                    except Exception:
                        continue

        if not output_sections:
            return "_No se encontró texto legible en la presentación PPT._"

        return "\n\n".join(output_sections)

    def _extract_slides_from_ppt_stream(self, stream_bytes: bytes) -> List[List[str]]:
        """Walk binary PowerPoint record atoms and containers to extract slide text."""
        offset = 0
        slides: List[List[str]] = []
        current_slide: List[str] = []

        while offset + 8 <= len(stream_bytes):
            ver_inst, rec_type, rec_len = struct.unpack_from("<HHI", stream_bytes, offset)
            rec_ver = ver_inst & 0x0F
            offset += 8

            if offset + rec_len > len(stream_bytes) and rec_ver != 0x0F:
                break

            # 1006 (0x03EE) = RT_Slide, 1008 (0x03F0) = RT_Notes
            if rec_type in (1006, 1008):
                if current_slide:
                    slides.append(current_slide)
                    current_slide = []
            elif rec_type in (4000, 4026):  # TextCharsAtom / CString (UTF-16LE)
                data = stream_bytes[offset:offset + rec_len]
                try:
                    text = data.decode("utf-16le", errors="replace").strip()
                    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
                    if text and len(text) > 1 and not text.isdigit():
                        current_slide.append(text)
                except Exception:
                    pass
            elif rec_type == 4008:  # TextBytesAtom (Latin-1 / ASCII)
                data = stream_bytes[offset:offset + rec_len]
                try:
                    text = data.decode("latin-1", errors="replace").strip()
                    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
                    if text and len(text) > 1 and not text.isdigit():
                        current_slide.append(text)
                except Exception:
                    pass

            if rec_ver != 0x0F:
                offset += rec_len

        if current_slide:
            slides.append(current_slide)

        return slides

    def _fallback_extract_strings(self, data: bytes) -> str:
        """Extract UTF-16LE and ASCII printable strings from raw binary data."""
        utf16_pattern = re.compile(rb"(?:[\x20-\x7e\xa0-\xff]\x00){4,}")
        ascii_pattern = re.compile(rb"[\x20-\x7e\xa0-\xff]{4,}")

        lines: List[str] = []
        for m in utf16_pattern.finditer(data):
            try:
                t = m.group(0).decode("utf-16le", errors="ignore").strip()
                if len(t) >= 4 and not t.startswith("Microsoft") and not t.startswith("Times"):
                    lines.append(t)
            except Exception:
                pass

        if not lines:
            for m in ascii_pattern.finditer(data):
                try:
                    t = m.group(0).decode("latin-1", errors="ignore").strip()
                    if len(t) >= 4 and not t.startswith("PowerPoint") and not t.startswith("Current"):
                        lines.append(t)
                except Exception:
                    pass

        deduped = []
        for line in lines:
            if not deduped or deduped[-1] != line:
                deduped.append(line)

        return "\n".join(deduped)

    def _parse_pptx(self, filepath: Path) -> str:
        """Extract all slide paragraphs and notes from a .pptx file.

        Args:
            filepath: Path to the presentation file.

        Returns:
            Structured text grouped by slide number.
        """
        output_sections: List[str] = []

        with zipfile.ZipFile(filepath, "r") as zf:
            namelist = zf.namelist()

            # Find slide files and sort numerically (e.g. slide1.xml, slide2.xml, slide10.xml)
            slide_files = [f for f in namelist if f.startswith("ppt/slides/slide") and f.endswith(".xml")]
            
            def _extract_slide_number(fname: str) -> int:
                m = re.search(r"slide(\d+)\.xml$", fname)
                return int(m.group(1)) if m else 0

            slide_files.sort(key=_extract_slide_number)

            for idx, slide_file in enumerate(slide_files, start=1):
                slide_lines: List[str] = [f"--- Slide {idx} ---"]
                xml_data = zf.read(slide_file)
                root = ET.fromstring(xml_data)

                # Extract text paragraphs in slide
                paragraphs = root.findall(".//a:p", PPTX_NAMESPACES) or root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}p")
                for p in paragraphs:
                    text_nodes = p.findall(".//a:t", PPTX_NAMESPACES) or p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t")
                    p_text = "".join(t.text for t in text_nodes if t.text).strip()
                    if p_text:
                        slide_lines.append(p_text)

                if len(slide_lines) > 1:
                    output_sections.append("\n".join(slide_lines))

            # Also check for speaker notes if present
            note_files = [f for f in namelist if f.startswith("ppt/notesSlides/notesSlide") and f.endswith(".xml")]
            if note_files:
                note_files.sort(key=lambda f: int(m.group(1)) if (m := re.search(r"notesSlide(\d+)\.xml$", f)) else 0)
                notes_lines: List[str] = ["=== Speaker Notes ==="]
                for n_file in note_files:
                    xml_data = zf.read(n_file)
                    root = ET.fromstring(xml_data)
                    for p in root.findall(".//a:p", PPTX_NAMESPACES) or root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}p"):
                        text_nodes = p.findall(".//a:t", PPTX_NAMESPACES) or p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t")
                        p_text = "".join(t.text for t in text_nodes if t.text).strip()
                        if p_text and not p_text.isdigit():
                            notes_lines.append(f" - {p_text}")

                if len(notes_lines) > 1:
                    output_sections.append("\n".join(notes_lines))

        return "\n\n".join(output_sections)
