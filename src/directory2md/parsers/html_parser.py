import base64
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
import logging
import mimetypes
from pathlib import Path
import re
from typing import List, Optional, Tuple
import urllib.parse

from bs4 import BeautifulSoup, Comment
from markdownify import MarkdownConverter

from directory2md.config import Config
from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

logger = logging.getLogger("directory2md.parsers.html")

MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/tiff": ".tif",
}


@dataclass
class ExtractedEmbeddedImage:
    """An image extracted from an HTML or MHTML container document."""

    index: int
    filename: str
    raw_bytes: bytes
    alt: str = ""
    mime_type: str = "image/png"


def html_has_embedded_images(filepath: Path) -> bool:
    """Check if an HTML, XHTML, or MHTML document contains embedded images.

    Fast pre-scans binary contents for data URI or MIME image declarations,
    then confirms if at least one embedded image exists.
    """
    try:
        suffix = filepath.suffix.lower()
        raw = filepath.read_bytes()

        if suffix == ".mhtml":
            return (
                b"Content-Type: image/" in raw
                or b"content-type: image/" in raw
                or b"data:image/" in raw
            )

        # HTML / XHTML fast pre-scan
        if b"data:image/" not in raw:
            return False

        # Verify occurrence inside <img> tags
        text = raw.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(text, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src and src.strip().lower().startswith("data:image/"):
                return True
        return False
    except Exception:
        return False


def extract_html_embedded_images(
    raw_bytes: bytes,
    suffix: str = ".html",
) -> Tuple[str, List[ExtractedEmbeddedImage]]:
    """Extract embedded images from HTML or MHTML and replace data URIs with relative image filenames.

    Args:
        raw_bytes: Raw file bytes.
        suffix: File extension (e.g. '.html', '.mhtml').

    Returns:
        Tuple of (modified_html_string, list_of_extracted_images).
    """
    extracted: List[ExtractedEmbeddedImage] = []

    if suffix.lower() == ".mhtml":
        try:
            msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
            html_content = ""
            # Locate HTML body part
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        html_content = part.get_content()
                    except Exception:
                        payload = part.get_payload(decode=True)
                        if payload:
                            html_content = payload.decode("utf-8", errors="ignore")
                    break

            if not html_content:
                html_content = raw_bytes.decode("utf-8", errors="ignore")

            idx = 1
            for part in msg.walk():
                if part.get_content_maintype() == "image":
                    c_type = part.get_content_type().lower()
                    ext = MIME_TO_EXT.get(c_type, ".png")
                    filename = part.get_filename() or f"image_{idx:03d}{ext}"
                    # Normalize filename to safe member name
                    clean_filename = f"image_{idx:03d}{ext}"
                    try:
                        img_bytes = part.get_content()
                        if isinstance(img_bytes, str):
                            img_bytes = img_bytes.encode("utf-8")
                    except Exception:
                        img_bytes = part.get_payload(decode=True) or b""

                    if img_bytes:
                        extracted.append(
                            ExtractedEmbeddedImage(
                                index=idx,
                                filename=clean_filename,
                                raw_bytes=img_bytes,
                                alt=filename or f"Image {idx}",
                                mime_type=c_type,
                            )
                        )
                        # Replace cid: and Content-Location references in HTML
                        cid = str(part.get("Content-ID", "")).strip("<>")
                        loc = str(part.get("Content-Location", "")).strip()
                        if cid:
                            html_content = html_content.replace(f"cid:{cid}", clean_filename)
                        if loc:
                            html_content = html_content.replace(loc, clean_filename)
                        idx += 1

            return html_content, extracted
        except Exception as exc:
            logger.warning("Failed extracting MHTML images: %s", exc)

    # Standard HTML / XHTML parsing with BeautifulSoup
    from directory2md.parsers.html_parser import HTMLParser

    html_text = HTMLParser._decode_html_bytes(raw_bytes)
    soup = BeautifulSoup(html_text, "html.parser")

    idx = 1
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src or not src.strip().lower().startswith("data:image/"):
            continue

        src_clean = src.strip()
        header_match = re.match(r"^data:(image/[a-zA-Z0-9\+\-\.]+)(?:;charset=[^;,]+)?(;base64)?,(.*)$", src_clean, re.DOTALL | re.IGNORECASE)
        if not header_match:
            continue

        mime_type = header_match.group(1).lower()
        is_base64 = bool(header_match.group(2))
        data_part = header_match.group(3)

        ext = MIME_TO_EXT.get(mime_type, ".png")
        filename = f"image_{idx:03d}{ext}"

        raw_img_data = b""
        try:
            if is_base64:
                raw_img_data = base64.b64decode(re.sub(r"\s+", "", data_part))
            else:
                raw_img_data = urllib.parse.unquote_to_bytes(data_part)
        except Exception as exc:
            logger.debug("Failed decoding embedded image %d: %s", idx, exc)
            continue

        if raw_img_data:
            alt_text = img.get("alt", "") or f"Image {idx}"
            extracted.append(
                ExtractedEmbeddedImage(
                    index=idx,
                    filename=filename,
                    raw_bytes=raw_img_data,
                    alt=alt_text,
                    mime_type=mime_type,
                )
            )
            # Replace img src in the soup with relative container member filename
            img["src"] = filename
            idx += 1

    return str(soup), extracted

MONOLITH_URL_PATTERNS = [
    re.compile(r"Snapshot taken by (?:monolith|Monolith) from (https?://\S+)", re.IGNORECASE),
    re.compile(r"Page saved (?:by|with) SingleFile from (https?://\S+)", re.IGNORECASE),
    re.compile(r"Saved from (https?://\S+)", re.IGNORECASE),
    re.compile(r"url:\s*(https?://\S+)", re.IGNORECASE),
]


def _extract_code_language(el) -> str:
    """Extract code programming language from HTML class names."""
    code_el = el.find("code") if hasattr(el, "find") else None
    target = code_el if code_el else el
    classes = target.get("class", [])
    if isinstance(classes, str):
        classes = classes.split()
    for cls in classes:
        cls_lower = cls.lower()
        if cls_lower.startswith("language-"):
            return cls[len("language-") :]
        if cls_lower.startswith("lang-"):
            return cls[len("lang-") :]
        if cls_lower.startswith("highlight-"):
            return cls[len("highlight-") :]
    return ""


class MonolithMarkdownConverter(MarkdownConverter):
    """Custom MarkdownConverter that strips Base64 blobs and cleans web boilerplate."""

    def convert_img(self, el, text, parent_tags):
        alt = el.attrs.get("alt", "") or ""
        src = el.attrs.get("src", "") or ""
        title = el.attrs.get("title", "")

        # Strictly avoid embedding raw binary Base64 data URIs
        if src.startswith("data:"):
            img_alt = alt.strip() if alt.strip() else "Image"
            return f"![{img_alt}](<embedded-image>)"

        title_part = f' "{title}"' if title else ""
        return f"![{alt}]({src}{title_part})"

    def convert_a(self, el, text, parent_tags):
        href = el.attrs.get("href", "") or ""
        # Clean javascript: or empty pseudolinks
        if not href or href.strip().lower().startswith("javascript:"):
            return text.strip()
        return super().convert_a(el, text, parent_tags)


class HTMLParser(BaseParser):
    """Parser for HTML documents, web pages, and Monolith/SingleFile offline archives."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        raw_bytes = filepath.read_bytes()
        html_text = self._decode_html_bytes(raw_bytes)
        return self.parse_html_string(html_text, filepath)

    def parse_html_string(self, html_text: str, filepath: Path) -> Tuple[DocumentMetadata, str]:
        metadata = self.build_initial_metadata(filepath)
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Extract Web & Monolith metadata
        title = self._extract_title(soup, filepath)
        if title:
            metadata.title = title

        source_url = self._extract_source_url(soup)
        meta_description = self._extract_meta_content(soup, ["description", "og:description", "twitter:description"])
        meta_author = self._extract_meta_content(soup, ["author", "article:author"])

        # 2. Clean web clutter and non-content tags
        # Drop script, style, noscript, svg, template, and head
        for tag_name in ("script", "style", "noscript", "template", "svg", "canvas", "head", "iframe"):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 3. Convert HTML tree to Markdown
        converter = MonolithMarkdownConverter(
            heading_style="ATX",
            code_language_callback=_extract_code_language,
            strip=["script", "style"],
        )
        body_soup = soup.body if soup.body else soup
        markdown_body = converter.convert_soup(body_soup).strip()

        # 4. Post-process Markdown content
        # Clean excessive newlines
        markdown_body = re.sub(r"\n{3,}", "\n\n", markdown_body).strip()

        # If body doesn't start with a header and we found a title, prepend it
        if title and not markdown_body.startswith("#"):
            markdown_body = f"# {title}\n\n{markdown_body}"

        metadata.extracted_text = markdown_body
        words = markdown_body.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:60])

        return metadata, markdown_body

    @staticmethod
    def _decode_html_bytes(raw_bytes: bytes) -> str:
        """Decode raw HTML bytes trying charset declarations then common fallbacks."""
        # Quick check for charset in first 1024 bytes
        prefix = raw_bytes[:1024].decode("ascii", errors="ignore").lower()
        match = re.search(r'charset=["\']?([a-zA-Z0-9_\-]+)', prefix)
        if match:
            declared = match.group(1).strip()
            try:
                return raw_bytes.decode(declared)
            except Exception:
                pass

        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-15"):
            try:
                return raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue

        return raw_bytes.decode("utf-8", errors="replace")

    def _decode_html(self, raw_bytes: bytes) -> str:
        return self._decode_html_bytes(raw_bytes)

    def _extract_title(self, soup: BeautifulSoup, filepath: Path) -> str:
        """Extract title from <title>, OpenGraph tags, or first <h1>."""
        if soup.title and soup.title.string:
            clean = soup.title.string.strip()
            if clean:
                return clean

        og_title = self._extract_meta_content(soup, ["og:title", "twitter:title"])
        if og_title:
            return og_title

        first_h1 = soup.find("h1")
        if first_h1:
            clean_h1 = first_h1.get_text().strip()
            if clean_h1:
                return clean_h1

        return filepath.stem

    def _extract_meta_content(self, soup: BeautifulSoup, names: list[str]) -> Optional[str]:
        """Extract content from <meta> tags matching any of the specified names."""
        for name in names:
            # Check name attribute
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
            # Check property attribute (for OpenGraph)
            tag = soup.find("meta", attrs={"property": name})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    def _extract_source_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract source URL from Monolith comments, canonical links, or base tags."""
        # 1. Monolith / SingleFile comment header
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            comment_str = str(comment).strip()
            for pattern in MONOLITH_URL_PATTERNS:
                m = pattern.search(comment_str)
                if m:
                    return m.group(1).rstrip(" -;\"'")

        # 2. Canonical link
        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical and canonical.get("href"):
            return canonical["href"].strip()

        # 3. Base href
        base = soup.find("base", attrs={"href": True})
        if base and base.get("href"):
            return base["href"].strip()

        # 4. OpenGraph URL
        og_url = self._extract_meta_content(soup, ["og:url"])
        if og_url:
            return og_url

        return None
