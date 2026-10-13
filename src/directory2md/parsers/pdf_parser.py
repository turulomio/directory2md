from dataclasses import dataclass
import logging
from pathlib import Path
from typing import List, Tuple
import warnings

# Suppress noisy pypdf fontTools and parser warning messages
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", module="pypdf")

from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

logger = logging.getLogger("directory2md.parsers.pdf")


@dataclass
class ExtractedPdfImage:
    """An image extracted from a PDF page."""

    page_number: int
    image_index: int
    filename: str
    raw_bytes: bytes
    format: str = "png"


def pdf_has_images(filepath: Path) -> bool:
    """Check if a PDF file contains any embedded images.

    Fast scan of page images across all pages in the PDF.
    """
    try:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader

        reader = PdfReader(str(filepath))
        for page in reader.pages:
            try:
                images_obj = getattr(page, "images", None)
                if images_obj:
                    for img in images_obj:
                        data = getattr(img, "data", None)
                        if data and isinstance(data, (bytes, bytearray)) and len(data) > 0:
                            return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def extract_pdf_text_and_images(
    filepath: Path,
) -> Tuple[DocumentMetadata, str, List[ExtractedPdfImage]]:
    """Extract page text and embedded images from a PDF file.

    Returns:
        Tuple of (DocumentMetadata, formatted_markdown_text, list_of_extracted_images).
    """
    from directory2md.parsers.base import calculate_sha256

    metadata = DocumentMetadata(
        filepath=str(filepath.resolve()),
        filename=filepath.name,
        file_size_bytes=filepath.stat().st_size if filepath.exists() else 0,
        sha256_hash=calculate_sha256(filepath) if filepath.exists() else "",
    )
    text_parts = []
    extracted_images: List[ExtractedPdfImage] = []

    try:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader

        reader = PdfReader(str(filepath))
        total_pages = len(reader.pages)

        for page_idx, page in enumerate(reader.pages, start=1):
            page_lines = []

            # 1. Extract text
            try:
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    cleaned_text = page_text.strip().encode("utf-8", errors="replace").decode("utf-8")
                    page_lines.append(cleaned_text)
            except Exception as e:
                page_lines.append(f"[Error extracting text from page {page_idx}: {e}]")

            # 2. Extract images
            try:
                images_obj = getattr(page, "images", None)
                if images_obj:
                    for img_idx, img in enumerate(images_obj, start=1):
                        raw_data = getattr(img, "data", None)
                        if not raw_data or not isinstance(raw_data, (bytes, bytearray)):
                            continue
                        name_str = getattr(img, "name", "") or ""
                        ext = Path(name_str).suffix.lower() if name_str else ".png"
                        if not ext or ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"):
                            ext = ".png"

                        clean_name = f"page_{page_idx:03d}_img_{img_idx:02d}{ext}"
                        extracted_images.append(
                            ExtractedPdfImage(
                                page_number=page_idx,
                                image_index=img_idx,
                                filename=clean_name,
                                raw_bytes=bytes(raw_data),
                                format=ext.lstrip("."),
                            )
                        )
                        page_lines.append(f"![Image: {clean_name}]({clean_name})")
            except Exception as e:
                logger.debug("Failed extracting images from page %d of %s: %s", page_idx, filepath, e)

            page_content = "\n\n".join(line for line in page_lines if line).strip()
            if page_content:
                if total_pages > 1:
                    text_parts.append(f"## Page {page_idx}\n\n{page_content}")
                else:
                    text_parts.append(page_content)
    except Exception as e:
        text_parts.append(f"[Error reading PDF: {e}]")

    full_text = "\n\n".join(text_parts).strip()
    words = full_text.split()
    metadata.word_count = len(words)
    metadata.text_snippet = " ".join(words[:60]) + ("..." if len(words) > 60 else "")
    metadata.extracted_text = full_text

    return metadata, full_text, extracted_images


class PDFParser(BaseParser):
    """Parser implementation for PDF files."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Extract text from all pages in a PDF document formatted as Markdown."""
        metadata, full_text, _ = extract_pdf_text_and_images(filepath)
        return metadata, full_text


