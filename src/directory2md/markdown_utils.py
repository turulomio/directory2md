"""Markdown utilities using markdown-it-py and PyYAML for frontmatter processing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yaml
from markdown_it import MarkdownIt

from directory2md.models import DocumentMetadata


# Initialize MarkdownIt parser
md_parser = MarkdownIt("commonmark", {"breaks": True, "html": True})


def sanitize_unicode(text: str) -> str:
    """Sanitize lone surrogates or unencodable characters for safe UTF-8 handling.

    PDFs with corrupted font encodings or raw binary extracts may contain unpaired
    Unicode surrogate code points (\\ud800-\\udfff), which fail standard UTF-8 encoding.
    This helper replaces them with standard replacement characters.
    """
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8")


def validate_markdown(text: str) -> bool:
    """Validate that text parses properly with markdown-it-py.

    Args:
        text: Markdown text content.

    Returns:
        True if parsed successfully.
    """
    try:
        sanitized = sanitize_unicode(text)
        tokens = md_parser.parse(sanitized)
        return isinstance(tokens, list)
    except Exception:
        return False


def extract_title_from_markdown(text: str) -> Optional[str]:
    """Extract the first h1/h2 title from Markdown tokens using markdown-it-py.

    Args:
        text: Markdown text content.

    Returns:
        Heading text or None.
    """
    try:
        sanitized = sanitize_unicode(text)
        tokens = md_parser.parse(sanitized)
        for i, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag in ("h1", "h2") and i + 1 < len(tokens):
                content = token.content if hasattr(token, "content") and token.content else tokens[i + 1].content.strip()
                if content:
                    return sanitize_unicode(content)
    except Exception:
        pass
    return None


def serialize_document(
    metadata: DocumentMetadata,
    markdown_content: str,
    extra_frontmatter: Optional[Dict[str, Any]] = None,
) -> str:
    """Serialize document metadata as YAML frontmatter followed by markdown content.

    Args:
        metadata: Document metadata.
        markdown_content: Extracted markdown body text.
        extra_frontmatter: Optional additional dictionary key-values to include.

    Returns:
        Complete Markdown document string with YAML frontmatter.
    """
    fm_data: Dict[str, Any] = metadata.to_dict()
    if "conversion_time" not in fm_data:
        fm_data["conversion_time"] = metadata.conversion_time if metadata.conversion_time is not None else 0.0
    fm_data["conversion_date"] = datetime.now().isoformat(timespec="seconds")

    if extra_frontmatter:
        fm_data.update(extra_frontmatter)

    # Clean None values and sanitize string fields in frontmatter
    cleaned_fm: Dict[str, Any] = {}
    for k, v in fm_data.items():
        if v is None:
            continue
        if isinstance(v, str):
            cleaned_fm[k] = sanitize_unicode(v)
        else:
            cleaned_fm[k] = v

    yaml_header = yaml.dump(
        cleaned_fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    body = sanitize_unicode(markdown_content).strip()
    return f"---\n{yaml_header}\n---\n\n{body}\n"


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Extract YAML frontmatter and body from a Markdown document.

    Args:
        content: Full text of a markdown document.

    Returns:
        Tuple of (frontmatter_dict, body_text).
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) >= 3:
        raw_fm = parts[1]
        body = parts[2].lstrip("\r\n")
        try:
            parsed_fm = yaml.safe_load(raw_fm)
            if isinstance(parsed_fm, dict):
                return parsed_fm, body
        except Exception:
            pass

    return {}, content
