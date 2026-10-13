"""Email file parser for RFC-822 / MIME (.eml) and Outlook (.msg) messages.

Extracts header fields (From, To, Cc, Subject, Date, Message-ID), decodes
multipart plain text and HTML bodies, and recursively parses attached documents
(PDF, DOCX, XLSX, ODS, ODT, PPTX, TXT, CSV, etc.) to uncover nested intelligence.
"""

from __future__ import annotations

import email
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
import tempfile
from typing import List, Optional, Tuple

from directory2md.models import DocumentMetadata, EmailHeaders
from directory2md.parsers.base import BaseParser


def _clean_recipient_list(header_val: str | None) -> List[str]:
    """Split comma or semicolon-separated recipient strings into a clean list.

    Args:
        header_val: Raw recipient header string (e.g. 'a@b.com, c@d.com; e@f.com').

    Returns:
        List of trimmed individual recipient strings.
    """
    if not header_val:
        return []
    parts = [p.strip() for p in re.split(r"[,;]", header_val) if p.strip()]
    return parts


def _parse_attachment_data(filename: str, raw_data: bytes) -> str:
    """Parse raw bytes of an email attachment using the appropriate document parser.

    Args:
        filename: Name of the attached file.
        raw_data: Raw binary content of the attachment.

    Returns:
        Formatted textual representation of the parsed attachment.
    """
    if not filename or not raw_data:
        return ""

    from directory2md.parsers import get_parser_for_file

    with tempfile.TemporaryDirectory() as tmpdir:
        # Sanitize attachment filename
        safe_name = Path(filename).name
        temp_file = Path(tmpdir) / safe_name
        temp_file.write_bytes(raw_data)

        try:
            parser = get_parser_for_file(temp_file)
            _, extracted_text = parser.parse(temp_file)
            if extracted_text.strip():
                return (
                    f"\n\n--- Email Attachment: {safe_name} ({len(raw_data)} bytes) ---\n"
                    f"{extracted_text.strip()}"
                )
        except Exception as exc:
            return f"\n\n[Attachment {safe_name} could not be parsed: {exc}]"

    return ""


