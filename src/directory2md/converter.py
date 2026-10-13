"""Directory to Markdown conversion engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import email
from email import policy
from email.parser import BytesParser
import logging
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
from typing import Callable, List, Optional, Tuple
import zipfile

from directory2md.config import Config
from directory2md.markdown_utils import (
    extract_title_from_markdown,
    serialize_document,
    validate_markdown,
)
from directory2md.models import DocumentMetadata, EmailHeaders
from directory2md.parsers import (
    get_parser_for_file,
    is_archive_file,
    is_container_file,
    is_email_file,
    email_has_attachments,
)
from directory2md.parsers.base import calculate_sha256

logger = logging.getLogger("directory2md")


@dataclass
class ConversionStats:
    """Statistics for directory conversion."""

    total_scanned: int = 0
    converted: int = 0
    skipped: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class DirectoryConverter:
    """Recursively converts source directory tree into markdown directory tree."""

    def __init__(
        self,
        max_age_days: int = 180,
        force: bool | str | Path = False,
        verbose: bool = False,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        config: Optional[Config] = None,
    ) -> None:
        """Initialize converter.

        Args:
            max_age_days: Number of days threshold before an existing .md file is refreshed.
            force: If True, always convert regardless of age. If a path or string, only convert that file/dir recursively.
            verbose: Enable verbose logging.
            log_callback: Optional callback receiving progress log messages.
            progress_callback: Optional callback receiving (current, total, filename) for progress reporting.
            config: Optional Config instance for AI and format settings.
        """
        self.max_age_days = max_age_days
        self.force = force
        self.verbose = verbose
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback
        self.config = config

    def log(self, message: str) -> None:
        """Log message via callback and logger."""
        self.log_callback(message)
        if self.verbose:
            logger.info(message)

    def should_update(
        self,
        src_path: Path,
        dst_target: Path,
        is_container: bool,
    ) -> bool:
        """Check whether a target file or container needs conversion.

        Updates if:
        1. Destination does not exist.
        2. Force flag is True.
        3. Destination conversion/modification is older than max_age_days.
        4. Source file was modified more recently than destination target.

        Args:
            src_path: Path to source file.
            dst_target: Destination path (file or container directory).
            is_container: Whether target is a container directory.

        Returns:
            True if target should be converted/updated, False to skip.
        """
        if self.force:
            return True

        if not dst_target.exists():
            return True

        # For containers, check the primary markdown summary file inside it
        if is_container:
            primary_md = dst_target / f"{src_path.name}.md"
            if not primary_md.exists():
                return True
            eval_target = primary_md
        else:
            eval_target = dst_target

        try:
            target_stat = eval_target.stat()
            target_mtime = datetime.fromtimestamp(target_stat.st_mtime)
            src_stat = src_path.stat()
            src_mtime = datetime.fromtimestamp(src_stat.st_mtime)
            now = datetime.now()

            # Age threshold check
            age = now - target_mtime
            if age > timedelta(days=self.max_age_days):
                return True

            # Source newer than destination check
            if src_mtime > target_mtime:
                return True

            return False
        except Exception:
            return True

    def convert_directory(
        self,
        src_dir: Path | str,
        dst_dir: Path | str,
    ) -> ConversionStats:
        """Recursively convert entire directory to destination markdown directory.

        Args:
            src_dir: Root directory of source files.
            dst_dir: Root directory of destination markdown files.

        Returns:
            ConversionStats summary.
        """
        src_root = Path(src_dir).resolve()
        dst_root = Path(dst_dir).resolve()

        if not src_root.exists() or not src_root.is_dir():
            raise ValueError(f"Source directory '{src_root}' does not exist or is not a directory.")

        if dst_root == src_root or dst_root.is_relative_to(src_root):
            raise ValueError(
                f"Destination directory '{dst_root}' cannot be inside or the same as the source directory '{src_root}'."
            )

        dst_root.mkdir(parents=True, exist_ok=True)
        stats = ConversionStats()

        # Check if force specifies a targeted file or directory
        force_target_path: Optional[Path] = None
        if isinstance(self.force, (str, Path)):
            force_str = str(self.force).strip()
            if force_str in ("*", "true", "True", "1"):
                self.force = True
            elif force_str in ("", "false", "False", "0"):
                self.force = False
            else:
                force_target_path = self._resolve_force_target(src_root, force_str)
                if not force_target_path.exists():
                    raise ValueError(
                        f"Target path '{self.force}' specified in --force does not exist in source directory '{src_root}'."
                    )

        # Collect all files to process
        files_to_process: List[Tuple[Path, Path]] = []
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel_dir = Path(dirpath).relative_to(src_root)
            current_dst_dir = dst_root / rel_dir
            current_dst_dir.mkdir(parents=True, exist_ok=True)

            for filename in filenames:
                src_file = Path(dirpath) / filename
                rel_file = rel_dir / filename if str(rel_dir) != "." else Path(filename)

                # When a force target is specified, filter only that file or directory members recursively
                if force_target_path is not None:
                    if src_file != force_target_path and not src_file.is_relative_to(force_target_path):
                        continue

                files_to_process.append((src_file, rel_file))

        total_files = len(files_to_process)

        for idx, (src_file, rel_file) in enumerate(files_to_process, start=1):
            if self.progress_callback:
                self.progress_callback(idx - 1, total_files, str(rel_file))
            stats.total_scanned += 1

            try:
                self._process_file(src_file, rel_file, dst_root, stats)
            except Exception as exc:
                err_msg = f"Failed processing '{src_file}': {exc}"
                logger.error(err_msg, exc_info=True)
                stats.errors.append((str(src_file), str(exc)))

            if self.progress_callback:
                self.progress_callback(idx, total_files, str(rel_file))

        return stats

    def _resolve_force_target(self, src_root: Path, target_str: str) -> Path:
        """Resolve a targeted path string specified in force option."""
        target = Path(target_str)
        src_resolved = src_root.resolve()

        if target.is_absolute():
            resolved = target.resolve()
            if not (resolved == src_resolved or resolved.is_relative_to(src_resolved)):
                raise ValueError(
                    f"Target path '{target_str}' specified in --force is outside source directory '{src_root}'."
                )
            if not resolved.exists():
                raise ValueError(
                    f"Target path '{target_str}' specified in --force does not exist in source directory '{src_root}'."
                )
            return resolved

        candidate_src = (src_resolved / target).resolve()
        candidate_cwd = target.resolve()

        if candidate_src == src_resolved or candidate_src.is_relative_to(src_resolved):
            if candidate_src.exists():
                return candidate_src
            if candidate_cwd.exists() and (candidate_cwd == src_resolved or candidate_cwd.is_relative_to(src_resolved)):
                return candidate_cwd
            raise ValueError(
                f"Target path '{target_str}' specified in --force does not exist in source directory '{src_root}'."
            )

        if candidate_cwd.exists() and (candidate_cwd == src_resolved or candidate_cwd.is_relative_to(src_resolved)):
            return candidate_cwd

        raise ValueError(
            f"Target path '{target_str}' specified in --force is outside source directory '{src_root}'."
        )

    def _process_file(
        self,
        src_file: Path,
        rel_file: Path,
        dst_root: Path,
        stats: ConversionStats,
    ) -> None:
        """Route file processing based on whether it is a container or normal file."""
        if is_container_file(src_file):
            # Container: directory destination
            dst_container = dst_root / rel_file
            if not self.should_update(src_file, dst_container, is_container=True):
                self.log(f"Skipping up-to-date container: {rel_file}")
                stats.skipped += 1
                return

            self.log(f"Converting container: {rel_file} -> {dst_container.name}/")
            dst_container.mkdir(parents=True, exist_ok=True)

            if is_archive_file(src_file):
                self._convert_archive(src_file, rel_file, dst_container)
            elif is_email_file(src_file):
                self._convert_email_container(src_file, rel_file, dst_container)

            stats.converted += 1
        else:
            # Normal file: .md suffix added
            dst_file = dst_root / f"{rel_file}.md"
            if not self.should_update(src_file, dst_file, is_container=False):
                self.log(f"Skipping up-to-date file: {rel_file}")
                stats.skipped += 1
                return

            self.log(f"Converting file: {rel_file} -> {dst_file.name}")
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            self._convert_single_file(src_file, rel_file, dst_file)
            stats.converted += 1

    def _convert_single_file(
        self,
        src_file: Path,
        rel_file: Path,
        dst_file: Path,
        extra_frontmatter: Optional[dict] = None,
    ) -> None:
        """Convert a single standard document into a Markdown file with frontmatter."""
        start_time = time.perf_counter()
        parser = get_parser_for_file(src_file, config=self.config)
        metadata, content = parser.parse(src_file)

        metadata.filepath = str(src_file.resolve())
        metadata.relative_path = str(rel_file)

        # Infer title from markdown headings if title equals stem
        inferred_title = extract_title_from_markdown(content)
        if inferred_title and metadata.title == src_file.stem:
            metadata.title = inferred_title

        # Validate with markdown-it-py
        validate_markdown(content)

        metadata.conversion_time = round(time.perf_counter() - start_time, 4)

        fm_extras = {
            "original_path": str(src_file.resolve()),
        }
        if extra_frontmatter:
            fm_extras.update(extra_frontmatter)

        full_md = serialize_document(metadata, content, extra_frontmatter=fm_extras)
        dst_file.write_text(full_md, encoding="utf-8")

    def _convert_archive(
        self,
        archive_path: Path,
        rel_archive: Path,
        dst_container: Path,
    ) -> None:
        """Convert a compressed archive into a directory with its summary and member files."""
        start_time = time.perf_counter()
        name_lower = archive_path.name.lower()
        parser = get_parser_for_file(archive_path, config=self.config)
        archive_meta, archive_summary = parser.parse(archive_path)
        archive_meta.filepath = str(archive_path.resolve())
        archive_meta.relative_path = str(rel_archive)
        archive_meta.conversion_time = round(time.perf_counter() - start_time, 4)

        # 1. Write archive primary summary file: <archive_name>.md
        primary_md = dst_container / f"{archive_path.name}.md"
        primary_content = serialize_document(
            archive_meta,
            archive_summary,
            extra_frontmatter={"original_path": str(archive_path.resolve()), "is_archive_root": True},
        )
        primary_md.write_text(primary_content, encoding="utf-8")

        # 2. Extract and recursively process children
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            extracted_files: List[Tuple[str, Path]] = []

            if name_lower.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for info in zf.infolist():
                        if info.is_dir() or ".." in info.filename or info.filename.startswith("/"):
                            continue
                        extracted = zf.extract(info, tmp_path)
                        extracted_files.append((info.filename, Path(extracted)))
            elif (
                name_lower.endswith(".tar.gz")
                or name_lower.endswith(".tgz")
                or name_lower.endswith(".tar.bz2")
                or name_lower.endswith(".tbz2")
                or name_lower.endswith(".tar")
            ):
                with tarfile.open(archive_path, "r:*") as tf:
                    members = [m for m in tf.getmembers() if m.isfile()]
                    for m in members:
                        if ".." in m.name or m.name.startswith("/"):
                            continue
                        try:
                            tf.extract(m, tmp_path, filter="data" if hasattr(tarfile, "data_filter") else None)
                            inner = tmp_path / m.name
                            if inner.is_file():
                                extracted_files.append((m.name, inner))
                        except Exception as e:
                            logger.warning(f"Failed extracting {m.name} from {archive_path}: {e}")

            # Process each member into dst_container
            for member_rel_str, member_extracted_path in extracted_files:
                member_rel = Path(member_rel_str)
                member_dst_target = dst_container / member_rel

                if is_container_file(member_extracted_path):
                    # Nested container
                    member_dst_dir = dst_container / member_rel
                    member_dst_dir.mkdir(parents=True, exist_ok=True)
                    if is_archive_file(member_extracted_path):
                        self._convert_archive(member_extracted_path, member_rel, member_dst_dir)
                    elif is_email_file(member_extracted_path):
                        self._convert_email_container(member_extracted_path, member_rel, member_dst_dir)
                else:
                    member_dst_file = dst_container / f"{member_rel}.md"
                    member_dst_file.parent.mkdir(parents=True, exist_ok=True)
                    self._convert_single_file(
                        member_extracted_path,
                        member_rel,
                        member_dst_file,
                        extra_frontmatter={
                            "original_path": str(archive_path.resolve()),
                            "archive_member": member_rel_str,
                        },
                    )

    def _convert_email_container(
        self,
        email_path: Path,
        rel_email: Path,
        dst_container: Path,
    ) -> None:
        """Convert an email with attachments into a container directory."""
        suffix = email_path.suffix.lower()
        if suffix == ".msg":
            self._convert_msg_container(email_path, rel_email, dst_container)
        else:
            self._convert_eml_container(email_path, rel_email, dst_container)

    def _convert_eml_container(
        self,
        email_path: Path,
        rel_email: Path,
        dst_container: Path,
    ) -> None:
        """Extract MIME .eml body to <name>.md and attachments to <att>.md."""
        start_time = time.perf_counter()
        with open(email_path, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        sender = str(msg.get("From", "")) if msg.get("From") else None
        to_hdr = str(msg.get("To", "")) if msg.get("To") else ""
        to_list = [p.strip() for p in to_hdr.split(",") if p.strip()]
        cc_hdr = str(msg.get("Cc", "")) if msg.get("Cc") else ""
        cc_list = [p.strip() for p in cc_hdr.split(",") if p.strip()]
        subject = str(msg.get("Subject", "")) if msg.get("Subject") else None
        date_hdr = str(msg.get("Date", "")) if msg.get("Date") else None
        msg_id = str(msg.get("Message-ID", "")) if msg.get("Message-ID") else None

        body_text = ""
        attachments_to_process: List[Tuple[str, bytes]] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()
                filename = part.get_filename()

                if filename or "attachment" in content_disposition:
                    att_name = filename or f"attachment_{len(attachments_to_process)+1}.bin"
                    safe_name = Path(att_name).name
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments_to_process.append((safe_name, payload))
                else:
                    if content_type == "text/plain":
                        try:
                            body_text += part.get_content() + "\n"
                        except Exception:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text += payload.decode("utf-8", errors="replace") + "\n"
                    elif content_type == "text/html" and not body_text:
                        try:
                            body_text += part.get_content() + "\n"
                        except Exception:
                            pass
        else:
            try:
                body_text = msg.get_content()
            except Exception:
                payload = msg.get_payload(decode=True)
                body_text = payload.decode("utf-8", errors="replace") if payload else str(msg.get_payload())

        email_headers = EmailHeaders(
            sender=sender,
            to=to_list,
            cc=cc_list,
            subject=subject,
            date=date_hdr,
            message_id=msg_id,
            attachments=[name for name, _ in attachments_to_process],
        )

        headers_md = (
            f"**From:** {sender or ''}  \n"
            f"**To:** {', '.join(to_list)}  \n"
            + (f"**Cc:** {', '.join(cc_list)}  \n" if cc_list else "")
            + f"**Subject:** {subject or ''}  \n"
            f"**Date:** {date_hdr or ''}  \n"
            + (f"**Attachments:** {', '.join(email_headers.attachments)}  \n" if email_headers.attachments else "")
            + "\n---\n\n"
        )
        email_full_text = headers_md + body_text.strip()

        # 1. Write primary email markdown: <email_name>.md
        primary_md = dst_container / f"{email_path.name}.md"
        meta = DocumentMetadata(
            filepath=str(email_path.resolve()),
            relative_path=str(rel_email),
            filename=email_path.name,
            extension=email_path.suffix.lower(),
            title=subject or email_path.stem,
            file_size_bytes=email_path.stat().st_size,
            sha256_hash=calculate_sha256(email_path),
            word_count=len(email_full_text.split()),
            extracted_text=email_full_text,
            email_headers=email_headers,
            contained_files=[name for name, _ in attachments_to_process],
            conversion_time=round(time.perf_counter() - start_time, 4),
        )
        primary_md.write_text(
            serialize_document(meta, email_full_text, extra_frontmatter={"original_path": str(email_path.resolve())}),
            encoding="utf-8",
        )

        # 2. Extract each attachment and convert
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for att_name, att_bytes in attachments_to_process:
                temp_file = tmp_path / att_name
                temp_file.write_bytes(att_bytes)

                if is_container_file(temp_file):
                    att_dst_dir = dst_container / att_name
                    att_dst_dir.mkdir(parents=True, exist_ok=True)
                    if is_archive_file(temp_file):
                        self._convert_archive(temp_file, Path(att_name), att_dst_dir)
                    elif is_email_file(temp_file):
                        self._convert_email_container(temp_file, Path(att_name), att_dst_dir)
                else:
                    att_dst_file = dst_container / f"{att_name}.md"
                    self._convert_single_file(
                        temp_file,
                        Path(att_name),
                        att_dst_file,
                        extra_frontmatter={
                            "original_path": str(email_path.resolve()),
                            "attachment_name": att_name,
                        },
                    )

    def _convert_msg_container(
        self,
        msg_path: Path,
        rel_msg: Path,
        dst_container: Path,
    ) -> None:
        """Convert an Outlook .msg file with attachments into a container directory."""
        start_time = time.perf_counter()
        import extract_msg

        msg = extract_msg.Message(str(msg_path))
        sender = msg.sender
        to_list = [p.strip() for p in str(msg.to or "").split(";") if p.strip()]
        cc_list = [p.strip() for p in str(msg.cc or "").split(";") if p.strip()]
        subject = msg.subject
        date_hdr = str(msg.date) if msg.date else None
        body_text = msg.body or ""

        att_files: List[Tuple[str, bytes]] = []
        if hasattr(msg, "attachments") and msg.attachments:
            for att in msg.attachments:
                att_name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "attachment.bin"
                safe_name = Path(att_name).name
                att_data = getattr(att, "data", None)
                if att_data:
                    att_files.append((safe_name, att_data))

        email_headers = EmailHeaders(
            sender=sender,
            to=to_list,
            cc=cc_list,
            subject=subject,
            date=date_hdr,
            attachments=[name for name, _ in att_files],
        )

        headers_md = (
            f"**From:** {sender or ''}  \n"
            f"**To:** {', '.join(to_list)}  \n"
            + (f"**Cc:** {', '.join(cc_list)}  \n" if cc_list else "")
            + f"**Subject:** {subject or ''}  \n"
            f"**Date:** {date_hdr or ''}  \n"
            + (f"**Attachments:** {', '.join(email_headers.attachments)}  \n" if email_headers.attachments else "")
            + "\n---\n\n"
        )
        full_text = headers_md + body_text.strip()

        primary_md = dst_container / f"{msg_path.name}.md"
        meta = DocumentMetadata(
            filepath=str(msg_path.resolve()),
            relative_path=str(rel_msg),
            filename=msg_path.name,
            extension=msg_path.suffix.lower(),
            title=subject or msg_path.stem,
            file_size_bytes=msg_path.stat().st_size,
            sha256_hash=calculate_sha256(msg_path),
            word_count=len(full_text.split()),
            extracted_text=full_text,
            email_headers=email_headers,
            contained_files=[name for name, _ in att_files],
            conversion_time=round(time.perf_counter() - start_time, 4),
        )
        primary_md.write_text(
            serialize_document(meta, full_text, extra_frontmatter={"original_path": str(msg_path.resolve())}),
            encoding="utf-8",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for att_name, att_bytes in att_files:
                temp_file = tmp_path / att_name
                temp_file.write_bytes(att_bytes)

                if is_container_file(temp_file):
                    att_dst_dir = dst_container / att_name
                    att_dst_dir.mkdir(parents=True, exist_ok=True)
                    if is_archive_file(temp_file):
                        self._convert_archive(temp_file, Path(att_name), att_dst_dir)
                    elif is_email_file(temp_file):
                        self._convert_email_container(temp_file, Path(att_name), att_dst_dir)
                else:
                    att_dst_file = dst_container / f"{att_name}.md"
                    self._convert_single_file(
                        temp_file,
                        Path(att_name),
                        att_dst_file,
                        extra_frontmatter={
                            "original_path": str(msg_path.resolve()),
                            "attachment_name": att_name,
                        },
                    )


def convert_directory(
    src_dir: Path | str,
    dst_dir: Path | str,
    max_age_days: int = 180,
    force: bool | str | Path = False,
    verbose: bool = False,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    config: Optional[Config] = None,
) -> ConversionStats:
    """Convenience helper to convert a directory to markdown with default settings."""
    converter = DirectoryConverter(
        max_age_days=max_age_days,
        force=force,
        verbose=verbose,
        log_callback=log_callback,
        progress_callback=progress_callback,
        config=config,
    )
    return converter.convert_directory(src_dir, dst_dir)
