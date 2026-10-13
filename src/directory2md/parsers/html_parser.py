"""HTML and Monolith web page parser for directory2md."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup, Comment
from markdownify import MarkdownConverter

from directory2md.config import Config
from directory2md.models import DocumentMetadata
from directory2md.parsers.base import BaseParser

logger = logging.getLogger("directory2md.parsers.html")

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
        metadata = self.build_initial_metadata(filepath)
        raw_bytes = filepath.read_bytes()

        # Multi-encoding decoding
        html_text = self._decode_html(raw_bytes)
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

    def _decode_html(self, raw_bytes: bytes) -> str:
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
