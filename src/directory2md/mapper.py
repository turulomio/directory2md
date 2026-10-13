"""Bidirectional path mapping functions between original files and markdown converted files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from directory2md.markdown_utils import parse_frontmatter
from directory2md.parsers import is_archive_file, is_container_file, ARCHIVE_EXTENSIONS


CONTAINER_EXT_PARTS = (
    ".tar.gz",
    ".tar.bz2",
    ".tgz",
    ".tbz2",
    ".zip",
    ".tar",
    ".eml",
    ".msg",
)


@dataclass
class PathMapping:
    """Detailed result of mapping resolution."""

    original_path: Path
    md_path: Path
    is_container: bool
    is_container_member: bool
    container_original_path: Optional[Path] = None
    member_subpath: Optional[str] = None


def get_md_path(
    original_path: Union[Path, str],
    src_dir: Optional[Union[Path, str]] = None,
    dst_dir: Optional[Union[Path, str]] = None,
    primary_file: bool = False,
) -> Path:
    """Calculate destination markdown path corresponding to an original file.

    For normal files, appends '.md' (e.g. 'doc.pdf' -> 'doc.pdf.md').
    For containers (archives, or emails with attachments), returns the container directory
    (e.g. 'archive.zip' -> 'archive.zip/'), or if primary_file=True, the container's
    main summary markdown file ('archive.zip/archive.zip.md').

    Args:
        original_path: Path to the original file.
        src_dir: Root directory of source files (optional).
        dst_dir: Root directory of destination files (optional).
        primary_file: If True and target is a container, return the primary .md file inside it.

    Returns:
        Corresponding destination Path.
    """
    orig = Path(original_path)

    # Determine relative path from src_dir if provided
    if src_dir is not None:
        src = Path(src_dir).resolve()
        resolved_orig = orig.resolve() if orig.is_absolute() else (src / orig).resolve()
        try:
            rel = resolved_orig.relative_to(src)
        except ValueError:
            rel = orig
    else:
        rel = orig

    # Determine if it is a container
    is_container = False
    if orig.exists():
        is_container = is_container_file(orig)
    else:
        # Check by extension if file does not exist on disk
        is_container = is_archive_file(orig)

    if dst_dir is not None:
        dst = Path(dst_dir)
        if is_container:
            container_dir = dst / rel
            return container_dir / f"{rel.name}.md" if primary_file else container_dir
        else:
            return dst / f"{rel}.md"
    else:
        if is_container:
            return rel / f"{rel.name}.md" if primary_file else rel
        else:
            return Path(f"{rel}.md")


def get_original_path(
    md_path: Union[Path, str],
    src_dir: Optional[Union[Path, str]] = None,
    dst_dir: Optional[Union[Path, str]] = None,
) -> Path:
    """Calculate the original file path corresponding to a markdown file or directory.

    If the markdown file exists on disk and contains YAML frontmatter with 'original_path',
    that recorded path is preferred. Otherwise, the path structure is parsed:
    - Normal file: strips '.md' extension.
    - File inside a container directory: returns the container file path in source.

    Args:
        md_path: Path to the markdown file or container directory.
        src_dir: Root directory of source files (optional).
        dst_dir: Root directory of destination files (optional).

    Returns:
        Corresponding original file Path in the source directory.
    """
    target = Path(md_path)

    # 1. Check if file exists and has frontmatter with original_path
    if target.is_file():
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
            fm, _ = parse_frontmatter(text)
            if "original_path" in fm and fm["original_path"]:
                recorded = Path(fm["original_path"])
                if src_dir is not None:
                    # If recorded path is already rooted at src_dir or absolute
                    if recorded.is_absolute() and recorded.exists():
                        return recorded
                    # Check if relative to src_dir
                    candidate = Path(src_dir) / recorded.name
                    if candidate.exists():
                        return candidate
                return recorded
        except Exception:
            pass

    # 2. Pure path resolution
    if dst_dir is not None:
        dst = Path(dst_dir).resolve()
        resolved_target = target.resolve() if target.is_absolute() else (dst / target).resolve()
        try:
            rel = resolved_target.relative_to(dst)
        except ValueError:
            rel = target
    else:
        rel = target

    parts = list(rel.parts)
    if not parts:
        return Path(src_dir) if src_dir else target

    # Search for container directory in the path components
    container_index = -1
    for idx, part in enumerate(parts):
        part_lower = part.lower()
        if any(part_lower.endswith(ext) for ext in CONTAINER_EXT_PARTS):
            # Check if this part is an archive or email directory
            # If it is the last part and ends with .md, it's a file, not a container directory
            if idx == len(parts) - 1 and part_lower.endswith(".md"):
                # E.g. 'foo.zip.md' or 'file.txt.md'
                continue
            container_index = idx
            break

    if container_index >= 0:
        # The path is inside or is the container directory
        container_rel = Path(*parts[: container_index + 1])
        return Path(src_dir) / container_rel if src_dir else container_rel

    # Normal file: strip trailing '.md'
    str_rel = str(rel)
    if str_rel.endswith(".md"):
        orig_rel_str = str_rel[:-3]
    else:
        orig_rel_str = str_rel

    orig_rel = Path(orig_rel_str)
    return Path(src_dir) / orig_rel if src_dir else orig_rel


def resolve_mapping_details(
    md_path: Union[Path, str],
    src_dir: Union[Path, str],
    dst_dir: Union[Path, str],
) -> PathMapping:
    """Resolve full mapping details including whether the target is a container member.

    Args:
        md_path: Markdown path.
        src_dir: Root source directory.
        dst_dir: Root destination directory.

    Returns:
        Populated PathMapping dataclass.
    """
    src = Path(src_dir).resolve()
    dst = Path(dst_dir).resolve()
    target = Path(md_path)
    resolved_target = target.resolve() if target.is_absolute() else (dst / target).resolve()

    try:
        rel = resolved_target.relative_to(dst)
    except ValueError:
        rel = target

    orig_path = get_original_path(md_path, src, dst)
    parts = list(rel.parts)

    container_idx = -1
    for idx, part in enumerate(parts):
        part_lower = part.lower()
        if any(part_lower.endswith(ext) for ext in CONTAINER_EXT_PARTS):
            if idx == len(parts) - 1 and part_lower.endswith(".md"):
                continue
            container_idx = idx
            break

    if container_idx >= 0:
        container_rel = Path(*parts[: container_idx + 1])
        container_orig = src / container_rel
        is_member = len(parts) > container_idx + 1
        member_subpath = "/".join(parts[container_idx + 1 :]) if is_member else None
        return PathMapping(
            original_path=orig_path,
            md_path=resolved_target,
            is_container=not is_member,
            is_container_member=is_member,
            container_original_path=container_orig,
            member_subpath=member_subpath,
        )
    else:
        return PathMapping(
            original_path=orig_path,
            md_path=resolved_target,
            is_container=False,
            is_container_member=False,
        )
