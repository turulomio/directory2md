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


def validate_markdown(text: str) -> bool:
    """Validate that text parses properly with markdown-it-py.

    Args:
        text: Markdown text content.

    Returns:
        True if parsed successfully.
    """
    try:
        tokens = md_parser.parse(text)
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
        tokens = md_parser.parse(text)
        for i, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag in ("h1", "h2") and i + 1 < len(tokens):
                content = tokens[i + 1].content.strip()
                if content:
                    return content
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
    fm_data["conversion_date"] = datetime.now().isoformat(timespec="seconds")

    if extra_frontmatter:
        fm_data.update(extra_frontmatter)

    # Clean None values from frontmatter
    fm_data = {k: v for k, v in fm_data.items() if v is not None}

    yaml_header = yaml.dump(
        fm_data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()

    body = markdown_content.strip()
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