class EmailParser(BaseParser):
    """Parser implementation for email messages (.eml and .msg)."""

    def parse(self, filepath: Path) -> Tuple[DocumentMetadata, str]:
        """Parse email file and extract metadata, structured headers, body text, and attachments.

        Args:
            filepath: Path to the email file.

        Returns:
            Tuple of (:class:`DocumentMetadata`, combined_header_body_and_attachment_text).
        """
        metadata, text, _ = self.parse_with_children(filepath)
        return metadata, text

    def parse_with_children(
        self, filepath: Path
    ) -> Tuple[DocumentMetadata, str, List[Tuple[DocumentMetadata, str]]]:
        """Parse email file, extract headers and body, and return child attachment documents.

        Args:
            filepath: Path to the email file.

        Returns:
            Tuple of (parent_metadata, email_full_text, list_of_child_tuples).
        """
        metadata = self.build_initial_metadata(filepath)
        suffix = filepath.suffix.lower()

        if suffix == ".msg":
            return self._parse_msg_with_children(filepath, metadata)
        else:
            return self._parse_eml_with_children(filepath, metadata)

    def _parse_eml_with_children(
        self, filepath: Path, metadata: DocumentMetadata
    ) -> Tuple[DocumentMetadata, str, List[Tuple[DocumentMetadata, str]]]:
        """Internal parser for standard MIME .eml files extracting child attachments."""
        import hashlib
        from directory2md.extractors.filename_parser import parse_filename

        with open(filepath, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        sender = str(msg.get("From", "")) if msg.get("From") else None
        to_list = _clean_recipient_list(str(msg.get("To", "")))
        cc_list = _clean_recipient_list(str(msg.get("Cc", "")))
        bcc_list = _clean_recipient_list(str(msg.get("Bcc", "")))
        subject = str(msg.get("Subject", "")) if msg.get("Subject") else None
        date_hdr = str(msg.get("Date", "")) if msg.get("Date") else None
        msg_id = str(msg.get("Message-ID", "")) if msg.get("Message-ID") else None

        attachment_names: List[str] = []
        attachment_sections: List[str] = []
        children: List[Tuple[DocumentMetadata, str]] = []

        body_text = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                filename = part.get_filename()

                # Check if this part is an attachment
                if filename or "attachment" in content_disposition:
                    att_name = filename or f"attachment_{len(attachment_names)+1}"
                    safe_name = Path(att_name).name
                    attachment_names.append(safe_name)
                    payload = part.get_payload(decode=True)
                    if payload:
                        att_sha = hashlib.sha256(payload).hexdigest()
                        att_text = _parse_attachment_data(safe_name, payload)
                        if att_text:
                            attachment_sections.append(att_text)

                        # Create child document metadata
                        child_d_str, child_t_str, child_dt, child_title = parse_filename(Path(safe_name))
                        if not child_d_str:
                            child_d_str = metadata.date_str
                            child_t_str = metadata.time_str
                            child_dt = metadata.timestamp

                        # Extract clean text from attachment without header wrapper
                        clean_att_text = att_text.strip()
                        if clean_att_text.startswith("--- Email Attachment:"):
                            lines = clean_att_text.splitlines()
                            if len(lines) > 1:
                                clean_att_text = "\n".join(lines[1:]).strip()

                        child_words = clean_att_text.split()
                        child_meta = DocumentMetadata(
                            filepath=f"{filepath.name}::{safe_name}",
                            relative_path=f"{filepath.name}::{safe_name}",
                            filename=safe_name,
                            extension=Path(safe_name).suffix.lower(),
                            date_str=child_d_str,
                            time_str=child_t_str,
                            timestamp=child_dt,
                            title=child_title or safe_name,
                            file_size_bytes=len(payload),
                            sha256_hash=att_sha,
                            word_count=len(child_words),
                            text_snippet=" ".join(child_words[:50]) + ("..." if len(child_words) > 50 else ""),
                            extracted_text=clean_att_text,
                            parent_document=filepath.name,
                            origin_type="email_attachment",
                        )
                        children.append((child_meta, clean_att_text))
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
                            html_text = part.get_content()
                            body_text += re.sub(r"<[^>]+>", " ", html_text) + "\n"
                        except Exception:
                            pass
        else:
            try:
                body_text = msg.get_content()
            except Exception:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="replace")
                else:
                    body_text = str(msg.get_payload())

        metadata.email_headers = EmailHeaders(
            sender=sender,
            to=to_list,
            cc=cc_list,
            bcc=bcc_list,
            subject=subject,
            date=date_hdr,
            message_id=msg_id,
            attachments=attachment_names,
        )

        headers_summary = (
            f"From: {sender or ''}\n"
            f"To: {', '.join(to_list)}\n"
            f"Cc: {', '.join(cc_list)}\n"
            f"Subject: {subject or ''}\n"
            f"Date: {date_hdr or ''}\n"
            + (f"Attachments: {', '.join(attachment_names)}\n" if attachment_names else "")
            + "\n"
        )
        full_text = headers_summary + body_text.strip() + "".join(attachment_sections)

        words = full_text.split()
        metadata.word_count = len(words)
        metadata.text_snippet = " ".join(words[:60]) + ("..." if len(words) > 60 else "")
        metadata.extracted_text = full_text
        metadata.contained_files = [child_meta.filename for child_meta, _ in children]

        return metadata, full_text, children

    def _parse_msg_with_children(
        self, filepath: Path, metadata: DocumentMetadata
    ) -> Tuple[DocumentMetadata, str, List[Tuple[DocumentMetadata, str]]]:
        """Internal parser for Outlook .msg files extracting child attachments."""
        import hashlib
        from directory2md.extractors.filename_parser import parse_filename

        try:
            import extract_msg

            msg = extract_msg.Message(str(filepath))
            sender = msg.sender
            to_list = _clean_recipient_list(msg.to)
            cc_list = _clean_recipient_list(msg.cc)
            subject = msg.subject
            date_hdr = str(msg.date) if msg.date else None
            body_text = msg.body or ""

            attachment_names: List[str] = []
            attachment_sections: List[str] = []
            children: List[Tuple[DocumentMetadata, str]] = []

            if hasattr(msg, "attachments") and msg.attachments:
                for att in msg.attachments:
                    att_name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "attachment.bin"
                    safe_name = Path(att_name).name
                    attachment_names.append(safe_name)
                    att_data = getattr(att, "data", None)
                    if att_data:
                        att_sha = hashlib.sha256(att_data).hexdigest()
                        att_text = _parse_attachment_data(safe_name, att_data)
                        if att_text:
                            attachment_sections.append(att_text)

                        child_d_str, child_t_str, child_dt, child_title = parse_filename(Path(safe_name))
                        if not child_d_str:
                            child_d_str = metadata.date_str
                            child_t_str = metadata.time_str
                            child_dt = metadata.timestamp

                        clean_att_text = att_text.strip()
                        if clean_att_text.startswith("--- Email Attachment:"):
                            lines = clean_att_text.splitlines()
                            if len(lines) > 1:
                                clean_att_text = "\n".join(lines[1:]).strip()

                        child_words = clean_att_text.split()
                        child_meta = DocumentMetadata(
                            filepath=f"{filepath.name}::{safe_name}",
                            relative_path=f"{filepath.name}::{safe_name}",
                            filename=safe_name,
                            extension=Path(safe_name).suffix.lower(),
                            date_str=child_d_str,
                            time_str=child_t_str,
                            timestamp=child_dt,
                            title=child_title or safe_name,
                            file_size_bytes=len(att_data),
                            sha256_hash=att_sha,
                            word_count=len(child_words),
                            text_snippet=" ".join(child_words[:50]) + ("..." if len(child_words) > 50 else ""),
                            extracted_text=clean_att_text,
                            parent_document=filepath.name,
                            origin_type="email_attachment",
                        )
                        children.append((child_meta, clean_att_text))

            metadata.email_headers = EmailHeaders(
                sender=sender,
                to=to_list,
                cc=cc_list,
                subject=subject,
                date=date_hdr,
                attachments=attachment_names,
            )

            headers_summary = (
                f"From: {sender or ''}\n"
                f"To: {', '.join(to_list)}\n"
                f"Cc: {', '.join(cc_list)}\n"
                f"Subject: {subject or ''}\n"
                f"Date: {date_hdr or ''}\n"
                + (f"Attachments: {', '.join(attachment_names)}\n" if attachment_names else "")
                + "\n"
            )
            full_text = headers_summary + body_text.strip() + "".join(attachment_sections)
            words = full_text.split()
            metadata.word_count = len(words)
            metadata.text_snippet = " ".join(words[:60]) + ("..." if len(words) > 60 else "")
            metadata.extracted_text = full_text
            metadata.contained_files = [child_meta.filename for child_meta, _ in children]

            return metadata, full_text, children
        except Exception:
            empty_meta = self.build_initial_metadata(filepath)
            empty_meta.extracted_text = ""
            return empty_meta, "", []
