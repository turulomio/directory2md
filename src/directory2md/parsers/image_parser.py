"""Image file parser for raster and vector graphics (.png, .jpg, .gif, .webp, .svg, .bmp, .ico, .tiff).

Extracts filename metadata, file dimensions/size, generates base64 data URIs for
safe embedding in static web views, and prevents binary junk text corruption.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Optional, Tuple

from directory2md.ai_client import query_ollama_vision
from directory2md.config import Config
from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

# Common image MIME type mappings
IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable size string (KB, MB).

    Args:
        size_bytes: File size in bytes.

    Returns:
        Formatted string such as '12.4 KB' or '1.5 MB'.
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class ImageParser(BaseParser):
    """Parser for image formats preserving visual assets with optional AI OCR and description."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse an image file, generate metadata, and construct an embedded image representation.

        Args:
            filepath: Path to the image file on disk.

        Returns:
            Tuple of (:class:`DocumentMetadata`, extracted_full_text).
        """
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()
        mime_type = IMAGE_MIME_TYPES.get(suffix) or mimetypes.guess_type(str(filepath))[0] or "image/png"

        size_bytes = metadata.file_size_bytes
        size_str = _format_file_size(size_bytes)

        # Read binary data and convert to base64 Data URI for zero-CORS embedding
        data_uri = ""
        raw_bytes = b""
        try:
            raw_bytes = filepath.read_bytes()
            b64_str = base64.b64encode(raw_bytes).decode("ascii")
            data_uri = f"data:{mime_type};base64,{b64_str}"
        except Exception:
            data_uri = ""

        # Construct clean Markdown representation
        lines = [
            f"# Image: {filepath.name}",
            "",
            f"- **Format:** {suffix.upper().lstrip('.')} (`{mime_type}`)",
            f"- **File Size:** {size_str} ({size_bytes:,} bytes)",
            f"- **Path:** `{filepath.name}`",
            "",
        ]

        if data_uri:
            lines.append(f"![{filepath.name}]({data_uri})")
        else:
            lines.append(f"> *Preview unavailable for {filepath.name}*")
        lines.append("")

        # AI Processing (OCR and Description) if enabled
        used_ai = False
        all_ai_text = []

        if self.config and self.config.ai.enabled and self.config.ai.vision_model and raw_bytes:
            # 1. OCR text extraction
            ocr_text = query_ollama_vision(
                raw_bytes,
                prompt=self.config.ai.prompt_image_ocr,
                ai_config=self.config.ai,
            )
            if ocr_text:
                used_ai = True
                all_ai_text.append(ocr_text)
                lines.extend([
                    "## AI OCR (Extracted Text)",
                    "",
                    ocr_text,
                    "",
                ])

            # 2. Image description
            desc_text = query_ollama_vision(
                raw_bytes,
                prompt=self.config.ai.prompt_image_description,
                ai_config=self.config.ai,
            )
            if desc_text:
                used_ai = True
                all_ai_text.append(desc_text)
                lines.extend([
                    "## AI Image Description",
                    "",
                    desc_text,
                    "",
                ])

        metadata.ia = used_ai

        clean_text = "\n".join(lines).strip()
        if all_ai_text:
            combined = " ".join(all_ai_text)
            words = combined.split()
            metadata.word_count = len(words)
            metadata.text_snippet = " ".join(words[:60])
        else:
            metadata.word_count = 0
            metadata.text_snippet = f"[Image ({suffix.upper().lstrip('.')}) • {size_str}]"

        metadata.extracted_text = clean_text
        return metadata, clean_text

